#!/usr/bin/env python3
"""Create a separate 95 mm Rev B routing seed from the accepted 107 mm board."""
from pathlib import Path
import shutil,json,hashlib,argparse
import wx
APP=wx.AppConsole()
import pcbnew
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'routing/revb-interfaces'
SOURCE_SHA256='bb83a8df62be1491980e951d05a024fb468352b4433c94da6738f054fb4384ac'
DELTA=pcbnew.VECTOR2I(0,-12000000)
def pos(x,y): return pcbnew.VECTOR2I(round((100+x)*1e6),round((50+y)*1e6))
def mapped(p):
 y=p.y/1e6-50
 shift=0 if y<=49 else 12 if y>=66 else (y-49)*12/17
 return pcbnew.VECTOR2I(p.x,p.y-round(shift*1e6))
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True,help='new seed directory; must not be the accepted candidate')
 args=parser.parse_args();OUT=args.output.resolve()
 if OUT==(ROOT/'routing/revb-95').resolve():raise ValueError('Refusing to overwrite the routed review candidate with a placement seed')
 if hashlib.sha256((SRC/'o2-probe.kicad_pcb').read_bytes()).hexdigest()!=SOURCE_SHA256:raise ValueError('Reviewed 107 mm source changed; re-evaluate compaction')
 OUT.mkdir(parents=True,exist_ok=False)
 for name in ['o2-probe.kicad_pro','o2-probe.kicad_dru','o2-probe.kicad_sch','sym-lib-table','fp-lib-table']:
  shutil.copy2(SRC/name,OUT/name)
 shutil.copytree(SRC/'lib',OUT/'lib',dirs_exist_ok=True)
 b=pcbnew.LoadBoard(str(SRC/'o2-probe.kicad_pcb'))
 fps={f.GetReference():f for f in b.GetFootprints()}
 for f in fps.values():
  if f.GetPosition().y>=116000000: f.Move(DELTA)
 for ref,x,y in [('J3',5.3,51.8),('J105',11.75,51.8),('J106',17,51.8),('TP2',4,48),('TP5',1,53.5)]:
  fps[ref].SetPosition(pos(x,y))
 for ref in ['R31','C16','R38','C28','C31','R41','C9','R33']:
  f=fps[ref];f.SetPosition(pos(f.GetPosition().x/1e6-100,54.9))
 for ref,x,y in [('R8',3.5,48.95),('R9',6.2,48.95),('C15',8.8,49.15),('R10',10,51.2),('R11',14.3,51.2),('R19',17.5,48.5)]:
  f=fps[ref]
  if f.GetLayer()!=pcbnew.B_Cu: f.Flip(f.GetPosition(),False)
  f.SetOrientationDegrees(90);f.SetPosition(pos(x,y))
 f=fps['R19'];f.Flip(f.GetPosition(),False);f.SetOrientationDegrees(180);f.SetPosition(pos(13.4,57.6))
 detached=[]; removed=[]
 for t in list(b.GetTracks()):
  lo=min(t.GetStart().y,t.GetEnd().y);hi=max(t.GetStart().y,t.GetEnd().y)
  if hi>=99000000 and lo<116000000:
   removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});b.Remove(t);detached.append(t)
  elif lo>=116000000:t.Move(DELTA)
 # Repack copper around relocated contacts/passives; preserve the leakage guard.
 for t in list(b.GetTracks()):
  lo=min(t.GetStart().y,t.GetEnd().y);hi=max(t.GetStart().y,t.GetEnd().y)
  if hi>=99000000 and lo<107500000 and t.GetNetname() not in ['/CELL_RE','/GUARD_REPLICA']:
   removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});b.Remove(t);detached.append(t)
 for t in b.GetTracks(): t.SetLocked(True)
 for d in b.Drawings():
  if d.GetClass()=='PCB_SHAPE':
   if min(d.GetStart().y,d.GetEnd().y)>=116000000:d.Move(DELTA)
   elif d.GetShape()==pcbnew.SHAPE_T_SEGMENT:
    d.SetStart(mapped(d.GetStart()));d.SetEnd(mapped(d.GetEnd()))
  else:d.SetPosition(mapped(d.GetPosition()))
 for z in b.Zones():
  poly=z.Outline()
  for i in range(poly.OutlineCount()):
   for contour in [poly.Outline(i)]+[poly.Hole(i,h) for h in range(poly.HoleCount(i))]:
    for n in range(contour.PointCount()): contour.SetPoint(n,mapped(contour.CPoint(n)))
  z.UnFill()
 b.BuildConnectivity();pcbnew.ZONE_FILLER(b).Fill(b.Zones())
 pcbnew.SaveBoard(str(OUT/'o2-probe.kicad_pcb'),b)
 # KiCad must not replace the reviewed design constraints while saving.
 shutil.copy2(SRC/'o2-probe.kicad_pro',OUT/'o2-probe.kicad_pro')
 (OUT/'seed-changes.json').write_text(json.dumps({'source_sha256':hashlib.sha256((SRC/'o2-probe.kicad_pcb').read_bytes()).hexdigest(),'removed_copper':removed,'target_mm':[20,95]},indent=2)+'\n')
 print('95 mm seed; removed',len(removed),'middle-section copper items')
if __name__=='__main__':main()
