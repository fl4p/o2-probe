#!/usr/bin/env python3
"""Native 87-footprint witness and exact drill inventory for the Rev B 86 mm ring board.

A clone of inspect_revb_current_fab.py for routing/revb-86-ring. Each difference
is deliberate:

- 87 footprints: J5 (membrane-ring lands), J107 (external-sensor / UART
  pads) and the two single I2C lands J108 / J109 are added. J5 is therefore
  required, not retired.
- The witness is taken from the CANDIDATE board. The 86 mm trim changed no drill,
  so the 86 mm exporter could witness the reference board; this revision adds
  and removes vias, so only the board being exported can witness its drills.
- The outline is not re-derived here. verify_revb_86_ring.py pins every outline
  object against the accepted board and must PASS before this runs.

The protected-net, via/trace floor and CELL_RE rules are the ones in
verify_revb_current.load_state, applied unchanged.
"""
import argparse
import hashlib
import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

COMPONENTS = 87
RETIRED = {'RV1', 'F3', 'U8'}
REQUIRED = {'U16', 'C35', 'U15', 'C36', 'D3', 'J5', 'J107'}


def load_state(board_path, xml_path):
    import pcbnew as p
    from verify_revb_current import PROTECTED, copper, fp_record
    root = ET.parse(xml_path).getroot()
    comps = {}
    for c in root.findall('./components/comp'):
        ref = c.attrib['ref']
        if ref in comps:
            raise ValueError('Duplicate schematic reference ' + ref)
        comps[ref] = (c.findtext('value'), c.findtext('footprint'))
    if len(comps) != COMPONENTS:
        raise ValueError('Expected %d-component netlist; got %d' % (COMPONENTS, len(comps)))
    mapping = {}
    for n in root.findall('./nets/net'):
        for node in n.findall('node'):
            k = (node.attrib['ref'], node.attrib['pin'])
            if k in mapping:
                raise ValueError('Duplicate netlist pin ' + str(k))
            mapping[k] = n.attrib['name']
    if not mapping:
        raise ValueError('Empty netlist pads')
    b = p.LoadBoard(str(board_path))
    problems = []
    fps = {}
    for f in b.Footprints():
        ref = f.GetReference()
        if ref in fps:
            raise ValueError('Duplicate native reference ' + ref)
        fps[ref] = fp_record(f)
    if set(fps) != set(comps):
        problems.append('Native/schematic reference sets differ')
    seen = set()
    for ref, f in fps.items():
        if ref not in comps:
            continue
        if (f['value'], f['fpid']) != comps[ref]:
            problems.append('Value/FPID mismatch ' + ref)
        for q in f['pads']:
            if not q['number']:
                continue
            key = (ref, q['number'])
            seen.add(key)
            if key not in mapping or q['net'] != mapping[key]:
                problems.append('Pad net mismatch ' + str(key))
    if set(mapping) != seen:
        problems.append('Schematic/native numbered pad inventory differs')
    all_cu = {q.m_Uuid.AsString(): copper(q) for q in b.GetTracks()}
    if not all_cu:
        raise ValueError('No native copper')
    critical = {uid: r for uid, r in all_cu.items() if r['locked']}
    if not critical:
        raise ValueError('No locked critical inventory')
    for net in sorted(PROTECTED):
        selected = [r for r in all_cu.values() if r['net'] == net]
        if not selected:
            problems.append('Missing critical net copper ' + net)
        if any(not r['locked'] for r in selected):
            problems.append('Unlocked critical net copper ' + net)
    for uid, r in all_cu.items():
        if r['kind'] == 'via':
            if (r['drill'] < p.FromMM(.2) or r['diameter'] < p.FromMM(.4)
                    or r['diameter'] - r['drill'] < p.FromMM(.2)):
                problems.append('Via floor ' + uid)
            if r['net'] == '/CELL_RE':
                problems.append('CELL_RE via ' + uid)
        else:
            if r['width'] < p.FromMM(.1):
                problems.append('Trace floor ' + uid)
            if r['net'] == '/CELL_RE' and r['layer'] != p.F_Cu:
                problems.append('CELL_RE off F.Cu ' + uid)
    return {'footprints': fps, 'critical_copper': critical}, all_cu, problems


