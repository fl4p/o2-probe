#!/usr/bin/env python3
"""Close U13 power after the bounded SGX-port KRT reroute."""
from pathlib import Path
import os
import pcbnew


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe-port-routed.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-port-final.kicad_pcb"))
board = pcbnew.LoadBoard(str(SRC))
u13 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "U13")
ep = u13.FindPadByNumber("7").GetNet()
ep_code = u13.FindPadByNumber("7").GetNetCode()
input_tracks = list(board.GetTracks())


def mm_point(item, which):
    point = which(item)
    return (round(pcbnew.ToMM(point.x), 3), round(pcbnew.ToMM(point.y), 3))


# KRT connected both U13 SDA pads independently, then also added this redundant
# U-shaped loop beneath them. Remove only that loop to free the centre power-pad
# escape. Endpoint sets make the operation independent of segment direction.
sda_code = board.FindNet("/I2C_SDA").GetNetCode()
redundant = {
    frozenset(((109.350, 165.000), (109.800, 164.550))),
    frozenset(((109.800, 164.550), (110.200, 164.550))),
    frozenset(((110.200, 164.550), (110.650, 165.000))),
}
removed = 0
for item in input_tracks:
    if isinstance(item, pcbnew.PCB_VIA) or item.GetNetCode() != sda_code:
        continue
    endpoints = frozenset((mm_point(item, lambda x: x.GetStart()),
                           mm_point(item, lambda x: x.GetEnd())))
    if endpoints in redundant:
        board.Remove(item)
        removed += 1
assert removed == 3, f"expected three redundant SDA segments, removed {removed}"


def segment(net, layer, start, end, width=0.09):
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(net); track.SetLayer(layer); track.SetWidth(pcbnew.FromMM(width))
    track.SetStart(pcbnew.VECTOR2I_MM(*start)); track.SetEnd(pcbnew.VECTOR2I_MM(*end))
    board.Add(track)


rail = board.FindNet("/3V3D")
segment(rail, pcbnew.F_Cu, (110.000, 165.025), (110.000, 164.550))
dogbone = pcbnew.PCB_VIA(board)
dogbone.SetNet(rail); dogbone.SetPosition(pcbnew.VECTOR2I_MM(110.000, 164.550))
dogbone.SetWidth(pcbnew.FromMM(0.25)); dogbone.SetDrill(pcbnew.FromMM(0.15))
dogbone.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(dogbone)
segment(rail, pcbnew.In1_Cu, (110.000, 164.550), (108.000, 164.150))

# The original bottom-layer exposed-pad return ran directly beneath the new
# through-via. Move that one trace 0.60 mm to the right while preserving its
# endpoints and net; this avoids a blind/buried or via-in-pad requirement.
ep_removed = 0
for item in input_tracks:
    if isinstance(item, pcbnew.PCB_VIA) or item.GetNetCode() != ep_code:
        continue
    endpoints = frozenset((mm_point(item, lambda x: x.GetStart()),
                           mm_point(item, lambda x: x.GetEnd())))
    if endpoints == frozenset(((110.000, 166.000), (110.000, 162.500))):
        board.Remove(item); ep_removed += 1
assert ep_removed == 1
segment(ep, pcbnew.B_Cu, (110.000, 166.000), (110.600, 165.400), 0.18)
segment(ep, pcbnew.B_Cu, (110.600, 165.400), (110.600, 163.100), 0.18)
segment(ep, pcbnew.B_Cu, (110.600, 163.100), (110.000, 162.500), 0.18)

# Remove two sub-0.04 mm KRT tail fragments reported as dangling by KiCad.
for item in input_tracks:
    if (not isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetCode() == rail.GetNetCode()
            and pcbnew.ToMM(item.GetLength()) < 0.04):
        board.Remove(item)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}")
