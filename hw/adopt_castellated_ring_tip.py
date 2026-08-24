#!/usr/bin/env python3
"""Square the gas end and install the edge-plated heated-ring interface.

This deterministic migration replaces J5's inset front/back SMD lands with two
plated-slot castellations centred on the left and right board edges.  The gas
end is changed from R2 corners to square corners, and the complete HEATER_LOW
tip route is rebuilt so the two contacts remain joined without the metal ring.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import (ensure_gnd_bridge, ensure_heater_spreader,
                            ensure_thermal_gap, replace_thermal_slots,
                            save_board_preserving_project)
from route_thermal_barrier import apply as route_thermal_barrier


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0


def point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def absolute_xy(position) -> tuple[float, float]:
    return round(pcbnew.ToMM(position.x), 4), round(pcbnew.ToMM(position.y), 4)


def local_xy(position) -> tuple[float, float]:
    return (
        round(pcbnew.ToMM(position.x) - ORIGIN_X_MM, 4),
        round(pcbnew.ToMM(position.y) - ORIGIN_Y_MM, 4),
    )


def edge_line(board, start, end) -> None:
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_SEGMENT)
    item.SetStart(point(*start))
    item.SetEnd(point(*end))
    item.SetLayer(pcbnew.Edge_Cuts)
    item.SetWidth(pcbnew.FromMM(0.05))
    board.Add(item)


def edge_arc(board, start, midpoint, end) -> None:
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_ARC)
    item.SetArcGeometry(point(*start), point(*midpoint), point(*end))
    item.SetLayer(pcbnew.Edge_Cuts)
    item.SetWidth(pcbnew.FromMM(0.05))
    board.Add(item)


def add_square_tip_outline(board) -> None:
    edge_line(board, (2.0, 0.0), (18.0, 0.0))
    edge_arc(board, (18.0, 0.0), (19.414, 0.586), (20.0, 2.0))
    edge_line(board, (20.0, 2.0), (20.0, 107.0))
    edge_line(board, (20.0, 107.0), (0.0, 107.0))
    edge_line(board, (0.0, 107.0), (0.0, 2.0))
    edge_arc(board, (0.0, 2.0), (0.586, 0.586), (2.0, 0.0))


def segment(board, netname: str, start, end, width=0.80) -> None:
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(board.FindNet(netname))
    item.SetLayer(pcbnew.B_Cu)
    item.SetStart(point(*start))
    item.SetEnd(point(*end))
    item.SetWidth(pcbnew.FromMM(width))
    board.Add(item)


def path(board, netname: str, points, width=0.80) -> None:
    for start, end in zip(points, points[1:]):
        segment(board, netname, start, end, width)


def same_endpoints(item, start, end) -> bool:
    return frozenset((local_xy(item.GetStart()), local_xy(item.GetEnd()))) == frozenset((start, end))


def fresh_ring() -> pcbnew.FOOTPRINT:
    """Clone J5 from a generator seed so the board and library cannot drift."""
    with tempfile.TemporaryDirectory(prefix="o2-castellated-ring-") as directory:
        seed_path = Path(directory) / "o2-probe.kicad_pcb"
        environment = os.environ.copy()
        environment["O2_PCB_OUT"] = str(seed_path)
        subprocess.run([sys.executable, str(HERE / "gen_pcb.py")], cwd=HERE,
                       env=environment, check=True, capture_output=True, text=True)
        seed = pcbnew.LoadBoard(str(seed_path))
        source = next(fp for fp in seed.Footprints() if fp.GetReference() == "J5")
        return pcbnew.Cast_to_FOOTPRINT(source.Duplicate(False))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    footprints = {fp.GetReference(): fp for fp in board.Footprints()}
    old_ring = footprints.get("J5")
    if old_ring is None:
        raise SystemExit("J5 is missing")

    # Replace the two y=134 slots with the accepted wider geometry while
    # replacing the outer contour. Both the former rounded outline and this new
    # six-item outline are accepted as migration inputs.
    edges = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    slots = [
        item for item in edges
        if 133.2 <= min(absolute_xy(item.GetStart())[1], absolute_xy(item.GetEnd())[1])
        and max(absolute_xy(item.GetStart())[1], absolute_xy(item.GetEnd())[1]) <= 134.8
    ]
    outer = [item for item in edges if item not in slots]
    if len(slots) != 8 or len(outer) not in (6, 8):
        raise SystemExit(
            f"unexpected Edge.Cuts input: {len(outer)} outer and {len(slots)} slot items"
        )
    for item in outer:
        board.Delete(item)
    add_square_tip_outline(board)
    replace_thermal_slots(board)
    ensure_thermal_gap(board)

    # Replace the footprint as a whole so the library is the single source for
    # pad, plated-slot, mask, and courtyard geometry.
    ring = fresh_ring()
    board.Delete(old_ring)
    board.Add(ring)
    ring.SetPosition(point(10.0, 105.5))
    ring.SetOrientationDegrees(0.0)
    ring.Reference().SetLayer(pcbnew.F_Fab)
    for field in ring.GetFields():
        field.SetVisible(False)
    heater_low = board.FindNet("/HEATER_LOW")
    if heater_low is None:
        raise SystemExit("/HEATER_LOW net is missing")
    for pad in ring.Pads():
        pad.SetNet(heater_low)
    ensure_heater_spreader(board)
    ensure_gnd_bridge(board)

    # Remove the complete previous branch, including the two obsolete stitch
    # vias, then route directly into the through-plated edge contacts.
    old_heater_items = [item for item in board.GetTracks()
                        if item.GetNetname() == "/HEATER_LOW"]
    if not old_heater_items:
        raise SystemExit("no existing HEATER_LOW route found")
    for item in old_heater_items:
        board.Delete(item)
    path(board, "/HEATER_LOW",
         ((5.0, 99.4625), (3.0, 101.0), (3.0, 103.5),
          (1.0, 104.5), (0.75, 105.5)))
    path(board, "/HEATER_LOW",
         ((15.0, 99.4625), (18.5, 98.5), (19.0, 104.0), (19.25, 105.5)))
    segment(board, "/HEATER_LOW", (0.75, 106.25), (19.25, 106.25))
    segment(board, "/HEATER_LOW", (10.0, 102.1875), (10.0, 106.25))

    # Pull the In1 PWM return 0.9 mm inboard so the right castellation does not
    # contact the previous x=19.3 mm corridor on the inner copper layer.
    old_pwm_tail = (
        ((13.85, 86.5), (18.8, 90.0)),
        ((18.8, 90.0), (19.3, 90.5)),
        ((19.3, 90.5), (19.3, 104.6)),
        ((19.3, 104.6), (6.8, 104.6)),
    )
    new_pwm_tail = (
        ((13.85, 86.5), (18.0, 90.0)),
        ((18.0, 90.0), (18.5, 90.5)),
        ((18.5, 90.5), (18.5, 104.2)),
        ((18.5, 104.2), (6.8, 104.6)),
    )
    pwm_tail_items = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/HEATER_PWM"
        and item.GetLayer() == pcbnew.In1_Cu
        and any(same_endpoints(item, *pair) for pair in old_pwm_tail + new_pwm_tail)
    ]
    if len(pwm_tail_items) != 4:
        raise SystemExit(f"expected four HEATER_PWM tail segments, found {len(pwm_tail_items)}")
    for item in pwm_tail_items:
        board.Delete(item)
    for start, end in new_pwm_tail:
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(board.FindNet("/HEATER_PWM"))
        item.SetLayer(pcbnew.In1_Cu)
        item.SetStart(point(*start))
        item.SetEnd(point(*end))
        item.SetWidth(pcbnew.FromMM(0.18))
        board.Add(item)

    route_thermal_barrier(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(
        f"wrote {OUT}: square gas end; two 2.00 x 3.00 mm J5 pads with "
        "1.00 x 2.00 mm plated-slot castellations; 6.75 x 1.5 mm barrier slots, "
        "all-layer pour gap, and heated B.Cu spreader"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
