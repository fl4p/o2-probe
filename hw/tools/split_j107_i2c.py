#!/usr/bin/env python3
"""Split J107's I2C lands into their own components, J108 (SDA) and J109 (SCL).

WHY.  `tools/relocate_j107_i2c.py` moved pads 3 and 4 of the six-land J107 off
the analog front end, but they stayed pads of J107.  A pad inside a placed
footprint cannot be dragged in pcbnew without Pad Edit Mode, and a board whose
footprint no longer matches its library raises `lib_footprint_mismatch`.  Fab,
2026-09-14: "ungroup the pads, i will do it myself" - and then, having tried it,
"the copy it opened still had SDA/SCL pads grouped, i could not move them
separately".  The only real ungroup is to stop calling them one part.

WHAT.  Three parts where there was one:

    J107  SolderPads_1x04_SMD_PwrUart   (110.00,  61.50)  1=3V3D 2=GND 5=TX 6=RX
    J108  SolderPad_SMD_I2C_SDA         (104.10, 125.95)  pad 1 = /I2C_SDA
    J109  SolderPad_SMD_I2C_SCL         (118.85, 100.00)  pad 1 = /I2C_SCL

No copper moves: J108 and J109 land exactly where J107's pads 3 and 4 already
were, so the routed SCL leg and the SDA land's seat on existing bus copper are
untouched.  The silk legends keep their measured offsets from the land, because
those offsets are what passed `silk_edge_clearance` and `silk_over_copper`.

Each new part is an ordinary footprint, so it drags with a plain click.

The schematic side is `gen_sch.py`; run it first, and keep the Design Notes
here byte-identical with the ones it writes.
"""
import argparse
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIB = ROOT / 'lib' / 'o2-probe.pretty'

OLD_FP = 'SolderPads_1x06_SMD_SplitI2C'
ROW_FP = 'SolderPads_1x04_SMD_PwrUart'
PAD_SIZE = (1.6, 1.2)
SILK = (0.8, 0.12)              # board rules: min_text_height 0.8, min_text_thickness 0.12
# Courtyard half-extents for a single land.  These lands have no body, so the
# courtyard is the pad outline and nothing more: at the pad-plus-0.15 mm size
# used elsewhere the SDA land's rectangle collides with RH1's courtyard
# (measured 2026-09-14; RH1 is 0.725 mm from the land centre).  A footprint with
# no courtyard at all is a `missing_courtyard` DRC *error*, so omitting it is not
# an option once the lands are their own parts.
CY = (0.8, 0.6)

ROW_DESCR = ('Four plain SMD solder lands in a row on 2.6 mm pitch for hand-soldered flying '
             'leads, 1.6 x 1.2 mm, no drills, no castellations, no paste (1=3V3D 2=GND 5=TX '
             '6=RX). The I2C pair that used to sit between them is now J108 and J109. Pad 1 '
             'is marked on B.Fab.')
ROW_NOTE = ("Hand-solder lands, back copper, in a row at the cable end: 1=3V3D 2=GND "
            "5=UART2_TX 6=UART2_RX. The I2C pair is NOT here - SDA is J108 and SCL is J109, "
            "separate single lands placed up the board clear of the analog front end. A lead "
            "for an external TMP117 therefore lands power at the cable end and I2C mid-board. "
            "Strap its ADD0 to SDA (0x4A) or SCL (0x4B) - NOT GND, which is 0x48 and collides "
            "with the LMP91000. No pull-ups on the lead; R10/R11 already bias the bus. "
            "3.3 V logic only. Pads 5/6 duplicate J105/J106.")

