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
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import (SIDE_THERMAL_SLOTS, THERMAL_SLOTS,
                            add_vertical_slot, ensure_gnd_bridge,
                            ensure_heater_spreader, ensure_thermal_gap,
                            save_board_preserving_project)
from canonicalize import canonicalize
from critical_routes import (add_critical_routes,
                             ensure_cell_re_via_keepout, ensure_gnd_plane,
                             ensure_barrier_web_keepout,
                             ensure_gnd_stitches, write_stackup)

HERE = Path(__file__).resolve().parent
XML = HERE / "o2-probe.xml"
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
DSN = OUT.with_suffix(".dsn")
KI_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PROJECT_FP = HERE / "lib" / "o2-probe.pretty"
TMP117_FP = HERE.parent / "tmp117-probe" / "lib" / "tmp117-probe.pretty"
ORG = pcbnew.VECTOR2I_MM(100, 50)
W, L, R = 20.0, 107.0, 2.0
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
    line(board,W,R,W,L,pcbnew.Edge_Cuts,.05)
    line(board,W,L,0,L,pcbnew.Edge_Cuts,.05)
    line(board,0,L,0,R,pcbnew.Edge_Cuts,.05); arc(board,0,R,.586,.586,R,0)


def horizontal_slot(board, x, y, length, width):
    """Add one exact horizontal Edge.Cuts capsule in board-local coordinates."""
    x0, x1 = x - length / 2, x + length / 2
    y0, y1 = y - width / 2, y + width / 2
    radius = width / 2
    line(board, x0 + radius, y0, x1 - radius, y0, pcbnew.Edge_Cuts, .05)
    arc(board, x1 - radius, y0, x1, y, x1 - radius, y1)
    line(board, x1 - radius, y1, x0 + radius, y1, pcbnew.Edge_Cuts, .05)
    arc(board, x0 + radius, y1, x0, y, x0 + radius, y0)


def text(board, value, x, y, layer=pcbnew.F_SilkS, size=.7, rot=0):
    t=pcbnew.PCB_TEXT(board); t.SetText(value); t.SetPosition(pt(x,y)); t.SetLayer(layer)
    size=max(size,.8); t.SetTextSize(pcbnew.VECTOR2I_MM(size,size)); t.SetTextThickness(mm(.12))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS: t.SetMirrored(True)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); board.Add(t)


