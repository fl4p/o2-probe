"""Rip one stretch of a net's copper and re-route it away from sensitive analog nets.

Written 2026-09-13 after the revb-86-ring review: J107's SCL route ran on B.Cu
between /CELL_WE and /GUARD_REPLICA (0.100 mm from the guard) and its SDA route
passed 0.100 mm from /VREF_TRIM. Generic clearance is legal there and still
wrong: a 100 kHz clock does not belong beside an electrode guard or a reference
trim. The router therefore inflates every sensitive net's copper by SENS_EXTRA
on top of the ordinary clearance, so a new route cannot hug them.

    route  PCB --net N --rip X0,Y0,X1,Y1 --reference REF --source X,Y --target X0,Y0,X1,Y1 --out PKL
    emit   PCB --net N --source X,Y --pkl PKL

route: removes nothing from the board. It routes as if every segment/via of N
lying wholly inside the --rip box were already gone, from the free end at
--source (existing copper of N, which must survive the rip) to any OTHER copper
component of N inside --target.

emit: deletes that same rip set from the board file and writes the route, the
first point landed on the source point and the last snapped onto existing
copper. Refill and DRC afterwards; the fill and DRC are the arbiters.
"""
import argparse
import os
import pickle
import re
import sys
import uuid

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board
import route
from route import build, astar, path_of, simplify

W, CLR, EDGE, HOLE = 0.15, 0.1, 0.3, 0.25
VIA_D, VIA_DR = 0.4, 0.2
# Analog nets a new route must keep away from. /AFE_MENB is deliberately NOT in
# the default set: it is the LMP91000 module-enable input, a static digital line
# (confirmed from the netlist before use). Matching it through a blanket 'AFE_'
# prefix walled the MCU's I2C copper off from both board edges (2026-09-13).
# Override with SENSITIVE_RE for a different policy.
SENSITIVE = re.compile(os.environ.get('SENSITIVE_RE',
                                      r'^/(CELL_|GUARD|LMP_|TMP_CELL|VREF|AFE_VOUT|BIAS)'))
SENS_EXTRA = float(os.environ.get('SENS_EXTRA', '0.5'))
VIA_COST = float(os.environ.get('VIA_COST', '40'))
FRONT_LIMIT = float(os.environ.get('FRONT_LIMIT', '136.5'))


