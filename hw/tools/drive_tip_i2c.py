"""Re-route the tip end of /I2C_SDA and /I2C_SCL so no B.Cu crosses the front band.

The defect this fixes
---------------------
HEATED_ISLAND_SPREADER (B.Cu, /HEATER_LOW) is held together by one continuous
band of back copper along the front edge, Y ~136.6..138.70. That band is the
ONLY copper joining the left membrane-ring land to RH1/RH2/Q2. /I2C_SDA used to
run along it (the Y 138.5 run plus the diagonal feeding it), which cut the pour
in two and stranded the left land. Measured with pcbnew's ZONE_FILLER: deleting
exactly those four B.Cu segments, and nothing else, refills the pour as ONE
island holding both lands, both heaters and Q2.

Why both nets move
------------------
U10's SDA pad (pad 6) is on the DFN's south row, facing the front edge, inside
a sealed F.Cu pocket: 3V3D's bus and via close it to the north, the front-band
F.Cu run of /I2C_SCL closes it to the south, and the board edge closes it below.
With B.Cu refused in the band the pocket has no exit, so SDA cannot be fixed
alone -- SCL's U12<->U10 hop has to vacate the band first. It has somewhere
better to go: /I2C_SCL already runs north of the tip at X 106.25, Y 127.6..131.65,
so U12 pad 2 can join the net there instead of reaching across the tip.

The rule enforced here is narrow and geometric: no new B.Cu below FRONT_LIMIT.
A track may still dive north out of a pocket; nothing may run along the band.
The fill is the arbiter, not this rule -- run fillcheck.py afterwards.
"""
import os
import re
import sys
import pickle
from collections import deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board
import route
from route import build, astar, path_of, simplify

PCB = sys.argv[1]
REGION = (99.5, 100.0, 120.5, 139.5)
# HOLE is 0.30, not 0.25: the board's 'milled NPTH copper clearance' rule is
# 0.30 mm. At 0.25 the router put an /I2C_SDA run 0.275 mm from U11's 3 x 6 mm
# NPTH cell slot at (110, 129.3) - a real DRC error, measured 2026-09-14. The
# same gap once bit h2h, which was 0.25 against the same 0.30 rule.
W, CLR, EDGE, HOLE = 0.15, 0.1, 0.3, 0.30
VIA_D, VIA_DR = 0.4, 0.2
VIA_COST = float(os.environ.get("VIA_COST", "40"))
FRONT_LIMIT = float(os.environ.get("FRONT_LIMIT", "136.50"))

# (net, source footprint, source pad) -- routed in this order, each result
# blocking the next.
_JOB = {"scl": ("/I2C_SCL", "U12", "2"), "sda": ("/I2C_SDA", "U10", "6"),
        # SCL's U12 leg closes an F.Cu GND pocket (C20.2 + U10.2, joined by a
        # GND track). No straight two-via jumper clears RH1.2 and the HEATER_LOW
        # run under it (620 positions, best margin -0.079 mm), so route a bent
        # link from C20.2 to GND copper outside the pocket.
        "gnd": ("GND", "C20", "2")}
JOBS = [_JOB[k] for k in os.environ.get("ORDER", "scl,sda").split(",")]

# Optional F.Cu front limit per net. U10's SDA pad can only leave its pocket
# through the F.Cu front band, so a net that does not need the band (SCL, which
# has copper north of the tip) can be kept out of it: F_LIMIT_SCL=137.0.
F_LIMIT = {"/I2C_SCL": os.environ.get("F_LIMIT_SCL"),
           "/I2C_SDA": os.environ.get("F_LIMIT_SDA")}

# Optional per-net X window. Joining SCL at X 106.2 walled off a 14.6 mm^2 F.Cu
# GND island under U12/C20/Q2, and wrapping west of U12 ran into the thermal
# slot's edge clearance. TGT_XMIN_SCL restricts which existing SCL copper
# counts as the target (join further east, from inside that GND pocket);
# XMIN_SCL blocks routing west of a line.
TGT_XMIN = {"/I2C_SCL": os.environ.get("TGT_XMIN_SCL"),
            "/I2C_SDA": os.environ.get("TGT_XMIN_SDA")}
XMIN = {"/I2C_SCL": os.environ.get("XMIN_SCL"),
        "/I2C_SDA": os.environ.get("XMIN_SDA")}

