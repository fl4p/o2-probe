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

    # 2. THE GROOVE IS CUT IN IT. A spigot with no groove holds no ring, and the
    #    groove is the half that a nesting error takes first.
    in_spig = [r for r, z in v if z0 - 0.05 <= z <= z1 + 0.05]
    if not in_spig:
        fails.append('groove: no cap geometry at all in the spigot band')
    else:
        got = min(r for r in in_spig if r >= n['id'] / 2.0 - 0.05)
        if got > r_root + 0.05:
            fails.append('groove: the smallest radius on the spigot is %.3f, but '
                         'the groove root should reach %.3f -- no groove is cut'
                         % (got, r_root))

    if fails:
        for f in fails:
            print('FAIL ' + f)
        return 1
    print('spigot_check OK: spigot at r=%.3f over %.2f mm, groove root %.3f '
          '(measured on the mesh, not on the model\'s arithmetic)'
          % (r_spig, max(on_od) - min(on_od), r_root))
    return 0


if __name__ == '__main__':
    sys.exit(main())
