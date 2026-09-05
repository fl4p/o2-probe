"""Compare the numbers o2_probe_head_end.scad duplicates from the body model.

The two models cannot include each other -- the head asserts on four unmeasured
inputs and refuses to load, and both files define the same names ($fn, part,
board_w, board_t, e) -- so the head restates the handful of body dimensions it
needs to place the tube and the cap. Restated numbers drift.

They already had. On 2026-09-05 `cap_engage` moved 12 -> 18 in the body when the
radial seal pushed the lock boss past the reamer; the head kept 12, and the
prototype drawing placed the cap 6 mm into the tube. Every gate passed: the
parts are separate solids in that view, so no mesh check could see it, and the
picture looked right.

`body_tube_len` was worse, because it was WRONG AND HARMLESS: the head held 127
while the monolithic tube was 113, and `socket_len - 127` happens to equal
`-113`. It placed the tube correctly by coincidence, and would have stopped the
day either number moved.

So: read both files, compare, exit non-zero on disagreement. No geometry, no
rendering -- this is a text check, and that is the point. It is cheap enough to
run in every build.
"""
import os
import re
import struct
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
BODY = os.path.join(CAD, 'o2_probe_body_tube.scad')
HEAD = os.path.join(CAD, 'o2_probe_head_end.scad')
OUT = os.path.join(CAD, 'exports')
OPENSCAD = os.environ.get('OPENSCAD', 'openscad')
# The head's provisional MEASURE inputs, the same four the Makefile supplies.
# It refuses to load without them, which is deliberate and not this file's
# business to work around -- so they are passed, not defaulted away.
# The head's provisional MEASURE inputs plus the process claims its seal gates
# require -- i.e. the Makefile's ASA set, read from the Makefile rather than
# copied, so this file cannot render a different head than `make` does.
def _asa_flags():
    r = subprocess.run(['make', '-s', 'print-ASA'], cwd=CAD,
                       capture_output=True, text=True)
    val = r.stdout.strip() if r.returncode == 0 else ''
    if not val:
        raise SystemExit("interface_check: cannot read ASA from cad/Makefile")
    return shlex.split(val)


PROV = _asa_flags()


_iface = {}


def head_interface(name, joint='bonded'):
    """A number the head prints on its `INTERFACE ...` echo line.

    scalar() below can only read a plain literal, and it says so rather than
    guessing -- which is right, but it means a value that becomes DERIVED drops
    out of the comparison entirely and the two models can then drift unchecked.
    cav_board_len did exactly that on 2026-09-05 when the standing cell made it
    solve against the retainer screws. So derived interface numbers are read from
    a render instead: one openscad call, cached, parsed off a line whose spelling
    the model's own comment pins."""
    if joint not in _iface:
        r = subprocess.run([OPENSCAD] + PROV + ['-D', 'joint="%s"' % joint,
                           '-D', 'part="cavity"', '--export-format', 'asciistl',
                           '-o', os.devnull, HEAD],
                           capture_output=True, text=True)
        m = re.search(r'INTERFACE ([^"]*)', r.stdout + r.stderr)
        if not m:
            return None
        toks = m.group(1).split()
        _iface[joint] = dict(zip(toks[0::2], toks[1::2]))
    try:
        return float(_iface[joint][name])
    except (KeyError, ValueError):
        return None


def verts(path):
    """Vertices of an STL, binary or ASCII. Both are produced in this repo."""
    data = open(path, 'rb').read()
    n = struct.unpack('<I', data[80:84])[0] if len(data) >= 84 else 0
    if n and len(data) == 84 + n * 50:
        for i in range(n):
            v = struct.unpack_from('<9f', data, 84 + i * 50 + 12)
            yield v[0:3]; yield v[3:6]; yield v[6:9]
        return
    for line in data.decode('utf-8', 'replace').splitlines():
        if line.strip().startswith('vertex'):
            yield tuple(float(x) for x in line.split()[1:4])


def mesh_volume(path):
    """Signed volume by the divergence theorem."""
    v, tri = 0.0, []
    for p in verts(path):
        tri.append(p)
        if len(tri) == 3:
            a, b, c = tri
            v += (a[0]*(b[1]*c[2] - b[2]*c[1])
                  - a[1]*(b[0]*c[2] - b[2]*c[0])
                  + a[2]*(b[0]*c[1] - b[1]*c[0])) / 6.0
            tri = []
    return abs(v)


