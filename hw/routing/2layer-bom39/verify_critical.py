#!/usr/bin/env python3
"""Assert that a routed board still contains every authored critical route.

`critical_routes.py` emits its copper LOCKED, on the assumption that a router
will route around locked geometry rather than through it.  That assumption is
false in at least one case, measured 2026-09-05: invoked with
`--rip-existing-nets '*'`, KiCadRoutingTools deleted all seven authored
GUARD_REPLICA segments and all four of its vias and re-routed the net from
scratch, while its own JSON summary reported other nets as `protected_skipped
... "locked"`.  The lock is honoured on some code paths and not others, and a
flag whose effect you cannot see is not a protection.

So this checks the board instead of trusting the flag.  It compares the copper
`critical_routes.py` says it authored against what is actually on the board,
by geometry, and fails naming what is missing.  Run it after every routing
pass, before anything downstream believes the board.

`--expect-locked` additionally requires each survivor to still carry the locked
flag, which catches a router that preserved the copper but cleared the bit.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

try:
    if "pcbnew" not in sys.modules:
        import wx

        _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from critical_routes import (CORRIDOR_SPINE_TRACKS, CORRIDOR_SPINE_VIAS,
                             CRITICAL_TRACKS, CRITICAL_VIAS,
                             DENSE_ESCAPE_TRACKS, DENSE_ESCAPE_VIAS,
                             ROW_LOCAL_TRACKS)
from thermal_design import ORIGIN_X_MM, ORIGIN_Y_MM

HERE = Path(__file__).resolve().parent
TOLERANCE = 0.001
# A guard rail sits 0.275 mm off the run by design; anything beyond this is not
# guarding it.
GUARD_REACH = 0.60
# Nearest foreign copper allowed anywhere on CELL_RE, guarded or not.  The DRC
# rule is 0.15 mm and says nothing about leakage; this is the surface-leakage
# floor.  Across 0.25 mm of masked FR-4 at 3.3 V a clean board leaks on the
# order of 10 pA against the LMP91000's 900 pA budget, so 0.25 mm is defensible
# and 0.15 mm is not.  Rev A shipped a /HEATER_PWM turn at 0.252 mm and
# ROUTING.md flagged it as the closest a switching net comes to the node.
CELL_RE_MIN_APPROACH = 0.25


def mm(value) -> float:
    return round(pcbnew.ToMM(value), 4)


def absolute(x: float, y: float) -> tuple[float, float]:
    return round(ORIGIN_X_MM + x, 4), round(ORIGIN_Y_MM + y, 4)


def near(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= TOLERANCE and abs(a[1] - b[1]) <= TOLERANCE


def _segment_distance(a0, a1, b0, b1) -> float:
    """Shortest distance between two 2-D segments."""
    def sub(p, q): return (p[0] - q[0], p[1] - q[1])
    def dot(p, q): return p[0] * q[0] + p[1] * q[1]

    def point_seg(p, s0, s1) -> float:
        d = sub(s1, s0)
        length = dot(d, d)
        if length == 0.0:
            return dot(sub(p, s0), sub(p, s0)) ** 0.5
        t = max(0.0, min(1.0, dot(sub(p, s0), d) / length))
        near = (s0[0] + t * d[0], s0[1] + t * d[1])
        return dot(sub(p, near), sub(p, near)) ** 0.5

    # Segments that cross have distance zero; otherwise the minimum is attained
    # at one of the four endpoint-to-segment distances.
    d1, d2 = sub(a1, a0), sub(b1, b0)
    denom = d1[0] * d2[1] - d1[1] * d2[0]
    if denom != 0.0:
        t = ((b0[0] - a0[0]) * d2[1] - (b0[1] - a0[1]) * d2[0]) / denom
        u = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return 0.0
    return min(point_seg(a0, b0, b1), point_seg(a1, b0, b1),
               point_seg(b0, a0, a1), point_seg(b1, a0, a1))


def edge_gap(one, other) -> float:
    """Copper-edge-to-copper-edge distance between two straight tracks, in mm.

    KiCad's SHAPE::Distance takes a point, not another shape, so there is no
    one-call way to ask this from Python.  Every track here is a straight
    segment, so the capsule-to-capsule distance is the centreline distance less
    both half-widths.
    """
    a0 = (mm(one.GetStart().x), mm(one.GetStart().y))
    a1 = (mm(one.GetEnd().x), mm(one.GetEnd().y))
    b0 = (mm(other.GetStart().x), mm(other.GetStart().y))
    b1 = (mm(other.GetEnd().x), mm(other.GetEnd().y))
    centre = _segment_distance(a0, a1, b0, b1)
    return centre - mm(one.GetWidth()) / 2.0 - mm(other.GetWidth()) / 2.0


def expected(essential_only: bool = False) -> tuple[list, list]:
    tracks = []
    track_prefix = (len(DENSE_ESCAPE_TRACKS) + len(ROW_LOCAL_TRACKS)
                    + len(CORRIDOR_SPINE_TRACKS))
    via_prefix = len(DENSE_ESCAPE_VIAS) + len(CORRIDOR_SPINE_VIAS)
    selected_tracks = CRITICAL_TRACKS[track_prefix:] if essential_only else CRITICAL_TRACKS
    selected_vias = CRITICAL_VIAS[via_prefix:] if essential_only else CRITICAL_VIAS
    for netname, layer, width, points in selected_tracks:
        for start, end in zip(points, points[1:]):
            tracks.append((netname, layer, round(width, 4),
                           frozenset((absolute(*start), absolute(*end)))))
    vias = [(netname, absolute(x, y), round(size, 4), round(drill, 4))
            for netname, x, y, size, drill in selected_vias]
    return tracks, vias


def check(board_path: Path, expect_locked: bool, essential_only: bool = False) -> list[str]:
    board = pcbnew.LoadBoard(str(board_path))
    want_tracks, want_vias = expected(essential_only)
    problems = []

    have_tracks = []
    have_vias = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            have_vias.append(item)
        else:
            have_tracks.append(item)

    for netname, layer, width, ends in want_tracks:
        match = None
        for item in have_tracks:
            if item.GetNetname() != netname or item.GetLayer() != layer:
                continue
            if abs(mm(item.GetWidth()) - width) > TOLERANCE:
                continue
            actual = (mm(item.GetStart().x), mm(item.GetStart().y))
            other = (mm(item.GetEnd().x), mm(item.GetEnd().y))
            pair = list(ends)
            if ((near(actual, pair[0]) and near(other, pair[1]))
                    or (near(actual, pair[1]) and near(other, pair[0]))):
                match = item
                break
        if match is None:
            problems.append(
                f"MISSING track {netname} on {board.GetLayerName(layer)} "
                f"{width} mm {sorted(ends)}")
        elif expect_locked and not match.IsLocked():
            problems.append(
                f"UNLOCKED track {netname} on {board.GetLayerName(layer)} "
                f"{sorted(ends)}")

    for netname, position, size, drill in want_vias:
        match = None
        for item in have_vias:
            if item.GetNetname() != netname:
                continue
            if not near((mm(item.GetPosition().x), mm(item.GetPosition().y)), position):
                continue
            # PCB_VIA::GetWidth() asserts without a layer argument in KiCad 9.
            if abs(mm(item.GetWidth(pcbnew.F_Cu)) - size) > TOLERANCE:
                continue
            if abs(mm(item.GetDrill()) - drill) > TOLERANCE:
                continue
            match = item
            break
        if match is None:
            problems.append(f"MISSING via {netname} at {position} {size}/{drill}")
        elif expect_locked and not match.IsLocked():
            problems.append(f"UNLOCKED via {netname} at {position}")

    # CELL_RE's whole point is that it has no via barrel anywhere on the net,
    # not merely that the authored segments survived.
    stray = [(mm(v.GetPosition().x), mm(v.GetPosition().y))
             for v in have_vias if v.GetNetname() == "/CELL_RE"]
    if stray:
        problems.append(f"CELL_RE carries via(s) at {stray}; it must have none")
    off_layer = sorted({board.GetLayerName(t.GetLayer()) for t in have_tracks
                        if t.GetNetname() == "/CELL_RE"} - {"F.Cu"})
    if off_layer:
        problems.append(f"CELL_RE has copper on {off_layer}; it must be F.Cu only")

    # The guard's job is to be the NEAREST thing to CELL_RE along the stretch
    # it guards.  A rail that survives while some other net has been squeezed in
    # between guards nothing, and neither the inventory above nor DRC would say
    # so -- DRC is happy at 0.15 mm whoever the neighbour is.
    #
    # Scoped to y=83.40..89.60, the band the rails actually cover.  CELL_RE's
    # approach to U7 and its detour to U4 are deliberately unguarded, and a
    # whole-net version of this check would fail on them by construction.
    #
    # It fails when there is no guard copper in the band at all, not just when
    # foreign copper is nearer.  The first version compared "nearest guard"
    # against "nearest foreign" and SKIPPED when nearest-guard was None -- so
    # deleting every rail made it pass, which is the exact shape of a check
    # that treats unevaluable input as OK.
    band = (133.40, 139.60)

    def clipped(track):
        """The part of a track inside the guarded band, or None."""
        (x0, y0) = (mm(track.GetStart().x), mm(track.GetStart().y))
        (x1, y1) = (mm(track.GetEnd().x), mm(track.GetEnd().y))
        if y0 == y1:
            return ((x0, y0), (x1, y1)) if band[0] <= y0 <= band[1] else None
        lo, hi = sorted((y0, y1))
        if hi < band[0] or lo > band[1]:
            return None
        def at(y):
            t = (y - y0) / (y1 - y0)
            return (x0 + t * (x1 - x0), y)
        return (at(max(lo, band[0])), at(min(hi, band[1])))

    re_tracks = [t for t in have_tracks if t.GetNetname() == "/CELL_RE"]

    # 1. Is the guard the nearest copper along the stretch it covers?  Measured
    #    on the CLIPPED segment: CELL_RE crosses the band in one segment running
    #    from y=133.10 to y=140.06, and comparing along its whole length
    #    reported an /I2C_SCL track at y=90.3 -- ABOVE the rails, on the
    #    deliberately unguarded approach to the cell land -- as though the guard
    #    had been undercut inside the band.  Right to fire, wrong reason.
    nearest_guard = None
    nearest_foreign = None
    for track in re_tracks:
        piece = clipped(track)
        if piece is None:
            continue
        layer = track.GetLayer()
        half = mm(track.GetWidth()) / 2.0
        for other in have_tracks:
            if other is track or other.GetLayer() != layer:
                continue
            name = other.GetNetname()
            if name == "/CELL_RE":
                continue
            gap = round(_segment_distance(
                piece[0], piece[1],
                (mm(other.GetStart().x), mm(other.GetStart().y)),
                (mm(other.GetEnd().x), mm(other.GetEnd().y)))
                - half - mm(other.GetWidth()) / 2.0, 4)
            if name == "/GUARD_REPLICA":
                nearest_guard = gap if nearest_guard is None else min(nearest_guard, gap)
            elif nearest_foreign is None or gap < nearest_foreign[0]:
                nearest_foreign = (gap, name)
    if re_tracks and any(clipped(t) for t in re_tracks):
        if nearest_guard is None or nearest_guard > GUARD_REACH:
            problems.append(
                f"no GUARD_REPLICA copper within {GUARD_REACH} mm of CELL_RE "
                f"between y={band[0]} and y={band[1]}"
                + (f" (nearest guard {nearest_guard} mm)" if nearest_guard else ""))
        elif nearest_foreign is not None and nearest_foreign[0] < nearest_guard:
            gap, name = nearest_foreign
            problems.append(
                f"inside the guarded band, {name} is {gap} mm from CELL_RE, "
                f"closer than the guard at {nearest_guard} mm")

    # 2. And how close does anything foreign get to CELL_RE ANYWHERE?  The
    #    approach to the cell land and the detour to U4 carry no rails by
    #    design, and DRC scores them at 0.15 mm like any other copper.
    closest = None
    for track in re_tracks:
        layer = track.GetLayer()
        for other in have_tracks:
            if other is track or other.GetLayer() != layer:
                continue
            if other.GetNetname() in ("/CELL_RE", "/GUARD_REPLICA"):
                continue
            gap = round(edge_gap(track, other), 4)
            if closest is None or gap < closest[0]:
                closest = (gap, other.GetNetname())
    if closest is not None and closest[0] < CELL_RE_MIN_APPROACH:
        problems.append(
            f"{closest[1]} comes within {closest[0]} mm of CELL_RE "
            f"(floor {CELL_RE_MIN_APPROACH} mm); DRC allows it at 0.15 mm and "
            "scores no leakage")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", nargs="?",
                        default=os.environ.get("O2_PCB_IN",
                                               str(HERE / "o2-probe.kicad_pcb")))
    parser.add_argument("--expect-locked", action="store_true",
                        help="also require the surviving copper to still be locked")
    parser.add_argument("--essential-only", action="store_true",
                        help="check only leakage/guard/heater routes, excluding router-assist copper")
    args = parser.parse_args()

    problems = check(Path(args.board), args.expect_locked, args.essential_only)
    want_tracks, want_vias = expected(args.essential_only)
    total = len(want_tracks) + len(want_vias)
    if problems:
        print(f"FAIL: {len(problems)} of {total} authored critical item(s) "
              f"wrong in {args.board}")
        for problem in problems:
            print(f"  - {problem}")
        # Two severities, because they mean different things to a caller.
        # Exit 2: authored copper is MISSING, UNLOCKED, or CELL_RE has grown a
        # via -- the board has lost a design decision and no later step can
        # recover it, so a routing loop must stop.
        # Exit 1: everything is present but something has crowded CELL_RE.
        # That is a real defect and the board must not ship, but it is a
        # property of the routed copper AROUND the authored set, and the next
        # routing pass can fix it.  Aborting a twelve-pass loop over a 15 um
        # shortfall on one plane strap throws away the other eleven.
        structural = any(p.startswith(("MISSING", "UNLOCKED"))
                         or "must have none" in p or "must be F.Cu only" in p
                         for p in problems)
        return 2 if structural else 1
    print(f"OK: all {total} authored critical item(s) present in {args.board}"
          + (" and locked" if args.expect_locked else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
