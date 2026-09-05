"""Emit viewer/parts.json: what the three.js viewer loads, and where it goes.

The transforms are the SAME ones o2_probe_board_in_body.scad applies, written
out as 4x4 row-major matrices instead of OpenSCAD multmatrix. Keeping them here
rather than in the HTML means the viewer has no geometry knowledge at all -- it
draws what this file tells it to -- and the KiCad-frame mapping lives in exactly
two places rather than three.

The hand-drawn stand-ins for the parts KiCad omits come straight from
board_clearance.py's MISSING table, so the viewer cannot silently disagree with
the clearance numbers about which parts exist or how tall they are.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import board_clearance as bc          # noqa: E402

BOARD_T = bc.BOARD_T
TAIL, TUBE_LEN, CAP_ENGAGE = 22.0, 113.0, 18.0
BZ = TAIL - TUBE_LEN                  # board local y -> body z

# KiCad export frame -> body frame:
#   bodyX = kx - 110 ; bodyY = kz - t/2 ; bodyZ = -ky - 50 + BZ
# Determinant of the 3x3 is +1, so it is a rotation and not a mirror -- a mirror
# would put RV1 on the wrong face and still look plausible.
BOARD_M = [1, 0, 0, -110,
           0, 0, 1, -BOARD_T / 2,
           0, -1, 0, -50 + BZ,
           0, 0, 0, 1]
CAP_M = [1, 0, 0, 0,
         0, 1, 0, 0,
         0, 0, -1, -TUBE_LEN + CAP_ENGAGE,
         0, 0, 0, 1]
IDENT = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def main():
    boxes = [dict(
        name=name.strip(), kind="box",
        size=[x1 - x0, h, y1 - y0],
        center=[(x0 + x1) / 2 - 10.0,
                (-(BOARD_T / 2) - h / 2) if back else (BOARD_T / 2 + h / 2),
                BZ + (y0 + y1) / 2],
        color="#c62828",
        note="no 3D model in KiCad; drawn from footprint extents",
    ) for name, x0, x1, y0, y1, h, back in bc.MISSING]

    parts = [
        dict(name="body (head + tube)", kind="stl",
             file="../exports/body-monobody.stl", matrix=IDENT, color="#a0522d",
             note="printed ASA, one part, 146.6 mm"),
        dict(name="cable cap", kind="stl", file="../exports/body-cap.stl",
             matrix=CAP_M, color="#ff8c00", note="bayonet, M12x1.5 gland"),
        dict(name="PCB (KiCad export)", kind="stl",
             file="../exports/o2-probe-board-bin.stl", matrix=BOARD_M,
             color="#1b5e20",
             note="kicad-cli export; 0.910 mm board, 8 parts omitted"),
    ] + boxes

    out = dict(
        meta=dict(bore_r=bc.BORE_R, head_bore_r=bc.HEAD_BORE_R,
                  board_t_mesh=BOARD_T, board_t_model=1.6,
                  tube_len=TUBE_LEN, cap_engage=CAP_ENGAGE),
        parts=parts)
    path = os.path.join(CAD, 'viewer', 'parts.json')
    json.dump(out, open(path, 'w'), indent=1)
    print("viewer/parts.json: %d parts (%d STL, %d hand-drawn)"
          % (len(parts), sum(1 for p in parts if p['kind'] == 'stl'), len(boxes)))


if __name__ == '__main__':
    main()
