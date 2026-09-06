"""Weigh the probe's connected gas volume with the gas shell fitted.

WHY THIS IS NOT A PLAIN THRESHOLD GATE

The response budget is 5.0 cm3 (RESPONSE-CANDIDATE-VOLUME.md). Nothing this
project can currently build meets it: the head's own cavity is 2.93 cm3 bonded
and 4.37 monolithic, so the head spends between 59 % and 87 % of the budget
before the shell displaces a single cubic millimetre. A gate written as
`assert total <= 5000` would fail on every commit, be switched off within a
week, and take the real regression detection with it. A gate written as
`assert total <= whatever it measures today` is a mute button with a threshold
for a face.

So this is a RATCHET plus a REPORT:

  * the ratchet fails if the measured volume is worse than the recorded
    baseline. That catches the regression -- a shell that stopped filling, a
    rail channel that grew, a head cavity that opened up -- which is the failure
    this file exists to catch and the only one it can honestly claim.
  * the report always prints the distance to 5.0, for every combination of the
    two open decisions, so the shortfall cannot be forgotten by being silent.

Moving BASELINE down is the normal way to record an improvement. Moving it UP
is a decision, and the message says so.

UNEVALUABLE IS A FAILURE. A missing mesh, a failed render, an empty solid and a
zero volume all raise. None of them mean "fine": the whole point of measuring
the mesh rather than modelling the void is that a model cannot fail to produce
a plausible number, and a measurement can.
"""
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
HEAD = os.path.join(CAD, 'o2_probe_head_end.scad')
SHELL = os.path.join(CAD, 'o2_probe_gas_shell.scad')
OPENSCAD = os.environ.get('OPENSCAD', 'openscad')

BUDGET = 5000.0            # mm3, the response gate
# Measured 2026-09-06 on the as-drawn shell (shell_seal="none", rails_in_span
# =false) with the monolithic head. Both are the pessimistic branch of their
# decision, which is the right thing for a baseline to track.
BASELINE = 7962.0          # mm3
BASELINE_SLACK = 25.0      # mm3, mesh/tessellation noise


def sh(cmd):
    r = subprocess.run(cmd, cwd=CAD, capture_output=True, text=True)
    return r


def asa_flags():
    r = sh(['make', '-s', 'print-ASA'])
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit("shell_volume: cannot read ASA flags from cad/Makefile")
    return shlex.split(r.stdout.strip())


