import csv
import io
import math
import os
import subprocess
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import main
from app.details import Feature, operation
from app.engines import cad_command
from app.parameters import DEFAULTS


TEMPLATE = main.ROOT/"templates"/"detailed_mounting_plate.csv"


def feature(name,kind,dimensions,**settings):
    return {"id":name,"kind":kind,"dimensions":{
        key: {"parameter":value} if isinstance(value,str) else {"value":value}
        for key,value in dimensions.items()
    }, **settings}


def test_missing_binding_and_invalid_pocket():
    missing=Feature.model_validate(feature("hole","hole",dict(x=8,y=8,diameter="removedField")))
    with pytest.raises(ValueError,match="Choose a field again"):
        operation(missing,DEFAULTS)
    pocket=Feature.model_validate(feature("pocket","pocket",dict(x=20,y=45,width=15,length=8,depth=9)))
    with pytest.raises(ValueError,match="less than plate thickness"):
        operation(pocket,DEFAULTS)


@pytest.mark.skipif(os.getenv("RUN_CADRS_TESTS")!="1",
                    reason="Set RUN_CADRS_TESTS=1 with CADRS_WORKER and Linux FreeCAD installed.")
def test_mounting_plate_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(main,"JOBS",tmp_path)
    client=TestClient(main.app)

    def upload(data, name="plate.csv"):
        result=client.post("/api/spreadsheet/upload",files={"file":(name,data)})
        assert result.status_code==200,result.text
        return result.json()

    csv_bytes=TEMPLATE.read_bytes()
    workbook=Workbook()
    for row,(key,value) in enumerate(csv.reader(io.StringIO(csv_bytes.decode())),1):
        workbook.active.append([key,float(value) if 2<=row<=9 else value])
    xlsx=io.BytesIO()
    workbook.save(xlsx)
    first=upload(xlsx.getvalue(),"plate.xlsx")
    assert first["sources"]["holeSpacing"]=="Sheet!B9"
    started=client.post("/api/model/generate",json={"engine":"freecad","parameters":first["parameters"],
                                                  "sources":first["sources"],"detail_parameters":first["detailParameters"]})
    assert started.status_code==200,started.text
    original=started.json()
    original_stl=client.get(original["files"]["pegboard.stl"]).content
    recipe=[
        feature("mount","pattern",dict(x=8,y=8,diameter=4,pitchX="holeSpacing",pitchY="holeSpacing")),
        feature("pocket","pocket",dict(x=20,y=50,width=15,length=8,depth=2)),
        feature("chamfer","chamfer",dict(size=1),edge="top-front"),
    ]
    payload={"source_model_id":original["id"],"features":recipe}
    before=client.post("/api/details/build",json=payload)
    assert before.status_code==200,before.text
    assert before.json()["geometry"]["bounds"]["max"]==[120,100,8]

    refreshed=upload(csv_bytes.replace(b"boardWidth,120",b"boardWidth,140").replace(b"holeSpacing,55",b"holeSpacing,65"))
    payload.update(parameters=refreshed["parameters"],sources=refreshed["sources"],detail_parameters=refreshed["detailParameters"])
    rebuilt=client.post("/api/details/build",json=payload)
    assert rebuilt.status_code==200,rebuilt.text
    model=rebuilt.json()
    assert model["geometry"]["bounds"]["max"]==[140,100,8]
    assert model["sourceModelId"]==original["id"]
    assert model["geometry"]["volume"]==pytest.approx(140*100*8-2*4*8*8-4*math.pi*4*8-15*8*2-140/2,abs=0.01)
    assert client.get("/api/details").json()==[]
    assert client.post(f'/api/details/{model["id"]}/save',json={}).status_code==200
    assert client.get("/api/details").json()[0]["id"]==model["id"]
    assert client.get(f'/api/details/{model["id"]}').json()==model
    assert model["features"][0]["dimensions"]["pitchX"]=={"parameter":"holeSpacing"}

    step=tmp_path/"verified.step"
    step.write_bytes(client.get(model["files"]["detailed.step"]).content)
    # Inspect the actual STEP with an independent kernel, including hole centres and pocket floor.
    script=tmp_path/"verify.py"
    script.write_text("""
import json, sys, FreeCAD, Part
shape=Part.read(sys.argv[1])
b=shape.BoundBox
centers=sorted({(round(e.Curve.Center.x,3),round(e.Curve.Center.y,3)) for e in shape.Edges
                if isinstance(e.Curve,Part.Circle) and abs(e.Curve.Radius-2)<1e-5})
floor=shape.isInside(FreeCAD.Vector(25,53,5.9),1e-6,False)
cavity=shape.isInside(FreeCAD.Vector(25,53,6.1),1e-6,False)
print(json.dumps(dict(valid=shape.isValid(), solids=len(shape.Solids), volume=shape.Volume,
                      bounds=[b.XLength,b.YLength,b.ZLength],centers=centers,floor=floor,cavity=cavity)))
""",encoding="utf-8")
    args,env=cad_command(tmp_path/"command.json")
    result=subprocess.run([args[0],str(script),str(step)],env=env,check=True,capture_output=True,text=True,timeout=30)
    measured=json.loads(result.stdout.splitlines()[-1])
    assert measured["valid"] and measured["solids"]==1
    assert measured["bounds"]==pytest.approx([140,100,8])
    assert measured["centers"]==[[8,8],[8,73],[73,8],[73,73]]
    assert measured["floor"] and not measured["cavity"]
    assert measured["volume"]==pytest.approx(model["geometry"]["volume"],abs=.01)

    extra=[
        feature("standalone-hole","hole",dict(x=98,y=78,diameter=4)),
        feature("rear-fillet","fillet",dict(size=1),edge="top-back"),
        feature("suppressed","chamfer",dict(size=99),edge="top-front",suppressed=True),
    ]
    extended=client.post("/api/details/build",json={**payload,"features":recipe+extra})
    assert extended.status_code==200,extended.text
    assert extended.json()["geometry"]["volume"]==pytest.approx(
        model["geometry"]["volume"]-math.pi*4*8-140*(1-math.pi/4),abs=.02)

    stl=client.get(model["files"]["detailed.stl"]).content
    payload["features"][1]["dimensions"]["depth"]={"value":9}
    rejected=client.post("/api/details/build",json=payload)
    assert rejected.status_code==422 and rejected.json()["detail"]["feature"]=="pocket"
    assert client.get(model["files"]["detailed.stl"]).content==stl
    assert client.get(original["files"]["pegboard.stl"]).content==original_stl
    payload["detail_parameters"]={}
    broken=client.post("/api/details/build",json=payload)
    assert broken.status_code==422 and broken.json()["detail"]["feature"]=="mount"
