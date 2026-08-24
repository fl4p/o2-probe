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
    return pcbnew.VECTOR2I(pcbnew.FromMM(value[0]), pcbnew.FromMM(value[1]))


def endpoint_key(start, end):
    return frozenset(((round(pcbnew.ToMM(start.x), 4), round(pcbnew.ToMM(start.y), 4)),
                      (round(pcbnew.ToMM(end.x), 4), round(pcbnew.ToMM(end.y), 4))))


def route_key(start, end):
    return frozenset(tuple(round(value, 4) for value in point_) for point_ in (start, end))


def path_present(board, netname: str, layer: int, segments) -> bool:
    wanted = {route_key(*segment) for segment in segments}
    actual = {
        endpoint_key(item.GetStart(), item.GetEnd())
        for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and item.GetLayer() == layer
        and endpoint_key(item.GetStart(), item.GetEnd()) in wanted
    }
    return actual == wanted


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


def replace_via(board, netname: str, old_position: tuple[float, float],
                new_position: tuple[float, float], diameter=0.25, drill=0.15) -> None:
    positions = {
        (round(pcbnew.ToMM(item.GetPosition().x), 4),
         round(pcbnew.ToMM(item.GetPosition().y), 4)): item
        for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA) and item.GetNetname() == netname
        and (round(pcbnew.ToMM(item.GetPosition().x), 4),
             round(pcbnew.ToMM(item.GetPosition().y), 4)) in (old_position, new_position)
    }
    if set(positions) == {old_position}:
        board.Delete(positions[old_position])
        ensure_via(board, netname, new_position, diameter, drill)
    elif set(positions) == {new_position}:
        ensure_via(board, netname, new_position, diameter, drill)
    else:
        raise SystemExit(f"ambiguous {netname} via move: found {sorted(positions)}")


