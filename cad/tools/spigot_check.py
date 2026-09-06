#!/usr/bin/env python3
"""Prove the cap's sealing spigot and its O-ring groove are IN THE MESH.

Why this exists, and why an assert would not have done
------------------------------------------------------
On 2026-09-06 the cap rendered as a perfect closed solid with NO SEALING SPIGOT
AT ALL. The spigot (dia 27.0, z 10..18.5) sat in cap()'s outer union while the
tube's seat (dia 32.4, z -e..18.5) sat in the subtraction, and the seat contains
the spigot completely, so the subtraction deleted it in full. tube() already
carried a comment about this exact mistake -- "put it in the outer union and the
bore subtraction eats it whole ... It was written the wrong way round and
shipped" -- and it was made a second time in the same file.

Nothing caught it:

  * `Volumes: 2` passed. Removing the spigot leaves one closed solid.
  * Every seal assert passed -- install stretch, squeeze after stretch-thinning,
    the tolerance band. All of them are arithmetic on `spigot_od`, `groove_root`
    and `seal_cord`, and none of them touches the geometry. They went on
    describing a seal that was not in the part.
  * The viewer drew the O-ring in its correct place, floating in the bore, which
    is how it was finally noticed -- by eye, by Fab: "it has no purpose there".

So the rule this file enforces is the one grip_check.py already enforces for the
wire-end grip band: measure the feature in the MESH, never in the .scad's own
arithmetic. Numbers come from the model's own SPIGOT echo, so this checker
re-derives nothing and cannot drift from the part it is checking.

Known-bad calibration (guard checklist item 7)
----------------------------------------------
Run against the pre-fix cap mesh, this reports:

    FAIL spigot: no material at r=13.500 anywhere in z 10.000..18.500
                 -- the spigot is ABSENT from the mesh

and exits 1. Verified 2026-09-06 on the mesh rendered immediately before the
nesting fix. The far tail is the case that matters here: the failure mode is
total absence, not a slightly short spigot, and a guard that only caught
"slightly wrong" would have scored this defect as a pass.

Usage:  tools/spigot_check.py [cap.stl]
With no argument it renders part="cap" itself, which is the only mode that
proves the SHIPPING geometry rather than whatever happens to be on disk.
"""
import math
import os
import re
import subprocess
import sys
import tempfile

CAD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAD = 'o2_probe_body_tube.scad'


def model_numbers():
    """The SPIGOT echo, straight from the model. Never recomputed here."""
    r = subprocess.run(
        # --export-format is REQUIRED with /dev/null: it has no suffix, and
        # without one OpenSCAD refuses with "Either add a valid suffix or
        # specify one using the --export-format option" -- which this checker
        # then correctly reports as unevaluable rather than as a pass, but the
        # echo is what it wanted. interface_check.py spells it the same way.
        [os.environ.get('OPENSCAD', 'openscad'),
         '--export-format', 'asciistl', '-o', os.devnull,
         '-D', 'part="cap"', SCAD],
        cwd=CAD, capture_output=True, text=True)
    m = re.search(r'SPIGOT od ([\d.]+) id ([\d.]+) len ([\d.]+) chamfer ([\d.]+)'
                  r' bore_depth ([\d.]+) groove_root_drawn ([\d.]+) groove_w ([\d.]+)',
                  r.stdout + r.stderr)
    if not m:
        # An unreadable model is NOT a pass. (Guard checklist item 1.)
        sys.exit('spigot_check: the model emitted no SPIGOT echo -- cannot '
                 'evaluate, so this is a FAILURE, not an OK.\n' + r.stderr[-2000:])
    k = [float(x) for x in m.groups()]
    return dict(od=k[0], id=k[1], len=k[2], chamfer=k[3],
                bore_depth=k[4], root=k[5], groove_w=k[6])


