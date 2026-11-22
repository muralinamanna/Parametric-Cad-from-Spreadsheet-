import csv
import io
import json
import os
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app import main
from app.parameters import DEFAULTS


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "JOBS", tmp_path)
    return TestClient(main.app)


def test_workbook_csv_and_invalid_upload(client):
    for extension in ("csv","xlsx"):
        path = main.ROOT/"templates"/f"pegboard_parameters.{extension}"
        response = client.post("/api/spreadsheet/upload",files={"file":(path.name,path.read_bytes())})
        assert response.status_code==200
        assert response.json()["calculations"]["totalSlots"]==80
    assert client.post("/api/spreadsheet/upload",files={"file":("bad.xlsx",b"invalid")}).status_code==422
    assert client.get("/api/exports/no/job.FCStd").status_code==404


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_json_returns_validation_error(client, value):
    response = client.post("/api/parameters/validate",
                           content=json.dumps(DEFAULTS | {"boardWidth": value}),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "boardWidth"


@pytest.mark.skipif(os.getenv("RUN_CAD_TESTS")!="1",reason="Set RUN_CAD_TESTS=1 to exercise FreeCAD and Inkscape.")
def test_real_recompute_drawings_and_acceptance(client):
    assert client.get("/api/health").json()["status"]=="ready"
    initial=client.post("/api/model/generate",json={"parameters":DEFAULTS})
    assert initial.status_code==200, initial.text
    model=initial.json()
    broken=client.post("/api/model/recompute",json={"parameters":DEFAULTS|{"boardWidth":29},"model_id":model["id"]})
    assert broken.status_code==422
    assert client.get(model["files"]["pegboard.FCStd"]).status_code==200
    wider=DEFAULTS|{"boardWidth":360}
    recomputed=client.post("/api/model/recompute",json={"parameters":wider,"model_id":model["id"]})
    assert recomputed.status_code==200, recomputed.text
    assert recomputed.json()["evidence"]["actualSlots"]==95
    response=client.post("/api/drawing/generate",json={
        "parameters":wider,"model_id":recomputed.json()["id"],"metadata":{"date":"2026-11-20"}})
    assert response.status_code==200,response.text
    files=response.json()["files"]
    def get(name):
        result=client.get(files[name])
        assert result.status_code==200
        return result.content
    with ZipFile(io.BytesIO(get("pegboard.FCStd"))) as archive:
        doc=archive.read("Document.xml")
        for prefix in (b"Top",b"Front",b"Right",b"Isometric"):
            assert prefix+b'View' in doc
        assert b"TechDraw::DrawPage" in doc
    assert b"ISO-10303-21" in get("pegboard.step")
    stl = get("pegboard.stl")
    assert stl.startswith(b"solid") and b"endsolid" in stl
    assert get("pegboard.pdf").startswith(b"%PDF-")
    assert ET.fromstring(get("pegboard.svg")).tag.endswith("svg")
    assert b"CUT_PROFILE" in get("pegboard.dxf")
    report=client.post("/api/tests/run",json={}).json()
    rows=list(csv.DictReader(io.StringIO(client.get(report["files"]["pegboard_test_log.csv"]).text)))
    assert [row["Result"] for row in rows]==["PASS"]*3
    assert [row["Actual Slots"] for row in rows]==["1","80","95"]
    assert report["evidence"]["transitionsPassed"]