def inspect(board, netlist):
    import pcbnew
    state, copper, problems = load_state(board, netlist)
    if problems:
        raise ValueError(problems)
    b = pcbnew.LoadBoard(str(board))
    if b.GetCopperLayerCount() != 2 or b.GetDesignSettings().GetBoardThickness() != pcbnew.FromMM(1.6):
        raise ValueError('Expected two copper layers and 1.6 mm thickness')
    fps = list(b.GetFootprints())
    if len(fps) != COMPONENTS or len(state['footprints']) != COMPONENTS:
        raise ValueError('Expected %d ring-board footprints' % COMPONENTS)
    if RETIRED & state['footprints'].keys():
        raise ValueError('Retired component present')
    if not REQUIRED <= state['footprints'].keys():
        raise ValueError('Ring-board device inventory incomplete')
    drills = {'PTH': [], 'NPTH': []}

    def drill(position, size, angle, kind):
        dx, dy = size
        if min(dx, dy) <= 0:
            raise ValueError('Nonpositive drill dimension')
        x, y = position.x / 1e6, position.y / 1e6
        if dx == dy:
            record = ('hit', round(dx, 6), (round(x, 6), round(-y, 6)))
        else:
            theta = math.radians(-angle + (90 if dy > dx else 0))
            half = abs(dx - dy) / 2
            ends = [(round(x + s * half * math.cos(theta), 6),
                     round(-(y + s * half * math.sin(theta)), 6)) for s in (-1, 1)]
            record = ('slot', round(min(dx, dy), 6), tuple(sorted(ends)))
        drills[kind].append(record)

    for f in fps:
        for p in f.Pads():
            d = p.GetDrillSize()
            if d.x or d.y:
                drill(p.GetPosition(), (d.x / 1e6, d.y / 1e6), p.GetOrientationDegrees(),
                      'NPTH' if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else 'PTH')
    for v in b.GetTracks():
        if isinstance(v, pcbnew.PCB_VIA):
            if v.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise ValueError('Unexpected blind/microvia')
            d = v.GetDrillValue() / 1e6
            drill(v.GetPosition(), (d, d), 0, 'PTH')
    return {'layers': 2, 'components': COMPONENTS, 'thickness_mm': 1.6, 'drills': drills,
            'footprints': state['footprints'], 'production_qualified': False}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_witness(board, netlist, output):
    board, netlist, output = [Path(x).resolve() for x in (board, netlist, output)]
    paths = [board, netlist, board.with_suffix('.kicad_pro'), board.with_suffix('.kicad_dru'),
             Path(__file__).resolve(), Path(__file__).resolve().with_name('verify_revb_current.py')]
    if output in set(paths) or output.suffix != '.json':
        raise ValueError('Witness output must be a separate .json file, never an input or producer')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'status': 'UNVERIFIED', 'input_paths': [str(x) for x in paths],
              'scope': 'Ring-board native inventory/parity, protected-copper and floor rules, and source drill '
                       'witness taken from the candidate board; not fabrication acceptance'}

    def save():
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    save()  # invalidates any prior success before native imports or missing-input failures
    started = time.monotonic()
    try:
        import wx
        app = wx.AppConsole()  # noqa: F841 - pcbnew needs a live wx app
        import pcbnew
        import verify_revb_current  # noqa: F401 - producer fingerprinted below
        paths += [Path(pcbnew.__file__).resolve(), Path(pcbnew._pcbnew.__file__).resolve()]
        report['input_paths'] = [str(x) for x in paths]
        before = {str(x): sha(x) for x in paths}
        report['inputs_sha256'] = before
        report['kicad_version'] = pcbnew.GetBuildVersion()
        save()
        result = inspect(board, netlist)
        if before != {str(x): sha(x) for x in paths}:
            raise ValueError('Native witness input or producer changed during probe')
        report.update(result, status='PASS', seconds=time.monotonic() - started)
        save()
        return 0
    except Exception as error:
        report.update(status='UNVERIFIED', exception=repr(error), seconds=time.monotonic() - started)
        save()
        return 2


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('board', 'netlist', 'output'):
        ap.add_argument(key, type=Path)
    a = ap.parse_args()
    raise SystemExit(run_witness(a.board, a.netlist, a.output))
