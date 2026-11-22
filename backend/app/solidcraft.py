"""SolidCraft 0.45.0 CLI adapter. All scripts use the upstream command catalog."""
import csv
import json
import math
import os
import re
import shutil
import subprocess
from bisect import bisect_left
from collections import Counter
from pathlib import Path

from .exports import convert_svg, write_profile_dxf
from .parameters import DEFAULTS, EPS, calculate, positions

VERSION = "0.45.0"
NATIVE = "pegboard.sc"
BODY = "Pegboard"
TOL = max(EPS, 1e-6)  # millimetres, for SolidCraft's native edge coordinates
INSPECT = [
    {"command": "inspect.measure", "params": {}},
    {"command": "model.edges", "params": {"body": BODY}},
]


def command(name, /, **params):
    return {"command": name, "params": params}


def executable():
    binary = shutil.which(os.environ.get("SOLIDCRAFT_CLI", "solidcraft-cli"))
    if not binary:
        raise OSError("SolidCraft CLI not found. Set SOLIDCRAFT_CLI to the v0.45.0 executable.")
    return str(Path(binary).resolve())


def version():
    output = subprocess.run([executable(), "--version"], check=True, capture_output=True,
                            text=True, timeout=10).stdout
    match = re.fullmatch(r"solidcraft-cli ([^\s]+)\s*", output)
    if not match or match[1] != VERSION:
        raise ValueError(f"Expected SolidCraft {VERSION}; detected {output.strip() or 'unknown'}.")
    return match[1]


