"""Executed inside FreeCAD's Python interpreter by the local worker."""
import csv
import json
from pathlib import Path

import FreeCAD as App
import Part
import Sketcher
from draftmake.make_orthoarray import make_ortho_array

from parameters import DEFAULTS, EPS, FORMULAS, calculate, positions

V = App.Vector
CELLS = {key: f"B{index}" for index, key in enumerate([*DEFAULTS, *FORMULAS], 2)}

def edit(doc, p):
    for key in DEFAULTS:
        doc.Parameters.set(CELLS[key], f"{p[key]:.16g} mm")
    doc.recompute()

def build(p):
    doc = App.newDocument("Pegboard")
    sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
    sheet.set("A1", "Parameter")
    sheet.set("B1", "Value")
    for key, cell in CELLS.items():
        sheet.set(f"A{cell[1:]}", key)
        if key in DEFAULTS:
            sheet.set(cell, f"{p[key]:.16g} mm")
        else:
            sheet.set(cell, "=" + FORMULAS[key])
        sheet.setAlias(cell, key)
    sheet.setColumnWidth("A", 180)
    doc.recompute()

    blank = doc.addObject("Part::Box", "BoardBlank")
    for target, key in zip(("Length", "Width", "Height"), list(DEFAULTS)[:3]):
        blank.setExpression(target, f"Parameters.{key}")
    sketch = doc.addObject("Sketcher::SketchObject", "MasterSlot")
    w, h = p["slotWidth"], p["slotLength"]
    points = [V(0,0,0), V(w,0,0), V(w,h,0), V(0,h,0)]
    sketch.addGeometry([Part.LineSegment(points[i], points[(i+1)%4]) for i in range(4)], False)
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i+1)%4, 1))
        sketch.addConstraint(Sketcher.Constraint("Horizontal" if i%2 == 0 else "Vertical", i))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
    for edge, key, value in [(0, "slotWidth", w), (1, "slotLength", h)]:
        index = sketch.addConstraint(Sketcher.Constraint("Distance", edge, value))
        sketch.renameConstraint(index, key)
        sketch.setExpression(f"Constraints.{key}", f"Parameters.{key}")
    for axis in "xy":
        sketch.setExpression(f"Placement.Base.{axis}", "Parameters.edgeMargin")
    sketch.setExpression("Placement.Base.z", "-1 mm")

    punch = doc.addObject("Part::Extrusion", "ThroughCutter")
    punch.Base = sketch
    punch.DirMode = "Custom"
    punch.Dir = V(0,0,1)
    punch.Solid = True
    punch.setExpression("LengthFwd", "Parameters.boardThickness + 2 mm")
    doc.recompute()

    pattern = make_ortho_array(punch, n_x=1, n_y=1, n_z=1, use_link=False)
    pattern.Label = "Rectangular slot pattern"
    for prop, expression in {
        "NumberX": "columnCount", "NumberY": "rowCount",
        "IntervalX.x": "pitchX / 1 mm", "IntervalY.y": "pitchY / 1 mm",
    }.items():
        pattern.setExpression(prop, "Parameters." + expression)
    cleanup = [blank, sketch, punch, pattern]
    result = doc.addObject("Part::Cut", "Pegboard")
    result.Base = blank
    result.Tool = pattern
    result.Refine = True
    doc.recompute()
    for obj in cleanup:
        obj.Visibility = False
    if App.GuiUp:
        import FreeCADGui as Gui
        result.ViewObject.ShapeColor = (0.73,0.79,0.87)
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
    return doc

def check(doc, p):
    c = calculate(p)
    sheet, sketch, result = doc.Parameters, doc.MasterSlot, doc.Pegboard
    shape = result.Shape
    broken = [obj.Name for obj in doc.Objects if any(state in {"Invalid", "Error", "Touched"} for state in obj.State)]
    stats = dict(shapeValid=False, brokenReferences=broken, recomputeSuccessful=not broken)
    errors = []
    for key, expected in {**p, **c}.items():
        actual = getattr(sheet, key, None)
        actual = getattr(actual, "Value", actual)
        if actual is None or abs(actual-expected) > EPS:
            errors.append(f"Spreadsheet {key}: {actual} instead of {expected}")
    if not sketch.FullyConstrained:
        errors.append("MasterSlot is underconstrained.")
    if (result.Base != doc.BoardBlank or result.Tool.Base != doc.ThroughCutter
            or doc.ThroughCutter.Base != sketch or len(result.Tool.ExpressionEngine) != 4
            or len(sketch.ExpressionEngine) != 5 or len(result.Base.ExpressionEngine) != 3
            or not doc.ThroughCutter.ExpressionEngine):
        errors.append("Feature history is incomplete.")
    if broken:
        errors.append("FreeCAD reports incomplete objects: " + ", ".join(broken))

    w, h, t = (p[key] for key in list(DEFAULTS)[:3])
    sw, sl, margin = (p[key] for key in ("slotWidth", "slotLength", "edgeMargin"))
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        return {**stats, "errors": errors + ["Result must be one valid solid."]}
    stats["shapeValid"] = True
    bounds = shape.BoundBox
    if any(abs(a-b) > EPS for a,b in zip(
            [bounds.XMin, bounds.YMin, bounds.ZMin, bounds.XLength, bounds.YLength, bounds.ZLength],
            [0,0,0,w,h,t])):
        errors.append("Board placement or dimensions differ from the spreadsheet.")
    if abs(shape.Volume - (w*h-c["totalSlots"]*sw*sl)*t) > EPS*max(1, w*h, w*t, h*t):
        errors.append("Solid volume does not match the intended through-cut volume.")

    def holes(z):
        face = next((f for f in shape.Faces if abs(f.BoundBox.ZMin-z) <= EPS and abs(f.BoundBox.ZMax-z) <= EPS), None)
        if face is None:
            return []
        boxes = [wire.BoundBox for wire in face.Wires if not wire.isSame(face.OuterWire)]
        return sorted((b.XMin, b.YMin, b.XLength, b.YLength) for b in boxes)

    top, bottom = holes(t), holes(0)
    intended = sorted((x,y,sw,sl) for x,y in positions(p,c))
    for name, loops in [("top",top), ("bottom",bottom)]:
        # Match in row/column order, allowing noise on nominally equal coordinates.
        loops.sort(key=lambda a: (round((a[0]-margin)/c["pitchX"]), a[1]))
        if len(loops) != len(intended) or any(abs(a-b)>EPS for actual,target in zip(loops,intended) for a,b in zip(actual,target)):
            errors.append(f"The {name} face does not contain the expected rectangular slot loops.")
    stats.update(actualSlots=len(top), actualRows=len(set(round((y-margin)/c["pitchY"]) for _,y,_,_ in top)),
                 actualColumns=len(set(round((x-margin)/c["pitchX"]) for x,_,_,_ in top)))
    if top:
        minimums = [min(values) for values in zip(*[(x,w-x-a,y,h-y-b) for x,y,a,b in top])]
        stats["edgeClearances"] = dict(zip(("left","right","bottom","top"),minimums))
        stats["minimumClearance"] = min(minimums)
        if min(minimums) < margin-EPS:
            errors.append("Minimum edge clearance violated.")
    stats.update(topOpenings=top, bottomOpenings=bottom, errors=errors)
    return stats

