#!/usr/bin/env python3
"""Extract the head-side 30 mm of the KiCad PCB STL into head coordinates.

NO DIMENSION IS WRITTEN HERE, and the reason is a measured defect rather than
tidiness. This file used to carry a literal `-152` in its placement matrix. That
constant is right for the MONOLITHIC joint (socket_len 3 + cav_board_len 2 puts
the board tip at z = 5) and wrong by 11 mm for the bonded head the head-end scene
actually renders -- so the viewer drew the PCB 11 mm below where the model says
it ends, and the picture looked entirely plausible. It is the same class of bug
tools/make_viewer_parts.py's docstring is about, and the same 11 mm.

So the tip's z comes OUT OF A RENDER of the model: the head prints an
`INTERFACE board_tip_z <n>` line, and the flags that render it come from the
Makefile via `make -s print-ASA`, exactly as tools/view.py gets them. Anything
that cannot be read is a hard failure, never a default.

The rest of the matrix is the KiCad-export -> head-frame rotation and the two
in-plane offsets, which are geometry of the board export and do not move with the
head. Its determinant is +1, so it is a rotation and not a mirror -- a mirror
would put the components on the wrong face and still look right in a render.
"""
import argparse
import math
import os
import re
import shlex
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
MODEL = 'o2_probe_head_end.scad'
FLAG_VAR = 'ASA'

# KiCad export frame -> head frame, less the axial offset:
#   headX = kx - 110 ; headY = kz - 0.455 ; headZ = -ky + Z_SHIFT
MATRIX_XY = (
    1, 0, 0, -110,
    0, 0, 1, -0.455,
    0, -1, 0, 0,
)
KEEP_LEN = 30.0          # how much of the head end of the board to keep
# The KiCad export's own board thickness, which is what puts a vertex "in the
# board" rather than on something mounted to it. Read from board_clearance.py so
# there is one copy; that module owns the mesh's dimensions.
BOARD_T = None           # filled in main(), from board_clearance.BOARD_T


def make_var(name):
    """Read a variable out of the Makefile, so the flags have ONE definition."""
    out = subprocess.run(['make', '-s', 'print-' + name], cwd=CAD,
                         capture_output=True, text=True)
    val = out.stdout.strip() if out.returncode == 0 else ''
    if not val:
        raise SystemExit(
            "board_tip: cannot read Makefile variable %s (tried `make -s "
            "print-%s`). Without it the model refuses its measured inputs and "
            "there is no board_tip_z to read -- placing the board on a guess is "
            "exactly the 11 mm bug this file exists to not repeat." % (name, name))
    return val


def board_tip_z(openscad, extra_flags):
    """Ask the model where the board's end face sits. Never assume it."""
    cmd = ([openscad] + shlex.split(make_var(FLAG_VAR)) + shlex.split(extra_flags)
           + ['-D', 'part="cavity"', '--export-format', 'asciistl',
              '-o', '/dev/null', MODEL])
    out = subprocess.run(cmd, cwd=CAD, capture_output=True, text=True)
    m = re.search(r'INTERFACE board_tip_z ([-\d.]+)', out.stdout + out.stderr)
    if not m:
        sys.stderr.write(out.stderr[-2000:])
        raise SystemExit(
            "board_tip: %s printed no `INTERFACE board_tip_z` line. Either the "
            "render failed (see above) or the echo was renamed -- fix one of "
            "those; do NOT fall back to a constant." % MODEL)
    return float(m.group(1))


def transform(vertex, z_shift):
    x, y, z = vertex
    return (
        MATRIX_XY[0] * x + MATRIX_XY[1] * y + MATRIX_XY[2] * z + MATRIX_XY[3],
        MATRIX_XY[4] * x + MATRIX_XY[5] * y + MATRIX_XY[6] * z + MATRIX_XY[7],
        MATRIX_XY[8] * x + MATRIX_XY[9] * y + MATRIX_XY[10] * z + z_shift,
    )


