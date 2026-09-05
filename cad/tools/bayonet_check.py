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
import math
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


# The ramp feeler. A thin pin standing on the pocket floor at the lug's mean
# contact radius: everything above the pocket's ceiling is cap skirt, so the
# solid it meets converts straight into a ceiling height. `push` carries the
# cap-frame ANGLE here -- overlap() only ever sets rot/push/sa.
FEEL_R = 17.0       # between the slot's r0 (16.2) and r1 (17.95)
# A SQUARE pin, not a cylinder. A cylinder has to be faceted, and a $fn=16
# 16-gon inscribed in O0.4 has 2.5 % less area than pi*r^2 -- which over a 4 mm
# pin is 0.1 mm of apparent ceiling, exactly the tolerance being tested. A cube
# has the area it says it has.
FEEL_W = 0.4
FEEL_LEN = 4.0      # from the pocket floor, past the tallest ceiling
FEEL_AREA = FEEL_W * FEEL_W
FEELER = """
rot = 0;
push = 0;
sa = 0;
intersection() {
  import("%s");
  rotate([0, 0, push])
    translate([%.3f - %.3f/2, -%.3f/2, %.4f])
      cube([%.3f, %.3f, %.3f]);
}
"""


def flag(name):
    """Read a top-level boolean out of the model. param() only sees numbers."""
    m = re.search(r'^%s\s*=\s*(true|false)\s*;' % re.escape(name),
                  open(MODEL).read(), re.M)
    return None if not m else m.group(1) == 'true'


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


def build(part, tmp, extra=(), tag=None):
    """Export one part of the model, and require it to have come out.

    `extra` is a list of -D overrides, used for the ramp's known-bad control:
    the SAME part, built with the closure switched off, so the calibration
    differs from the real cap in exactly one quantity.
    """
    out = os.path.join(tmp, (tag or part) + '.stl')
    r = subprocess.run([OPENSCAD, '--hardwarnings', '-D', 'part="%s"' % part]
                       + [a for d in extra for a in ('-D', d)]
                       + ['-o', out, MODEL], capture_output=True, text=True)
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

# BLOCK IS A COLLISION TEST, NOT A RETENTION TEST, and using it as one was a
# real hole. The 2026-09-05 Codex review, finding 5:
#
#     `BLOCK=1 mm3` is conservative for detecting a collision but has no
#     demonstrated relationship to mechanical retention -- a paper-thin tongue
#     exceeding 1 mm3 qualifies.
#
# Measured on this geometry: two full lugs sweep 20.6 mm2, so a 2 mm pull should
# interfere by ~41 mm3. A lug shrunk to a 0.3 mm tongue sweeps 1.86 mm2 and gives
# 7.4 mm3 -- over BLOCK by a factor of seven, and not a lock. So retention is
# judged against the lug's OWN section, and the thin tongue is built and required
# to fail (see RETAIN_FRAC below).
RETAIN_FRAC = 0.60   # of the ideal two-lug swept volume at the pull depth
RETAIN_PULL = 2.0    # mm, the depth retention is weighed at
THIN_LUG_R = 0.3     # mm, the known-bad tongue

# HOW FINELY THE MECHANISM IS SAMPLED. Discovery stays coarse because it is a
# search; everything that makes a CLAIM is re-sampled at 1 deg or 1 mm. The same
# finding, on the same page:
#
#     A sub-2 deg obstruction between twist samples passes; conversely, a single
#     sampled clear angle is accepted as a lock window even if its real width is
#     effectively unassemblable.
FINE = 1             # deg, for every sweep that asserts
ENTRY_MIN_DEG = 6    # a window narrower than this cannot be found by hand
POCKET_MIN_DEG = 6


def clear(v):
    """The two solids are not interfering (they may be in exact contact)."""
    return v < TOUCH


def blocked(v):
    """They obstruct each other by more than a coincident-face sliver."""
    return v > BLOCK


