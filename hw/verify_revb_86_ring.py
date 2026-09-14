#!/usr/bin/env python3
"""Verify the Rev B 86 mm ring board against the immutable accepted revb-86 board.

Every difference from routing/revb-86 must be one of the ring revision's pinned
changes; anything else fails. The revision (2026-09-13) adds the membrane-ring
lands J5, the external-sensor lands J107 / J108 / J109 and their routes, turns the
UART bench taps J105 / J106 into undrilled SMD lands, shortens both
thermal slots 2 mm at the tip, moves C35 and the TMP_CELL label clear of the
right/left land, and re-routes the tip ends of I2C_SCL / I2C_SDA plus one GND link
so HEATED_ISLAND_SPREADER fills as one island.

Checked exactly:
- reference hash; project and rules files identical to the reference; board
  metadata, setup and layers identical; zone definitions identical
- every object present on both boards identical, except ten pinned field
  changes (six slot outline objects, the TMP_CELL text, C35's position and two
  segment endpoints), one hidden C12 property whose layer is B.SilkS -> B.Fab,
  and the two wholesale footprint replacements J105 / J106, each pinned by the
  complete new record plus named checks (position, angle, net, SMD, no drill,
  back copper only)
- removed objects: only tracks/vias, counted per (type, net)
- added objects: footprints J5, J107, J108 and J109 plus tracks/vias counted per
  (type, net);
  the two HEATER_LOW land vias pinned by position, size, drill and lock
- J5 / J107 / J108 / J109 native placement and every pad (number, net, position,
  size, layers)
- HEATED_ISLAND_SPREADER filled as ONE island containing every HEATER_LOW pad on
  B.Cu, including both back ring lands

Recorded, not gated: per-zone filled area and island counts on both boards. The
new routes remove GND fill; no threshold here would be anything but invented,
so that is a review question, not a rule.
"""
import argparse
import copy
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from verify_revb_86 import child, filled_union, parse, records, sha

REFERENCE_SHA = '9da60f0c3bbf4bc85fe11fb920bd16b3d50b55f7edb4ab5fc0db4f19af203794'
PROTECTED = {'/CELL_RE', '/CELL_WE', '/GUARD_REPLICA', '/HEATER_LOW', '/HEATER_GATE'}

# uuid -> (object type, expected layer or net or reference, {field: (before, after)})
CHANGES = {
    '42ac7ba1-2d8f-5742-b9e2-9c37a33cdd71': ('gr_line', 'Edge.Cuts', {'end': ((100.8, 136.6), (100.8, 134.6))}),
    '826fb8e5-68d2-5b9d-8011-b8689e3de374': ('gr_arc', 'Edge.Cuts', {'start': ((101.6, 136.6), (101.6, 134.6)),
                                                                     'mid': ((101.2, 137), (101.2, 135)),
                                                                     'end': ((100.8, 136.6), (100.8, 134.6))}),
    '382a52b4-f2a3-57b7-ae91-549ae3cc41c4': ('gr_line', 'Edge.Cuts', {'start': ((101.6, 136.6), (101.6, 134.6))}),
    '18318814-42c6-5733-80e9-5695c30bd779': ('gr_line', 'Edge.Cuts', {'end': ((118.4, 136.6), (118.4, 134.6))}),
    '7e81c88a-a270-5856-8a2f-65865eda73a3': ('gr_arc', 'Edge.Cuts', {'start': ((119.2, 136.6), (119.2, 134.6)),
                                                                     'mid': ((118.8, 137), (118.8, 135)),
                                                                     'end': ((118.4, 136.6), (118.4, 134.6))}),
    'f9a48ad8-9dfb-512d-ae28-f18979bb171c': ('gr_line', 'Edge.Cuts', {'start': ((119.2, 136.6), (119.2, 134.6))}),
    'a5879816-2168-5d10-8f9e-ac4a02c99e15': ('gr_text', 'B.SilkS', {'at': ((104.5, 138.2, 0), (111.3, 138.2, 0))}),
    '9560ae0a-763f-49c1-a818-523f0591496d': ('segment', 'GND', {'start': ((116.75, 135.77), (116.3, 135.785))}),
    'f75872a2-2396-416d-a67b-432ac5b85ef0': ('segment', '/I2C_SDA', {'end': ((104.2, 136.45), (104.2, 136.55))}),
    '23430439-5e79-46ee-86a2-a2a3502e32ae': ('footprint', 'C35', {'at': ((117, 136.5, 90), (117, 135.4, 90))}),
}
# The hidden KiLib_Generator property on C12 is on B.SilkS in revb-86 and on
# B.Fab here, from the ring board's first commit (d875ef1). It is hidden, so it
# plots on neither layer. Allowed as exactly that one field, and disclosed.
C12_PROPERTY = ('KiLib_Generator', 'B.SilkS', 'B.Fab')

