#!/usr/bin/env python3
"""Verify only the exact 3 mm head trim against the immutable accepted 89 mm PCB."""
import argparse, copy, hashlib, json, re, time
from collections import Counter
from pathlib import Path

SOURCE_SHA = '3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665'
# Absolute endpoints independently read from the accepted contour: two 2 mm
# corner arcs, a 16 mm top line, and two vertical sides ending at y139.
CHANGES = {
 'ea06dc41-11e6-594d-baab-da6250d792e7': {'start': ((100,52),(100,55)), 'mid': ((100.586,50.586),(100.586,53.586)), 'end': ((102,50),(102,53))},
 '42935040-3c92-56f0-85c9-ada5c91405bd': {'start': ((102,50),(102,53)), 'end': ((118,50),(118,53))},
 '8a7edcbb-f470-5578-9193-2c238760b099': {'start': ((118,50),(118,53)), 'mid': ((119.414,50.586),(119.414,53.586)), 'end': ((120,52),(120,55))},
 'ae686e5e-e0e3-5956-a5ee-2629db626bb1': {'end': ((100,52),(100,55))},
 '44fcae7e-d934-5b11-a976-d306df3e3d78': {'start': ((120,52),(120,55))},
 '50cb1b95-414f-55da-86b0-24bfc55b5569': {'at': ((110,51.5,0),(110,57,90))},
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse(path):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', Path(path).read_text())
    stack, roots = [], []
    for token in tokens:
        if token == '(':
            item = []
            (stack[-1] if stack else roots).append(item)
            stack.append(item)
        elif token == ')':
            if not stack: raise ValueError('Unbalanced native expression')
            stack.pop()
        elif stack: stack[-1].append(token)
        else: raise ValueError('Unexpected native token')
    if stack or len(roots) != 1 or roots[0][0] != 'kicad_pcb':
        raise ValueError('Incomplete native board')
    return roots[0]


def child(node, name):
    rows = [x for x in node if isinstance(x,list) and x and x[0] == name]
    if len(rows) != 1: raise ValueError('Expected single '+name)
    return rows[0]


def unfilling(node):
    return [x for x in node if not (isinstance(x,list) and x and x[0] in ('filled_polygon','fill_segments'))]


def records(tree):
    rows = {}
    metadata = []
    for node in tree[1:]:
        if not isinstance(node,list): raise ValueError('Unexpected root atom')
        ids = [x[1] for x in node if isinstance(x,list) and x and x[0]=='uuid']
        if ids:
            if len(ids)!=1 or ids[0] in rows: raise ValueError('Duplicate object UUID')
            rows[ids[0]] = unfilling(node) if node[0]=='zone' else node
        else: metadata.append(node)
    return rows, metadata


def filled_union(board, layer):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polygons=[]
    for z in board.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(layer): continue
        if not z.IsFilled(): raise ValueError('Unfilled native zone')
        import pcbnew
        ps=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(layer)); ps.Unfracture()
        for i in range(ps.OutlineCount()):
            def points(chain):
                return [(chain.CPoint(k).x/1e6,chain.CPoint(k).y/1e6) for k in range(chain.PointCount())]
            poly=Polygon(points(ps.Outline(i)),[points(ps.Hole(i,j)) for j in range(ps.HoleCount(i))])
            if not poly.is_valid: raise ValueError('Invalid native filled polygon')
            polygons.append((z.m_Uuid.AsString()+'|'+z.GetNetname(),poly))
    nets={n for n,_ in polygons}
    return {n:unary_union([p for name,p in polygons if name==n]) for n in nets}


