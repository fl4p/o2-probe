#!/usr/bin/env python3
"""Heuristic screen of generated schematic geometry; not rendered signoff.

ERC does not care what a sheet LOOKS like, and this board's sheet had grown
symbols sitting on each other and value strings printed through net labels
(Fab, 2026-09-12: "fix that overlapping text").  The legacy pass uses coarse model boxes; those are not the emitted field
anchors. A separate bounded pass reads saved reference anchors for 0/180-degree
instances and detects their overlap with symbol body boxes.

Text extents are ESTIMATED from KiCad's default 1.27 mm text and ~0.85 aspect,
so these hits are screening findings, not exact glyph intersections. Symbol
body overlap is estimated from the generator body model. Values and quarter-turn fields remain
outside the saved-reference check and require visual review.
"""
import importlib.util, io, contextlib, sys, hashlib
from pathlib import Path
from audit_layout_references import reference_body_hits

ROOT = Path(__file__).resolve().parent

CH_W, TXT_H, PAD = 1.08, 1.27, 0.4

def load():
    spec = importlib.util.spec_from_file_location("gs", str(ROOT / "gen_sch.py"))
    m = importlib.util.module_from_spec(spec)
    sys.argv = ["gen_sch.py"]
    with contextlib.redirect_stdout(io.StringIO()):
        try: spec.loader.exec_module(m)
        except SystemExit: pass
    return m

def boxes(m):
    out = []
    for ref, i in m.INST.items():
        sym = m.SYMS[i["lib_id"]]
        # BODY ONLY. An earlier version added pin_len here, which made every
        # correctly-placed label at a pin read as a collision -- the guard was
        # reporting its own model, not the sheet. Pins are lines; text may sit
        # beside them. What must not overlap is body-on-body and text-on-body.
        hw = sym["half_w"]
        hh = sym["half_h"]
        x, y = i["x"], i["y"]
        if i.get("angle") in (90, 270):
            hw, hh = hh, hw
        out.append((f"{ref} body", x - hw, y - hh, x + hw, y + hh))
        if ref.startswith("#PWR"):
            continue        # reference and value are hidden on power symbols
        for kind, dy in (("ref", -hh - 1.8), ("value", -hh - 3.6)):
            t = ref if kind == "ref" else str(i.get("value", ""))
            if not t: continue
            w = len(t) * CH_W
            out.append((f"{ref}.{kind} '{t}'", x - w / 2, y + dy - TXT_H / 2,
                        x + w / 2, y + dy + TXT_H / 2))
    for text, x, y, ang in m.LABELS:
        w = len(text) * CH_W
        x0 = x - w if ang == 180 else x
        # Labels are emitted (justify ... bottom), so the glyphs sit ABOVE the
        # anchor, not centred on it. Modelling them centred put every label half
        # inside its own wire and made the strike-through check fire 44 times.
        out.append((f"label '{text}'", x0, y - TXT_H - 0.2, x0 + w, y - 0.2))
    return out

def struck_through(m, bx):
    """Labels a HORIZONTAL wire is drawn straight through.

    A label must touch its wire -- that is how it attaches -- so text-on-wire is
    not by itself a fault. What is unreadable is text lying ALONG a horizontal
    run, with the line striking through the glyphs; Fab photographed exactly
    that on NRST (2026-09-12). A vertical wire merely crosses the text and is
    fine. The guard has to encode that distinction or it reports nothing.
    """
    horiz = [(min(x1, x2), max(x1, x2), y1)
             for x1, y1, x2, y2 in m.WIRES if abs(y1 - y2) < 0.01]
    out = []
    for name, a, b, c, d in bx:
        if not name.startswith("label"):
            continue
        for lo, hi, wy in horiz:
            # STRICTLY inside the glyph band. A wire touching the bottom edge
            # is the label attaching to it, which is correct and universal.
            if b + 0.25 < wy < d - 0.25:
                overlap = min(c, hi) - max(a, lo)
                if overlap > 2.0:
                    out.append((round(overlap, 2), name,
                                f"struck through by horizontal wire y={wy:g}"))
                    break
    return out


def main():
    for name in ("gen_sch.py", "audit_layout.py", "audit_layout_references.py", "o2-probe.kicad_sch"):
        try:
            digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        except OSError as exc:
            print("result: UNVERIFIED - missing audit input:", exc)
            return 2
        print(f"input {name}: {digest}")
    m = load()
    bx = boxes(m)
    hits = []
    for i in range(len(bx)):
        n1, a1, b1, c1, d1 = bx[i]
        for j in range(i + 1, len(bx)):
            n2, a2, b2, c2, d2 = bx[j]
            if n1.split()[0].split('.')[0] == n2.split()[0].split('.')[0]:
                continue
            ox = min(c1, c2) - max(a1, a2)
            oy = min(d1, d2) - max(b1, b2)
            if ox > PAD and oy > PAD:
                hits.append((round(ox * oy, 2), n1, n2))
    hits.extend(struck_through(m, bx))
    try:
        reference_hits, coverage = reference_body_hits(m, (ROOT / "o2-probe.kicad_sch").read_text())
    except (OSError, ValueError) as exc:
        print("result: UNVERIFIED - saved reference/body screen:", exc)
        return 2
    hits.extend(reference_hits)
    hits.sort(reverse=True)
    print("O2 probe schematic LAYOUT audit")
    print("scope: heuristic model boxes plus bounded saved-reference/body screen; rendered review required")
    print(f"items: {len(bx)}")
    print("saved reference coverage:", coverage)
    print(f"collisions: {len(hits)}")
    for area, n1, n2 in hits[:40]:
        print(f"  {area:8.2f} mm2  {n1}  <->  {n2}")
    print("result:", "PASS" if not hits else "FAIL")
    return 1 if hits else 0

if __name__ == "__main__":
    raise SystemExit(main())
