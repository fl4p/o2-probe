#!/usr/bin/env python3
"""Move J107's I2C lands off the analog front end, and delete the legs that fed them.

WHY.  On the accepted revb-86-ring candidate, J107's SDA and SCL ran from the
cable-end row (Y 61.5) past the AFE to the bus: 107.68 mm of track and 5 vias,
at the board minimum 0.100 mm from `/GUARD_REPLICA` and `/VREF_TRIM`.  DRC is
silent there because 0.100 mm *is* the rule.  With the row's pads held fixed no
route exists that keeps any real distance from the analog nets - measured, by
flood fill, ripping the whole route and permitting a join anywhere.  The pads
therefore have to move; Fab, 2026-09-14: "i dont care where the pads are".

WHAT.  Pads 3 (/I2C_SDA) and 4 (/I2C_SCL) move to the bus side of the AFE:

    pad 3  ->  (104.10, 125.95)   sits ON existing B.Cu SDA copper: no new track
    pad 4  ->  (118.85, 100.00)   7.54 mm of new track + 1 via to U6 pin 45

Measured clearances of the new lands (shapely, against every other net's copper
on B.Cu):

    land  nearest copper            nearest analog/ADC net
    SDA   /HEATER_PWM   0.250 mm    /CELL_CE   1.551 mm
    SCL   /AFE_MENB     0.279 mm    /CE_MON    1.657 mm

against 0.100 mm to `/GUARD_REPLICA` and `/VREF_TRIM` today - a 15x improvement
on the quantity that mattered, for 8 mm of copper instead of 108.

WHAT THIS COSTS, stated plainly: J107 is no longer one block.  Its 3V3D, GND and
UART lands stay at the cable end; the I2C pair is 38.5 and 64.5 mm up the board.
An external TMP117 on a lead therefore lands its power pair and its signal pair
in two places.  No site exists for a whole four-land block on the bus side - the
search is in the README - so this is forced, not chosen.

This script does the deterministic part: the library footprint, the placed
footprint, and the deletion of the old legs.  The new SCL track is routed by
`tools/reroute_net.py` (SENS_EXTRA=0.3) and written by its `emit`; see the
README for the invocation.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board

ROOT = HERE.parent
LIB = ROOT / 'lib' / 'o2-probe.pretty'
OLD_FP = 'SolderPads_1x06_SMD'
NEW_FP = 'SolderPads_1x06_SMD_SplitI2C'
ORIGIN = (110.0, 61.5)
# pad number -> (offset from the footprint origin, silk label offset)
# pad -> (pad offset, silk-label offset, label). The labels are short and sit
# where DRC leaves them clear: 'J107 SDA' at 0.8 mm ran into the left thermal
# slot and over U11 pad 1, and 'J107 SCL' into the right board edge and J106.
MOVED = {
    '3': ((-5.90, 64.45), (-5.90, 63.05), 'SDA'),
    '4': ((8.85, 38.50), (8.60, 40.45), 'SCL'),
}
SILK_SIZE = 0.8      # board rules: min_text_height 0.8, min_text_thickness 0.12
# No courtyard around the relocated lands: they have no body, and a pad-sized
# rectangle around the SDA land still overlapped RH1's courtyard (measured).
MOVED_COURTYARD = False
NETS = ('/I2C_SDA', '/I2C_SCL')
YLIM = 120.0            # the tip re-route is all north of this; the legs are south

DESCR = ('Six plain SMD solder lands for hand-soldered flying leads, 1.6 x 1.2 mm, '
         'no drills, no castellations, no paste. Four sit in a row on 2.6 mm pitch at '
         'the cable end (1=3V3D 2=GND 5=TX 6=RX); pads 3 (SDA) and 4 (SCL) are placed '
         'away from the row, clear of the analog front end. Pad 1 is marked on B.Fab.')

NOTE = ('Hand-solder lands, back copper: 1=3V3D 2=GND 5=UART2_TX 6=UART2_RX in the row at the cable end; 3=SDA and 4=SCL are NOT in the row - they sit 64.5 mm and 38.5 mm up the board at (104.10, 125.95) and (118.85, 100.00), labelled SDA/SCL on B.SilkS. A lead for an external TMP117 therefore lands power at the cable end and I2C mid-board. Strap its ADD0 to SDA (0x4A) or SCL (0x4B) - NOT GND, which is 0x48 and collides with the LMP91000. No pull-ups on the lead; R10/R11 already bias the bus. 3.3 V logic only. Pads 5/6 duplicate J105/J106.')


def library_footprint():
    """The .kicad_mod text for the split footprint."""
    rows = [('1', -6.5, '3V3'), ('2', -3.9, 'GND'), ('5', 3.9, 'TX'), ('6', 6.5, 'RX')]
    out = ['(footprint "%s"' % NEW_FP,
           '\t(version 20240108)',
           '\t(generator "pcbnew")',
           '\t(layer "B.Cu")',
           '\t(descr "%s")' % DESCR,
           '\t(tags "solder pad lead expansion i2c uart smd")',
           '\t(attr smd exclude_from_pos_files)',
           '\t(duplicate_pad_numbers_are_jumpers no)',
           '\t(fp_rect (start -7.9 -1.0) (end 7.9 1.0)',
           '\t\t(stroke (width 0.05) (type default)) (fill none) (layer "B.CrtYd"))']
    if MOVED_COURTYARD:
        for n in MOVED:
            ox, oy = MOVED[n][0]
            out.append('\t(fp_rect (start %g %g) (end %g %g)'
                       % (ox - 0.95, oy - 0.75, ox + 0.95, oy + 0.75))
            out.append('\t\t(stroke (width 0.05) (type default)) (fill none) (layer "B.CrtYd"))')

    def text(layer, s, x, y, size=0.8, thick=0.12):
        return ('\t(fp_text user "%s"\n\t\t(at %g %g 0)\n\t\t(layer "%s")\n'
                '\t\t(effects (font (size %g %g) (thickness %g)) (justify mirror))\n\t)'
                % (s, x, y, layer, size, size, thick))

    out.append(text('B.Fab', '1', -6.5, -1.6, 0.6, 0.1))
    for _num, x, lbl in rows:
        out.append(text('B.SilkS', lbl, x, -1.75))
    out.append(text('B.SilkS', 'J107 EXT SENSOR / UART', 0, -3.3))
    for num in MOVED:
        (ox, oy), (tx, ty), lbl = MOVED[num]
        out.append(text('B.SilkS', lbl, tx, ty, SILK_SIZE, 0.12))
    out.append('\t(fp_circle\n\t\t(center -8.1 0)\n\t\t(end -7.85 0)\n'
               '\t\t(stroke (width 0.12) (type solid))\n\t\t(fill solid)\n\t\t(layer "B.SilkS")\n\t)')
    for num, x, _lbl in rows:
        out.append('\t(pad "%s" smd rect (at %g 0) (size 1.6 1.2) (layers "B.Cu" "B.Mask"))' % (num, x))
    for num in sorted(MOVED):
        (ox, oy), _t, _l = MOVED[num]
        out.append('\t(pad "%s" smd rect (at %g %g) (size 1.6 1.2) (layers "B.Cu" "B.Mask"))'
                   % (num, ox, oy))
    out.append('\t(embedded_fonts no)')
    out.append(')')
    return '\n'.join(out) + '\n'


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


def edit_footprint(text):
    i = text.find('(footprint "o2-probe:%s"' % OLD_FP)
    if i < 0:
        i = text.find('(footprint "o2-probe:%s"' % NEW_FP)
    if i < 0:
        sys.exit('J107 footprint not found as %s or %s' % (OLD_FP, NEW_FP))
    fp, end = _block(text, i)
    new = fp.replace('(footprint "o2-probe:%s"' % OLD_FP,
                     '(footprint "o2-probe:%s"' % NEW_FP, 1)
    new = re.sub(r'\(descr "[^"]*"\)', '(descr "%s")' % DESCR, new, count=1)
    new = re.sub(r'(\(property "Design Note" )"[^"]*"', lambda m: m.group(1) + '"%s"' % NOTE,
                 new, count=1)
    # the row loses its SDA / SCL legends; each moved land gains its own
    for lbl in ('SDA', 'SCL'):
        while True:
            m = re.search(r'\n\t\t\(fp_text user "%s"\n.*?\n\t\t\)' % lbl, new, re.S)
            if not m:
                break
            new = new[:m.start()] + new[m.end():]
    new = new.replace('"J107 EXT I2C / UART"', '"J107 EXT SENSOR / UART"', 1)
    add = []
    for num in sorted(MOVED):
        (ox, oy), (tx, ty), lbl = MOVED[num]
        add.append('\n\t\t(fp_text user "%s"\n\t\t\t(at %g %g 0)\n\t\t\t(layer "B.SilkS")\n'
                   '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size %g %g)\n'
                   '\t\t\t\t\t(thickness 0.12)\n\t\t\t\t)\n\t\t\t\t(justify mirror)\n\t\t\t)\n\t\t)'
                   % (lbl, tx, ty, SILK_SIZE, SILK_SIZE))
        if MOVED_COURTYARD:
            add.append('\n\t\t(fp_rect\n\t\t\t(start %g %g)\n\t\t\t(end %g %g)\n\t\t\t(stroke\n'
                       '\t\t\t\t(width 0.05)\n\t\t\t\t(type default)\n\t\t\t)\n\t\t\t(fill no)\n'
                       '\t\t\t(layer "B.CrtYd")\n\t\t)'
                       % (ox - 0.95, oy - 0.75, ox + 0.95, oy + 0.75))
    anchor = new.index('\n\t\t(pad "1"')
    new = new[:anchor] + ''.join(add) + new[anchor:]
    for num in sorted(MOVED):
        (ox, oy), _t, _l = MOVED[num]
        m = re.search(r'\(pad "%s" smd rect\s*\n\t+\(at ([-\d.]+) ([-\d.]+)\)' % num, new)
        if not m:
            sys.exit('pad %s not found' % num)
        new = new[:m.start(1)] + ('%g %g' % (ox, oy)) + new[m.end(2):]
    return text[:i] + new + text[end:]


def delete_legs(text, pcb, reference):
    """Remove the copper this revision added for J107's I2C, south of YLIM."""
    cur, ref = board.parse(pcb), board.parse(reference)

    def skey(s):
        return (s['net'], s['layer'], tuple(round(v, 4) for v in s['a']),
                tuple(round(v, 4) for v in s['b']), round(s['w'], 4))

    def vkey(v):
        return (v['net'], tuple(round(x, 4) for x in v['at']), round(v['size'], 4))

    ka = {skey(s) for s in ref['segs']}
    kv = {vkey(v) for v in ref['vias']}
    segs = {(round(s['a'][0], 4), round(s['a'][1], 4), round(s['b'][0], 4), round(s['b'][1], 4), s['layer'])
            for s in cur['segs'] if s['net'] in NETS and skey(s) not in ka
            and max(s['a'][1], s['b'][1]) < YLIM}
    vias = {(round(v['at'][0], 4), round(v['at'][1], 4))
            for v in cur['vias'] if v['net'] in NETS and vkey(v) not in kv and v['at'][1] < YLIM}
    kill = []
    for m in re.finditer(r'\n\t\((segment|via)\b', text):
        blk, end = _block(text, m.start() + 1)
        if not any('(net "%s")' % n in blk for n in NETS):
            continue
        if m.group(1) == 'segment':
            a = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)', blk)
            b = re.search(r'\(end ([-\d.]+) ([-\d.]+)\)', blk)
            ly = re.search(r'\(layer "([^"]+)"\)', blk).group(1)
            k = (round(float(a.group(1)), 4), round(float(a.group(2)), 4),
                 round(float(b.group(1)), 4), round(float(b.group(2)), 4), ly)
            if k in segs:
                kill.append((m.start() + 1, end))
        else:
            a = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', blk)
            if (round(float(a.group(1)), 4), round(float(a.group(2)), 4)) in vias:
                kill.append((m.start() + 1, end))
    if len(kill) != len(segs) + len(vias):
        sys.exit('leg mismatch: %d blocks for %d items' % (len(kill), len(segs) + len(vias)))
    for st, en in sorted(kill, reverse=True):
        text = text[:st - 1] + text[en:]
    return text, len(segs), len(vias)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb')
    ap.add_argument('--reference', required=True,
                    help='accepted board; only copper THIS revision added is rippable')
    a = ap.parse_args()
    (LIB / (NEW_FP + '.kicad_mod')).write_text(library_footprint())
    print('wrote', LIB / (NEW_FP + '.kicad_mod'))
    text = Path(a.pcb).read_text()
    text = edit_footprint(text)
    text, ns, nv = delete_legs(text, a.pcb, a.reference)
    Path(a.pcb).write_text(text)
    print('J107 -> %s; deleted %d segments and %d vias' % (NEW_FP, ns, nv))


if __name__ == '__main__':
    main()