def verify(board_path, reference):
    import pcbnew as p
    from shapely.geometry import box
    if sha(reference)!=SOURCE_SHA: raise ValueError('Accepted 89 mm source hash changed')
    for ext in ('.kicad_pro','.kicad_dru','.kicad_sch'):
        if sha(board_path.with_suffix(ext))!=sha(reference.with_suffix(ext)):
            raise ValueError('Project/rules/schematic changed: '+ext)
    old, old_meta=records(parse(reference)); actual, meta=records(parse(board_path))
    if Counter(map(repr,meta))!=Counter(map(repr,old_meta)): raise ValueError('Board metadata/setup/layers changed')
    if set(actual)!=set(old): raise ValueError('Native object UUID inventory changed')
    wanted=copy.deepcopy(old)
    for uid, fields in CHANGES.items():
        key=json.dumps(uid)
        if key not in wanted: raise ValueError('Missing approved drawing '+uid)
        node=wanted[key]
        if uid=='50cb1b95-414f-55da-86b0-24bfc55b5569':
            if node[0]!='gr_text' or node[1]!='"CABLE"': raise ValueError('Unexpected cable annotation')
        elif child(node,'layer')[1]!='"Edge.Cuts"': raise ValueError('Approved contour object is off Edge.Cuts')
        for name,(before,after) in fields.items():
            q=child(node,name)
            if tuple(float(x) for x in q[1:])!=before: raise ValueError('Pinned drawing pose differs '+uid)
            q[1:]=[format(x,'.12g') for x in after]
    mismatches=[json.loads(uid) for uid in old if actual[uid]!=wanted[uid]]
    if mismatches: raise ValueError('Unexpected full native object changes: '+repr(mismatches))
    b=p.LoadBoard(str(board_path)); a=p.LoadBoard(str(reference))
    if len(list(b.GetFootprints()))!=83 or b.GetCopperLayerCount()!=2: raise ValueError('Expected 83 footprints/two copper layers')
    areas={}
    for layer in (p.F_Cu,p.B_Cu):
        before=filled_union(a,layer); after=filled_union(b,layer)
        if set(before)!=set(after): raise ValueError('Filled net inventory changed')
        for net in before:
            clip=box(0,55.3,1000,1000)
            delta=before[net].intersection(clip).symmetric_difference(after[net].intersection(clip)).area
            added=after[net].difference(before[net]).area
            removed=before[net].difference(after[net]).area
            areas[b.GetLayerName(layer)+':'+net]={'below_y55_3':delta,'added':added,'removed':removed}
            if delta>1e-8 or added>1e-8 or (not net.endswith('|GND') and removed>1e-8):
                raise ValueError('Unexpected native fill change: '+str((layer,net,delta,added,removed)))
    def point(v): return [round(v.x/1e6,3),round(-v.y/1e6,3)]
    edges=[]
    for q in b.GetDrawings():
        if q.GetLayer()!=p.Edge_Cuts: continue
        ends=[point(q.GetStart()),point(q.GetEnd())]
        if q.GetShape()==p.SHAPE_T_SEGMENT: edges.append(['line',ends])
        elif q.GetShape()==p.SHAPE_T_ARC: edges.append(['arc',ends,point(q.GetCenter()),point(q.GetArcMid())])
        else: raise ValueError('Unsupported native contour primitive')
    return {'footprints':83,'vias':sum(isinstance(t,p.PCB_VIA) for t in b.GetTracks()),
            'all_copper_items':len(list(b.GetTracks())),'modified_drawings':sorted(CHANGES),
            'outline_mm':[20,86],'edge_primitives_schema':2,'edge_primitives':edges,'fill_comparison_y_min_mm':55.3,
            'filled_difference_mm2':areas,'scope':'Full native objects and zone definitions unchanged except six exact drawings; native fill below y55.3 unchanged; only GND removal allowed above that'}


def run(board,reference,out):
    paths=[board,reference,Path(__file__).resolve()]
    paths += [x.with_suffix(ext) for x in (board,reference) for ext in ('.kicad_pro','.kicad_dru','.kicad_sch')]
    paths=[x.resolve() for x in paths];out=out.resolve()
    if out in paths or out.suffix!='.json': raise ValueError('Output must be a separate JSON report')
    out.parent.mkdir(parents=True,exist_ok=True)
    report={'schema':1,'status':'UNVERIFIED','input_paths':list(map(str,paths))}
    def save():out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    save();start=time.monotonic()
    try:
        import wx
        app=wx.AppConsole()
        import pcbnew,shapely
        paths += [Path(pcbnew.__file__),Path(pcbnew._pcbnew.__file__),Path(shapely.__file__),Path(shapely.lib.__file__)]
        fingerprints={str(x):sha(x) for x in paths};report['inputs_sha256']=fingerprints;save()
        result=verify(board,reference)
        if fingerprints!={str(x):sha(x) for x in paths}:raise ValueError('Input/producer changed during verification')
        report.update(result,status='PASS',seconds=time.monotonic()-start);save();return 0
    except Exception as e:
        report.update(status='UNVERIFIED',exception=repr(e),seconds=time.monotonic()-start);save();return 2

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('board',type=Path);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();raise SystemExit(run(a.board,a.reference,a.out))
