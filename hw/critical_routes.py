#!/usr/bin/env python3
"""Generator-owned copper: the routes a router is not allowed to invent.

`gen_pcb.py` owns placement and mechanical geometry; `KiCadRoutingTools` owns
the routine nets.  This module owns the third category -- copper whose exact
topology is a design decision rather than a connectivity problem, so it is
authored here, emitted before the router runs, and marked locked so the router
routes *around* it instead of through it.

Four things qualify on this board.

1.  **The In2 ground plane.**  The Rev-A board had one; the regenerated Rev-B
    placement had no ground plane at all, which is why the pre-route board
    showed 253 unconnected items with GND as the largest single contributor.
    It is generator-owned because the all-layer thermal rule area splits it,
    and `thermal_design.ensure_gnd_bridge` is the only thing that reconnects
    the two halves.

2.  **CELL_RE.**  The electrometer input.  One F.Cu polyline, no vias, no layer
    change, from the cell's reference land to U7 pin 13.  A via barrel in this
    net is a leakage path through the laminate that no DRC rule scores, so the
    router must never be in a position to add one.

3.  **CELL_WE.**  Same argument, one rank weaker: the working electrode carries
    the measured current, so its surface leakage matters, but it is not the
    high-impedance node CELL_RE is.  The U7 leg is authored; the TP1 and U4
    taps are left to the router.

4.  **The heater current path and the fork tip.**  RH1/RH2 -> Q2 -> J5 carries
    ~80 mA at 12 V and is the load the bench run in FAB-READINESS.md exercised.
    The B.Cu spreader zone would in fact weld all of these pads together on its
    own, but a zone fill is not a conductor a reviewer can point at, and any
    later net routed across the island can fragment it.  The explicit 0.80 mm
    B.Cu path pins the current where the thermal model assumes it is.

    The fork tip is the part the exploratory scout could not solve at all:
    `/+12V_HTR` was the one open net out of 61, because J5's two fingers are
    F.Cu *and* B.Cu lands at the board tip with no via joining the two, and
    the direct B.Cu run from F3 to the far finger is blocked by TP6.  The feed
    crosses on In1 instead and drops onto both fingers through one through via
    each -- which is also what `audit_pcb.RING_FORK_LAYER_JOIN` requires.

5.  **The driven guard.**  Two F.Cu rails flanking CELL_RE, tied under it on
    B.Cu and fed once from R40.  Rev A poured this and needed a whole migration
    to keep the pour connected; rails are immune to the fragmentation that made
    a pour expensive.  See the CRITICAL_TRACKS entry for why.
"""

from __future__ import annotations

from pathlib import Path

import pcbnew

from thermal_design import (ORIGIN_X_MM, ORIGIN_Y_MM, copper_layers,
                            _polygon, _one_named_zone)


# The fabrication stack, in the order KiCad serialises it.  Two layers, total
# 1.0 mm: 0.035 outer copper, a 0.93 mm FR-4 core, and ENIG.
#
# 1.0 mm is not a default.  It is the thickness the probe's mechanics already
# assume -- the tube fit, the potting fixture, and RING-PCB.md's finger
# envelope, which budgets the board's own thickness as +/-0.5 mm against the
# neck annulus.  Going to the more usual 1.6 mm would change a mechanical
# interface, so the layer count changed and the thickness did not.
#
# gen_pcb.py never wrote this.  The Rev-A board carried it because it was set
# once in the GUI and the board was never regenerated from the generator after
# that; the moment Rev B was regenerated the whole stack vanished, and the fab
# would have received a four-layer board with no layer thickness, no dielectric
# and no surface finish.  audit_pcb.py's STACKUP guard is what found it.
#
# The dielectric numbers are a nominal 1.0 mm model and the fab note authorises
# vendor adjustment; the copper weights and the finish are not negotiable.
STACKUP = (
    ("F.Mask", "Top Solder Mask", 0.01, None),
    ("F.Cu", "copper", 0.035, None),
    ("dielectric 1", "core", 0.93, "FR4"),
    ("B.Cu", "copper", 0.035, None),
    ("B.Mask", "Bottom Solder Mask", 0.01, None),
)
COPPER_FINISH = "ENIG"

