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

from critical_routes import CRITICAL_TRACKS, CRITICAL_VIAS
from thermal_design import ORIGIN_X_MM, ORIGIN_Y_MM

HERE = Path(__file__).resolve().parent
TOLERANCE = 0.001


def mm(value) -> float:
    return round(pcbnew.ToMM(value), 4)


def absolute(x: float, y: float) -> tuple[float, float]:
    return round(ORIGIN_X_MM + x, 4), round(ORIGIN_Y_MM + y, 4)


def near(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= TOLERANCE and abs(a[1] - b[1]) <= TOLERANCE


def expected() -> tuple[list, list]:
    tracks = []
    for netname, layer, width, points in CRITICAL_TRACKS:
        for start, end in zip(points, points[1:]):
            tracks.append((netname, layer, round(width, 4),
                           frozenset((absolute(*start), absolute(*end)))))
    vias = [(netname, absolute(x, y), round(size, 4), round(drill, 4))
            for netname, x, y, size, drill in CRITICAL_VIAS]
    return tracks, vias


def check(board_path: Path, expect_locked: bool) -> list[str]:
    board = pcbnew.LoadBoard(str(board_path))
    want_tracks, want_vias = expected()
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

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", nargs="?",
                        default=os.environ.get("O2_PCB_IN",
                                               str(HERE / "o2-probe.kicad_pcb")))
    parser.add_argument("--expect-locked", action="store_true",
                        help="also require the surviving copper to still be locked")
    args = parser.parse_args()

    problems = check(Path(args.board), args.expect_locked)
    want_tracks, want_vias = expected()
    total = len(want_tracks) + len(want_vias)
    if problems:
        print(f"FAIL: {len(problems)} of {total} authored critical item(s) "
              f"wrong in {args.board}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OK: all {total} authored critical item(s) present in {args.board}"
          + (" and locked" if args.expect_locked else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