def box(s):
    x0, y0, x1, y1 = map(float, s.split(','))
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def inbox(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def _skey(s):
    return (s['net'], s['layer'], round(s['a'][0], 4), round(s['a'][1], 4), round(s['b'][0], 4), round(s['b'][1], 4))


def _vkey(v):
    return (v['net'], round(v['at'][0], 4), round(v['at'][1], 4))


def rip_set(bd, net, rip, reference):
    """Copper of `net` wholly inside `rip`, EXCLUDING anything the reference board has.

    A plain box swept up two segments of the accepted board's own SDA copper on
    the first try (2026-09-13); only copper this revision added may be ripped.
    """
    ref = board.parse(reference)
    rs = {_skey(s) for s in ref['segs']}
    rv = {_vkey(v) for v in ref['vias']}
    segs = [s for s in bd['segs'] if s['net'] == net and inbox(s['a'], rip) and inbox(s['b'], rip)
            and _skey(s) not in rs]
    vias = [v for v in bd['vias'] if v['net'] == net and inbox(v['at'], rip) and _vkey(v) not in rv]
    return segs, vias


def cmd_route(a):
    import netgeom as dti  # net_mask / components / keepouts / block_polygon
    bd = board.parse(a.pcb)
    rip = box(a.rip)
    rs, rv = rip_set(bd, a.net, rip, a.reference)
    print('rip set: %d segments, %d vias' % (len(rs), len(rv)))
    ids = {id(x) for x in rs + rv}
    b2 = dict(bd)
    b2['segs'] = [s for s in bd['segs'] if id(s) not in ids]
    b2['vias'] = [v for v in bd['vias'] if id(v) not in ids]
    region = (99.5, 53.0, 120.5, 139.5)
    g, _all, vg = build(b2, region, a.net, W, CLR, EDGE, HOLE, via_d=VIA_D, via_drill=VIA_DR)
    jy = g.ij(0.0, FRONT_LIMIT)[1]
    g.block[1, max(jy, 0):, :] = True
    vg.block[1, max(jy, 0):, :] = True
    for lis, pts in dti.keepouts(bd['text']):
        for li in lis:
            dti.block_polygon(g, g.block[li], pts, W / 2)
    nsens = 0
    for s in b2['segs']:
        if s['net'] and SENSITIVE.match(s['net']) and s['layer'] in route.LAYERS:
            li = route.LAYERS.index(s['layer'])
            g.capsule(g.block[li], s['a'], s['b'], s['w'] / 2 + CLR + W / 2 + SENS_EXTRA)
            g.capsule(vg.block[li], s['a'], s['b'], s['w'] / 2 + CLR + VIA_D / 2 + SENS_EXTRA)
            nsens += 1
    for v in b2['vias']:
        if v['net'] and SENSITIVE.match(v['net']):
            for li in (0, 1):
                g._disc(g.block[li], v['at'][0], v['at'][1], v['size'] / 2 + CLR + W / 2 + SENS_EXTRA)
                g._disc(vg.block[li], v['at'][0], v['at'][1], v['size'] / 2 + CLR + VIA_D / 2 + SENS_EXTRA)
            nsens += 1
    for p in b2['pads']:
        if p['net'] and SENSITIVE.match(p['net']):
            lis = [0, 1] if '*.Cu' in p['layers'] else (
                ([0] if 'F.Cu' in p['layers'] else []) + ([1] if 'B.Cu' in p['layers'] else []))
            for li in lis:
                g._rect(g.block[li], p['at'][0], p['at'][1], p['w'] / 2 + CLR + W / 2 + SENS_EXTRA,
                        p['h'] / 2 + CLR + W / 2 + SENS_EXTRA)
            nsens += 1
    print('sensitive items inflated by %.2f mm: %d' % (SENS_EXTRA, nsens))

    m, links = dti.net_mask(g, b2, a.net)
    lab, ncomp = dti.components(g, m, links)
    sx, sy = map(float, a.source.split(','))
    si, sj = g.ij(sx, sy)
    own = -1
    for li in (0, 1):
        if lab[li, sj, si] >= 0:
            own = lab[li, sj, si]
            break
    if own < 0:
        sys.exit('source point is not on surviving copper of ' + a.net)
    tb = box(a.target)
    tgt = (lab >= 0) & (lab != own)
    i0, j0 = g.ij(tb[0], tb[1])
    i1, j1 = g.ij(tb[2], tb[3])
    keep = np.zeros_like(tgt)
    keep[:, max(j0, 0):j1 + 1, max(i0, 0):i1 + 1] = True
    tgt &= keep
    print('%s: %d components, source #%d, %d target cells in box' % (a.net, ncomp, own, int(tgt.sum())))
    if not tgt.any():
        sys.exit('no target copper inside the target box')
    starts = []
    r = int(0.1 / route.G)
    for li in (0, 1):
        if lab[li, sj, si] != own:
            continue
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                ii, jj = si + di, sj + dj
                if 0 <= ii < g.nx and 0 <= jj < g.ny and not g.block[li, jj, ii]:
                    starts.append((li, ii, jj))
    if not starts:
        sys.exit('source point fully blocked (sensitive inflation may cover it)')
    end, prev = astar(g, tgt, starts, via_cost=VIA_COST, vg=vg)
    if end is None:
        sys.exit('NO PATH')
    pl = simplify(path_of(end, prev), g)
    length = sum(((run[k + 1][1] - run[k][1]) ** 2 + (run[k + 1][2] - run[k][2]) ** 2) ** 0.5
                 for run in pl for k in range(len(run) - 1))
    print('path %.2f mm, %d via(s)' % (length, len(pl) - 1))
    for run in pl:
        print('  %s: %s' % (route.LAYERS[run[0][0]], ' -> '.join('(%.2f,%.2f)' % (q[1], q[2]) for q in run)))
    pickle.dump({'net': a.net, 'rip': a.rip, 'reference': a.reference, 'source': (sx, sy), 'path': pl}, open(a.out, 'wb'))
    print('saved', a.out)


def cmd_emit(a):
    # The pickle is only ever this tool's own `route` output, written one step earlier.
    job = pickle.load(open(a.pkl, 'rb'))
    if job['net'] != a.net:
        sys.exit('pickle is for %s, not %s' % (job['net'], a.net))
    bd = board.parse(a.pcb)
    rs, rv = rip_set(bd, a.net, box(job['rip']), job['reference'])
    text = open(a.pcb).read()

    def spans(kind):
        out = []
        for m in re.finditer(r'\n\t\(%s\b' % kind, text):
            st = m.start() + 1
            d = 0
            k = st
            while True:
                if text[k] == '(':
                    d += 1
                elif text[k] == ')':
                    d -= 1
                    if d == 0:
                        break
                k += 1
            out.append((st, k + 1, text[st:k + 1]))
        return out

    kill = []
    want_s = {(round(s['a'][0], 4), round(s['a'][1], 4), round(s['b'][0], 4), round(s['b'][1], 4), s['layer']) for s in rs}
    want_v = {(round(v['at'][0], 4), round(v['at'][1], 4)) for v in rv}
    for st, en, blk in spans('segment'):
        if '(net "%s")' % a.net not in blk:
            continue
        sa = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)', blk)
        sb = re.search(r'\(end ([-\d.]+) ([-\d.]+)\)', blk)
        ly = re.search(r'\(layer "([^"]+)"\)', blk).group(1)
        k = (round(float(sa.group(1)), 4), round(float(sa.group(2)), 4), round(float(sb.group(1)), 4), round(float(sb.group(2)), 4), ly)
        if k in want_s:
            kill.append((st, en))
    for st, en, blk in spans('via'):
        if '(net "%s")' % a.net not in blk:
            continue
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', blk)
        if (round(float(at.group(1)), 4), round(float(at.group(2)), 4)) in want_v:
            kill.append((st, en))
    if len(kill) != len(rs) + len(rv):
        sys.exit('rip set mismatch: found %d blocks for %d items' % (len(kill), len(rs) + len(rv)))
    for st, en in sorted(kill, reverse=True):
        # drop the preceding newline+tab too
        text = text[:st - 1] + text[en:]
    pl = job['path']
    sx, sy = job['source']
    pl[0][0] = (pl[0][0][0], round(sx, 4), round(sy, 4))
    lx = pl[-1][-1]
    best = None
    for s in bd['segs']:
        if s['net'] != a.net or s in rs:
            continue
        (ax, ay), (bx, by) = s['a'], s['b']
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((lx[1] - ax) * dx + (lx[2] - ay) * dy) / L2))
        q = (ax + t * dx, ay + t * dy)
        d = ((q[0] - lx[1]) ** 2 + (q[1] - lx[2]) ** 2) ** 0.5
        if best is None or d < best[0]:
            best = (d, q)
    for p in bd['pads']:
        if p['net'] == a.net:
            d = ((p['at'][0] - lx[1]) ** 2 + (p['at'][1] - lx[2]) ** 2) ** 0.5
            if best is None or d < best[0]:
                best = (d, p['at'])
    for v in bd['vias']:
        if v['net'] == a.net and v not in rv:
            d = ((v['at'][0] - lx[1]) ** 2 + (v['at'][1] - lx[2]) ** 2) ** 0.5
            if best is None or d < best[0]:
                best = (d, v['at'])
    if best is None or best[0] > 0.35:
        sys.exit('route end is not within 0.35 mm of surviving copper')
    pl[-1][-1] = (lx[0], round(best[1][0], 4), round(best[1][1], 4))
    add = []
    for run in pl:
        for k in range(len(run) - 1):
            (li, x1, y1), (_, x2, y2) = run[k], run[k + 1]
            if (x1, y1) == (x2, y2):
                continue
            add.append('\n\t(segment\n\t\t(start %g %g)\n\t\t(end %g %g)\n\t\t(width %s)\n\t\t(layer "%s")\n'
                       '\t\t(net "%s")\n\t\t(uuid "%s")\n\t)' % (x1, y1, x2, y2, W, route.LAYERS[li], a.net, uuid.uuid4()))
    for k in range(len(pl) - 1):
        _, vx, vy = pl[k][-1]
        add.append('\n\t(via\n\t\t(at %g %g)\n\t\t(size %s)\n\t\t(drill %s)\n\t\t(layers "F.Cu" "B.Cu")\n'
                   '\t\t(net "%s")\n\t\t(uuid "%s")\n\t)' % (vx, vy, VIA_D, VIA_DR, a.net, uuid.uuid4()))
    k = text.rindex('\n\t(segment')
    k = text.index('\n\t)', k) + 3
    text = text[:k] + ''.join(add) + text[k:]
    open(a.pcb, 'w').write(text)
    print('removed %d segments + %d vias; wrote %d segments + %d vias; end snapped %.3f mm'
          % (len(rs), len(rv), len(add) - (len(pl) - 1), len(pl) - 1, best[0]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('route')
    r.add_argument('pcb')
    r.add_argument('--net', required=True)
    r.add_argument('--rip', required=True)
    r.add_argument('--reference', required=True, help='accepted board: its copper is never ripped')
    r.add_argument('--source', required=True)
    r.add_argument('--target', required=True)
    r.add_argument('--out', required=True)
    e = sub.add_parser('emit')
    e.add_argument('pcb')
    e.add_argument('--net', required=True)
    e.add_argument('--pkl', required=True)
    a = ap.parse_args()
    cmd_route(a) if a.cmd == 'route' else cmd_emit(a)
