"""Independent fixed-input native shrink measurement, not a reusable release gate."""
from pathlib import Path
import sys,json,hashlib,time
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
import verify_revb_current as v
from revb_fab_checks import normalized_board
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
p=v.p;start=time.monotonic();source=root/'routing/revb-current/o2-probe.kicad_pcb';candidate=root/'routing/revb-86/o2-probe.kicad_pcb';pins={str(x):v.sha(x) for x in [source,candidate,Path(__file__),Path(v.__file__)]};b0=p.LoadBoard(str(source));b1=p.LoadBoard(str(candidate))
cu=lambda b:{q.m_Uuid.AsString():v.copper(q) for q in b.GetTracks()}
fps=lambda b:{f.GetReference():v.fp_record(f) for f in b.Footprints()}
def draw(q):
 r={'uuid':q.m_Uuid.AsString(),'layer':q.GetLayer()}
 if isinstance(q,p.PCB_TEXT):r.update(kind='text',text=q.GetText(),position=v.vec(q.GetPosition()),angle=q.GetTextAngle().AsDegrees(),size=v.vec(q.GetTextSize()),thickness=q.GetTextThickness())
 else:
  r.update(kind='shape',shape=int(q.GetShape()),start=v.vec(q.GetStart()),end=v.vec(q.GetEnd()),width=q.GetWidth())
  if q.GetShape()==p.SHAPE_T_ARC:r['mid']=v.vec(q.GetArcMid())
 return r
a={q.m_Uuid.AsString():draw(q) for q in b0.GetDrawings()};b={q.m_Uuid.AsString():draw(q) for q in b1.GetDrawings()};delta=[{'before':a.get(k),'after':b.get(k)} for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
r0=json.loads(normalized_board(source));r1=json.loads(normalized_board(candidate))
fullfps=lambda r:[x for x in r if isinstance(x,list) and x[0]=='footprint']
def zoneparams(r):return [[x[0]]+[y for y in x[1:] if not isinstance(y,list) or y[0] not in ['filled_polygon','filled_segments']] for x in r if isinstance(x,list) and x[0]=='zone']
other=lambda r:[x for x in r if not isinstance(x,list) or x[0] not in ['zone','gr_line','gr_arc','gr_text']]
def fill(b):
 out={}
 for z in b.Zones():
  if z.GetIsRuleArea():continue
  if not z.IsFilled():raise ValueError('Unfilled zone')
  for layer in [p.F_Cu,p.B_Cu]:
   if not z.IsOnLayer(layer):continue
   poly=p.SHAPE_POLY_SET(z.GetFilledPolysList(layer));poly.Unfracture();pieces=[]
   def ring(c):return [(p.ToMM(c.CPoint(i).x),p.ToMM(c.CPoint(i).y)) for i in range(c.PointCount())]
   for i in range(poly.OutlineCount()):
    shape=Polygon(ring(poly.COutline(i)),[ring(poly.CHole(i,j)) for j in range(poly.HoleCount(i))])
    if not shape.is_valid:raise ValueError('Invalid native fill polygon')
    pieces.append(shape)
   out[(z.m_Uuid.AsString(),b.GetLayerName(layer),z.GetNetname())]=unary_union(pieces)
 return out
f0=fill(b0);f1=fill(b1);fills=[]
if set(f0)!=set(f1):raise ValueError('Zone inventory changed')
for k,g0 in f0.items():
 g1=f1[k];gone=g0.difference(g1);added=g1.difference(g0);diff=g0.symmetric_difference(g1)
 fills.append({'zone_layer_net':k,'removed_area_mm2':gone.area,'added_area_mm2':added.area,'difference_bounds_mm':list(diff.bounds) if not diff.is_empty else None,'difference_below_y55_3_mm2':diff.intersection(box(0,55.3,1000,1000)).area})
report={'scope':__doc__,'inputs_sha256':pins,'source_sha256':v.sha(source),'candidate_sha256':v.sha(candidate),'native_copper_exact':cu(b0)==cu(b1),'native_copper_items':len(cu(b1)),'via_count':sum(isinstance(q,p.PCB_VIA) for q in b1.GetTracks()),'native_footprint_pad_records_exact':fps(b0)==fps(b1),'full_normalized_footprint_serialization_exact':fullfps(r0)==fullfps(r1),'all_other_normalized_board_serialization_exact':other(r0)==other(r1),'zone_parameters_exact':zoneparams(r0)==zoneparams(r1),'drawing_delta':delta,'filled_zone_differences':fills,'seconds':time.monotonic()-start}
if pins!={str(x):v.sha(x) for x in [source,candidate,Path(__file__),Path(v.__file__)]}:raise ValueError('Input changed')
(Path(__file__).parent/'geometry.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['candidate_sha256','native_copper_exact','native_copper_items','via_count','native_footprint_pad_records_exact','full_normalized_footprint_serialization_exact','all_other_normalized_board_serialization_exact','zone_parameters_exact','filled_zone_differences','seconds']},indent=2));print('drawing changes',len(delta))
