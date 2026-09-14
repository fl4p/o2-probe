#!/usr/bin/env python3
"""Turn the two UART bench taps J105 / J106 into SMD solder lands.

WHY.  Fab, 2026-09-14: "replace the uart 2 pin headers with solder pads (smd)".
J105 (/UART2_TX) and J106 (/UART2_RX) were `SolderWireNoRelief_*` parts: a
1.85 x 1.85 mm roundrect on every copper layer over an 0.85 mm plated hole.  Two
of the board's 215 plated holes existed only so a bench wire could be threaded.

WHAT.  Same position, same 1.85 x 1.85 mm roundrect outline, same net - the pad
becomes `smd` on B.Cu / B.Mask and the drill goes away.  The back is where the
solderable surface already was: both footprints are placed on B.Cu, so only the
back mask was open, and the front annulus was doing nothing but blocking the
front ground pour.

    J105  SolderPad_SMD_J105  (111.75, 97.80)  /UART2_TX   B.Cu land
    J106  SolderPad_SMD_J106  (117.00, 97.80)  /UART2_RX   B.Cu land

Each gains a B.SilkS legend.  The old parts had none - the same mistake that
made J107 read as missing on 2026-09-13: an unmarked copper rectangle on the
back of a board cannot be soldered to by someone who does not already know what
it is.  The 3D model goes with the hole; it modelled a threaded wire.

WHAT THIS BREAKS, and the fix.  /UART2_TX arrives at J105 on B.Cu and is
unaffected.  /UART2_RX arrives at J106 on *F.Cu* and used the plated hole as its
layer change, so its tail has to be re-routed onto the back; the invocation is
in routing/revb-86-ring/README.md.  Run this script first, then the re-route,
then refill and DRC.
"""
import argparse
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIB = ROOT / 'lib' / 'o2-probe.pretty'

PAD = (1.85, 1.85)
RRATIO = 0.135135
SILK = (0.8, 0.12)              # board rules: min_text_height 0.8, min_text_thickness 0.12

# ref -> (old footprint, new footprint, net, label, local silk offset, descr, note)
#
# The silk offsets are LOCAL to the footprint and J105 is placed at 90 degrees,
# so its legend offset is rotated: both legends come out on the cable side of
# their land, clear of the neighbouring copper. Verified by reading the placed
# positions back, not by assuming the rotation convention.
TAPS = {
    'J105': ('SolderWireNoRelief_J105', 'SolderPad_SMD_J105', '/UART2_TX', 'TX', (1.7, 0.0),
             'Plain SMD solder land for a hand-soldered bench wire, 1.85 x 1.85 mm roundrect, '
             'no drill, no paste. Back copper. Was a plated-through wire land.',
             "Bench-bridge TTL tap, MCU side. Laptop TTL RX <- here. SMD land on BACK copper "
             "since 2026-09-14 - it was a 0.85 mm plated hole; the wire now solders flat. "
             "3.3 V logic ONLY: PA2/PA3 are not 5 V tolerant on this device "
             "(bridge_main.c:23). Duplicated at J107 pad 5."),
    'J106': ('SolderWireNoRelief_J106', 'SolderPad_SMD_J106', '/UART2_RX', 'RX', (0.0, -1.7),
             'Plain SMD solder land for a hand-soldered bench wire, 1.85 x 1.85 mm roundrect, '
             'no drill, no paste. Back copper. Was a plated-through wire land.',
             "Bench-bridge TTL tap, MCU side. Laptop TTL TX -> here. SMD land on BACK copper "
             "since 2026-09-14 - it was a 0.85 mm plated hole, which is also how this net "
             "used to change layers, so its tail is routed on B.Cu now. 3.3 V logic ONLY: "
             "PA2/PA3 are not 5 V tolerant on this device (bridge_main.c:23). Duplicated at "
             "J107 pad 6."),
}


# /UART2_RX reached J106 on F.Cu and changed layers through the pad's own plated
# hole. With the hole gone this tail ends in mid-air over a pad that no longer
# has front copper, so it goes with the hole. These two segments are ACCEPTED
# copper (they exist on routing/revb-86), which is why reroute_net.py refuses to
# rip them and they are named here instead: deleting accepted copper is a
# decision, not something a router should do on its own.
DELETE = [('/UART2_RX', 'F.Cu', (118.4, 95.75), (118.4, 96.2)),
          ('/UART2_RX', 'F.Cu', (118.4, 96.2), (117.0, 97.6))]


def delete_segments(text):
    killed = 0
    for net, layer, a, b in DELETE:
        want = ('(start %g %g)' % a, '(end %g %g)' % b, '(layer "%s")' % layer,
                '(net "%s")' % net)
        hit = None
        for m in re.finditer(r'\n\t\(segment\b', text):
            blk, end = _block(text, m.start() + 1)
            flat = re.sub(r'\s+', ' ', blk)
            if all(re.sub(r'\s+', ' ', w) in flat for w in want):
                if hit is not None:
                    sys.exit('ambiguous segment %s %s' % (a, b))
                hit = (m.start(), end)
        if hit is None:
            continue
        text = text[:hit[0]] + text[hit[1]:]
        killed += 1
    return text, killed


