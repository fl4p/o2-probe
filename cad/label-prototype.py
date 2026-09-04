"""Label cad/exports/prototype-exploded.png — the WHOLE prototype-1 probe.

Same method as label-exploded.py, which labels the head on its own: parts are
found by their assembly() colour, and the three that share a neutral grey (the
debris cap, its screws, and the radial O-ring) are found by row band instead,
because a grey normalises to (1/3, 1/3, 1/3) at any brightness and no chroma
test can separate them.

This is a separate script rather than an option on that one. The two drawings
have different stack orders and different grey populations, and the band logic
depends on both -- folding them together would mean one script whose behaviour
is decided by a flag, in a file whose whole purpose is that its assumptions are
inspectable.

What is added here, all chromatic and all below the head: the printed body tube,
the split dam, and the bayonet cable cap that carries the M12 gland thread.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = 'cad/exports/prototype-exploded.png'
im = Image.open(SRC).convert('RGB')
A = np.array(im).astype(int)
H, W, _ = A.shape
bright = A.sum(axis=2)
norm = A / np.maximum(bright[:, :, None], 1)


def mask(rgb, tol=0.045, bmin=120, bmax=735):
    """Pixels whose CHROMA matches rgb, so the match survives OpenSCAD's shading
    (which scales a face's colour but does not rotate it)."""
    t = np.array(rgb)
    tn = t / t.sum()
    return (np.abs(norm - tn).sum(axis=2) < tol) & (bright > bmin) & (bright < bmax)


def bands(m, min_px=40, gap=8):
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
    out = np.zeros_like(m)
    counts = m.sum(axis=1)
    hi = counts[y0:y1 + 1].max()
    for y in range(y0, y1 + 1):
        if keep(counts[y], hi):
            out[y] = m[y]
    return out


grey = (np.abs(norm - 1 / 3).sum(axis=2) < 0.035) & (bright > 120) & (bright < 735)
gb = bands(grey)
assert len(gb) >= 2, f"expected a cap band and an O-ring band, got {gb}"
cap_y0, cap_y1 = gb[0]
ring_y0, ring_y1 = gb[-1]

cap_m = rows_of(grey, cap_y0, cap_y1, lambda c, hi: c >= 0.5 * hi)
screw_m = rows_of(grey, cap_y0, cap_y1, lambda c, hi: c < 0.5 * hi)
ring_m = np.zeros_like(grey)
ring_m[ring_y0:ring_y1 + 1] = grey[ring_y0:ring_y1 + 1]

# GhostWhite normalises like any grey, so the membrane is found on its absolute
# brightness and slight blue cast instead.
membrane = ((A[:, :, 2] - A[:, :, 0]) > 4) & (bright > 640) & (bright < 741)

parts = [
    ("debris cap — replaceable",            cap_m,                  'r'),
    ("retainer screws (6 + 2 cap)",         screw_m,                'l'),
    ("retainer",                            mask((176, 196, 222)),  'r'),
    ("membrane (Porex PMV15T)",             membrane,               'l'),
    ("membrane gasket",                     mask((205, 92, 92)),    'r'),
    ("PP carrier — coupon fused in",        mask((240, 230, 140)),  'l'),
    ("O-ring 24 × 1.5 EPDM — carrier seal", ring_m,                 'r'),
    ("head — ONE part with the tube",       mask((210, 180, 140)),  'l'),
    ("SGX-OX cell — socketed, consumable",  mask((47, 79, 79)),     'r'),
    ("cell socket — stand-off DERIVED",     mask((218, 165, 32)),   'l'),
    ("PCB (20 × 107, Rev A, UNPOTTED)",     mask((34, 139, 34)),    'r'),
    ("dam, 2 halves",                       mask((147, 112, 219)), 'l'),
    ("body tube Ø32 — no bonded joint",     mask((160, 82, 45)),    'r'),
    ("O-ring 28 × 2 EPDM — cable seal",     mask((220, 20, 60)),    'r'),
    ("cable cap — bayonet, M12×1.5",        mask((255, 140, 0)),    'l'),
]

im2 = im.copy()
d = ImageDraw.Draw(im2)
try:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
except Exception:
    f = ImageFont.load_default()

missing = []
for name, m, side in parts:
    ys, xs = np.nonzero(m)
    if len(ys) < 40:
        missing.append(f"{name} ({m.sum()} px)")
        continue
    cy = int(np.median(ys))
    row = xs[(ys > cy - 6) & (ys < cy + 6)]
    if len(row) < 3:
        row = xs
    x_edge = int(row.max()) if side == 'r' else int(row.min())
    tx = x_edge + 50 if side == 'r' else x_edge - 50
    bb = d.textbbox((0, 0), name, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lx = tx if side == 'r' else tx - tw
    d.line([(x_edge + (8 if side == 'r' else -8), cy),
            (tx - (8 if side == 'r' else -8), cy)], fill=(70, 70, 70), width=3)
    d.ellipse([x_edge - 4, cy - 4, x_edge + 4, cy + 4], fill=(70, 70, 70))
    d.text((lx, cy - th / 2 - 4), name, font=f, fill=(20, 20, 20))
    print(f"  {name:42} y={cy:5d} ({m.sum()} px)")

im2.save('cad/exports/prototype-exploded-labelled.png')
print("\nwrote cad/exports/prototype-exploded-labelled.png")
# A part that vanishes from the drawing is the failure this labeller exists to
# catch -- it means a colour changed, or a part is hidden inside another.
if missing:
    raise SystemExit("NOT FOUND in the render: " + "; ".join(missing))