# 2026-09-14: Fab placed J108 and routed it in pcbnew. KiCad reissues uuids on
# save, and these inventories are uuid-keyed, so 17 /3V3D segments appear here as
# removed-and-re-added although their geometry is untouched - checked segment by
# segment against the previous board. The real change on that net is two
# segments nudged aside to clear the new SDA run, +2.21 mm.
REMOVED = Counter({('segment', '/3V3D'): 19, ('segment', '/I2C_SCL'): 33, ('segment', '/I2C_SDA'): 5,
                   ('segment', '/UART2_RX'): 2, ('segment', 'GND'): 1, ('via', '/I2C_SDA'): 1})
ADDED = Counter({('segment', '/3V3D'): 32, ('segment', '/I2C_SCL'): 29, ('segment', '/I2C_SDA'): 19,
                 ('segment', '/UART2_RX'): 24, ('segment', '/UART2_TX'): 18, ('segment', 'GND'): 4,
                 ('via', '/3V3D'): 1, ('via', '/HEATER_LOW'): 2, ('via', '/I2C_SCL'): 1, ('via', '/I2C_SDA'): 3,
                 ('via', '/UART2_RX'): 4, ('via', '/UART2_TX'): 1, ('via', 'GND'): 3})
LAND_VIAS = {(101.75, 137.0), (118.25, 137.0)}

# (fpid, (x, y), angle, layer, sorted pads: (number, net, x, y, sx, sy, layers))
NEW_FOOTPRINTS = {
    'J5': ('o2-probe:Heater_Ring_Lands', (110.0, 137.65), 0.0, 'B.Cu', sorted(
        [('1', '/HEATER_LOW', x, 137.65, 2.8, 2.0, lay) for x in (101.75, 118.25)
         for lay in (('F.Cu', 'F.Mask'), ('B.Cu', 'B.Mask'))])),
    # J107's I2C pair is NOT in the row, and since 2026-09-14 is not even the same
    # part: the lands were moved to the bus side of the AFE
    # (tools/relocate_j107_i2c.py) and then split out as J108 and J109
    # (tools/split_j107_i2c.py) so each can be placed on its own. Pinned where
    # they are, so a drift back towards the guard or the ADC reference fails here.
    'J107': ('o2-probe:SolderPads_1x04_SMD_PwrUart', (110.0, 61.5), 0.0, 'B.Cu', sorted(
        [(str(i + 1), net, 103.5 + 2.6 * i, 61.5, 1.6, 1.2, ('B.Cu', 'B.Mask'))
         for i, net in enumerate(('/3V3D', 'GND', None, None, '/UART2_TX', '/UART2_RX'))
         if net is not None])),
    # Fab placed J108 himself on 2026-09-14, next to J109 rather than at the tip:
    # (104.10, 125.95) -> (118.82, 101.97), 1.97 mm from the SCL land. That is the
    # adjacency he asked for in the first place, and it is only reachable because
    # the lands are separate parts.
    'J108': ('o2-probe:SolderPad_SMD_I2C_SDA', (118.82, 101.97), 0.0, 'B.Cu',
             [('1', '/I2C_SDA', 118.82, 101.97, 1.6, 1.2, ('B.Cu', 'B.Mask'))]),
    'J109': ('o2-probe:SolderPad_SMD_I2C_SCL', (118.85, 100.0), 0.0, 'B.Cu',
             [('1', '/I2C_SCL', 118.85, 100.0, 1.6, 1.2, ('B.Cu', 'B.Mask'))]),
}
SPREADER_PADS = {('RH1', '2'), ('RH2', '2'), ('Q2', '3'), ('J5', '1')}