CELL_RE_KEEPOUT_NAME = "CELL_RE_VIA_KEEPOUT"
# A corridor 0.4 mm either side of the authored CELL_RE run, on every layer,
# in which no via may be placed.
#
# The locked trace alone is not enough.  Measured 2026-09-05: with CELL_RE
# authored and locked but its U4 leg left to the router, KRT dropped a through
# via at (11.00, 82.00) -- in the MIDDLE of the protected run -- took the leg
# down to B.Cu, snaked it under U7 and brought it back up at (4.00, 76.00).
# Two barrels through the laminate in the electrometer reference node, and
# every rule on the board says that is fine, because no rule scores leakage.
# Follows the run at +/-0.30 mm.  It deliberately stops short of the guard
# rails at x=11.05 and 12.15, whose own vias at y=86.00 must remain legal.
CELL_RE_KEEPOUT = ((10.70, 81.20), (11.30, 81.20), (11.30, 82.60),
                   (11.90, 83.20), (11.90, 91.40), (11.30, 91.40),
                   (11.30, 83.40), (10.70, 82.80))

GND_PLANE_NAME = "GND_PLANE"
GND_PLANE = ((0.0, 0.0), (20.0, 0.0), (20.0, 107.0), (0.0, 107.0))
# The heater spreader and the ground pour share B.Cu on the two-layer board.
# Priority decides who yields: the spreader is a thermal element whose area is
# budgeted in HEATED-SPREADER.md, ground is not, so ground retreats.
GND_PLANE_PRIORITY = 0
HEATER_SPREADER_PRIORITY = 10

F = pcbnew.F_Cu
B = pcbnew.B_Cu

