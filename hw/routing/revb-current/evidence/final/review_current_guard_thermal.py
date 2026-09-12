#!/usr/bin/env python3
"""Bounded diagnostic of current native filled copper, not a release validator."""
import hashlib,json,math,sys,time,shutil
from pathlib import Path
import wx
APP=wx.AppConsole()
import pcbnew as p
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(sys.argv[1]).resolve();OUT=Path(sys.argv[2]).resolve();OUT.mkdir(parents=True,exist_ok=False)
BOARD=OUT/'board.kicad_pcb';shutil.copyfile(SOURCE,BOARD)
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
start=time.monotonic();b=p.LoadBoard(str(BOARD));b.BuildConnectivity()
xy=lambda q:(p.ToMM(q.x),p.ToMM(q.y))
def chain(c):return [xy(c.CPoint(i)) for i in range(c.PointCount())]
def polygons(poly):
 poly=p.SHAPE_POLY_SET(poly);poly.Unfracture()
 result=[]
 for i in range(poly.OutlineCount()):
  ring=chain(poly.COutline(i))
  if len(ring)<3:raise ValueError('Invalid native outline')
  q=Polygon(ring,[chain(poly.CHole(i,j)) for j in range(poly.HoleCount(i))])
  if not q.is_valid:raise ValueError('Invalid extracted native polygon')
  result.append(q)
 return result
items={p.F_Cu:[],p.B_Cu:[]};guard_interlayers=[]
for q in list(b.GetTracks())+[q for f in b.Footprints() for q in f.Pads()]:
 if isinstance(q,p.PAD) and q.GetAttribute()==p.PAD_ATTRIB_NPTH:continue
 for layer in items:
  if not q.IsOnLayer(layer):continue
  poly=p.SHAPE_POLY_SET();q.TransformShapeToPolygon(poly,layer,0,1000,p.ERROR_INSIDE)
  geoms=polygons(poly)
  if not geoms:raise ValueError('Copper item polygon empty')
  items[layer].append({'uuid':q.m_Uuid.AsString(),'net':q.GetNetname(),'kind':'via' if isinstance(q,p.PCB_VIA) else 'pad' if isinstance(q,p.PAD) else 'track','shape':q.GetEffectiveShape(layer),'geom':unary_union(geoms)})
 if q.GetNetname()=='/GUARD_REPLICA' and (isinstance(q,p.PCB_VIA) or isinstance(q,p.PAD) and q.GetAttribute()==p.PAD_ATTRIB_PTH):guard_interlayers.append(xy(q.GetPosition()))
for z in b.Zones():
 if z.GetIsRuleArea():continue
 for layer in items:
  if not z.IsOnLayer(layer):continue
  if not z.IsFilled():raise ValueError('Unfilled native zone')
  poly=z.GetFilledPolysList(layer)
  for i,q in enumerate(polygons(poly)):
   items[layer].append({'uuid':z.m_Uuid.AsString()+':'+str(i),'net':z.GetNetname(),'kind':'zone','shape':None,'geom':q})
re=[q for q in b.GetTracks() if q.GetNetname()=='/CELL_RE'];bad_re=[q.m_Uuid.AsString() for q in re if isinstance(q,p.PCB_VIA) or q.GetLayer()!=p.F_Cu]
foreign=[r for r in items[p.F_Cu] if r['net'] not in ['/CELL_RE','/GUARD_REPLICA']]
guard=[r for r in items[p.F_Cu] if r['net']=='/GUARD_REPLICA']
if not re or not guard:raise ValueError('Missing CELL_RE or GUARD geometry')
def distance(r,point):
 if r['shape'] is not None:return p.ToMM(r['shape'].Distance(p.VECTOR2I(p.FromMM(point[0]),p.FromMM(point[1]))))
 return r['geom'].distance(Point(point))
samples=[]
for t in re:
 if isinstance(t,(p.PCB_VIA,p.PCB_ARC)):continue
 a=xy(t.GetStart());z=xy(t.GetEnd());lo=max(117.,min(a[1],z[1]));hi=min(123.6,max(a[1],z[1]))
 if lo>hi:continue
 if a[1]==z[1]:points=[a,z] if 117<=a[1]<=123.6 else []
 else:
  count=max(1,math.ceil((hi-lo)/.025));ys=[lo+(hi-lo)*j/count for j in range(count+1)];points=[(a[0]+(z[0]-a[0])*(y-a[1])/(z[1]-a[1]),y) for y in ys]
 for point in points:
  gs=min((distance(r,point),r['uuid']) for r in guard);fs=min((distance(r,point),r['net'],r['kind'],r['uuid']) for r in foreign)
  samples.append({'at':point,'guard_copper_gap_mm':gs[0]-p.ToMM(t.GetWidth())/2,'guard':gs[1],'foreign_copper_gap_mm':fs[0]-p.ToMM(t.GetWidth())/2,'foreign_net':fs[1],'foreign_kind':fs[2],'foreign':fs[3]})
if not samples:raise ValueError('No samples in actual band')
# Per-layer connected guard polygons and inter-layer plated ties.
components=[]
for layer in items:
 u=unary_union([r['geom'] for r in items[layer] if r['net']=='/GUARD_REPLICA'])
 gs=list(u.geoms) if hasattr(u,'geoms') else [u]
 components.extend((layer,g) for g in gs if not g.is_empty)
parent=list(range(len(components)))
def find(i):
 while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
 return i
for pt in guard_interlayers:
 touching=[i for i,(layer,g) in enumerate(components) if g.distance(Point(pt))<.000002]
 for i in touching[1:]:parent[find(i)]=find(touching[0])
groups={}
for i,(layer,g) in enumerate(components):groups.setdefault(find(i),[]).append({'layer':b.GetLayerName(layer),'bounds':list(g.bounds),'area_mm2':g.area})
line=LineString([(99,118),(121,118)]);crossings=[]
for layer,rows in items.items():
 for r in rows:
  if r['net']!='GND':continue
  inter=r['geom'].intersection(line)
  if inter.is_empty:continue
  crossings.append({'layer':b.GetLayerName(layer),'kind':r['kind'],'uuid':r['uuid'],'intersection_wkt':inter.wkt,'bounds':list(inter.bounds)})
fail_samples=[r for r in samples if r['foreign_copper_gap_mm']<r['guard_copper_gap_mm']-.000002 or r['guard_copper_gap_mm']>.6]
report={'scope':'diagnostic native filled-copper geometry; sample spacing <=0.025 mm; polygon chord error <=0.001 mm; no leakage/thermal performance claim','source':str(SOURCE),'board_sha256':sha(BOARD),'producer_sha256':sha(Path(__file__)),'cell_re_items':len(re),'cell_re_via_or_offlayer':bad_re,'samples':samples,'foreign_closer_or_guard_out_of_reach':fail_samples,'guard_connected_groups':list(groups.values()),'guard_interlayer_ties':guard_interlayers,'ground_crossings_y118':crossings,'seconds':time.monotonic()-start}
(OUT/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['board_sha256','cell_re_items','cell_re_via_or_offlayer','ground_crossings_y118','seconds']}));print('samples',len(samples),'coverage findings',len(fail_samples),'guard groups',len(groups))