CASES = [("Smallest valid board",30,49,1,1), ("Nominal board",300,200,5,16), ("Wider board",360,200,5,19)]
HEADERS = ["Test Case","Board Width","Board Height","Board Thickness","Expected Rows","Actual Rows",
           "Expected Columns","Actual Columns","Expected Slots","Actual Slots","Minimum Edge Clearance",
           "Shape Valid","Broken References","Recompute Successful","Result"]

def run_tests(folder):
    doc = build(DEFAULTS)
    rows, details, transitions = [], [], []
    for index, (label,w,h,nr,nc) in enumerate(CASES,1):
        p = dict(DEFAULTS, boardWidth=w, boardHeight=h)
        edit(doc,p)
        result = check(doc,p)
        actual = [result.get(key) for key in ("actualRows","actualColumns","actualSlots")]
        passed = not result["errors"] and actual == [nr,nc,nr*nc]
        filename = f"case_{index}.FCStd"
        if passed:
            doc.saveAs(str(folder / filename))
        rows.append([label,w,h,p["boardThickness"],nr,actual[0],nc,actual[1],nr*nc,actual[2],
                     result.get("minimumClearance"),result["shapeValid"],bool(result["brokenReferences"]),
                     result["recomputeSuccessful"],"PASS" if passed else "FAIL"])
        details.append(dict(case=label, parameters=p, expected=[nr,nc,nr*nc], result=result,
                            passed=passed, file=filename if passed else None))
    for parameter, measured, threshold in [("boardHeight","actualRows",86), ("boardWidth","actualColumns",48)]:
        for offset, count in [(0.001,2),(0,2),(-0.001,1),(0,2)]:
            p = dict(DEFAULTS, **{parameter: threshold+offset})
            edit(doc,p)
            evidence = check(doc,p)
            transitions.append(dict(parameter=parameter, value=p[parameter], expected=count,
                                    actual=evidence.get(measured), errors=evidence["errors"],
                                    passed=not evidence["errors"] and evidence.get(measured)==count))
    with (folder/"pegboard_test_log.csv").open("w",newline="") as log:
        writer=csv.writer(log)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    report = dict(freecad=".".join(App.Version()[:3]), geometryToleranceMM=EPS, cases=details, transitions=transitions)
    (folder/"validation_report.json").write_text(json.dumps(report,indent=2))
    return {"cases": [{"name": row[0], "result": row[-1]} for row in rows], "transitionsPassed": all(t["passed"] for t in transitions)}

def main(job_file):
    job = json.loads(Path(job_file).read_text())
    folder = Path(job["output"])
    response = folder/"result.json"
    try:
        if job["action"] == "health":
            result = {"version": ".".join(App.Version()[:3])}
        elif job["action"] == "tests":
            result = run_tests(folder)
        else:
            p = job["parameters"]
            c = calculate(p)
            if job.get("model"):
                doc = App.openDocument(job["model"])
                for name in ("EngineeringDrawing", "TopView", "FrontView", "RightView", "IsometricView", "SheetTemplate"):
                    if doc.getObject(name):
                        doc.removeObject(name)
                edit(doc,p)
            else:
                doc = build(p)
            result = check(doc,p)
            if result["errors"]:
                raise ValueError("; ".join(result["errors"]))
            if job["action"] == "drawing":
                from drawing import draw
                draw(doc,p,c,folder,job["metadata"])
            doc.saveAs(str(folder/"pegboard.FCStd"))
            doc.Pegboard.Shape.exportStep(str(folder/"pegboard.step"))
        response.write_text(json.dumps(result))
    except Exception as error:
        import traceback
        traceback.print_exc()
        response.write_text(json.dumps({"error": str(error)}))