def sync_library():
    """Write the library copies FROM the board, so they cannot drift.

    Needs KiCad's bundled Python. A hand-written .kicad_mod did not match what
    pcbnew holds - property angles, the flip convention for a back-side part and
    the uuids are all pcbnew's to decide - and DRC said so: `lib_footprint_mismatch`
    on both taps. Exporting the placed footprint, flipped back to the front with
    its nets cleared, is the only version that is right by construction.
    """
    import pcbnew
    b = pcbnew.LoadBoard(str(BOARD))
    for ref in TAPS:
        f = b.FindFootprintByReference(ref)
        if f is None:
            sys.exit('%s not on the board' % ref)
        d = f.Duplicate(False).Cast()
        if d.GetLayer() == pcbnew.B_Cu:
            d.Flip(d.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        d.SetOrientationDegrees(0)
        d.SetPosition(pcbnew.VECTOR2I(0, 0))
        for pad in d.Pads():
            pad.SetNetCode(0)
        pcbnew.FootprintSave(str(LIB), d)
        print('synced', LIB / (TAPS[ref][1] + '.kicad_mod'))
        old = LIB / (TAPS[ref][0] + '.kicad_mod')
        if old.exists():
            old.unlink()
            print('removed', old)


def _block(text, start):
    d = 0
    for k in range(start, len(text)):
        if text[k] == '(':
            d += 1
        elif text[k] == ')':
            d -= 1
            if d == 0:
                return text[start:k + 1], k + 1
    raise ValueError('unbalanced')


def _drop(block, pattern):
    out = block
    while True:
        m = re.search(pattern, out)
        if not m:
            return out
        _blk, end = _block(out, m.start(1))
        st = out.rindex('\n', 0, m.start(1))
        out = out[:st] + out[end:]


def convert(text, ref, uid):
    old, new, net, lbl, (sx, sy), descr, note = TAPS[ref]
    i = text.find('(footprint "o2-probe:%s"' % old)
    if i < 0:
        if text.find('(footprint "o2-probe:%s"' % new) >= 0:
            return text, False
        sys.exit('%s not found as %s or %s' % (ref, old, new))
    fp, end = _block(text, i)
    if reference_of(fp) != ref:
        sys.exit('%s footprint block is not %s' % (old, ref))
    out = fp.replace('(footprint "o2-probe:%s"' % old, '(footprint "o2-probe:%s"' % new, 1)
    out = re.sub(r'\(descr "[^"]*"\)', '(descr "%s")' % descr, out, count=1)
    out = re.sub(r'\(tags "[^"]*"\)', '(tags "solder pad wire uart bench smd")', out, count=1)
    out = re.sub(r'(\(property "Design Note" )"[^"]*"',
                 lambda m: m.group(1) + '"%s"' % note, out, count=1)
    out = out.replace('\n\t\t(attr exclude_from_pos_files)',
                      '\n\t\t(attr smd exclude_from_pos_files)', 1)
    # the fab circle marked the hole, and the 3D model is a threaded wire
    out = _drop(out, r'(\(fp_circle)')
    out = _drop(out, r'(\(model )')
    pad = re.search(r'\n\t\t\(pad "1" thru_hole roundrect\n', out)
    if not pad:
        sys.exit('%s pad is not the expected plated wire land' % ref)
    blk, pend = _block(out, pad.start() + 3)
    if '(net "%s")' % net not in blk:
        sys.exit('%s pad is not on %s' % (ref, net))
    newpad = ('\t\t(pad "1" smd roundrect\n\t\t\t(at 0 0 180)\n\t\t\t(size %g %g)\n'
              '\t\t\t(layers "B.Cu" "B.Mask")\n\t\t\t(roundrect_rratio %g)\n'
              '\t\t\t(net "%s")\n\t\t\t(uuid "%s")\n\t\t)'
              % (PAD[0], PAD[1], RRATIO, net, uuid_of(blk)))
    out = out[:pad.start() + 1] + newpad + out[pend:]
    silk = ('\n\t\t(fp_text user "%s"\n\t\t\t(at %g %g 0)\n\t\t\t(layer "B.SilkS")\n'
            '\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size %g %g)\n'
            '\t\t\t\t\t(thickness %g)\n\t\t\t\t)\n\t\t\t\t(justify mirror)\n\t\t\t)\n\t\t)'
            % (lbl, sx, sy, uid, SILK[0], SILK[0], SILK[1]))
    anchor = out.index('\n\t\t(pad "1"')
    out = out[:anchor] + silk + out[anchor:]
    return text[:i] + out + text[end:], True


def reference_of(block):
    m = re.search(r'\(property "Reference" "([^"]*)"', block)
    return m.group(1) if m else None


def uuid_of(block):
    m = re.search(r'\(uuid "([0-9a-f-]+)"\)', block)
    return m.group(1)


NS = uuid.UUID('a1d4f0c2-6b7e-4f21-9c33-0c1f2d3e4a5b')   # stable uuids, stable diffs


BOARD = None


def main():
    global BOARD
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb')
    ap.add_argument('--sync-library', action='store_true',
                    help='write the library copies from the board; needs KiCad python, edits no board')
    a = ap.parse_args()
    BOARD = Path(a.pcb)
    if a.sync_library:
        sync_library()
        return
    text = Path(a.pcb).read_text()
    text, killed = delete_segments(text)
    done = ['deleted %d dangling F.Cu segment(s) of /UART2_RX' % killed]
    for ref in TAPS:
        text, changed = convert(text, ref, str(uuid.uuid5(NS, ref + ':silk')))
        done.append('%s %s' % (ref, 'converted' if changed else 'already SMD'))
    Path(a.pcb).write_text(text)
    print('; '.join(done))


if __name__ == '__main__':
    main()