# Functional placement. Coordinates are board-local; the central 80--86 mm
# dam and the 15 mm cell keepout are intentionally empty. Support parts stay
# with their owning IC instead of being spread over a generic grid.
PLACEMENT = {
 "J101":(3.0,4.5,0,"F"), "J102":(7.7,4.5,0,"F"), "J103":(12.3,4.5,0,"F"), "J104":(17.0,4.5,0,"F"),
 "D2":(14.7,9.0,90,"F"), "R2":(12.0,9.0,90,"F"), "R3":(17.5,9.0,90,"F"),
 "F1":(2.5,19.5,90,"F"), "D1":(6.5,19.5,90,"F"), "Q1":(11.5,19.5,90,"F"), "DZ1":(16.0,19.5,90,"F"), "R1":(18.0,21.5,90,"F"),
 "C1":(2.0,31.0,90,"F"), "U1":(4.5,27.5,0,"F"), "C2":(4.5,31.0,90,"F"), "L1":(10.5,27.5,0,"F"), "C3":(15.2,25.0,90,"F"), "C4":(17.5,30.0,90,"F"),
 "C5":(1.8,36.0,90,"F"), "U2":(4.5,36.0,0,"F"), "C6":(7.5,36.0,90,"F"),
 "R32":(10.0,34.5,90,"F"), "U3":(13.0,36.0,0,"F"), "C7":(16.2,34.5,90,"F"), "C27":(18.0,34.5,90,"F"), "C8":(18.0,37.5,90,"F"),
 "U5":(3.8,42.0,90,"F"), "R4":(7.4,39.0,0,"B"), "R45":(7.5,42.7,0,"B"), "R7":(2.25,44.5,0,"B"), "C11":(6.8,46.0,0,"B"),
 # Right-side MCU lane beside U5. Rotation 180 faces RS-485 toward U5 and
 # leaves the centre-left lane for SWD and low-speed fanout.
 "U6":(14.5,44.5,180,"F"), "C12":(9.0,46.0,0,"B"), "C13":(11.8,46.0,0,"B"), "C14":(14.6,46.0,0,"B"), "C26":(17.4,46.0,0,"B"),
 "R8":(8.0,52.5,0,"B"), "C15":(10.8,52.5,180,"B"), "R9":(13.6,52.5,0,"B"), "R10":(16.0,54.5,0,"B"), "R11":(18.0,54.5,90,"B"),
 "R18":(9.0,54.5,0,"B"), "R19":(12.0,54.5,0,"B"),
 "J3":(4.5,56.5,0,"F"),
 # J2/F2/R12-R16/D4-D6 deleted 2026-09-05 (docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 3). J105/J106 are
 # the bench-bridge TTL lands that replace R15/R16, kept in the same band so the
 # USART2 runs do not lengthen.
 # R41 moved 1.00 mm left (12.4 -> 11.4) rather than moving J105/J106.
 # The SolderWire "_Relief" footprint carries its 2.20 mm NPTH 10.2 mm from
 # the pad, so J105's relief hole landed inside R41's courtyard
 # (npth_inside_courtyard, ERROR, plus a hole_clearance).
 #
 # Moving the CONNECTORS was tried first and is measurably wrong.  A sweep
 # counting every drilled hole against every courtyard leaves them 28 legal
 # poses, all one cluster at x 15.5/18.25; that clears R41 and DRC, but it
 # pushes the 2.2 mm hole to 0.65 mm of the right board edge and closes the
 # right-hand routing channel: 17 -> 51 unconnected with the seam re-ask off,
 # and gate failures (cell_re_surface_leakage) on 6 of 8 runs.  R41 has 153
 # legal poses in the same sweep and is a 0603 in a reference divider, not an
 # assembly interface, so it is the cheap side of this collision.
 "J105":(14.5,57.5,0,"B"), "J106":(17.5,57.5,0,"B"),
 "U4":(3.0,77.0,90,"F"), "U7":(10.0,79.5,270,"F"), "U8":(15.5,77.0,270,"F"),
 # The reference chain reads left to right along the row RV1/R20/R21 vacated:
 # R41 feeds the AZ431 shunt, C9 damps it, R31 isolates the bulk C10.  U15 is a
 # two-terminal shunt, so it needs no wiper and no adjustment access -- which is
 # the entire reason POTTING.md 1.2 could delete the trimmer.
 "C25":(1.2,68.0,0,"F"), "R41":(11.4,69.0,0,"B"), "U15":(8.9,73.75,0,"B"), "C9":(12.4,72.5,180,"B"), "R31":(15.6,72.5,0,"B"), "C10":(6.75,67.0,0,"B"),
 # Keep the back-side passives out from directly below U7/U8 perimeter pads;
 # through-via dogbones otherwise have no legal annulus/clearance corridor.
 # R40 taps the RE follower for the guard; R42 is the CE fault limit and wants
 # to be at U7's pin 14, not out at the cell.
 "R40":(3.0,77.0,0,"B"), "R42":(9.25,78.5,0,"B"), "C16":(12.4,74.5,0,"B"), "C17":(15.6,74.5,0,"B"), "C18":(18.0,80.2,90,"B"), "C19":(18.5,80.2,90,"F"),
 "R24":(6.0,80.2,0,"B"), "R25":(9.2,80.2,0,"B"), "R26":(12.4,80.2,0,"B"), "R27":(14.0,82.2,180,"B"), "R17":(5.0,77.0,90,"F"),
 # The AFE-output filter cannot sit below U7's left dogbones.  Put it in the
 # back-side expansion bay; the extra millimetres of trace are preferable to
 # an unroutable supply/ADC escape at the converter itself.
 "R33":(6.0,64.0,0,"B"), "C28":(9.0,64.0,0,"B"), "R39":(12.4,78.5,0,"B"), "R37":(15.6,78.5,0,"B"), "C30":(17.8,70.5,90,"B"),
 "R38":(1.5,70.0,0,"B"), "C31":(3.0,73.5,270,"B"), "R34":(6.8,70.8,0,"B"), "R35":(9.8,70.8,0,"B"), "R36":(12.8,70.8,0,"B"), "C29":(15.8,70.8,0,"B"),
 "TP1":(1.0,70.0,0,"F"), "TP3":(1.0,73.5,0,"F"), "TP4":(19.0,73.5,0,"F"), "TP5":(1.0,65.5,0,"F"),
 # Every coordinate added in this revision was solved against the real courtyard
 # geometry of the already-placed parts -- nearest free position to a functional
 # anchor, on the correct side, clear of the thermal slots, the all-layer pour
 # gap and the potting datum -- not chosen by eye.  The first hand-guessed pass
 # produced two pad-to-pad SHORTS (R44/R41 and R35/U15) and eight courtyard
 # collisions, because a SOT-23 is 3.9 mm across and the row it was dropped into
 # is on a 3.2 mm pitch.  The second pass still put D7 and F3 on top of the
 # cell's THROUGH-HOLE pads: a same-side courtyard model does not see them, but
 # a PTH pad blocks both sides.  Through-hole and NPTH pads are obstacles for
 # back-side parts regardless of which side they are drawn on.
 # TP2 is the local ground that makes the rest of the column readable with one
 # hand.  It sits at the head of the column rather than the foot: below TP3 is
 # U4, and a ground pad has no reason to be the thing that crowds the
 # electrometer.  y=61.0 is not cosmetic: at 62.0 the TESTPOINT_LABEL_AMBIGUOUS
 # guard could find NO legal position for TP5's label, because every spot within
 # 4 mm of TP5 was also close to TP2; at 58.5 the pad landed in J3's courtyard,
 # and J3 is FITTED, unlike the DNP J2 whose courtyard TP1 and TP5 already share.
 # 61.0 is the one value that both clears every courtyard outright and leaves all
 # six legends solvable.
 "TP2":(1.5,61.0,0,"F"),
 # CE compliance telemetry.  R43/R44 divide U7's DRIVE pin -- see gen_sch.py --
 # and C34 is the sampling reservoir, so it belongs at the divider tap, not at
 # the MCU.  D7 clamps the CE ELECTRODE, i.e. the exposed side of R42.
 # Rev B moves D7 to x=3.8, with a corrected DBZ pinout and a direct ground
 # stitch. The former x=10 displacement measurement does not apply here.
 # Requalify the filled spreader/thermal result for the revised candidate;
 # see docs/2026-09-09-revb-protection.md for the CE-only ESD boundary.
 "R43":(10.0,76.75,0,"B"), "R44":(6.75,76.75,0,"B"), "C34":(12.5,76.75,0,"B"), "D7":(3.8,88.0,0,"B"),
 # Rail-monitor filters, at the MCU pins they feed rather than at the dividers.
 "C32":(14.5,44.5,0,"B"), "C33":(14.5,47.5,0,"B"),
 "U11":(10.0,93.5,0,"F"),
 # User-authored ring-tip floorplan, snapped and opened up for routing/rework.
 # RH1/RH2 conduct into the HEATER_LOW ring lands; U10 measures the warm tip.
 # They STAY here (Fab, 2026-09-04, "the heater stays where it is"); F3 remains
 # the reserved protective land in the fork feed, which they do not sit in.
 "RH1":(5.0,96.5,270,"B"), "RH2":(15.0,96.5,270,"B"),
 "F3":(12.25,105.0,90,"B"),
 "Q2":(10.0,101.25,270,"B"), "R28":(6.5,101.25,180,"B"), "R29":(13.5,101.25,180,"B"), "TP6":(8.3,103.0,180,"B"),
 # U12 turned 180 degrees on 2026-09-05.  Its west pad column sits 0.60 mm from
 # the left side thermal slot's copper-clearance limit -- one 0.18 mm lane in
 # practice -- and at rotation 0 the two nets that had to leave that way were
 # I2C_SDA and I2C_SCL.  The router put SCL in the lane and then reported U12
 # pad 1 unroutable on an OTHERWISE EMPTY board, at 0.1 and 0.05 mm grid, with
 # rip-up enabled, and with SDA routed first.  Turning the part puts SDA/SCL on
 # the open east side and 3V3D/GND in the lane, where GND needs no lane at all
 # -- it drops straight into the In2 plane through a via.  Moving the part east
 # instead was tried and made it worse (three open nets, not one): the lane is
 # the constraint, not the millimetre.
 "U12":(3.5,101.5,180,"F"), "C20":(6.0,101.5,90,"F"),
 "U10":(10.0,102.525,270,"F"), "C21":(12.5,102.5,90,"F"),
 "J5":(10.0,105.5,0,"F"),
}


