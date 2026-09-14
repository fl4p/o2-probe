#!/usr/bin/env python3
"""Find (and optionally place) a via that reconnects an orphaned GND pour island.

A new route can cut a ground pour in two, or push it back off the via that used
to feed it. KiCad reports that as one `unconnected_items` between the two GND
zones and gives no position, so this asks the connectivity engine directly:
anything not reachable from a known-good GND pad is an orphan. It then looks for
a via position inside the orphan that also lies inside a CONNECTED island on the
other layer, and that the router's via grid says is legal.

Run with KiCad's bundled Python.  `--place` adds the best via and refills.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(1, str(HERE))
import wx  # noqa: E402  - pcbnew needs an app object
_APP = wx.AppConsole()
import pcbnew as p  # noqa: E402
import numpy as np  # noqa: E402
from shapely.geometry import Point  # noqa: E402
import verify_revb_86_ring as V  # noqa: E402
import board as B  # noqa: E402
from route import build  # noqa: E402
import reroute_net as rn  # noqa: E402


def islands(b, layer, net='GND'):
    out = []
    for k, g in V.filled_union(b, layer).items():
        if not k.endswith(net):
            continue
        out += list(g.geoms) if hasattr(g, 'geoms') else [g]
    return out


def orphans(b, net='GND'):
    """Islands per layer, split into connected and orphaned, by KiCad connectivity."""
    c = b.GetConnectivity()
    c.RecalculateRatsnest()
    seed = next(q for f in b.GetFootprints() for q in f.Pads() if q.GetNetname() == net)
    pts = []
    for it in c.GetConnectedItems(seed):
        try:
            pts.append(Point(it.GetPosition().x / 1e6, it.GetPosition().y / 1e6))
        except Exception:
            pass
    live, dead = {}, {}
    for layer in (p.F_Cu, p.B_Cu):
        live[layer], dead[layer] = [], []
        for isl in islands(b, layer, net):
            (live if any(isl.buffer(0.01).covers(q) for q in pts) else dead)[layer].append(isl)
    return live, dead


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb')
    ap.add_argument('--net', default='GND')
    ap.add_argument('--place', action='store_true')
    ap.add_argument('--size', type=float, default=0.6)
    ap.add_argument('--drill', type=float, default=0.3)
    a = ap.parse_args()
    b = p.LoadBoard(a.pcb)
    live, dead = orphans(b, a.net)
    n = sum(len(v) for v in dead.values())
    if not n:
        print('no orphaned %s island' % a.net)
        return 0
    for layer in dead:
        for isl in dead[layer]:
            print('orphan %s %.3f mm2 bounds %s'
                  % (b.GetLayerName(layer), isl.area, [round(v, 2) for v in isl.bounds]))
    target_layer = max(dead, key=lambda l: max((g.area for g in dead[l]), default=0))
    target = max(dead[target_layer], key=lambda g: g.area)
    other = p.B_Cu if target_layer == p.F_Cu else p.F_Cu
    x0, y0, x1, y1 = target.bounds
    bd = B.parse(a.pcb)
    region = (max(99.5, x0 - 1), max(53.0, y0 - 1), min(120.5, x1 + 1), min(139.5, y1 + 1))
    g, _t, vg = build(bd, region, a.net, rn.W, rn.CLR, rn.EDGE, rn.HOLE,
                      via_d=rn.VIA_D, via_drill=rn.VIA_DR)
    r = a.size / 2 + rn.CLR
    found = []
    for x in np.arange(region[0], region[2], 0.05):
        for y in np.arange(region[1], region[3], 0.05):
            q = Point(float(x), float(y))
            if not target.contains(q.buffer(r)):
                continue
            if not any(h.contains(q.buffer(r)) for h in live[other]):
                continue
            i, j = g.ij(float(x), float(y))
            if not (0 <= i < g.nx and 0 <= j < g.ny):
                continue
            if vg.block[0, j, i] or vg.block[1, j, i]:
                continue
            found.append((round(float(x), 2), round(float(y), 2)))
    print('legal stitch positions in the largest orphan: %d' % len(found))
    if not found:
        return 1
    # pick the most central one, so the pour has copper all round it
    cx = sum(q[0] for q in found) / len(found)
    cy = sum(q[1] for q in found) / len(found)
    best = min(found, key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
    print('best: (%.2f, %.2f)' % best)
    if a.place:
        v = p.PCB_VIA(b)
        v.SetPosition(p.VECTOR2I(int(best[0] * 1e6), int(best[1] * 1e6)))
        v.SetWidth(int(a.size * 1e6))
        v.SetDrill(int(a.drill * 1e6))
        v.SetLayerPair(p.F_Cu, p.B_Cu)
        v.SetNetCode(b.GetNetcodeFromNetname(a.net))
        b.Add(v)
        b.BuildConnectivity()
        if not p.ZONE_FILLER(b).Fill(b.Zones()):
            raise SystemExit('zone fill failed')
        p.SaveBoard(a.pcb, b)
        print('placed and refilled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
