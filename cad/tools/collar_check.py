#!/usr/bin/env python3
"""Prove the cable-end SEALING COLLAR is in the tube mesh, and that its lead
cone is too.

Why this exists
---------------
The collar stands INSIDE the tube bore. That puts it in the one structural slot
this file has now gotten wrong twice -- a feature unioned before the bore is
subtracted, so the subtraction eats it whole:

  * tube()'s lock boss, which vanished and turned a blind pilot into a through
    hole into the sealed volume;
  * cap()'s sealing spigot, which vanished ENTIRELY while every seal assert went
    on describing it, and was noticed only because Fab looked at the viewer and
    said "it has no purpose there".

Both rendered as clean closed solids. `Volumes: 2` cannot see this class of
defect, and neither can any assert in the .scad: install stretch, squeeze after
stretch-thinning and the tolerance band are all arithmetic on cable_bore_d,
groove_root and seal_cord. Delete the collar from the mesh and every one of them
still passes, describing a seal that is not in the part.

So this measures the MESH, and it measures the two things that can go wrong:

  1. THE COLLAR IS THERE. Eaten by the bore, the cable end reads tube_id/2
     instead of cable_bore_d/2 -- a Ø27.2 hole where a Ø25.5 sealing land should
     be. A 22 x 2 ring in a 27.2 bore is not a loose seal, it is no seal.
  2. THE LEAD CONE IS THERE. The monobody prints head-end down, so this file's
     +z runs downward through the print and the collar's top face is a
     downward-facing annular ledge. Unchamfered it is an unsupported overhang of
     collar_lead -- the identical defect that spiderwebbed the head's bore entry
     on 2026-09-06, except here it is strung across the sealing surface. The
     cone is not cosmetic and it must not be silently lost.

Numbers come from the model's own COLLAR echo, so this checker re-derives
nothing and cannot drift from the part it is checking (the rule grip_check.py
and spigot_check.py already follow).

Known-bad calibration (guard checklist item 7)
----------------------------------------------
`--selftest` builds both failures from the real model by patching the .scad in a
temp copy, and requires each to FAIL:

    collar-eaten   the collar moved into the outer union, as the lock boss and
                   the spigot each really were once
    cone-gone      collar_lead driven to zero

Neither is a near miss; both are the far tail, which is the tail that actually
happened twice.

Usage:  tools/collar_check.py [tube.stl]
        tools/collar_check.py --selftest
With no argument it renders part="tube" itself, which is the only mode that
proves the SHIPPING geometry rather than whatever happens to be on disk.
"""
import math
import os
import re
import subprocess
import sys
import tempfile
from typing import NoReturn

CAD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAD = 'o2_probe_body_tube.scad'
OPENSCAD = os.environ.get('OPENSCAD', 'openscad')


def die(msg) -> NoReturn:
    # An unevaluable input is NOT a pass (guard checklist item 1).
    sys.exit('collar_check: ' + msg)


def model_numbers(scad=SCAD):
    """The COLLAR echo, straight from the model. Never recomputed here."""
    r = subprocess.run(
        # --export-format is REQUIRED with /dev/null: it has no suffix, and
        # without one OpenSCAD refuses outright.
        [OPENSCAD, '--export-format', 'asciistl', '-o', os.devnull,
         '-D', 'part="tube"', scad],
        cwd=CAD, capture_output=True, text=True)
    m = re.search(r'COLLAR bore ([\d.]+) len ([\d.]+) lead ([\d.]+)'
                  r' tube_id ([\d.]+) wall ([\d.]+)', r.stdout + r.stderr)
    if not m:
        die('the model emitted no COLLAR echo -- cannot evaluate, so this is a '
            'FAILURE, not an OK.\n' + (r.stderr or r.stdout)[-2000:])
    k = [float(x) for x in m.groups()]
    return dict(bore=k[0], len=k[1], lead=k[2], tube_id=k[3], wall=k[4])