# Test-point identity on silkscreen.
#
# gen_pcb.py moves every footprint Reference to *.Fab and hides every field, so
# a bare board carries no printed identity at all.  That is right for the 100
# ordinary parts -- their identity is the BOM's job -- and wrong for the five
# test points, which exist to be found with a probe tip on an assembled board.
#
# The pads are 1.0 mm and this board is 20 mm wide, so the label cannot simply
# sit on top of its pad.  Each entry below is the closest position, on the pad's
# own side, that is clear of silkscreen, of every solder-mask opening, and of
# the board edge, and that is nearer to its own test point than to any other by
# audit_pcb.py -- which re-derives that from the board rather than from this
# table, and separately checks each legend is a token run of its pad's own NET,
# so a swapped pair of legends fails.  An earlier version of this comment said
# "by a wide margin", which was not true: the narrowest is GUARD at 1.41x
# against a 1.40x threshold.  Names are the electrode/function, not the reference
# designator: WE/CE are what a potentiostat bring-up sheet calls them, and a
# reference designator would need a key that a bare board cannot carry.
#
# These coordinates are solved, not chosen: nearest free position to the pad, on
# the pad's own side, clear of silk and every mask opening, AND satisfying the
# same 4.0 mm / 1.4x-margin rule audit_pcb.py enforces -- so the generator cannot
# emit a legend the audit will reject.
#
# Margins achieved run 1.41x (GUARD) to 9.23x. GUARD's 1.41x is not slack that
# was left on the table: it is the MAXIMUM the geometry allows -- searching for
# best-margin rather than nearest returns the same 1.41x, and requiring 1.75x
# returns no position at all. Five test points in a 20 mm-wide column with a
# 5-character label is the limit. A sixth pad in that column, or a longer word
# than GUARD, makes this legend unplaceable rather than merely tight.
#
# TP5 and TP1 land inside the outline of J2, which is DNP on this revision.
# That is not a coincidence to be tidied away: J2's courtyard already overlaps
# TP1 and TP5 (ASSEMBLY-EXCEPTIONS.md), so a fitted J2 buries the pads it would
# bury the labels of.  The labels are readable in exactly the build where the
# pads are reachable.
TESTPOINT_LABELS = {
    "TP2": ("GND",       3.25,  61.00, 90, "F"),
    "TP5": ("GUARD",     4.25,  64.80,  0, "F"),
    "TP1": ("WE",        3.10,  69.50,  0, "F"),
    "TP3": ("CE",        2.75,  72.90, 90, "F"),
    "TP4": ("VREF",     17.25,  73.30, 90, "F"),
    "TP6": ("TMP_CELL",  8.30, 104.75,  0, "B"),
}

