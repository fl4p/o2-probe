#!/usr/bin/env python3
"""Independent accepted-schematic and controlled-geometry PCB audit."""
from pathlib import Path
import math
import os
import xml.etree.ElementTree as ET
import pcbnew

HERE=Path(__file__).resolve().parent
b=pcbnew.LoadBoard(os.environ.get("O2_PCB_IN",str(HERE/"o2-probe.kicad_pcb")))
root=ET.parse(HERE/"o2-probe.xml").getroot()
want_refs={c.attrib["ref"] for c in root.find("components")}
fps={f.GetReference():f for f in b.Footprints()}
assert set(fps)==want_refs,(sorted(want_refs-set(fps)),sorted(set(fps)-want_refs))

want={}
for n in root.find("nets"):
    for node in n: want[(node.attrib["ref"],node.attrib["pin"])]=n.attrib["name"]
for ref,f in fps.items():
    for pad in f.Pads():
        key=(ref,pad.GetNumber())
        if not pad.GetNumber(): continue
        assert key in want,f"extra numbered pad {ref}.{pad.GetNumber()}"
        assert pad.GetNetname()==want[key],f"{ref}.{pad.GetNumber()}: {pad.GetNetname()} != {want[key]}"

bb=b.GetBoardEdgesBoundingBox()
# KiCad's edge bounding box includes half the 0.05 mm outline stroke on both
# sides; the centreline manufacturing geometry remains exactly 20 x 125 mm.
assert abs(pcbnew.ToMM(bb.GetWidth())-20.05)<.01
assert abs(pcbnew.ToMM(bb.GetHeight())-125.05)<.01
assert abs(pcbnew.ToMM(b.GetDesignSettings().GetBoardThickness())-1.0)<.01
assert b.GetCopperLayerCount()==4,f"expected four copper layers, got {b.GetCopperLayerCount()}"

u11=fps["U11"].GetPosition()
assert abs(pcbnew.ToMM(u11.x)-110.0)<.01 and abs(pcbnew.ToMM(u11.y)-143.5)<.01
cell_apertures=[p for p in fps["U11"].Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH and not p.GetNumber()]
assert len(cell_apertures)==1,"cell aperture missing or duplicated"
assert abs(pcbnew.ToMM(cell_apertures[0].GetDrillSize().x)-3.0)<.01,"cell aperture is not 3.00 mm"

# Keep every trace/via outside a 4.50 mm diameter construction envelope so the
# prototype port can be carefully opened further without immediately cutting a
# routed net. Pads are deliberately checked separately: SGX pad 2, 2.50 mm from
# the centre, remains the hard limit on any drill-out.
def point_mm(point): return pcbnew.ToMM(point.x),pcbnew.ToMM(point.y)
def segment_distance(a,b,c):
    ax,ay=a; bx,by=b; cx,cy=c; dx=bx-ax; dy=by-ay
    if dx==0 and dy==0: return math.hypot(cx-ax,cy-ay)
    t=max(0.0,min(1.0,((cx-ax)*dx+(cy-ay)*dy)/(dx*dx+dy*dy)))
    return math.hypot(cx-(ax+t*dx),cy-(ay+t*dy))
centre=(110.0,143.5)
for item in b.GetTracks():
    if isinstance(item,pcbnew.PCB_VIA):
        copper_edge=math.dist(point_mm(item.GetPosition()),centre)-pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu))/2
    else:
        copper_edge=segment_distance(point_mm(item.GetStart()),point_mm(item.GetEnd()),centre)-pcbnew.ToMM(item.GetWidth())/2
    assert copper_edge>=2.25-0.001,f"routed copper enters SGX drill-out envelope: {item.GetNetname()} at {copper_edge:.3f} mm"
drill_markers=[]
for shape in b.GetDrawings():
    if not isinstance(shape,pcbnew.PCB_SHAPE) or shape.GetLayer()!=pcbnew.Dwgs_User:
        continue
    if shape.GetShape()!=pcbnew.SHAPE_T_CIRCLE: continue
    if math.dist(point_mm(shape.GetCenter()),centre)<0.01:
        drill_markers.append(math.dist(point_mm(shape.GetCenter()),point_mm(shape.GetEnd())))
assert any(abs(radius-2.25)<0.01 for radius in drill_markers),"Ø4.50 mm drill-out construction circle missing"

edge=[s for s in b.Drawings() if s.GetLayer()==pcbnew.Edge_Cuts]
assert len(edge)==32,f"expected 8 outer + 24 slot edge items, got {len(edge)}"
pot=[]
for s in b.Drawings():
    if s.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS) and isinstance(s,pcbnew.PCB_SHAPE):
        if abs(pcbnew.ToMM(s.GetStart().y)-132.0)<.01 and abs(pcbnew.ToMM(s.GetEnd().y)-132.0)<.01: pot.append(s)
assert len(pot)==2,"front/back y=82 pot lines missing"
texts=[t.GetText() for t in b.Drawings() if isinstance(t,pcbnew.PCB_TEXT)]
assert texts.count("POT TO HERE")==2 and "DO NOT OBSTRUCT" in texts
zones=list(b.Zones())
assert len(zones)==1,"expected one continuous internal GND plane"
assert zones[0].GetNetname()=="/GND" and zones[0].GetLayer()==pcbnew.In2_Cu

track_count=len(list(b.GetTracks()))
out=HERE/"pcb-audit.rpt"
out.write_text(
 f"PASS: {len(fps)} schematic footprints; {len(want)} numbered pad/net assignments; "
 f"20.00 x 125.00 mm outline; 1.00 mm board; cell (10.00, 93.50); "
 f"six routed slots; four copper layers; one internal GND plane; "
 f"{track_count} track/via objects.\n")
print(out.read_text(),end="")