# ref -> (footprint name, value, net, board position, silk label, silk offset from the
#         land, one-line descr, Design Note)
#
# The silk offsets are the ones already measured clear on this board: SDA's legend sat
# 1.40 mm toward the cable end of its land, SCL's 1.95 mm the other way and 0.25 mm across.
# Do not "tidy" them - 'J107 SDA' at these sizes hit the left thermal slot and U11 pad 1.
LANDS = {
    'J108': (
        'SolderPad_SMD_I2C_SDA', 'EXT SENSOR SDA', '/I2C_SDA', (104.10, 125.95),
        'SDA', (0.0, -1.40),
        'One plain SMD solder land, 1.6 x 1.2 mm, no drill, no paste: /I2C_SDA to a flying '
        'lead. Placed clear of the analog front end; its power pair is J107.',
        "Single hand-solder land, back copper, carrying /I2C_SDA to a flying lead. Its "
        "power pair is J107 at the cable end and SCL is J109; the three are one connector "
        "in three pieces. Placed clear of the analog front end - routed from J107's row "
        "this net ran ~9 mm at the board minimum 0.100 mm from /GUARD_REPLICA. No pull-up "
        "here; R10/R11 already bias the bus. 3.3 V logic only."),
    'J109': (
        'SolderPad_SMD_I2C_SCL', 'EXT SENSOR SCL', '/I2C_SCL', (118.85, 100.00),
        'SCL', (-0.25, 1.95),
        'One plain SMD solder land, 1.6 x 1.2 mm, no drill, no paste: /I2C_SCL to a flying '
        'lead. Placed clear of the analog front end; its power pair is J107.',
        "Single hand-solder land, back copper, carrying /I2C_SCL to a flying lead. Its "
        "power pair is J107 at the cable end and SDA is J108; the three are one connector "
        "in three pieces. Placed clear of the analog front end - routed from J107's row "
        "this net ran ~6 mm at the board minimum 0.100 mm from /VREF_TRIM. No pull-up "
        "here; R10/R11 already bias the bus. 3.3 V logic only."),
}

NS = uuid.UUID('a1d4f0c2-6b7e-4f21-9c33-0c1f2d3e4a5b')   # stable uuids, stable diffs


def uid(key):
    return str(uuid.uuid5(NS, key))


# --------------------------------------------------------------------------- library


def row_library_footprint():
    rows = [('1', -6.5, '3V3'), ('2', -3.9, 'GND'), ('5', 3.9, 'TX'), ('6', 6.5, 'RX')]
    out = ['(footprint "%s"' % ROW_FP,
           '\t(version 20240108)',
           '\t(generator "pcbnew")',
           '\t(layer "B.Cu")',
           '\t(descr "%s")' % ROW_DESCR,
           '\t(tags "solder pad lead expansion uart smd")',
           '\t(attr smd exclude_from_pos_files)',
           '\t(duplicate_pad_numbers_are_jumpers no)',
           '\t(fp_rect (start -7.9 -1.0) (end 7.9 1.0)',
           '\t\t(stroke (width 0.05) (type default)) (fill none) (layer "B.CrtYd"))']
    out.append(_lib_text('B.Fab', '1', -6.5, -1.6, 0.6, 0.1))
    for _num, x, lbl in rows:
        out.append(_lib_text('B.SilkS', lbl, x, -1.75))
    out.append(_lib_text('B.SilkS', 'J107 EXT SENSOR / UART', 0, -3.3))
    out.append('\t(fp_circle\n\t\t(center -8.1 0)\n\t\t(end -7.85 0)\n'
               '\t\t(stroke (width 0.12) (type solid))\n\t\t(fill solid)\n\t\t(layer "B.SilkS")\n\t)')
    for num, x, _lbl in rows:
        out.append('\t(pad "%s" smd rect (at %g 0) (size %g %g) (layers "B.Cu" "B.Mask"))'
                   % (num, x, PAD_SIZE[0], PAD_SIZE[1]))
    out.append('\t(embedded_fonts no)')
    out.append(')')
    return '\n'.join(out) + '\n'


