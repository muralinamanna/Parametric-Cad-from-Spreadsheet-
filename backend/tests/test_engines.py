import csv
import io
import json
import os
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app import main, solidcraft
from app.engines import CADEngineManager, FreeCADEngine, SolidCraftEngine
from app.parameters import DEFAULTS

SC = pytest.mark.skipif(os.getenv("RUN_SOLIDCRAFT_TESTS") != "1",
                        reason="Set RUN_SOLIDCRAFT_TESTS=1 and install the pinned CLI.")
FC = pytest.mark.skipif(os.getenv("RUN_CAD_TESTS") != "1", reason="Install FreeCAD to exercise both engines.")
META = {"date": "2026-11-22", "material": "Steel"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "JOBS", tmp_path)
    monkeypatch.setenv("CAD_ENGINE","auto")
    monkeypatch.setenv("CAD_PRIMARY","freecad")
    monkeypatch.setenv("CAD_FALLBACK","solidcraft")
    monkeypatch.setenv("CAD_FALLBACK_ENABLED","true")
    return TestClient(main.app)


def request(client, path="/api/model/generate", **body):
    return client.post(path, json={"parameters":DEFAULTS, **body})


def test_both_engines_unavailable_and_manual_override(client, monkeypatch):
    monkeypatch.setenv("FREECAD_PYTHON", str(Path("/missing/freecad-python")))
    monkeypatch.setenv("SOLIDCRAFT_CLI", str(Path("/missing/solidcraft-cli")))
    health = client.get("/api/health").json()
    assert health["status"] == "unavailable"
    assert not any(engine["available"] for engine in health["engines"].values())
    automatic = request(client)
    assert automatic.status_code == 503
    assert all(name in automatic.json()["detail"] for name in ("freecad:", "solidcraft:"))
    manual = request(client, engine="solidcraft")
    assert manual.status_code == 503
    assert "solidcraft:" in manual.json()["detail"] and "freecad:" not in manual.json()["detail"]
    monkeypatch.setenv("CAD_FALLBACK_ENABLED","false")
    assert "solidcraft:" not in request(client).json()["detail"]


def test_invalid_spreadsheet_never_invokes_engine(client, monkeypatch):
    def unexpected(*args):
        pytest.fail("An engine was called for invalid parameters.")
    monkeypatch.setattr(FreeCADEngine,"health_check",unexpected)
    monkeypatch.setattr(SolidCraftEngine,"health_check",unexpected)
    assert request(client, parameters=DEFAULTS | {"boardWidth": 29}).status_code == 422
    assert request(client, parameters=DEFAULTS | {"units": "in"}).status_code == 422
    bad = client.post("/api/spreadsheet/upload", files={"file": ("invalid.csv", b"boardWidth,29\n")})
    assert bad.status_code == 422


def test_configured_priority_and_one_attempt_per_engine(monkeypatch):
    monkeypatch.setenv("CAD_PRIMARY", "solidcraft")
    monkeypatch.setenv("CAD_FALLBACK", "solidcraft")
    assert CADEngineManager("auto").engine_order() == ["solidcraft"]
    assert CADEngineManager("freecad").engine_order() == ["freecad"]