def render_tube(scad=SCAD):
    fd, path = tempfile.mkstemp(suffix='.stl', prefix='collar-check-')
    os.close(fd)
    r = subprocess.run(
        [OPENSCAD, '--hardwarnings', '-D', 'part="tube"', '-o', path, scad],
        cwd=CAD, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.getsize(path):
        die('the tube did not render -- cannot evaluate, so this is a FAILURE, '
            'not an OK.\n' + (r.stderr or r.stdout)[-2000:])
    return path


VERT = re.compile(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)')


def read(path):
    """Return (vertices, triangles) as (r, z) -- cylindrical, since every
    feature here is a body of revolution."""
    cur, tris, verts = [], [], []
    with open(path, errors='ignore') as f:
        for line in f:
            m = VERT.search(line)
            if not m:
                continue
            x, y, z = (float(g) for g in m.groups())
            p = (math.hypot(x, y), z)
            verts.append(p)
            cur.append(p)
            if len(cur) == 3:
                tris.append(cur)
                cur = []
    if not verts:
        die('%s is not an ASCII STL with vertices -- cannot evaluate, so this '
            'is a FAILURE, not an OK.' % path)
    return verts, tris


def check(path, n):
    fails = []
    inner = float('nan')
    verts, tris = read(path)
    r_bore = n['bore'] / 2.0
    r_tube = n['tube_id'] / 2.0

    # 1. THE COLLAR IS PRESENT, tested through the band INTERIOR and with
    #    TRIANGLES, not vertices. A plain cylinder carries vertices only at its
    #    two ends, so vertex sampling reads nothing at all in the middle of the
    #    collar -- which is indistinguishable from the collar being absent. That
    #    is precisely the hole that made spigot_check's first groove test a mute
    #    button, and it is not being dug twice.
    lo, hi = 0.30, n['len'] - 0.30
    if hi <= lo:
        fails.append('collar: length %.3f is too short to test (band interior '
                     'is empty) -- treat as NO COLLAR' % n['len'])
    else:
        inner = min((min(r for r, _ in t) for t in tris
                     if max(z for _, z in t) >= lo
                     and min(z for _, z in t) <= hi),
                    default=float('inf'))
        if inner > r_bore + 0.05:
            fails.append(
                'collar: the smallest radius through z %.2f..%.2f is %.3f, not '
                'the %.3f sealing land%s -- the collar is ABSENT from the mesh, '
                'and the ring would sit in open bore'
                % (lo, hi, inner, r_bore,
                   ' (it reads as the plain %.3f bore)' % r_tube
                   if abs(inner - r_tube) < 0.05 else ''))

    # 2. THE LEAD CONE IS PRESENT. Its two ends are where the mesh does carry
    #    vertices, so this one is asked of vertices: the collar's top face at
    #    z=len must stand at the tube bore, and the cone must run out to the
    #    sealing radius collar_lead further on. Lose the cone and both of those
    #    land at the same z, as a ledge.
    def at(z, want):
        return any(abs(zz - z) < 0.02 and abs(rr - want) < 0.02
                   for rr, zz in verts)

    if n['lead'] <= 0.2:
        fails.append('cone: collar_lead is %.3f -- below one extrusion width '
                     'there is no lead, only an unsupported ledge over the '
                     'sealing surface' % n['lead'])
    else:
        if not at(n['len'], r_tube):
            fails.append('cone: no material at r=%.3f on z=%.3f -- the cone '
                         'does not start at the tube bore' % (r_tube, n['len']))
        if not at(n['len'] + n['lead'], r_bore):
            fails.append(
                'cone: nothing at r=%.3f on z=%.3f -- the collar ends in a '
                '%.2f mm ledge instead of a 45 deg lead. The cable end prints '
                'UP, so that ledge is an unsupported overhang ACROSS THE '
                'SEALING BORE' % (r_bore, n['len'] + n['lead'],
                                  r_tube - r_bore))

    if fails:
        for f in fails:
            print('FAIL ' + f)
        return 1
    # Report MEASURED numbers, not the model's own -- provenance the guard has
    # actually earned (guard checklist item 6).
    print('collar_check OK: sealing land measured at r=%.3f over z %.2f..%.2f '
          '(bore %.2f), 45 deg lead to r=%.3f at z=%.2f, wall %.2f there. '
          'Measured on the mesh.'
          % (inner, lo, hi, n['bore'], r_bore, n['len'] + n['lead'], n['wall']))
    return 0


def selftest():
    """Build the two real failure modes and require the guard to catch both."""
    src = open(os.path.join(CAD, SCAD)).read()
    cases = [
        # The collar moved OUT of the post-bore union and into the outer one,
        # which is exactly what happened to the lock boss and to the spigot.
        # The bore subtraction then eats it and the mesh loses the sealing land.
        ('collar-eaten',
         lambda s: s.replace(
             'translate([0, 0, -e]) cylinder(d=tube_id, h=tube_len + 2*e);\n            }',
             '}\n                translate([0, 0, -e]) cylinder(d=tube_id, h=tube_len + 2*e);',
             1)),
        # The lead cone quietly lost, leaving the overhang. Caught upstream by
        # the .scad's own collar_lead assert -- which is the right place for it
        # -- so it does NOT exercise the mesh test below. Kept because the
        # assert is the guard here and an assert that is never seen to fire is
        # not a guard either.
        ('cone-param-zero',
         lambda s: s.replace('collar_lead    = (tube_id - cable_bore_d)/2;',
                             'collar_lead    = 0.001;', 1)),
        # The one that DOES exercise the mesh test: collar_lead stays legal, so
        # every assert in the .scad still passes and the tube still renders as a
        # clean closed solid, but the cone is not in the geometry. This is the
        # shape of every defect in this file's history -- the arithmetic goes on
        # describing a feature the mesh no longer has.
        ('cone-not-drawn',
         lambda s: s.replace(
             '''                    translate([0, 0, cable_bore_len])
                        cylinder(d1=tube_id, d2=cable_bore_d, h=collar_lead);''',
             '', 1)),
    ]
    bad = 0
    for name, patch in cases:
        mutated = patch(src)
        if mutated == src:
            print('SELFTEST INCONCLUSIVE %s: the patch did not apply -- the '
                  'model moved under this test, so it proves nothing' % name)
            bad += 1
            continue
        fd, tmp = tempfile.mkstemp(suffix='.scad', prefix='collar-bad-',
                                   dir=CAD)
        os.close(fd)
        rel = os.path.basename(tmp)
        try:
            open(tmp, 'w').write(mutated)
            try:
                n = model_numbers(rel)
                stl = render_tube(rel)
            except SystemExit as ex:
                # A known-bad that will not even render is still caught, as
                # long as it is caught LOUDLY rather than scored as a pass.
                print('SELFTEST %s: caught at render/echo -- %s'
                      % (name, str(ex).splitlines()[0]))
                continue
            rc = check(stl, n)
            os.unlink(stl)
            if rc == 0:
                print('SELFTEST FAILED %s: the guard PASSED a known-bad tube'
                      % name)
                bad += 1
            else:
                print('SELFTEST %s: caught.' % name)
        finally:
            os.unlink(tmp)
    print('selftest: %s' % ('OK' if not bad else '%d CASE(S) NOT CAUGHT' % bad))
    return 1 if bad else 0


def main():
    if '--selftest' in sys.argv:
        return selftest()
    n = model_numbers()
    path = sys.argv[1] if len(sys.argv) > 1 else render_tube()
    return check(path, n)


if __name__ == '__main__':
    sys.exit(main())