# 0.8 mm is the floor, not a preference: it is the smallest character height the
# fab prints legibly, and every one of these five is at that floor.
TESTPOINT_LABEL_SIZE = 0.8


def add_testpoint_labels(board):
    """Print each test point's function next to its pad, on the pad's own side.

    Idempotent: any label this function previously wrote is removed first, so it
    can be re-applied to an already-labelled board without stacking duplicates.
    """
    wanted = {value for value, *_ in TESTPOINT_LABELS.values()}
    for item in list(board.GetDrawings()):
        if (isinstance(item, pcbnew.PCB_TEXT)
                and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
                and item.GetText() in wanted):
            board.Remove(item)
    for ref, (value, x, y, rot, side) in TESTPOINT_LABELS.items():
        layer = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
        text(board, value, x, y, layer, TESTPOINT_LABEL_SIZE, rot)
    return len(TESTPOINT_LABELS)


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
    # Two layers (Fab, 2026-09-05).  Everything downstream derives the layer
    # list from the board rather than restating it; see
    # thermal_design.copper_layers.
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().m_SolderMaskMinWidth=0
    board.GetDesignSettings().m_MinClearance=mm(.15)
    # The 0.5 mm-pitch U7 and 0.4 mm-pitch U8 escape fan-outs require the
    # documented advanced-fab floor.  Keep these values explicit so a router
    # cannot silently "solve" the board with geometry that the DRC rejects.
    board.GetDesignSettings().m_TrackMinWidth=mm(.09)
    board.GetDesignSettings().m_ViasMinSize=mm(.25)
    board.GetDesignSettings().m_MinThroughDrill=mm(.15)
    board.GetDesignSettings().m_ViasMinAnnularWidth=mm(.05)
    board.GetDesignSettings().m_CopperEdgeClearance=mm(.20)
    board.GetDesignSettings().m_HoleClearance=mm(.20)
    board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().SetClearance(mm(.15))
    outline(board)
    for slot_spec in THERMAL_SLOTS:
        horizontal_slot(board, *slot_spec)
    for slot_spec in SIDE_THERMAL_SLOTS:
        add_vertical_slot(board, *slot_spec)
    ensure_thermal_gap(board)
    for ly in (pcbnew.F_SilkS,pcbnew.B_SilkS): line(board,.5,POT_Y,19.5,POT_Y,ly,.3)
    text(board,"POT TO HERE",10,81,pcbnew.F_SilkS,.7); text(board,"POT TO HERE",10,83,pcbnew.B_SilkS,.7)
    text(board,"CABLE",10,1.5,pcbnew.F_SilkS,.7); text(board,"GAS / DO NOT POT",10,109.5,pcbnew.F_SilkS,.65)
    text(board,"DO NOT OBSTRUCT",10,99.0,pcbnew.F_SilkS,.6)
    add_testpoint_labels(board)
    # Two horizontal slots at absolute Y=134 mm reduce heat leakage from the
    # gas-side ring region while retaining 0.75 mm edge webs and a 5 mm centre
    # neck. Two 0.8 x 16 mm side slots remove lateral coupling along y=137..153;
    # their upper caps remain 2.25 mm below the transverse-slot edge and are not
    # modelled as a full 16 mm series path. The 2.0 mm all-layer rule area
    # removes plane copper across the complete transverse barrier. The SGX
    # footprint's aperture remains a separate NPTH feature.
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
            pads=[pad for pad in fps[ref].Pads() if pad.GetNumber() == pnum]
            if not pads: raise SystemExit(f"footprint pad missing: {ref}.{pnum}")
            for pad in pads: pad.SetNet(netitems[name])
    ensure_heater_spreader(board)
    ensure_gnd_plane(board)
    ensure_gnd_bridge(board)
    # The router owns the routine nets, but not these.  See critical_routes.py
    # for why each one is authored here rather than solved: CELL_RE must have no
    # via barrel, the heater path must be where the thermal model puts it, and
    # J5's fork fingers are two lands per finger that nothing in the footprint
    # joins -- the one net the exploratory scout could not close.
    ensure_cell_re_via_keepout(board)
    ensure_barrier_web_keepout(board)
    add_critical_routes(board)
    # After the authored copper, so stitch positions can avoid it.
    ensure_gnd_stitches(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    write_stackup(OUT)
    # pcbnew gives every item a fresh random KIID and writes the file in KIID
    # order, so two runs of this generator on the same inputs differ in item
    # order and in every uuid.  That is not cosmetic: a router reads the file in
    # order, and this placement measured 22, 28 and 36 unconnected links across
    # identical runs until the order was pinned.  See canonicalize.py.
    canonicalize(OUT)
    # One-node KiCad "unconnected-(...)" nets are needed for schematic parity
    # but trigger a known Freerouting 2.1 null-target bug.  Omit only those
    # one-node pseudo-nets from the DSN seed; the saved KiCad board retains them.
    for name,nodes in nets.items():
        if name.startswith("unconnected-"):
            for ref,pnum in nodes:
                for pad in fps[ref].Pads():
                    if pad.GetNumber() == pnum: pad.SetNetCode(0)
    board.BuildConnectivity()
    if not pcbnew.ExportSpecctraDSN(board,str(DSN)): raise SystemExit("Specctra export failed")
    print(f"wrote {OUT}: {len(comps)} schematic footprints, {len(nets)} connected nets")
    print(f"wrote {DSN}")


if __name__ == "__main__": build()