# Footprints this revision replaces WHOLESALE. CHANGES above pins one field at a
# time; the two UART bench taps change footprint id, pad type, drill, layer set,
# attributes, graphics and 3D model in one step (2026-09-14, Fab: "replace the
# uart 2 pin headers with solder pads (smd)"), so what is pinned is the complete
# new record, hashed. The named checks beside it say what the hash is standing
# for - position, angle, net, SMD with no drill, back copper only - so a drift
# reads as a sentence and not just a digest mismatch. UNSET fails closed.
#
# ref -> (old fpid, new fpid, net, sha256 of the new footprint record)
REPLACED_FOOTPRINTS = {
    'J105': ('o2-probe:SolderWireNoRelief_J105', 'o2-probe:SolderPad_SMD_J105', '/UART2_TX',
             '41d2f926280d068575516e78e827561efe8cfda7dad2cc36c4e0d5ad94f4ff05'),
    'J106': ('o2-probe:SolderWireNoRelief_J106', 'o2-probe:SolderPad_SMD_J106', '/UART2_RX',
             '58bb2b6e87a2ee18af395db60b7e903dd93ac7c7f63977d35be1047983857ef1'),
}
REPLACED_LAND = (1.85, 1.85)            # unchanged copper outline; only the hole goes
REPLACED_LAYERS = ('B.Cu', 'B.Mask')

# Exact delta pin (review finding 2, 2026-09-13). The (type, net) counts above
# let an added track move anywhere on its net and still PASS - demonstrated by
# moving an added SCL segment to (110,110)-(110,112), and by rotating a J5 pad or
# changing its mask margin. The complete native records of every added and every
# removed object are hashed, so any change to position, width, layer, lock, pad
# shape, angle, mask or paste fails. Regenerate with --print-delta only for an
# intended change, and treat that as a new review. UNSET fails closed.
ADDED_SHA256 = '167029b0f13b2f8dfd60ff39089acec2fc990ce267fa8ddc21ba4f29fddc0f3a'
REMOVED_SHA256 = '3d9f4ed0e3588cb6d80d6a01c2f1a72e71471c68887ca440fe0b5b13f88faebe'


def _canon(item):
    """Order-insensitive canonical form, preserving polygon vertex order.

    KiCad reorders sibling fields on save - measured 2026-09-14: a plain
    pcbnew save moves `(locked yes)` from before `(layers ...)` to after it on
    both ring-land vias. An order-sensitive digest therefore rejected the
    exporter's own refill-and-save step. Children are sorted, except under
    `pts`, where vertex order is geometry.
    """
    if not isinstance(item, list):
        return item
    atoms = [v for v in item if isinstance(v, str)]
    kids = [_canon(v) for v in item if isinstance(v, list)]
    if item and item[0] == 'pts':
        return atoms + kids
    kids.sort(key=lambda v: json.dumps(v, separators=(',', ':')))
    return atoms + kids


def delta_digest(nodes):
    canon = sorted(json.dumps(_canon(n), separators=(',', ':')) for n in nodes)
    return hashlib.sha256('\n'.join(canon).encode()).hexdigest()


def delta(board_path, reference):
    old, _ = records(parse(reference))
    actual, _ = records(parse(board_path))
    removed = [k for k in old if k not in actual]
    added = [k for k in actual if k not in old]
    return {'added': len(added), 'removed': len(removed),
            'added_sha256': delta_digest([actual[k] for k in added]),
            'removed_sha256': delta_digest([old[k] for k in removed]),
            'added_by_type_net': sorted(map(list, Counter(kind_net(actual[k]) for k in added).items())),
            'removed_by_type_net': sorted(map(list, Counter(kind_net(old[k]) for k in removed).items()))}


