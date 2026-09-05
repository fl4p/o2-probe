#!/usr/bin/env python3
"""Extract the head-side 30 mm of the KiCad PCB STL into head coordinates."""
import argparse
import math
import os
import struct

MATRIX = (
    1, 0, 0, -110,
    0, 0, 1, -0.455,
    0, -1, 0, -152,
    0, 0, 0, 1,
)
Z_MIN = -25.0


def transform(vertex):
    x, y, z = vertex
    return (
        MATRIX[0] * x + MATRIX[1] * y + MATRIX[2] * z + MATRIX[3],
        MATRIX[4] * x + MATRIX[5] * y + MATRIX[6] * z + MATRIX[7],
        MATRIX[8] * x + MATRIX[9] * y + MATRIX[10] * z + MATRIX[11],
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()

    triangles = []
    with open(args.source, "rb") as source:
        source.seek(80)
        count = struct.unpack("<I", source.read(4))[0]
        for _ in range(count):
            data = struct.unpack("<12fH", source.read(50))
            poly = clip_above(
                [transform(data[3:6]), transform(data[6:9]), transform(data[9:12])],
                Z_MIN,
            )
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
