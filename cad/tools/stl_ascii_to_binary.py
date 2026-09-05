"""ASCII STL -> binary STL. KiCad's exporter writes ASCII; the board comes out
at 54 MB, which OpenSCAD reloads on every preview. Binary is 10.7 MB and loads
in a fraction of the time. Geometry is unchanged -- same facets, same order."""
import struct
import sys

src, dst = sys.argv[1], sys.argv[2]
tris, cur, nrm = [], [], (0.0, 0.0, 1.0)
for line in open(src):
    t = line.strip()
    if t.startswith('facet normal'):
        nrm = tuple(float(x) for x in t.split()[2:5])
        cur = []
    elif t.startswith('vertex'):
        cur.append(tuple(float(x) for x in t.split()[1:4]))
        if len(cur) == 3:
            tris.append((nrm, *cur))
            cur = []
with open(dst, 'wb') as f:
    f.write(b'\0' * 80)
    f.write(struct.pack('<I', len(tris)))
    for n, a, b, c in tris:
        f.write(struct.pack('<12fH', *n, *a, *b, *c, 0))
print("%s: %d facets" % (dst, len(tris)))