bd = board.parse(PCB)
extra_segs = []
extra_vias = []
results = {}


def net_mask(g, b, net):
    """Same-net copper rasterised per layer, plus the via layer links."""
    m = np.zeros((2, g.ny, g.nx), dtype=bool)
    links = []
    for s in b["segs"]:
        if s["net"] != net or s["layer"] not in route.LAYERS:
            continue
        g.capsule(m[route.LAYERS.index(s["layer"])], s["a"], s["b"], s["w"] / 2)
    for v in b["vias"]:
        if v["net"] != net:
            continue
        for li in (0, 1):
            g._disc(m[li], v["at"][0], v["at"][1], v["size"] / 2)
        links.append(g.ij(*v["at"]))
    for p in b["pads"]:
        if p["net"] != net:
            continue
        lis = [0, 1] if "*.Cu" in p["layers"] else (
            ([0] if "F.Cu" in p["layers"] else []) +
            ([1] if "B.Cu" in p["layers"] else []))
        for li in lis:
            g._rect(m[li], p["at"][0], p["at"][1], p["w"] / 2, p["h"] / 2)
        if len(lis) == 2:
            links.append(g.ij(*p["at"]))
    return m, links


def components(g, m, links):
    lab = -np.ones((2, g.ny, g.nx), dtype=int)
    linkset = set(links)
    nxt = 0
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    for li0 in (0, 1):
        for j0, i0 in zip(*np.where(m[li0])):
            if lab[li0, j0, i0] >= 0:
                continue
            q = deque([(li0, int(i0), int(j0))])
            lab[li0, j0, i0] = nxt
            while q:
                li, i, j = q.popleft()
                for dx, dy in steps:
                    ni, nj = i + dx, j + dy
                    if (0 <= ni < g.nx and 0 <= nj < g.ny
                            and m[li, nj, ni] and lab[li, nj, ni] < 0):
                        lab[li, nj, ni] = nxt
                        q.append((li, ni, nj))
                lo = 1 - li
                if (i, j) in linkset and m[lo, j, i] and lab[lo, j, i] < 0:
                    lab[lo, j, i] = nxt
                    q.append((lo, i, j))
            nxt += 1
    return lab, nxt


