#!/usr/bin/env python3
"""Reserve deterministic escape geometry before automatic signal routing.

KiCadRoutingTools can route the bulk of this narrow board, but it cannot infer
the intended escape direction for the 0.4/0.5 mm-pitch analog devices once the
surrounding nets occupy their channels.  This pass connects the three known
boxed nets on otherwise unused layer corridors using the explicit advanced-fab
floor recorded in ``gen_pcb.py``.  The later router must preserve this copper.
"""
from pathlib import Path
import os
import pcbnew

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe-seed.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-prerouted.kicad_pcb"))
mm = pcbnew.FromMM


def point(x, y):
    return pcbnew.VECTOR2I_MM(x, y)


board = pcbnew.LoadBoard(str(SRC))


def net(name):
    found = board.FindNet(name)
    if found is None:
        raise SystemExit(f"missing net {name}")
    return found


def segment(netinfo, layer, a, b, width):
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(netinfo)
    track.SetLayer(layer)
    track.SetWidth(mm(width))
    track.SetStart(point(*a))
    track.SetEnd(point(*b))
    board.Add(track)


def path(netinfo, layer, coords, width):
    for a, b in zip(coords, coords[1:]):
        if a != b:
            segment(netinfo, layer, a, b, width)


def via(netinfo, at, size=.25, drill=.15):
    item = pcbnew.PCB_VIA(board)
    item.SetNet(netinfo)
    item.SetPosition(point(*at))
    item.SetWidth(mm(size))
    item.SetDrill(mm(drill))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(item)


def pad(ref, number):
    fp = board.FindFootprintByReference(ref)
    item = fp.FindPadByNumber(str(number)) if fp else None
    if item is None:
        raise SystemExit(f"missing pad {ref}.{number}")
    p = item.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


# +12V switched rail: a wide In1.Cu spine joins the protection/buck section,
# cable hand-off, monitor divider, and both cell-heater feed resistors.
p12 = net("/+12V_SW")
p12_pads = [("J2", 1), ("U1", 2), ("U1", 3), ("DZ1", 1), ("Q1", 2),
            ("C1", 1), ("RH1", 1), ("R26", 1), ("RH2", 1)]
p12_xy = {key: pad(*key) for key in p12_pads}
for xy in p12_xy.values():
    via(p12, xy, .45, .20)
path(p12, pcbnew.In1_Cu, [(104.0, 70.44), (104.0, 154.5)], .40)
for xy in p12_xy.values():
    path(p12, pcbnew.In1_Cu, [xy, (104.0, xy[1])], .40)


# 3V3A: the low-current analog rail gets an In2.Cu spine.  Fine-pitch pads
# escape along their long axis before the through via, avoiding via-in-pad on
# U7/U8.  C25 is linked to U4 locally on F.Cu to keep it away from +12V.
p3a = net("/3V3A")
u7_escape = (106.80, 128.00)
u8_escape = (117.70, 127.25)
path(p3a, pcbnew.F_Cu, [pad("U7", 6), u7_escape], .09)
path(p3a, pcbnew.F_Cu, [pad("U8", 10), u8_escape], .09)
via(p3a, u7_escape)
via(p3a, u8_escape)
path(p3a, pcbnew.F_Cu, [pad("C25", 1), (101.20, 118.0),
                        (101.20, 124.8875), pad("U4", 8)], .18)
p3a_nodes = [pad("U3", 5), pad("U4", 8), pad("C8", 1), u7_escape,
             u8_escape, pad("R24", 1), pad("C16", 1), pad("R20", 1),
             pad("C18", 1)]
for xy in p3a_nodes:
    via(p3a, xy)
path(p3a, pcbnew.In2_Cu, [(119.20, 85.05), (119.20, 128.0)], .25)
for xy in p3a_nodes:
    path(p3a, pcbnew.In2_Cu, [xy, (119.20, xy[1])], .25)


# I2C SDA: use the back copper with two vertical spines around the gas-end
# thermal slot.  U7/U8 escape outward on F.Cu before changing layers.
sda = net("/I2C_SDA")
u7_sda = (106.80, 127.00)
u8_sda = (116.25, 124.70)
u14_sda = (117.40, 159.75)
path(sda, pcbnew.F_Cu, [pad("U7", 4), u7_sda], .09)
path(sda, pcbnew.F_Cu, [pad("U8", 13), u8_sda], .09)
path(sda, pcbnew.F_Cu, [pad("U14", 4), u14_sda], .09)
for xy in (u7_sda, u8_sda, u14_sda):
    via(sda, xy)
sda_nodes = [pad("U6", 46), pad("U12", 1), pad("U13", 4), pad("U13", 6),
             pad("U10", 6), pad("R12", 1), pad("R11", 1)]
for xy in sda_nodes:
    via(sda, xy)
path(sda, pcbnew.B_Cu, [(106.0, 94.8375), (106.0, 164.50),
                        (116.0, 164.50), (116.0, 170.0)], .18)
for xy in sda_nodes:
    spine_x = 116.0 if xy[1] >= 166.0 else 106.0
    path(sda, pcbnew.B_Cu, [xy, (spine_x, xy[1])], .18)
path(sda, pcbnew.B_Cu, [u7_sda, (106.0, u7_sda[1])], .18)
path(sda, pcbnew.B_Cu, [u8_sda, (106.0, u8_sda[1])], .18)
path(sda, pcbnew.B_Cu, [u14_sda, (106.0, u14_sda[1])], .18)

board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}")
