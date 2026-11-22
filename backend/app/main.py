"""Local API. Each CAD operation runs in a fresh process and publishes an immutable job."""
import csv
import io
import json
import os
import re
import shutil
from pathlib import Path
from typing import Literal
from uuid import uuid4
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .engines import CADEngineManager, EngineFailure, EngineMode
from .parameters import DEFAULTS, calculate, positions

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs"
JOBS = OUTPUT / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
DIST = ROOT / "frontend" / "dist"

class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    boardWidth: float
    boardHeight: float
    boardThickness: float
    edgeMargin: float
    slotWidth: float
    slotLength: float
    slotSpacing: float
    units: Literal["mm"] = Field(default="mm", exclude=True)

class EngineRequest(BaseModel):
    engine: EngineMode | None = None

class JobRequest(EngineRequest):
    parameters: Parameters
    model_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

class DrawingMetadata(BaseModel):
    title: str = Field(default="Parametric Pegboard", min_length=1, max_length=48)
    part: str = Field(default="PB-001", min_length=1, max_length=24)
    revision: str = Field(default="A", min_length=1, max_length=12)
    material: str = Field(default="Unspecified", min_length=1, max_length=48)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

class DrawingRequest(JobRequest):
    metadata: DrawingMetadata

class JobResponse(BaseModel):
    id: str
    files: dict[str,str]
    evidence: dict

class Preview(BaseModel):
    parameters: Parameters
    calculations: dict
    slots: list[tuple[float,float]]

app = FastAPI(title="Spreadsheet to Drawing", version="1.0.0")

@app.exception_handler(RequestValidationError)
async def invalid_request(_request, error):
    # Validation entries may echo non-finite floats, which JSON cannot encode.
    detail = [{key: issue[key] for key in ("loc", "msg", "type")} for issue in error.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})

def preview(p):
    values = p.model_dump()
    try:
        metrics = calculate(values)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return Preview(parameters=p, calculations=metrics,slots=positions(values, metrics))

def execute(action: str, request=None, mode: EngineMode | None = None):
    parameters = metadata = previous = None
    if request is not None:
        preview(request.parameters)
        parameters = request.parameters.model_dump()
        if request.model_id:
            previous = JOBS / request.model_id
            if not any((previous / name).is_file() for name in ("pegboard.FCStd","pegboard.sc")):
                raise HTTPException(404, "The referenced native model is missing.")
    if isinstance(request, DrawingRequest):
        metadata = request.metadata.model_dump()
    ident = uuid4().hex
    staging = JOBS / (".tmp-" + ident)
    staging.mkdir()
    try:
        try:
            result = CADEngineManager(mode or (request.engine if request else None)).execute(
                staging, action, parameters, metadata, previous)
        except EngineFailure as error:
            raise HTTPException(error.status, str(error), headers={"X-CAD-Engine-Status": "failed"}) from error
        except ValueError as error:
            raise HTTPException(503, str(error)) from error
        publish = staging / "publish"
        publish.mkdir()
        for name in result.files:
            (result.folder / name).replace(publish / name)
        if request:
            (publish / "preview.json").write_text(preview(request.parameters).model_dump_json(), encoding="utf-8")
        publish.replace(JOBS / ident)
        return JobResponse(id=ident, files={name:f"/api/exports/{ident}/{name}" for name in result.files},
                           evidence=result.evidence)
    finally:
        shutil.rmtree(staging,ignore_errors=True)

@app.get("/api/health")
def health():
    try:
        with TemporaryDirectory(dir=JOBS, prefix=".health-") as folder:
            return CADEngineManager().health(Path(folder))
    except ValueError as error:
        return {"status":"unavailable","detail":str(error),"pdf":False}

@app.get("/api/parameters/defaults", response_model=Preview)
def defaults():
    return preview(Parameters(**DEFAULTS))

@app.post("/api/parameters/validate", response_model=Preview)
def validate(p: Parameters):
    return preview(p)

@app.get("/api/model/preview", response_model=Preview)
def model_preview(model_id: str | None = None):
    if model_id is None:
        return defaults()
    if not re.fullmatch(r"[a-f0-9]{32}",model_id):
        raise HTTPException(404,"Model missing.")
    path = JOBS/model_id/"preview.json"
    if not path.is_file():
        raise HTTPException(404,"Model missing.")
    return Preview.model_validate_json(path.read_text())

@app.post("/api/spreadsheet/upload", response_model=Preview)
async def upload(file: UploadFile = File(...)):
    raw = await file.read(1024*1024+1)
    if len(raw) > 1024*1024:
        raise HTTPException(413,"Maximum spreadsheet size is 1 MB.")
    suffix = Path(file.filename or "").suffix.lower()
    try:
        if suffix == ".csv":
            rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        elif suffix == ".xlsx":
            with ZipFile(io.BytesIO(raw)) as book:
                if sum(member.file_size for member in book.infolist()) > 8*1024*1024:
                    raise ValueError("Expanded workbook exceeds 8 MB.")
            workbook = load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
            try:
                rows = list(workbook.active.iter_rows(min_row=1,max_row=1000,max_col=2,values_only=True))
            finally:
                workbook.close()
        else:
            raise ValueError("Choose a .csv or .xlsx file.")
        values = {}
        for row in rows:
            if not row or (row[0] not in DEFAULTS and row[0] != "units"):
                continue
            if row[0] in values or len(row)<2:
                raise ValueError(f"Missing or duplicate value for {row[0]}.")
            values[row[0]] = row[1]
        missing = list(DEFAULTS.keys() - values.keys())
        if missing:
            raise ValueError("Missing spreadsheet values: " + ", ".join(sorted(missing)))
        return preview(Parameters.model_validate(values))
    except (ValueError, ValidationError, BadZipFile, InvalidFileException, KeyError, SyntaxError) as error:
        raise HTTPException(422,f"Invalid spreadsheet. {error}") from error

def model_response(action, request):
    return execute(action, request)

@app.post("/api/model/generate", response_model=JobResponse)
def generate(job: JobRequest):
    return model_response("generate",job)

@app.post("/api/model/recompute", response_model=JobResponse)
def recompute(job: JobRequest):
    if not job.model_id:
        raise HTTPException(422,"Supply the existing model ID.")
    return model_response("recompute",job)

@app.post("/api/drawing/generate", response_model=JobResponse)
def drawing(job: DrawingRequest):
    return model_response("drawing",job)

@app.post("/api/tests/run", response_model=JobResponse)
def tests(options: EngineRequest | None = None):
    return execute("tests", mode=options.engine if options else None)

@app.get("/api/exports/{job_id}/{file_id}")
def download(job_id: str, file_id: str):
    if not re.fullmatch("[a-f0-9]{32}",job_id) or not re.fullmatch(r"[a-zA-Z0-9_]+\.(FCStd|sc|step|svg|png|pdf|dxf|csv|json|stl|glb)",file_id) or file_id=="preview.json":
        raise HTTPException(404,"Export missing.")
    path = JOBS/job_id/file_id
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404,"Export missing.")
    return FileResponse(path,filename=file_id)

if DIST.is_dir():
    app.mount("/",StaticFiles(directory=DIST,html=True),name="frontend")