def fusion():
    """Weigh the monobody against its parts.

    This is the OTHER half of the 2026-09-05 review's finding 7, and text
    comparison cannot reach it. The Makefile gates the monobody on CGAL saying
    `Volumes: 2`, and the reviewer built the control that shows what that does
    not prove: two cylinders merely SHARING A FACE also report 2, a 0.001 mm gap
    reports 3, a 0.001 mm overlap reports 2. So the gate separates a gap from
    contact and cannot separate contact from interpenetration -- and a stale
    tube LONGER than the head expects overlaps it, deletes real material, and
    still reports 2.

    Volume separates them. Two solids meeting on one plane conserve volume when
    unioned; overlapping ones do not:

        vol(monobody) == vol(head) + vol(tube)   fused or touching -- ok
        vol(monobody) <  vol(head) + vol(tube)   interpenetrating  -- FAIL

    Returns a list of failure strings, and prints what it measured either way.
    It found a stale monobody the first time it ran: 54071.6 against 48188.2,
    a +5883 mm3 excess that was exactly the ASA a socket_len change had removed
    from a head the mesh predated.
    """
    mono = os.path.join(OUT, 'body-monobody.stl')
    tube = os.path.join(OUT, 'body-tube.stl')
    for f in (mono, tube):
        if not os.path.exists(f):
            print("  -- %s not built; skipping the fusion test"
                  % os.path.basename(f))
            return []
    head_stl = os.path.join(OUT, '.iface-head.stl')
    r = subprocess.run([OPENSCAD, '--hardwarnings'] + PROV
                       + ['-D', 'joint="monolithic"', '-D', 'part="head"',
                          '-o', head_stl, HEAD],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(head_stl):
        return ["could not build the head alone for the fusion test:\n"
                + r.stderr[-400:]]
    vh, vt, vm = mesh_volume(head_stl), mesh_volume(tube), mesh_volume(mono)
    os.remove(head_stl)
    want = vh + vt
    slack = 0.001 * want
    print("  fusion: head %.1f + tube %.1f = %.1f, monobody %.1f (%+.1f mm3)"
          % (vh, vt, want, vm, vm - want))
    if vm < want - slack:
        return ["the monobody is %.1f mm3 SMALLER than head plus tube (%.2f %%):"
                " they interpenetrate rather than meet. CGAL still reports one"
                " closed solid -- exactly what `Volumes: 2` cannot see."
                % (want - vm, 100 * (want - vm) / want)]
    if vm > want + slack:
        return ["the monobody is %.1f mm3 LARGER than head plus tube: one of the"
                " three meshes is not what it claims -- most likely one of them"
                " is STALE and predates a change to the others." % (vm - want)]
    return []


def scalar(path, name):
    """A top-level `name = <number>;` assignment. Returns None if it is not a
    plain literal -- a computed value is not something this check can compare,
    and silently treating it as absent would be worse than saying so."""
    m = re.search(r'^%s\s*=\s*([-\d.]+)\s*;' % re.escape(name),
                  open(path).read(), re.M)
    return float(m.group(1)) if m else None


def body_tube_len(joint):
    """The body model derives it; recompute the same way rather than parsing a
    value that is not written down as one."""
    bl = scalar(BODY, 'board_len')
    cav = scalar(BODY, 'cav_board_len')
    tail = scalar(BODY, 'tail_len')
    sock = scalar(BODY, 'head_socket_len')
    if None in (bl, cav, tail, sock):
        return None
    return bl - cav + tail - (sock if joint == 'monolithic' else 0)


def ternary(path, name, joint):
    """A `name = monolithic ? A : B;` assignment, resolved to one branch.

    socket_len became conditional on 2026-09-05 -- 3.0 monolithic, 14.0 bonded,
    because in a head with no socket the 14 was only a coordinate. scalar()
    cannot see a ternary and returns None, which this file reports as `??` and
    counts as a failure rather than skipping: a check that quietly stops
    covering a number is worse than no check. This is the read that keeps it
    covered.
    """
    m = re.search(r'^%s\s*=\s*monolithic\s*\?\s*(-?[\d.]+)\s*:\s*(-?[\d.]+)\s*;'
                  % re.escape(name), open(path).read(), re.M)
    if not m:
        return None
    return float(m.group(1) if joint == 'monolithic' else m.group(2))


def head_tube_len(joint):
    """The head writes it as a ternary on `monolithic`."""
    m = re.search(r'^body_tube_len\s*=\s*monolithic\s*\?\s*([\d.]+)\s*:\s*([\d.]+)\s*;',
                  open(HEAD).read(), re.M)
    if not m:
        return None
    return float(m.group(1) if joint == 'monolithic' else m.group(2))


def main():
    checks = [
        ("tube_id",
         (lambda od, w: None if None in (od, w) else od - 2 * w)(
             scalar(BODY, 'tube_od'), scalar(BODY, 'wall')),
         scalar(HEAD, 'body_tube_id')),
        ("cap_engage",
         scalar(BODY, 'cap_engage'), scalar(HEAD, 'body_cap_engage')),
        ("seal_id",
         scalar(BODY, 'seal_id'), scalar(HEAD, 'body_seal_id')),
        ("seal_cord",
         scalar(BODY, 'seal_cord'), scalar(HEAD, 'body_seal_cord')),
        ("head_socket_len",
         scalar(BODY, 'head_socket_len'), ternary(HEAD, 'socket_len', 'monolithic')),
        ("cav_board_len",
         scalar(BODY, 'cav_board_len'), head_interface('cav_board_len')),
        ("board_t",
         scalar(BODY, 'board_t'), scalar(HEAD, 'board_t')),
        ("board_w",
         scalar(BODY, 'board_w'), scalar(HEAD, 'board_w')),
        ("tube_len (monolithic)",
         body_tube_len('monolithic'), head_tube_len('monolithic')),
        ("tube_len (bonded)",
         body_tube_len('bonded'), head_tube_len('bonded')),
    ]
    # groove_root is derived in the body and hardcoded in the head for drawing.
    root = None
    cb = scalar(BODY, 'cable_bore_d')
    cord = scalar(BODY, 'seal_cord')
    sq = scalar(BODY, 'seal_squeeze')
    if None not in (cb, cord, sq):
        root = cb - 2 * cord * (1 - sq)
    checks.append(("groove_root", root, scalar(HEAD, 'body_groove_root')))

    bad = 0
    for name, a, b in checks:
        if a is None or b is None:
            print("  ?? %-22s could not read (body=%s head=%s)" % (name, a, b))
            bad += 1
        elif abs(a - b) > 1e-3:
            print("  FAIL %-20s body=%-10g head=%-10g  DRIFTED" % (name, a, b))
            bad += 1
        else:
            print("  ok   %-20s %g" % (name, a))
    fusion_fails = fusion()
    for f in fusion_fails:
        print("  FAIL " + f)
    bad += len(fusion_fails)
    if bad:
        print("\n%d interface check(s) failed between the two models" % bad)
        return 1
    print("\ninterfaces agree, and the monobody conserves volume")
    return 0


if __name__ == '__main__':
    sys.exit(main())
