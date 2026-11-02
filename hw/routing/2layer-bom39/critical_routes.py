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
    high-impedance node CELL_RE is.  It is authored in full because it is what
    makes CELL_RE possible -- it dives to B.Cu and crosses underneath, which is
    the only way CELL_RE reaches U4 without a via.

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

# Repeatable radial escapes for every routed signal pad on the three dense
# packages.  They terminate beyond the owning courtyard (or at the legal board
# edge inset for U6's east row) and stay on F.Cu.  One-pad pseudo-nets, GND,
# exposed pads, and the separately authored critical nets are deliberately
# absent.  Generated by author_escapes.py from seed-baseline.kicad_pcb; the
# four-decimal coordinates preserve the exact 0.5/0.4 mm-pitch pad centres.
DENSE_ESCAPE_TRACKS = (
    ("/NRST", F, 0.18, ((18.6625, 42.7500), (19.7100, 42.7500))),
    ("/UART2_TX", F, 0.18, ((17.2500, 40.3375), (17.2500, 38.8050))),
    ("/UART2_RX", F, 0.18, ((16.7500, 40.3375), (16.7500, 38.8050))),
    ("/CE_MON", F, 0.18, ((16.2500, 40.3375), (16.2500, 38.8050))),
    ("/VIN_MON", F, 0.18, ((15.2500, 40.3375), (15.2500, 38.8050))),
    ("/VA_MON", F, 0.18, ((14.7500, 40.3375), (14.7500, 38.8050))),
    ("/AFE_MENB", F, 0.18, ((14.2500, 40.3375), (14.2500, 38.8050))),
    ("/ADC_DRDY", F, 0.18, ((13.7500, 40.3375), (13.7500, 38.8050))),
    ("/EXP_INT", F, 0.18, ((13.2500, 40.3375), (13.2500, 38.8050))),
    ("/HEATER_PWM", F, 0.18, ((10.3375, 43.2500), (8.8050, 43.2500))),
    ("/RS485_TX", F, 0.18, ((10.3375, 43.7500), (8.8050, 43.7500))),
    ("/RS485_DE", F, 0.18, ((10.3375, 44.2500), (8.8050, 44.2500))),
    ("/RS485_RX", F, 0.18, ((10.3375, 45.2500), (8.8050, 45.2500))),
    ("/SWDIO", F, 0.18, ((10.3375, 46.7500), (8.8050, 46.7500))),
    ("/SWCLK_BOOT0", F, 0.18, ((10.3375, 47.2500), (8.8050, 47.2500))),
    ("/3V3D", F, 0.18, ((18.6625, 45.7500), (19.7100, 45.7500))),
    ("/SWO", F, 0.18, ((14.2500, 48.6625), (14.2500, 50.1950))),
    ("/I2C_SCL", F, 0.18, ((15.7500, 48.6625), (15.7500, 50.1950))),
    ("/I2C_SDA", F, 0.18, ((16.2500, 48.6625), (16.2500, 50.1950))),
    ("/3V3D", F, 0.18, ((18.6625, 45.2500), (19.7100, 45.2500))),
    ("/3V3D", F, 0.18, ((18.6625, 44.7500), (19.7100, 44.7500))),
    ("/LMP_C1", F, 0.18, ((9.5000, 81.4000), (9.5000, 82.1000))),
    ("/VREF_TRIM", F, 0.18, ((10.0000, 81.4000), (9.9500, 81.7500))),
    ("/CELL_CE_DRV", F, 0.18, ((11.5000, 81.4000), (11.5000, 81.9950))),
    ("/AFE_MENB", F, 0.18, ((11.0000, 77.6000), (11.0000, 76.5050))),
    ("/I2C_SCL", F, 0.18, ((10.5000, 77.6000), (10.5000, 76.5050))),
    ("/I2C_SDA", F, 0.18, ((10.0000, 77.6000), (10.0000, 76.5050))),
    ("/3V3A", F, 0.18, ((9.0000, 77.6000), (9.0000, 76.5050))),
    ("/AFE_VOUT", F, 0.18, ((8.5000, 81.4000), (8.5000, 82.4950))),
    ("/LMP_C2", F, 0.18, ((9.0000, 81.4000), (9.0000, 82.1000))),
    ("/ADC_RESET", F, 0.18, ((14.0625, 76.2500), (12.8750, 76.2500))),
    ("/3V3A", F, 0.18, ((16.9375, 77.2500), (18.1750, 77.2500))),
    ("/3V3D", F, 0.18, ((16.9375, 76.7500), (18.1750, 76.7500))),
    ("/ADC_DRDY", F, 0.18, ((16.9375, 76.2500), (18.1750, 76.2500))),
    ("/I2C_SDA", F, 0.18, ((16.2500, 75.5625), (16.2500, 74.3250))),
    ("/I2C_SCL", F, 0.18, ((15.7500, 75.5625), (15.7500, 74.3250))),
    ("/ADC_RE_BUF", F, 0.18, ((14.0625, 77.7500), (12.8750, 77.7500))),
    ("/ADC_WE_BUF", F, 0.18, ((14.7500, 78.4375), (14.7500, 79.6750))),
    ("/VREF_TRIM", F, 0.18, ((15.7500, 78.4375), (15.7500, 79.6750))),
    ("/ADC_VREF_MON", F, 0.18, ((16.2500, 78.4375), (16.2500, 79.6750))),
    ("/ADC_AFE_VOUT", F, 0.18, ((16.9375, 77.7500), (18.1750, 77.7500))),
)

