#!/usr/bin/env python3
"""Widen the revb-86-ring side thermal slots from 0.80 mm to 0.81 mm.

Why
---
AISLER mills nothing narrower than 1.8 mm and nibbles the rest, with a stated
**minimum non-plated slot width of 0.8 mm**. At exactly 0.80 mm these two slots
sat *on* that floor, with no allowance for the tolerance on a nibbled slot.
0.81 mm buys the margin for 5 um of FR-4 per wall.

What it does NOT change
-----------------------
Two things are held fixed, because both are load-bearing.

**The inboard walls stay at x = 101.60 and 118.40.** Each slot grows outward
only, toward the board edge. Growing them symmetrically was tried first and put
two short `/I2C_SCL` F.Cu segments at (101.95, 134.9) and (101.95, 134.8) at
0.2975 mm from the left slot's top cap against a 0.300 mm rule -- that copper
had only 0.0025 mm of margin to start with. Holding the island-side walls means
no clearance on the island changes at all, the 16.80 mm island width is
untouched, and the whole 10 um comes off the outer FR-4 rails, which thin from
0.80 mm to 0.79 mm and carry no copper.

**Y extents stay 121.0 to 135.0 mm.** Widening a stadium by growing its cap
radius would push the apex to 135.005 and eat into the 4.0 mm slot-to-tip bridge
that `routing/revb-86-ring/README.md` records as deliberately restored -- the
geometry the theta = 68 K/W measurement (aa6133d) was taken on. So the cap
centres move inward by 5 um instead and the length stays 14.0 mm.

How
---
The eight primitives are edited **in place, by uuid**. That matters: the ring
board's records are uuid-keyed (`verify_revb_86.records`), and
`verify_revb_86_ring.CHANGES` pins these very objects by uuid with their
before/after coordinates. Deleting and re-adding them would churn the uuids,
break every one of those pins and make a one-line geometry tweak look like eight
objects vanishing. So the pin table stays the source of truth and this script
just moves the points it names.

Idempotent: re-running on an already-widened board is a no-op.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import wx
    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

REPO = Path(__file__).resolve().parent.parent
BOARD = Path(os.environ.get(
    "O2_PCB", REPO / "routing" / "revb-86-ring" / "o2-probe.kicad_pcb"))

OLD_WIDTH = 0.80
NEW_WIDTH = 0.81

# Ring-board slot envelope. thermal_design.SIDE_THERMAL_SLOTS describes the
# older, longer board (16 mm slots centred at y=145); this is the shortened pair.
Y_LOW, Y_HIGH = 121.0, 135.0
INBOARD = {"LEFT": 101.60, "RIGHT": 118.40}   # held fixed
OUTWARD = {"LEFT": -1.0, "RIGHT": +1.0}

# uuid -> (slot, role). Roles: "inner"/"outer" walls, "low"/"high" end caps.
# These uuids are the accepted board's and are pinned in
# verify_revb_86_ring.CHANGES; keep the two tables in step.
PRIMITIVES = {
    "42ac7ba1-2d8f-5742-b9e2-9c37a33cdd71": ("LEFT", "outer"),
    "382a52b4-f2a3-57b7-ae91-549ae3cc41c4": ("LEFT", "inner"),
    "826fb8e5-68d2-5b9d-8011-b8689e3de374": ("LEFT", "high"),
    "fc3c2def-8e7c-59d9-9699-dc0a5922f1bf": ("LEFT", "low"),
    "f9a48ad8-9dfb-512d-ae28-f18979bb171c": ("RIGHT", "outer"),
    "18318814-42c6-5733-80e9-5695c30bd779": ("RIGHT", "inner"),
    "7e81c88a-a270-5856-8a2f-65865eda73a3": ("RIGHT", "high"),
    "120616ce-a72a-51c2-b22c-b08c0d1bc5d8": ("RIGHT", "low"),
}


def geometry(width: float) -> dict:
    """Target points per uuid for a given slot width, inboard walls fixed."""
    out = {}
    radius = width / 2.0
    for uid, (slot, role) in PRIMITIVES.items():
        inner = INBOARD[slot]
        outer = round(inner + OUTWARD[slot] * width, 4)
        centre = round((inner + outer) / 2.0, 4)
        low, high = round(Y_LOW + radius, 4), round(Y_HIGH - radius, 4)
        if role == "outer":
            out[uid] = ((outer, low), None, (outer, high))
        elif role == "inner":
            out[uid] = ((inner, high), None, (inner, low))
        elif role == "high":
            out[uid] = ((inner, high), (centre, Y_HIGH), (outer, high))
        else:
            out[uid] = ((outer, low), (centre, Y_LOW), (inner, low))
    return out


def mm(point):
    return pcbnew.VECTOR2I_MM(point[0], point[1])


def orient(target, current):
    """Match a target triple to the direction the board already stores.

    The two slots are mirror images, and the generator walked each contour in
    the same rotational sense, so the right-hand primitives run start-to-end
    opposite to the left-hand ones. Rather than encode that per slot, keep
    whichever direction the object already has: an Edge.Cuts contour is
    direction-agnostic, but rewriting it backwards would churn the coordinates
    in CHANGES for no reason.
    """
    start, mid, end = target
    def near(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    if near(start, current[0]) > near(end, current[0]):
        return (end, mid, start)
    return target


def read(shape):
    def pt(v):
        return (round(v.x / 1e6, 4), round(v.y / 1e6, 4))
    mid = pt(shape.GetArcMid()) if shape.GetShapeStr() == "Arc" else None
    return (pt(shape.GetStart()), mid, pt(shape.GetEnd()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=str(BOARD))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    board = pcbnew.LoadBoard(args.board)
    shapes = {}
    for item in board.Drawings():
        uid = item.m_Uuid.AsString()
        if uid in PRIMITIVES:
            shapes[uid] = item
    missing = sorted(set(PRIMITIVES) - set(shapes))
    if missing:
        sys.exit("thermal-slot primitives missing from the board: %r" % missing)

    have = {uid: read(shapes[uid]) for uid in PRIMITIVES}
    want = {uid: orient(t, have[uid]) for uid, t in geometry(NEW_WIDTH).items()}
    before = {uid: orient(t, have[uid]) for uid, t in geometry(OLD_WIDTH).items()}
    if have == want:
        print("already %.2f mm -- nothing to do" % NEW_WIDTH)
        return 0
    if have != before:
        for uid in sorted(PRIMITIVES):
            if have[uid] != before[uid]:
                print("  %s expected %r, found %r" % (uid, before[uid], have[uid]))
        sys.exit("slots are not the pinned %.2f mm geometry -- refusing to guess"
                 % OLD_WIDTH)

    print("widening both side thermal slots %.2f -> %.2f mm, outward only "
          "(inboard walls x=%.2f/%.2f and Y %.1f..%.1f unchanged)"
          % (OLD_WIDTH, NEW_WIDTH, INBOARD["LEFT"], INBOARD["RIGHT"], Y_LOW, Y_HIGH))
    if args.dry_run:
        return 0

    for uid, (start, mid, end) in want.items():
        shape = shapes[uid]
        if mid is None:
            shape.SetStart(mm(start))
            shape.SetEnd(mm(end))
        else:
            shape.SetArcGeometry(mm(start), mm(mid), mm(end))

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(args.board, board)

    check = pcbnew.LoadBoard(args.board)
    got = {i.m_Uuid.AsString(): read(i) for i in check.Drawings()
           if i.m_Uuid.AsString() in PRIMITIVES}
    want = {uid: orient(t, got[uid]) for uid, t in geometry(NEW_WIDTH).items()}
    if got != want:
        sys.exit("wrote the board but it does not read back as expected")
    print("saved %s" % args.board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
