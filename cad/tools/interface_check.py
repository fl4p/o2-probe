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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
BODY = os.path.join(CAD, 'o2_probe_body_tube.scad')
HEAD = os.path.join(CAD, 'o2_probe_head_end.scad')


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


def head_tube_len(joint):
    """The head writes it as a ternary on `monolithic`."""
    m = re.search(r'^body_tube_len\s*=\s*monolithic\s*\?\s*([\d.]+)\s*:\s*([\d.]+)\s*;',
                  open(HEAD).read(), re.M)
    if not m:
        return None
    return float(m.group(1) if joint == 'monolithic' else m.group(2))


def main():
    checks = [
        ("cap_engage",
         scalar(BODY, 'cap_engage'), scalar(HEAD, 'body_cap_engage')),
        ("seal_id",
         scalar(BODY, 'seal_id'), scalar(HEAD, 'body_seal_id')),
        ("seal_cord",
         scalar(BODY, 'seal_cord'), scalar(HEAD, 'body_seal_cord')),
        ("head_socket_len",
         scalar(BODY, 'head_socket_len'), scalar(HEAD, 'socket_len')),
        ("cav_board_len",
         scalar(BODY, 'cav_board_len'), scalar(HEAD, 'cav_board_len')),
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
    if bad:
        print("\n%d duplicated interface number(s) disagree between the two "
              "models" % bad)
        return 1
    print("\ninterfaces agree")
    return 0


if __name__ == '__main__':
    sys.exit(main())
