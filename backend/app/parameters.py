"""Shared millimetre geometry rules for the web API and FreeCAD worker."""
from math import floor, isclose, isfinite

DEFAULTS = dict(boardWidth=300, boardHeight=200, boardThickness=6, edgeMargin=12,
                slotWidth=6, slotLength=25, slotSpacing=12)
EPS = 1e-7  # mm, used at occurrence boundaries and for CAD clearance
FORMULAS = {
    "minBoardWidth": "2 * edgeMargin + slotWidth",
    "minBoardHeight": "2 * edgeMargin + slotLength",
    "pitchX": "slotWidth + slotSpacing",
    "pitchY": "slotLength + slotSpacing",
    "availableWidth": "boardWidth - 2 * edgeMargin",
    "availableHeight": "boardHeight - 2 * edgeMargin",
    "columnCount": "floor((availableWidth - slotWidth + 0.0000001 mm) / pitchX) + 1",
    "rowCount": "floor((availableHeight - slotLength + 0.0000001 mm) / pitchY) + 1",
    "totalSlots": "columnCount * rowCount",
    "rightClearance": "boardWidth - edgeMargin - slotWidth - (columnCount - 1) * pitchX",
    "topClearance": "boardHeight - edgeMargin - slotLength - (rowCount - 1) * pitchY",
}

def calculate(values):
    p = {key: float(values[key]) for key in DEFAULTS}
    if not all(isfinite(value) for value in p.values()):
        raise ValueError("All parameters must be finite numbers.")
    w, h, t, m, sw, sl, gap = p.values()
    if max(p.values()) > 1_000_000:
        raise ValueError("Dimensions cannot exceed 1,000,000 mm.")
    if min(t, sw, sl) <= EPS or m < 0 or gap < 0:
        raise ValueError("Thickness and slot dimensions must exceed 0.0000001 mm. Margin and spacing must be nonnegative.")
    minimum_w, minimum_h = 2*m+sw, 2*m+sl
    if ((w < minimum_w and not isclose(w, minimum_w, rel_tol=2e-16, abs_tol=1e-12))
            or (h < minimum_h and not isclose(h, minimum_h, rel_tol=2e-16, abs_tol=1e-12))):
        raise ValueError(f"Minimum board size for these inputs is {minimum_w:g} × {minimum_h:g} mm.")
    px, py = sw+gap, sl+gap
    cols = floor((w-minimum_w+EPS)/px)+1
    rows = floor((h-minimum_h+EPS)/py)+1
    if cols*rows > 2000:
        raise ValueError("This application supports up to 2,000 slots per board.")
    right = w-m-sw-(cols-1)*px
    top = h-m-sl-(rows-1)*py
    if min(m, right, top) <= EPS or (cols*rows > 1 and gap <= EPS):
        raise ValueError("Distinct enclosed through-slots require positive material around every opening and between neighboring openings.")
    return dict(minBoardWidth=minimum_w, minBoardHeight=minimum_h, pitchX=px, pitchY=py,
                availableWidth=w-2*m, availableHeight=h-2*m, columnCount=cols,
                rowCount=rows, totalSlots=cols*rows, rightClearance=right, topClearance=top)

def positions(p, c):
    return [(p["edgeMargin"]+col*c["pitchX"], p["edgeMargin"]+row*c["pitchY"])
            for row in range(c["rowCount"]) for col in range(c["columnCount"])]
