#!/usr/bin/env python3
"""Add a GND stitching via at X,Y. Run with KiCad's bundled Python.

Used when a new route splits a ground pour into islands: the pour reconnects
through a via to the other layer's plane. Refill and re-run DRC afterwards;
DRC's unconnected-items count is the arbiter, not this script.
"""
import sys
import pcbnew


def main(path, x, y, size=0.6, drill=0.3, net='GND'):
    b = pcbnew.LoadBoard(path)
    code = b.GetNetcodeFromNetname(net)
    if code < 0:
        raise SystemExit('no net named ' + net)
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
    v.SetWidth(int(size * 1e6))
    v.SetDrill(int(drill * 1e6))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNetCode(code)
    b.Add(v)
    b.BuildConnectivity()
    if not pcbnew.ZONE_FILLER(b).Fill(b.Zones()):
        raise SystemExit('zone fill failed')
    pcbnew.SaveBoard(path, b)
    print('added %s via %.2f/%.2f at (%.3f, %.3f)' % (net, size, drill, x, y))


if __name__ == '__main__':
    main(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]),
         *(float(a) for a in sys.argv[4:6]))