# Short B.Cu links whose topology is fixed by the standing passive rows.  They
# are emitted before global routing so a later unrelated trace cannot form a
# complete barrier between two pads only 1.75 mm apart.  Alternate part
# rotations in gen_pcb.PLACEMENT align the shared pads on the same row.
ROW_LOCAL_TRACKS = (
    ("/ADC_RE_BUF", B, 0.18,
     ((2.8500, 64.8250), (4.6000, 64.4800))),
    ("/ADC_AFE_VOUT", B, 0.18,
     ((6.3500, 64.8250), (8.1000, 64.4800))),
    ("/VREF_SHUNT", B, 0.18,
     ((9.8500, 64.8250), (11.6000, 64.7750), (13.3500, 64.8250))),
    ("/VREF_MON_RAW", B, 0.18,
     ((2.8500, 69.1750), (4.6000, 69.1750), (6.3500, 69.1750))),
    ("/ADC_VREF_MON", B, 0.18,
     ((6.3500, 70.8250), (8.1000, 70.4800))),
    ("/VA_MON", B, 0.18,
     ((9.8500, 70.8250), (11.6000, 70.8250))),
    ("/VIN_MON", B, 0.18,
     ((13.3500, 70.8250), (15.1000, 70.8250))),
    ("/CELL_CE_DRV", B, 0.18,
     ((4.8500, 76.6750), (6.6000, 76.6750))),
    ("/CE_MON", B, 0.18,
     ((6.6000, 78.3250), (8.3500, 78.3250), (10.1000, 77.9800))),
)

# Dense-package-to-passive-row trunks.  These are exact-shape-checked chords
# compacted from 0.1 mm A* paths on the otherwise unrouted board.  Owning the
# topology here prevents routine routes from walling off the U7/U8 dogbones;
# the companion passive-pair links above complete each destination island.
CORRIDOR_SPINE_TRACKS = (
    ("/LMP_C1", F, 0.09,
     ((9.5000, 82.1000), (8.8000, 83.0000), (8.4000, 83.1000),
      (8.0000, 82.8000), (7.3000, 81.6750))),
    ("/LMP_C2", F, 0.09,
     ((9.0000, 82.1000), (8.8000, 82.6000), (8.6000, 82.8000),
      (8.4000, 82.8000), (8.2000, 82.6000), (7.3000, 80.1250))),
    ("/CELL_CE_DRV", B, 0.09,
     ((11.5000, 81.9950), (11.2000, 78.9000), (10.5000, 77.5000),
      (8.3000, 77.5000), (6.6000, 76.6750))),
    ("/ADC_VREF_MON", B, 0.09,
     ((16.2500, 79.6750), (13.7000, 75.4000), (9.8000, 71.5000),
      (9.3000, 71.4000), (8.1000, 70.4800))),
    ("/ADC_RE_BUF", B, 0.09,
     ((12.8750, 77.7500), (11.3000, 77.2000), (7.0000, 74.1000),
      (5.6000, 71.0000), (5.7000, 70.4000), (6.6000, 69.8000),
      (6.9000, 69.7000), (7.1000, 69.4000), (7.0000, 68.7000),
      (5.7000, 67.0000), (4.6000, 64.4800))),
    ("/ADC_AFE_VOUT", B, 0.09,
     ((18.1750, 77.7500), (12.3000, 70.8000), (12.3000, 68.8000),
      (8.1000, 64.4800))),
    ("/ADC_RESET", F, 0.09,
     ((12.8750, 76.2500), (16.3000, 72.4000))),
    ("/ADC_RESET", B, 0.09,
     ((16.3000, 72.4000), (16.3250, 72.4000))),
)

