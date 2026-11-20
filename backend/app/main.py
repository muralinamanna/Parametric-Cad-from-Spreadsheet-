"""Local API. Each CAD operation runs in a fresh process and publishes an immutable job."""
import csv
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .parameters import DEFAULTS, calculate, positions

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs"
JOBS = OUTPUT / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
DIST = ROOT / "frontend" / "dist"
APP = Path(__file__).resolve().parent

class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    boardWidth: float
    boardHeight: float
    boardThickness: float
    edgeMargin: float
    slotWidth: float
    slotLength: float
    slotSpacing: float

class JobRequest(BaseModel):
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

def cad_command(job_path):
    runner = os.getenv("FREECAD_PYTHON")
    env = os.environ.copy()
    modules = Path(os.getenv("FREECAD_LIB", "/usr/lib/freecad-python3/lib"))
    resources = Path(os.getenv("FREECAD_RESOURCES", "/usr/share/freecad"))
    config = job_path.parent / ".runtime"
    config.mkdir()
    env["XDG_CONFIG_HOME"] = str(config)
    if runner or (modules/"FreeCAD.so").is_file():
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        default_python = "/usr/bin/python3" if os.name != "nt" else "python.exe"
        names = [modules,resources/"Ext",*(resources/"Mod"/n for n in ("Draft","BIM","Arch","Part"))]
        old = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join([*(str(p) for p in names), *([old] if old else [])])
        if os.name != "nt":
            library_path = env.get("LD_LIBRARY_PATH")
            env["LD_LIBRARY_PATH"] = os.pathsep.join([str(modules),*([library_path] if library_path else [])])
        else:
            env["PATH"] = str(modules) + os.pathsep + env["PATH"]
        return [runner or default_python, str(APP/"worker.py"), str(job_path)], env
    binary = os.getenv("FREECAD_EXECUTABLE") or shutil.which("FreeCAD") or shutil.which("freecad")
    if not binary:
        raise HTTPException(503,"Install FreeCAD 1.0+ and configure the worker using the README.")
    macro = job_path.parent/"run.FCMacro"
    macro.write_text(
        f"import sys\nsys.path.insert(0, {str(APP)!r})\n"
        f"import cad\ncad.main({str(job_path)!r})\n"
        "if App.ActiveDocument:\n    App.closeDocument(App.ActiveDocument.Name)\n"
        "Gui.getMainWindow().close()\n",
        encoding="utf-8",
    )
    return [binary, str(macro)], env

def execute(action: str, request=None):
    model = None
    if request:
        preview(request.parameters)
        if request.model_id:
            model = JOBS / request.model_id / "pegboard.FCStd"
            if not model.is_file():
                raise HTTPException(404,"The referenced native model is missing.")
    ident = uuid4().hex
    staging = JOBS / (".tmp-" + ident)
    staging.mkdir()
    data = {"action": action, "output": str(staging)}
    if request:
        data.update(parameters=request.parameters.model_dump(), model=str(model) if model else None)
    if isinstance(request, DrawingRequest):
        data["metadata"] = request.metadata.model_dump()
    path = staging/"job.json"
    path.write_text(json.dumps(data))
    try:
        command, env = cad_command(path)
        try:
            completed = subprocess.run(command,env=env,capture_output=True,text=True,timeout=180)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HTTPException(503,f"The FreeCAD worker did not complete. {error}") from error
        result_path = staging/"result.json"
        if not result_path.is_file():
            tail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise HTTPException(503, "FreeCAD produced no result. " + tail)
        result = json.loads(result_path.read_text())
        if "error" in result:
            raise HTTPException(422,f'FreeCAD operation failed. {result["error"]}')
        if action == "health":
            return result
        files = {
            "tests": ["pegboard_test_log.csv","validation_report.json",*(f"case_{i}.FCStd" for i,case in enumerate(result.get("cases",[]),1) if case["result"]=="PASS")],
            "drawing": ["pegboard.FCStd","pegboard.step","pegboard.svg","pegboard.pdf","pegboard.dxf"],
        }.get(action, ["pegboard.FCStd","pegboard.step"])
        if any(not (staging/name).is_file() or (staging/name).stat().st_size == 0 for name in files):
            raise HTTPException(503,"FreeCAD produced incomplete export files.")
        final = JOBS/ident
        final.mkdir()
        for name in files:
            (staging/name).replace(final/name)
        return JobResponse(id=ident, files={name:f"/api/exports/{ident}/{name}" for name in files}, evidence=result)
    finally:
        shutil.rmtree(staging,ignore_errors=True)

@app.get("/api/health")
def health():
    try:
        return {"status":"ready","freecad":execute("health")["version"],
                "pdf":shutil.which("inkscape") is not None}
    except HTTPException as error:
        return {"status":"unavailable","detail":error.detail}

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
            if not row or row[0] not in DEFAULTS:
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
    response = execute(action, request)
    (JOBS/response.id/"preview.json").write_text(preview(request.parameters).model_dump_json())
    return response

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
def tests():
    return execute("tests")

@app.get("/api/exports/{job_id}/{file_id}")
def download(job_id: str, file_id: str):
    if not re.fullmatch("[a-f0-9]{32}",job_id) or not re.fullmatch(r"[a-zA-Z0-9_]+\.(FCStd|step|svg|pdf|dxf|csv|json)",file_id) or file_id=="preview.json":
        raise HTTPException(404,"Export missing.")
    path = JOBS/job_id/file_id
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404,"Export missing.")
    return FileResponse(path,filename=file_id)

if DIST.is_dir():
    app.mount("/",StaticFiles(directory=DIST,html=True),name="frontend")
