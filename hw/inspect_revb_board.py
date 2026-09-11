#!/usr/bin/env python3
"""Extract the exact drill inventory and physical build facts using KiCad."""
import json
import math
from pathlib import Path
import sys
import wx
_APP = wx.AppConsole()
import pcbnew


def inspect(path, *, tmp302=False):
    b = pcbnew.LoadBoard(str(path))
    if b is None or b.GetCopperLayerCount() != 2:
        raise ValueError('Expected a two-layer Rev B board')
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    if len(fps) != (101 if tmp302 else 99) or {'RV1', 'J5', 'F3'} & fps.keys() or ({'U16','C35'} <= fps.keys()) != tmp302:
        raise ValueError('Unexpected Rev B component inventory')
    drills = {'PTH': [], 'NPTH': []}
    def drill(position, size, angle, kind):
        dx, dy = size
        x, y = position.x/1e6, position.y/1e6
        if dx == dy:
            record = ('hit', round(dx, 6), (round(x,6), round(-y,6)))
        else:
            theta = math.radians(-angle + (90 if dy > dx else 0))
            half = abs(dx-dy)/2
            points = [(round(x+s*half*math.cos(theta),6),
                       round(-(y+s*half*math.sin(theta)),6)) for s in (-1,1)]
            record = ('slot', round(min(dx,dy),6), tuple(sorted(points)))
        drills[kind].append(record)
    for f in fps.values():
        for p in f.Pads():
            d = p.GetDrillSize()
            if d.x or d.y:
                drill(p.GetPosition(), (d.x/1e6,d.y/1e6), p.GetOrientationDegrees(),
                      'NPTH' if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else 'PTH')
    for v in b.GetTracks():
        if v.GetClass() == 'PCB_VIA':
            if v.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise ValueError('Unexpected blind/microvia')
            d = v.GetDrillValue()/1e6
            drill(v.GetPosition(), (d,d), 0, 'PTH')
    return {'layers': 2, 'components': len(fps), 'drills': drills,
            'external_ring': 'Absent in Rev B; J5/F3 deferred to optional Rev C',
            'production_qualified': False}

if __name__ == '__main__':
    if len(sys.argv) not in (3,4) or (len(sys.argv)==4 and sys.argv[3]!='--tmp302'):
        raise SystemExit('usage: inspect_revb_board.py BOARD JSON')
    Path(sys.argv[2]).write_text(json.dumps(inspect(Path(sys.argv[1]),tmp302=len(sys.argv)==4), indent=2)+'\n')
