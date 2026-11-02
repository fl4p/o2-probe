#!/usr/bin/env python3
"""Native 83-footprint witness and exact drill inventory for current Rev B exports."""
import argparse, hashlib, json, math, time
from pathlib import Path


def inspect(board, netlist, baseline):
    import pcbnew
    from verify_revb_current import load_state
    state, copper, problems = load_state(board, netlist, baseline)
    if problems:
        raise ValueError(problems)
    b = pcbnew.LoadBoard(str(board))
    if b.GetCopperLayerCount() != 2 or b.GetDesignSettings().GetBoardThickness() != pcbnew.FromMM(1.6):
        raise ValueError('Expected two copper layers and 1.6 mm thickness')
    fps = list(b.GetFootprints())
    if len(fps) != 83 or len(state['footprints']) != 83:
        raise ValueError('Expected 83 current footprints')
    if {'RV1', 'J5', 'F3', 'U8'} & state['footprints'].keys():
        raise ValueError('Retired component present')
    if not {'U16', 'C35', 'U15', 'C36', 'D3'} <= state['footprints'].keys():
        raise ValueError('Current device inventory incomplete')
    drills = {'PTH': [], 'NPTH': []}
    def drill(position, size, angle, kind):
        dx, dy = size
        if min(dx, dy) <= 0:
            raise ValueError('Nonpositive drill dimension')
        x, y = position.x/1e6, position.y/1e6
        if dx == dy:
            record = ('hit', round(dx, 6), (round(x, 6), round(-y, 6)))
        else:
            theta = math.radians(-angle + (90 if dy > dx else 0))
            half = abs(dx-dy)/2
            ends = [(round(x+s*half*math.cos(theta), 6),
                     round(-(y+s*half*math.sin(theta)), 6)) for s in (-1, 1)]
            record = ('slot', round(min(dx, dy), 6), tuple(sorted(ends)))
        drills[kind].append(record)
    for f in fps:
        for p in f.Pads():
            d = p.GetDrillSize()
            if d.x or d.y:
                drill(p.GetPosition(), (d.x/1e6, d.y/1e6), p.GetOrientationDegrees(),
                      'NPTH' if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else 'PTH')
    for v in b.GetTracks():
        if isinstance(v, pcbnew.PCB_VIA):
            if v.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise ValueError('Unexpected blind/microvia')
            d = v.GetDrillValue()/1e6
            drill(v.GetPosition(), (d, d), 0, 'PTH')
    return {'layers': 2, 'components': 83, 'thickness_mm': 1.6, 'drills': drills,
            'footprints': state['footprints'], 'production_qualified': False}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_witness(board, netlist, baseline, output):
    board, netlist, baseline, output = [Path(x).resolve() for x in (board, netlist, baseline, output)]
    paths = [board, netlist, baseline, board.with_suffix('.kicad_pro'),
             board.with_suffix('.kicad_dru'), Path(__file__).resolve(),
             Path(__file__).resolve().with_name('verify_revb_current.py')]
    if output in set(paths) or output.suffix != '.json':
        raise ValueError('Witness output must be a separate .json file, never an input or producer')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'status': 'UNVERIFIED', 'input_paths': [str(x) for x in paths],
              'scope': 'Current native inventory/parity, dimensions and source drill witness; not fabrication acceptance'}
    def save():
        output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    save()  # Also invalidates prior success before native imports or missing-input failures.
    started = time.monotonic()
    try:
        import wx
        app = wx.AppConsole()
        import pcbnew
        import verify_revb_current
        paths += [Path(pcbnew.__file__).resolve(), Path(pcbnew._pcbnew.__file__).resolve()]
        report['input_paths'] = [str(x) for x in paths]
        before = {str(x): sha(x) for x in paths}
        report['inputs_sha256'] = before
        report['kicad_version'] = pcbnew.GetBuildVersion()
        save()
        result = inspect(board, netlist, baseline)
        if before != {str(x): sha(x) for x in paths}:
            raise ValueError('Native witness input or producer changed during probe')
        report.update(result, status='PASS', seconds=time.monotonic()-started)
        save()
        return 0
    except Exception as error:
        report.update(status='UNVERIFIED', exception=repr(error), seconds=time.monotonic()-started)
        save()
        return 2


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('board', 'netlist', 'baseline', 'output'):
        ap.add_argument(key, type=Path)
    a = ap.parse_args()
    raise SystemExit(run_witness(a.board, a.netlist, a.baseline, a.output))
