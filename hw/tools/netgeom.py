"""Shared grid helpers: net copper masks, connected components, keepout rule areas.

Copied from drive_tip_i2c.py (2026-09-13), which runs its routing job at import
time and so cannot be imported. drive_tip_i2c.py keeps its own copies unchanged
because it is the committed, reproducible record of the tip re-route.
"""
import re
from collections import deque

import numpy as np

import route


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
    """Rule areas that forbid tracks, board- or footprint-level (board coordinates)."""
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
