#!/usr/bin/env python3
"""Validate the 95 mm candidate against the pinned 107 mm geometry and circuit."""
import hashlib,json,sys,time
from pathlib import Path
import wx
_APP=wx.AppConsole()
import pcbnew
from verify_critical import check as check_critical, expected, _segment_distance
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'routing/revb-interfaces/o2-probe.kicad_pcb'
SOURCE_SHA='bb83a8df62be1491980e951d05a024fb468352b4433c94da6738f054fb4384ac'

def xy(p):return (round(p.x/1e6,6),round(p.y/1e6,6))
def copper(b):
 out={}
 for t in b.GetTracks():
  via=t.GetClass()=='PCB_VIA'
  out[t.m_Uuid.AsString()]=(t.GetNetname(),t.GetLayer(),t.GetWidth(pcbnew.F_Cu) if via else t.GetWidth(),frozenset([xy(t.GetStart()),xy(t.GetEnd())]),t.GetDrill() if via else None)
 return out

def check(path, *, tip_trim_mm=0, power_compact_mm=0):
 if power_compact_mm not in (0,4) or (power_compact_mm and tip_trim_mm!=2):raise ValueError("Unsupported power compaction profile")
 if tip_trim_mm not in (0,2):raise ValueError("Unsupported tip trim")
 started=time.monotonic()
 if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('107 mm source changed')
 b=pcbnew.LoadBoard(str(path));old=pcbnew.LoadBoard(str(SOURCE));problems=[]
 if b.GetCopperLayerCount()!=2:problems.append('Expected two copper layers')
 if b.GetDesignSettings().GetBoardThickness()!=old.GetDesignSettings().GetBoardThickness():problems.append('Board thickness changed')
 fps={f.GetReference():f for f in b.GetFootprints()};orig={f.GetReference():f for f in old.GetFootprints()}
 if set(fps)!=set(orig) or len(fps)!=99:problems.append('Footprint inventory differs')
 moved=[]
 for ref,f in orig.items():
  if f.GetPosition().y<116000000:continue
  g=fps.get(ref)
  if g is None:continue
  a=xy(f.GetPosition());want=(a[0],a[1]-12-power_compact_mm)
  if any(abs(a-c)>1e-6 for a,c in zip(xy(g.GetPosition()),want)) or f.GetLayer()!=g.GetLayer() or f.GetOrientationDegrees()!=g.GetOrientationDegrees():problems.append('Lower footprint moved nonrigidly: '+ref)
  def pad_geometry(footprint):
   center=footprint.GetPosition()
   return sorted((p.GetNumber(),p.GetNetname(),p.GetShape(),xy(p.GetSize()),
                  xy(p.GetDrillSize()),p.GetDrillShape(),xy(p.GetPosition()-center),
                  p.GetOrientationDegrees(),p.GetAttribute(),tuple(p.GetLayerSet().Seq()),
                  xy(p.GetOffset()),xy(p.GetDelta()),p.GetRoundRectRadiusRatio(),p.GetChamferRectRatio())
                 for p in footprint.Pads())
  if pad_geometry(f)!=pad_geometry(g):problems.append('Lower pad/drill geometry changed: '+ref)
  moved.append(ref)
 # All original authored routes except TP5's two relocated feed segments.
 tracks,vias=expected(True)
 omit={frozenset(((101.0,115.8),(101.5,116.3))),frozenset(((101.0,115.5),(101.0,115.8)))}
 removed=[t for t in tracks if t[0]=='/GUARD_REPLICA' and t[3] in omit]
 if len(removed)!=2:raise ValueError('Unexpected original TP5 route inventory')
 tracks=[(n,l,w,frozenset((x,y-12-power_compact_mm) for x,y in ends)) for n,l,w,ends in tracks if (n,l,w,ends) not in removed]
 vias=[(n,(x,y-12-power_compact_mm),s,d) for n,(x,y),s,d in vias]
 if len(tracks)+len(vias)!=49:raise ValueError('Expected 49 retained critical copper items')
 problems+=check_critical(path,True,True,expected_routes=(tracks,vias),guarded_band=(121.4-power_compact_mm,127.6-power_compact_mm))
 # New/changed switching and signal vias must respect the same 0.25 mm
 # leakage floor as tracks. Existing ground pours/vias are not retrospectively
 # declared qualified by this comparison; see the review report.
 prior=copper(old);re=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='/CELL_RE'];checked=0;nearest=None
 if not re:raise ValueError('Missing CELL_RE copper')
 for v in b.GetTracks():
  if v.GetClass()!='PCB_VIA' or v.GetNetname() in ['/CELL_RE','/GUARD_REPLICA']:continue
  p=xy(v.GetPosition());previous=prior.get(v.m_Uuid.AsString());current=(v.GetNetname(),v.GetLayer(),v.GetWidth(pcbnew.F_Cu),frozenset([(p[0],round(p[1]+12+power_compact_mm,6))]),v.GetDrill())
  # Only vias near the translated analog node need this leakage assessment.
  gap=min(_segment_distance(p,p,xy(t.GetStart()),xy(t.GetEnd()))-v.GetWidth(pcbnew.F_Cu)/2e6-t.GetWidth()/2e6 for t in re)
  if gap>=1:continue
  if current==previous:continue
  checked+=1
  if nearest is None or gap<nearest['gap_mm']:nearest={'net':v.GetNetname(),'xy':p,'gap_mm':gap}
  if gap<.25-1e-6:problems.append(f'New/changed {v.GetNetname()} via {p}: CELL_RE gap {gap:.6f} mm < 0.25 mm')
 # Exact outline/slot primitives and zone-free thermal gap are checked again
 # in the Gerbers; native board bounds must agree before export.
 p=pcbnew.SHAPE_POLY_SET();b.GetBoardPolygonOutlines(p,False)
 allxy=[xy(p.Outline(k).CPoint(i)) for k in range(p.OutlineCount()) for i in range(p.Outline(k).PointCount())]
 if not allxy:problems.append('Missing outline')
 elif tuple(round(v,3) for v in (min(x for x,y in allxy),min(y for x,y in allxy),max(x for x,y in allxy),max(y for x,y in allxy)))!=(100,50,120,145-tip_trim_mm-power_compact_mm):problems.append(f'Outline is not 20 x {95-tip_trim_mm-power_compact_mm} mm')
 if tip_trim_mm and not power_compact_mm:
  tip_source=ROOT/'routing/revb-95/o2-probe.kicad_pcb'
  if hashlib.sha256(tip_source.read_bytes()).hexdigest()!='2139ab97aa7dd59272d35398bdb80f01eda497574057ac22c1ef1d07b6794fc5':raise ValueError('95 mm tip source changed')
  source=pcbnew.LoadBoard(str(tip_source));source_fps={f.GetReference():f for f in source.GetFootprints()}
  for ref,f in source_fps.items():
   g=fps.get(ref)
   if g is None or xy(f.GetPosition())!=xy(g.GetPosition()) or f.GetOrientationDegrees()!=g.GetOrientationDegrees() or f.GetLayer()!=g.GetLayer() or pad_geometry(f)!=pad_geometry(g):problems.append('Tip trim changed footprint/pads: '+ref)
 if power_compact_mm:
  compact_source=ROOT/'routing/revb-93/o2-probe.kicad_pcb'
  if hashlib.sha256(compact_source.read_bytes()).hexdigest()!='4ed481d215c52301c134473bddcd1b50291c8b24fdcc663c881ce8727b927545':raise ValueError('93 mm power source changed')
  source=pcbnew.LoadBoard(str(compact_source));ldo={'U2','U3','C5','C6','C7','C8','C27','R32'}
  for f in source.GetFootprints():
   ref=f.GetReference();g=fps.get(ref);x,y=xy(f.GetPosition());mirror=ref in ldo
   expected_xy=(x,167-y) if mirror else (x,y-4 if y>=88 else y)
   if g is None or any(abs(a-c)>1e-6 for a,c in zip(xy(g.GetPosition()),expected_xy)):problems.append('Power compaction footprint pose: '+ref);continue
   if not mirror:
    if f.GetLayer()!=g.GetLayer() or f.GetOrientationDegrees()!=g.GetOrientationDegrees() or pad_geometry(f)!=pad_geometry(g):problems.append('Power compaction changed retained footprint: '+ref)
   else:
    if f.GetLayer()!=pcbnew.F_Cu or g.GetLayer()!=pcbnew.B_Cu:problems.append('Power compaction footprint side: '+ref)
    pp={p.m_Uuid.AsString():p for p in g.Pads()}
    if len(pp)!=len(list(f.Pads())):problems.append('Power compaction pad count: '+ref)
    for p in f.Pads():
     q=pp.get(p.m_Uuid.AsString());px,py=xy(p.GetPosition())
     def shape_fields(p):return (p.GetNumber(),p.GetNetname(),p.GetShape(),xy(p.GetSize()),xy(p.GetDrillSize()),p.GetDrillShape(),p.GetAttribute(),xy(p.GetOffset()),xy(p.GetDelta()),p.GetRoundRectRadiusRatio(),p.GetChamferRectRatio())
     layers=sorted(('B.'+source.GetLayerName(l)[2:]) if source.GetLayerName(l).startswith('F.') else ('F.'+source.GetLayerName(l)[2:]) if source.GetLayerName(l).startswith('B.') else source.GetLayerName(l) for l in p.GetLayerSet().Seq())
     if q is None or shape_fields(p)!=shape_fields(q) or any(abs(a-c)>1e-6 for a,c in zip(xy(q.GetPosition()),(px,167-py))) or layers!=sorted(b.GetLayerName(l) for l in q.GetLayerSet().Seq()) or abs((p.GetOrientationDegrees()+q.GetOrientationDegrees())%180)>1e-6:problems.append('Power compaction mirrored pad: '+ref+'.'+p.GetNumber())
  old_copper=copper(source);new_copper=copper(b)
  for net in ['/BUCK_SW','/BUCK_BST']:
   before={k:v for k,v in old_copper.items() if v[0]==net};after={k:v for k,v in new_copper.items() if v[0]==net}
   if not before or before!=after:problems.append('Buck copper changed: '+net)
 if problems:raise ValueError('\n'.join(problems))
 return {'outline_mm':[20,95-tip_trim_mm-power_compact_mm],'rigidly_translated_footprints':sorted(moved),'retained_critical_items':49,'CELL_RE_no_vias':True,'new_nearby_vias_checked':checked,'nearest_new_via':nearest,'seconds':round(time.monotonic()-started,3)}

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('board',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--tip-trim-mm',type=int,choices=[0,2],default=0);parser.add_argument('--power-compact-mm',type=int,choices=[0,4],default=0);args=parser.parse_args()
 result=check(args.board,tip_trim_mm=args.tip_trim_mm,power_compact_mm=args.power_compact_mm);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