def keepouts(text):
    """Rule areas that forbid tracks, board- or footprint-level.

    board.py does not read zones at all. The first run of this driver put SCL
    straight through U12's footprint keepout (the no-copper area under the
    SHT45) and DRC reported items_not_allowed. Footprint zones are stored in
    board coordinates, so no transform is needed.
    """
    out = []
    for m in re.finditer(r"\(zone\b", text):
        st = m.start()
        d = 0
        e = st
        while True:
            if text[e] == "(":
                d += 1
            elif text[e] == ")":
                d -= 1
                if d == 0:
                    break
            e += 1
        zb = text[st:e + 1]
        if "(keepout" not in zb or "(tracks not_allowed)" not in zb:
            continue
        lm = re.search(r"\(layers? ([^)]*)\)", zb)
        lays = re.findall(r'"([^"]+)"', lm.group(1)) if lm else []
        lis = [i for i, name in enumerate(route.LAYERS)
               if name in lays or "*.Cu" in lays or "F&B.Cu" in lays]
        pm = re.search(r"\(polygon\s*\(pts(.*?)\)\s*\)", zb, re.S)
        if not pm or not lis:
            continue
        pts = [(float(x), float(y))
               for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", pm.group(1))]
        out.append((lis, pts))
    return out


def block_polygon(g, mask, pts, r):
    """Fill a polygon on the grid and inflate its outline by r."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    i0, j0 = g.ij(min(xs) - r, min(ys) - r)
    i1, j1 = g.ij(max(xs) + r, max(ys) + r)
    i0, j0 = max(i0, 0), max(j0, 0)
    i1, j1 = min(i1, g.nx - 1), min(j1, g.ny - 1)
    if i1 < i0 or j1 < j0:
        return
    gx = g.x0 + np.arange(i0, i1 + 1) * route.G
    gy = g.y0 + np.arange(j0, j1 + 1) * route.G
    X, Y = np.meshgrid(gx, gy)
    inside = np.zeros(X.shape, dtype=bool)
    n = len(pts)
    for a in range(n):
        x1, y1 = pts[a]
        x2, y2 = pts[(a + 1) % n]
        if y1 == y2:
            continue
        cross = ((y1 > Y) != (y2 > Y)) & (X < (x2 - x1) * (Y - y1) / (y2 - y1) + x1)
        inside ^= cross
    mask[j0:j1 + 1, i0:i1 + 1] |= inside
    for a in range(n):
        g.capsule(mask, pts[a], pts[(a + 1) % n], r)


KEEPOUTS = keepouts(bd["text"])
print("track keepouts parsed: %d" % len(KEEPOUTS))

for net, ref, padnum in JOBS:
    b2 = dict(bd)
    b2["segs"] = bd["segs"] + extra_segs
    b2["vias"] = bd["vias"] + extra_vias
    g, _all, vg = build(b2, REGION, net, W, CLR, EDGE, HOLE, exclude_ref=ref,
                        via_d=VIA_D, via_drill=VIA_DR)
    jy = g.ij(0.0, FRONT_LIMIT)[1]
    g.block[1, max(jy, 0):, :] = True
    vg.block[1, max(jy, 0):, :] = True
    for lis, pts in KEEPOUTS:
        for li in lis:
            block_polygon(g, g.block[li], pts, W / 2)
    if F_LIMIT.get(net):
        fy = g.ij(0.0, float(F_LIMIT.get(net)))[1]
        g.block[0, max(fy, 0):, :] = True
    if XMIN.get(net):
        xi = g.ij(float(XMIN.get(net)), 0.0)[0]
        g.block[:, :, :max(xi, 0)] = True

    m, links = net_mask(g, b2, net)
    lab, ncomp = components(g, m, links)

    src = [p for p in b2["pads"] if p["ref"] == ref and p["num"] == padnum][0]
    si, sj = g.ij(*src["at"])
    # the component the source pad sits in (the pad itself is excluded from the
    # obstacle set but still carries the net, so look it up in the label map)
    own = lab[0, sj, si]
    if own < 0:
        own = lab[1, sj, si]
    tgt = (lab >= 0) & (lab != own)
    if TGT_XMIN.get(net):
        tgt[:, :, :max(g.ij(float(TGT_XMIN.get(net)), 0.0)[0], 0)] = False
    print("%s: %d net component(s), source in #%d, %d target cells"
          % (net, ncomp, own, int(tgt.sum())))
    if not tgt.any():
        sys.exit("%s: no other component to reach" % net)

    # Start only on the pad copper itself: a radius around the centre lets the
    # route begin in free space beside a small DFN pad and never touch it.
    ri = int((src["w"] / 2) / route.G)
    rj = int((src["h"] / 2) / route.G)
    starts = [(0, si + di, sj + dj)
              for di in range(-ri, ri + 1) for dj in range(-rj, rj + 1)
              if 0 <= si + di < g.nx and 0 <= sj + dj < g.ny
              and not g.block[0, sj + dj, si + di]]
    if not starts:
        sys.exit("%s: source pad %s.%s fully blocked" % (net, ref, padnum))

    end, prev = astar(g, tgt, starts, via_cost=VIA_COST, vg=vg)
    if end is None:
        sys.exit("%s: NO PATH" % net)

    pl = simplify(path_of(end, prev), g)
    length = sum(((run[k + 1][1] - run[k][1]) ** 2
                  + (run[k + 1][2] - run[k][2]) ** 2) ** 0.5
                 for run in pl for k in range(len(run) - 1))
    print("  path %.2f mm, %d via(s), %d vertices"
          % (length, len(pl) - 1, sum(len(r_) for r_ in pl)))
    for run in pl:
        print("    %s: %s" % (route.LAYERS[run[0][0]],
                              " -> ".join("(%.2f,%.2f)" % (p[1], p[2]) for p in run)))
    results[net] = pl
    for run in pl:
        for k in range(len(run) - 1):
            extra_segs.append(dict(a=(run[k][1], run[k][2]),
                                   b=(run[k + 1][1], run[k + 1][2]),
                                   w=W, layer=route.LAYERS[run[k][0]], net=net))
    for k in range(len(pl) - 1):
        lp = pl[k][-1]
        extra_vias.append(dict(at=(lp[1], lp[2]), size=VIA_D, drill=VIA_DR, net=net))

out = os.environ.get("OUT", "/tmp/tip_i2c.pkl")
pickle.dump(results, open(out, "wb"))
print("saved", out)