# (net, layer, width_mm, [(x, y), ...])  -- board-local millimetres.
CRITICAL_TRACKS = (
    # -- CELL_RE: U11 pad 2 (the cell's reference land) to U7 pin 13.  x=12.10
    # is the only column that clears both thermal slots: the right slot starts
    # at x=12.5, so the 0.25 mm trace edge sits 0.275 mm off it against a
    # 0.20 mm copper-to-edge rule.  Via-free by construction.  It steps to
    # x=11.00 inside the barrier and comes down on the pad from due north: the
    # first version cut the corner at 45 degrees and DRC caught it SHORTING
    # U7 pin 14 (/CELL_CE_DRV), which is 0.5 mm away on the same row.
    ("/CELL_RE", F, 0.25, ((12.54, 91.00), (11.60, 90.06), (11.60, 83.10),
                           (11.00, 82.50), (11.00, 81.40))),

    # -- The driven guard.  Two F.Cu rails at 0.275 mm either side of the run,
    # joined under it on B.Cu, fed once from R40.
    #
    # On the four-layer board this was going to be a POUR, and a pour is why it
    # never got built: the all-layer thermal rule area and CELL_RE between them
    # split it into four regions, each needing its own feed, and every feed
    # competed for In1 in the same 5 mm neck the signals cross.  Rev A solved
    # that with a separate migration owning four vias and ten stitch links.
    #
    # A rule area blocks zone FILL, not tracks.  Rails are therefore immune to
    # the thing that fragmented the pour, need no island-removal handling, and
    # cost ONE crossing in the neck instead of four.  Going to two layers is
    # what made it worth redoing rather than porting.
    #
    # They start at y=83.40, above CELL_RE's step to U7's pin-13 column, and
    # the last 2 mm into the pad is unguarded: below that the run is squeezed
    # between CELL_WE at x=10.60 and its own column, and it arrives at a device
    # whose pins are on 0.5 mm pitch, which no guard rail can improve on.
    ("/GUARD_REPLICA", F, 0.30, ((11.05, 83.40), (11.05, 89.60))),
    ("/GUARD_REPLICA", F, 0.30, ((12.15, 83.40), (12.15, 89.60))),
    # The rails cannot meet on F.Cu -- CELL_RE runs between them and ends on
    # U11's land -- so they are tied underneath at BOTH ends instead.  That
    # closes the guard into a ring around the run rather than leaving two
    # stubs, which is both better shielding and the difference between two
    # track_dangling findings and none: a rail with a free end is, to DRC,
    # exactly an unfinished route.
    ("/GUARD_REPLICA", B, 0.30, ((10.80, 83.40), (12.15, 83.40))),
    ("/GUARD_REPLICA", B, 0.30, ((11.05, 89.60), (12.15, 89.60))),
    # One feed, from R40's output pad, west of everything at y=79.35: that lane
    # clears R42/R39 (bottom edge 78.97) and the R24..R27 row (top edge 79.73)
    # by 0.28 mm either side.  It crosses the barrier at x=10.80, inside the
    # 7.70..12.30 neck and 0.255 mm clear of R26.
    ("/GUARD_REPLICA", B, 0.25, ((2.17, 77.00), (2.17, 79.35),
                                 (10.80, 79.35), (10.80, 83.40))),
    # -- CELL_WE: the same crossing, 2.1 mm west of CELL_RE.  It comes down U7's
    # pin-12 COLUMN, not across it.  U7's south row is on 0.5 mm pitch with
    # 0.26 mm between pad edges, so nothing fits between two pads: every pad on
    # that row escapes straight south in its own column or not at all.  The
    # first version cut west at y=82.40 and sat on top of pin 11's column, and
    # the router reported /VREF_TRIM boxed_in_static at that pad.
    ("/CELL_WE", F, 0.20, ((10.00, 91.00), (10.00, 84.00),
                           (10.50, 83.50), (10.50, 81.40))),

    # -- Heater current path.  The bus threads a 1.27 mm band: U11's gas
    # aperture is a 3.0 x 6.0 mm NPTH slot ending at y=98.30, and Q2's pin-1/2
    # row starts at y=99.57.  At 0.80 mm wide with 0.20 mm to the slot and
    # 0.15 mm to the pads the centreline has 0.12 mm of freedom; y=98.96 is the
    # middle of it.  The descent at x=10.00 then runs down the 1.3 mm gap
    # between Q2's two pads with 0.25 mm either side and lands on pad 3.
    ("/HEATER_LOW", B, 0.80, ((6.00, 99.46), (6.00, 98.96), (14.00, 98.96),
                              (14.00, 99.46))),
    ("/HEATER_LOW", B, 0.80, ((10.00, 98.96), (10.00, 102.19))),
    # Q2 pad 3 out to the far fork finger.  y=102.60 clears R29 (bottom edge
    # 101.725) and stays south of F3 (top edge 103.78).
    ("/HEATER_LOW", B, 0.80, ((10.00, 102.19), (10.00, 102.60),
                              (17.80, 102.60))),
    # Necked to 0.60 for the last leg: at 0.80 the trace edge would sit exactly
    # 0.20 mm off the right side slot, i.e. on the rule rather than inside it.
    ("/HEATER_LOW", B, 0.60, ((17.80, 102.60), (17.80, 105.50))),
    ("/HEATER_LOW", F, 0.60, ((17.80, 104.60), (17.80, 105.50))),

    # -- +12V_HTR: F3 down to In1, west under the tip, up onto both faces of
    # the near fork finger.  B.Cu at y=103.40 is not available -- TP6 occupies
    # x=7.8..8.8 there -- and In1 is empty across the whole island.
    # y=103.75 rather than 103.60: at 103.60 the In1 drop via cleared C21's
    # 3V3D land by 0.1216 mm against a 0.15 mm rule.
    ("/+12V_HTR", B, 0.60, ((12.25, 104.18), (12.25, 103.75))),
    # The crossing runs at y=104.40, not straight west at 103.75: at 103.75 the
    # 0.60 mm feed sat directly under U10's south pad row (y=103.275..103.725)
    # and walled off its escape -- the router then left /I2C_SDA open at U10
    # pad 6.  0.375 mm of clearance below that row is enough for both.
    #
    # It was on In1 while this board had four layers.  On two it goes on F.Cu,
    # NOT B.Cu: a 10 mm gash at y=104.40 through the B.Cu heater spreader would
    # cut a 2 mm strip off the tip end of the very pour that is supposed to be
    # isothermal, to save one via.
    ("/+12V_HTR", F, 0.60, ((12.25, 103.75), (11.60, 104.40),
                            (2.20, 104.40))),
    ("/+12V_HTR", B, 0.60, ((2.20, 104.40), (2.20, 105.50))),
    ("/+12V_HTR", F, 0.60, ((2.20, 104.40), (2.20, 105.50))),
)