def land_library_footprint(ref):
    fp, _value, _net, _at, lbl, (sx, sy), descr, _note = LANDS[ref]
    out = ['(footprint "%s"' % fp,
           '\t(version 20240108)',
           '\t(generator "pcbnew")',
           '\t(layer "B.Cu")',
           '\t(descr "%s")' % descr,
           '\t(tags "solder pad lead expansion i2c smd")',
           '\t(attr smd exclude_from_pos_files)',
           '\t(duplicate_pad_numbers_are_jumpers no)',
           '\t(fp_rect (start %g %g) (end %g %g)' % (-CY[0], -CY[1], CY[0], CY[1]),
           '\t\t(stroke (width 0.05) (type default)) (fill none) (layer "B.CrtYd"))',
           _lib_text('B.SilkS', lbl, sx, sy),
           '\t(pad "1" smd rect (at 0 0) (size %g %g) (layers "B.Cu" "B.Mask"))'
           % PAD_SIZE,
           '\t(embedded_fonts no)',
           ')']
    return '\n'.join(out) + '\n'


def _lib_text(layer, s, x, y, size=SILK[0], thick=SILK[1]):
    return ('\t(fp_text user "%s"\n\t\t(at %g %g 0)\n\t\t(layer "%s")\n'
            '\t\t(effects (font (size %g %g) (thickness %g)) (justify mirror))\n\t)'
            % (s, x, y, layer, size, size, thick))


# --------------------------------------------------------------------------- board


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
    """Delete every whole s-expression whose opening line matches `pattern`."""
    out = block
    while True:
        m = re.search(pattern, out)
        if not m:
            return out
        _blk, end = _block(out, m.start(1))
        st = out.rindex('\n', 0, m.start(1))
        out = out[:st] + out[end:]


def shrink_j107(text):
    i = text.find('(footprint "o2-probe:%s"' % OLD_FP)
    if i < 0:
        if text.find('(footprint "o2-probe:%s"' % ROW_FP) >= 0:
            return text, False
        sys.exit('J107 footprint not found as %s or %s' % (OLD_FP, ROW_FP))
    fp, end = _block(text, i)
    new = fp.replace('(footprint "o2-probe:%s"' % OLD_FP,
                     '(footprint "o2-probe:%s"' % ROW_FP, 1)
    new = re.sub(r'\(descr "[^"]*"\)', '(descr "%s")' % ROW_DESCR, new, count=1)
    new = re.sub(r'\(tags "[^"]*"\)', '(tags "solder pad lead expansion uart smd")', new, count=1)
    new = re.sub(r'(\(property "Design Note" )"[^"]*"',
                 lambda m: m.group(1) + '"%s"' % ROW_NOTE, new, count=1)
    for lbl in ('SDA', 'SCL'):
        new = _drop(new, r'(\(fp_text user "%s")' % lbl)
    for num in ('3', '4'):
        new = _drop(new, r'(\(pad "%s" smd rect)' % num)
    for num in ('1', '2', '5', '6'):
        if '(pad "%s" smd rect' % num not in new:
            sys.exit('row pad %s went missing' % num)
    return text[:i] + new + text[end:], True


