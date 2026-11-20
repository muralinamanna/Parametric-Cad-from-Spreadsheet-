import math

import pytest

from app.parameters import DEFAULTS, EPS, calculate, positions


@pytest.mark.parametrize("w,h,nr,nc", [(30,49,1,1),(300,200,5,16),(360,200,5,19)])
def test_counts_and_all_four_clearances(w,h,nr,nc):
    p = dict(DEFAULTS,boardWidth=w,boardHeight=h)
    c = calculate(p)
    assert (c["rowCount"],c["columnCount"],c["totalSlots"]) == (nr,nc,nr*nc)
    for x,y in positions(p,c):
        assert min(x,w-x-p["slotWidth"],y,h-y-p["slotLength"]) >= p["edgeMargin"]-EPS


@pytest.mark.parametrize("axis,count,threshold", [("boardWidth","columnCount",48),("boardHeight","rowCount",86)])
def test_transition_in_both_directions(axis,count,threshold):
    for offset,expected in [(0.001,2),(0,2),(-0.001,1),(0,2),(-EPS/2,2),(-2*EPS,1)]:
        assert calculate(dict(DEFAULTS, **{axis:threshold+offset}))[count] == expected


@pytest.mark.parametrize("invalid", [
    {"boardWidth":29.999}, {"boardHeight":48.999}, {"boardThickness":0},
    {"slotWidth":0}, {"slotLength":-1}, {"edgeMargin":-1}, {"slotSpacing":-1},
    {"boardWidth":math.nan}, {"boardHeight":math.inf}, {"edgeMargin":0},
    {"slotSpacing":0}, {"boardWidth":1e9}, {"boardWidth":1e308},
])
def test_invalid_dimensions(invalid):
    with pytest.raises(ValueError):
        calculate(DEFAULTS | invalid)


def test_zero_spacing_is_allowed_for_a_single_enclosed_opening():
    assert calculate(dict(DEFAULTS, boardWidth=30, boardHeight=49, slotSpacing=0))["totalSlots"] == 1


def test_decimal_minimum_accepts_binary_roundoff():
    p = dict(DEFAULTS, edgeMargin=0.1, slotWidth=0.1, slotLength=0.1, boardWidth=0.3, boardHeight=0.3)
    assert calculate(p)["totalSlots"] == 1
    with pytest.raises(ValueError):
        calculate(dict(p, boardWidth=0.29999999))