# The lock pilot, measured on the tube's own mesh. A rod is driven along the
# screw axis and the material it meets is weighed.
PILOT_HARNESS = """
rot = 0;
push = 0;
r0 = rot;   // overlap() only ever sets rot/push/sa, so the rod's two radii
r1 = push;  // ride in on those. Reusing them beats a fourth -D name.
intersection() {
  import("%s");
  translate([0, 0, %.4f]) rotate([0, 0, %.4f]) rotate([0, 90, 0])
    translate([0, 0, r0]) cylinder(d=%.2f, h=r1 - r0, $fn=32);
}
"""


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
        # SEATED is NOT simply "clear at the sealing depth". That is true in the
        # entry slot too, and defining it that way made this check report the
        # entry window as the lock window and then fail its own pull-out case.
        # Seated means clear at the sealing depth AND retained when pulled.
        #
        # It is called seated rather than locked because with the wedge ramp
        # fitted it is only the FREE part of the pocket -- where the lug has
        # dropped in but has not yet met the closing wall. The lock is further
        # round, and is found by case 7 below rather than assumed to be the
        # middle of this window.
        seated = [r for r in clear_pushed
                  if r not in entry
                  and clear(overlap(harness, tmp, r, 0.0))
                  and blocked(overlap(harness, tmp, r, -2.0))]
        if os.environ.get('BAYONET_DEBUG'):
            print("  engage=%g detent=%g twist=%g lug_arc=%g"
                  % (engage, detent, twist, lug_arc))
            print("  channel %s\n  entry %s\n  seated %s"
                  % (clear_pushed, entry, seated))
        if not entry:
            fails.append("no angle lets the tube enter the cap at all")
        if not seated:
            fails.append("no angle seats the lug in the pocket "
                         "-- the cap cannot lock")
        if fails:
            print('\n'.join("FAIL " + f for f in fails))
            return 1

        # THE WINDOWS MUST BE WIDE ENOUGH TO FIND BY HAND. Discovery ran at
        # 3 deg, so a "window" of one sample could be 1 deg wide in reality.
        # Re-walk each one outward at FINE resolution and measure it.
        def width(centre, depth, pred, need):
            """How wide the window is, walked at FINE -- but STOPS once `need`
            is proven.

            The first version walked to the window's real edges and cost up to
            360 probes at ~1.1 s each, which took this check from three minutes
            to over seven. The claim being made is "at least `need` degrees
            wide", so the walk stops as soon as that is established. It reports
            `>=` in that case, and the exact edges only when the window really
            is narrower than needed -- which is the case where the number
            matters."""
            lo = hi = centre
            room = need + FINE
            while centre - lo < room and pred(overlap(harness, tmp,
                                                      lo - FINE, depth)):
                lo -= FINE
            while (hi - lo) < room and pred(overlap(harness, tmp,
                                                    hi + FINE, depth)):
                hi += FINE
            return lo, hi

        e_lo, e_hi = width(entry[len(entry)//2], -6.0, clear, ENTRY_MIN_DEG)
        if e_hi - e_lo < ENTRY_MIN_DEG:
            fails.append("the entry window is only %d deg wide (%d..%d); "
                         "below %d deg it cannot be found by feel with the "
                         "tube in one hand"
                         % (e_hi - e_lo, e_lo, e_hi, ENTRY_MIN_DEG))
        p_lo, p_hi = width(seated[len(seated)//2], 0.0, clear, POCKET_MIN_DEG)
        if p_hi - p_lo < POCKET_MIN_DEG:
            fails.append("the pocket accepts the lug over only %d deg "
                         "(%d..%d), against %d needed"
                         % (p_hi - p_lo, p_lo, p_hi, POCKET_MIN_DEG))
        print("  measured at %d deg: entry window >=%d deg, pocket >=%d deg "
              "(walked only far enough to prove %d and %d)"
              % (FINE, e_hi - e_lo, p_hi - p_lo, ENTRY_MIN_DEG, POCKET_MIN_DEG))

        r_entry = entry[0]
        # 7. THE WEDGE RAMP, and it has to be measured before anything else uses
        # a lock angle, because with a ramp the lock is where the wall bites --
        # not the middle of the free pocket.
        #
        # The signature of a wedge is a BAND of angles where the two solids
        # interfere by a little and not by a lot: below TOUCH they are not
        # touching, above BLOCK the lug has run into the pocket's far wall and
        # the cap has stopped. A flat pocket has no such band -- it goes from
        # clear straight to blocked in about a degree.
        ramp_on = flag('ramp')
        if not ramp_on:
            r_lock = seated[len(seated)//2]
            print("  entry window %d..%d deg, lock window %d..%d deg"
                  % (min(entry), max(entry), min(seated), max(seated)))
        else:
            # MEASURE THE RAMP ITSELF, not the lug's interference with it. The
            # first attempt probed the interference band and it was the wrong
            # instrument: closure starts from the pocket's full height, so the
            # band is only ramp_interf/rate wide -- 3 deg here -- and a 3 deg
            # band cannot be told apart from a hard stop.
            #
            # This drives a thin pin down the pocket at a series of angles and
            # weighs the SOLID it meets. The pin spans FEEL_LEN from the pocket
            # floor, so everything above the ceiling is cap material and
            #     ceiling height = FEEL_LEN - solid/area
            # comes straight off the mesh, in millimetres, one probe per angle.
            pocket_z = engage - param('lug_z') - param('lug_h')/2
            fh_feel = os.path.join(tmp, 'feel.scad')
            feeler = lambda stl: (FEELER % (stl, FEEL_R, FEEL_W, FEEL_W,
                                            pocket_z, FEEL_W, FEEL_W, FEEL_LEN))
            open(fh_feel, 'w').write(feeler(cap_stl))

            def ceiling(hs, a):
                v = overlap(hs, tmp, 0.0, a)
                return FEEL_LEN - v/FEEL_AREA

            # pocket_extra and ramp_close are DERIVED in the model, so param()
            # cannot read them; rebuild from the primitives it can see. That is
            # duplicated arithmetic, and it is deliberate: the ANGLES only say
            # where to look, and every claim below is measured off the mesh.
            ramp_deg = param('ramp_deg')
            ramp_close = detent + param('slot_slack') - param('ramp_clear')
            a0 = -param('twist_deg') - (param('ramp_free') + ramp_deg)
            a_ramp = a0 + ramp_deg
            # INSET 1 deg FROM BOTH POCKET WALLS. The first version probed at
            # exactly pocket_a0 and the pin straddled the far wall, half in
            # solid -- which read as a 1.50 mm ceiling and ALSO made the flat
            # control vary by 1.78 mm. A probe that fails on the known-good
            # part and on the known-bad part alike is measuring the fixture.
            free = [a_ramp + 8, a_ramp + 4, a_ramp + 1]
            ramped = [a_ramp - ramp_deg*k/4.0 for k in (1, 2, 3)] + [a0 + 1]
            angles = free + ramped
            prof = [(a, ceiling(fh_feel, a)) for a in angles]
            if os.environ.get('BAYONET_DEBUG'):
                print("  ramp profile %s"
                      % [(a, round(h, 3)) for a, h in prof])

            full = param('lug_h') + param('slot_slack') + detent
            # The free pocket must be at FULL height -- if it is not, the lug
            # cannot drop off the detent step and there is no seated state.
            for a, hgt in prof[:len(free)]:
                if abs(hgt - full) > 0.08:
                    fails.append("the pocket is %.2f mm tall at %g deg, not the "
                                 "%.2f it must be for the lug to drop in"
                                 % (hgt, a, full))
            # And it must close, monotonically, ALONG THE DESIGNED RAMP. Compared
            # against the ideal ramp at each angle rather than only at the end,
            # so a ramp with the right endpoints and the wrong middle fails too.
            # 0.12 covers the 0.05 mm staircase riser and mesh noise.
            hs = [h for _, h in prof[len(free) - 1:]]
            for x, y in zip(hs, hs[1:]):
                if y > x + 0.02:
                    fails.append("the ramp rises as the cap is twisted in "
                                 "(%.2f -> %.2f mm): it is not a wedge" % (x, y))
                    break
            for a, hgt in prof[len(free):]:
                want = full - ramp_close * min(1.0, (a_ramp - a)/ramp_deg)
                if abs(hgt - want) > 0.12:
                    fails.append("the pocket is %.2f mm at %g deg where the ramp "
                                 "designs %.2f -- it is missing, flattened, or "
                                 "swept the wrong way" % (hgt, a, want))

            # KNOWN-BAD CALIBRATION: the SAME cap with one quantity changed.
            # ramp_close=0 leaves the pocket's arc, depth and floor identical
            # and only stops the deep wall descending. If the flat control also
            # reads as closing, this probe is measuring facets, not the ramp.
            flat_stl = build('cap', tmp, extra=['ramp_close=0'], tag='cap-flat')
            fh2 = os.path.join(tmp, 'feel-flat.scad')
            open(fh2, 'w').write(feeler(flat_stl))
            flat = [ceiling(fh2, a) for a in angles]
            if os.environ.get('BAYONET_DEBUG'):
                print("  flat control %s" % [round(h, 3) for h in flat])
            if max(flat) - min(flat) > 0.1:
                fails.append("the KNOWN-BAD flat pocket (ramp_close=0) varies by "
                             "%.2f mm across the same angles -- this check is "
                             "measuring facets, not the wedge"
                             % (max(flat) - min(flat)))

            # The lock angle is MEASURED: the furthest the cap can still be
            # twisted before the lug runs into the far wall. Not read from the
            # model, which is what the screw case below is testing.
            r_lock = max(seated)
            while r_lock < max(seated) + 20:
                if blocked(overlap(harness, tmp, r_lock + 1, 0.0)):
                    break
                r_lock += 1
            if fails:
                print('\n'.join("FAIL " + f for f in fails))
                return 1
            print("  entry window %d..%d deg, free pocket from %d deg, wedge "
                  "closes %.2f -> %.2f mm, cap stops at %d deg"
                  % (min(entry), max(entry), min(seated), full, hs[-1], r_lock))

        # 1. sliding in, at the entry angle
        # Every millimetre of the travel, not six chosen depths: a 2 mm-deep
        # obstruction sat between -12 and -8 in the old ladder and passed.
        depths = [-d for d in range(12, 0, -1)] + [0.0, detent]
        for p in depths:
            v = overlap(harness, tmp, r_entry, p)
            if not clear(v):
                fails.append("entry fouls at push=%g (%.1f mm3)" % (p, v))

        # 2. Twisting, at the PUSHED-IN depth, as far as the pocket. It stops at
        # the seated window and not at r_lock: past that the lug has dropped into
        # the pocket and travels at push=0, and probing the ramp at push=detent
        # would report the wedge -- which is there on purpose -- as a foul.
        r_seat = max(seated) if ramp_on else r_lock
        lo, hi = min(r_entry, r_seat), max(r_entry, r_seat)
        for r in range(int(lo), int(hi) + 1, FINE):
            v = overlap(harness, tmp, r, detent)
            if not clear(v):
                fails.append("twist fouls at rot=%d (%.1f mm3)" % (r, v))

        # 2b. And the rest of the travel, at the SEALING depth, where the lug is
        # in the pocket running up the ramp. It must tighten, never jam: nothing
        # before the stop may reach BLOCK, or the cap binds short of home.
        if ramp_on:
            for r in range(int(r_seat), int(r_lock) + 1):
                v = overlap(harness, tmp, r, 0.0)
                if blocked(v):
                    fails.append("the cap jams at rot=%d (%.1f mm3), short of "
                                 "the %d deg it is supposed to reach"
                                 % (r, v, r_lock))
                    break

        # 3. locked
        v = overlap(harness, tmp, r_lock, 0.0)
        if not clear(v):
            fails.append("locked position fouls (%.1f mm3)" % v)

        # 4. RETENTION, weighed against the lug's own section rather than
        # against BLOCK. Pulling out must be obstructed by something that could
        # actually hold, not merely by something detectable.
        lug_r_v = param('lug_r')
        rr0 = param('tube_od')/2
        rr1 = rr0 + lug_r_v
        lug_area = (param('lug_arc')/360.0) * math.pi * (rr1**2 - rr0**2)
        ideal = param('lug_n') * lug_area * RETAIN_PULL
        floor = RETAIN_FRAC * ideal
        for p in (-0.5, -RETAIN_PULL, -5.0):
            v = overlap(harness, tmp, r_lock, p)
            if not blocked(v):
                fails.append("pulls straight out of the lock at push=%g "
                             "-- the bayonet does not retain" % p)
        v_ret = overlap(harness, tmp, r_lock, -RETAIN_PULL)
        if v_ret < floor:
            fails.append("only %.1f mm3 of lug is in the way at a %g mm pull, "
                         "against %.1f mm3 of ideal section and a %.1f mm3 "
                         "floor -- there is something there, but not enough of "
                         "it to be a lock" % (v_ret, RETAIN_PULL, ideal, floor))

        # 4b. KNOWN-BAD CALIBRATION for that floor: the same tube with the lug
        # shrunk to a tongue. It still collides -- it would sail past a bare
        # BLOCK test -- and it must fail the retention floor. If it passes, the
        # floor is decoration.
        thin_stl = build('tube', tmp, extra=['lug_r=%g' % THIN_LUG_R],
                         tag='tube-thin')
        th = os.path.join(tmp, 'thin.scad')
        open(th, 'w').write(HARNESS % (cap_stl, engage, thin_stl))
        v_thin = overlap(th, tmp, r_lock, -RETAIN_PULL)
        if v_thin >= floor:
            fails.append("the KNOWN-BAD %g mm tongue also clears the retention "
                         "floor (%.1f >= %.1f mm3) -- the floor does not "
                         "separate a lock from a lip"
                         % (THIN_LUG_R, v_thin, floor))
        elif not blocked(v_thin):
            notes_thin = ("  (the %g mm tongue does not even register as a "
                          "collision, so this calibration is weaker than "
                          "intended)" % THIN_LUG_R)
            print(notes_thin)
        if not any('lock' in f or 'retention' in f or 'lug' in f
                   for f in fails):
            print("  retention: %.1f mm3 of lug at a %g mm pull (floor %.1f, "
                  "ideal %.1f); the %g mm tongue gives %.1f and fails as it "
                  "should" % (v_ret, RETAIN_PULL, floor, ideal, THIN_LUG_R,
                              v_thin))

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

        # 6. THE LOCK PILOT, on the mesh rather than on the declared numbers.
        # The assert in the model compares lock_pilot_floor with lock_boss_r --
        # two things it was told, not two things it built -- and it passed
        # cleanly while the tube shipped with the boss eaten by the bore and the
        # pilot straight through the wall into the sealed volume. Weigh what is
        # actually there.
        try:
            boss_r = param('lock_boss_r')
            floor_r = param('lock_pilot_floor')
            pilot_d = param('lock_pilot_d')
            a_tube = param('lock_a_tube')
            z = param('lock_z')
            od = param('tube_od')
        except SystemExit:
            boss_r = None
        if boss_r is not None:
            ph = os.path.join(tmp, 'pilot.scad')
            open(ph, 'w').write(PILOT_HARNESS % (tube_stl, z, a_tube, pilot_d - 0.1))
            rod = math.pi * ((pilot_d - 0.1)/2)**2

            # Inboard of the pilot floor must be SOLID -- that is the boss, and
            # it is the only thing between the screw and the sealed volume.
            lo, hi = boss_r + 0.1, floor_r - 0.1
            v = overlap(ph, tmp, lo, hi)
            want = rod * (hi - lo)
            # 0.97, not the 0.90 this shipped with. At 0.90 a coaxial Ø0.75
            # THROUGH-CHANNEL removes 1.24 mm3 of a 12.67 mm3 rod -- 9.8 % --
            # and passes, certifying an enclosure with compost connected
            # straight to the bore. The 2026-09-05 Codex review constructed
            # exactly that. Calibrated, not guessed: the sound part measures
            # 99.2 % (the 0.8 % is faceting, rod at $fn=32 against a 128-gon
            # boss), and the Ø0.75 channel measures 90.2 %, so 0.97 separates
            # them with room either side.
            # ITS LIMIT, stated rather than left to be discovered: a channel
            # below about Ø0.4 removes under 3 % and would still pass this rod.
            # The THIN probe below is what covers that.
            if v < 0.97 * want:
                fails.append("only %.1f of %.1f mm3 of boss under the pilot "
                             "(r %.1f..%.1f, %.1f%%) -- the bore has eaten it, "
                             "or something is bored through it, and the screw "
                             "hole vents the sealed volume"
                             % (v, want, lo, hi, 100 * v / want))

            # A THIN rod on the same axis. The realistic defect -- a pilot cut
            # too deep -- removes this one entirely, and so does any coaxial
            # channel wide enough to matter, because it is narrower than the
            # channel rather than wider.
            open(ph, 'w').write(PILOT_HARNESS % (tube_stl, z, a_tube, 0.6))
            thin = math.pi * 0.3 ** 2
            v = overlap(ph, tmp, lo, hi)
            if v < 0.98 * thin * (hi - lo):
                fails.append("the material under the pilot is not solid on its "
                             "own axis (%.2f of %.2f mm3) -- there is a channel "
                             "through it" % (v, thin * (hi - lo)))
            open(ph, 'w').write(PILOT_HARNESS % (tube_stl, z, a_tube, pilot_d - 0.1))

            # Outboard of it must be OPEN -- otherwise there is no pilot.
            lo, hi = floor_r + 0.1, od/2 - 0.1
            v = overlap(ph, tmp, lo, hi)
            if not clear(v):
                fails.append("the pilot is blocked over r %.1f..%.1f "
                             "(%.1f mm3) -- no hole was cut" % (lo, hi, v))
            if not any('pilot' in f or 'boss' in f for f in fails):
                print("  lock pilot: blind, %.1f mm of boss under it"
                      % (floor_r - boss_r))

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