@SC
def test_excel_to_solidcraft_drawing_when_freecad_is_missing(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FREECAD_PYTHON", "/missing/freecad-python")
    path = main.ROOT / "templates" / "pegboard_parameters.xlsx"
    loaded = client.post("/api/spreadsheet/upload",files={"file":(path.name,path.read_bytes())}).json()
    result = request(client,"/api/drawing/generate",parameters=loaded["parameters"],metadata=META)
    assert result.status_code == 200,result.text
    job = result.json()
    evidence = job["evidence"]
    assert evidence["engine"] == "solidcraft" and evidence["engineVersion"] == "0.45.0"
    assert [attempt["code"] for attempt in evidence["attempts"]] == ["unavailable","ok"]
    assert evidence["fallbackReason"] and evidence["nativeReopened"] and evidence["stepReopened"]
    assert evidence["actualSlots"] == 80 and evidence["minimumClearance"] == pytest.approx(12)
    assert evidence["drawing"]["validated"] and evidence["drawing"]["views"] == 4

    def get(name):
        response = client.get(job["files"][name])
        assert response.status_code == 200
        return response.content
    original_native = get("pegboard.sc")
    with ZipFile(io.BytesIO(original_native)) as native:
        assert json.loads(native.read("container.json"))["format"] == "solidcraft-container/1"
    svg = ElementTree.fromstring(get("pegboard.svg"))
    assert svg.tag.endswith("svg") and "mm" in svg.attrib["width"]
    assert get("pegboard.png").startswith(b"\x89PNG\r\n\x1a\n")
    assert get("pegboard.pdf").startswith(b"%PDF-")
    dxf = get("pegboard.dxf")
    assert dxf.count(b"\nLINE\n") == (80+1)*4 and b"$INSUNITS\n70\n4" in dxf
    step = tmp_path / "validate.step"
    step.write_bytes(get("pegboard.step"))
    [measure] = solidcraft.run(tmp_path,[solidcraft.command("inspect.measure")],model=step)
    assert measure["bodies"][0]["volume_mm3"] == pytest.approx(evidence["volume"])

    resized = request(client,"/api/model/recompute",parameters=DEFAULTS | {"boardWidth":360},
                      model_id=job["id"],engine="solidcraft")
    assert resized.status_code == 200,resized.text
    assert resized.json()["evidence"]["actualSlots"] == 95
    assert get("pegboard.sc") == original_native


@SC
@FC
def test_real_freecad_primary_drawing_failure_switches_then_recovers(client, monkeypatch):
    generated = request(client)
    assert generated.status_code == 200,generated.text
    first = generated.json()
    assert first["evidence"]["engine"] == "freecad"
    original = FreeCADEngine.run_job
    def fail_drawing(self, folder, action, *args):
        if action == "drawing":
            (folder / "pegboard.svg").write_text("partial output",encoding="utf-8")
            raise ValueError("Injected FreeCAD drawing export failure")
        return original(self,folder,action,*args)
    monkeypatch.setattr(FreeCADEngine,"run_job",fail_drawing)
    drawing = request(client,"/api/drawing/generate",model_id=first["id"],metadata=META)
    assert drawing.status_code == 200,drawing.text
    next_job = drawing.json()
    evidence = next_job["evidence"]
    assert evidence["engine"] == "solidcraft"
    assert [attempt["code"] for attempt in evidence["attempts"]] == ["operation_failed","ok"]
    assert "Injected FreeCAD drawing export failure" in evidence["fallbackReason"]
    assert client.get(next_job["files"]["pegboard.svg"]).content != b"partial output"
    assert client.get(first["files"]["pegboard.FCStd"]).status_code == 200
    for metric in ("actualRows","actualColumns","actualSlots","minimumClearance"):
        assert evidence[metric] == pytest.approx(first["evidence"][metric])
    switched = request(client,"/api/model/recompute",model_id=next_job["id"],engine="freecad")
    assert switched.status_code == 200,switched.text
    assert switched.json()["evidence"]["engine"] == "freecad"


@SC
def test_solidcraft_acceptance_models_and_thresholds(client):
    tested = client.post("/api/tests/run",json={"engine":"solidcraft"})
    assert tested.status_code == 200,tested.text
    job = tested.json()
    rows = list(csv.DictReader(io.StringIO(client.get(job["files"]["pegboard_test_log.csv"]).text)))
    assert [(row["Actual Slots"],row["Minimum Edge Clearance"],row["Result"]) for row in rows] == [
        ("1","12.0","PASS"),("80","12.0","PASS"),("95","12.0","PASS")]
    assert job["evidence"]["transitionsPassed"]
    for index in range(1,4):
        assert client.get(job["files"][f"case_{index}.sc"]).status_code == 200
