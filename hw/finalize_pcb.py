#!/usr/bin/env python3
"""Apply deterministic post-router cleanup and refill copper zones."""
from pathlib import Path
import os
import pcbnew


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe-krt-final.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-final.kicad_pcb"))

board = pcbnew.LoadBoard(str(SRC))

# KRT inherited two /3V3D vias only 0.15 mm apart at U12.  They connect the
# same local copper, so retain the via at x=106.95 and remove the duplicate.
for item in list(board.GetTracks()):
    if not isinstance(item, pcbnew.PCB_VIA):
        continue
    pos = item.GetPosition()
    if (item.GetNetname() == "/3V3D"
            and abs(pcbnew.ToMM(pos.x) - 107.10) < 0.001
            and abs(pcbnew.ToMM(pos.y) - 162.40) < 0.001):
        board.Remove(item)

# The GND tap beside U7's LMP_C2 escape was generated as a 0.45/0.20 mm via
# and misses the 0.15 mm copper clearance by 0.02 mm.  A 0.40/0.20 mm via
# preserves a 0.10 mm annular ring and clears the signal without moving the
# connected bottom-side ground stub.
for item in board.GetTracks():
    if not isinstance(item, pcbnew.PCB_VIA):
        continue
    pos = item.GetPosition()
    if (item.GetNetname() == "/GND"
            and abs(pcbnew.ToMM(pos.x) - 112.05) < 0.001
            and abs(pcbnew.ToMM(pos.y) - 128.50) < 0.001):
        item.SetWidth(pcbnew.FromMM(0.40))

# Keep the back-side potting datum readable, but move its label clear of the
# B-side monitor-divider pads.  The datum line itself stays at y=132.0 mm.
for drawing in board.GetDrawings():
    if (isinstance(drawing, pcbnew.PCB_TEXT)
            and drawing.GetText() == "POT TO HERE"
            and drawing.GetLayer() == pcbnew.B_SilkS):
        drawing.SetPosition(pcbnew.VECTOR2I_MM(110.0, 133.0))

# Plane repair's exact-fill oracle runs after its first write.  Refill and save
# once more so the persisted board contains the same anti-pads the oracle used.
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}")
