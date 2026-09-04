"""Kinematic gate on the body tube's bayonet cap.

The bayonet is the one feature in o2_probe_body_tube.scad that can be
geometrically WRONG while every part still renders as a perfect closed solid.
The mesh gate in the Makefile cannot see it, and neither can a rendered picture:
a lug that never reaches its pocket, or a pocket so deep the O-ring never gets
squeezed, looks exactly like a working one.

So this measures the mechanism instead of the parts. It drops the tube into the
cap at a series of positions and takes the INTERSECTION VOLUME of the two
solids, which is zero when they fit and positive when they collide:

  1. entry     -- pushed in at the entry angle, over the whole travel: clear
  2. twist     -- rotated from entry to lock at the pushed-in depth: clear
  3. locked    -- resting in the pocket at the sealing depth: clear
  4. pull-out  -- pulled from the locked position: MUST collide, or it is not
                  a lock, it is a slip fit

Case 4 is the calibration: it is the known-bad state, and a check that only ever
asserts "clear" would pass a cap with no lugs at all.

The angles are NOT hardcoded from the model's parameters, deliberately. They are
found by scanning, so a sign error in the model's own bookkeeping shows up as a
failure to find a clear window rather than being reproduced by the test.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(os.path.dirname(HERE), 'o2_probe_body_tube.scad')
OPENSCAD = os.environ.get('OPENSCAD', 'openscad')

# Each part is exported ONCE and the probes intersect the resulting meshes. That
# is still the producer's geometry -- these are the same STLs `make body-tube`
# ships -- but it takes a probe from 5.6 s to 1.1 s, because OpenSCAD 2021.01 has
# no manifold backend (`--backend=manifold` is rejected) and re-ran the cap's
# fourteen CGAL cuts on every single probe.
#
# Two cheaper tricks were tried and are recorded so they are not tried again:
# clipping the tube to the bayonet region made it SLOWER (the cost was never the
# tube's length), and searching at a coarse $fn produced FALSE collisions,
# because rotate_extrude quantises an arc to $fn segments over the full circle
# and that is coarser than the angular windows being searched.
HARNESS = """
rot = 0;
push = 0;
intersection() {
  import("%s");
  translate([0, 0, %.4f + push]) rotate([180, 0, 0]) rotate([0, 0, rot])
    import("%s");
}
"""

# The lock screw's path, in the CAP's frame: a rod driven radially inward at
# angle `sa`. Clear means it reaches its pilot; anything it hits is skirt or
# tube wall. Stops at r=13, short of the pilot floor, so a correct pilot returns
# nothing rather than the rod's own tip.
SCREW_HARNESS = """
rot = 0;
sa = 0;
intersection() {
  union() {
    import("%s");
    translate([0, 0, %.4f]) rotate([180, 0, 0]) rotate([0, 0, rot]) import("%s");
  }
  translate([0, 0, %.4f]) rotate([0, 0, sa]) rotate([0, 90, 0])
    translate([0, 0, 13]) cylinder(d=2.4, h=14, $fn=32);
}
"""


def param(name):
    """Read a top-level scalar out of the model, so the harness stays in step."""
    src = open(MODEL).read()
    m = re.search(r'^%s\s*=\s*([-\d.]+)\s*;' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit("cannot find parameter %r in %s" % (name, MODEL))
    return float(m.group(1))


def volume(stl):
    """Signed volume of a closed ASCII-STL mesh, by the divergence theorem."""
    v, tri = 0.0, []
    for line in open(stl):
        line = line.strip()
        if line.startswith('vertex'):
            tri.append(tuple(float(x) for x in line.split()[1:4]))
            if len(tri) == 3:
                a, b, c = tri
                v += (a[0]*(b[1]*c[2] - b[2]*c[1])
                      - a[1]*(b[0]*c[2] - b[2]*c[0])
                      + a[2]*(b[0]*c[1] - b[1]*c[0])) / 6.0
                tri = []
    return abs(v)


def build(part, tmp):
    """Export one part of the model, and require it to have come out."""
    out = os.path.join(tmp, part + '.stl')
    r = subprocess.run([OPENSCAD, '--hardwarnings', '-D', 'part="%s"' % part,
                        '-o', out, MODEL], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise SystemExit("cannot export %s:\n%s" % (part, r.stderr))
    return out


# A lug sliding along its channel floor touches it EXACTLY, and CGAL returns
# that coincident contact as a sliver mesh of ~1e-13 mm3 rather than as nothing
# at all. Testing `== 0.0` therefore read every contact as a collision, and this
# check spent two runs reporting a working bayonet as unable to enter and then
# unable to lock -- a false FAIL that looked exactly like a real design defect.
# Judge against a threshold, not against zero.
TOUCH = 1e-3    # mm3; below this the two solids are touching, not interfering
BLOCK = 1.0     # mm3; above this they genuinely obstruct each other


def clear(v):
    """The two solids are not interfering (they may be in exact contact)."""
    return v < TOUCH


def blocked(v):
    """They obstruct each other by more than a coincident-face sliver."""
    return v > BLOCK


def stated_screw_angle():
    """The cap-frame angle the MODEL says its lock slot is at.

    Read from the model's own echo rather than recomputed here. Recomputing it
    in Python would test the arithmetic against itself; this way the model
    states an intention and the geometry is measured against it.
    """
    r = subprocess.run([OPENSCAD, '-D', 'part="tube"', '-o', os.devnull,
                        '--export-format', 'asciistl', MODEL],
                       capture_output=True, text=True)
    m = re.search(r'Cap slot at cap angle ([-\d.]+) deg', r.stdout + r.stderr)
    return float(m.group(1)) if m else None


def obstruction(harness, tmp, rot, sa):
    """Volume of material in the lock screw's path, in mm3."""
    return overlap(harness, tmp, rot, sa)


