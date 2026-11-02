#!/usr/bin/env python3
"""Restore the transverse and edge-rail thermal slots and preserve routing."""

from __future__ import annotations
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))

import os
from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import (ensure_gnd_bridge, ensure_heater_spreader,
                            ensure_thermal_gap, replace_thermal_slots,
                            save_board_preserving_project, thermal_slot_items)
from route_thermal_barrier import apply as route_thermal_barrier


HERE = Path(__file__).resolve().parent.parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0


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


def add_via(board, netname, position, diameter=0.25, drill=0.15) -> None:
    item = pcbnew.PCB_VIA(board)
    item.SetNet(board.FindNet(netname))
    item.SetPosition(point(*position))
    item.SetWidth(pcbnew.FromMM(diameter))
    item.SetDrill(pcbnew.FromMM(drill))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(item)


def same_endpoints(item, start, end) -> bool:
    actual = frozenset((local_xy(item.GetStart()), local_xy(item.GetEnd())))
    return actual == frozenset((start, end))


def replace_path(board, netname, layer, width, old_segments, new_segments,
                 new_width=None) -> None:
    if new_width is None:
        new_width = width

    def matches(segments, wanted_width):
        return [
            item for item in board.GetTracks()
            if not isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == netname
            and item.GetLayer() == layer
            and round(pcbnew.ToMM(item.GetWidth()), 4) == wanted_width
            and any(same_endpoints(item, start, end) for start, end in segments)
        ]

    old_items = matches(old_segments, width)
    new_items = matches(new_segments, new_width)
    if len(new_items) == len(new_segments) and not old_items:
        return
    if len(old_items) != len(old_segments) or new_items:
        raise SystemExit(
            f"ambiguous {netname} {board.GetLayerName(layer)} side-slot route: "
            f"old {len(old_items)}/{len(old_segments)}, new {len(new_items)}/{len(new_segments)}"
        )
    for item in old_items:
        board.Delete(item)
    for start, end in new_segments:
        track_segment(board, netname, layer, start, end, new_width)


def replace_via(board, netname, old_position, new_position) -> None:
    old = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and local_xy(item.GetPosition()) == old_position
    ]
    new = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and local_xy(item.GetPosition()) == new_position
    ]
    if len(new) == 1 and not old:
        return
    if len(old) != 1 or new:
        raise SystemExit(
            f"ambiguous {netname} side-slot via: old {len(old)}, new {len(new)}"
        )
    board.Delete(old[0])
    add_via(board, netname, new_position)


