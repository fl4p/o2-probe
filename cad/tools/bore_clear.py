"""Assert that nothing is printed inside the cable-end seal bore.

WHY A GEOMETRIC CHECK AND NOT ANOTHER SETTING

tools/seal_check.sh now asserts `brim_type = outer_only` for the monobody, and
that assertion would have caught the 2026-09-06 failure -- a fused 0.2 mm brim
disc across the O25.5 collar bore, which stopped the cap going on at all.

But it would only have caught it because we now know that brim_type was the
cause. It is one named setting out of many that can put plastic in that bore: a
wider brim, a raft, a skirt that overlaps, supports generated inside the bore, a
second object placed over it, an ironing pass. Every one of those leaves
`brim_type = outer_only` reading perfectly correct.

So this check does not look at settings at all. It looks at where the extruder
actually went, and fails if any extruding move lands inside the bore over the
bore's depth. That is the property that matters, and it is true or false
independently of how it came to be.

G2/G3 arcs are sampled, not skipped. A G1-only reader under-samples exactly the
round features this is about.

    python3 tools/bore_clear.py <plate.gcode> [--part monobody]
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
BODY = os.path.join(CAD, 'o2_probe_body_tube.scad')

# The bore is only allowed to be dirty by this much on radius before it is a
# finding: one extrusion width, so a wall loop sitting on the bore surface is
# not mistaken for something standing in it.
MARGIN = 0.30


def scalar(name, default=None):
    m = re.search(r'^%s\s*=\s*([\d.]+)\s*;' % re.escape(name),
                  open(BODY).read(), re.M)
    if m:
        return float(m.group(1))
    if default is None:
        raise SystemExit("bore_clear: cannot read %s from the model. "
                         "UNEVALUABLE IS A FAILURE." % name)
    return default


def points(path):
    """(z, x, y) of every extruding move, arcs sampled."""
    x = y = z = e = 0.0
    rel = False
    num = lambda s, k: (lambda m: float(m.group(1)) if m else None)(
        re.search(r'%s(-?[\d.]+)' % k, s))
    for line in open(path, 'r', errors='ignore'):
        line = line.split(';')[0].strip()
        if not line:
            continue
        if line.startswith('M83'):
            rel = True
            continue
        if line.startswith('M82'):
            rel = False
            continue
        if line.startswith('G92'):
            v = num(line, 'E')
            if v is not None:
                e = v
            continue
        g = re.match(r'G([0123])\b', line)
        if not g:
            continue
        code = int(g.group(1))
        nz = num(line, 'Z')
        if nz is not None:
            z = nz
        ne = num(line, 'E')
        hot = ne is not None and (ne > 0 if rel else ne > e)
        if ne is not None:
            e = ne
        px, py = x, y
        tx = num(line, 'X')
        ty = num(line, 'Y')
        tx = px if tx is None else tx
        ty = py if ty is None else ty
        if hot:
            if code in (2, 3):
                cx, cy = px + (num(line, 'I') or 0.0), py + (num(line, 'J') or 0.0)
                r = math.hypot(px - cx, py - cy)
                a0 = math.atan2(py - cy, px - cx)
                a1 = math.atan2(ty - cy, tx - cx)
                if code == 2:
                    while a1 > a0:
                        a1 -= 2 * math.pi
                else:
                    while a1 < a0:
                        a1 += 2 * math.pi
                n = max(2, int(abs(a1 - a0) / math.radians(2)))
                for k in range(n + 1):
                    a = a0 + (a1 - a0) * k / n
                    yield (z, cx + r * math.cos(a), cy + r * math.sin(a))
            else:
                yield (z, px, py)
                yield (z, tx, ty)
        x, y = tx, ty


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    part = None
    for i, a in enumerate(sys.argv):
        if a == '--part':
            part = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    if not argv:
        raise SystemExit("bore_clear: no G-code given")
    g = argv[0]
    if part not in (None, 'monobody', 'tube'):
        print("  bore-clear: not applicable to --part %s" % part)
        return 0
    if not os.path.exists(g) or os.path.getsize(g) == 0:
        raise SystemExit("bore_clear: %s is missing or empty. A slice that "
                         "produced nothing is a FAILURE, not a clean bore." % g)

    bore_d = scalar('cable_bore_d')
    depth = scalar('cable_bore_len')
    pts = list(points(g))
    if len(pts) < 1000:
        raise SystemExit("bore_clear: only %d extruding points in %s -- this "
                         "file is not a sliced plate. UNEVALUABLE IS A FAILURE."
                         % (len(pts), g))

    # The axis, from the widest layer well above the bore, where the only thing
    # at maximum radius is the tube's own OD. Taking it from the whole file
    # would centre on the brim, which is concentric anyway, but taking it from
    # layer 1 would centre on the brim's bounding box -- and that is the object
    # under test.
    high = [p for p in pts if p[0] > depth + 5.0]
    if not high:
        raise SystemExit("bore_clear: nothing above z=%.1f in %s -- this is not "
                         "the monobody." % (depth + 5.0, g))
    cx = (min(p[1] for p in high) + max(p[1] for p in high)) / 2
    cy = (min(p[2] for p in high) + max(p[2] for p in high)) / 2

    r_bore = bore_d / 2
    bad = [(p[0], math.hypot(p[1] - cx, p[2] - cy))
           for p in pts if p[0] <= depth and
           math.hypot(p[1] - cx, p[2] - cy) < r_bore - MARGIN]
    print("  bore-clear: axis (%.2f, %.2f), bore Ø%.2f x %.1f deep, "
          "%d extruding points below z=%.1f"
          % (cx, cy, bore_d, depth, sum(1 for p in pts if p[0] <= depth), depth))
    if not bad:
        print("  bore-clear OK: nothing is printed inside the seal bore.")
        return 0
    zs = sorted({round(z, 2) for z, _ in bad})
    print("\nBORE-CLEAR FAIL: %d extruding points land INSIDE the Ø%.2f seal "
          "bore,\n  reaching in to r=%.2f (the bore wall is r=%.2f), on %d layer(s) "
          "from z=%.2f to z=%.2f.\n  The cap's spigot cannot enter a bore with "
          "plastic in it. Check brim_type,\n  raft, skirt and support settings for "
          "this plate -- and do not print it."
          % (len(bad), bore_d, min(r for _, r in bad), r_bore, len(zs),
             min(zs), max(zs)), file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