def land_board_footprint(ref):
    fp, value, net, (x, y), lbl, (sx, sy), descr, note = LANDS[ref]

    def text(layer, s, tx, ty, size, thick, key, hide=''):
        return ('\t\t(fp_text user "%s"\n\t\t\t(at %g %g 0)\n\t\t\t(layer "%s")\n%s'
                '\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size %g %g)\n'
                '\t\t\t\t\t(thickness %g)\n\t\t\t\t)\n\t\t\t\t(justify mirror)\n\t\t\t)\n\t\t)\n'
                % (s, tx, ty, layer, hide, uid(key), size, size, thick))

    def prop(name, val, py, layer, size, thick, key, mirror=True):
        just = '\t\t\t\t(justify mirror)\n' if mirror else ''
        return ('\t\t(property "%s" "%s"\n\t\t\t(at 0 %g 0)\n\t\t\t(layer "%s")\n'
                '\t\t\t(hide yes)\n\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n'
                '\t\t\t\t\t(size %g %g)\n\t\t\t\t\t(thickness %g)\n\t\t\t\t)\n%s\t\t\t)\n\t\t)\n'
                % (name, val, py, layer, uid(key), size, size, thick, just))

    out = ['\t(footprint "o2-probe:%s"\n' % fp,
           '\t\t(layer "B.Cu")\n',
           '\t\t(uuid "%s")\n' % uid(ref + ':fp'),
           '\t\t(at %g %g)\n' % (x, y),
           '\t\t(descr "%s")\n' % descr,
           '\t\t(tags "solder pad lead expansion i2c smd")\n',
           prop('Reference', ref, 2.6, 'B.Fab', 0.8, 0.12, ref + ':ref'),
           prop('Value', value, 3.8, 'B.Fab', 0.8, 0.12, ref + ':val'),
           ('\t\t(property "Datasheet" ""\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.Fab")\n'
            '\t\t\t(hide yes)\n\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n'
            '\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n' % uid(ref + ':ds')),
           ('\t\t(property "Description" ""\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.Fab")\n'
            '\t\t\t(hide yes)\n\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n'
            '\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n' % uid(ref + ':dsc')),
           prop('Design Note', note, 5.0, 'B.Fab', 0.8, 0.12, ref + ':note'),
           '\t\t(attr smd exclude_from_pos_files)\n',
           '\t\t(duplicate_pad_numbers_are_jumpers no)\n',
           ('\t\t(fp_rect\n\t\t\t(start %g %g)\n\t\t\t(end %g %g)\n\t\t\t(stroke\n'
            '\t\t\t\t(width 0.05)\n\t\t\t\t(type default)\n\t\t\t)\n\t\t\t(fill no)\n'
            '\t\t\t(layer "B.CrtYd")\n\t\t\t(uuid "%s")\n\t\t)\n'
            % (-CY[0], -CY[1], CY[0], CY[1], uid(ref + ':crtyd'))),
           text('B.SilkS', lbl, sx, sy, SILK[0], SILK[1], ref + ':silk'),
           ('\t\t(pad "1" smd rect\n\t\t\t(at 0 0)\n\t\t\t(size %g %g)\n'
            '\t\t\t(layers "B.Cu" "B.Mask")\n\t\t\t(net "%s")\n\t\t\t(uuid "%s")\n\t\t)\n'
            % (PAD_SIZE[0], PAD_SIZE[1], net, uid(ref + ':pad1'))),
           '\t\t(embedded_fonts no)\n',
           '\t)\n']
    return ''.join(out)


def add_lands(text):
    added = []
    for ref in sorted(LANDS):
        if '(property "Reference" "%s"' % ref in text:
            continue
        i = text.find('(footprint "o2-probe:%s"' % ROW_FP)
        if i < 0:
            sys.exit('J107 row footprint not found; run shrink first')
        _blk, end = _block(text, i)
        end = text.index('\n', end) + 1
        text = text[:end] + land_board_footprint(ref) + text[end:]
        added.append(ref)
    return text, added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb')
    a = ap.parse_args()
    for name, body in ((ROW_FP, row_library_footprint()),
                       (LANDS['J108'][0], land_library_footprint('J108')),
                       (LANDS['J109'][0], land_library_footprint('J109'))):
        (LIB / (name + '.kicad_mod')).write_text(body)
        print('wrote', LIB / (name + '.kicad_mod'))
    old = LIB / (OLD_FP + '.kicad_mod')
    if old.exists():
        old.unlink()
        print('removed', old)
    text = Path(a.pcb).read_text()
    text, shrank = shrink_j107(text)
    text, added = add_lands(text)
    Path(a.pcb).write_text(text)
    print('J107 -> %s (%s); added %s'
          % (ROW_FP, 'shrunk' if shrank else 'already split', ', '.join(added) or 'nothing'))


if __name__ == '__main__':
    main()
