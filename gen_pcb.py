#!/usr/bin/env python3
"""Generate the schematic-linked Rev-A PCB placement and Specctra seed.

Run with KiCad's bundled Python.  The accepted XML netlist is generated from
o2-probe.kicad_sch and is the only electrical input; this script owns the
controlled outline, mechanical features, placement, and board constraints.
"""

from pathlib import Path
import os
import sys
import xml.etree.ElementTree as ET

try:
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

HERE = Path(__file__).resolve().parent
XML = HERE / "o2-probe.xml"
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
DSN = OUT.with_suffix(".dsn")
KI_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PROJECT_FP = HERE / "lib" / "o2-probe.pretty"
TMP117_FP = HERE.parent / "tmp117-probe" / "lib" / "tmp117-probe.pretty"
ORG = pcbnew.VECTOR2I_MM(100, 50)
W, L, R = 20.0, 125.0, 2.0
POT_Y = 82.0


def mm(v): return pcbnew.FromMM(v)
def pt(x, y): return pcbnew.VECTOR2I(ORG.x + mm(x), ORG.y + mm(y))


def libpath(nick):
    if nick == "o2-probe": return PROJECT_FP
    if nick == "tmp117-probe": return TMP117_FP
    return KI_FP / f"{nick}.pretty"


def line(board, x1, y1, x2, y2, layer, width=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(pt(x1,y1)); s.SetEnd(pt(x2,y2))
    s.SetLayer(layer); s.SetWidth(mm(width)); board.Add(s)


def arc(board, sx, sy, mx, my, ex, ey):
    s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(pt(sx,sy), pt(mx,my), pt(ex,ey)); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.05)); board.Add(s)


def outline(board):
    line(board,R,0,W-R,0,pcbnew.Edge_Cuts,.05); arc(board,W-R,0,W-.586,.586,W,R)
    line(board,W,R,W,L-R,pcbnew.Edge_Cuts,.05); arc(board,W,L-R,W-.586,L-.586,W-R,L)
    line(board,W-R,L,R,L,pcbnew.Edge_Cuts,.05); arc(board,R,L,.586,L-.586,0,L-R)
    line(board,0,L-R,0,R,pcbnew.Edge_Cuts,.05); arc(board,0,R,.586,.586,R,0)


def text(board, value, x, y, layer=pcbnew.F_SilkS, size=.7, rot=0):
    t=pcbnew.PCB_TEXT(board); t.SetText(value); t.SetPosition(pt(x,y)); t.SetLayer(layer)
    size=max(size,.8); t.SetTextSize(pcbnew.VECTOR2I_MM(size,size)); t.SetTextThickness(mm(.12))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS: t.SetMirrored(True)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); board.Add(t)


def slot(board, x, y, length, width, vertical=False):
    """Closed routed slot on Edge.Cuts without a fake schematic footprint."""
    if vertical:
        # Generate a horizontal capsule in swapped coordinates.
        return slot_xy_swapped(board, y, x, length, width)
    x0,x1=x-length/2,x+length/2; y0,y1=y-width/2,y+width/2; rr=width/2
    line(board,x0+rr,y0,x1-rr,y0,pcbnew.Edge_Cuts,.05)
    arc(board,x1-rr,y0,x1,y,x1-rr,y1)
    line(board,x1-rr,y1,x0+rr,y1,pcbnew.Edge_Cuts,.05)
    arc(board,x0+rr,y1,x0,y,x0+rr,y0)


def slot_xy_swapped(board, y, x, length, width):
    y0,y1=y-length/2,y+length/2; x0,x1=x-width/2,x+width/2; rr=width/2
    line(board,x0,y0+rr,x0,y1-rr,pcbnew.Edge_Cuts,.05)
    # Three-point arcs, start -> midpoint -> end.
    s=pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(pt(x0,y1-rr),pt(x,y1),pt(x1,y1-rr)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(.05)); board.Add(s)
    line(board,x1,y1-rr,x1,y0+rr,pcbnew.Edge_Cuts,.05)
    s=pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(pt(x1,y0+rr),pt(x,y0),pt(x0,y0+rr)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(.05)); board.Add(s)