def reroute_side_slots(board) -> None:
    """Move the four historical cut-line routes into the central island."""
    replace_path(
        board, "/I2C_SCL", pcbnew.F_Cu, 0.09,
        (((2.2, 102.7), (1.5, 102.7)),),
        (((2.2, 102.7), (1.95, 102.7)),),
    )
    replace_path(
        board, "/I2C_SCL", pcbnew.In1_Cu, 0.09,
        (((1.5, 102.7), (1.5, 99.5)), ((1.5, 99.5), (12.5, 99.5))),
        (((1.95, 102.7), (1.95, 99.5)), ((1.95, 99.5), (12.5, 99.5))),
    )
    replace_via(board, "/I2C_SCL", (1.5, 102.7), (1.95, 102.7))

    replace_path(
        board, "/I2C_SDA", pcbnew.F_Cu, 0.09,
        (((2.8, 101.1), (2.0, 100.5)), ((2.0, 100.5), (0.7, 100.5))),
        (((2.8, 101.1), (2.35, 100.5)),),
    )
    replace_path(
        board, "/I2C_SDA", pcbnew.In1_Cu, 0.09,
        (((0.7, 100.5), (0.7, 103.5)), ((0.7, 103.5), (12.0, 103.5))),
        (((2.35, 100.5), (2.35, 103.5)), ((2.35, 103.5), (12.0, 103.5))),
    )
    replace_via(board, "/I2C_SDA", (0.7, 100.5), (2.35, 100.5))
    replace_path(
        board, "/I2C_SDA", pcbnew.F_Cu, 0.09,
        (((17.2625, 101.0), (17.8, 101.0)),
         ((17.8, 101.0), (17.8, 103.5))),
        (((17.2625, 101.0), (18.1, 101.0)),
         ((18.1, 101.0), (18.1, 103.5)),
         ((18.1, 103.5), (17.5, 103.5))),
    )
    replace_path(
        board, "/I2C_SDA", pcbnew.In1_Cu, 0.09,
        (((12.0, 103.5), (17.8, 103.5)),),
        (((12.0, 103.5), (17.5, 103.5)),),
    )
    replace_via(board, "/I2C_SDA", (17.8, 103.5), (17.5, 103.5))

    replace_path(
        board, "/HEATER_PWM", pcbnew.In1_Cu, 0.18,
        (((13.85, 86.5), (18.0, 90.0)),
         ((18.0, 90.0), (18.5, 90.5)),
         ((18.5, 90.5), (18.5, 104.2)),
         ((18.5, 104.2), (6.8, 104.6))),
        (((13.85, 86.5), (18.1, 90.0)),
         ((18.1, 90.0), (18.1, 104.2)),
         ((18.1, 104.2), (6.8, 104.6))),
        # This corridor has only 0.75 mm between the +12 V via centre and the
        # slot edge.  A 0.12 mm control trace leaves positive margin above both
        # the 0.15 mm copper clearance and 0.20 mm copper-to-edge rules.
        new_width=0.12,
    )
    replace_path(
        board, "/HEATER_LOW", pcbnew.B_Cu, 0.8,
        (((15.0, 99.4625), (18.5, 98.5)),
         ((18.5, 98.5), (19.0, 104.0)),
         ((19.0, 104.0), (19.25, 105.5))),
        (((15.0, 99.4625), (16.45, 100.5)),
         ((16.45, 100.5), (16.45, 104.25)),
         ((16.45, 104.25), (19.0, 104.25)),
         ((19.0, 104.25), (19.25, 105.5))),
    )


def ensure_sensor_aperture(board) -> None:
    """Keep the embedded SGX aperture synchronized with its project library."""
    sensors = [fp for fp in board.Footprints() if fp.GetReference() == "U11"]
    if len(sensors) != 1:
        raise SystemExit(f"found {len(sensors)} U11 footprints, want one")
    apertures = [
        pad for pad in sensors[0].Pads()
        if not pad.GetNumber() and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
    ]
    if len(apertures) != 1:
        raise SystemExit(f"U11 has {len(apertures)} NPTH apertures, want one")
    aperture = apertures[0]
    actual = local_xy(aperture.GetPosition())
    if actual not in ((10.0, 96.0), (10.0, 95.3)):
        raise SystemExit(f"U11 aperture at local {actual}, want (10,96) or (10,95.3)")
    aperture.SetPosition(point(10.0, 95.3))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    edge_items = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    slot_items = thermal_slot_items(board)
    if slot_items:
        if len(edge_items) not in (14, 22) or len(slot_items) not in (8, 16):
            raise SystemExit(
                f"unexpected existing thermal-slot geometry: {len(edge_items)} Edge.Cuts, "
                f"{len(slot_items)} slot items"
            )
    else:
        if len(edge_items) != 6:
            raise SystemExit(f"expected six-item square-tip outline before migration, found {len(edge_items)} items")
    replace_thermal_slots(board)
    reroute_side_slots(board)
    ensure_sensor_aperture(board)
    ensure_thermal_gap(board)
    ensure_heater_spreader(board)
    ensure_gnd_bridge(board)
    # The barrier router already recognizes both the original long SCL segment
    # and every accepted expanded-barrier state.  Keep that migration logic in
    # one place instead of maintaining a second stale state machine here.
    route_thermal_barrier(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(
        f"wrote {OUT}: two 6.75 x 1.5 mm horizontal slots at Y=134 mm plus "
        "two 0.8 x 16 mm side slots; 5 mm centre neck, 2 mm all-layer pour "
        "gap, heated B.Cu spreader"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