def mesh_volume(path):
    """Signed volume by the divergence theorem, from an ASCII or binary STL."""
    import struct
    if not os.path.exists(path):
        raise SystemExit("shell_volume: %s does not exist -- the render that "
                         "should have produced it did not run or did not "
                         "succeed. A missing mesh is a FAILURE, not a zero."
                         % path)
    data = open(path, 'rb').read()
    pts = []
    n = struct.unpack('<I', data[80:84])[0] if len(data) >= 84 else 0
    if n and len(data) == 84 + n * 50:
        for i in range(n):
            v = struct.unpack_from('<9f', data, 84 + i * 50 + 12)
            pts += [v[0:3], v[3:6], v[6:9]]
    else:
        for line in data.decode('utf-8', 'replace').splitlines():
            if line.strip().startswith('vertex'):
                pts.append(tuple(float(x) for x in line.split()[1:4]))
    if len(pts) < 3:
        raise SystemExit("shell_volume: %s holds %d vertices -- an empty or "
                         "unparseable mesh. UNEVALUABLE IS A FAILURE."
                         % (path, len(pts)))
    v = 0.0
    for i in range(0, len(pts) - 2, 3):
        a, b, c = pts[i], pts[i + 1], pts[i + 2]
        v += (a[0] * (b[1] * c[2] - b[2] * c[1])
              - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    v = abs(v)
    if v <= 0.0:
        raise SystemExit("shell_volume: %s weighs 0 mm3." % path)
    return v


def head_cavity(joint, flags):
    stl = os.path.join(CAD, 'exports', '.sv-cav-%s.stl' % joint)
    r = sh([OPENSCAD, '--hardwarnings'] + flags
           + ['-D', 'joint="%s"' % joint, '-D', 'part="cavity"',
              '--export-format', 'asciistl', '-o', stl, HEAD])
    if r.returncode != 0:
        raise SystemExit("shell_volume: the head's cavity would not render for "
                         "joint=%s. This is not a pass:\n%s"
                         % (joint, r.stderr[-600:]))
    v = mesh_volume(stl)
    os.remove(stl)
    return v


def shell_gas(extra):
    """The connected gas inside the shell's span, for one set of options."""
    stl = os.path.join(CAD, 'exports', '.sv-gas.stl')
    r = sh([OPENSCAD, '--hardwarnings'] + extra
           + ['-D', 'part="gas"', '--export-format', 'asciistl', '-o', stl,
              SHELL])
    if r.returncode != 0:
        raise SystemExit("shell_volume: the shell's gas solid would not render "
                         "with %s. This is not a pass:\n%s"
                         % (' '.join(extra) or '<defaults>', r.stderr[-600:]))
    v = mesh_volume(stl)
    os.remove(stl)
    return v


# The two open decisions, and what each costs. Named so the output reads as the
# decision it is rather than as a parameter sweep.
OPTIONS = [
    ("collar kept, station B short  (as drawn)", []),
    ("collar kept, station B extended", ['-D', 'rails_in_span=true']),
    ("collar deleted, station B short",
     ['-D', 'collar_bore=27.2', '-D', 'shell_pass_clr=0.2',
      '-D', 'cable_end_bore_is_full=true']),
    ("collar deleted, station B extended",
     ['-D', 'collar_bore=27.2', '-D', 'shell_pass_clr=0.2',
      '-D', 'cable_end_bore_is_full=true', '-D', 'rails_in_span=true']),
]


def main():
    argv = sys.argv[1:]
    given = argv[0] if argv else None
    flags = asa_flags()

    cav = {j: head_cavity(j, flags) for j in ('bonded', 'monolithic')}
    print("  head cavity, MEASURED off the cavity mesh: "
          "bonded %.0f, monolithic %.0f mm3" % (cav['bonded'], cav['monolithic']))
    # Bonded, the tube runs to board y=105 but the shell stops at 102 -- the
    # board's own clear-edge band ends at 103.6, so it cannot follow. That gap is
    # open bore and belongs in the bonded total.
    bonded_gap = 581.069 * 3.0 - 20.0 * 1.6 * 3.0

    # THE REFERENCE ROW, and it is the one that reframes the whole exercise.
    # POTTING.md / PLAN.md pot y=0..82 and leave y=82..107 as the gas zone. The
    # cell is at y=93.5. So the pot never filled the bore the cell breathes: the
    # potted production build the 5.0 budget is said to describe is itself about
    # 3x over it. The shell is not the price of giving up the pot -- it is work
    # the pot was never doing.
    potted_mono = (581.069 - 20.0 * 1.6) * 20.0 + cav['monolithic']
    potted_bond = (581.069 - 20.0 * 1.6) * 23.0 + cav['bonded']
    print("  %-40s %9s %11s %11s" % ("", "shell", "+mono head", "+bonded head"))
    print("  %-40s %7s   %6.0f %4.2fx  %6.0f %4.2fx"
          % ("POTTED to y=82, no shell (reference)", "--",
             potted_mono, potted_mono / BUDGET, potted_bond, potted_bond / BUDGET))
    rows = []
    for name, extra in OPTIONS:
        g = shell_gas(extra)
        mono = g + cav['monolithic']
        bond = g + cav['bonded'] + bonded_gap
        rows.append((name, g, mono, bond))
        print("  %-40s %7.0f   %6.0f %4.2fx  %6.0f %4.2fx"
              % (name, g, mono, mono / BUDGET, bond, bond / BUDGET))
    print("  (mm3; the multiple is against the %.1f cm3 response budget)"
          % (BUDGET / 1000))

    # The ratchet runs on the as-drawn shell against the monolithic head: the
    # pessimistic branch of both open decisions, so it cannot be improved by
    # choosing a friendlier configuration.
    measured = rows[0][2]
    if given:
        # A mesh handed in by the Makefile. Weigh THAT rather than re-rendering,
        # so the gate measures the file the build produced.
        measured = mesh_volume(given) + cav['monolithic']

    short = measured - BUDGET
    print("  as drawn, monolithic: %.0f mm3 -- %.0f mm3 OVER the %.0f budget "
          "(%.2fx). The head is %.0f of that."
          % (measured, short, BUDGET, measured / BUDGET, cav['monolithic']))
    if measured > BASELINE + BASELINE_SLACK:
        print("\nFAIL: %.0f mm3 against a %.0f baseline -- the connected gas "
              "volume got WORSE by %.0f mm3.\nIf that is intended, move "
              "BASELINE in tools/shell_volume.py and say why in the commit."
              % (measured, BASELINE, measured - BASELINE))
        return 1
    if measured < BASELINE - BASELINE_SLACK:
        print("  improved on the %.0f baseline by %.0f mm3 -- ratchet it down "
              "in tools/shell_volume.py." % (BASELINE, BASELINE - measured))
    print("\ngas-shell: no regression against the baseline. THE 5.0 cm3 BUDGET "
          "IS STILL NOT MET\nand this shell cannot meet it -- the head's spigot "
          "bore is 2163 mm3 of the 5000.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
