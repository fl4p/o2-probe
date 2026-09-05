"""Measure the real board against the bore it has to live in.

The enclosure model reasons about the board through two declared numbers,
board_env_front and board_env_back, and a swept diagonal derived from them. That
is a rectangle standing in for a populated assembly, and it cannot see the one
failure it is meant to prevent: a single tall part in the wrong place. This
weighs the actual mesh KiCad exports instead.

Two questions, both answered off the mesh:

  1. Does anything on the board exceed the bore radius, anywhere along it?
  2. Do any component BODIES reach into the 1.0 mm of board width the guide
     rails occupy at their two stations? The earlier scan of o2-probe.kicad_pcb
     could only see PADS; a body overhanging its own pads was explicitly called
     out as not covered, and this is what covers it.

WHAT THE MESH DOES NOT CONTAIN, and the first number is worthless without it:
KiCad ships no 3D model for Potentiometer_SMD:Potentiometer_Bourns_3224W_Vertical
(the library has 3314G and 3314J), so RV1 -- the tallest part on the board and
the whole reason anyone asked -- is silently absent from the export. It is added
back here from its footprint extents and its measured height. Also absent, and
ALSO absent, and now added back too rather than argued away: L1 (3.0 mm), U8,
U12, and the four J101-104 wire lands. Their heights are package nominals, not
measurements -- good enough to answer "does it foul the bore" with millimetres
to spare, not good enough for a question about tenths.
"""
import math
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
MESH = os.path.join(os.path.dirname(HERE), 'exports', 'o2-probe-board-bin.stl')

BOARD_T = 0.910         # the dielectric stack in the board file, off the mesh
BORE_R = 13.60          # tube, Ø27.2
HEAD_BORE_R = 12.59     # head, Ø25.18
RAIL_ENGAGE = 1.0       # board width each guide rail overlaps
STATIONS = {'A (board y 4..24)': (4.0, 24.0), 'B (board y 82..90)': (82.0, 90.0)}
# Copper is 35 um and mask a little more. Anything further off the face than
# this is a real part; anything within it is copper, and a plastic rail bearing
# on copper is not a mechanical problem.
COPPER = 0.15

# RV1, absent from the export. Footprint pad extents from o2-probe.kicad_pcb,
# height measured by Fab 2026-09-04. On B.Cu, so it hangs below the board.
# Every part the export names and then omits. Same table as
# o2_probe_board_in_body.scad's `missing`; keep them together.
# name, x0, x1, y0, y1, height, on-the-back
MISSING = [
    ("RV1  trimmer",   0.25,  4.75,  71.10,  74.90, 5.0, True),
    ("L1   inductor",  7.00, 14.00,  26.30,  28.70, 3.0, False),
    ("U8   WQFN-16",  13.62, 17.38,  75.12,  78.88, 0.8, False),
    ("U12  SHT45",     2.55,  4.45, 100.95, 102.05, 0.5, False),
    ("J101 wire",      1.90,  4.10,   3.58,  15.80, 1.7, False),
    ("J102 wire",      6.60,  8.80,   3.58,  15.80, 1.7, False),
    ("J103 wire",     11.20, 13.40,   3.58,  15.80, 1.7, False),
    ("J104 wire",     15.90, 18.10,   3.58,  15.80, 1.7, False),
]


def verts():
    with open(MESH, 'rb') as f:
        n = struct.unpack('<I', f.read(84)[80:84])[0]
        data = f.read()
    for i in range(n):
        v = struct.unpack_from('<12f', data, i * 50)
        for k in (3, 6, 9):
            kx, ky, kz = v[k], v[k + 1], v[k + 2]
            # KiCad export frame -> board local. Measured off the export, not
            # assumed: x is page x from 100, y is NEGATED page y from -50, and
            # z runs 0..BOARD_T through the dielectric.
            yield kx - 100.0, -ky - 50.0, kz