# These closures are individually copper-clean on the unrouted seed, but
# keeping them as global-router obstacles regressed the independent result
# from 24 to 27 open connections.  Preserve the measured experiment without
# making it part of the best-known default seed.
SECONDARY_CLOSURE_TRACKS = (
    ("/RE_BUF", B, 0.09,
     ((2.8500, 63.1750), (2.1000, 64.6000), (1.9000, 66.9000),
      (1.9000, 72.7000), (2.5000, 73.3000), (3.1000, 76.6750),
      (3.1000, 76.7000))),
    ("/RE_BUF", F, 0.09,
     ((3.1000, 76.7000), (2.6750, 74.8875), (3.3250, 74.8875))),
    ("/WE_BUF", B, 0.09,
     ((13.6000, 76.6750), (12.1000, 76.0000), (11.2000, 76.0000))),
    ("/WE_BUF", F, 0.09,
     ((11.2000, 76.0000), (8.9000, 76.2000), (4.6000, 77.2000),
      (2.9000, 78.2000), (2.6750, 79.1125), (2.0250, 79.1125))),
    ("/CELL_CE", B, 0.09,
     ((4.8500, 78.3250), (3.2000, 77.5000))),
    ("/CELL_CE", F, 0.09,
     ((3.2000, 77.5000), (1.6000, 75.8000), (1.0000, 73.5000))),
    ("/HEATER_GATE", B, 0.09,
     ((12.6750, 101.2500), (12.7000, 101.2000))),
    ("/HEATER_GATE", F, 0.09,
     ((12.7000, 101.2000), (10.0000, 101.1000), (9.8000, 101.1000),
      (9.3500, 101.5500), (9.2000, 101.5000))),
    ("/HEATER_GATE", B, 0.09,
     ((9.2000, 101.5000), (9.0500, 100.3125), (7.3250, 101.2500))),
    ("/EXP_SDA", F, 0.09,
     ((14.5000, 62.3000), (12.2000, 60.8000), (4.1000, 60.8000),
      (3.9500, 60.9375))),
    ("/EXP_SDA", B, 0.09,
     ((3.9500, 60.9375), (3.4000, 57.9000), (3.1750, 57.5000))),
    ("/EXP_SCL", F, 0.09,
     ((5.5000, 71.7000), (5.5000, 65.4000))),
    ("/EXP_SCL", B, 0.09,
     ((5.5000, 65.4000), (5.9000, 59.1000), (5.9750, 59.0000))),
    ("/EXP_SCL", F, 0.09,
     ((3.0000, 59.0625), (5.9750, 59.0000))),
    ("/EXP_TX", F, 0.09,
     ((11.5000, 71.7000), (10.9000, 64.1000))),
    ("/EXP_TX", B, 0.09,
     ((10.9000, 64.1000), (10.9500, 60.9375), (13.6750, 57.5000))),
    ("/EXP_INT_OUT", F, 0.09,
     ((8.5000, 71.7000), (10.8000, 73.2000), (12.2000, 73.2000),
      (12.4000, 73.0000), (12.6000, 62.0000))),
    ("/EXP_INT_OUT", B, 0.09,
     ((12.6000, 62.0000), (14.3000, 57.8000), (14.3000, 57.1000),
      (14.2000, 56.9000), (13.9000, 56.8000), (12.0000, 56.8000),
      (10.6750, 57.5000))),
    ("/EXP_INT_OUT", B, 0.09,
     ((12.6000, 62.0000), (12.6000, 61.8000), (12.9000, 61.5000),
      (16.2000, 60.7000))),
    ("/EXP_INT_OUT", F, 0.09,
     ((16.2000, 60.7000), (16.0500, 60.9375))),
    ("/I2C_SDA", F, 0.09,
     ((10.6500, 103.5000), (12.2000, 102.5000), (13.3000, 102.5000),
      (13.8000, 102.6000), (14.0000, 102.3000), (14.0000, 100.6000),
      (13.5000, 100.4000), (8.0000, 101.0000), (6.2000, 101.5000),
      (5.0000, 101.5000), (4.2000, 101.9000))),
)