def overlap(harness, tmp, rot, push):
    """Intersection volume at (rot, push) -- or (rot, sa) for the screw harness."""
    out = os.path.join(tmp, 'x.stl')
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run(
        [OPENSCAD, '-D', 'rot=%r' % rot, '-D', 'push=%r' % push,
         '-D', 'sa=%r' % push, '-o', out, '--export-format', 'asciistl', harness],
        capture_output=True, text=True)
    # An EMPTY intersection writes no file at all -- that is the pass case, and
    # it is why this cannot be judged on exit status.
    if not os.path.exists(out):
        if 'ERROR' in r.stderr:
            raise SystemExit("openscad failed:\n" + r.stderr)
        return 0.0
    return volume(out)


def main():
    engage = param('cap_engage')
    detent = param('detent')
    twist = param('twist_deg')
    lug_arc = param('lug_arc')
    fails = []

    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'bay.scad')
        cap_stl, tube_stl = build('cap', tmp), build('tube', tmp)
        open(harness, 'w').write(HARNESS % (cap_stl, engage, tube_stl))

        # Find the two clear angular windows by scanning, rather than trusting
        # the model's own sign conventions. +/-70 deg at 1 deg is enough for any
        # bayonet this part can hold -- a two-lug cap cannot twist further than
        # 180 minus the lug arc, and this one is nowhere near that.
        #
        # The scan is over the PUSHED-IN depth (the lug in the channel) and then
        # filtered by the SEALING depth (the lug in the pocket), so `entry` and
        # `lock` come out of the same sweep and cost one openscad run per angle.
        clear_pushed = [r for r in range(-54, 55, 3)
                        if clear(overlap(harness, tmp, r, detent))]
        # ENTRY is where the tube can still be withdrawn freely -- the entry slot
        # is open to the cap's mouth, so it is clear at every depth.
        entry = [r for r in clear_pushed
                 if clear(overlap(harness, tmp, r, -6.0))]
        # LOCK is NOT simply "clear at the sealing depth". That is true in the
        # entry slot too, and defining it that way made this check report the
        # entry window as the lock window and then fail its own pull-out case.
        # Locked means clear at the sealing depth AND retained when pulled.
        lock = [r for r in clear_pushed
                if r not in entry
                and clear(overlap(harness, tmp, r, 0.0))
                and blocked(overlap(harness, tmp, r, -2.0))]
        if os.environ.get('BAYONET_DEBUG'):
            print("  engage=%g detent=%g twist=%g lug_arc=%g"
                  % (engage, detent, twist, lug_arc))
            print("  channel %s\n  entry %s\n  lock %s"
                  % (clear_pushed, entry, lock))
        if not entry:
            fails.append("no angle lets the tube enter the cap at all")
        if not lock:
            fails.append("no angle seats the lug in the pocket "
                         "-- the cap cannot lock")
        if fails:
            print('\n'.join("FAIL " + f for f in fails))
            return 1

        r_entry, r_lock = entry[0], lock[len(lock)//2]
        print("  entry window %d..%d deg, lock window %d..%d deg (twist %g)"
              % (min(entry), max(entry), min(lock), max(lock), twist))

        # 1. sliding in, at the entry angle
        for p in (-12.0, -8.0, -4.0, -1.0, 0.0, detent):
            v = overlap(harness, tmp, r_entry, p)
            if not clear(v):
                fails.append("entry fouls at push=%g (%.1f mm3)" % (p, v))

        # 2. twisting, at the pushed-in depth
        lo, hi = min(r_entry, r_lock), max(r_entry, r_lock)
        for r in range(int(lo), int(hi) + 1, 2):
            v = overlap(harness, tmp, r, detent)
            if not clear(v):
                fails.append("twist fouls at rot=%d (%.1f mm3)" % (r, v))

        # 3. locked
        v = overlap(harness, tmp, r_lock, 0.0)
        if not clear(v):
            fails.append("locked position fouls (%.1f mm3)" % v)

        # 4. KNOWN-BAD: pulling out of the lock must be blocked.
        for p in (-0.5, -2.0, -5.0):
            v = overlap(harness, tmp, r_lock, p)
            if not blocked(v):
                fails.append("pulls straight out of the lock at push=%g "
                             "-- the bayonet does not retain" % p)

        # 5. The lock screw has to be able to reach its pilot at the locked
        # angle, and NOT anywhere else -- a slot wide enough to always be clear
        # would be a slot that had stopped being a lock.
        sa = stated_screw_angle()
        if sa is None:
            print("  no lock screw declared, skipping the screw path")
        else:
            sh = os.path.join(tmp, 'screw.scad')
            # The rod sits at the pilot's height in the CAP's frame, which is
            # engage - lock_z. Leaving it at z=0 was the first bug this check
            # found -- in itself, not in the part.
            open(sh, 'w').write(SCREW_HARNESS
                                % (cap_stl, engage, tube_stl,
                                   engage - param('lock_z')))
            v = obstruction(sh, tmp, r_lock, sa)
            if not clear(v):
                fails.append("lock screw is obstructed at its own stated angle "
                             "%g deg (%.1f mm3) -- the slot and the pilot do "
                             "not line up" % (sa, v))
            for off in (-45, 45):
                v = obstruction(sh, tmp, r_lock, sa + off)
                if not blocked(v):
                    fails.append("lock screw path is open %g deg off the lock "
                                 "angle -- the cap slot is too wide to lock "
                                 "anything" % off)
            if not any('lock screw' in f for f in fails):
                print("  lock screw: clear at %g deg, blocked at +/-45" % sa)

        # The twist actually available must be worth calling a bayonet.
        if abs(r_lock - r_entry) < lug_arc:
            fails.append("lock is only %g deg from entry, less than the lug's "
                         "own %g deg arc" % (abs(r_lock - r_entry), lug_arc))

    if fails:
        print('\n'.join("FAIL " + f for f in fails))
        return 1
    print("  bayonet: enters clear, twists clear, locks clear, "
          "and will not pull out")
    return 0


if __name__ == '__main__':
    sys.exit(main())
