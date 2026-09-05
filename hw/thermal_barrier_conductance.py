#!/usr/bin/env python3
"""Re-derive the thermal barrier's routed-copper conductance from the board.

`THERMAL-BARRIER.md` quoted 8.7--9.2 mW/K for the copper crossing the y=133..135
transverse strip.  That number was computed by hand against Rev A: 14 segments
on four layers, two of them 0.5 oz inner copper.  It cannot be scaled to a
different route or a different stackup -- going to two layers makes every
crossing thicker AND adds crossings, because the same nets have fewer layers to
cross on -- so it has to be recomputed, and recomputing it by hand again would
just produce another number that goes stale the next time anyone routes.

This derives it from the board file instead: every track clipped to the strip,
every via through it, at the copper thickness the board's own stackup declares.

Model: first-order steady-state conduction.  Each crossing net contributes one
parallel path PER LAYER across the full 2 mm strip,

    G = k_cu * width * thickness / 2 mm

taking that net's NARROWEST track in the strip as the width, because the
narrowest point is what limits a series path.  k_cu = 385..400 W/(m*K).  It is
not a 2-D or 3-D field solution and does not claim to be.

Vias inside the strip are COUNTED AND REPORTED BUT NOT SUMMED.  A via barrel
conducts through the board thickness, in z; the barrier is a gap in y.  A via
at y=83.4 does not carry heat from y<83 to y>85, it only ties the two layers
together at a point that is already inside the gap.  Adding barrels as parallel
crossings put 11 mW/K on the board per via and tripled the answer.

The first version summed every segment independently using the segment's own
clipped length, and was wrong by an order of magnitude -- 93 mW/K against Rev
A's hand-computed 8.7 for a comparable board.  A segment that merely clips the
edge of the strip got a length of 0.14 mm instead of 2 mm and so a conductance
23 mW/K on its own, when in reality it is in SERIES with the rest of its net's
path, not a parallel path of its own.  Treating each net as one path of the
strip's full height is the conservative reading of the same data.
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

HERE = Path(__file__).resolve().parent
BOARD = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))

STRIP_Y = (133.0, 135.0)        # absolute mm, the all-layer pour gap
K_CU = (385.0, 400.0)           # W/(m*K)
VIA_PLATING_UM = (15.0, 25.0)
BOARD_THICKNESS_MM = 1.0        # via barrel length


def mm(value) -> float:
    return pcbnew.ToMM(value)


def layer_thickness(text: str) -> dict:
    """Copper thickness per layer, read from the board's own stackup."""
    import re

    found = {}
    for match in re.finditer(
            r'\(layer "([^"]+)"\s*\(type "copper"\)\s*\(thickness ([0-9.]+)\)', text):
        found[match.group(1)] = float(match.group(2))
    if not found:
        raise SystemExit(
            f"{BOARD} declares no copper thicknesses; a board with no stackup "
            "cannot be given a conduction number")
    return found


def clip(y0: float, y1: float) -> float:
    """Length of a segment's y-extent inside the strip, in mm."""
    low, high = min(y0, y1), max(y0, y1)
    return max(0.0, min(high, STRIP_Y[1]) - max(low, STRIP_Y[0]))


def main() -> int:
    text = BOARD.read_text()
    thickness = layer_thickness(text)
    board = pcbnew.LoadBoard(str(BOARD))

    crossings = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            y = mm(item.GetPosition().y)
            if STRIP_Y[0] <= y <= STRIP_Y[1]:
                crossings.append(("via", item.GetNetname(), None,
                                  mm(item.GetWidth()), None))
            continue
        y0, y1 = mm(item.GetStart().y), mm(item.GetEnd().y)
        spanned = clip(y0, y1)
        if spanned <= 0.0:
            continue
        name = board.GetLayerName(item.GetLayer())
        if name not in thickness:
            raise SystemExit(f"track on {name}, which the stackup does not describe")
        # Path length through the barrier is the segment's own length scaled to
        # the part inside the strip, so a diagonal crossing is not counted as
        # if it went straight across.
        total = mm(item.GetLength())
        dy = abs(y1 - y0)
        length = spanned * (total / dy) if dy > 0 else total
        crossings.append(("track", item.GetNetname(), name,
                          mm(item.GetWidth()), length))

    tracks = [c for c in crossings if c[0] == "track"]
    vias = [c for c in crossings if c[0] == "via"]

    # One path per (net, layer): the narrowest track that net has in the strip.
    narrowest = {}
    for _, net, layer, width, _ in tracks:
        key = (net, layer)
        narrowest[key] = min(narrowest.get(key, width), width)

    def total(k_cu: float, plating_um: float) -> float:
        g = 0.0
        for (_, layer), width in narrowest.items():
            area = (width * 1e-3) * (thickness[layer] * 1e-3)
            g += k_cu * area / ((STRIP_Y[1] - STRIP_Y[0]) * 1e-3)
        return g

    low = total(K_CU[0], VIA_PLATING_UM[0])
    high = total(K_CU[1], VIA_PLATING_UM[1])

    print(f"board: {BOARD}")
    print(f"copper layers in stackup: "
          f"{', '.join(f'{k} {v} mm' for k, v in thickness.items())}")
    print(f"crossings: {len(tracks)} track segment(s) forming "
          f"{len(narrowest)} net-layer path(s), {len(vias)} via(s)")
    by_net = {}
    for kind, net, layer, width, length in crossings:
        by_net.setdefault(net or "(none)", []).append(kind)
    for net in sorted(by_net):
        kinds = by_net[net]
        print(f"  {net}: {kinds.count('track')} track(s), {kinds.count('via')} via(s)")
    print(f"routed-copper conductance: {low * 1e3:.1f}--{high * 1e3:.1f} mW/K"
          f"  ({len(vias)} via(s) inside the strip, counted but not summed --"
          " a barrel conducts in z, the barrier is a gap in y)")
    print(f"                    i.e.   {1.0 / high:.0f}--{1.0 / low:.0f} K/W "
          "for the copper path alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
