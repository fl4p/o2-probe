"""Fail-closed checks for Rev B review exports; no production qualification claim."""
from collections import Counter
from decimal import Decimal
import json
import math
from pathlib import Path
import re
from make_fab import (expected_outline_primitives, expected_thermal_slot_primitives,
                      parse_gerber_primitives, parse_gerber_regions)

LAYERS = ['F.Cu', 'B.Cu', 'F.Mask', 'B.Mask', 'F.Paste', 'B.Paste',
          'F.Silkscreen', 'B.Silkscreen', 'Edge.Cuts']
FUNCTIONS = ['Copper,L1,Top', 'Copper,L2,Bot', 'Soldermask,Top', 'Soldermask,Bot',
             'Paste,Top', 'Paste,Bot', 'Legend,Top', 'Legend,Bot', 'Profile,NP']
# Individual manual-assembly dispositions: docs/REVB-ASSEMBLY.md. No DRC
# exclusions are installed: these findings remain in both the report and ZIP.
COURTYARDS = {tuple(sorted(p.split('/'))) for p in (
    'C14/C26', 'D1/J102', 'D1/J101', 'R10/R11', 'C3/L1', 'C7/C8',
    'C1/U1', 'C5/U2', 'J104/R3', 'D2/J103', 'D2/J104', 'TP3/U4',
    'J103/R2', 'C4/C7', 'Q2/TP6')}


def check_drc(path):
    report = json.loads(path.read_text())
    for key in ('violations', 'schematic_parity', 'unconnected_items', 'ignored_checks'):
        if not isinstance(report.get(key), list):
            raise ValueError(f'{path}: absent/malformed {key}')
    if report['ignored_checks'] or report['schematic_parity'] or report['unconnected_items']:
        raise ValueError('Ignored checks, schematic parity or unconnected copper in DRC')
    if set(report.get('included_severities', [])) != {'error', 'warning', 'exclusion'}:
        raise ValueError('DRC did not include all severities')
    pairs = []
    for finding in report['violations']:
        if finding.get('severity') != 'warning' or finding.get('type') != 'courtyards_overlap':
            raise ValueError(f'Unaccepted DRC finding: {finding}')
        refs = []
        for item in finding['items']:
            match = re.fullmatch(r'Footprint (\w+)', item['description'])
            if match is None:
                raise ValueError('Unrecognised courtyard item')
            refs.append(match.group(1))
        pairs.append(tuple(sorted(refs)))
    if Counter(pairs) != Counter(COURTYARDS):
        raise ValueError(f'Courtyard set changed: {pairs}')
    return {'errors': 0, 'unconnected': 0, 'parity': 0, 'silkscreen': 0,
            'manual_assembly_courtyard_warnings': len(pairs)}


