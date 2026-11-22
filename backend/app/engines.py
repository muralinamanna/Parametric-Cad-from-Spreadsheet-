"""CAD adapters and finite, operation-scoped engine failover."""
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal, Protocol
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from . import solidcraft
from .exports import validate_files
from .parameters import DEFAULTS, calculate

APP = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)
EngineMode = Literal["auto", "freecad", "solidcraft"]
DRAWING_FILES = ["pegboard.svg","pegboard.png","pegboard.pdf","pegboard.dxf"]
ENGINE_ERRORS = (OSError, ValueError, RuntimeError, ParseError, subprocess.SubprocessError,
                 KeyError, TypeError, IndexError, BadZipFile)

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
        raise OSError("Install FreeCAD 1.0+ and configure the worker using the README.")
    macro = job_path.parent/"run.FCMacro"
    macro.write_text(
        f"import sys\nsys.path.insert(0, {str(APP)!r})\n"
        f"import cad\ncad.main({str(job_path)!r})\n"
        "if App.ActiveDocument:\n    App.closeDocument(App.ActiveDocument.Name)\n"
        "Gui.getMainWindow().close()\n",
        encoding="utf-8",
    )
    return [binary, str(macro)], env

class CADEngine(Protocol):
    name: str
    native: str

    def health_check(self, folder: Path) -> str: ...

    def run_job(self, folder: Path, action: str, parameters: dict | None,
                metadata: dict | None, model: Path | None) -> dict: ...


class FreeCADEngine:
    name = "freecad"
    native = "pegboard.FCStd"

    def _worker(self, folder, **data):
        path = folder / "job.json"
        path.write_text(json.dumps(dict(data, output=str(folder))), encoding="utf-8")
        args, env = cad_command(path)
        completed = subprocess.run(args,env=env,capture_output=True,text=True,
                                   encoding="utf-8",errors="replace",timeout=180)
        result_path = folder / "result.json"
        if completed.returncode or not result_path.is_file():
            tail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise OSError("FreeCAD produced no result. " + tail)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if "error" in result:
            raise ValueError(f'FreeCAD operation failed. {result["error"]}')
        return result

    def health_check(self, folder):
        folder.mkdir()
        return self._worker(folder, action="health")["version"]

    def run_job(self, folder, action, parameters, metadata, model):
        result = self._worker(folder, action=action, parameters=parameters, metadata=metadata,
                              model=str(model) if model else None)
        if action == "drawing":
            result["drawing"] = {"validated": True, "views": 4}
        return result


class SolidCraftEngine:
    name = "solidcraft"
    native = solidcraft.NATIVE

    def health_check(self, folder):
        return solidcraft.version()

    def run_job(self, folder, action, parameters, metadata, model):
        if action == "tests":
            return solidcraft.acceptance(folder)
        evidence, edges = solidcraft.build_model(folder, parameters, model)
        if action == "drawing":
            evidence["drawing"] = solidcraft.generate_drawing(folder, parameters, metadata, edges)
        return evidence


class EngineFailure(Exception):
    def __init__(self, attempts):
        self.attempts = attempts
        self.status = 503 if all(item["code"] == "unavailable" for item in attempts) else 422
        messages = [f'{item["engine"]}: {item["reason"]}' for item in attempts]
        super().__init__(" | ".join(messages))


class EngineResult:
    def __init__(self, folder, files, evidence):
        self.folder = folder
        self.files = files
        self.evidence = evidence


class CADEngineManager:
    def __init__(self, mode=None):
        self.engines: dict[str, CADEngine] = {engine.name:engine for engine in (FreeCADEngine(),SolidCraftEngine())}
        self.mode = mode or os.environ.get("CAD_ENGINE", "auto").lower()
        self.primary = os.environ.get("CAD_PRIMARY","freecad").lower()
        self.fallback = os.environ.get("CAD_FALLBACK","solidcraft").lower()
        self.fallback_enabled = os.environ.get("CAD_FALLBACK_ENABLED","true").lower() in {"true","1","yes","on"}
        if self.mode not in (*self.engines,"auto") or self.primary not in self.engines or self.fallback not in self.engines:
            raise ValueError("Invalid CAD engine configuration. Use auto, freecad, or solidcraft as appropriate.")

    def engine_order(self):
        if self.mode != "auto":
            return [self.mode]
        if self.fallback_enabled and self.primary != self.fallback:
            return [self.primary,self.fallback]
        return [self.primary]

    def health(self, folder):
        engines = {}
        for name,engine in self.engines.items():
            try:
                engines[name] = {"available":True,"version":engine.health_check(folder/name)}
            except ENGINE_ERRORS as error:
                engines[name] = {"available":False,"reason":str(error)}
        available = any(engines[name]["available"] for name in self.engine_order())
        return {"status":"ready" if available else "unavailable",
                "freecad":engines["freecad"].get("version"), "pdf":shutil.which("inkscape") is not None,
                "engines":engines, "mode":self.mode, "primary":self.primary,
                "fallback":self.fallback, "fallbackEnabled":self.fallback_enabled}

    def execute(self, folder, action, parameters=None, metadata=None, previous=None):
        if parameters is not None and set(parameters) != set(DEFAULTS):
            raise ValueError("The engine requires all seven normalized millimetre parameters.")
        if parameters is not None:
            calculate(parameters)  # Input errors must never start an engine.
        attempts = []
        for name in self.engine_order():
            engine = self.engines[name]
            start = time.monotonic()
            version = None
            directory = folder / name
            directory.mkdir()
            phase = "unavailable"
            try:
                version = engine.health_check(directory / "health")
                phase = "operation_failed"
                model = previous / engine.native if previous else None
                model = model if model and model.is_file() else None
                result = engine.run_job(directory, action, parameters, metadata, model)
                phase = "validation_failed"
                if action == "tests":
                    if (len(result["cases"]) != 3 or any(case["result"] != "PASS" for case in result["cases"])
                            or not result["transitionsPassed"]):
                        raise ValueError("One or more CAD acceptance or pitch-threshold cases failed.")
                    native_suffix = Path(engine.native).suffix
                    files = ["pegboard_test_log.csv","validation_report.json",
                             *(f"case_{i}{native_suffix}" for i in range(1,4))]
                else:
                    if not result["shapeValid"] or not result["recomputeSuccessful"]:
                        raise ValueError("CAD geometry or recomputation did not pass validation.")
                    files = [engine.native,"pegboard.step"]
                    if action == "drawing":
                        if not result.get("drawing",{}).get("validated"):
                            raise ValueError("CAD drawing did not pass validation.")
                        files.extend(DRAWING_FILES)
                validate_files(directory, files)
            except ENGINE_ERRORS as error:
                attempts.append(dict(engine=name, version=version, operation=action,
                                     elapsed_ms=round((time.monotonic()-start)*1000),
                                     code=phase, validationPassed=False, reason=str(error)))
                LOG.warning("CAD attempt %s", attempts[-1])
                continue
            attempts.append(dict(engine=name, version=version, operation=action,
                                 elapsed_ms=round((time.monotonic()-start)*1000),
                                 code="ok", validationPassed=True))
            LOG.info("CAD attempt %s", attempts[-1])
            result.update(engine=name, engineVersion=version, engineMode=self.mode,
                          fallbackReason=attempts[0]["reason"] if len(attempts)>1 else None,
                          attempts=attempts)
            return EngineResult(directory,files,result)
        raise EngineFailure(attempts)