# Functional placement. Coordinates are board-local; the central 80--86 mm
# dam and the 15 mm cell keepout are intentionally empty. Support parts stay
# with their owning IC instead of being spread over a generic grid.
PLACEMENT = {
 "J101":(3.0,4.5,0,"F"), "J102":(7.7,4.5,0,"F"), "J103":(12.3,4.5,0,"F"), "J104":(17.0,4.5,0,"F"),
 "D2":(14.7,9.0,90,"F"), "R2":(12.0,9.0,90,"F"), "R3":(17.5,9.0,90,"F"),
 "F1":(2.5,19.5,90,"F"), "D1":(6.5,19.5,90,"F"), "Q1":(11.5,19.5,90,"F"), "DZ1":(16.0,19.5,90,"F"), "R1":(18.0,21.5,90,"F"),
 "C1":(2.0,31.0,90,"F"), "U1":(4.5,27.5,0,"F"), "C2":(4.5,31.0,90,"F"), "L1":(10.5,27.5,0,"F"), "C3":(15.2,25.0,90,"F"), "C4":(17.5,30.0,90,"F"),
 "C5":(1.8,36.0,90,"F"), "U2":(4.5,36.0,0,"F"), "C6":(7.5,36.0,90,"F"),
 "R32":(10.0,34.5,90,"F"), "U3":(13.0,36.0,0,"F"), "C7":(16.2,34.5,90,"F"), "C27":(18.0,34.5,90,"F"), "C8":(16.8,38.5,90,"F"),
 "U5":(3.8,42.0,90,"F"), "R4":(7.4,39.0,0,"B"), "R5":(7.4,41.0,0,"B"), "R6":(7.4,43.0,0,"B"), "R7":(1.5,46.0,0,"B"), "C11":(6.8,46.0,0,"B"),
 "U6":(12.5,49.0,0,"F"), "C12":(9.0,46.0,0,"B"), "C13":(11.8,46.0,0,"B"), "C14":(14.6,46.0,0,"B"), "C26":(17.4,46.0,0,"B"),
 "R8":(8.0,52.5,0,"B"), "C15":(10.8,52.5,180,"B"), "R9":(13.6,52.5,0,"B"), "R10":(16.0,54.5,0,"B"), "R11":(18.0,54.5,90,"B"),
 "R18":(9.0,54.5,0,"B"), "R19":(12.0,54.5,0,"B"),
 "J3":(4.5,56.5,0,"F"),
 "J2":(10.0,67.0,0,"F"), "F2":(17.5,62.0,90,"B"), "R12":(4.0,57.5,0,"B"), "R13":(6.8,59.0,0,"B"), "R14":(11.5,57.5,0,"B"), "R15":(14.5,57.5,0,"B"), "R16":(17.5,57.5,0,"B"),
 "D4":(3.0,60.0,90,"B"), "D5":(10.0,60.0,90,"B"), "D6":(17.0,60.0,90,"F"),
 "U4":(3.0,77.0,90,"F"), "RV1":(2.5,73.0,90,"B"), "U7":(10.0,79.5,270,"F"), "U8":(15.5,77.0,0,"F"),
 "C25":(1.2,68.0,0,"F"), "R20":(6.0,72.5,0,"B"), "R21":(9.2,72.5,0,"B"), "C9":(12.4,72.5,180,"B"), "R31":(15.6,72.5,0,"B"), "C10":(18.3,74.0,90,"B"),
 # Keep the back-side passives out from directly below U7/U8 perimeter pads;
 # through-via dogbones otherwise have no legal annulus/clearance corridor.
 "R22":(6.5,74.5,0,"B"), "R23":(9.2,74.5,0,"B"), "C16":(12.4,74.5,0,"B"), "C17":(15.6,74.5,0,"B"), "C18":(18.0,80.2,90,"B"), "C19":(18.5,80.2,90,"F"),
 "R24":(6.0,80.2,0,"B"), "R25":(9.2,80.2,0,"B"), "R26":(12.4,80.2,0,"B"), "R27":(15.6,80.2,0,"B"), "R17":(5.0,77.0,90,"F"),
 # The AFE-output filter cannot sit below U7's left dogbones.  Put it in the
 # back-side expansion bay; the extra millimetres of trace are preferable to
 # an unroutable supply/ADC escape at the converter itself.
 "R33":(6.0,64.0,0,"B"), "C28":(9.0,64.0,0,"B"), "R39":(12.4,78.5,0,"B"), "R37":(15.6,78.5,0,"B"), "C30":(17.8,70.5,90,"B"),
 "R38":(1.5,70.0,0,"B"), "C31":(4.0,70.0,0,"B"), "R34":(6.8,70.8,0,"B"), "R35":(9.8,70.8,0,"B"), "R36":(12.8,70.8,0,"B"), "C29":(15.8,70.8,0,"B"),
 "TP1":(1.0,70.0,0,"F"), "TP3":(1.0,73.5,0,"F"), "TP4":(19.0,73.5,0,"F"), "TP5":(1.0,65.5,0,"F"),
 "U11":(10.0,93.5,0,"F"),
 "RH1":(5.3,104.5,0,"B"), "RH2":(14.7,104.5,0,"B"), "U10":(10.0,104.0,90,"B"), "Q2":(10.0,108.0,90,"B"), "R28":(7.0,108.0,90,"B"), "R29":(13.0,108.0,90,"B"), "TP6":(10.0,101.0,0,"B"),
 "U12":(6.0,112.0,0,"F"), "C20":(8.0,112.0,90,"F"), "U13":(10.0,116.0,90,"F"), "C21":(12.0,116.0,90,"F"), "R30":(8.0,116.0,90,"F"), "TP7":(10.0,119.0,0,"B"),
 "U14":(16.0,120.0,0,"F"), "C22":(18.0,116.0,90,"F"), "C23":(15.0,116.0,90,"F"), "C24":(18.0,122.0,90,"F"),
}


