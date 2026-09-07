#!/usr/bin/env python3
"""Adopt the saved U10/C23 tip compaction and SGX aperture shift.

The migration accepts the released layout or the intermediate interactive
draft, then emits one exact placement/routing state.  The SGX 3 x 6 mm NPTH
keeps its size and moves 0.70 mm toward pad 2, leaving 0.50 mm from the pad's
gas-side copper edge to the slot's nearest edge.
"""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import save_board_preserving_project


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))


def xy(position) -> tuple[float, float]:
    return round(pcbnew.ToMM(position.x), 6), round(pcbnew.ToMM(position.y), 6)


def point(position: tuple[float, float]):
    return pcbnew.VECTOR2I(pcbnew.FromMM(position[0]), pcbnew.FromMM(position[1]))


def route_key(start, end):
    return frozenset(
        tuple(round(value, 4) for value in position)
        for position in (start, end)
    )


def item_key(item):
    return route_key(xy(item.GetStart()), xy(item.GetEnd()))


def add_track(board, netname: str, layer: int, width: float, start, end) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(board.FindNet(netname))
    track.SetLayer(layer)
    track.SetStart(point(start))
    track.SetEnd(point(end))
    track.SetWidth(pcbnew.FromMM(width))
    board.Add(track)


def replace_routes(board, netname: str, layer: int, width: float,
                   variants, final) -> None:
    known = {route_key(*segment) for variant in variants for segment in variant}
    wanted = Counter(route_key(*segment) for segment in final)
    candidates = [
        item for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and item.GetLayer() == layer
        and item_key(item) in known
    ]
    actual = Counter(item_key(item) for item in candidates)
    allowed = [Counter(route_key(*segment) for segment in variant)
               for variant in variants]
    if actual == wanted:
        for item in candidates:
            item.SetWidth(pcbnew.FromMM(width))
        return
    if actual not in allowed:
        raise SystemExit(
            f"ambiguous {netname} {board.GetLayerName(layer)} tip routes: "
            f"found {sorted((sorted(key), count) for key, count in actual.items())}"
        )
    for item in candidates:
        board.Delete(item)
    for start, end in final:
        add_track(board, netname, layer, width, start, end)


def move_footprint(footprints, reference: str, old, final) -> None:
    footprint = footprints[reference]
    actual = xy(footprint.GetPosition())
    if actual not in (old, final):
        raise SystemExit(f"{reference} at {actual}, want {old} or {final}")
    footprint.SetPosition(point(final))


