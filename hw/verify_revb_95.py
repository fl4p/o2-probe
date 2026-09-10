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

def check(path):
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
  a=xy(f.GetPosition());want=(a[0],a[1]-12)
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
 tracks=[(n,l,w,frozenset((x,y-12) for x,y in ends)) for n,l,w,ends in tracks if (n,l,w,ends) not in removed]
 vias=[(n,(x,y-12),s,d) for n,(x,y),s,d in vias]
 if len(tracks)+len(vias)!=49:raise ValueError('Expected 49 retained critical copper items')
 problems+=check_critical(path,True,True,expected_routes=(tracks,vias),guarded_band=(121.4,127.6))
 # New/changed switching and signal vias must respect the same 0.25 mm
 # leakage floor as tracks. Existing ground pours/vias are not retrospectively
 # declared qualified by this comparison; see the review report.
 prior=copper(old);re=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='/CELL_RE'];checked=0;nearest=None
 if not re:raise ValueError('Missing CELL_RE copper')
 for v in b.GetTracks():
  if v.GetClass()!='PCB_VIA' or v.GetNetname() in ['/CELL_RE','/GUARD_REPLICA']:continue
  p=xy(v.GetPosition());previous=prior.get(v.m_Uuid.AsString());current=(v.GetNetname(),v.GetLayer(),v.GetWidth(pcbnew.F_Cu),frozenset([(p[0],round(p[1]+12,6))]),v.GetDrill())
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
 elif tuple(round(v,3) for v in (min(x for x,y in allxy),min(y for x,y in allxy),max(x for x,y in allxy),max(y for x,y in allxy)))!=(100,50,120,145):problems.append('Outline is not 20 x 95 mm')
 if problems:raise ValueError('\n'.join(problems))
 return {'outline_mm':[20,95],'rigidly_translated_footprints':sorted(moved),'retained_critical_items':49,'CELL_RE_no_vias':True,'new_nearby_vias_checked':checked,'nearest_new_via':nearest,'seconds':round(time.monotonic()-started,3)}

if __name__=='__main__':
 if len(sys.argv)!=3:raise SystemExit('usage: verify_revb_95.py BOARD OUTPUT_JSON')
 result=check(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