def unquote(token):
    return token[1:-1] if isinstance(token, str) and token.startswith('"') else token


def kind_net(node):
    nets = [x for x in node if isinstance(x, list) and x and x[0] == 'net']
    return node[0], unquote(nets[0][1]) if nets else None


def reference_of(node):
    refs = [x for x in node if isinstance(x, list) and x[:2] == ['property', '"Reference"']]
    return unquote(refs[0][2]) if len(refs) == 1 else None


def floats(q):
    return tuple(float(x) for x in q[1:])


def verify(board_path, reference):
    import pcbnew as p
    if sha(reference) != REFERENCE_SHA:
        raise ValueError('Accepted revb-86 reference hash changed')
    for ext in ('.kicad_pro', '.kicad_dru'):
        if sha(board_path.with_suffix(ext)) != sha(reference.with_suffix(ext)):
            raise ValueError('Project/rules file differs from the accepted board: ' + ext)
    old, old_meta = records(parse(reference))
    actual, meta = records(parse(board_path))
    if Counter(map(repr, meta)) != Counter(map(repr, old_meta)):
        raise ValueError('Board metadata/setup/layers changed')

    removed = [k for k in old if k not in actual]
    added = [k for k in actual if k not in old]
    bad = [kind_net(old[k]) for k in removed if old[k][0] not in ('segment', 'via')]
    if bad:
        raise ValueError('Non-copper object removed: ' + repr(bad))
    got = Counter(kind_net(old[k]) for k in removed)
    if got != REMOVED:
        raise ValueError('Removed copper inventory differs: ' + repr(sorted(got.items())))

    added_fps = sorted(reference_of(actual[k]) for k in added if actual[k][0] == 'footprint')
    if added_fps != sorted(NEW_FOOTPRINTS):
        raise ValueError('Added footprints differ: ' + repr(added_fps))
    other = [actual[k][0] for k in added if actual[k][0] not in ('footprint', 'segment', 'via')]
    if other:
        raise ValueError('Unexpected added object types: ' + repr(other))
    got = Counter(kind_net(actual[k]) for k in added if actual[k][0] in ('segment', 'via'))
    if got != ADDED:
        raise ValueError('Added copper inventory differs: ' + repr(sorted(got.items())))
    for k in added:
        node = actual[k]
        if kind_net(node) != ('via', '/HEATER_LOW'):
            continue
        at = floats(child(node, 'at'))
        if at not in LAND_VIAS or floats(child(node, 'size')) != (0.6,) or floats(child(node, 'drill')) != (0.3,):
            raise ValueError('HEATER_LOW land via is not the pinned 0.6/0.3 via at a land: ' + repr(at))
        # /HEATER_LOW is a protected net: all of its copper must be locked
        # (verify_revb_current.PROTECTED). Checked by name so the report says why.
        if [x for x in node if isinstance(x, list) and x and x[0] == 'locked'] != [['locked', 'yes']]:
            raise ValueError('HEATER_LOW land via is not locked (protected net): ' + repr(at))
    land_vias = {floats(child(actual[k], 'at')) for k in added if kind_net(actual[k]) == ('via', '/HEATER_LOW')}
    if land_vias != LAND_VIAS:
        raise ValueError('HEATER_LOW land via positions differ: ' + repr(sorted(land_vias)))

    if ADDED_SHA256 == 'UNSET' or REMOVED_SHA256 == 'UNSET':
        raise ValueError('Delta digests are unset: run --print-delta on the intended board, pin, and re-review')
    if delta_digest([actual[k] for k in added]) != ADDED_SHA256:
        raise ValueError('Added objects differ from the pinned records (geometry, width, layer, lock or pad detail)')
    if delta_digest([old[k] for k in removed]) != REMOVED_SHA256:
        raise ValueError('Removed objects differ from the pinned records')

    wanted = copy.deepcopy(old)
    for uid, (kind, owner, fields) in CHANGES.items():
        key = json.dumps(uid)
        if key not in wanted or key not in actual:
            raise ValueError('Missing pinned object ' + uid)
        node = wanted[key]
        if node[0] != kind:
            raise ValueError('Pinned object has the wrong type ' + uid)
        if kind in ('gr_line', 'gr_arc', 'gr_text'):
            if unquote(child(node, 'layer')[1]) != owner or (kind == 'gr_text' and node[1] != '"TMP_CELL"'):
                raise ValueError('Pinned drawing is not the expected object ' + uid)
        elif kind == 'segment':
            if kind_net(node)[1] != owner:
                raise ValueError('Pinned segment is on the wrong net ' + uid)
        elif reference_of(node) != owner:
            raise ValueError('Pinned footprint is not ' + owner)
        for name, (before, after) in fields.items():
            q = child(node, name)
            if floats(q) != before:
                raise ValueError('Pinned field %s of %s is not the accepted value' % (name, uid))
            q[1:] = [format(x, '.12g') for x in after]
    for ref, (old_fpid, new_fpid, net, digest) in REPLACED_FOOTPRINTS.items():
        keys = [k for k in old if old[k][0] == 'footprint' and reference_of(old[k]) == ref]
        if len(keys) != 1 or keys[0] not in actual:
            raise ValueError('Replaced footprint %s is not one object on both boards' % ref)
        key = keys[0]
        was, now = old[key], actual[key]
        if unquote(was[1]) != old_fpid or unquote(now[1]) != new_fpid:
            raise ValueError('%s is not %s -> %s' % (ref, old_fpid, new_fpid))
        if floats(child(was, 'at')) != floats(child(now, 'at')):
            raise ValueError('%s moved or rotated; the replacement may not move it' % ref)
        pads = [x for x in now if isinstance(x, list) and x and x[0] == 'pad']
        if len(pads) != 1:
            raise ValueError('%s must have exactly one land' % ref)
        pad = pads[0]
        if pad[2] != 'smd':
            raise ValueError('%s land is still %s, not smd' % (ref, pad[2]))
        if [x for x in pad if isinstance(x, list) and x and x[0] == 'drill']:
            raise ValueError('%s land still carries a drill' % ref)
        if floats(child(pad, 'size')) != REPLACED_LAND:
            raise ValueError('%s land outline changed' % ref)
        layers = tuple(unquote(x) for x in child(pad, 'layers')[1:])
        if layers != REPLACED_LAYERS:
            raise ValueError('%s land is on %r, not the back only' % (ref, layers))
        if unquote(child(pad, 'net')[1]) != net:
            raise ValueError('%s land is not on %s' % (ref, net))
        if digest == 'UNSET':
            raise ValueError('Replacement digest for %s is unset: pin it and re-review' % ref)
        if delta_digest([now]) != digest:
            raise ValueError('%s replacement differs from the pinned record' % ref)
        wanted[key] = now

    c12 = [k for k in old if old[k][0] == 'footprint' and reference_of(old[k]) == 'C12']
    if len(c12) != 1:
        raise ValueError('Expected one C12 footprint')
    props = [x for x in wanted[c12[0]] if isinstance(x, list) and x[:2] == ['property', '"%s"' % C12_PROPERTY[0]]]
    if len(props) != 1 or unquote(child(props[0], 'layer')[1]) != C12_PROPERTY[1]:
        raise ValueError('C12 hidden property is not in its accepted state')
    child(props[0], 'layer')[1] = '"%s"' % C12_PROPERTY[2]
    mismatches = [json.loads(k) for k in old if k in actual and actual[k] != wanted[k]]
    if mismatches:
        raise ValueError('Unexpected native object changes: ' + repr(mismatches))

    b = p.LoadBoard(str(board_path))
    a = p.LoadBoard(str(reference))
    if len(list(b.GetFootprints())) != 87 or b.GetCopperLayerCount() != 2:
        raise ValueError('Expected 87 footprints and two copper layers')
    for ref, (fpid, pos, angle, layer, pads) in NEW_FOOTPRINTS.items():
        f = b.FindFootprintByReference(ref)
        if (f is None or f.GetFPID().GetUniStringLibId() != fpid
                or (round(f.GetPosition().x / 1e6, 4), round(f.GetPosition().y / 1e6, 4)) != pos
                or f.GetOrientationDegrees() != angle or b.GetLayerName(f.GetLayer()) != layer):
            raise ValueError('%s placement differs from the pinned placement' % ref)
        native = sorted((q.GetNumber(), q.GetNetname(), round(q.GetPosition().x / 1e6, 4),
                         round(q.GetPosition().y / 1e6, 4), round(q.GetSize().x / 1e6, 4),
                         round(q.GetSize().y / 1e6, 4), tuple(b.GetLayerName(l) for l in q.GetLayerSet().Seq()))
                        for q in f.Pads())
        pinned = sorted((n, net, round(x, 4), round(y, 4), sx, sy, lay) for n, net, x, y, sx, sy, lay in pads)
        if native != pinned:
            raise ValueError('%s pads differ from the pinned pads: %r' % (ref, native))
        if any(q.GetDrillSize().x or q.GetDrillSize().y or q.GetAttribute() != p.PAD_ATTRIB_SMD for q in f.Pads()):
            raise ValueError('%s pads must be undrilled SMD lands' % ref)

    spreader = [z for z in b.Zones() if z.GetZoneName() == 'HEATED_ISLAND_SPREADER']
    if len(spreader) != 1 or not spreader[0].IsFilled():
        raise ValueError('HEATED_ISLAND_SPREADER missing or unfilled')
    fill = spreader[0].GetFilledPolysList(p.B_Cu)
    if fill.OutlineCount() != 1:
        raise ValueError('HEATED_ISLAND_SPREADER fills as %d islands, not one' % fill.OutlineCount())
    inside, seen = [], set()
    for f in b.GetFootprints():
        for q in f.Pads():
            if q.GetNetname() != '/HEATER_LOW' or not q.IsOnLayer(p.B_Cu):
                continue
            seen.add((f.GetReference(), q.GetNumber()))
            if not fill.Contains(q.GetPosition()):
                raise ValueError('HEATER_LOW B.Cu pad outside the spreader island: %s.%s' % (f.GetReference(), q.GetNumber()))
            inside.append([f.GetReference(), q.GetNumber(), round(q.GetPosition().x / 1e6, 3), round(q.GetPosition().y / 1e6, 3)])
    if seen != SPREADER_PADS or sum(1 for r in inside if r[0] == 'J5') != 2:
        raise ValueError('Spreader pad set differs: ' + repr(sorted(seen)))

    # Pinned filled areas (review finding 4, 2026-09-14): deleting 23 of 24 saved
    # B.Cu GND fill polygons dropped that fill from 828.88 to 119.83 mm2 and still
    # PASSed, because unfilling() strips saved fill before comparison. Areas are now
    # pinned to 0.05 mm2, which is far tighter than any real tampering and looser
    # than KiCad's own refill jitter.
    # Repinned 2026-09-14 after J107's I2C relocation: removing 107.68 mm of
    # track and 5 vias returned 25.7 mm2 of F.Cu and 46.3 mm2 of B.Cu to GND.
    # Repinned again the same day after J105/J106 became SMD lands: their front
    # annuli and the F.Cu tail that used to reach J106 through its own plated hole
    # are gone, and the front ground pour closed over all three - F.Cu GND
    # 972.5760 -> 982.1839 mm2, while the 2.4 mm of new B.Cu tail into J106 costs
    # the back pour 0.17 mm2: B.Cu GND 875.1727 -> 875.0074.
    # Repinned once more after Fab placed J108 beside J109 and routed it: the new
    # SDA run and the two /3V3D segments it displaces cost the front pour 1.06 mm2
    # (982.1839 -> 981.1283) and the back pour 4.61 mm2 (875.0074 -> 870.3926).
    PINNED_FILL = {'F.Cu:GND': 981.1283, 'B.Cu:GND': 870.3926, 'B.Cu:/HEATER_LOW': 215.1312}
    fills = {}
    for layer in (p.F_Cu, p.B_Cu):
        before, after = filled_union(a, layer), filled_union(b, layer)
        if set(before) != set(after):
            raise ValueError('Filled zone/net inventory changed')
        for key in sorted(before):
            def islands(geom):
                return len(geom.geoms) if hasattr(geom, 'geoms') else (0 if geom.is_empty else 1)
            fills[b.GetLayerName(layer) + ':' + key] = {
                'reference_mm2': round(before[key].area, 4), 'ring_mm2': round(after[key].area, 4),
                'added_mm2': round(after[key].difference(before[key]).area, 4),
                'removed_mm2': round(before[key].difference(after[key]).area, 4),
                'reference_islands': islands(before[key]), 'ring_islands': islands(after[key])}
            short = b.GetLayerName(layer) + ':' + key.split('|')[-1]
            if short in PINNED_FILL and abs(after[key].area - PINNED_FILL[short]) > 0.05:
                raise ValueError('Filled area of %s is %.4f mm2, pinned %.4f'
                                 % (short, after[key].area, PINNED_FILL[short]))

    def point(v):
        return [round(v.x / 1e6, 3), round(-v.y / 1e6, 3)]
    edges = []
    for q in b.GetDrawings():
        if q.GetLayer() != p.Edge_Cuts:
            continue
        ends = [point(q.GetStart()), point(q.GetEnd())]
        if q.GetShape() == p.SHAPE_T_SEGMENT:
            edges.append(['line', ends])
        elif q.GetShape() == p.SHAPE_T_ARC:
            edges.append(['arc', ends, point(q.GetCenter()), point(q.GetArcMid())])
        else:
            raise ValueError('Unsupported native contour primitive')
    return {'footprints': 87, 'vias': sum(isinstance(t, p.PCB_VIA) for t in b.GetTracks()),
            'all_copper_items': len(list(b.GetTracks())), 'pinned_changes': sorted(CHANGES),
            'c12_hidden_property_layer': list(C12_PROPERTY), 'removed_copper': len(removed),
            'added_objects': len(added), 'spreader_islands': 1, 'spreader_pads': sorted(inside),
            'outline_mm': [20, 86], 'edge_primitives_schema': 2, 'edge_primitives': edges,
            'filled_zones': fills,
            'scope': 'Every difference from accepted revb-86 is a pinned ring change; spreader is one island '
                     'holding every B.Cu HEATER_LOW pad. Fill areas recorded, not gated.'}


