#!/usr/bin/env python3
"""Restore the two Y=134 mm thermal slots and preserve the neck crossing."""

from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0
THERMAL_SLOTS = ((3.75, 84.0, 5.5, 1.0), (16.25, 84.0, 5.5, 1.0))


def point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def local_xy(position) -> tuple[float, float]:
    return (
        round(pcbnew.ToMM(position.x) - ORIGIN_X_MM, 4),
        round(pcbnew.ToMM(position.y) - ORIGIN_Y_MM, 4),
    )


def edge_line(board, start, end) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(point(*start))
    shape.SetEnd(point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def edge_arc(board, start, midpoint, end) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(point(*start), point(*midpoint), point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def add_horizontal_slot(board, x, y, length, width) -> None:
    x0, x1 = x - length / 2, x + length / 2
    y0, y1 = y - width / 2, y + width / 2
    radius = width / 2
    edge_line(board, (x0 + radius, y0), (x1 - radius, y0))
    edge_arc(board, (x1 - radius, y0), (x1, y), (x1 - radius, y1))
    edge_line(board, (x1 - radius, y1), (x0 + radius, y1))
    edge_arc(board, (x0 + radius, y1), (x0, y), (x0 + radius, y0))


def track_segment(board, netname, layer, start, end, width) -> None:
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(board.FindNet(netname))
    item.SetLayer(layer)
    item.SetStart(point(*start))
    item.SetEnd(point(*end))
    item.SetWidth(pcbnew.FromMM(width))
    board.Add(item)


def same_endpoints(item, start, end) -> bool:
    actual = frozenset((local_xy(item.GetStart()), local_xy(item.GetEnd())))
    return actual == frozenset((start, end))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    edge_items = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    slot_items = [
        item for item in edge_items
        if 83.4 <= min(local_xy(item.GetStart())[1], local_xy(item.GetEnd())[1])
        and max(local_xy(item.GetStart())[1], local_xy(item.GetEnd())[1]) <= 84.6
    ]
    if slot_items:
        if len(edge_items) != 14 or len(slot_items) != 8:
            raise SystemExit(
                f"unexpected existing Y=134 slot geometry: {len(edge_items)} Edge.Cuts, "
                f"{len(slot_items)} slot-band items"
            )
    else:
        if len(edge_items) != 6:
            raise SystemExit(f"expected six-item square-tip outline before migration, found {len(edge_items)} items")
        for slot_spec in THERMAL_SLOTS:
            add_horizontal_slot(board, *slot_spec)

    original_scl = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/I2C_SCL"
        and item.GetLayer() == pcbnew.B_Cu
        and same_endpoints(item, (2.4, 79.1), (10.65, 87.35))
    ]
    neck_points = ((2.4, 79.1), (7.1, 82.8), (8.2, 84.0), (10.65, 87.35))
    interim_b_scl = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/I2C_SCL"
        and item.GetLayer() == pcbnew.B_Cu
        and any(same_endpoints(item, start, end)
                for start, end in zip(neck_points, neck_points[1:]))
    ]
    interim_in1_scl = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/I2C_SCL"
        and item.GetLayer() == pcbnew.In1_Cu
        and any(same_endpoints(item, start, end)
                for start, end in zip(neck_points, neck_points[1:]))
    ]
    interim_vias = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/I2C_SCL"
        and local_xy(item.GetPosition()) in (neck_points[0], neck_points[-1])
    ]
    if len(original_scl) == 1:
        if interim_b_scl or interim_in1_scl or interim_vias:
            raise SystemExit("original SCL neck crossing coexists with an interim detour")
    elif not original_scl:
        valid_interim = (
            (len(interim_b_scl) == 3 and not interim_in1_scl and not interim_vias)
            or (not interim_b_scl and len(interim_in1_scl) == 3 and len(interim_vias) == 2)
        )
        if not valid_interim:
            raise SystemExit("ambiguous I2C_SCL neck-crossing route state")
        for item in interim_b_scl + interim_in1_scl + interim_vias:
            board.Delete(item)
        track_segment(board, "/I2C_SCL", pcbnew.B_Cu,
                      (2.4, 79.1), (10.65, 87.35), 0.09)
    else:
        raise SystemExit("multiple original I2C_SCL neck crossings are present")

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(OUT), board)
    print(
        f"wrote {OUT}: two 5.5 x 1.0 mm horizontal slots at Y=134 mm; "
        "I2C_SCL preserved through 7 mm centre neck"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
