#!/usr/bin/env python3
"""Clear routed copper from a rework envelope around the SGX rear port."""
from pathlib import Path
import os
import pcbnew


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-drill-clearance.kicad_pcb"))
board = pcbnew.LoadBoard(str(SRC))


def xy(point):
    return round(pcbnew.ToMM(point.x), 3), round(pcbnew.ToMM(point.y), 3)


def endpoints(track):
    return frozenset((xy(track.GetStart()), xy(track.GetEnd())))


def segment(net, layer, start, end, width):
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(net)
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width))
    track.SetStart(pcbnew.VECTOR2I_MM(*start))
    track.SetEnd(pcbnew.VECTOR2I_MM(*end))
    board.Add(track)


# Snapshot and classify before any removal. KiCad's SWIG track container can no
# longer be iterated safely after objects from it have been deleted.
input_tracks = list(board.GetTracks())

# Move the local SDA run to In1 and take it around the outside of cell pad 1.
# In2 remains an uninterrupted GND plane.  The existing via at the lower end is
# retained; a second 0.25/0.15 mm through-via returns to the original B.Cu run.
sda = board.FindNet("/I2C_SDA")
sda_remove = []
for item in input_tracks:
    if isinstance(item, pcbnew.PCB_VIA) or item.GetNetCode() != sda.GetNetCode():
        continue
    if item.GetLayer() != pcbnew.B_Cu:
        continue
    points = endpoints(item)
    if all(107.5 <= x <= 108.5 and 139.15 <= y <= 148.25 for x, y in points):
        sda_remove.append(item)
assert len(sda_remove) == 11, f"expected 11 local SDA segments, found {len(sda_remove)}"

segment(sda, pcbnew.In1_Cu, (107.600, 139.150), (106.200, 137.750), 0.09)
segment(sda, pcbnew.In1_Cu, (106.200, 137.750), (105.800, 137.750), 0.09)
segment(sda, pcbnew.In1_Cu, (105.800, 137.750), (105.800, 148.250), 0.09)
segment(sda, pcbnew.In1_Cu, (105.800, 148.250), (108.250, 148.250), 0.09)
sda_via = pcbnew.PCB_VIA(board)
sda_via.SetNet(sda)
sda_via.SetPosition(pcbnew.VECTOR2I_MM(108.250, 148.250))
sda_via.SetWidth(pcbnew.FromMM(0.25))
sda_via.SetDrill(pcbnew.FromMM(0.15))
sda_via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
board.Add(sda_via)

# Shift the unrelated heater-PWM trunk 0.40 mm outward.  Its previous diagonal
# and vertical segments were the second-closest routed copper to the port.
pwm = board.FindNet("/HEATER_PWM")
pwm_old = {
    frozenset(((119.500, 135.600), (112.000, 143.100))),
    frozenset(((112.000, 143.100), (112.000, 152.200))),
}
pwm_remove = []
for item in input_tracks:
    if isinstance(item, pcbnew.PCB_VIA) or item.GetNetCode() != pwm.GetNetCode():
        continue
    if endpoints(item) in pwm_old:
        pwm_remove.append(item)
assert len(pwm_remove) == 2, f"expected two heater-PWM segments, found {len(pwm_remove)}"

for item in sda_remove + pwm_remove:
    board.Remove(item)
segment(pwm, pcbnew.B_Cu, (119.500, 135.600), (112.800, 142.300), 0.18)
segment(pwm, pcbnew.B_Cu, (112.800, 142.300), (112.400, 143.100), 0.18)
segment(pwm, pcbnew.B_Cu, (112.400, 143.100), (112.400, 152.200), 0.18)
segment(pwm, pcbnew.B_Cu, (112.400, 152.200), (112.000, 152.200), 0.18)

# A board-level construction circle makes the audited no-track envelope visible
# without pretending that it is the presently drilled diameter.
marker = pcbnew.PCB_SHAPE(board)
marker.SetShape(pcbnew.SHAPE_T_CIRCLE)
marker.SetCenter(pcbnew.VECTOR2I_MM(110.0, 143.5))
marker.SetEnd(pcbnew.VECTOR2I_MM(112.25, 143.5))
marker.SetLayer(pcbnew.Dwgs_User)
marker.SetWidth(pcbnew.FromMM(0.05))
board.Add(marker)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}; cleared routed copper from the diameter-4.50 mm envelope")
