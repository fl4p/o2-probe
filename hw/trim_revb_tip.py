#!/usr/bin/env python3
"""Create the 93 mm tip-trim candidate from the pinned 95 mm routed board."""
from pathlib import Path
import hashlib,shutil,json
import wx
_APP=wx.AppConsole()
import pcbnew
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'routing/revb-95';OUT=ROOT/'routing/revb-93'
SOURCE_SHA='2139ab97aa7dd59272d35398bdb80f01eda497574057ac22c1ef1d07b6794fc5'

def main(output):
 OUT=output.resolve()
 if hashlib.sha256((SRC/'o2-probe.kicad_pcb').read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('95 mm source changed')
 OUT.mkdir(exist_ok=False)
 for name in ['o2-probe.kicad_pcb','o2-probe.kicad_pro','o2-probe.kicad_dru','o2-probe.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(SRC/name,OUT/name)
 shutil.copytree(SRC/'lib',OUT/'lib')
 b=pcbnew.LoadBoard(str(OUT/'o2-probe.kicad_pcb'));edges=0
 for d in b.Drawings():
  if d.GetClass()=='PCB_SHAPE' and d.GetLayer()==pcbnew.Edge_Cuts:
   for side in ['Start','End']:
    p=getattr(d,'Get'+side)()
    if p.y==145000000:getattr(d,'Set'+side)(pcbnew.VECTOR2I(p.x,143000000));edges+=1
 if edges!=4:raise ValueError('Unexpected original tip contour')
 detached=[];removed=[]
 for t in list(b.GetTracks()):
  if t.GetBoundingBox().GetBottom()>142750000:
   if t.GetNetname()=='/I2C_SDA' and t.GetClass()=='PCB_TRACK':
    for side in ['Start','End']:
     p=getattr(t,'Get'+side)()
     if p.y>142700000:getattr(t,'Set'+side)(pcbnew.VECTOR2I(p.x,142700000))
    continue
   if t.GetNetname()!='/GND':raise ValueError('Unexpected net in trimmed tip')
   removed.append(t.m_Uuid.AsString());b.Remove(t);detached.append(t)
 for z in b.Zones():
  poly=z.Outline()
  for k in range(poly.OutlineCount()):
   for c in [poly.Outline(k)]+[poly.Hole(k,h) for h in range(poly.HoleCount(k))]:
    for i in range(c.PointCount()):
     p=c.CPoint(i)
     if p.y>143000000:c.SetPoint(i,pcbnew.VECTOR2I(p.x,143000000))
  z.UnFill()
 for d in b.Drawings():
  if d.GetClass()=='PCB_TEXT' and d.GetText()=='TMP_CELL':d.SetPosition(pcbnew.VECTOR2I_MM(104.5,142.2))
 v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('/GND'));v.SetPosition(pcbnew.VECTOR2I_MM(111.35,138.825));v.SetWidth(250000);v.SetDrill(150000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
 b.BuildConnectivity();pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(str(OUT/'o2-probe.kicad_pcb'),b);shutil.copy2(SRC/'o2-probe.kicad_pro',OUT/'o2-probe.kicad_pro')
 (OUT/'tip-trim.json').write_text(json.dumps({'source_sha256':SOURCE_SHA,'removed_ground_copper':removed,'trim_mm':2,'outline_mm':[20,93]},indent=2)+'\n');print('Trimmed tip; removed',len(removed),'ground copper items')
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True,help='new output directory; existing directories are never overwritten');args=parser.parse_args();main(args.output)
