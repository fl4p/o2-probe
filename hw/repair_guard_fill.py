#!/usr/bin/env python3
"""Stitch the saved F.Cu driven-guard rails into the guard source.

The narrow CELL_RE enclosure is split into several legal F.Cu fill regions by
the protected cell trace, the all-layer thermal pour gap, and nearby routed
signals. KiCad removes regions which are not physically connected, so the
source polygon alone is not proof that a driven guard will reach the sensor.
This deterministic migration owns four through vias and six short In1/B.Cu
links. The resulting saved fill has connected rails on both sides of the long
CELL_RE run while the y=133--135 mm plane gap remains empty.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    if "pcbnew" not in sys.modules:
        import wx

        _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import save_board_preserving_project

HERE = Path(__file__).resolve().parent
BOARD = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", BOARD))
NET = "/GUARD_REPLICA"

STITCH_VIAS = {
    (106.95, 136.00),
    (108.80, 136.00),
    (109.45, 139.00),
    (111.00, 135.50),
}

STITCH_TRACKS = {
    ("In1.Cu", (106.60, 132.60), (106.95, 132.95)),
    ("In1.Cu", (106.95, 132.95), (106.95, 136.00)),
    ("B.Cu", (106.95, 136.00), (109.45, 139.00)),
    ("B.Cu", (106.95, 136.00), (108.80, 136.00)),
    ("In1.Cu", (108.80, 136.00), (110.65, 136.00)),
    ("In1.Cu", (110.65, 136.00), (111.00, 135.50)),
}

OBSOLETE_VIA = (111.50, 133.60)
OBSOLETE_TRACK = ("In1.Cu", (110.65, 136.00), (111.50, 133.60))

EXPECTED_FILLED_RAILS = {
    (108.974715, 135.000000, 110.393458, 140.878865, 59),
    (110.323477, 135.000000, 111.604500, 141.650000, 63),
    (109.220228, 131.971835, 110.405022, 132.974500, 37),
}


def point_tuple(point) -> tuple[float, float]:
    return round(pcbnew.ToMM(point.x), 2), round(pcbnew.ToMM(point.y), 2)


def add_via(board, net, position: tuple[float, float]) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetNet(net)
    via.SetPosition(pcbnew.VECTOR2I_MM(*position))
    via.SetWidth(pcbnew.FromMM(0.25))
    via.SetDrill(pcbnew.FromMM(0.15))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)


def add_track(board, net, layer_name: str,
              start: tuple[float, float], end: tuple[float, float]) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(net)
    track.SetLayer(board.GetLayerID(layer_name))
    track.SetStart(pcbnew.VECTOR2I_MM(*start))
    track.SetEnd(pcbnew.VECTOR2I_MM(*end))
    track.SetWidth(pcbnew.FromMM(0.15))
    board.Add(track)


def filled_signatures(zone) -> set[tuple[float, float, float, float, int]]:
    polyset = zone.GetFilledPolysList(pcbnew.F_Cu)
    signatures = set()
    for index in range(polyset.OutlineCount()):
        outline = polyset.COutline(index)
        bbox = outline.BBox()
        signatures.add(tuple(round(pcbnew.ToMM(value), 6) for value in (
            bbox.GetLeft(), bbox.GetTop(), bbox.GetRight(), bbox.GetBottom()
        )) + (outline.PointCount(),))
    return signatures


def main() -> int:
    board = pcbnew.LoadBoard(str(BOARD))
    net = board.FindNet(NET)
    if net is None:
        raise SystemExit(f"missing {NET}")

    # The all-layer pour gap made the former y=133.6 stitch via F.Cu-dangling.
    # Remove that exact obsolete link rather than accepting the warning or
    # carrying unnecessary copper through the thermal barrier.
    obsolete_track_key = (OBSOLETE_TRACK[0],
                          *sorted((OBSOLETE_TRACK[1], OBSOLETE_TRACK[2])))
    for item in list(board.GetTracks()):
        if item.GetNetname() != NET:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            if point_tuple(item.GetPosition()) == OBSOLETE_VIA:
                board.Delete(item)
            continue
        item_key = (item.GetLayerName(),
                    *sorted((point_tuple(item.GetStart()), point_tuple(item.GetEnd()))))
        if item_key == obsolete_track_key:
            board.Delete(item)

    actual_vias = {
        point_tuple(item.GetPosition())
        for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == NET
        and pcbnew.ToMM(item.GetPosition().y) >= 133.5
    }
    if actual_vias not in (set(), STITCH_VIAS):
        raise SystemExit(f"unexpected partial guard-stitch vias: {sorted(actual_vias)}")
    if not actual_vias:
        for position in sorted(STITCH_VIAS):
            add_via(board, net, position)

    actual_tracks = {
        (item.GetLayerName(), *sorted((point_tuple(item.GetStart()),
                                      point_tuple(item.GetEnd()))))
        for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == NET
        and min(pcbnew.ToMM(item.GetStart().y), pcbnew.ToMM(item.GetEnd().y)) >= 132.6
        and frozenset((point_tuple(item.GetStart()), point_tuple(item.GetEnd())))
        != frozenset(((106.60, 132.60), (109.55, 132.80)))
    }
    expected_tracks = {
        (layer_name, *sorted((start, end)))
        for layer_name, start, end in STITCH_TRACKS
    }
    if actual_tracks not in (set(), expected_tracks):
        raise SystemExit(f"unexpected partial guard-stitch tracks: {sorted(actual_tracks)}")
    if not actual_tracks:
        for layer_name, start, end in sorted(STITCH_TRACKS):
            add_track(board, net, layer_name, start, end)

    zones = [zone for zone in board.Zones()
             if zone.GetNetname() == NET and zone.IsOnLayer(pcbnew.F_Cu)]
    if len(zones) != 1:
        raise SystemExit(f"found {len(zones)} F.Cu guard zones, want one")
    zone = zones[0]
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    actual_fill = filled_signatures(zone)
    if actual_fill != EXPECTED_FILLED_RAILS:
        raise SystemExit(
            f"guard fill differs after stitching: added={sorted(actual_fill - EXPECTED_FILLED_RAILS)}; "
            f"missing={sorted(EXPECTED_FILLED_RAILS - actual_fill)}"
        )

    save_board_preserving_project(board, OUT)
    print(f"wrote {OUT}: four guard vias, six links; three connected F.Cu guard regions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
