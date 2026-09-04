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

NOT owned here, and deliberately: the GUARD_REPLICA driven-guard zone.  On
Rev A that was a separate migration (`repair_guard_fill.py`) because the rule
area and CELL_RE itself split the pour into four regions that need individual
feeds, and every feed competes for In1 in the same 5 mm neck the signals cross.
Authoring it needs its own pass against a routed board, not a guess before one.
Until it lands, CELL_RE on this revision is an unguarded run.
"""

from __future__ import annotations

import pcbnew

from thermal_design import ORIGIN_X_MM, ORIGIN_Y_MM, _polygon, _one_named_zone


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
CELL_RE_KEEPOUT = ((10.55, 81.20), (11.45, 81.20), (11.45, 82.65),
                   (12.55, 83.75), (12.55, 91.40), (11.65, 91.40),
                   (11.65, 83.95), (10.55, 82.85))

GND_PLANE_NAME = "GND_PLANE_IN2"
GND_PLANE = ((0.0, 0.0), (20.0, 0.0), (20.0, 107.0), (0.0, 107.0))

F = pcbnew.F_Cu
IN1 = pcbnew.In1_Cu
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
    ("/CELL_RE", F, 0.25, ((12.54, 91.00), (12.10, 90.56), (12.10, 83.60),
                           (11.00, 82.50), (11.00, 81.40))),
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
    # The In1 crossing runs at y=104.40, not straight west at 103.75: at 103.75
    # the 0.60 mm feed sat directly under U10's south pad row (y=103.275..103.725)
    # and walled off its In1 escape -- the router then left /I2C_SDA open at
    # U10 pad 6.  0.375 mm of clearance below that row is enough for both.
    ("/+12V_HTR", IN1, 0.60, ((12.25, 103.75), (11.60, 104.40),
                              (2.20, 104.40))),
    ("/+12V_HTR", B, 0.60, ((2.20, 104.40), (2.20, 105.50))),
    ("/+12V_HTR", F, 0.60, ((2.20, 104.40), (2.20, 105.50))),
)

# (net, x, y, size_mm, drill_mm).  Both of these are the fork-tip layer joins:
# each finger is an F.Cu land and a B.Cu land at the same coordinate, and
# nothing in the footprint connects them.
CRITICAL_VIAS = (
    ("/HEATER_LOW", 17.80, 104.60, 0.45, 0.25),
    ("/+12V_HTR", 2.20, 104.40, 0.45, 0.25),
    ("/+12V_HTR", 12.25, 103.75, 0.45, 0.25),
)


def _point(x: float, y: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN_X_MM + x),
                           pcbnew.FromMM(ORIGIN_Y_MM + y))


def ensure_gnd_plane(board):
    """Pour In2 as a solid ground plane over the whole outline.

    The thermal rule area removes it across y=83..85 exactly as it removes
    every other pour; `ensure_gnd_bridge` carries continuity across that gap on
    one explicit 0.15 mm trace in the left edge web.
    """
    net = board.FindNet("/GND")
    if net is None:
        raise SystemExit("/GND net is missing")
    zone = _one_named_zone(board, GND_PLANE_NAME)
    zone.SetZoneName(GND_PLANE_NAME)
    zone.SetIsRuleArea(False)
    zone.SetLayer(pcbnew.In2_Cu)
    zone.SetNet(net)
    zone.SetLocalClearance(pcbnew.FromMM(0.15))
    zone.SetMinThickness(pcbnew.FromMM(0.09))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(False)
    zone.SetDoNotAllowFootprints(False)
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(_polygon(GND_PLANE))
    return zone


def ensure_cell_re_via_keepout(board):
    """Forbid via barrels alongside the reference node, on every layer."""
    zone = _one_named_zone(board, CELL_RE_KEEPOUT_NAME)
    zone.SetZoneName(CELL_RE_KEEPOUT_NAME)
    zone.SetIsRuleArea(True)
    layers = pcbnew.LSET()
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
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