# (net, x, y, size_mm, drill_mm).  Both of these are the fork-tip layer joins:
# each finger is an F.Cu land and a B.Cu land at the same coordinate, and
# nothing in the footprint connects them.
CRITICAL_VIAS = (
    # Guard rails to their B.Cu ties.  0.25/0.15, not 0.45/0.25: a 0.45 mm
    # barrel at x=12.15 would leave 0.125 mm to the right thermal slot against
    # a 0.20 mm copper-to-edge rule.  All four sit OUTSIDE CELL_RE_VIA_KEEPOUT,
    # which hugs the run at +/-0.30 mm; the keepout exists to keep foreign
    # barrels away from the reference node, and guard copper at the same
    # potential is the one thing that belongs beside it.
    ("/GUARD_REPLICA", 11.05, 83.40, 0.25, 0.15),
    ("/GUARD_REPLICA", 12.15, 83.40, 0.25, 0.15),
    ("/GUARD_REPLICA", 11.05, 89.60, 0.25, 0.15),
    ("/GUARD_REPLICA", 12.15, 89.60, 0.25, 0.15),
    ("/HEATER_LOW", 17.80, 104.60, 0.45, 0.25),
    ("/+12V_HTR", 2.20, 104.40, 0.45, 0.25),
    ("/+12V_HTR", 12.25, 103.75, 0.45, 0.25),
)


def _point(x: float, y: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN_X_MM + x),
                           pcbnew.FromMM(ORIGIN_Y_MM + y))


def stackup_block() -> str:
    """The `(stackup ...)` s-expression for STACKUP, tab-indented for `(setup`."""
    lines = ["\t\t(stackup"]
    for name, kind, thickness, material in STACKUP:
        lines.append(f'\t\t\t(layer "{name}"')
        lines.append(f'\t\t\t\t(type "{kind}")')
        lines.append(f"\t\t\t\t(thickness {thickness})")
        if material is not None:
            lines.append(f'\t\t\t\t(material "{material}")')
            lines.append("\t\t\t\t(epsilon_r 4.3)")
            lines.append("\t\t\t\t(loss_tangent 0.02)")
        lines.append("\t\t\t)")
    for name, side in (("F.SilkS", "Top Silk Screen"), ("F.Paste", "Top Solder Paste"),
                       ("B.Paste", "Bottom Solder Paste"), ("B.SilkS", "Bottom Silk Screen")):
        lines.append(f'\t\t\t(layer "{name}"')
        lines.append(f'\t\t\t\t(type "{side}")')
        lines.append("\t\t\t)")
    lines.append(f'\t\t\t(copper_finish "{COPPER_FINISH}")')
    lines.append("\t\t\t(dielectric_constraints no)")
    lines.append("\t\t)")
    return "\n".join(lines) + "\n"


def write_stackup(path) -> None:
    """Insert the fabrication stack into a saved board file.

    This is a text edit and not an API call because KiCad 9's Python bindings
    expose `GetStackupDescriptor()` as an opaque SwigPyObject with no methods,
    and setting `m_HasStackup` alone emits nothing.  A board saved without this
    reaches the fab with a layer count and no layer thicknesses, no dielectric
    and no surface finish, which is what `audit_pcb.py`'s STACKUP guard caught
    on the first regenerated Rev-B board.

    pcbnew PRESERVES a stackup it did not create across load/save, so this only
    has to run once, in the generator; the router and the repair pass carry it
    forward.  Verified by reloading the file afterwards.
    """
    path = Path(path)
    text = path.read_text()
    if "(stackup" in text:
        return
    anchor = "\n\t(setup\n"
    if text.count(anchor) != 1:
        raise SystemExit(f"expected exactly one '(setup' block in {path}, "
                         f"found {text.count(anchor)}")
    at = text.index(anchor) + len(anchor)
    path.write_text(text[:at] + stackup_block() + text[at:])
    if pcbnew.LoadBoard(str(path)) is None:
        raise SystemExit(f"{path} does not parse after writing the stackup")
    written = path.read_text()
    for token in ('(stackup', f'(copper_finish "{COPPER_FINISH}")'):
        if token not in written:
            raise SystemExit(f"stackup write produced no {token} in {path}")


