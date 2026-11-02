#!/usr/bin/env python3
"""Grow U11's three cell pads from the bare-pin hole to the socket land.

The SGX-OX-ROHS-Mini may NOT be soldered: DS-0317 Issue 2 note 3, the
same-platform 4-series sheet, says "Do not glue or solder to the connector
pins as this may damage the sensor and thereby invalidate the warranty,
please use PCB sockets."  Rev A carried a 1.6 mm land on a 0.9 mm drill,
which is 0.64 mm pin plus clearance -- a hole for the forbidden mount.

The land becomes 2.0 mm on a 1.32 mm drill:

  * 1.32 is TE Connectivity 5050462 (customer drawing C-5050462 rev P):
    recommended hole 1.32 +0.10/-0.00 for hand insertion, accepts 0.36-0.66 mm
    pins, 4.19 mm max pin length against this cell's 4.0 mm pin, 2.54 mm min
    contact point.  The one-sided tolerance is one a fab can hold.
  * 2.0 is deliberately larger than either candidate flange (TE 1.78,
    Cambion 450-3703 1.88) so the same board can be bored to 1.40 and take
    the Cambion instead -- a build-time choice, not a respin.  Annular ring
    is 0.34 mm at 1.32 and 0.30 mm at 1.40.

The land change costs clearance in exactly one place: pad-2 copper to the
rear-vent slot edge falls from 0.50 mm to 0.30 mm, still above the project's
0.20 mm hole-clearance floor.  ``audit_pcb.py`` asserts the new figure.

U11's pad positions and nets already carry the 2026-09-01 pin-identity fix,
so nothing here moves copper; only the land and drill change.  Run with
KiCad's bundled Python, then re-run DRC and audit_pcb.py.
"""

from __future__ import annotations
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))

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

HERE = Path(__file__).resolve().parent.parent
BOARD = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", BOARD))

LAND_MM = 2.0
DRILL_MM = 1.32
EXPECTED = {"1": "/CELL_CE", "2": "/CELL_RE", "3": "/CELL_WE"}


def main() -> None:
    board = pcbnew.LoadBoard(str(BOARD))
    u11 = next((f for f in board.Footprints() if f.GetReference() == "U11"), None)
    if u11 is None:
        sys.exit("U11 not found")

    pads = {p.GetNumber(): p for p in u11.Pads() if p.GetNumber()}
    if set(pads) != set(EXPECTED):
        sys.exit(f"U11 pads {sorted(pads)}, want {sorted(EXPECTED)}")
    for number, net in EXPECTED.items():
        if pads[number].GetNetname() != net:
            sys.exit(f"U11 pad {number} is on {pads[number].GetNetname()!r}, want {net!r}; "
                     "run the pin-identity migration first")

    for number, pad in pads.items():
        pad.SetSize(pcbnew.VECTOR2I_MM(LAND_MM, LAND_MM))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(DRILL_MM, DRILL_MM))
        print(f"U11.{number} ({EXPECTED[number]}): land {LAND_MM} mm, drill {DRILL_MM} mm")

    board.Save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
