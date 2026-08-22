#!/usr/bin/env python3
"""Close the two placement-defined links left after KiCadRoutingTools."""
from pathlib import Path
import os
import pcbnew

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe-krt5-lmp2.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe-signals-closed.kicad_pcb"))
mm = pcbnew.FromMM


def p(x, y): return pcbnew.VECTOR2I_MM(x, y)


b = pcbnew.LoadBoard(str(SRC))

def seg(net, layer, a, z, width=.09):
    t = pcbnew.PCB_TRACK(b); t.SetNet(net); t.SetLayer(layer)
    t.SetWidth(mm(width)); t.SetStart(p(*a)); t.SetEnd(p(*z)); b.Add(t)


def via(net, xy):
    v = pcbnew.PCB_VIA(b); v.SetNet(net); v.SetPosition(p(*xy))
    v.SetWidth(mm(.25)); v.SetDrill(mm(.15))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)


# R33/C28 were moved out of this escape lane in the generator.  Escape U7.6
# along its pad axis before changing layers; I2C_SCL is deliberately re-routed
# after this pass because its old trace occupied this exact dogbone corridor.
rail = b.FindNet("/3V3A")
seg(rail, pcbnew.F_Cu, (107.60, 128.00), (106.80, 128.00))
via(rail, (106.80, 128.00))
via(rail, (106.825, 130.20))
seg(rail, pcbnew.In2_Cu, (106.80, 128.00), (106.825, 130.20))

# C9 originally faced its ground pad toward R21's wiper pad.  Rotate the
# capacitor so the two VREF_WIPER pads face each other, then join them directly.
c9 = next(fp for fp in b.GetFootprints() if fp.GetReference() == "C9")
c9.Rotate(c9.GetPosition(), pcbnew.EDA_ANGLE(180, pcbnew.DEGREES_T))
wiper = b.FindNet("/VREF_WIPER")
c9p = c9.FindPadByNumber("1").GetPosition()
r21 = next(fp for fp in b.GetFootprints() if fp.GetReference() == "R21")
r21p = r21.FindPadByNumber("1").GetPosition()
seg(wiper, pcbnew.B_Cu,
    (pcbnew.ToMM(r21p.x), pcbnew.ToMM(r21p.y)),
    (pcbnew.ToMM(c9p.x), pcbnew.ToMM(c9p.y)), .18)

# Drop router-created GND fragments before the final, clean plane rebuild.  The
# other named routes are only the traces which occupy the two critical escape
# corridors; KRT reroutes this bounded set after the escapes are fixed.
rip_nets = {
    b.FindNet(name).GetNetCode()
    for name in (
        "/GND", "/I2C_SCL", "/I2C_SDA", "/VIN_MON", "/AFE_VOUT",
        "/ADC_VREF_MON",
    )
}
for item in list(b.GetTracks()):
    if item.GetNetCode() in rip_nets:
        b.Remove(item)

pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.BuildConnectivity(); pcbnew.SaveBoard(str(OUT), b)
print(f"wrote {OUT}")