def render_cap():
    fd, path = tempfile.mkstemp(suffix='.stl', prefix='spigot-check-')
    os.close(fd)
    r = subprocess.run(
        [os.environ.get('OPENSCAD', 'openscad'), '--hardwarnings',
         '-D', 'part="cap"', '-o', path, SCAD],
        cwd=CAD, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.getsize(path):
        sys.exit('spigot_check: the cap did not render -- cannot evaluate, so '
                 'this is a FAILURE, not an OK.\n' + (r.stderr or r.stdout)[-2000:])
    return path


def verts(path):
    pat = re.compile(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)')
    out = []
    with open(path, errors='ignore') as f:
        for line in f:
            m = pat.search(line)
            if m:
                x, y, z = (float(g) for g in m.groups())
                out.append((math.hypot(x, y), z))
    if not out:
        sys.exit('spigot_check: %s is not an ASCII STL with vertices -- cannot '
                 'evaluate, so this is a FAILURE, not an OK.' % path)
    return out


def tris(path):
    """Facets as [(r, z), (r, z), (r, z)]. verts() cannot answer a question
    about the MIDDLE of a prismatic face; a triangle can."""
    pat = re.compile(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)')
    cur, out = [], []
    with open(path, errors='ignore') as f:
        for line in f:
            m = pat.search(line)
            if not m:
                continue
            x, y, z = (float(g) for g in m.groups())
            cur.append((math.hypot(x, y), z))
            if len(cur) == 3:
                out.append(cur)
                cur = []
    return out


def main():
    n = model_numbers()
    path = sys.argv[1] if len(sys.argv) > 1 else render_cap()
    v = verts(path)

    z0 = n['bore_depth'] - n['len']          # spigot root
    z1 = n['bore_depth']                     # cap inner face
    r_spig = n['od'] / 2.0
    r_root = n['root'] / 2.0
    fails = []

    # 1. THE SPIGOT IS PRESENT. Total absence is the measured failure mode, so
    #    this is asked first and asked plainly.
    on_od = [z for r, z in v if abs(r - r_spig) < 0.05 and z0 - 0.6 <= z <= z1 + 0.6]
    if not on_od:
        fails.append('spigot: no material at r=%.3f anywhere in z %.3f..%.3f '
                     '-- the spigot is ABSENT from the mesh' % (r_spig, z0, z1))
    else:
        span = max(on_od) - min(on_od)
        want = n['len'] - n['chamfer'] - 0.05
        if span < want:
            fails.append('spigot: only %.3f mm of it at r=%.3f, against %.3f '
                         'expected (len %.2f - chamfer %.2f)'
                         % (span, r_spig, want, n['len'], n['chamfer']))

    # 2. THE GROOVE IS CUT IN IT -- tested by ABSENCE OF MATERIAL, not by the
    #    presence of a small radius somewhere.
    #
    #    THE FIRST VERSION OF THIS WAS A MUTE BUTTON and a review caught it.
    #    It asked for the smallest radius anywhere on the spigot band, above a
    #    floor of spigot_id/2. The Ø20 cable passage wall sits at r=10 for the
    #    whole of that band, so the answer was always 10, always <= the required
    #    root, and always a pass. A rendered, closed cap with groove_w=0 passed
    #    with exit 0 -- the guard could not see the very feature it named.
    #    The spigot tip chamfer (r 12.5) would have done the same job one level
    #    up, so raising the floor would not have fixed it either.
    #
    #    What actually distinguishes a cut groove from no groove is whether the
    #    spigot's OUTER WALL still runs through the groove's z-band. So: take
    #    the band INTERIOR (shrunk by `edge`, which drops the groove's own two
    #    side walls, whose triangles sit exactly on the boundary) and look for
    #    any TRIANGLE that crosses it carrying material at a radius meaningfully
    #    outside the root. Triangles, not vertices: a plain cylinder has
    #    vertices only at its ends, so vertex sampling sees nothing at all in
    #    the middle of the band -- which is exactly the missing-groove case.
    gz0 = z1 - n['len'] + n['chamfer'] + 1.2
    gz1 = gz0 + n['groove_w']
    edge = 0.20
    band = (gz0 + edge, gz1 - edge)
    wall = r_root + 0.15                 # clear of the root surface itself
    intruders = 0
    for tri in tris(path):
        zs = [z for _, z in tri]
        if max(zs) < band[0] or min(zs) > band[1]:
            continue                     # does not cross the band interior
        if any(wall <= r <= n['od'] / 2.0 + 0.05 for r, _ in tri):
            intruders += 1
    if band[1] <= band[0]:
        fails.append('groove: groove_w %.3f is too small to test (band interior '
                     'is empty) -- treat as NO GROOVE' % n['groove_w'])
    elif intruders:
        fails.append('groove: %d facets still carry spigot wall between r=%.3f '
                     'and the OD through the groove band z %.3f..%.3f -- the '
                     'groove is not cut, or is too shallow to hold the ring'
                     % (intruders, wall, band[0], band[1]))

    if fails:
        for f in fails:
            print('FAIL ' + f)
        return 1
    # Report the MEASURED numbers. The first version printed the model-derived
    # r_root here while claiming mesh measurement -- provenance the guard had
    # not earned (guard checklist item 6).
    # Over the FULL band, not the shrunk interior: the root cylinder's own
    # vertices sit on the band EDGES, so the interior contains none of them and
    # the first version of this line reported `nan`. The interior is the right
    # window for the wall test above and the wrong one for reading the root.
    root_meas = min((r for r, z in v if gz0 - 0.05 <= z <= gz1 + 0.05
                     and r >= n['id'] / 2.0 + 0.5), default=float('nan'))
    print('spigot_check OK: spigot at r=%.3f over %.2f mm; groove band clear of '
          'wall, measured root %.3f (expected %.3f). Measured on the mesh.'
          % (r_spig, max(on_od) - min(on_od), root_meas, r_root))
    return 0


if __name__ == '__main__':
    sys.exit(main())
