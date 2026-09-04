#!/usr/bin/env python3
"""Deterministic post-route cleanup of KiCadRoutingTools grid artefacts.

KRT routes on its own grid (0.05 or 0.1 mm) and places vias on that grid, so a
handful of accepted paths end a fraction of a millimetre off the centre of the
via they land on, and the occasional micro-stub is left behind.  KiCad accepts
both electrically -- the connectivity model joins them -- and reports them as
manufacturing-review findings: `track_not_centered_on_via` and `track_dangling`.

This is the Rev-B replacement for `repair_route_endpoints.py`, which was keyed
by track UUID against one specific accepted Rev-A route and cannot survive a
re-route.  This one is keyed by geometry instead, so it is idempotent and
re-runnable, and it is deliberately narrow:

  * it is driven BY THE DRC REPORT, not by a proximity sweep of the board.  The
    first version snapped any endpoint within 0.35 mm of a same-net via and
    moved 393 of them to fix 28 findings -- dragging endpoints that were
    already correctly anchored somewhere else, and producing 10 clearance
    violations, 8 crossing tracks and a short that were not there before.  DRC
    caught it, which is the only reason this note can be written honestly.
    Now the report names the via, and only endpoints of that via's own net,
    within SNAP_MAX of that via, and not already anchored on something else,
    are allowed to move.
  * a track is deleted ONLY if DRC called it dangling, it is shorter than
    STUB_MAX, and one of its endpoints still touches nothing after snapping.
  * locked copper (everything critical_routes.py authored) is never touched.

It fixes the report by moving the copper, not by changing what is reported.
Run KiCad's DRC afterwards: this script makes no claim of its own.
"""

from __future__ import annotations

import os
from pathlib import Path
import json
import sys

try:
    if "pcbnew" not in sys.modules:
        import wx

        _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import save_board_preserving_project

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", SRC))
# A DRC report for SRC, in JSON, produced with --severity-all.  Required: this
# script repairs what DRC found and nothing else.
DRC = Path(os.environ.get("O2_PCB_DRC", HERE / "pcb-drc-warnings.json"))

# One 0.1 mm grid step, plus a little.  It was 0.35 -- one step plus a
# 45-degree diagonal -- and at that reach a snap pulled a /3V3D In1 endpoint to
# 0.1344 mm from the locked /+12V_HTR feed, i.e. the repair created a clearance
# violation while removing a cosmetic one.  A finding that says "this endpoint
# is 0.3 mm off its via" is a manufacturing-review note; a clearance violation
# is a defect, so the trade is never worth taking.  Endpoints further out than
# this stay reported and unmoved.
SNAP_MAX = 0.15
# Stubs are removed only where DRC already called the track dangling, so this
# bound is about how much dead copper one finding is allowed to describe, not
# about deciding what is dead.
STUB_MAX = 2.00
# The board's own copper clearance rule; a snap may never route below it.
CLEARANCE = 0.15
TOUCH = 0.001


def mm(value) -> float:
    return round(pcbnew.ToMM(value), 4)


def key(point) -> tuple[float, float]:
    return mm(point.x), mm(point.y)


