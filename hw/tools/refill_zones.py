#!/usr/bin/env python3
"""Refill every zone on a board and save it. Run with KiCad's bundled Python.

Zones must be refilled after any copper edit, and the fill is what DRC and
verify_revb_86_ring.py's pinned filled areas are judged on.
"""
import sys
import pcbnew

def main(path):
    b = pcbnew.LoadBoard(path)
    b.BuildConnectivity()
    if not pcbnew.ZONE_FILLER(b).Fill(b.Zones()):
        raise SystemExit('zone fill failed: ' + path)
    pcbnew.SaveBoard(path, b)
    print('refilled', path)

if __name__ == '__main__':
    main(sys.argv[1])
