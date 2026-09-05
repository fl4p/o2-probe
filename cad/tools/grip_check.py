#!/usr/bin/env python3
"""Mesh check on the wire-end grip band -- the tube and the fit coupon.

WHY THIS EXISTS. `grip_slack` is a number in the .scad, and the .scad's own
asserts only compare declared numbers with each other. That is exactly the trap
the lock boss fell into (see `module tube()`): every assert passed while the
boss had been eaten by the bore. A friction fit can fail the same way and still
render as a flawless closed solid -- one wrong sign in `slot_ramp`'s scale, a
band placed outside its station, a `linear_extrude` scale that catches x as
well as y, and the slot is simply the clearance slot end to end, silently.

So this measures the SLOT, in the exported STL, at the band and away from it,
and refuses to pass unless both are what the model said they would be.

NO SILENT PASSES. A sample window with no vertices in it is a FAIL, never an
"unknown" -- with one named exception, and it is checked rather than skipped:
the reference rung, whose slack equals `guide_slack`, has no band at all by
construction (the ramps degenerate to scale 1.0 and the three cuts merge into
one plain slot). That rung is measured over its whole height as a plain slot.
"""
import re
import subprocess
import sys
from pathlib import Path

CAD = Path(__file__).resolve().parent.parent
SCAD = CAD / "o2_probe_body_tube.scad"
TOL = 1e-3

# The rail's radial window and the coupon's layout. These mirror the .scad and
# are the one place this file duplicates it; if guide_engage, guide_r_max,
# board_w, tube_od or coupon_pad move, they move here too.
BOARD_W, GUIDE_ENGAGE, GUIDE_R_MAX = 20.0, 1.0, 14.8
COUPON_PITCH, COUPON_PAD = 32.0 + 4, 4.0
# Where the ray is fired from: inside the rail, clear of the slot mouth at
# dx = 9.0 and of the rail's buried face at dx = 14.8.
X_PROBE = 12.0
GUIDE_LEAD = 1.5
guide_lead_pad = GUIDE_LEAD


def scad_numbers():
    """Read the model's own echoes rather than re-deriving anything here.

    Re-deriving is how a checker ends up agreeing with the bug: it computes the
    same wrong number from the same wrong source. The echoes are what the model
    believes it built; this file's job is to disagree if the mesh does.
    """
    out = subprocess.run(
        ["openscad", "--hardwarnings", "-D", 'part="tube"',
         "-o", "/dev/null.stl", str(SCAD)],
        capture_output=True, text=True, cwd=CAD).stderr
    grip = re.search(
        r"WIRE-END GRIP: station A carries a ([\d.]+) mm band at slack (-?[\d.]+) "
        r"\(slot ([\d.]+) mm on a ([\d.]+) mm board\), board y ([\d.]+)\.\.([\d.]+), "
        r"ramps ([\d.]+) mm\. Rest of station A and all of station B stay at ([\d.]+?)\. ", out)
    coup = re.search(r"FIT COUPON: (\d+) rings, slacks \[([^\]]*)\]", out)
    board = re.search(r"BOARD: y=0 at z=([\d.]+)", out)
    if not (grip and coup and board):
        sys.exit("grip_check: could not read the model's echoes -- did their text "
                 "change?\n" + out)
    return {
        "grip_len": float(grip[1]), "grip_slack": float(grip[2]),
        "grip_slot": float(grip[3]), "board_t": float(grip[4]),
        "band_y0": float(grip[5]), "band_y1": float(grip[6]),
        "grip_ramp": float(grip[7]), "guide_slack": float(grip[8]),
        "slacks": [float(v) for v in coup[2].split(",")],
        "zoff": float(board[1]),
    }


