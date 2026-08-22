#!/usr/bin/env python3
"""Enlarge the SGX gas aperture and withdraw only the affected routes."""
from pathlib import Path
import os
import pcbnew


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-port-seed.kicad_pcb"))

board = pcbnew.LoadBoard(str(SRC))
u11 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "U11")
apertures = [
    pad for pad in u11.Pads()
    if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and not pad.GetNumber()
]
assert len(apertures) == 1
apertures[0].SetSize(pcbnew.VECTOR2I_MM(3.0, 3.0))
apertures[0].SetDrillSize(pcbnew.VECTOR2I_MM(3.0, 3.0))

# These are the only two routed nets intersecting the enlarged hole/clearance
# envelope. KRT reroutes them as a bounded follow-on pass.
rip_codes = {board.FindNet(name).GetNetCode() for name in ("/I2C_SDA", "/3V3D")}
for item in list(board.GetTracks()):
    if item.GetNetCode() in rip_codes:
        board.Remove(item)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}")
