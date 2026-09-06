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
  2. THE LEAD CONE IS THERE. NOT for support -- the first version of this
     docstring claimed the monobody prints head-end down and that the cone was
     holding up an overhang, and both halves were wrong. It prints CABLE-END
     DOWN (measured in the sliced g-code: the collar's Ø25.5 bore is the first
     12 mm off the plate), so the collar is supported for its whole length and
     the step above it is top-facing. The cone is the BOARD'S LEAD-IN past the
     collar step, and it keeps a sealing land from ending in a sharp internal
     corner. Worth checking because it is easy to delete and nothing else
     would notice -- not because its absence would spiderweb.

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
        # without one OpenSCAD refuses outright. --hardwarnings because an
        # echo can be emitted BEFORE a later failure, and numbers scraped from
        # a run that then died would be paired with whatever stale mesh is on
        # disk -- a pass built from two different versions of the part.
        [OPENSCAD, '--hardwarnings', '--export-format', 'asciistl',
         '-o', os.devnull, '-D', 'part="tube"', scad],
        cwd=CAD, capture_output=True, text=True)
    if r.returncode != 0:
        die('the model did not evaluate (openscad exit %d) -- the COLLAR echo '
            'cannot be trusted even if one was printed, so this is a FAILURE, '
            'not an OK.\n%s' % (r.returncode, (r.stderr or r.stdout)[-2000:]))
    out = r.stdout + r.stderr
    m = re.search(r'COLLAR bore ([\d.]+) len ([\d.]+) lead ([\d.]+)'
                  r' tube_id ([\d.]+) wall ([\d.]+)', out)
    if not m:
        die('the model emitted no COLLAR echo -- cannot evaluate, so this is a '
            'FAILURE, not an OK.\n' + (r.stderr or r.stdout)[-2000:])
    # The O-ring's lead-in at the mouth. Its ABSENCE is a failure, not a default:
    # without it the ring meets a square edge and the cap does not go on, which
    # is what the tube on the bench did on 2026-09-06.
    lead = re.search(r'BORE LEAD-IN: ([\d.]+) deg x ([\d.]+) mm deep, '
                     r'opening the mouth to ([0-9]+\.?[0-9]*)', out)
    if not lead:
        die('the model emitted no BORE LEAD-IN echo. No echo means the mouth '
            'lead-in is not modelled, which is unevaluable, which is a FAILURE.')
    k = [float(x) for x in m.groups()]
    return dict(bore=k[0], len=k[1], lead=k[2], tube_id=k[3], wall=k[4],
                lead_h=float(lead.group(2)), mouth_d=float(lead.group(3)))


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
    # THE BAND STARTS PAST THE LEAD-IN. It used to start at 0.30, which was
    # right while the mouth was a square edge and wrong the moment a chamfer was
    # cut there on 2026-09-06: 0.30 is now ON the chamfer, where the bore is
    # deliberately oversize. Taking a MINIMUM hid that -- the cone's own far end
    # sits at r_bore, so the test passed and would have gone on passing even if
    # the chamfer had eaten the whole sealing land.
    lo, hi = n['lead_h'] + 0.30, n['len'] - 0.30
    if hi <= lo:
        fails.append('collar: length %.3f is too short to test (band interior '
                     'is empty) -- treat as NO COLLAR' % n['len'])
    else:
        inner = min((min(r for r, _ in t) for t in tris
                     if max(z for _, z in t) >= lo
                     and min(z for _, z in t) <= hi),
                    default=float('inf'))
        # BOTH SIDES. The first version asked only `inner > r_bore + 0.05`,
        # which catches a collar that is missing or too shallow and waves
        # through one that is too DEEP -- a bore bored undersize, a radial
        # spoke left across it, a partial collar. Every one of those makes
        # `inner` SMALLER, so the guard got quieter as the part got worse.
        # That is checklist item 2, and this file's own docstring cites the
        # monotonicity rule while the test broke it.
        #
        # Too small is not a cosmetic error either: the reamer would have to
        # take out more than its stock, and short of that the cap's Ø25.2
        # spigot does not enter at all.
        if inner > r_bore + 0.05:
            fails.append(
                'collar: the smallest radius through z %.2f..%.2f is %.3f, not '
                'the %.3f sealing land%s -- the collar is ABSENT or too shallow, '
                'and the ring would sit in open bore'
                % (lo, hi, inner, r_bore,
                   ' (it reads as the plain %.3f bore)' % r_tube
                   if abs(inner - r_tube) < 0.05 else ''))
        elif inner < r_bore - 0.05:
            fails.append(
                'collar: the smallest radius through z %.2f..%.2f is %.3f, '
                '%.3f mm INSIDE the %.3f sealing land -- something stands in '
                'the bore. The reamer has more than its stock to remove, and '
                'until it is reamed the cap spigot does not enter'
                % (lo, hi, inner, r_bore - inner, r_bore))

    # 1b. THE MOUTH IS ACTUALLY OPEN. The land test above is a minimum, so it
    #     cannot tell a chamfered mouth from a square one -- and a square one is
    #     what stopped the cap going on. Ask the mesh directly.
    r_mouth = n['mouth_d'] / 2.0
    face = min((r for r, z in verts if z < 0.05), default=float('inf'))
    if face < r_mouth - 0.10:
        fails.append(
            'mouth: the cable-end face carries material in to r=%.3f, but the '
            'lead-in should open it to r=%.3f. The O-ring stands proud of the '
            '%.3f bore and has to be squeezed in by that ramp; against a square '
            'edge it shaves or rolls and the cap does not seat -- exactly what '
            'the bench found on 2026-09-06.' % (face, r_mouth, r_bore))

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
                     'there is no lead at all, just a square step at the mouth '
                     'of the sealing land' % n['lead'])
    else:
        if not at(n['len'], r_tube):
            fails.append('cone: no material at r=%.3f on z=%.3f -- the cone '
                         'does not start at the tube bore' % (r_tube, n['len']))
        if not at(n['len'] + n['lead'], r_bore):
            fails.append(
                'cone: nothing at r=%.3f on z=%.3f -- the collar ends in a '
                '%.2f mm square step instead of a 45 deg lead -- the board '
                'loses its lead-in past the collar and the sealing land ends '
                'in a sharp internal corner' % (r_bore, n['len'] + n['lead'],
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
        # THE MONOTONICITY CASE. Bore driven UNDERSIZE: renders as a clean
        # closed solid, every seal assert still passes (they are arithmetic on
        # cable_bore_d, which is what moved), and the old test waved it through
        # because `inner` only got smaller. This is the direction the guard was
        # blind in.
        # Note it patches the GEOMETRY, not cable_bore_d: moving the variable
        # trips the seal asserts and the model never renders, so it would be
        # caught for an unrelated reason and the mesh test would go on being
        # unexercised. Cutting the collar's bore 1.5 mm undersize leaves every
        # assert passing and the tube a clean closed solid.
        ('collar-bored-undersize',
         lambda s: s.replace('''                translate([0, 0, -2*e])
                    cylinder(d=cable_bore_d,
                             h=cable_bore_len + collar_lead + 4*e);''',
                             '''                translate([0, 0, -2*e])
                    cylinder(d=cable_bore_d - 1.5,
                             h=cable_bore_len + collar_lead + 4*e);''', 1)),
        # THE MOUTH CHAMFER DELETED. Renders clean, every assert passes (the
        # arithmetic still describes a chamfer), the sealing land is perfect --
        # and the cap does not go on. The exact defect found on the bench.
        ('mouth-chamfer-gone',
         lambda s: s.replace('''                translate([0, 0, -e])
                    cylinder(d1=cable_bore_d + 2*seal_lead_r + 2*e,
                             d2=cable_bore_d, h=bore_lead_h + e);''', '', 1)),
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
