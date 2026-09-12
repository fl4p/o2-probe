"""Bounded reference/body screen for this generator's saved schematic format.

Uses emitted anchors, not the generator's old guessed property positions.
Reference glyph extents remain estimates. Quarter-turn fields, values, labels,
pins and wire collisions still require rendered review; this is not visual signoff.
"""
import math
import re

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


def reference_body_hits(model, schematic):
    # A malformed/truncated subject must not turn into zero inspected objects.
    depth = 0
    quoted = escaped = False
    for char in schematic:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced schematic')
    if quoted or depth or not schematic.startswith('(kicad_sch'):
        raise ValueError('malformed schematic')
    instances = {}
    for block in re.findall(r'^\t\(symbol\n.*?^\t\)', schematic, re.M | re.S):
        prop = next((line for line in block.splitlines()
                     if line.startswith('\t\t(property "Reference" ')), None)
        if prop is None:
            raise ValueError('instance without reference field')
        ref_match = re.search(r'\(property "Reference" "([^"\\]+)"', prop)
        pose = re.search(r'^\t\t\(at ('+NUM+r') ('+NUM+r') ('+NUM+r')\)', block, re.M)
        field = re.search(r'\(at ('+NUM+r') ('+NUM+r') ('+NUM+r')\)', prop)
        font = re.search(r'\(size ('+NUM+r') ('+NUM+r')\)', prop)
        lib = re.search(r'\(lib_id "([^"\\]+)"\)', block)
        if not all((ref_match, pose, field, font, lib)):
            raise ValueError('unsupported instance/reference encoding')
        ref = ref_match[1]
        # Power symbols are added by the generator finalization stage, and
        # their hidden fields/body graphics are outside this reference screen.
        if ref.startswith('#PWR'):
            continue
        if ref in instances or ref not in model.INST:
            raise ValueError('duplicate or foreign reference '+ref)
        if lib[1] != model.INST[ref]['lib_id']:
            raise ValueError('symbol body model does not match '+ref)
        x, y, angle = map(float, pose.groups())
        tx, ty, ta = map(float, field.groups())
        fw, fh = map(float, font.groups())
        if not all(math.isfinite(v) for v in (x,y,angle,tx,ty,ta,fw,fh)) or min(fw,fh)<=0:
            raise ValueError('invalid reference geometry '+ref)
        if angle not in (0,90,180,270) or ta != 0 or '(justify' in prop:
            raise ValueError('unsupported reference orientation/justification '+ref)
        sym = model.SYMS[lib[1]]
        hw, hh = sym['half_w'], sym['half_h']
        if angle in (90,270):
            hw, hh = hh, hw
        # Centered, horizontal generated references only. Native KiCad may
        # transform quarter-turn properties, which this screen does not model.
        visible = not ref.startswith('#') and 'hide' not in prop
        covered = visible and angle in (0,180)
        width = len(ref) * fw * .85
        instances[ref] = {'body': (x-hw,y-hh,x+hw,y+hh),
                          'text': (tx-width/2,ty-fh/2,tx+width/2,ty+fh/2),
                          'covered': covered, 'visible': visible}
    if not instances or set(instances) != set(model.INST):
        raise ValueError('incomplete schematic instance inventory')
    hits = []
    for ref, item in instances.items():
        if not item['covered']:
            continue
        a,b,c,d = item['text']
        for other, target in instances.items():
            if other == ref or other.startswith('#'):
                continue
            e,f,g,h = target['body']
            ox,oy = min(c,g)-max(a,e), min(d,h)-max(b,f)
            if ox > .4 and oy > .4:
                hits.append((round(ox*oy,2), ref+'.ref (saved anchor)', other+' body'))
    return hits, {'instances':len(instances),
                  'references_checked':sum(i['covered'] for i in instances.values()),
                  'quarter_turn_references_not_checked':sum(i['visible'] and not i['covered'] for i in instances.values())}