def parse():
    root=ET.parse(XML).getroot(); comps={}
    for c in root.find("components"):
        ref=c.attrib["ref"]; props={p.attrib["name"]:p.attrib.get("value","") for p in c.findall("property")}
        comps[ref]={"value":c.findtext("value"),"fp":c.findtext("footprint"),"uuid":c.findtext("tstamps"),"dnp":"dnp" in props,"props":props}
    nets={}
    for n in root.find("nets"):
        name=n.attrib["name"]
        nets[name]=[(x.attrib["ref"],x.attrib["pin"]) for x in n]
    return comps,nets


def build():
    comps,nets=parse(); board=pcbnew.CreateEmptyBoard(); board.GetDesignSettings().SetBoardThickness(mm(1.0))
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().m_SolderMaskMinWidth=0
    board.GetDesignSettings().m_MinClearance=mm(.15)
    # The 0.5 mm-pitch U7 and 0.4 mm-pitch U8 escape fan-outs require the
    # documented advanced-fab floor.  Keep these values explicit so a router
    # cannot silently "solve" the board with geometry that the DRC rejects.
    board.GetDesignSettings().m_TrackMinWidth=mm(.09)
    board.GetDesignSettings().m_ViasMinSize=mm(.25)
    board.GetDesignSettings().m_MinThroughDrill=mm(.15)
    board.GetDesignSettings().m_ViasMinAnnularWidth=mm(.05)
    board.GetDesignSettings().m_CopperEdgeClearance=mm(.25)
    board.GetDesignSettings().m_HoleClearance=mm(.20)
    board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().SetClearance(mm(.15))
    outline(board)
    for ly in (pcbnew.F_SilkS,pcbnew.B_SilkS): line(board,.5,POT_Y,19.5,POT_Y,ly,.3)
    text(board,"POT TO HERE",10,81,pcbnew.F_SilkS,.7); text(board,"POT TO HERE",10,83,pcbnew.B_SilkS,.7)
    text(board,"CABLE",10,1.5,pcbnew.F_SilkS,.7); text(board,"GAS / DO NOT POT",10,109.5,pcbnew.F_SilkS,.65)
    text(board,"DO NOT OBSTRUCT",10,99.0,pcbnew.F_SilkS,.6)
    # The dam slots keep the guarded AFE trace bridge central.  The two tip
    # slots are transverse to heater-to-U13 heat flow; their 0.75 mm edge webs
    # plus 3.5 mm centre neck leave 5.0 mm of direct FR-4 cross-section.
    slot(board,3.75,84.0,5.5,1.0); slot(board,16.25,84.0,5.5,1.0)
    slot(board,1.2,95.0,16.0,.8,True); slot(board,18.8,95.0,16.0,.8,True)
    slot(board,4.5,114.0,7.5,.8); slot(board,15.5,114.0,7.5,.8)
    # Nets must exist before pad assignment.
    netitems={}
    for name in nets:
        ni=pcbnew.NETINFO_ITEM(board,name); board.Add(ni); netitems[name]=ni
    pos=PLACEMENT; fps={}
    missing=set(comps)-set(pos)
    if missing: raise SystemExit(f"no placement for {sorted(missing)}")
    for ref,c in comps.items():
        nick,name=c["fp"].split(":",1); fp=pcbnew.FootprintLoad(str(libpath(nick)),name)
        if fp is None: raise SystemExit(f"missing footprint {c['fp']}")
        board.Add(fp); fp.SetFPID(pcbnew.LIB_ID(nick,name)); fp.SetReference(ref); fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/"+c["uuid"])); fp.SetDNP(c["dnp"]); fp.SetExcludedFromBOM(ref.startswith("TP"))
        for key,value in c.get("props",{}).items():
            if key not in ("Sheetname","Sheetfile","dnp"): fp.SetField(key,value)
        x,y,rot,side=pos[ref]; fp.SetPosition(pt(x,y)); fp.SetOrientationDegrees(rot)
        if side=="B": fp.Flip(fp.GetPosition(),False)
        # Preserve library geometry byte-for-byte.  Deleting silkscreen from
        # every placed copy made KiCad report 110 library mismatches and hid
        # genuine library drift.  Identity stays on Fab; release Gerbers omit
        # silkscreen because this probe has no assembly-print requirement.
        fp.Reference().SetLayer(pcbnew.B_Fab if side=="B" else pcbnew.F_Fab)
        # Hide every footprint field, including custom MPN/description fields.
        # KiCad otherwise renders those fields on the board and produces an
        # unreadable wall of text despite reference/value already being hidden.
        for field in fp.GetFields(): field.SetVisible(False)
        fps[ref]=fp
    for name,nodes in nets.items():
        for ref,pnum in nodes:
            pad=fps[ref].FindPadByNumber(pnum)
            if pad is None: raise SystemExit(f"footprint pad missing: {ref}.{pnum}")
            pad.SetNet(netitems[name])
    board.BuildConnectivity(); board.Save(str(OUT))
    # One-node KiCad "unconnected-(...)" nets are needed for schematic parity
    # but trigger a known Freerouting 2.1 null-target bug.  Omit only those
    # one-node pseudo-nets from the DSN seed; the saved KiCad board retains them.
    for name,nodes in nets.items():
        if name.startswith("unconnected-"):
            for ref,pnum in nodes: fps[ref].FindPadByNumber(pnum).SetNetCode(0)
    board.BuildConnectivity()
    if not pcbnew.ExportSpecctraDSN(board,str(DSN)): raise SystemExit("Specctra export failed")
    print(f"wrote {OUT}: {len(comps)} schematic footprints, {len(nets)} connected nets")
    print(f"wrote {DSN}")


if __name__ == "__main__": build()