def move_sensor_aperture(footprints) -> None:
    sensor = footprints["U11"]
    apertures = [
        pad for pad in sensor.Pads()
        if not pad.GetNumber() and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
    ]
    if len(apertures) != 1:
        raise SystemExit(f"U11 has {len(apertures)} NPTH apertures, want one")
    aperture = apertures[0]
    actual = xy(aperture.GetPosition())
    if actual not in ((110.0, 146.0), (110.0, 145.3)):
        raise SystemExit(f"U11 aperture at {actual}, want (110,146) or (110,145.3)")
    if xy(aperture.GetDrillSize()) != (3.0, 6.0):
        raise SystemExit(f"U11 aperture drill is {xy(aperture.GetDrillSize())}, want (3,6)")
    aperture.SetPosition(point((110.0, 145.3)))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    footprints = {footprint.GetReference(): footprint for footprint in board.Footprints()}
    for reference in ("U10", "C23", "U11"):
        if reference not in footprints:
            raise SystemExit(f"missing {reference}")

    move_footprint(footprints, "U10", (110.0, 152.0), (110.0, 152.525))
    move_footprint(footprints, "C23", (114.0, 150.0), (114.0, 151.0))
    move_sensor_aperture(footprints)

    # The old 12 V heater feed passed 0.50 mm above the old slot edge.  Moving
    # the slot 0.70 mm toward the pads makes that route intersect the hole, so
    # detour it 0.50 mm beyond the gas-side end.  On In1 this remains clear of
    # the B.Cu heater lands and the I2C corridor below it.
    replace_routes(board, "/+12V_SW", pcbnew.In1_Cu, 0.40, (
        (((117.65, 144.3), (117.65, 142.5)),
         ((117.65, 142.5), (105.0, 142.5))),
        (((117.65, 144.3), (117.65, 148.8)),
         ((117.65, 148.8), (105.0, 148.8)),
         ((105.0, 148.8), (105.0, 142.5))),
    ), (
        ((117.65, 144.3), (117.65, 148.8)),
        ((117.65, 148.8), (105.0, 148.8)),
        ((105.0, 148.8), (105.0, 142.5)),
    ))

    # U10 top row: exit away from the exposed pad instead of retaining the
    # interactive draft's vertical extensions to the old pad coordinates.
    replace_routes(board, "/I2C_SCL", pcbnew.F_Cu, 0.09, (
        (((110.65, 151.025), (110.4, 150.4)),),
        (((110.65, 151.55), (110.4, 150.4)),),
    ), (((110.65, 151.55), (110.4, 150.4)),))
    replace_routes(board, "/GND", pcbnew.F_Cu, 0.20, (
        (((110.0, 151.025), (109.8, 150.7)),),
        (((110.0, 151.025), (109.8, 150.7)),
         ((110.0, 151.025), (110.0, 151.55))),
        (((110.0, 151.55), (109.8, 150.7)),),
    ), (((110.0, 151.55), (109.8, 150.7)),))
    replace_routes(board, "/HEATER_GATE", pcbnew.F_Cu, 0.18, (
        (((109.35, 151.025), (108.3, 150.3)),),
        (((109.35, 151.025), (108.3, 150.3)),
         ((109.35, 151.025), (109.35, 151.55))),
        (((109.35, 151.55), (108.3, 150.3)),),
    ), (((109.35, 151.55), (108.3, 150.3)),))

    # U10 bottom row: move the old routes wholly below the exposed-pad land.
    replace_routes(board, "/3V3D", pcbnew.F_Cu, 0.15, (
        (((109.35, 153.9), (109.35, 152.975)),
         ((109.35, 152.975), (110.0, 152.975))),
        (((109.35, 153.9), (109.35, 153.5)),
         ((109.35, 153.5), (110.0, 153.5))),
    ), (
        ((109.35, 153.9), (109.35, 153.5)),
        ((109.35, 153.5), (110.0, 153.5)),
    ))
    replace_routes(board, "/I2C_SDA", pcbnew.F_Cu, 0.09, (
        (((111.85, 152.3), (111.175, 152.975)),
         ((111.175, 152.975), (110.65, 152.975))),
        (((112.0, 153.5), (110.65, 153.5)),),
    ), (((112.0, 153.5), (110.65, 153.5)),))
    replace_routes(board, "/TMP_CELL_EP", pcbnew.F_Cu, 0.18, (
        (((110.0, 152.0), (109.0, 152.0)),
         ((109.0, 152.0), (108.3, 153.0))),
        (((110.0, 152.525), (108.739706, 152.525)),
         ((108.739706, 152.525), (108.382353, 152.882353)),
         ((108.382353, 152.882353), (108.3, 153.0))),
    ), (
        ((110.0, 152.525), (108.739706, 152.525)),
        ((108.739706, 152.525), (108.382353, 152.882353)),
        ((108.382353, 152.882353), (108.3, 153.0)),
    ))

    # C23 joins the existing C21 ground junction.  Remove the 1 nm shove stub
    # emitted by the interactive router and save one intentional segment.
    replace_routes(board, "/GND", pcbnew.F_Cu, 0.18, (
        (((113.52, 150.0), (113.0, 150.5)),
         ((113.0, 150.5), (113.0, 151.25))),
        (((113.52, 151.0), (113.000001, 151.519999)),
         ((113.000001, 151.519999), (113.0, 151.519999))),
        (((113.52, 151.0), (113.0, 151.52)),),
    ), (((113.52, 151.0), (113.0, 151.52)),))

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(
        f"wrote {OUT}: U10/C23 compacted, U10 rerouted, "
        "SGX slot edge 0.50 mm from pad-2 copper"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