# (net, layer, width_mm, [(x, y), ...])  -- board-local millimetres.
CRITICAL_TRACKS = DENSE_ESCAPE_TRACKS + ROW_LOCAL_TRACKS + CORRIDOR_SPINE_TRACKS + (
    # -- CELL_RE: U11 pad 2 (the cell's reference land) to U7 pin 13.  x=12.10
    # is the only column that clears both thermal slots: the right slot starts
    # at x=12.5, so the 0.25 mm trace edge sits 0.275 mm off it against a
    # 0.20 mm copper-to-edge rule.  Via-free by construction.  It steps to
    # x=11.00 inside the barrier and comes down on the pad from due north: the
    # first version cut the corner at 45 degrees and DRC caught it SHORTING
    # U7 pin 14 (/CELL_CE_DRV), which is 0.5 mm away on the same row.
    ("/CELL_RE", F, 0.25, ((12.54, 91.00), (11.60, 90.06), (11.60, 83.10),
                           (11.00, 82.50), (11.00, 81.40))),
    # The U4 leg, and the reason the whole AFE corner is authored rather than
    # routed.  U4 (the RE follower) is at x=3.97, and CELL_RE is FENCED from it:
    # CELL_WE lies west of CELL_RE at both ends -- pin 12 west of pin 13 at U7,
    # the centre land west of the east land at the cell -- so on F.Cu there is
    # no path west that does not cross CELL_WE.  There is no way round U7
    # either: U7 pin 15 is a 2.6 x 2.6 mm EXPOSED PAD filling the whole body
    # footprint, so the space between its two pin rows is copper, not a lane.
    #
    # The resolution is to let the OTHER electrode dive.  CELL_WE takes a via
    # pair and crosses underneath on B.Cu (below), leaving this leg a single
    # via-free F.Cu run.  That is the right way round: CELL_RE is the node
    # budgeted against the LMP91000's +/-900 pA input current, and a via barrel
    # is a leakage path through the laminate that no rule scores.  CELL_WE
    # carries the cell current into a transimpedance input and tolerates two.
    # It reaches U4 by going EAST around U7 and back along y=74.89, under the
    # whole AFE.  West is not available at any y: CELL_WE's branch to the cell
    # runs x=10.40..10.00 from y=81.4 to y=91 and fences everything, and the
    # only gap in that fence is below U7 -- which this leg uses.  The detour is
    # 9 mm longer than a via would be and worth every millimetre.
    #
    # The north-south leg is at x=12.40, hard against the west side of the
    # corridor.  This is the single most consequential number in the file.
    #
    # U8 is a WQFN-16 on 0.5 mm pitch: four pads per side, and on two layers
    # with no inner layer and gaps too small for a via, every one of them must
    # fan out SIDEWAYS on F.Cu.  Its west pad row begins at x=13.62.  At
    # x=13.00 this leg left those four pads 0.495 mm to escape into, and the
    # router reported `endpoint cell blocked` for U8 pads 9..13 and
    # boxed_in_static on six nets -- NINE of the fifteen nets that would not
    # route were U8 pads.  At 12.40 the corridor is 1.095 mm, which takes the
    # two signal escapes (pads 2 and 3 are GND and reach the pour).
    #
    # Moving it the other way, to 13.50, was tried first and SHORTED U8 pad 1:
    # that pad reaches x=13.62, not the 13.9 its centre suggested.  Pad
    # extents, not pad centres -- and the right direction was west all along.
    ("/CELL_RE", F, 0.25, ((11.00, 82.50), (12.40, 82.50), (12.40, 75.30),
                           (11.99, 74.89), (3.97, 74.89))),

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
    ("/GUARD_REPLICA", B, 0.30, ((10.885, 83.40), (12.15, 83.40))),
    ("/GUARD_REPLICA", B, 0.30, ((11.05, 89.60), (12.15, 89.60))),
    # One feed from R40's output pad, routed SOUTH of the U7/passive column
    # band.  The former y=79.35 B.Cu leg was an 8.7 mm wall across the AFE:
    # together with CELL_WE's B.Cu neck descent it boxed U7's gas-side row.
    # Fable's controlled n1 experiment measured this topology change as the
    # dominant routing lever.  The two requirements are unchanged: the feed
    # is authored before routing and the rails remain tied at both ends.
    #
    # This copy uses the original-placement R40 pad at (3.10, 78.325), then
    # drops below the passive row before heading east.  C17 occupies the
    # B.Cu lane at x=6.825..7.775.  The horizontal F.Cu bridge starts west of
    # C17 so the fourth north-south signal can pass C17 on B.Cu, and continues to
    # x=10.10, opening B.Cu beneath U7's whole south pad row instead of boxing
    # the LMP_C1/LMP_C2 pair against the package.  It stays above the thermal
    # slots and is horizontal, so it does not diagonally split the neck.  The
    # bridge also overlaps the aligned B.Cu doorway around x=8.00 through
    # CELL_WE's west branch.  CELL_WE is F.Cu in the neck; its branch via at
    # (10.45, 82.65) remains 0.185 mm copper-edge clear of the final vertical
    # guard leg.
    # Join the original-placement R40 pad to the TP5/guard-source branch at
    # (2.17, 77.00); the standing-column seed placed that pad at the branch
    # point, but the original placement does not.
    ("/GUARD_REPLICA", B, 0.25, ((2.17, 77.00), (2.17, 78.325),
                                 (3.10, 78.325), (3.10, 80.05),
                                 (4.50, 80.05), (4.50, 82.10))),
    ("/GUARD_REPLICA", F, 0.25, ((4.50, 82.10), (10.10, 82.10))),
    ("/GUARD_REPLICA", B, 0.25, ((10.10, 82.10), (10.885, 82.10),
                                 (10.885, 83.40))),
    # TP5 is on this net, and it has to be authored too or the net cannot be
    # kept away from the router.  Leaving just this leg to KRT was tried and is
    # worse than it sounds: with the rails absent during routing the router
    # fills their corridor with other nets, and putting the rails back
    # afterwards produced 32 shorts and 15 clearance violations.  A guard you
    # restore after the fact is not a guard.
    #
    # x=1.50 is the 0.84 mm lane between R38's two pads (they end at 1.08 and
    # begin at 1.92); a 0.25 mm track centred there clears both by 0.295 mm.
    ("/GUARD_REPLICA", B, 0.25, ((2.17, 77.00), (2.17, 73.50), (1.50, 72.83),
                                 (1.50, 66.30))),
    ("/GUARD_REPLICA", F, 0.25, ((1.50, 66.30), (1.00, 65.80), (1.00, 65.50))),
    # -- CELL_WE.  It leaves U7 in its own pin-12 COLUMN, not across the row:
    # U7's south row is on 0.5 mm pitch with 0.26 mm between pad edges, so
    # nothing fits between two pads and every pad escapes straight south or not
    # at all.  An earlier version cut west at y=82.40, sat on top of pin 11's
    # column, and the router reported /VREF_TRIM boxed_in_static at that pad.
    #
    # It stays on F.Cu from U7 to the cell.  This removes CELL_WE's B.Cu neck
    # wall while leaving CELL_RE's via-free F.Cu route and guard geometry
    # untouched.  CELL_WE still changes layer once for its west branch, which
    # is the crossing that lets CELL_RE reach U4 without a via.
    ("/CELL_WE", F, 0.20, ((10.50, 81.40), (10.50, 90.50), (10.00, 91.00))),
    # West on B.Cu at y=82.60, NOT 81.30.  At 81.30 it ran directly under U7's
    # gas-side pad row and walled it off: pins 8..11 (AFE_VOUT, LMP_C2, LMP_C1,
    # VREF_TRIM) are on the gas side of a package whose body is one big exposed
    # pad, so their only route to their cable-side partners is a via just south
    # of the row and then north underneath on B.Cu -- straight through where
    # this run was.  Four nets stayed open on that alone.  At 82.60 the escape
    # is clear and this still clears the thermal slot edge by 0.55 mm.
    # A matching 6.2 mm F.Cu bridge leaves B.Cu open on both sides of C17.
    # C17 blocks the nominal centre of the window, so the window must reach
    # west of its body as well as east of it to provide independent lanes.
    # an electrical relaxation: CELL_WE may use vias, and its only protected
    # role here is to keep CELL_RE via-free.  The doorway prevents the two
    # authored horizontal nets from becoming a topological cut for the paired
    # I2C routes through the thermal neck.
    ("/CELL_WE", B, 0.20, ((10.45, 82.65), (10.00, 82.65))),
    ("/CELL_WE", F, 0.20, ((10.00, 82.65), (3.80, 82.65))),
    ("/CELL_WE", B, 0.20, ((3.80, 82.65), (0.80, 82.65))),
    ("/CELL_WE", B, 0.20, ((3.33, 82.65), (3.33, 80.60))),
    ("/CELL_WE", F, 0.20, ((3.33, 80.60), (3.33, 79.11))),
    # The TP1 descent hugs the board edge at x=0.80 so the guard's own descent
    # to TP5 can have the x=1.50 lane between R38's two pads.  Both fit; only
    # one fits at x=1.30.
    ("/CELL_WE", B, 0.20, ((0.80, 82.65), (0.80, 71.00))),
    ("/CELL_WE", F, 0.20, ((0.80, 71.00), (1.00, 70.80), (1.00, 70.00))),

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

# The 0.5 mm/0.4 mm-pitch packages cannot accept ordinary 0.45 mm vias side by
# side.  These advanced-floor 0.25/0.15 mm dogbones sit at the validated fanout
# endpoints.  Without them KRT repeatedly reports the escaped pads as
# boxed-in: it can draw the F.Cu stub but cannot invent a legal layer change.
DENSE_ESCAPE_VIAS = (
    ("/VREF_TRIM", 9.9500, 81.7500, 0.25, 0.15),
    ("/CELL_CE_DRV", 11.5000, 81.9950, 0.25, 0.15),
    ("/ADC_RE_BUF", 12.8750, 77.7500, 0.25, 0.15),
    ("/ADC_VREF_MON", 16.2500, 79.6750, 0.25, 0.15),
    ("/ADC_AFE_VOUT", 18.1750, 77.7500, 0.25, 0.15),
    # The LMP compensation pair changes layer inside its B.Cu capacitor pads;
    # keeping the trunks on F.Cu leaves the B.Cu VREF escape corridor open.
    ("/LMP_C1", 7.3000, 81.6750, 0.25, 0.15),
    ("/LMP_C2", 7.3000, 80.1250, 0.25, 0.15),
)

CORRIDOR_SPINE_VIAS = (
    ("/ADC_RESET", 16.3000, 72.4000, 0.45, 0.25),
)

SECONDARY_CLOSURE_VIAS = (
    ("/RE_BUF", 3.1000, 76.7000, 0.45, 0.25),
    ("/WE_BUF", 11.2000, 76.0000, 0.45, 0.25),
    ("/CELL_CE", 3.2000, 77.5000, 0.45, 0.25),
    ("/HEATER_GATE", 12.7000, 101.2000, 0.45, 0.25),
    ("/HEATER_GATE", 9.2000, 101.5000, 0.45, 0.25),
    ("/EXP_SDA", 3.9500, 60.9375, 0.25, 0.15),
    ("/EXP_SCL", 5.5000, 65.4000, 0.45, 0.25),
    ("/EXP_SCL", 3.0000, 59.0625, 0.25, 0.15),
    ("/EXP_SCL", 5.9750, 59.0000, 0.25, 0.15),
    ("/EXP_TX", 10.9000, 64.1000, 0.45, 0.25),
    ("/EXP_INT_OUT", 12.6000, 62.0000, 0.45, 0.25),
    ("/EXP_INT_OUT", 16.2000, 60.7000, 0.45, 0.25),
)

# (net, x, y, size_mm, drill_mm).  The remaining entries are the authored
# critical-net layer joins.
CRITICAL_VIAS = DENSE_ESCAPE_VIAS + CORRIDOR_SPINE_VIAS + (
    # Guard rails to their B.Cu ties.  0.25/0.15, not 0.45/0.25: a 0.45 mm
    # barrel at x=12.15 would leave 0.125 mm to the right thermal slot against
    # a 0.20 mm copper-to-edge rule.  All four sit OUTSIDE CELL_RE_VIA_KEEPOUT,
    # which hugs the run at +/-0.30 mm; the keepout exists to keep foreign
    # barrels away from the reference node, and guard copper at the same
    # potential is the one thing that belongs beside it.
    ("/GUARD_REPLICA", 1.50, 66.30, 0.45, 0.25),
    ("/GUARD_REPLICA", 11.05, 83.40, 0.25, 0.15),
    ("/GUARD_REPLICA", 12.15, 83.40, 0.25, 0.15),
    ("/GUARD_REPLICA", 11.05, 89.60, 0.25, 0.15),
    ("/GUARD_REPLICA", 12.15, 89.60, 0.25, 0.15),
    ("/GUARD_REPLICA", 4.50, 82.10, 0.25, 0.15),
    ("/GUARD_REPLICA", 10.10, 82.10, 0.25, 0.15),
    # CELL_WE changes layer only for its west branch.  CELL_RE has none, by
    # construction.  The 0.25/0.15 via preserves the neck clearance.
    ("/CELL_WE", 10.45, 82.65, 0.25, 0.15),
    ("/CELL_WE", 10.00, 82.65, 0.25, 0.15),
    ("/CELL_WE", 3.80, 82.65, 0.25, 0.15),
    ("/CELL_WE", 3.33, 80.60, 0.45, 0.25),
    ("/CELL_WE", 0.80, 71.00, 0.45, 0.25),
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


BARRIER_WEB_KEEPOUT_NAME = "BARRIER_WEB_KEEPOUT"
# The right-hand thermal edge web, x=19.25..20.00 across the barrier.
#
# THERMAL-BARRIER.md's model treats the edge webs as bare FR-4 and inventories
# every copper crossing in the neck.  The router does not know that: it put
# /I2C_SCL through this web at x=19.5, which is four copper_edge_clearance
# violations (0.35 mm of usable width against a 0.18 mm track needing 0.58 mm)
# AND a barrier crossing the thermal calculation never counted.
#
# Only the right web.  The LEFT web carries the GND bridge by design -- one
# 0.15 mm trace, the only thing keeping the two halves of the ground pour
# connected -- and a rule area cannot be made net-specific.
BARRIER_WEB_KEEPOUT = ((19.25, 82.90), (20.00, 82.90), (20.00, 85.10),
                       (19.25, 85.10))

GND_STITCH_PITCH = 6.0
GND_STITCH_CLEARANCE = 0.65


def ensure_barrier_web_keepout(board):
    """Keep routed copper out of the right-hand thermal edge web."""
    zone = _one_named_zone(board, BARRIER_WEB_KEEPOUT_NAME)
    zone.SetZoneName(BARRIER_WEB_KEEPOUT_NAME)
    zone.SetIsRuleArea(True)
    layers = pcbnew.LSET()
    for layer in copper_layers(board):
        layers.AddLayer(layer)
    zone.SetLayerSet(layers)
    zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(True)
    zone.SetDoNotAllowFootprints(False)
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(_polygon(BARRIER_WEB_KEEPOUT))
    return zone


def ensure_gnd_stitches(board):
    """Tie the F.Cu and B.Cu ground pours together with through vias.

    On the four-layer board GND was one inner plane and needed no stitching.
    With two pours there is nothing joining them at all: KiCad reported
    GND_PLANE_FCu and GND_PLANE_BCu as UNCONNECTED ZONES on a fully routed
    board, which is a ground plane in name only -- return current would have to
    find its way through whatever incidental pad vias happen to exist.

    Positions are searched, not listed: a coarse grid, keeping any point that
    clears every pad and every board-edge feature (the outline, both thermal
    slots, both side slots and the cell aperture) by GND_STITCH_CLEARANCE.  A
    hardcoded list would have to be re-derived by hand after any placement
    change, and this board's placement is still moving.
    """
    net = board.FindNet("/GND")
    if net is None:
        raise SystemExit("/GND net is missing")

    pads = [pad for footprint in board.GetFootprints() for pad in footprint.Pads()]
    edges = [item for item in board.GetDrawings()
             if item.GetLayer() == pcbnew.Edge_Cuts]
    # Existing copper counts too, and must: this runs AFTER add_critical_routes
    # precisely so it can see it.  A via dropped on a track is silently
    # REASSIGNED to that track's net by KiCad -- a stitch at (1.00, 80.00)
    # landed on CELL_WE's B.Cu column, became a CELL_WE via, and showed up as
    # one dangling via rather than as the short it morally was.
    others = [t for t in board.GetTracks() if t.GetNetname() != "/GND"]
    reach = pcbnew.FromMM(GND_STITCH_CLEARANCE)

    def free(x: float, y: float) -> bool:
        here = _point(x, y)
        box = pcbnew.BOX2I(pcbnew.VECTOR2I(here.x - reach, here.y - reach),
                           pcbnew.VECTOR2I(2 * reach, 2 * reach))
        for pad in pads:
            if pad.GetBoundingBox().Intersects(box):
                return False
        for edge in edges:
            if edge.GetBoundingBox().Intersects(box):
                return False
        for item in others:
            if item.GetBoundingBox().Intersects(box):
                return False
        return True

    # Cable side only.  Gas-side B.Cu is the HEATER_LOW spreader, so there is
    # no ground pour there to stitch TO: the first version gridded the whole
    # board and DRC reported two of its vias dangling, which is exactly right --
    # they joined the F.Cu pour to a layer that carries a different net at that
    # point.  Ground on the island therefore lives on F.Cu alone and reaches the
    # cable side through the barrier bridge; that is a property of the two-layer
    # stack, not an oversight.
    made = []
    # These two otherwise-valid grid sites repeatedly land in isolated B.Cu
    # fill fragments after routing.  Independent refill+DRC measurement on
    # the best route improved 24 -> 22 opens when only these were omitted;
    # omitting every stitch was worse (23), so this is deliberately selective.
    rejected_island_sites = {(13.0, 56.0), (13.0, 68.0)}
    steps_x = int(20.0 / GND_STITCH_PITCH)
    steps_y = int(82.0 / GND_STITCH_PITCH)
    for ix in range(steps_x + 1):
        for iy in range(steps_y + 1):
            x = 1.0 + ix * GND_STITCH_PITCH
            y = 2.0 + iy * GND_STITCH_PITCH
            if ((x, y) in rejected_island_sites or x > 19.0 or y > 82.0
                    or not free(x, y)):
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetNet(net)
            via.SetPosition(_point(x, y))
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetWidth(pcbnew.FromMM(0.45))
            via.SetDrill(pcbnew.FromMM(0.25))
            via.SetLocked(True)
            board.Add(via)
            made.append(via)
    if not made:
        raise SystemExit("no free position found for a single ground stitch via")
    return made


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
