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
SHELL = os.path.join(CAD, 'o2_probe_gas_shell.scad')
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


def cavity_mesh(joint):
    """Render the head's connected-gas cavity for one joint and weigh the mesh.

    The body model has to carry the head's cavity volume as a number -- it has no
    way to render the head -- and until 2026-09-06 that number was a hand-copied
    measurement with a comment on it saying, in as many words, that nothing
    checked it. It was wrong by 1988 mm3 in the direction that flatters a
    maximum-volume budget.

    A copied measurement is only as good as the thing that re-takes it. This is
    that thing: it re-renders the cavity and weighs it, so the body's literal is
    compared against the geometry rather than against the last person to edit it.
    """
    stl = os.path.join(OUT, '.iface-cav-%s.stl' % joint)
    r = subprocess.run([OPENSCAD, '--hardwarnings'] + PROV
                       + ['-D', 'joint="%s"' % joint, '-D', 'part="cavity"',
                          '-o', stl, HEAD],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(stl):
        return None
    v = mesh_volume(stl)
    os.remove(stl)
    return v


def body_head_cavity(joint, ring):
    """The body's copy, a table keyed on the ring with a column per joint."""
    return body_table('head_cavity', ring, 1 if joint == 'monolithic' else 2)


def scalar(path, name):
    """A top-level `name = <number>;` assignment. Returns None if it is not a
    plain literal -- a computed value is not something this check can compare,
    and silently treating it as absent would be worse than saying so."""
    m = re.search(r'^%s\s*=\s*([-\d.]+)\s*;' % re.escape(name),
                  open(path).read(), re.M)
    return float(m.group(1)) if m else None


def prov_ring():
    """Which radial ring the Makefile is building, read off the ASA flags.

    Everything below that is keyed on the ring has to be resolved for the SAME
    ring the head is rendered with, or this file compares one ring's tube against
    another ring's head and reports a drift that is really its own."""
    for tok in PROV:
        m = re.match(r'radial_ring="?([^"]*)"?$', tok)
        if m:
            return m.group(1)
    return None


def body_table(name, ring, col=1):
    """One row of a `name_by_ring = [ ["ring", a, b], ... ];` table in the body.

    cav_board_len and head_cavity stopped being single literals on 2026-09-09:
    both are set by the head's cav_board_len, which the radial ring moves, so a
    single value could only ever be right for one ring -- and this check could
    only ever pass for that one. Resolving the table here is what extends the
    comparison to every ring instead of the default.
    """
    if ring is None:
        return None
    src = open(BODY).read()
    m = re.search(r'^%s\s*=\s*\[(.*?)\];' % re.escape(name + '_by_ring'),
                  src, re.M | re.S)
    if not m:
        return None
    for row in re.finditer(r'\["([^"]+)"\s*,([^\]]*)\]', m.group(1)):
        if row.group(1) != ring:
            continue
        vals = [v.strip() for v in row.group(2).split(',') if v.strip()]
        try:
            return float(vals[col - 1])
        except (IndexError, ValueError):
            return None
    return None


def body_cav_board_len(ring):
    return body_table('cav_board_len', ring)


def body_tube_len(joint, ring):
    """The body model derives it; recompute the same way rather than parsing a
    value that is not written down as one."""
    bl = scalar(BODY, 'board_len')
    cav = body_cav_board_len(ring)
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
    """The head DERIVES it now, so it comes off the INTERFACE echo.

    It used to be `body_tube_len = monolithic ? 124.0 : 127.0` and this function
    read those two literals. That pair was the monobody failure under ors116787:
    the head solves cav_board_len to 2.4 there and the right tube is 123.6, while
    the literal went on saying 124.0 and the union opened a 0.4 mm gap. The head
    now computes the same identity the body does -- which means a regex can no
    longer see it, exactly as happened to cav_board_len, and for the same reason
    the value moves to a render."""
    return head_interface('body_tube_len', joint)


def main():
    ring = prov_ring()
    print("  radial_ring %s (from the Makefile's ASA flags)" % ring)
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
         body_cav_board_len(ring), head_interface('cav_board_len')),
        ("board_t",
         scalar(BODY, 'board_t'), scalar(HEAD, 'board_t')),
        ("board_w",
         scalar(BODY, 'board_w'), scalar(HEAD, 'board_w')),
        ("tube_len (monolithic)",
         body_tube_len('monolithic', ring), head_tube_len('monolithic')),
        ("tube_len (bonded)",
         body_tube_len('bonded', ring), head_tube_len('bonded')),
    ]
    # groove_root is derived in the body and hardcoded in the head for drawing.
    root = None
    cb = scalar(BODY, 'cable_bore_d')
    cord = scalar(BODY, 'seal_cord')
    sq = scalar(BODY, 'seal_squeeze')
    if None not in (cb, cord, sq):
        root = cb - 2 * cord * (1 - sq)
    checks.append(("groove_root", root, scalar(HEAD, 'body_groove_root')))
    # ---- the gas shell, a THIRD file restating the same interfaces.
    #
    # It is the newest and therefore the most likely to rot: it mirrors numbers
    # from BOTH other models, and it is the only part whose fit is decided by a
    # dimension of the cable end (the collar bore it has to pass through). When
    # cable_bore_d moved 25.5 -> 25.7 on 2026-09-06 the shell's OD moved with it;
    # nothing but this check would have noticed if it had not.
    if os.path.exists(SHELL):
        shell_pairs = [
            ('board_w', BODY, 'board_w'), ('board_t', BODY, 'board_t'),
            ('board_len', BODY, 'board_len'),
            ('guide_engage', BODY, 'guide_engage'),
            ('guide_body', BODY, 'guide_body'),
            ('collar_bore', BODY, 'cable_bore_d'),
            ('cell_d', HEAD, 'cell_d'), ('cell_h', HEAD, 'cell_h'),
        ]
        for mine, src, theirs in shell_pairs:
            checks.append(("shell %s" % mine, scalar(SHELL, mine),
                           scalar(src, theirs)))
        # tube_id is derived in the body, as it is for the head.
        checks.append(("shell tube_id", scalar(SHELL, 'tube_id'),
                       (lambda od, w: None if None in (od, w) else od - 2 * w)(
                           scalar(BODY, 'tube_od'), scalar(BODY, 'wall'))))
        # cell_y is the PLACEMENT.md datum; the head holds the same fact as a
        # setback from the board tip. Different spelling, one number.
        bl, sb = scalar(BODY, 'board_len'), scalar(HEAD, 'cell_setback')
        checks.append(("shell cell_y", scalar(SHELL, 'cell_y'),
                       None if None in (bl, sb) else bl - sb))
        # cell_seated_h is an UNMEASURED input the Makefile supplies. The shell
        # has to use the same provisional value the head is rendered with, or the
        # gas gap over the sensing face is sized against a different cell.
        prov_seated = None
        for i, tok in enumerate(PROV):
            if tok.startswith('cell_seated_h='):
                prov_seated = float(tok.split('=', 1)[1])
        checks.append(("shell cell_seated_h", scalar(SHELL, 'cell_seated_h'),
                       prov_seated))

    # The head's cavity volume, re-measured rather than trusted. Tolerance is
    # 1 mm3: this is one mesh weighed twice by the same code, so anything above
    # rounding means the literal has gone stale, which is the whole failure this
    # check exists to catch.
    for j in ('bonded', 'monolithic'):
        checks.append(("head_cavity (%s)" % j, body_head_cavity(j, ring),
                       cavity_mesh(j), 1.0))

    bad = 0
    for check in checks:
        name, a, b = check[0], check[1], check[2]
        tol = check[3] if len(check) > 3 else 1e-3
        if a is None or b is None:
            print("  ?? %-22s could not read (body=%s head=%s)" % (name, a, b))
            bad += 1
        elif abs(a - b) > tol:
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