def clip_above(poly, z_min):
    out = []
    for a, b in zip(poly[-1:] + poly[:-1], poly):
        a_inside = a[2] >= z_min
        b_inside = b[2] >= z_min
        if a_inside != b_inside:
            t = (z_min - a[2]) / (b[2] - a[2])
            out.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(3)))
        if b_inside:
            out.append(b)
    return out


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length) if length else (0, 0, 0)


def read_triangles(path):
    tris = []
    with open(path, "rb") as source:
        source.seek(80)
        count = struct.unpack("<I", source.read(4))[0]
        for _ in range(count):
            data = struct.unpack("<12fH", source.read(50))
            tris.append((data[3:6], data[6:9], data[9:12]))
    return tris


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--openscad", default="openscad")
    parser.add_argument("--flags", default="",
                        help="extra -D flags, e.g. -D 'joint=\"monolithic\"'")
    args = parser.parse_args()

    global BOARD_T
    sys.path.insert(0, HERE)
    import board_clearance                      # noqa: E402  -- owns BOARD_T
    BOARD_T = board_clearance.BOARD_T

    tip_z = board_tip_z(args.openscad, args.flags)
    raw = read_triangles(args.source)

    # Self-calibrating: shift so the board's head-most vertex lands ON the model's
    # board_tip_z. The alternative -- a KiCad y datum written here -- is a second
    # copy of a number the board file already owns, and copies go stale.
    #
    # BUT THE EXTREMUM HAS TO BE THE BOARD, and nothing guarantees that: a pad,
    # a track or a component model that overhangs the profile becomes the datum
    # instead, and every part of the board is then drawn that much too deep --
    # silently, and looking entirely plausible. (2026-09-05 Codex review.) So the
    # datum is taken from vertices inside the BOARD SLAB, |headY| <= t/2 + 0.05,
    # and compared against the extremum over everything. They agree on today's
    # export; if they ever stop agreeing, that is a fact about the export and it
    # has to be looked at, not averaged away.
    all_z = [transform(v, 0.0) for tri in raw for v in tri]
    mesh_tip = max(p[2] for p in all_z)
    slab = [p[2] for p in all_z if abs(p[1]) <= BOARD_T / 2 + 0.05]
    if not slab:
        raise SystemExit(
            "board_tip: no vertex lies in the board slab (|y| <= %.3f). The "
            "KiCad->head rotation is wrong, or BOARD_T is." % (BOARD_T / 2 + 0.05))
    slab_tip = max(slab)
    if mesh_tip - slab_tip > 1e-3:
        raise SystemExit(
            "board_tip: the head-most vertex is %.3f mm PAST the board profile "
            "(%.3f vs %.3f). Something overhangs the Edge.Cuts tip, so using the "
            "extremum as the datum would draw the whole board %.3f mm too deep. "
            "Look at the export before going further."
            % (mesh_tip - slab_tip, mesh_tip, slab_tip, mesh_tip - slab_tip))
    z_shift = tip_z - slab_tip
    print("board_tip: tip -> head z %.3f (shift %.3f, datum on the board profile)"
          % (tip_z, z_shift))

    triangles = []
    for tri in raw:
        poly = clip_above([transform(v, z_shift) for v in tri], tip_z - KEEP_LEN)
        triangles.extend(
            (poly[0], poly[i], poly[i + 1]) for i in range(1, len(poly) - 1)
        )

    temporary = args.output + ".tmp"
    with open(temporary, "wb") as output:
        output.write(b"O2 probe PCB tip, 30 mm".ljust(80, b" "))
        output.write(struct.pack("<I", len(triangles)))
        for a, b, c in triangles:
            output.write(struct.pack("<12fH", *(normal(a, b, c) + a + b + c), 0))
    os.replace(temporary, args.output)


if __name__ == "__main__":
    main()
