#!/usr/bin/env python3
"""Volume of an ASCII STL by the divergence theorem.

The point of this existing at all: the connected gas volume is a MESH
property. Every analytic figure in the .scad is a hand-written model of the
void, and a hand-written model of the void is exactly what missed a bored-out
spigot once already. With --max this becomes the gate: `cell_axial_len=14`
reports 4.85 cm3 analytically, passes every assert, renders one closed solid,
and measures 5.02 cm3 here.
"""
import sys


def tris_ascii(path):
    pts = []
    for line in open(path, 'r', errors='ignore'):
        s = line.split()
        if s and s[0] == 'vertex':
            pts.append((float(s[1]), float(s[2]), float(s[3])))
            if len(pts) == 3:
                yield pts
                pts = []


def vol(path):
    v = 0.0
    n = 0
    for a, b, c in tris_ascii(path):
        v += (a[0]*(b[1]*c[2]-b[2]*c[1])
              - a[1]*(b[0]*c[2]-b[2]*c[0])
              + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
        n += 1
    return abs(v), n


args = sys.argv[1:]
limit = None
if "--max" in args:
    i = args.index("--max")
    limit = float(args[i + 1])
    del args[i:i + 2]

fail = False
for p in args:
    mm3, n = vol(p)
    if n == 0:
        print(f"{p}: no triangles -- not an ASCII STL?")
        fail = True
        continue
    mark = ""
    if limit is not None and mm3 > limit:
        mark = f"  FAIL: over the {limit} mm3 budget"
        fail = True
    print(f"{p.split('/')[-1]:30s} {mm3:9.1f} mm3 = {mm3/1000:6.3f} cm3"
          f"  ({n} tris){mark}")

sys.exit(1 if fail else 0)
