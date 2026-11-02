#!/usr/bin/env python3
"""Author the TMP302 tip addition from the pinned 89 mm board into a new directory."""
from pathlib import Path
import shutil,hashlib,wx
app=wx.AppConsole()
import pcbnew as p
import sys
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root));import gen_sch as g
if len(sys.argv)!=2:raise SystemExit('Usage: KiCad-python add_tmp302.py NEW_OUTPUT_DIRECTORY')
dest=Path(sys.argv[1]).resolve()
if dest.exists():raise SystemExit('Output must not exist; preserve review or open GUI artifacts')
source=root/'routing/revb-89/o2-probe.kicad_pcb'
if hashlib.sha256(source.read_bytes()).hexdigest()!='283224fdf2e3ed3900043cf840596c73f5cb2672007a587459b459eb014a348a':raise ValueError('Baseline changed')
g.verify()
libs=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
f=p.FootprintLoad(str(libs/'Package_TO_SOT_SMD.pretty'),'SOT-563')
f.SetFPID(p.LIB_ID('o2-probe','TMP302_DRL6_TI'))
f.SetLibDescription('TI TMP302 DRL0006A top view; SBOS488E / 4223266F: six 0.67 x 0.30 mm lands, 1.48 mm column spacing, 0.50 mm pitch; no EP or holes.')
for a in f.Pads():
 n=int(a.GetNumber());a.SetPosition(p.VECTOR2I_MM(-.74 if n<=3 else .74, {1:-.5,2:0,3:.5,4:.5,5:0,6:-.5}[n]));a.SetSize(p.VECTOR2I_MM(.67,.30));a.SetRoundRectRadiusRatio(1/6)
shutil.copytree(root/'routing/revb-89',dest,ignore=shutil.ignore_patterns('review','~*','*.kicad_prl','power-seed.json','README.md'))
p.FootprintSave(str(dest/'lib/o2-probe.pretty'),f)
(dest/'o2-probe.kicad_sch').write_text(g.emit_schematic())
(dest/'lib/o2-probe.kicad_sym').write_text(g.emit_library())
(dest/'README.md').write_text('TMP302 routing replay; run verify_tmp302.py and fresh ERC/DRC before review.\n')
b=p.LoadBoard(str(source))
for ref,x,y,angle in [('U16',114.4,136.5,0),('C35',117,136.5,90)]:
 i=g.INST[ref];lib,name=i['footprint'].split(':');f=p.FootprintLoad(str(dest/'lib/o2-probe.pretty' if lib=='o2-probe' else libs/(lib+'.pretty')),name);b.Add(f)
 f.SetReference(ref);f.SetValue(i['value']);f.SetFPID(p.LIB_ID(lib,name));f.SetPosition(p.VECTOR2I_MM(x,y));f.SetOrientationDegrees(angle);f.SetPath(p.KIID_PATH('/'+g.uid('sym',ref)))
 f.SetField('MPN',i['mpn']);f.SetField('Design Note',i['note'])
 for field in f.GetFields():field.SetVisible(False)
 f.Reference().SetLayer(p.F_Fab)
 for a in f.Pads():a.SetNet(b.FindNet('/'+g.ASSIGNED[(ref,a.GetNumber())]))
def tr(net,pts,layer=p.F_Cu,w=.15):
 for a,c in zip(pts,pts[1:]):
  t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I_MM(*a));t.SetEnd(p.VECTOR2I_MM(*c));t.SetWidth(p.FromMM(w));t.SetLayer(layer);t.SetNet(b.FindNet('/'+net));b.Add(t)
def via(net,pt):
 v=p.PCB_VIA(b);v.SetPosition(p.VECTOR2I_MM(*pt));v.SetWidth(p.FromMM(.45));v.SetDrill(p.FromMM(.2));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(b.FindNet('/'+net));b.Add(v)
# Replace four local tip segments; all other authored copper is retained.
removed=[]
for t in list(b.GetTracks()):
 if t.m_Uuid.AsString() in {'11561d3a-1c76-473c-8165-025477dea63a'} or (t.GetClass()=='PCB_TRACK' and t.GetNetname()=='/3V3D' and tuple(round(p.ToMM(v),3) for v in [t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y]) in [(112.5,136.98,113.5,136.98),(113.5,136.98,114.48,136.0)]) or (t.GetClass()=='PCB_TRACK' and t.GetNetname()=='/GND' and tuple(round(p.ToMM(v),3) for v in [t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y])==(112.5,136.0,115.9,135.8)):
  removed.append(t);b.Remove(t)
if len(removed)!=4:raise RuntimeError('Unexpected local route inventory')
tr('3V3D',[(115.3583,136),(115.14,136),(115.14,136.5),(115.14,137),(115.14,137.5),(116.48,137.5),(117,136.98)])
tr('3V3D',[(113.66,136),(113.66,135.5),(115.14,135.5),(115.14,136)])
tr('3V3D',[(112.5,136.98),(112.8,137.28),(112.8,137.7),(113.35,138.25),(115.4,138.25),(115.7,137.95),(115.7,137.5)])
via('GND',(113.1,136.5));tr('GND',[(113.66,136.5),(113.1,136.5)])
via('GND',(112.5,136.2));tr('GND',[(112.5,136.2),(112.5,136.02)]);tr('GND',[(112.5,136),(112.5,136.2)],p.B_Cu)
tr('GND',[(117,136.02),(116.75,135.77),(115.9,135.8)])
via('HEATER_GATE',(113.7,137.35));tr('HEATER_GATE',[(113.66,137),(113.7,137.06),(113.7,137.35)])
tr('HEATER_GATE',[(112.675,135.25),(113.4,135.25),(113.7,135.55),(113.7,137.35)],p.B_Cu)
tr('GND',[(114.325,135.25),(114.875,135.8),(115.9,135.8)],p.B_Cu)
if not b.BuildConnectivity():raise RuntimeError('connectivity build failed')
if not p.ZONE_FILLER(b).Fill(b.Zones()):raise RuntimeError('zone fill failed')
pro=(dest/'o2-probe.kicad_pro').read_bytes();p.SaveBoard(str(dest/'o2-probe.kicad_pcb'),b);(dest/'o2-probe.kicad_pro').write_bytes(pro)
print(dest)
