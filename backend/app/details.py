"""CADRS detailed variants. Each successful rebuild is an immutable revision."""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .exports import validate_files
from .parameters import DEFAULTS, calculate, positions

ROOT = Path(__file__).resolve().parents[2]
REVISION = "07e7730daa7a717e22057bd65ea393b10fffbf66"
FIELDS = {
    "hole": ("x", "y", "diameter"),
    "pattern": ("x", "y", "diameter", "pitchX", "pitchY"),
    "pocket": ("x", "y", "width", "length", "depth"),
    "fillet": ("size",),
    "chamfer": ("size",),
}
EDGES = {"top-front", "top-back", "top-left", "top-right"}


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: float | None = None
    parameter: str | None = Field(default=None, max_length=64)


class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    kind: Literal["hole", "pattern", "pocket", "fillet", "chamfer"]
    dimensions: dict[str, Binding]
    suppressed: bool = False
    edge: str | None = Field(default=None,max_length=30)
    rows: int = Field(default=2, ge=1, le=8)
    columns: int = Field(default=2, ge=1, le=8)


def executable():
    configured = os.environ.get("CADRS_WORKER")
    if configured:
        return shutil.which(configured)
    binary = "spreadsheet-cadrs-worker" + (".exe" if os.name == "nt" else "")
    return (shutil.which(binary) or
            shutil.which(str(ROOT/"backend"/"cadrs-worker"/"target"/"release"/binary)))


def operation(feature, params):
    kind = feature.kind
    values = {}
    for name in FIELDS[kind]:
        binding = feature.dimensions.get(name)
        if not binding or (binding.parameter is None) == (binding.value is None):
            raise ValueError(f"{name}: choose a fixed value or one spreadsheet field.")
        if binding.parameter is not None:
            if binding.parameter not in params:
                raise ValueError(f"{name}: spreadsheet field {binding.parameter} was not found. Choose a field again.")
            value = params[binding.parameter]
        else:
            value = binding.value
        if not math.isfinite(value) or value < 0 or (value <= 1e-6 and name not in {"x","y"}):
            raise ValueError(f"{name}: enter a positive length in mm (positions may be zero).")
        values[name] = value
    width,length,thickness = (params[key] for key in ("boardWidth","boardHeight","boardThickness"))
    result = {"id":feature.id,"kind":kind}
    if kind in {"hole","pattern"}:
        x,y,diameter = (values[n] for n in ("x","y","diameter"))
        radius = diameter/2
        if kind=="pattern":
            px,py = values["pitchX"],values["pitchY"]
            if (feature.columns>1 and px<=diameter) or (feature.rows>1 and py<=diameter):
                raise ValueError("Pattern pitch must exceed hole diameter on repeated axes.")
            centers = [[x+col*px,y+row*py] for row in range(feature.rows) for col in range(feature.columns)]
        else:
            centers = [[x,y]]
        if any(min(cx-radius,cy-radius,width-cx-radius,length-cy-radius)<=1e-6 for cx,cy in centers):
            raise ValueError("Keep each hole fully inside the plate. Check centre, pitch and diameter.")
        return {**result,"kind":"holes","diameter":diameter,"centers":centers}
    if kind=="pocket":
        x,y,w,h,depth = (values[key] for key in FIELDS[kind])
        if depth>=thickness-1e-6:
            raise ValueError(f"Pocket depth must be less than plate thickness ({thickness:g} mm).")
        if min(x,y,width-x-w,length-y-h)<=1e-6:
            raise ValueError("Keep the pocket fully inside the top face of the plate.")
        return {**result,**values}
    if feature.edge not in EDGES:
        raise ValueError("Select an outside top edge again.")
    if values["size"]>=min(width,length,thickness):
        raise ValueError("The edge treatment must be smaller than the plate dimensions and thickness.")
    return {**result,"edge":feature.edge,**values}


def build(jobs, source_id, params, sources, extra, features):
    worker=executable()
    if not worker:
        raise HTTPException(503,"Install the CADRS worker or set CADRS_WORKER. The original CAD workflow is still available.")
    calc=calculate(params)
    commands=[]
    holes=0
    if len({feature.id for feature in features})!=len(features):
        raise HTTPException(422,"Each feature must have a unique ID.")
    for feature in features:
        if feature.suppressed:
            continue
        try:
            command=operation(feature,params|extra)
            holes+=len(command.get("centers",[]))
            if holes>128:
                raise ValueError("The detailed variant supports up to 128 additional holes.")
            commands.append(command)
        except ValueError as error:
            raise HTTPException(422,{"feature":feature.id,"message":str(error)}) from error
    model_id=uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".detail-",dir=jobs) as scratch:
        job=Path(scratch)
        (job/"job.json").write_text(json.dumps({
            "size":[params[key] for key in ("boardWidth","boardHeight","boardThickness")],
            "slots":[[x,y,params["slotWidth"],params["slotLength"]] for x,y in positions(params,calc)],
            "features":commands,
        }),encoding="utf-8")
        try:
            env=os.environ.copy()
            env.pop("CADRS_BOOL_LENIENT",None)
            subprocess.run([str(Path(worker).resolve()),str(job)],check=True,capture_output=True,timeout=120,env=env)
            outcome=json.loads((job/"result.json").read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired as error:
            raise HTTPException(503,"CADRS timed out. Try fewer features or a smaller hole pattern.") from error
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise HTTPException(503,"CADRS could not complete the rebuild. Check the worker installation.") from error
        if "error" in outcome:
            raise HTTPException(422,{"feature":outcome.get("feature"),"message":outcome["error"]})
        files=["detailed.step","detailed.stl"]
        try:
            validate_files(job,files)
        except (ValueError,OSError) as error:
            raise HTTPException(503,"CADRS produced an invalid export.") from error
        record={"id":model_id,"sourceModelId":source_id,"revision":REVISION,"parameters":params,
                "sources":sources,"detailParameters":extra,"units":"mm","features":[feature.model_dump(exclude_none=True) for feature in features],
                "geometry":outcome,"files":{name:f"/api/exports/{model_id}/{name}" for name in files}}
        publish=job/"publish"
        publish.mkdir()
        for name in files:
            (job/name).replace(publish/name)
        (publish/"variant.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
        publish.replace(jobs/model_id)
    return record


def load(jobs, model_id):
    path=jobs/model_id/"variant.json" if re.fullmatch(r"[a-f0-9]{32}",model_id) else None
    if not path or not path.is_file():
        raise HTTPException(404,"Detailed variant not found.")
    return json.loads(path.read_text(encoding="utf-8"))