def main():
    worst_r, worst_at, bands = 0.0, None, {}
    station_hit = {k: [None, None] for k in STATIONS}
    for bx, by, bz in verts():
        x, y = bx - 10.0, bz - BOARD_T / 2
        r = math.hypot(x, y)
        if r > worst_r:
            worst_r, worst_at = r, (bx, by, bz)
        b = int(by // 10) * 10
        bands[b] = max(bands.get(b, 0.0), r)
        if -COPPER <= bz <= BOARD_T + COPPER:
            continue                            # copper/mask, not a part
        for name, (y0, y1) in STATIONS.items():
            if y0 - 0.2 <= by <= y1 + 0.2:
                hit = station_hit[name]
                if bx < RAIL_ENGAGE and (hit[0] is None or bx < hit[0][0]):
                    hit[0] = (bx, by, bz)
                if bx > 20 - RAIL_ENGAGE and (hit[1] is None or bx > hit[1][0]):
                    hit[1] = (bx, by, bz)

    # The omitted parts, added back. Radius is taken at the OUTER TOP CORNER,
    # which is what binds in a round bore -- a mid-face height is not the
    # clearance for anything sitting near the board edge.
    def corner_r(x0, x1, h, back, t):
        y = -(t / 2 + h) if back else t / 2 + h
        return max(math.hypot(x0 - 10.0, y), math.hypot(x1 - 10.0, y))

    added = [(name, corner_r(x0, x1, h, back, BOARD_T),
              corner_r(x0, x1, h, back, 1.6), y0, y1)
             for name, x0, x1, y0, y1, h, back in MISSING]
    added.sort(key=lambda a: -a[2])
    rv_r = added[0][1]
    rv_r16 = added[0][2]

    fails = []
    print("MESH, %s" % os.path.basename(MESH))
    print("  worst radius on the exported board: %.3f mm at board (%.2f, %.1f)"
          % (worst_r, worst_at[0], worst_at[1]))
    print("\n  parts KiCad omitted, added back by hand"
          "  (r on 0.91 / 1.6 mm board):")
    for name, r09, r16, _, _ in added:
        print("    %-16s %6.3f / %6.3f%s"
              % (name, r09, r16, "   <- binding" if r16 == rv_r16 else ""))
    # RV1 sits at board y~73, i.e. in the TUBE, not in the head -- so only the
    # tube's bore is the right thing to compare it with. The head sees board
    # y 91..107 only, and its worst radius there is reported separately.
    print("  tube bore %.2f                      clearance %.3f mm"
          % (BORE_R, BORE_R - rv_r))
    head_r = max((r for b, r in bands.items() if b >= 90), default=0.0)
    print("  head bore %.2f, board y>=90 only    clearance %.3f mm"
          % (HEAD_BORE_R, HEAD_BORE_R - head_r))
    # The mesh is a 0.910 mm board; the enclosure is cut for board_t=1.6, which
    # pushes a back-side part 0.345 mm further out. Report the number the
    # enclosure actually has to swallow, not just the one the mesh implies.
    print("  worst of them on a 1.6 mm board:    %.3f mm, clearance %.3f mm"
          % (rv_r16, BORE_R - rv_r16))
    for name, r09, r16, y0, y1 in added:
        if r16 >= BORE_R:
            fails.append("%s does not clear the tube bore" % name.split()[0])
        if y0 >= 91.0 and r16 >= HEAD_BORE_R:
            fails.append("%s does not clear the head bore" % name.split()[0])
    if worst_r >= BORE_R:
        fails.append("the exported board does not clear the tube bore")
    if max((r for b, r in bands.items() if b >= 90), default=0.0) >= HEAD_BORE_R:
        fails.append("the board's gas end does not clear the head bore")

    print("\n  max radius by board-y band:")
    for b in sorted(bands):
        print("    %4d..%-4d  %6.3f" % (b, b + 10, bands[b]))

    print("\nCOMPONENT BODIES in the guide rails' %.1f mm:" % RAIL_ENGAGE)
    for name in STATIONS:
        lo, hi = station_hit[name]
        print("  station %s" % name)
        for label, p in (("x=0 edge ", lo), ("x=20 edge", hi)):
            if p is None:
                print("    %s: clear" % label)
            else:
                off = p[2] - BOARD_T if p[2] > BOARD_T else -p[2]
                print("    %s: INTRUDES to x=%.2f at y=%.1f, %.2f mm off the face"
                      % (label, p[0], p[1], off))
                fails.append("%s %s is fouled by a component body" % (name, label))

    if fails:
        print("\nFAIL: " + "; ".join(fails))
        return 1
    print("\nboard clears the bore, and both rail stations are free of component"
          " bodies")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