def run(folder, steps, *, model=None, save=None, step=False):
    script, result = folder / "solidcraft-job.json", folder / "solidcraft-result.json"
    script.write_text(json.dumps({"commands": steps}), encoding="utf-8")
    result.unlink(missing_ok=True)
    args = [executable(), "run", script.name, "--results", "--json-out", result.name,
            "--validation", "each_feature", "--param-check", "strict"]
    if model:
        args += ["--in", str(model)]
    if save:
        args += ["--save", save]
    if step:
        args += ["--out", "pegboard.step"]
    env = {**os.environ, "XDG_CACHE_HOME": str(folder / ".cache")}
    completed = subprocess.run(args, cwd=folder, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
    if completed.returncode:
        raise ValueError((completed.stderr or completed.stdout).strip()[-2000:] or "SolidCraft process failed.")
    output = json.loads(result.read_text(encoding="utf-8"))
    if not isinstance(output, list) or len(output) != len(steps):
        raise ValueError("SolidCraft returned an incomplete command result.")
    return output


def create_steps(p):
    steps = [command("parameters.add", name=key, expression=p[key], unit="mm") for key in DEFAULTS]
    for key, expression, unit in [
        ("pitchX", "slotWidth+slotSpacing", "mm"),
        ("pitchY", "slotLength+slotSpacing", "mm"),
        ("columnCount", f"floor((boardWidth-2*edgeMargin-slotWidth+{EPS:.7f} mm)/pitchX)+1", ""),
        ("rowCount", f"floor((boardHeight-2*edgeMargin-slotLength+{EPS:.7f} mm)/pitchY)+1", ""),
    ]:
        steps.append(command("parameters.add", name=key, expression=expression, unit=unit))
    return steps + [
        command("solid.box", length="boardWidth", width="boardHeight", height="boardThickness", body_name=BODY),
        command("sketch.create", plane="XY", name="Master Slot"),
        command("sketch.rectangle.two_point", p0=["edgeMargin", "edgeMargin"],
                p1=["edgeMargin+slotWidth", "edgeMargin+slotLength"]),
        command("solid.extrude", sketch="Master Slot", through_all=True, operation="cut",
                targets=[BODY], name="Slot Cut"),
        command("solid.pattern.rectangular", features=["Slot Cut"], dir1=[1, 0, 0],
                count1="columnCount", spacing1="pitchX", dir2=[0, 1, 0],
                count2="rowCount", spacing2="pitchY"),
    ]


def inspect_geometry(measurement, native_edges, p):
    """Match every 3D rectangular edge to the validated layout, then measure the actual clearance."""
    c = calculate(p)
    w,h,t,margin,sw,sl = (p[k] for k in list(DEFAULTS)[:6])
    bodies = measurement["bodies"]
    if len(bodies) != 1 or not bodies[0]["closed"] or bodies[0]["kernel"]["shells"] != 1:
        raise ValueError("SolidCraft did not produce one closed pegboard shell.")
    body = bodies[0]
    volume = t * (w*h - c["totalSlots"]*sw*sl)
    if not math.isclose(body["volume_mm3"], volume, rel_tol=1e-8, abs_tol=TOL):
        raise ValueError("SolidCraft body volume does not match the through-slot volume.")
    openings = positions(p,c)
    outlines = [(0,0,w,h), *((x,y,x+sw,y+sl) for x,y in openings)]
    axes = [sorted({value for low,high in ends for value in (low,high)})
            for ends in ([(x,xx) for x,_,xx,_ in outlines], [(y,yy) for _,y,_,yy in outlines], [(0,t)])]

    def snap(value, axis):
        index = bisect_left(axis, value)
        closest = min(axis[max(0,index-1):index+1], key=lambda expected: abs(value-expected))
        if not math.isclose(value, closest, rel_tol=0.0, abs_tol=TOL):
            raise ValueError("SolidCraft produced an edge outside the expected pegboard coordinates.")
        return closest

    def snap_point(point):
        return tuple(snap(value,axis) for value,axis in zip(point,axes))

    def key(a,b):
        return tuple(sorted((snap_point(a),snap_point(b))))

    expected = Counter()
    for x,y,xx,yy in outlines:
        points = [(x,y),(xx,y),(xx,yy),(x,yy)]
        for i, (a, b) in enumerate(zip(points, points[1:]+points[:1])):
            for z in (0,t):
                expected[key((*a,z),(*b,z))] += 1
            expected[key((*points[i],0),(*points[i],t))] += 1
    actual, top_edges, hole_points = Counter(), [], []
    measured_x, measured_y = set(), set()
    for edge in native_edges["edges"]:
        a,b = edge["start"],edge["end"]
        edge_key = key(a,b)
        actual[edge_key] += 1
        if not math.isclose(math.dist(a,b), edge["length"], rel_tol=1e-8, abs_tol=TOL):
            raise ValueError("SolidCraft returned a nonstraight pegboard edge.")
        if all(point[2] == t for point in edge_key):
            top_edges.append((tuple(a[:2]),tuple(b[:2])))
            for raw in (a,b):
                point = snap_point(raw)
                if point[0] not in (0,w) and point[1] not in (0,h):
                    hole_points.append(raw)
                    measured_x.add(point[0])
                    measured_y.add(point[1])
    if actual != expected or not hole_points:
        raise ValueError("SolidCraft through-slot edge topology does not match the spreadsheet.")
    min_x,min_y = min(p[0] for p in hole_points), min(p[1] for p in hole_points)
    max_x,max_y = max(p[0] for p in hole_points), max(p[1] for p in hole_points)
    clearances = dict(left=min_x,right=w-max_x,bottom=min_y,top=h-max_y)
    clearance = min(clearances.values())
    if clearance < margin-TOL:
        raise ValueError("SolidCraft slot clearance is below the requested edge margin.")
    return dict(actualSlots=(len(top_edges)-4)//4, actualRows=len(measured_y)//2,
                actualColumns=len(measured_x)//2, minimumClearance=clearance,
                edgeClearances=clearances, shapeValid=True, recomputeSuccessful=True,
                brokenReferences=[], nativeReopened=True, volume=body["volume_mm3"]), top_edges


def build_model(folder, p, source=None, *, export_step=True):
    if source:
        # Remove the previous generated sheet before changing occurrence counts and annotations.
        [drawings] = run(folder, [command("drawing.list")], model=source)
        steps = [command("drawing.delete", drawing=d["id"]) for d in drawings["drawings"]]
        steps.append(command("parameters.change", changes=p))
    else:
        steps = create_steps(p)
    if export_step:
        steps.append(command("file.export", path="pegboard.glb", format="glb"))
    run(folder, steps, model=source, save=NATIVE, step=export_step)
    evidence, edges = inspect_geometry(*run(folder, INSPECT, model=folder/NATIVE), p)
    if export_step:
        [measurement] = run(folder, [command("inspect.measure")], model=folder/"pegboard.step")
        bodies = measurement["bodies"]
        if (len(bodies) != 1 or not bodies[0]["closed"]
                or not math.isclose(bodies[0]["volume_mm3"], evidence["volume"], rel_tol=1e-8, abs_tol=TOL)):
            raise ValueError("Reopened STEP does not match the native body volume.")
        evidence["stepReopened"] = True
    return evidence, edges


def generate_drawing(folder, p, metadata, top_edges):
    native = folder / NATIVE
    drawing, views = run(folder, [
        command("drawing.create", name=metadata["title"], template="iso-a3-part",
                first_sheet_name="Pegboard", projection="third", units="mm"),
        command("drawing.view.standard", sheet="Pegboard", gap_mm=26),
    ], model=native, save="with-views.sc")
    if views.get("outside"):
        raise ValueError("SolidCraft could not fit the four views on the drawing sheet.")
    sheet = views["sheet"]
    c = calculate(p)
    w,h,t = (p[k] for k in ("boardWidth","boardHeight","boardThickness"))
    steps = [
        command("drawing.open", drawing=drawing["id"]),
        command("drawing.sheet.set", sheet=sheet, title_block_overrides={
            "title": metadata["title"], "identification_number": metadata["part"],
            "date_of_issue": metadata["date"], "material": metadata["material"],
            "finish": "Unspecified", "legal_owner": "Unspecified",
            "created_by": "Spreadsheet to Drawing", "approved_by": "Unspecified",
        }),
    ]
    for view,a,b in [(views["top"],[0,h,t],[w,h,t]), (views["top"],[0,0,t],[0,h,t]),
                     (views["view"],[0,0,0],[0,0,t])]:
        steps.append(command("drawing.dimension.add", view=view, kind={"linear":{"a":a,"b":b}},
                             offset_mm=7, decimals=6))
    notes = [
        f'{c["totalSlots"]} slots {p["slotWidth"]:g} x {p["slotLength"]:g} mm THRU',
        f'{c["columnCount"]} columns x {c["rowCount"]} rows; X/Y pitch {c["pitchX"]:g} / {c["pitchY"]:g} mm',
        f'Left and bottom datum offset {p["edgeMargin"]:g} mm',
        f'Revision {metadata["revision"]} | Units mm | Scale {views["scale"]["text"]}',
    ]
    steps += [command("drawing.note.add", anchor={"sheet":sheet}, at=[30, 53-i*8],
                      content=note, cap_mm=2.5) for i,note in enumerate(notes)]
    steps += [
        command("drawing.export", sheet=sheet, format="svg", path="pegboard.svg"),
        command("drawing.export", sheet=sheet, format="png", dpi=150, path="pegboard.png"),
    ]
    result = run(folder, steps, model=folder/"with-views.sc", save="dimensioned.sc")
    for wanted, measured in zip((w,h,t), result[2:5]):
        if measured["status"] != "ok" or not math.isclose(wanted, measured["value"], abs_tol=TOL):
            raise ValueError("A SolidCraft drawing dimension failed verification.")
    for export in result[-2:]:
        if (len(export["views"]) != 4 or any(v["status"] != "drawn" for v in export["views"])
                or len(export["dimensions"]) != 3 or len(export["notes"]) != len(notes)
                or any(not obj["drawn"] for obj in export["dimensions"] + export["notes"])):
            raise ValueError("The SolidCraft drawing has undrawn views or annotations.")
    convert_svg(folder, "pdf")
    write_profile_dxf(folder/"pegboard.dxf", top_edges, notes)
    native.unlink()
    (folder/"dimensioned.sc").replace(native)
    inspect_geometry(*run(folder, INSPECT, model=native), p)
    return {"validated":True, "views":4, "dimensions":3, "scale":views["scale"]["text"]}


def acceptance(folder):
    from .acceptance import CASES, HEADERS

    rows, details = [], []
    source = None
    for i,(label,w,h,nr,nc) in enumerate(CASES,1):
        job = folder / f"case-{i}"
        job.mkdir()
        p = dict(DEFAULTS, boardWidth=w, boardHeight=h)
        evidence, _ = build_model(job, p, source, export_step=False)
        case = f"case_{i}.sc"
        source = folder / case
        (job / NATIVE).replace(source)
        if evidence["actualSlots"] != nr*nc:
            raise ValueError(f"SolidCraft acceptance case {label} returned an unexpected slot count.")
        rows.append([label,w,h,p["boardThickness"],nr,evidence["actualRows"],nc,evidence["actualColumns"],
                     nr*nc,evidence["actualSlots"],round(evidence["minimumClearance"],6),True,False,True,"PASS"])
        details.append(dict(case=label, parameters=p, expected=[nr,nc,nr*nc], result=evidence, passed=True, file=case))
    transitions = []
    for axis, metric, threshold in [("boardHeight","actualRows",86), ("boardWidth","actualColumns",48)]:
        for i,(offset,wanted) in enumerate([(-0.001,1),(0,2),(0.001,2),(-0.001,1)]):
            job = folder / f"{axis}-{i}"
            job.mkdir()
            p = dict(DEFAULTS, **{axis:threshold+offset})
            evidence, _ = build_model(job, p, source, export_step=False)
            source = job / NATIVE
            if evidence[metric] != wanted:
                raise ValueError(f"SolidCraft occurrence transition failed at {axis}={p[axis]}.")
            transitions.append(dict(parameter=axis, value=p[axis], expected=wanted, actual=evidence[metric], passed=True))
    with (folder/"pegboard_test_log.csv").open("w",encoding="utf-8",newline="") as file:
        writer = csv.writer(file)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    (folder/"validation_report.json").write_text(json.dumps({
        "solidcraft":VERSION,"geometryToleranceMM":TOL,"cases":details,"transitions":transitions
    },indent=2), encoding="utf-8")
    return {"cases":[{"name":case[0],"result":"PASS"} for case in CASES], "transitionsPassed":True}