def distance(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def report_targets(report: Path) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return (via centres to snap onto, positions DRC called dangling)."""
    data = json.loads(report.read_text())
    vias, dangling = [], []
    for violation in data.get("violations", ()):
        kind = violation.get("type")
        if kind == "track_not_centered_on_via":
            for item in violation.get("items", ()):
                if item.get("description", "").startswith("Via "):
                    pos = item["pos"]
                    vias.append((round(pos["x"], 4), round(pos["y"], 4)))
        elif kind == "track_dangling":
            for item in violation.get("items", ()):
                pos = item.get("pos")
                if pos:
                    dangling.append((round(pos["x"], 4), round(pos["y"], 4)))
    return vias, dangling


def apply(board, report: Path) -> tuple[int, int, float, int]:
    flagged_vias, flagged_dangling = report_targets(report)
    if not flagged_vias and not flagged_dangling:
        return 0, 0, 0.0, 0

    tracks = [t for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)]
    vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
    targets = [v for v in vias
               if any(distance(key(v.GetPosition()), p) <= TOUCH for p in flagged_vias)]
    if len(targets) < len(set(flagged_vias)):
        raise SystemExit(
            f"DRC named {len(set(flagged_vias))} via(s) but only {len(targets)} "
            "were found on the board -- the report does not describe this board")

    def anchored_elsewhere(track, point, exclude) -> bool:
        """True if this endpoint already sits on some other same-net anchor."""
        for via in vias:
            if via is exclude or via.GetNetCode() != track.GetNetCode():
                continue
            if distance(point, key(via.GetPosition())) <= TOUCH:
                return True
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() != track.GetNetCode():
                    continue
                if pad.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(point[0]),
                                               pcbnew.FromMM(point[1]))):
                    return True
        return False

    # Foreign copper the snapped track must still clear.  Rebuilt per layer so
    # the collision test only looks at things that can actually touch.
    def foreign(track):
        layer = track.GetLayer()
        for other in tracks:
            if other is not track and other.GetNetCode() != track.GetNetCode() \
                    and other.GetLayer() == layer:
                yield other
        for other in vias:
            if other.GetNetCode() != track.GetNetCode() and other.IsOnLayer(layer):
                yield other
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() != track.GetNetCode() and pad.IsOnLayer(layer):
                    yield pad

    def clears(track) -> bool:
        """True if the track still holds CLEARANCE against every foreign item."""
        layer = track.GetLayer()
        shape = track.GetEffectiveShape(layer)
        for item in foreign(track):
            if shape.Collide(item.GetEffectiveShape(layer),
                             pcbnew.FromMM(CLEARANCE)):
                return False
        return True

    snapped = 0
    reverted = 0
    worst = 0.0
    for via in targets:
        centre = key(via.GetPosition())
        for track in tracks:
            if track.IsLocked() or track.GetNetCode() != via.GetNetCode():
                continue
            if not via.IsOnLayer(track.GetLayer()):
                continue
            for getter, setter in ((track.GetStart, track.SetStart),
                                   (track.GetEnd, track.SetEnd)):
                here = key(getter())
                gap = distance(here, centre)
                if gap <= TOUCH or gap > SNAP_MAX:
                    continue
                if anchored_elsewhere(track, here, via):
                    continue
                setter(pcbnew.VECTOR2I(pcbnew.FromMM(centre[0]),
                                       pcbnew.FromMM(centre[1])))
                # A snap that buys a cosmetic finding at the price of a
                # clearance violation is not a repair.  Measured 2026-09-05:
                # without this test a 0.1414 mm move put a /3V3D In1 endpoint
                # 0.1344 mm from the locked /+12V_HTR feed.
                if not clears(track):
                    setter(pcbnew.VECTOR2I(pcbnew.FromMM(here[0]),
                                           pcbnew.FromMM(here[1])))
                    reverted += 1
                    continue
                snapped += 1
                worst = max(worst, gap)

    board.BuildConnectivity()

    anchors = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            anchors.setdefault(pad.GetNetCode(), []).append(
                ("pad", pad, key(pad.GetPosition())))
    for via in vias:
        anchors.setdefault(via.GetNetCode(), []).append(
            ("via", via, key(via.GetPosition())))

    def touched(track, point) -> bool:
        for kind, item, centre in anchors.get(track.GetNetCode(), ()):
            if kind == "pad" and item.HitTest(pcbnew.VECTOR2I(
                    pcbnew.FromMM(point[0]), pcbnew.FromMM(point[1]))):
                return True
            if kind == "via" and distance(point, centre) <= TOUCH:
                return True
        for other in tracks:
            if other is track or other.GetNetCode() != track.GetNetCode():
                continue
            if distance(point, key(other.GetStart())) <= TOUCH:
                return True
            if distance(point, key(other.GetEnd())) <= TOUCH:
                return True
        return False

    removed = 0
    for track in tracks:
        if track.IsLocked():
            continue
        # A zero-length segment is not copper, it is a point.  KiCad still
        # tests it against every rule, so one collapsed by a snap shows up as
        # tracks_crossing against whatever it happens to sit on.
        if mm(track.GetLength()) <= TOUCH:
            board.Remove(track)
            removed += 1
            continue
        if mm(track.GetLength()) > STUB_MAX:
            continue
        near = min(distance(p, key(track.GetStart())) for p in flagged_dangling) \
            if flagged_dangling else None
        far = min(distance(p, key(track.GetEnd())) for p in flagged_dangling) \
            if flagged_dangling else None
        if near is None or min(near, far) > STUB_MAX:
            continue
        if touched(track, key(track.GetStart())) and touched(track, key(track.GetEnd())):
            continue
        board.Remove(track)
        removed += 1

    board.BuildConnectivity()
    return snapped, removed, worst, reverted


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))
    if not DRC.exists():
        raise SystemExit(f"no DRC report at {DRC}; run kicad-cli pcb drc "
                         "--severity-all --format json against this board first")
    snapped, removed, worst, reverted = apply(board, DRC)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(f"snapped {snapped} endpoint(s) onto same-net vias "
          f"(largest move {worst:.4f} mm, limit {SNAP_MAX} mm); "
          f"reverted {reverted} that would have broken clearance; "
          f"removed {removed} stub(s) under {STUB_MAX} mm")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
