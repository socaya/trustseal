"""Deterministic tests for Stamp Studio's pure SVG arc geometry module."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


MODULE = Path(__file__).parents[2] / "app/static/js/stamp_typography_geometry.js"


def _node(expression: str):
    script = (
        f"const G=require({json.dumps(str(MODULE))});"
        f"const value=({expression});"
        "process.stdout.write(JSON.stringify(value));"
    )
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def test_upper_and_lower_paths_are_upright_left_to_right():
    arcs = _node("[G.buildArc({rx:100,ry:100,side:'top'}),"
                 "G.buildArc({rx:100,ry:100,side:'bottom'})]")
    top, bottom = arcs
    assert round(top["start"]["x"]) == -100
    assert round(top["end"]["x"]) == 100
    assert top["sweepFlag"] == 1
    assert round(bottom["start"]["x"]) == -100
    assert round(bottom["end"]["x"]) == 100
    assert bottom["sweepFlag"] == 0


def test_custom_sweep_sets_large_arc_and_reverse_swaps_traversal():
    normal, reverse = _node(
        "[G.buildArc({rx:120,ry:80,side:'top',sweep:240}),"
        "G.buildArc({rx:120,ry:80,side:'top',sweep:240,direction:'reverse'})]"
    )
    assert normal["largeArc"] == reverse["largeArc"] == 1
    assert normal["start"] == reverse["end"]
    assert normal["end"] == reverse["start"]
    assert normal["sweepFlag"] != reverse["sweepFlag"]


def test_oval_path_uses_independent_axes_without_glyph_transform():
    arc = _node("G.buildArc({rx:150,ry:100,side:'top',sweep:180})")
    assert arc["rx"] == 150
    assert arc["ry"] == 100
    assert "A 150 100" in arc["d"]


def test_shrink_fit_leaves_short_text_natural_and_constrains_long_text():
    fits = _node(
        "(()=>{const a=G.buildArc({rx:100,ry:100,side:'top',sweep:120});"
        "return [G.fitText('OK',a,{mode:'shrink',size:18}),"
        "G.fitText('A VERY LONG OFFICIAL ORGANISATION NAME',a,{mode:'shrink',size:24,tracking:3})]})()"
    )
    assert fits[0]["target"] is None
    assert fits[0]["overflow"] is False
    assert fits[1]["target"] is not None
    assert fits[1]["overflow"] is True
    assert fits[1]["target"] <= fits[1]["available"]


def test_border_clearance_reduces_path_radius_for_large_text():
    small, large = _node(
        "[G.safePathRadius({outerRadius:140,borderWidth:3,fontSize:12,clearance:5}),"
        "G.safePathRadius({outerRadius:140,borderWidth:3,fontSize:32,clearance:5})]"
    )
    assert large < small < 140


def test_concentric_radius_aligns_top_and_bottom_optical_center():
    r_top, r_bot = _node(
        "[G.concentricRadius({bandRadius:115,fontSize:18,side:'top'}),"
        "G.concentricRadius({bandRadius:115,fontSize:18,side:'bottom'})]"
    )
    cap = 18 * 0.72  # 12.96
    # Top baseline is shifted inward so glyphs extend outward to 115 + cap/2
    assert abs(r_top - (115 - cap / 2)) < 0.01
    # Bottom baseline is shifted outward so glyphs extend inward to 115 - cap/2
    assert abs(r_bot - (115 + cap / 2)) < 0.01
    # Both share the exact optical centerline of 115
    optical_top = r_top + cap / 2
    optical_bot = r_bot - cap / 2
    assert round(optical_top, 2) == round(optical_bot, 2) == 115.0


def test_build_concentric_arc_generates_symmetric_arcs():
    top_arc, bot_arc = _node(
        "[G.buildConcentricArc({bandRadius:115,fontSize:20,side:'top',sweep:180}),"
        "G.buildConcentricArc({bandRadius:115,fontSize:20,side:'bottom',sweep:180})]"
    )
    assert top_arc["side"] == "top"
    assert bot_arc["side"] == "bottom"
    assert top_arc["sweepFlag"] == 1
    assert bot_arc["sweepFlag"] == 0
    assert top_arc["ry"] < 115 < bot_arc["ry"]
