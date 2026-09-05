"""Emit viewer/parts.json: what the three.js viewer loads, and where it goes.

EVERY DIMENSION IS READ OUT OF o2_probe_body_tube.scad. None is written here.

That is not tidiness, it is the bug this file exists to avoid. The viewer places
the board and the cap by arithmetic on the body's own constants, and the first
version hardcoded them -- tail_len 22, tube_len 113, cap_engage 18. Within the
hour `head_socket_len` moved 14 -> 3 in the model and `tube_len` became 124, so
those copies were stale and the viewer would have drawn the board 11 mm out of
place while looking entirely plausible. It is the same class of defect that had
already been found twice today between the two SCAD models (cap_engage 12 vs 18,
body_tube_len 127 vs 113), which is a good enough reason not to make it a third
time.

So: anything that cannot be read is a hard failure, never a default. A number
that has become a ternary -- as `socket_len` did in the head model -- stops being
readable, and this stops rather than guessing which branch to take.

The hand-drawn stand-ins for the parts KiCad omits come from board_clearance.py's
MISSING table, so the viewer cannot disagree with the clearance numbers about
which parts exist or how tall they are.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
BODY = os.path.join(CAD, 'o2_probe_body_tube.scad')
sys.path.insert(0, HERE)
import board_clearance as bc          # noqa: E402

_src = open(BODY).read()


def num(name):
    """A top-level `name = <literal>;` from the body model, or die saying so."""
    m = re.search(r'^%s\s*=\s*([-\d.]+)\s*;' % re.escape(name), _src, re.M)
    if not m:
        raise SystemExit(
            "make_viewer_parts: %s is not a plain number in %s.\n"
            "It has probably become a derived expression. Read it and decide -- "
            "do NOT let the viewer fall back to a default, which is exactly how "
            "it would draw the wrong geometry convincingly."
            % (name, os.path.basename(BODY)))
    return float(m.group(1))


def text(name):
    m = re.search(r'^%s\s*=\s*"([^"]*)"\s*;' % re.escape(name), _src, re.M)
    if not m:
        raise SystemExit("make_viewer_parts: cannot read %s" % name)
    return m.group(1)


def main():
    joint = text('joint')
    board_len = num('board_len')
    cav_board_len = num('cav_board_len')
    tail_len = num('tail_len')
    head_socket_len = num('head_socket_len')
    cap_engage = num('cap_engage')
    board_t_model = num('board_t')

    # Derived exactly as the model derives it. Monolithic, the tube stops where
    # the head begins, so the head's socket length comes off the end.
    tube_len = (board_len - cav_board_len + tail_len
                - (head_socket_len if joint == 'monolithic' else 0))

    board_t_mesh = bc.BOARD_T            # the KiCad export's own board thickness
    bz = tail_len - tube_len             # board local y -> body z

    # KiCad export frame -> body frame:
    #   bodyX = kx - 110 ; bodyY = kz - t/2 ; bodyZ = -ky - 50 + bz
    # Determinant of the 3x3 is +1, so it is a rotation and not a mirror -- a
    # mirror would put RV1 on the wrong face and still look plausible.
    board_m = [1, 0, 0, -110,
               0, 0, 1, -board_t_mesh / 2,
               0, -1, 0, -50 + bz,
               0, 0, 0, 1]
    cap_m = [1, 0, 0, 0,
             0, 1, 0, 0,
             0, 0, -1, -tube_len + cap_engage,
             0, 0, 0, 1]
    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    boxes = [dict(
        name=name.strip(), kind="box",
        size=[x1 - x0, h, y1 - y0],
        center=[(x0 + x1) / 2 - 10.0,
                (-(board_t_mesh / 2) - h / 2) if back else (board_t_mesh / 2 + h / 2),
                bz + (y0 + y1) / 2],
        color="#c62828",
        note="no 3D model in KiCad; drawn from footprint extents",
    ) for name, x0, x1, y0, y1, h, back in bc.MISSING]

    parts = [
        dict(name="body (head + tube)", kind="stl",
             file="../exports/body-monobody.stl", matrix=ident, color="#a0522d",
             note="printed ASA, one part, %s joint" % joint),
        dict(name="cable cap", kind="stl", file="../exports/body-cap.stl",
             matrix=cap_m, color="#ff8c00", note="bayonet, M12x1.5 gland"),
        dict(name="PCB (KiCad export)", kind="stl",
             file="../exports/o2-probe-board-bin.stl", matrix=board_m,
             color="#1b5e20",
             note="kicad-cli export; %.3f mm board, %d parts omitted"
                  % (board_t_mesh, len(bc.MISSING))),
    ] + boxes

    # STALENESS. The meshes are built by other targets from SCAD the main session
    # is actively editing, so the viewer can easily be handed a body that predates
    # the geometry it claims to show -- and a stale mesh looks exactly like a
    # current one. Record each file's mtime against the newest of its sources so
    # the page can say so on screen instead of quietly lying.
    sources = [BODY, os.path.join(CAD, 'o2_probe_head_end.scad')]
    newest_src = max(os.path.getmtime(f) for f in sources if os.path.exists(f))
    for part in parts:
        if part['kind'] != 'stl':
            continue
        f = os.path.normpath(os.path.join(CAD, 'viewer', part['file']))
        if not os.path.exists(f):
            part['stale'] = 'missing'
            continue
        age = newest_src - os.path.getmtime(f)
        part['stale'] = ('%.0f min older than the model' % (age / 60)) if age > 60 else None

    out = dict(
        meta=dict(
            generated=time.strftime('%Y-%m-%d %H:%M'),
            sources_mtime=time.strftime('%H:%M', time.localtime(newest_src)),
            bore_r=bc.BORE_R, head_bore_r=bc.HEAD_BORE_R,
            board_t_mesh=board_t_mesh, board_t_model=board_t_model,
            tube_len=tube_len, cap_engage=cap_engage, tail_len=tail_len,
            head_socket_len=head_socket_len, joint=joint, board_z0=bz),
        parts=parts)
    path = os.path.join(CAD, 'viewer', 'parts.json')
    json.dump(out, open(path, 'w'), indent=1)
    print("viewer/parts.json: %d parts (%d STL, %d hand-drawn)"
          % (len(parts), sum(1 for p in parts if p['kind'] == 'stl'), len(boxes)))
    print("  read from the model: joint=%s  tube_len=%g  tail=%g  "
          "head_socket_len=%g  cap_engage=%g  board_t=%g"
          % (joint, tube_len, tail_len, head_socket_len, cap_engage, board_t_model))


if __name__ == '__main__':
    main()
