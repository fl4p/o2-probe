#!/usr/bin/env python3
"""Put back any authored critical copper a routing pass removed.

`critical_routes.py` emits its copper locked, and `verify_critical.py` exists
because that lock is not honoured: KiCadRoutingTools deletes locked geometry on
nets it routes, and on 2026-09-05 it removed all seven authored GUARD_REPLICA
segments and all four of its vias while reporting other nets as
`protected_skipped ... "locked"`.

Excluding a net from the router is the first defence, and it works for the
nets `critical_routes.py` authors END TO END -- CELL_RE, CELL_WE, HEATER_LOW,
+12V_HTR.  GUARD_REPLICA is the exception: TP5 is on it and is not authored, so
the router has to be allowed at the net, and it takes the rails with it.

This restores them afterwards.  Re-adding copper the router removed is safe on
this net specifically because everything involved is the SAME net -- whatever
path the router chose for TP5 cannot short against a guard rail, only run
alongside one -- and DRC afterwards is what proves it.  Existing items that
already match are left alone, so this is idempotent.
"""

from __future__ import annotations

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

from critical_routes import add_critical_routes
from thermal_design import save_board_preserving_project
from verify_critical import check

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", SRC))


def track_key(item):
    return ("trk", item.GetNetname(), item.GetLayer(),
            round(pcbnew.ToMM(item.GetWidth()), 4),
            frozenset(((round(pcbnew.ToMM(item.GetStart().x), 4),
                        round(pcbnew.ToMM(item.GetStart().y), 4)),
                       (round(pcbnew.ToMM(item.GetEnd().x), 4),
                        round(pcbnew.ToMM(item.GetEnd().y), 4)))))


def via_key(item):
    """Identity of a via for de-duplication.

    Size and drill are part of it.  Without them a same-net via of the WRONG
    size sitting at an authored position counted as the authored via, the
    restore removed the correct one it had just added, and the run reported
    nothing missing while the board still had the wrong barrel.
    """
    return ("via", item.GetNetname(),
            round(pcbnew.ToMM(item.GetPosition().x), 4),
            round(pcbnew.ToMM(item.GetPosition().y), 4),
            round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 4),
            round(pcbnew.ToMM(item.GetDrill()), 4))


def main() -> int:
    before = check(SRC, expect_locked=False)
    if not before:
        print(f"nothing missing in {SRC}")
        if SRC != OUT:
            OUT.write_bytes(SRC.read_bytes())
        return 0

    board = pcbnew.LoadBoard(str(SRC))
    add_critical_routes(board)
    # De-duplicate by GEOMETRY, not by object identity.  The first version
    # captured `id(item)` before adding and compared it after, which cannot
    # work: pcbnew hands out a fresh SWIG proxy on every GetTracks() call, so
    # no id ever matched, and the pass silently dropped two of the four vias it
    # had just restored.  Geometric keys are stable across calls.
    seen = set()
    for item in list(board.GetTracks()):
        key = via_key(item) if isinstance(item, pcbnew.PCB_VIA) else track_key(item)
        if key in seen:
            board.Remove(item)
            continue
        seen.add(key)

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)

    after = check(OUT, expect_locked=False)
    print(f"restored {len(before) - len(after)} of {len(before)} missing "
          f"critical item(s) into {OUT}")
    if after:
        print("STILL MISSING after restore:")
        for problem in after:
            print(f"  - {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
