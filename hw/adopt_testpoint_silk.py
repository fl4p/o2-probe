#!/usr/bin/env python3
"""Apply gen_pcb.py's test-point silkscreen labels to the routed board.

`gen_pcb.py` owns the labels and is the only place they are defined, but it
builds a board from scratch: re-running it would discard every routing pass
recorded in ROUTING.md.  Silkscreen is additive and touches no copper, so this
script imports the same table and the same placement function and applies them
in place.

Idempotent -- re-running replaces the labels rather than stacking duplicates.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

import gen_pcb
from thermal_design import save_board_preserving_project

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))


def main() -> int:
    board = pcbnew.LoadBoard(str(SRC))

    placed = {ref for ref in gen_pcb.TESTPOINT_LABELS}
    on_board = {footprint.GetReference() for footprint in board.Footprints()}
    missing = sorted(placed - on_board)
    if missing:
        sys.exit(f"labelled test points absent from {SRC.name}: {missing}")
    unlabelled = sorted(ref for ref in on_board
                        if ref.startswith("TP") and ref not in placed)
    if unlabelled:
        sys.exit(f"test points with no label in gen_pcb.TESTPOINT_LABELS: {unlabelled}")

    count = gen_pcb.add_testpoint_labels(board)
    save_board_preserving_project(board, OUT)
    print(f"wrote {OUT}: {count} test-point silkscreen labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
