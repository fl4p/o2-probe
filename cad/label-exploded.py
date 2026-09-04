"""Label cad/exports/head-end-exploded.png.

Parts are picked out by their assembly() colour, which works for every part that
HAS a distinct one. Three do not: the cap, the retainer screws and the radial
O-ring are all neutral greys, and a grey normalises to (1/3, 1/3, 1/3) whatever
its brightness, so no chroma test can ever separate them.

Those three are found positionally instead, which is safe because the stack order
is fixed by the design:

  * take all near-neutral pixels and split them into contiguous row bands;
  * the TOP band is the cap and the screws hanging under it, separated by row
    density -- the cap is a Ø45 disc (~190 px/row), the eight screws are thin
    shanks (~40-70 px/row);
  * the BOTTOM band is the O-ring.

The middle band is the membrane's shaded rim; it is ignored here because the
membrane has its own detector below.

This replaces hard-coded pixel windows, which broke silently the moment the PCB
tip was added below the head and --viewall re-framed the whole image.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = 'cad/exports/head-end-exploded.png'
im = Image.open(SRC).convert('RGB')
A = np.array(im).astype(int)
H, W, _ = A.shape
bright = A.sum(axis=2)
norm = A / np.maximum(bright[:, :, None], 1)


def mask(rgb, tol=0.045, bmin=120, bmax=735):
    """Pixels whose CHROMA matches rgb. Normalising by brightness makes the match
    survive OpenSCAD's shading, which scales a face's colour but does not rotate
    it."""
    t = np.array(rgb)
    tn = t / t.sum()
    return (np.abs(norm - tn).sum(axis=2) < tol) & (bright > bmin) & (bright < bmax)


def bands(m, min_px=40, gap=8):
    """Contiguous row bands of a mask, as (y0, y1), ignoring specks."""
    rows = m.any(axis=1)
    out, start, blank = [], None, 0
    for y, v in enumerate(rows):
        if v:
            if start is None:
                start = y
            blank = 0
        elif start is not None:
            blank += 1
            if blank > gap:
                out.append((start, y - blank))
                start = None
    if start is not None:
        out.append((start, H - 1))
    return [(a, b) for a, b in out if m[a:b + 1].sum() >= min_px]


def rows_of(m, y0, y1, keep):
    """Rows of m within [y0, y1] selected by a predicate on their pixel count."""
    out = np.zeros_like(m)
    counts = m.sum(axis=1)
    hi = counts[y0:y1 + 1].max()
    for y in range(y0, y1 + 1):
        if keep(counts[y], hi):
            out[y] = m[y]
    return out


grey = (np.abs(norm - 1 / 3).sum(axis=2) < 0.035) & (bright > 120) & (bright < 735)
gb = bands(grey)
assert len(gb) >= 2, f"expected at least a cap band and an O-ring band, got {gb}"
cap_y0, cap_y1 = gb[0]
ring_y0, ring_y1 = gb[-1]

cap_m = rows_of(grey, cap_y0, cap_y1, lambda c, hi: c >= 0.5 * hi)
screw_m = rows_of(grey, cap_y0, cap_y1, lambda c, hi: c < 0.5 * hi)
ring_m = np.zeros_like(grey)
ring_m[ring_y0:ring_y1 + 1] = grey[ring_y0:ring_y1 + 1]

# GhostWhite normalises the same as any grey, so the membrane is found on its
# absolute brightness and slight blue cast instead.
# The lit membrane face measures (230, 230, 237): near-neutral, slightly blue,
# and just BELOW the background's (248, 248, 248). The blue cast is what excludes
# the background, so the brightness window only has to bracket the disc itself --
# an earlier 700..770 window sat above the face entirely and found nothing once
# the camera moved.
membrane = ((A[:, :, 2] - A[:, :, 0]) > 4) & (bright > 640) & (bright < 741)

parts = [
    ("cap",                                cap_m,                      'r'),
    ("retainer screws (6 + 2 cap)",        screw_m,                    'l'),
    ("retainer",                           mask((176, 196, 222)),      'r'),
    ("membrane (PMV15T)",                  membrane,                   'l'),
    ("membrane gasket",                    mask((205, 92, 92)),        'r'),
    ("carrier",                            mask((240, 230, 140)),      'l'),
    ("O-ring 24 x 1.5",                    ring_m,                     'r'),
    ("head",                               mask((210, 180, 140)),      'l'),
    ("SGX-OX cell - socketed, consumable", mask((47, 79, 79)),         'r'),
    ("cell socket - stand-off DERIVED",    mask((218, 165, 32)),       'l'),
    ("PCB tip (20 x 1.0, gas zone)",       mask((34, 139, 34)),        'r'),
]

im2 = im.copy()
d = ImageDraw.Draw(im2)
try:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
except Exception:
    f = ImageFont.load_default()

for name, m, side in parts:
    ys, xs = np.nonzero(m)
    if len(ys) < 40:
        print(f"  SKIP {name} ({m.sum()} px)")
        continue
    cy = int(np.median(ys))
    row = xs[(ys > cy - 6) & (ys < cy + 6)]
    if len(row) < 3:
        row = xs
    x_edge = int(row.max()) if side == 'r' else int(row.min())
    tx = x_edge + 60 if side == 'r' else x_edge - 60
    bb = d.textbbox((0, 0), name, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lx = tx if side == 'r' else tx - tw
    d.line([(x_edge + (8 if side == 'r' else -8), cy),
            (tx - (8 if side == 'r' else -8), cy)], fill=(70, 70, 70), width=3)
    d.ellipse([x_edge - 4, cy - 4, x_edge + 4, cy + 4], fill=(70, 70, 70))
    d.text((lx, cy - th / 2 - 4), name, font=f, fill=(20, 20, 20))
    print(f"  {name:38} y={cy:5d} edge x={x_edge:5d} ({m.sum()} px)")

im2.save('cad/exports/head-end-exploded-labelled.png')
print("\nwrote cad/exports/head-end-exploded-labelled.png")