def apply(board) -> None:
    intermediate_va = (
        ((110.3, 134.05), (110.3, 136.0)),
        ((110.3, 136.0), (112.8, 136.0)),
        ((112.8, 136.0), (112.8, 132.85)),
        ((112.8, 132.85), (116.45, 132.85)),
        ((116.45, 132.85), (118.65, 130.95)),
    )
    expanded_va = (
        ((110.3, 134.05), (110.3, 136.0)),
        ((110.3, 136.0), (112.0, 136.0)),
        ((112.0, 136.0), (112.0, 132.90305)),
        ((112.0, 132.90305), (112.05305, 132.85)),
        ((112.05305, 132.85), (116.45, 132.85)),
        ((116.45, 132.85), (118.65, 130.95)),
    )
    if not path_present(board, "/VA_MON", pcbnew.B_Cu, expanded_va):
        # Normalize pre-barrier boards before applying the user-expanded slot
        # corridor below.
        replace_path(board, "/VA_MON", pcbnew.B_Cu, 0.18,
                     (((110.3, 134.05), (111.2, 133.15)),
                      ((111.2, 133.15), (116.45, 133.15)),
                      ((116.45, 133.15), (118.65, 130.95))),
                     intermediate_va)

    intermediate_sda = (
        ((112.75, 133.05), (111.8, 134.55)),
        ((111.8, 134.55), (111.8, 139.5)),
        ((111.8, 139.5), (111.25, 140.0)),
        ((111.25, 140.0), (111.25, 141.45)),
    )
    expanded_sda_changed = (
        ((112.75, 127.9), (112.75, 132.25)),
        ((112.75, 132.25), (111.5, 133.5)),
        ((111.5, 133.5), (111.5, 135.0)),
        ((111.5, 135.0), (111.8, 135.3)),
        ((111.8, 135.3), (111.8, 139.5)),
        ((111.85, 142.05), (111.85, 152.3)),
    )
    if not path_present(board, "/I2C_SDA", pcbnew.F_Cu, expanded_sda_changed):
        replace_path(board, "/I2C_SDA", pcbnew.F_Cu, 0.09,
                     (((112.75, 133.05), (111.25, 134.55)),
                      ((111.25, 134.55), (111.25, 141.45))),
                     intermediate_sda)

    ensure_via(board, "/GUARD_REPLICA", (111.0, 135.5))
    replace_path(board, "/GUARD_REPLICA", pcbnew.In1_Cu, 0.15, (),
                 (((110.65, 136.0), (111.0, 135.5)),))

    # The previous guard stitch landed inside the new pour gap, where its F.Cu
    # rail is intentionally absent. Remove that now-dangling via and its link;
    # the northern guard region is already connected at the source side.
    replace_path(board, "/GUARD_REPLICA", pcbnew.In1_Cu, 0.15,
                 (((110.65, 136.0), (111.5, 133.6)),), ())
    remove_exact_via(board, "/GUARD_REPLICA", (111.5, 133.6))

    # The user-expanded 6.75 mm slots reduce the centre neck to 5.0 mm and the
    # edge webs to 0.75 mm. Adopt KiCad's shove-routed solution exactly.
    replace_path(board, "/+12V_SW", pcbnew.B_Cu, 0.18,
                 (((106.5, 132.7), (107.15, 132.7)),
                  ((107.15, 132.7), (108.05, 133.6)),
                  ((108.05, 133.6), (109.9, 133.6))),
                 (((106.5, 132.7), (107.7, 132.7)),
                  ((107.7, 132.7), (108.6, 133.6)),
                  ((108.6, 133.6), (109.9, 133.6))))

    replace_path(board, "/3V3D", pcbnew.F_Cu, 0.15,
                 (((114.6, 139.25), (119.3, 134.55)),
                  ((119.3, 134.5), (119.3, 134.55)),
                  ((119.3, 134.5), (119.35, 134.45)),
                  ((119.35, 131.55), (119.35, 134.45))),
                 (((114.6, 139.25), (118.35, 135.5)),
                  ((118.35, 135.5), (118.5, 135.5)),
                  ((118.5, 135.5), (119.101292, 134.898708)),
                  ((119.101292, 134.898708), (119.184673, 134.858554)),
                  ((119.184673, 134.858554), (119.5, 134.543227)),
                  ((119.35, 131.55), (119.35, 132.85)),
                  ((119.35, 132.85), (119.5, 133.0)),
                  ((119.5, 133.0), (119.5, 133.57006)),
                  ((119.5, 133.57006), (119.725, 133.79506)),
                  ((119.5, 134.42994), (119.5, 134.543227)),
                  ((119.5, 134.42994), (119.725, 134.20494)),
                  ((119.725, 133.79506), (119.725, 134.20494))))

    replace_path(board, "/CELL_CE", pcbnew.F_Cu, 0.15,
                 (((101.5, 129.95), (102.95, 131.4)),
                  ((102.95, 131.4), (107.3, 131.4)),
                  ((107.3, 131.4), (108.25, 132.35))),
                 (((101.5, 129.95), (102.55, 131.0)),
                  ((102.55, 131.0), (106.9, 131.0)),
                  ((106.9, 131.0), (108.25, 132.35))))

    replace_path(board, "/CELL_WE", pcbnew.F_Cu, 0.15,
                 (((106.7, 132.25), (109.55, 135.1)),),
                 (((106.9, 132.165), (106.9, 132.45)),
                  ((106.9, 132.45), (109.55, 135.1))))
    replace_path(board, "/CELL_WE", pcbnew.In1_Cu, 0.15,
                 (((106.7, 132.25), (106.8, 132.25)),
                  ((106.8, 132.25), (108.2, 130.85))),
                 (((106.9, 132.15), (106.9, 132.165)),
                  ((106.9, 132.15), (108.2, 130.85))))
    replace_via(board, "/CELL_WE", (106.7, 132.25), (106.9, 132.165))

    replace_path(board, "/GUARD_REPLICA", pcbnew.In1_Cu, 0.15,
                 (((106.6, 132.6), (106.95, 132.95)),
                  ((106.95, 132.95), (106.95, 136.0))),
                 (((106.6, 132.6), (107.438983, 132.6)),
                  ((107.438983, 132.6), (108.0, 133.161017)),
                  ((108.0, 133.161017), (108.0, 134.525736)),
                  ((108.0, 134.525736), (107.15, 135.375736)),
                  ((107.15, 135.375736), (107.15, 135.8)),
                  ((107.15, 135.8), (106.95, 136.0))))

    replace_path(board, "/HEATER_PWM", pcbnew.F_Cu, 0.18,
                 (((112.75, 133.65), (112.75, 134.35)),
                  ((112.75, 133.65), (112.8, 133.6)),
                  ((112.75, 134.35), (112.8, 134.4)),
                  ((112.8, 133.55), (112.8, 133.6)),
                  ((112.8, 133.55), (112.85, 133.5)),
                  ((112.8, 134.4), (112.8, 134.45)),
                  ((112.8, 134.45), (112.85, 134.5)),
                  ((112.85, 133.45), (112.85, 133.5)),
                  ((112.85, 133.45), (114.2, 132.1)),
                  ((112.85, 134.5), (112.85, 134.55)),
                  ((112.85, 134.55), (112.9, 134.6)),
                  ((112.9, 134.6), (112.9, 134.65)),
                  ((112.9, 134.65), (113.85, 135.6)),
                  ((113.85, 135.6), (113.85, 136.5))),
                 (((112.0, 133.5), (112.0, 135.0)),
                  ((112.0, 133.5), (113.4, 132.1)),
                  ((112.0, 135.0), (113.5, 136.5)),
                  ((113.4, 132.1), (114.2, 132.1)),
                  ((113.5, 136.5), (113.85, 136.5))))

    replace_path(board, "/I2C_SCL", pcbnew.B_Cu, 0.09,
                 (((102.4, 127.55), (102.4, 129.1)),
                  ((102.4, 129.1), (110.65, 137.35)),
                  ((110.65, 137.35), (110.65, 140.2))),
                 (((102.4, 127.55), (102.4, 127.9)),
                  ((102.4, 127.9), (103.165, 128.665)),
                  ((103.165, 128.665), (103.165, 129.76805)),
                  ((103.165, 129.76805), (106.38195, 132.985)),
                  ((106.38195, 132.985), (107.485, 132.985)),
                  ((107.485, 132.985), (109.615, 135.115)),
                  ((109.615, 135.115), (109.615, 136.26805)),
                  ((109.615, 136.26805), (110.65, 137.30305)),
                  ((110.65, 137.30305), (110.65, 140.2))))

    replace_path(board, "/I2C_SDA", pcbnew.F_Cu, 0.09,
                 (((111.8, 134.55), (111.8, 139.5)),
                  ((111.8, 134.55), (112.75, 133.05)),
                  ((111.85, 142.05), (111.85, 151.65)),
                  ((111.85, 151.65), (111.85, 152.3)),
                  ((112.75, 127.9), (112.75, 133.05))),
                 expanded_sda_changed)

    replace_path(board, "/VA_MON", pcbnew.B_Cu, 0.18,
                 (((110.3, 136.0), (112.8, 136.0)),
                  ((112.8, 132.85), (112.8, 136.0)),
                  ((112.8, 132.85), (116.45, 132.85))),
                 (((110.3, 136.0), (112.0, 136.0)),
                  ((112.0, 132.90305), (112.0, 136.0)),
                  ((112.0, 132.90305), (112.05305, 132.85)),
                  ((112.05305, 132.85), (116.45, 132.85))))
    replace_path(board, "/VA_MON", pcbnew.In1_Cu, 0.18,
                 (((105.15, 130.2), (106.75, 131.8)),),
                 (((105.15, 130.2), (106.4625, 131.5125)),))
    replace_path(board, "/VA_MON", pcbnew.F_Cu, 0.18, (),
                 (((106.4625, 131.5125), (106.75, 131.8)),))
    replace_via(board, "/VA_MON", (106.75, 131.8), (106.4625, 131.5125))


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