def run(board, reference, out):
    here = Path(__file__).resolve()
    paths = [board, reference, here, here.with_name('verify_revb_86.py')]
    paths += [x.with_suffix(ext) for x in (board, reference) for ext in ('.kicad_pro', '.kicad_dru', '.kicad_sch')]
    paths = [x.resolve() for x in paths]
    out = out.resolve()
    if out in paths or out.suffix != '.json':
        raise ValueError('Output must be a separate JSON report')
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'status': 'UNVERIFIED', 'input_paths': list(map(str, paths))}

    def save():
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    save()
    start = time.monotonic()
    try:
        import wx
        app = wx.AppConsole()  # noqa: F841 - pcbnew needs a live wx app
        import pcbnew
        import shapely
        paths += [Path(pcbnew.__file__), Path(pcbnew._pcbnew.__file__), Path(shapely.__file__), Path(shapely.lib.__file__)]
        fingerprints = {str(x): sha(x) for x in paths}
        report['inputs_sha256'] = fingerprints
        save()
        result = verify(board, reference)
        if fingerprints != {str(x): sha(x) for x in paths}:
            raise ValueError('Input/producer changed during verification')
        report.update(result, status='PASS', seconds=time.monotonic() - start)
        save()
        return 0
    except Exception as e:
        report.update(status='UNVERIFIED', exception=repr(e), seconds=time.monotonic() - start)
        save()
        return 2


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('board', type=Path)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--print-delta', action='store_true',
                    help='print the added/removed record digests to pin; needs no KiCad, verifies nothing')
    a = ap.parse_args()
    if a.print_delta:
        print(json.dumps(delta(a.board, a.reference), indent=2))
        raise SystemExit(0)
    if a.out is None:
        ap.error('--out is required unless --print-delta')
    raise SystemExit(run(a.board, a.reference, a.out))