def ensure_gnd_plane(board):
    """Pour ground on every outer copper layer over the whole outline.

    This was a single In2 plane while the board had four layers.  With two,
    ground has to live on F.Cu and B.Cu alongside the signals, so it is poured
    on both and yields to the heater spreader by priority where they overlap.

    The thermal rule area removes it across y=83..85 exactly as it removes
    every other pour; `ensure_gnd_bridge` carries continuity across that gap on
    one explicit 0.15 mm trace in the left edge web.
    """
    net = board.FindNet("/GND")
    if net is None:
        raise SystemExit("/GND net is missing")
    layers = copper_layers(board)
    if not layers:
        raise SystemExit("board has no enabled copper layers")
    made = []
    for layer in layers:
        name = f"{GND_PLANE_NAME}_{board.GetLayerName(layer).replace('.', '')}"
        zone = _one_named_zone(board, name)
        zone.SetZoneName(name)
        zone.SetIsRuleArea(False)
        zone.SetLayer(layer)
        zone.SetNet(net)
        zone.SetAssignedPriority(GND_PLANE_PRIORITY)
        zone.SetLocalClearance(pcbnew.FromMM(0.15))
        zone.SetMinThickness(pcbnew.FromMM(0.09))
        # Solid, not thermal relief.  Thermal spokes on this board's smallest
        # ground pads could not be drawn at the zone's minimum spoke width and
        # DRC reported five starved_thermal findings; a starved spoke is a
        # connection that exists in the connectivity model and not in copper.
        # Solid connections also serve a reference pour better, and nothing
        # here is reflow-mass-critical.
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.SetDoNotAllowTracks(False)
        zone.SetDoNotAllowVias(False)
        zone.SetDoNotAllowPads(False)
        zone.SetDoNotAllowZoneFills(False)
        zone.SetDoNotAllowFootprints(False)
        zone.Outline().RemoveAllContours()
        zone.AddPolygon(_polygon(GND_PLANE))
        made.append(zone)
    return made


def ensure_cell_re_via_keepout(board):
    """Forbid via barrels alongside the reference node, on every layer."""
    zone = _one_named_zone(board, CELL_RE_KEEPOUT_NAME)
    zone.SetZoneName(CELL_RE_KEEPOUT_NAME)
    zone.SetIsRuleArea(True)
    layers = pcbnew.LSET()
    for layer in copper_layers(board):
        layers.AddLayer(layer)
    zone.SetLayerSet(layers)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(False)
    zone.SetDoNotAllowFootprints(False)
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(_polygon(CELL_RE_KEEPOUT))
    return zone


def add_critical_routes(board):
    """Emit the authored copper, locked, and fail if a target net is absent."""
    made = []
    for netname, layer, width, points in CRITICAL_TRACKS:
        net = board.FindNet(netname)
        if net is None:
            raise SystemExit(f"critical route references missing net {netname}")
        for start, end in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(net)
            track.SetLayer(layer)
            track.SetWidth(pcbnew.FromMM(width))
            track.SetStart(_point(*start))
            track.SetEnd(_point(*end))
            track.SetLocked(True)
            board.Add(track)
            made.append(track)
    for netname, x, y, size, drill in CRITICAL_VIAS:
        net = board.FindNet(netname)
        if net is None:
            raise SystemExit(f"critical via references missing net {netname}")
        via = pcbnew.PCB_VIA(board)
        via.SetNet(net)
        via.SetPosition(_point(x, y))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.FromMM(size))
        via.SetDrill(pcbnew.FromMM(drill))
        via.SetLocked(True)
        board.Add(via)
        made.append(via)
    return made