def clipped_area(points, bounds):
    """Signed polygon clipping also preserves KiCad's bridged hole contours."""
    for axis, boundary, greater in ((0, bounds[0], True), (0, bounds[2], False),
                                     (1, bounds[1], True), (1, bounds[3], False)):
        output = []
        if not points:
            return 0.0
        previous = points[-1]
        for current in points:
            old_in = previous[axis] >= boundary if greater else previous[axis] <= boundary
            new_in = current[axis] >= boundary if greater else current[axis] <= boundary
            if old_in != new_in:
                t = (boundary - previous[axis]) / (current[axis] - previous[axis])
                output.append(tuple(a + t * (b-a) for a, b in zip(previous, current)))
            if new_in:
                output.append(current)
            previous = current
        points = output
    return abs(sum(a[0]*b[1] - b[0]*a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2


def check_gerbers(directory):
    expected = {f'o2-probe-{l.replace(".", "_")}.gbr': f
                for l, f in zip(LAYERS, FUNCTIONS)}
    if {p.name for p in directory.glob('*.gbr')} != set(expected):
        raise ValueError('Missing or extra Gerber layer')
    texts = {}
    formats = {}
    for name, function in expected.items():
        text = (directory/name).read_text()
        if f'%TF.FileFunction,{function}*%' not in text or not text.rstrip().endswith('M02*'):
            raise ValueError(f'{name}: wrong X2 layer or incomplete output')
        fmt = re.search(r'%FSLAX\d(\d)Y\d(\d)\*%', text)
        if fmt is None or not re.search(r'X-?\d+Y-?\d+', text):
            raise ValueError(f'{name}: missing coordinates/format')
        texts[name] = text
        formats[name] = tuple(map(int, fmt.groups()))
    edge = 'o2-probe-Edge_Cuts.gbr'
    primitives = parse_gerber_primitives(texts[edge], *formats[edge])
    if primitives != expected_outline_primitives() + expected_thermal_slot_primitives():
        raise ValueError('Exported outline/thermal slot geometry changed')
    regions = 0
    for layer in ('F_Cu', 'B_Cu'):
        name = f'o2-probe-{layer}.gbr'
        # The exporter emits linear zone regions. An unrecognised command
        # cannot silently disappear from the copper-area check.
        for region in re.findall(r'G36\*(.*?)G37\*', texts[name], re.S):
            for line in region.splitlines():
                line = line.strip()
                if line and line != 'G01*' and not re.fullmatch(r'X-?\d+Y-?\d+(?:D0[12])?\*', line):
                    raise ValueError(f'{layer}: unsupported region record {line}')
        polygons = parse_gerber_regions(texts[name], *formats[name])
        if not polygons:
            raise ValueError(f'{layer}: missing filled copper')
        for polygon in polygons:
            if clipped_area(polygon, (100, -135, 120, -133)) > 1e-7:
                raise ValueError(f'{layer}: zone copper bridges thermal fill gap')
        regions += len(polygons)
    return {'layers': LAYERS, 'outline_mm': [20, 107], 'thermal_slots': 4,
            'copper_regions': regions, 'thermal_fill_gap_clear': True}


def read_drills(path):
    """Read KiCad metric/decimal Excellon hits and routed oblongs."""
    text = path.read_text()
    if 'METRIC' not in text or not text.rstrip().endswith('M30'):
        raise ValueError(f'{path}: incomplete or nonmetric drills')
    tools = {str(int(n)): float(d) for n, d in re.findall(r'^T(\d+)C([\d.]+)$', text, re.M)}
    selected = None
    start = None
    routing = False
    result = Counter()
    coord = re.compile(r'(?:G0[01])?X(-?[\d.]+)Y(-?[\d.]+)$')
    for line in text.splitlines():
        if re.fullmatch(r'T\d+', line):
            selected = str(int(line[1:])); continue
        if line == 'M15':
            if start is None or routing:
                raise ValueError('Malformed slot start')
            routing = True; continue
        if line == 'M16':
            if not routing:
                raise ValueError('Unmatched slot end')
            routing = False; start = None; continue
        match = coord.fullmatch(line)
        if match:
            if selected not in tools:
                raise ValueError('Coordinate without known drill tool')
            point = tuple(round(float(v), 6) for v in match.groups())
            if line.startswith('G00'):
                start = point
            elif line.startswith('G01'):
                if not routing or start is None:
                    raise ValueError('Route without start')
                result[('slot', tools[selected], tuple(sorted((start, point))))] += 1
                start = point
            else:
                if routing:
                    raise ValueError('Hit while routing')
                result[('hit', tools[selected], point)] += 1
        elif ('X' in line or 'Y' in line) and not line.startswith(';'):
            raise ValueError(f'Unparsed drill coordinate: {line}')
    if routing:
        raise ValueError('Unterminated drill route')
    return result


def check_drills(directory, witness):
    actual = {p.name for p in directory.glob('*.drl')}
    expected_files = {'o2-probe-PTH.drl', 'o2-probe-NPTH.drl'}
    if actual != expected_files:
        raise ValueError('Drill file inventory differs')
    def frozen(value):
        return tuple(frozen(v) for v in value) if isinstance(value, list) else value
    for kind in ('PTH', 'NPTH'):
        records = witness.get('drills', {}).get(kind)
        if not isinstance(records, list) or not records:
            raise ValueError(f'No {kind} source drill inventory')
        def finite(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        def valid_record(record):
            if not isinstance(record, (list, tuple)) or len(record) != 3:
                raise ValueError('Malformed drill record')
            shape, diameter, geometry = record
            if shape not in ('hit', 'slot') or not finite(diameter) or diameter <= 0:
                raise ValueError('Unknown drill kind or invalid diameter')
            points = [geometry] if shape == 'hit' else geometry
            if not isinstance(points, (list, tuple)) or len(points) != (1 if shape == 'hit' else 2):
                raise ValueError('Wrong drill endpoint count')
            if any(not isinstance(p, (list, tuple)) or len(p) != 2 or
                   not all(finite(v) for v in p) for p in points):
                raise ValueError('Missing or nonfinite drill coordinates')
            if shape == 'slot' and points[0] == points[1]:
                raise ValueError('Zero-length routed slot')
        for record in records:
            valid_record(record)
        expected = Counter(frozen(v) for v in records)
        actual = read_drills(directory/f'o2-probe-{kind}.drl')
        for record in actual:
            valid_record(record)
        # KiCad 10 metric decimal Excellon quantizes positions to 0.001 mm.
        # Match every hit/slot one-to-one within half that export quantum;
        # diameters use the same quantum; plating and counts match exactly.
        def close(a, b):
            if a[0] != b[0] or abs(a[1]-b[1]) > .000500001:
                return False
            pa = [a[2]] if a[0] == 'hit' else a[2]
            pb = [b[2]] if b[0] == 'hit' else b[2]
            return all(abs(x-y) <= .000500001 for p, q in zip(pa,pb) for x,y in zip(p,q))
        remaining = list(expected.elements())
        for record in actual.elements():
            matches = [i for i, want in enumerate(remaining) if close(record, want)]
            if len(matches) != 1:
                raise ValueError(f'{kind}: missing/ambiguous source match for drill {record}')
            remaining.pop(matches[0])
        if remaining:
            raise ValueError(f'{kind}: {len(remaining)} source drills absent from export')
    return {'drill_geometry_matches_board': True,
            'coordinate_quantum_mm': .001, 'maximum_coordinate_error_mm': .0005,
            'PTH_count': len(witness['drills']['PTH']), 'NPTH_count': len(witness['drills']['NPTH'])}


def normalized_board(path):
    """Ignore fresh item IDs/order, preserving polygon vertex order and fields."""
    tokens = iter(re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', path.read_text()))
    stack = []
    roots = []
    for token in tokens:
        if token == '(':
            item = []
            if stack:
                stack[-1].append(item)
            else:
                roots.append(item)
            stack.append(item)
        elif token == ')':
            if not stack:
                raise ValueError('Unbalanced PCB expression')
            stack.pop()
        elif stack:
            stack[-1].append(token)
        else:
            raise ValueError('Unexpected token outside PCB')
    if stack or len(roots) != 1 or roots[0][0] != 'kicad_pcb':
        raise ValueError('Incomplete PCB expression')
    def normalize(item):
        atoms = [v for v in item if isinstance(v, str)]
        children = [normalize(v) for v in item if isinstance(v, list)
                    and v and v[0] not in ('uuid', 'tstamp')]
        if item[0] == 'pts':
            # KiCad refill may insert a vertex on an existing straight edge.
            # Remove only exact, forward collinear interior vertices: neither
            # tolerance nor reversed winding can hide a geometry change.
            reduced = []
            for point in children:
                reduced.append(point)
                while len(reduced) >= 3:
                    a, b, c = reduced[-3:]
                    if any(len(p) != 3 or p[0] != 'xy' for p in (a,b,c)):
                        raise ValueError('Malformed polygon vertex')
                    ax, ay, bx, by, cx, cy = map(Decimal, a[1:]+b[1:]+c[1:])
                    if ((bx-ax)*(cy-by) != (by-ay)*(cx-bx) or
                            (bx-ax)*(cx-bx)+(by-ay)*(cy-by) < 0):
                        break
                    reduced.pop(-2)
            children = reduced
        else:
            children.sort(key=lambda v: json.dumps(v, separators=(',', ':')))
        return atoms + children
    return json.dumps(normalize(roots[0]), separators=(',', ':'))
