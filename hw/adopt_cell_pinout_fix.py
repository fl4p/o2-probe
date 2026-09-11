#!/usr/bin/env python3
"""Move the board copper onto the corrected SGX-OX-ROHS-Mini pin map.

``lib/o2-probe.pretty/SGX-OX-ROHS-Mini_ISS2.kicad_mod`` was corrected on
2026-09-01 after DS-0637 (Issue 2, and Issue 1 before it) was read as a
drawing rather than as prose: the physical pin order is Counter, Working,
Reference with Working in the CENTRE.  ``sync_footprints.py`` moves U11 pad 2
(RE) to x=+2.54 and pad 3 (WE) to the centre; this migration moves the copper
that used to reach the old pads, and re-tapers the driven guard onto the new
CELL_RE run.

Run once, after ``sync_footprints.py`` and before ``repair_guard_fill.py``:

    sync_footprints.py && adopt_cell_pinout_fix.py && repair_guard_fill.py

The guard fill itself is NOT written here.  ``repair_guard_fill.py`` owns it
and re-derives the three connected rails from the geometry this script leaves
behind.
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
OUT = Path(os.environ.get("O2_PCB_OUT", BOARD))

# The re-tapered driven guard.  The top edge is unchanged; the bottom edge
# follows CELL_RE east and clears the relocated WE land at (110.0, 141.0),
# whose 1.6 mm circular land plus 0.15 mm clearance reaches x=110.95.
GUARD_OUTLINE = ((109.25, 131.75), (112.15, 131.75),
                 (114.0, 141.65), (111.1, 141.65))


def point(value) -> tuple[float, float]:
    return round(pcbnew.ToMM(value.x), 4), round(pcbnew.ToMM(value.y), 4)


class Migration:
    def __init__(self, board) -> None:
        self.board = board

    def _vector(self, position):
        return pcbnew.VECTOR2I_MM(*position)

    def track(self, net, layer, start, end):
        layer_id = self.board.GetLayerID(layer)
        hits = [item for item in self.board.GetTracks()
                if not isinstance(item, pcbnew.PCB_VIA)
                and item.GetNetname() == net
                and item.GetLayer() == layer_id
                and {point(item.GetStart()), point(item.GetEnd())} == {start, end}]
        if len(hits) != 1:
            raise SystemExit(
                f"expected exactly one {net} {layer} segment {start}-{end}, "
                f"found {len(hits)}; the board is not the state this migration "
                "was written against")
        return hits[0]

    def via(self, net, position):
        hits = [item for item in self.board.GetTracks()
                if isinstance(item, pcbnew.PCB_VIA)
                and item.GetNetname() == net
                and point(item.GetPosition()) == position]
        if len(hits) != 1:
            raise SystemExit(f"expected exactly one {net} via at {position}, "
                             f"found {len(hits)}")
        return hits[0]

    def retarget(self, net, layer, start, end, new_start, new_end):
        item = self.track(net, layer, start, end)
        item.SetStart(self._vector(new_start))
        item.SetEnd(self._vector(new_end))

    def drop_track(self, net, layer, start, end):
        self.board.Delete(self.track(net, layer, start, end))

    def drop_via(self, net, position):
        self.board.Delete(self.via(net, position))

    def add_track(self, net, layer, width, start, end):
        item = pcbnew.PCB_TRACK(self.board)
        item.SetNet(self.board.FindNet(net))
        item.SetLayer(self.board.GetLayerID(layer))
        item.SetStart(self._vector(start))
        item.SetEnd(self._vector(end))
        item.SetWidth(pcbnew.FromMM(width))
        self.board.Add(item)

    def add_via(self, net, position, diameter=0.25, drill=0.15):
        item = pcbnew.PCB_VIA(self.board)
        item.SetNet(self.board.FindNet(net))
        item.SetPosition(self._vector(position))
        item.SetWidth(pcbnew.FromMM(diameter))
        item.SetDrill(pcbnew.FromMM(drill))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        self.board.Add(item)


def main() -> int:
    board = pcbnew.LoadBoard(str(BOARD))
    pads = {pad.GetNumber(): point(pad.GetPosition())
            for footprint in board.Footprints() if footprint.GetReference() == "U11"
            for pad in footprint.Pads() if pad.GetNumber()}
    if pads != {"1": (107.46, 141.0), "2": (112.54, 141.0), "3": (110.0, 141.0)}:
        raise SystemExit(
            f"U11 pads are at {pads}; run sync_footprints.py first so the board "
            "carries the corrected library footprint")

    edit = Migration(board)

    # CELL_RE: still exactly one F.Cu segment, now reaching the east pad.
    edit.retarget("/CELL_RE", "F.Cu", (111.0, 131.4), (110.0, 141.0),
                  (111.0, 131.4), (112.54, 141.0))

    # CELL_WE: the In1 tail lands on the centre pad and no longer runs beneath
    # CELL_RE, which is the coupling the guard exists to prevent.
    edit.retarget("/CELL_WE", "In1.Cu", (109.55, 138.0), (112.55, 141.0),
                  (109.55, 138.0), (110.0, 141.0))

    # CELL_CE already terminates on pad 1; nothing to do.

    # I2C_SDA leaves the guard corridor.  A straight CELL_RE run passes
    # x=111.63 at y=135.30 where the old F.Cu SDA sat at x=111.80, ~0.054 mm
    # edge to edge against a 0.15 mm rule, and the two actually cross at
    # y=134.4.  SDA is low-impedance digital, so it is the constraint that
    # moves: it now crosses the thermal barrier on In1 at x=112.15 and runs
    # down the east side, rejoining its original F.Cu descent at y=142.2.
    # The layer change cannot happen at the old (112.75, 132.25) corner: that
    # corner lies in a 0.707 mm corridor between the /VREF_TRIM B.Cu diagonal
    # and the /HEATER_PWM F.Cu diagonal, and a 0.25 mm through via needs
    # 0.715 mm of it.  It moves north-east to (113.55, 131.6), where the
    # nearest foreign copper is 0.285 mm away.
    edit.retarget("/I2C_SDA", "F.Cu", (112.75, 127.9), (112.75, 132.25),
                  (112.75, 127.9), (112.75, 130.8))
    edit.add_track("/I2C_SDA", "F.Cu", 0.09, (112.75, 130.8), (113.55, 131.6))
    for start, end in (((112.75, 132.25), (111.5, 133.5)),
                       ((111.5, 133.5), (111.5, 135.0)),
                       ((111.5, 135.0), (111.8, 135.3)),
                       ((111.8, 135.3), (111.8, 139.5)),
                       ((111.8, 139.5), (111.25, 140.0)),
                       ((111.25, 140.0), (111.25, 141.45)),
                       ((111.25, 141.45), (111.85, 142.05))):
        edit.drop_track("/I2C_SDA", "F.Cu", start, end)
    edit.retarget("/I2C_SDA", "F.Cu", (111.85, 142.05), (111.85, 152.3),
                  (111.85, 142.2), (111.85, 152.3))
    edit.add_via("/I2C_SDA", (113.55, 131.6))
    edit.add_via("/I2C_SDA", (111.85, 142.2))
    for start, end in (((113.55, 131.6), (112.15, 133.0)),
                       ((112.15, 133.0), (112.15, 135.6)),
                       ((112.15, 135.6), (114.1, 137.55)),
                       ((114.1, 137.55), (114.1, 142.2)),
                       ((114.1, 142.2), (111.85, 142.2))):
        edit.add_track("/I2C_SDA", "In1.Cu", 0.09, start, end)

    # The +12V_SW In1-to-B.Cu transition sat at (111.3, 132.3), which the new
    # CELL_RE run passes through -- KiCad reports it as a short, not a
    # clearance miss.  CELL_RE must stay one straight segment, so the via
    # slides 1.13 mm further along the same 45-degree line it already sits on;
    # the In1 and B.Cu legs keep their direction and the point where +12V_SW
    # crosses under CELL_RE is unchanged.
    edit.retarget("/+12V_SW", "In1.Cu", (110.75, 132.85), (111.3, 132.3),
                  (110.75, 132.85), (112.1, 131.5))
    edit.retarget("/+12V_SW", "B.Cu", (111.3, 132.3), (113.2, 130.4),
                  (112.1, 131.5), (113.2, 130.4))
    edit.drop_via("/+12V_SW", (111.3, 132.3))
    edit.add_via("/+12V_SW", (112.1, 131.5))

    # Guard stitch: the west spur landed on the old west rail, which the
    # re-tapered zone no longer covers.  The east rail is the one that now
    # needs a link, so the same four vias and ten links are re-aimed, not
    # added to.
    edit.drop_via("/GUARD_REPLICA", (109.45, 139.0))
    edit.drop_track("/GUARD_REPLICA", "B.Cu", (106.95, 136.0), (109.45, 139.0))
    edit.add_via("/GUARD_REPLICA", (112.65, 137.15))
    edit.add_track("/GUARD_REPLICA", "In1.Cu", 0.15,
                   (111.0, 135.5), (112.65, 137.15))

    zones = [zone for zone in board.Zones()
             if zone.GetNetname() == "/GUARD_REPLICA" and zone.IsOnLayer(pcbnew.F_Cu)]
    if len(zones) != 1:
        raise SystemExit(f"found {len(zones)} F.Cu guard zones, want one")
    outline = pcbnew.VECTOR_VECTOR2I()
    for x, y in GUARD_OUTLINE:
        outline.append(pcbnew.VECTOR2I_MM(x, y))
    zones[0].Outline().RemoveAllContours()
    zones[0].AddPolygon(outline)
    zones[0].SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(OUT), board)
    print(f"wrote {OUT}: CELL_RE and CELL_WE re-aimed, I2C_SDA off the guard "
          "corridor, guard re-tapered; now run repair_guard_fill.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
