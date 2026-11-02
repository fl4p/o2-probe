#!/usr/bin/env python3
"""Create an UNROUTED 89 mm placement seed from the pinned 93 mm candidate."""
import wx
app=wx.AppConsole()
import pcbnew,shutil,json,hashlib
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
root=Path(__file__).resolve().parent;src=root/'routing/revb-93';out=args.output
if hashlib.sha256((src/'o2-probe.kicad_pcb').read_bytes()).hexdigest()!='4ed481d215c52301c134473bddcd1b50291c8b24fdcc663c881ce8727b927545':raise ValueError('93 mm source changed')
out.mkdir(parents=True,exist_ok=False)
for n in ['o2-probe.kicad_pro','o2-probe.kicad_dru','o2-probe.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(src/n,out/n)
shutil.copytree(src/'lib',out/'lib',dirs_exist_ok=True)
b=pcbnew.LoadBoard(str(src/'o2-probe.kicad_pcb'));ldo={'U2','U3','C5','C6','C7','C8','C27','R32'}
for f in b.GetFootprints():
 p=f.GetPosition()
 if f.GetReference() in ldo:
  y=p.y;f.Flip(p,True);f.SetPosition(pcbnew.VECTOR2I(p.x,167000000-y))
 elif p.y>=88000000:f.Move(pcbnew.VECTOR2I(0,-4000000))
def mapped(p):
 y=p.y;shift=0 if y<=82000000 else 4000000 if y>=88000000 else round((y-82000000)*4/6)
 return pcbnew.VECTOR2I(p.x,y-shift)
removed=[];mirrored=[];detached=[]
for t in list(b.GetTracks()):
 lo=min(t.GetStart().y,t.GetEnd().y);hi=max(t.GetStart().y,t.GetEnd().y);net=t.GetNetname();via=t.GetClass()=='PCB_VIA'
 if net in ['/BUCK_SW','/BUCK_BST']:t.SetLocked(True);continue
 if lo>=88000000:t.Move(pcbnew.VECTOR2I(0,-4000000));t.SetLocked(True);continue
 if not via and t.GetLayer()==pcbnew.F_Cu and lo>=83300000 and hi<=88000000 and net in ['/3V3D','/3V3A','/+5V_ANALOG','/+5V']:
  t.SetStart(pcbnew.VECTOR2I(t.GetStart().x,167000000-t.GetStart().y));t.SetEnd(pcbnew.VECTOR2I(t.GetEnd().x,167000000-t.GetEnd().y));t.SetLayer(pcbnew.B_Cu);t.SetLocked(True);mirrored.append(t.m_Uuid.AsString());continue
 if (hi>=83300000 and lo<88000000) or (not via and t.GetLayer()==pcbnew.B_Cu and hi>=76500000 and lo<84300000):
  removed.append({'uuid':t.m_Uuid.AsString(),'net':net});b.Remove(t);detached.append(t)
 else:t.SetLocked(True)
for d in b.Drawings():
 if d.GetClass()=='PCB_SHAPE':
  if min(d.GetStart().y,d.GetEnd().y)>=88000000:d.Move(pcbnew.VECTOR2I(0,-4000000))
  elif d.GetShape()==pcbnew.SHAPE_T_SEGMENT:d.SetStart(mapped(d.GetStart()));d.SetEnd(mapped(d.GetEnd()))
 else:d.SetPosition(mapped(d.GetPosition()))
for z in b.Zones():
 poly=z.Outline()
 for k in range(poly.OutlineCount()):
  for c in [poly.Outline(k)]+[poly.Hole(k,h) for h in range(poly.HoleCount(k))]:
   for i in range(c.PointCount()):c.SetPoint(i,mapped(c.CPoint(i)))
 z.UnFill()
b.BuildConnectivity();pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(str(out/'o2-probe.kicad_pcb'),b);shutil.copy2(src/'o2-probe.kicad_pro',out/'o2-probe.kicad_pro')
(out/'power-seed.json').write_text(json.dumps({'source_sha256':hashlib.sha256((src/'o2-probe.kicad_pcb').read_bytes()).hexdigest(),'removed':removed,'mirrored':mirrored},indent=2)+'\n');print('removed',len(removed),'mirrored',len(mirrored))
