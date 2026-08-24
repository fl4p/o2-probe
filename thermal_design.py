#!/usr/bin/env python3
"""Shared deterministic geometry for the O2 probe thermal barrier and island."""

from __future__ import annotations

from pathlib import Path

import pcbnew


ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0

# The user-expanded 6.75 mm contours leave 0.75 mm FR-4 at each board edge and
# a 5.0 mm centre neck. The 1.5 mm cutter width provides the axial air gap.
THERMAL_SLOTS = (
    (4.125, 84.0, 6.75, 1.5),
    (15.875, 84.0, 6.75, 1.5),
)
THERMAL_GAP_NAME = "THERMAL_BARRIER_COPPER_GAP"
HEATER_SPREADER_NAME = "HEATED_ISLAND_SPREADER"
THERMAL_GAP = ((0.0, 83.0), (20.0, 83.0), (20.0, 85.0), (0.0, 85.0))
HEATER_SPREADER = ((0.25, 85.0), (19.75, 85.0),
                   (19.75, 106.75), (0.25, 106.75))
GND_BRIDGE = ((0.5, 83.0), (0.4, 83.1), (0.4, 84.9), (0.5, 85.0))


def point(x: float, y: float):
    return pcbnew.VECTOR2I(
        pcbnew.FromMM(ORIGIN_X_MM + x), pcbnew.FromMM(ORIGIN_Y_MM + y)
    )


def absolute_xy(position) -> tuple[float, float]:
    return round(pcbnew.ToMM(position.x), 4), round(pcbnew.ToMM(position.y), 4)


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


def add_horizontal_slot(board, x: float, y: float,
                        length: float, width: float) -> None:
    x0, x1 = x - length / 2, x + length / 2
    y0, y1 = y - width / 2, y + width / 2
    radius = width / 2
    edge_line(board, (x0 + radius, y0), (x1 - radius, y0))
    edge_arc(board, (x1 - radius, y0), (x1, y), (x1 - radius, y1))
    edge_line(board, (x1 - radius, y1), (x0 + radius, y1))
    edge_arc(board, (x0 + radius, y1), (x0, y), (x0 + radius, y0))


def thermal_slot_items(board) -> list:
    return [
        item for item in board.Drawings()
        if item.GetLayer() == pcbnew.Edge_Cuts
        and 133.2 <= min(absolute_xy(item.GetStart())[1],
                         absolute_xy(item.GetEnd())[1])
        and max(absolute_xy(item.GetStart())[1],
                absolute_xy(item.GetEnd())[1]) <= 134.8
    ]


def replace_thermal_slots(board) -> None:
    slots = thermal_slot_items(board)
    if len(slots) not in (0, 8):
        raise SystemExit(f"expected zero or eight thermal-slot primitives, found {len(slots)}")
    for item in slots:
        board.Delete(item)
    for slot in THERMAL_SLOTS:
        add_horizontal_slot(board, *slot)


def _polygon(points) -> pcbnew.SHAPE_LINE_CHAIN:
    outline = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        outline.Append(point(x, y))
    outline.SetClosed(True)
    return outline


def _one_named_zone(board, name: str):
    matches = [zone for zone in board.Zones() if zone.GetZoneName() == name]
    if len(matches) > 1:
        raise SystemExit(f"found {len(matches)} zones named {name}")
    if matches:
        return matches[0]
    zone = pcbnew.ZONE(board)
    board.Add(zone)
    return zone


def ensure_thermal_gap(board):
    """Keep pours off every copper layer across the complete slot centreline."""
    zone = _one_named_zone(board, THERMAL_GAP_NAME)
    zone.SetZoneName(THERMAL_GAP_NAME)
    zone.SetIsRuleArea(True)
    layers = pcbnew.LSET()
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        layers.AddLayer(layer)
    zone.SetLayerSet(layers)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(True)
    zone.SetDoNotAllowFootprints(False)
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(_polygon(THERMAL_GAP))
    return zone


def ensure_heater_spreader(board):
    """Fill the gas-side B.Cu island with switched-low thermal-spreader copper."""
    net = board.FindNet("/HEATER_LOW")
    if net is None:
        raise SystemExit("/HEATER_LOW net is missing")
    zone = _one_named_zone(board, HEATER_SPREADER_NAME)
    zone.SetZoneName(HEATER_SPREADER_NAME)
    zone.SetIsRuleArea(False)
    zone.SetLayer(pcbnew.B_Cu)
    zone.SetNet(net)
    zone.SetLocalClearance(pcbnew.FromMM(0.15))
    zone.SetMinThickness(pcbnew.FromMM(0.09))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(False)
    zone.SetDoNotAllowFootprints(False)
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(_polygon(HEATER_SPREADER))
    return zone


def ensure_gnd_bridge(board):
    """Retain ground continuity with one narrow explicit trace, not plane fill."""
    old = {
        frozenset((absolute_xy(point(0.5, 83.0)), absolute_xy(point(0.5, 85.0))))
    }
    wanted_segments = tuple(zip(GND_BRIDGE, GND_BRIDGE[1:]))
    wanted = {frozenset((absolute_xy(point(*start)), absolute_xy(point(*end))))
              for start, end in wanted_segments}
    candidates = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/GND"
        and item.GetLayer() == pcbnew.In2_Cu
        and frozenset((absolute_xy(item.GetStart()), absolute_xy(item.GetEnd())))
        in old | wanted
    ]
    actual = {
        frozenset((absolute_xy(item.GetStart()), absolute_xy(item.GetEnd())))
        for item in candidates
    }
    if actual == old:
        for item in candidates:
            board.Delete(item)
        candidates = []
    elif actual != wanted:
        raise SystemExit(f"ambiguous thermal-barrier GND bridge: {sorted(map(sorted, actual))}")
    if not candidates:
        candidates = []
        for start, end in wanted_segments:
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(board.FindNet("/GND"))
            track.SetLayer(pcbnew.In2_Cu)
            track.SetStart(point(*start))
            track.SetEnd(point(*end))
            board.Add(track)
            candidates.append(track)
    for track in candidates:
        track.SetWidth(pcbnew.FromMM(0.15))
    return candidates


def save_board_preserving_project(board, output: Path) -> None:
    """Save a board without allowing pcbnew to rewrite its adjacent project."""
    project = output.with_suffix(".kicad_pro")
    existed = project.exists()
    previous = project.read_bytes() if existed else None
    try:
        pcbnew.SaveBoard(str(output), board)
    finally:
        if existed:
            project.write_bytes(previous)
        elif project.exists():
            project.unlink()