def tris(path):
    """Triangles out of an ASCII STL."""
    v, out = [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if p and p[0] == "vertex":
                v.append((float(p[1]), float(p[2]), float(p[3])))
                if len(v) == 3:
                    out.append(tuple(v))
                    v = []
    if not out:
        sys.exit(f"grip_check: {path} has no triangles -- binary STL, or an empty render?")
    return out


def _hit(tri, o, d):
    """Moller-Trumbore, returning t or None."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    e1 = (bx - ax, by - ay, bz - az)
    e2 = (cx - ax, cy - ay, cz - az)
    px = d[1] * e2[2] - d[2] * e2[1]
    py = d[2] * e2[0] - d[0] * e2[2]
    pz = d[0] * e2[1] - d[1] * e2[0]
    det = e1[0] * px + e1[1] * py + e1[2] * pz
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    t0 = (o[0] - ax, o[1] - ay, o[2] - az)
    u = (t0[0] * px + t0[1] * py + t0[2] * pz) * inv
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    qx = t0[1] * e1[2] - t0[2] * e1[1]
    qy = t0[2] * e1[0] - t0[0] * e1[2]
    qz = t0[0] * e1[1] - t0[1] * e1[0]
    vv = (d[0] * qx + d[1] * qy + d[2] * qz) * inv
    if vv < -1e-9 or u + vv > 1 + 1e-9:
        return None
    t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
    return t if t > 1e-9 else None


def slot_h(mesh, x, z):
    """Slot opening at one point, measured by RAY, not by vertex position.

    An earlier version took the smallest |y| among vertices in a z window, and
    it was wrong twice over: a slot face that spans a window has NO vertices
    inside it (they sit on the window's boundary planes), and a scaled
    linear_extrude drops fan vertices on the board plane that read as a zero
    slot. A ray fired both ways from y=0 measures the void itself and does not
    care where the triangulation put its corners. Returns None if either ray
    escapes -- which means the probe point is not inside a slot at all, and
    that is a failure, never a pass.
    """
    up, dn = [], []
    for t in mesh:
        h = _hit(t, (x, 0.0, z), (0.0, 1.0, 0.0))
        if h is not None:
            up.append(h)
        h = _hit(t, (x, 0.0, z), (0.0, -1.0, 0.0))
        if h is not None:
            dn.append(h)
    if not up or not dn:
        return None
    return min(up) + min(dn)


def fmt(pair):
    return " ".join(f"{v:7.3f}" if v is not None else "  ---- " for v in pair)


def main():
    # Which parts to check. Named explicitly so a missing STL is a FAILURE for
    # the part that was asked for, and never a silent skip -- `make body-tube`
    # has no coupon and must not be scored on one.
    parts = set(sys.argv[1:]) or {"tube", "coupon"}
    unknown = parts - {"tube", "coupon"}
    if unknown:
        sys.exit(f"grip_check: unknown part(s) {sorted(unknown)}; use tube and/or coupon")
    m = scad_numbers()
    clear = m["board_t"] + m["guide_slack"]
    ramp, glen = m["grip_ramp"], m["grip_len"]
    fails, rows = [], []

    # ---- the coupon ladder
    stl = CAD / "exports" / "body-fit-coupon.stl"
    if "coupon" not in parts:
        pass
    elif not stl.exists():
        fails.append(f"{stl.name} missing -- run `make fit-coupon`")
    else:
        mesh = tris(stl)
        g0, g1 = COUPON_PAD + ramp, COUPON_PAD + ramp + glen
        n = len(m["slacks"])
        for i, gs in enumerate(m["slacks"]):
            xc = (i - (n - 1) / 2) * COUPON_PITCH
            want = m["board_t"] + gs
            # Both rails, and they must agree: a mirror bug shows up as one
            # side gripping and the other not, which no single probe would see.
            band = [slot_h(mesh, xc + s * X_PROBE, (g0 + g1) / 2) for s in (1, -1)]
            plain = [slot_h(mesh, xc + s * X_PROBE, COUPON_PAD / 2) for s in (1, -1)]
            if abs(gs - m["guide_slack"]) < TOL:
                # No band by construction: the whole rail is the clearance slot.
                want = clear
            bad = (None in band or None in plain
                   or max(abs(b - want) for b in band) > TOL
                   or max(abs(p - clear) for p in plain) > TOL)
            rows.append((f"coupon {gs:g}", band, want, plain, clear, bad))
            if bad:
                fails.append(f"coupon rung {gs:g}: band {band} (want {want}), "
                             f"plain {plain} (want {clear})")

    # ---- the tube itself, station A
    stl = CAD / "exports" / "body-tube.stl"
    if "tube" not in parts:
        pass
    elif not stl.exists():
        fails.append(f"{stl.name} missing -- run `make body-tube`")
    else:
        mesh = tris(stl)
        z = m["zoff"]
        band = [slot_h(mesh, s * X_PROBE, z + (m["band_y0"] + m["band_y1"]) / 2)
                for s in (1, -1)]
        # Plain probe halfway between the rail's lead-in and the ramp's start.
        z_plain = z + (4.0 + guide_lead_pad + m["band_y0"] - ramp) / 2
        plain = [slot_h(mesh, s * X_PROBE, z_plain) for s in (1, -1)]
        bad = (None in band or None in plain
               or max(abs(b - m["grip_slot"]) for b in band) > TOL
               or max(abs(p - clear) for p in plain) > TOL)
        rows.append(("tube stn A", band, m["grip_slot"], plain, clear, bad))
        if bad:
            fails.append(f"tube station A: band {band} (want {m['grip_slot']}), "
                         f"plain {plain} (want {clear})")

    print(f"{'part':<13} {'band +x  -x':>16} {'want':>6} "
          f"{'plain +x  -x':>16} {'want':>6}  verdict")
    for name, band, want, plain, cl, bad in rows:
        print(f"{name:<13} {fmt(band):>16} {want:6.2f} {fmt(plain):>16} {cl:6.2f}  "
              f"{'FAIL' if bad else 'ok'}")

    if fails:
        print("\ngrip_check: FAIL")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    if not rows:
        sys.exit("grip_check: nothing was measured -- that is a failure, not a pass")
    # Say which thing passed. The coupon always carries bands -- it is the
    # measuring tool -- while the tube's band can be switched off, and a message
    # that conflates the two would report "band off" for a plate full of bands.
    band_off = abs(m["grip_slack"] - m["guide_slack"]) < TOL
    said = []
    if "tube" in parts:
        said.append("station A is plain clearance end to end, as drawn (band off)"
                    if band_off else "the tube's grip band is in the mesh at the drawn slack")
    if "coupon" in parts:
        said.append("every coupon rung's band is in the mesh at its drawn slack")
    print("\ngrip_check: " + "; ".join(said))


main()
