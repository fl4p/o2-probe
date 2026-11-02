#!/usr/bin/env python3
"""Compatibility entry point for the deterministic final PCB cleanup.

The former version deleted the four-layer board's internal plane and created
front/back zones. Keep this wrapper so old notes fail safe and use the current
finalization implementation instead.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
from runpy import run_path
from pathlib import Path

run_path(str(Path(__file__).resolve().parent.parent.joinpath("finalize_pcb.py")), run_name="__main__")
