#!/usr/bin/env python3
"""Route the narrow explicit crossings through the widened thermal barrier."""

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

from thermal_design import (ensure_gnd_bridge, ensure_heater_spreader,
                            ensure_thermal_gap, replace_thermal_slots,
                            save_board_preserving_project)


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))


def point(value: tuple[float, float]):
    return pcbnew.VECTOR2I_MM(*value)


def endpoint_key(start, end):
    return frozenset(((round(pcbnew.ToMM(start.x), 4), round(pcbnew.ToMM(start.y), 4)),
                      (round(pcbnew.ToMM(end.x), 4), round(pcbnew.ToMM(end.y), 4))))


def route_key(start, end):
    return frozenset((start, end))


def add_track(board, netname: str, layer: int, width: float, start, end) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(board.FindNet(netname))
    track.SetLayer(layer)
    track.SetStart(point(start))
    track.SetEnd(point(end))
    track.SetWidth(pcbnew.FromMM(width))
    board.Add(track)


def replace_path(board, netname: str, layer: int, width: float,
                 old_segments, new_segments) -> None:
    old = {route_key(*segment) for segment in old_segments}
    new = {route_key(*segment) for segment in new_segments}
    candidates = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and item.GetLayer() == layer
        and endpoint_key(item.GetStart(), item.GetEnd()) in old | new
    ]
    actual = {endpoint_key(item.GetStart(), item.GetEnd()) for item in candidates}
    if actual == new:
        for item in candidates:
            item.SetWidth(pcbnew.FromMM(width))
        return
    if actual != old:
        raise SystemExit(
            f"ambiguous {netname} {board.GetLayerName(layer)} thermal crossing: "
            f"found {sorted(map(sorted, actual))}"
        )
    for item in candidates:
        board.Delete(item)
    for start, end in new_segments:
        add_track(board, netname, layer, width, start, end)


def ensure_via(board, netname: str, position: tuple[float, float],
               diameter=0.25, drill=0.15) -> None:
    matches = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and (round(pcbnew.ToMM(item.GetPosition().x), 4),
             round(pcbnew.ToMM(item.GetPosition().y), 4)) == position
    ]
    if len(matches) > 1:
        raise SystemExit(f"multiple {netname} vias at {position}")
    if matches:
        via = matches[0]
    else:
        via = pcbnew.PCB_VIA(board)
        via.SetNet(board.FindNet(netname))
        via.SetPosition(point(position))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
    via.SetWidth(pcbnew.FromMM(diameter))
    via.SetDrill(pcbnew.FromMM(drill))


def remove_exact_via(board, netname: str, position: tuple[float, float]) -> None:
    matches = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and (round(pcbnew.ToMM(item.GetPosition().x), 4),
             round(pcbnew.ToMM(item.GetPosition().y), 4)) == position
    ]
    if len(matches) > 1:
        raise SystemExit(f"multiple obsolete {netname} vias at {position}")
    for item in matches:
        board.Delete(item)


def apply(board) -> None:
    # Widening the slots in Y moves their top edge toward an existing VA_MON
    # run.  Cross the centre neck below the slot, return above it at x=112.8,
    # and keep the long horizontal section north of the all-layer pour gap.
    replace_path(board, "/VA_MON", pcbnew.B_Cu, 0.18,
                 (((110.3, 134.05), (111.2, 133.15)),
                  ((111.2, 133.15), (116.45, 133.15)),
                  ((116.45, 133.15), (118.65, 130.95))),
                 (((110.3, 134.05), (110.3, 136.0)),
                  ((110.3, 136.0), (112.8, 136.0)),
                  ((112.8, 136.0), (112.8, 132.85)),
                  ((112.8, 132.85), (116.45, 132.85)),
                  ((116.45, 132.85), (118.65, 130.95))))

    # Open a legal corridor for the new right-hand guard stitch, then return
    # SDA to its original sensor-side x coordinate before U11's pad field.
    replace_path(board, "/I2C_SDA", pcbnew.F_Cu, 0.09,
                 (((112.75, 133.05), (111.25, 134.55)),
                  ((111.25, 134.55), (111.25, 141.45))),
                 (((112.75, 133.05), (111.8, 134.55)),
                  ((111.8, 134.55), (111.8, 139.5)),
                  ((111.8, 139.5), (111.25, 140.0)),
                  ((111.25, 140.0), (111.25, 141.45))))

    ensure_via(board, "/GUARD_REPLICA", (111.0, 135.5))
    replace_path(board, "/GUARD_REPLICA", pcbnew.In1_Cu, 0.15, (),
                 (((110.65, 136.0), (111.0, 135.5)),))

    # The previous guard stitch landed inside the new pour gap, where its F.Cu
    # rail is intentionally absent. Remove that now-dangling via and its link;
    # the northern guard region is already connected at the source side.
    replace_path(board, "/GUARD_REPLICA", pcbnew.In1_Cu, 0.15,
                 (((110.65, 136.0), (111.5, 133.6)),), ())
    remove_exact_via(board, "/GUARD_REPLICA", (111.5, 133.6))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    replace_thermal_slots(board)
    ensure_thermal_gap(board)
    ensure_heater_spreader(board)
    ensure_gnd_bridge(board)
    apply(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(f"wrote {OUT}: widened slots and minimal explicit thermal-barrier crossings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
