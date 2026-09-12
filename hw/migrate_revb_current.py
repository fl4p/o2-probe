#!/usr/bin/env python3
"""Deterministic current-schematic migration from the committed 89 mm TMP302 board.

Run using KiCad Python. Routine copper in the changed electronics region is
withdrawn as a region before new authored circuits and whole-board routing.
The cell input, driven guard, heater circuit and thermal barrier are retained.
"""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
import wx
APP=wx.AppConsole()
import pcbnew as p
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'routing/revb-89-tmp302/o2-probe.kicad_pcb'
OUT=ROOT/'routing/revb-current'
BASE_SHA='4520074e475656a14fe82fea1ac86e2004d09b85485ee1155a594fc5e271b303'
BRIDGE_IDS={'6fd7263e-12eb-4bfc-9997-6f95db867c28','da8e353d-d4fa-40ad-afe4-3022fbd0eef3','e5c418ee-ce00-48fa-99bb-1452609f54ce'}
PROTECTED={'/CELL_RE','/CELL_WE','/GUARD_REPLICA','/HEATER_LOW','/HEATER_GATE'}
def mm(v):return p.FromMM(v)
def pt(x,y):return p.VECTOR2I(mm(x),mm(y))
def xy(v):return [p.ToMM(v.x),p.ToMM(v.y)]
def migrate():
 assert hashlib.sha256(BASE.read_bytes()).hexdigest()==BASE_SHA
 OUT.mkdir(parents=True,exist_ok=True)
 pro=json.loads(BASE.with_suffix('.kicad_pro').read_text())
 ds=pro['board']['design_settings']; ds['drc_exclusions']=[]
 ds['rules'].update(min_clearance=.1,min_track_width=.1,min_through_hole_diameter=.2,min_via_diameter=.4,min_via_annular_width=.1,min_copper_edge_clearance=.3,min_hole_clearance=.2,min_hole_to_hole=.3)
 ds['track_widths']=[0,.1,.15,.2,.25,.4,.5,.8]
 ds['via_dimensions']=[{'diameter':.4,'drill':.2}]
 for c in pro['net_settings']['classes']:
  if c['name']=='Default':c.update(clearance=.1,track_width=.15,via_diameter=.4,via_drill=.2)
 ds['rule_severities'].update(missing_footprint='error',extra_footprint='error',net_conflict='error',footprint_symbol_mismatch='error',footprint_symbol_field_mismatch='error')
 (OUT/'o2-probe.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
 (OUT/'o2-probe.kicad_dru').write_text((ROOT/'revb_current_process.kicad_dru').read_text())
 shutil.copy2(ROOT/'o2-probe.kicad_sch',OUT/'o2-probe.kicad_sch')
 (OUT/'fp-lib-table').write_text((ROOT/'fp-lib-table').read_text().replace('${KIPRJMOD}/lib','${KIPRJMOD}/../../lib').replace('${KIPRJMOD}/../tmp117-probe','${KIPRJMOD}/../../../tmp117-probe'))
 (OUT/'krt-floor.txt').write_text('via_diameter = 0.4\nvia_drill = 0.2\nclearance = 0.1\ntrack_width = 0.1\nhole_to_hole = 0.3\nboard_edge = 0.3\n')
 b=p.LoadBoard(str(BASE));b.SetFileName(str(OUT/'o2-probe.kicad_pcb'));b.GetDesignSettings().SetBoardThickness(mm(1.6))
 root=ET.parse(ROOT/'o2-probe.xml').getroot()
 comps={c.attrib['ref']:c for c in root.findall('./components/comp')}
 mapping={};nets={}
 for n in root.findall('./nets/net'):
  name=n.attrib['name'];net=b.FindNet(name)
  if not net:net=p.NETINFO_ITEM(b,name);b.Add(net)
  nets[name]=net
  for node in n.findall('node'):mapping[(node.attrib['ref'],node.attrib['pin'])]=name
 removed=[];retained=[]
 for t in list(b.GetTracks()):
  name=t.GetNetname();ys=[p.ToMM(t.GetStart().y),p.ToMM(t.GetEnd().y)]
  if name in PROTECTED or min(ys)>=118 or t.m_Uuid.AsString() in BRIDGE_IDS:
   if name=='/GND':t.SetNet(nets['GND'])
   if isinstance(t,p.PCB_VIA):t.SetWidth(max(t.GetWidth(p.F_Cu),mm(.4)));t.SetDrill(max(t.GetDrillValue(),mm(.2)))
   else:t.SetWidth(max(t.GetWidth(),mm(.1)))
   t.SetLocked(name in PROTECTED or min(ys)>=118 or t.m_Uuid.AsString() in BRIDGE_IDS)
   retained.append(t.m_Uuid.AsString())
  else:removed.append(t.m_Uuid.AsString());b.RemoveNative(t)
 for z in b.Zones():
  if z.GetNetname()=='/GND':z.SetNet(nets['GND'])
  if not z.GetIsRuleArea():z.SetLocalClearance(mm(.1))
 old={f.GetReference():f for f in b.Footprints()}
 for ref,f in old.items():
  if ref not in comps:b.RemoveNative(f)
 poses={'D3':(112,69.5,0,False),'D8':(115.1,106.2,0,True),'C36':(115.5,108.6,0,False)}
 replaced=[]
 for ref,c in comps.items():
  f=old.get(ref);libid=c.findtext('footprint');nick,item=libid.split(':',1)
  replace=f is None or f.GetFPID().GetUniStringLibId()!=libid
  if replace:
   if f:pose=(*xy(f.GetPosition()),f.GetOrientationDegrees(),f.GetLayer()==p.B_Cu);path=f.GetPath();b.RemoveNative(f)
   else:pose=poses[ref];path=p.KIID_PATH('/'+c.findtext('tstamps'))
   lib=ROOT/'lib/o2-probe.pretty' if nick=='o2-probe' else ROOT.parent/'tmp117-probe/lib/tmp117-probe.pretty' if nick=='tmp117-probe' else Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')/(nick+'.pretty')
   f=p.FootprintLoad(str(lib),item)
   if f is None:raise ValueError(libid)
   b.Add(f);f.SetFPID(p.LIB_ID(nick,item));f.SetReference(ref);f.SetPosition(pt(*pose[:2]));f.SetPath(path)
   if pose[3]:f.Flip(f.GetPosition(),False)
   f.SetOrientationDegrees(pose[2]);replaced.append(ref)
  f.SetValue(c.findtext('value'));f.SetDNP(c.find("property[@name='dnp']") is not None)
  for prop in c.findall('property'):
   name=prop.attrib['name']
   if name not in {'dnp','Sheetname','Sheetfile'}:f.SetField(name,prop.attrib.get('value',''))
  for field in f.GetFields():field.SetVisible(False)
  f.Reference().SetLayer(p.B_Fab if f.GetLayer()==p.B_Cu else p.F_Fab)
  for a in f.Pads():
   name=mapping.get((ref,a.GetNumber()))
   if a.GetNumber() and not name:raise ValueError('Unmapped pad '+ref+'.'+a.GetNumber())
   if name:a.SetNet(nets[name])
   else:a.SetNetCode(0)
 import author_revb_power as power
 import author_revb_support as support
 power.place(b);power.author(b);support.apply(b)
 import author_revb_mcu as mcu
 mcu.apply(b)
 import author_revb_tip as tip
 tip.apply(b)
 for t in b.GetTracks():
  if t.m_Uuid.AsString() in BRIDGE_IDS:
   for getter,setter in ((t.GetStart,t.SetStart),(t.GetEnd,t.SetEnd)):
    v=getter()
    if v.x==mm(.4+100):v.x=mm(100.375);setter(v)
 b.BuildConnectivity();p.ZONE_FILLER(b).Fill(b.Zones())
 p.SaveBoard(str(OUT/'o2-probe.kicad_pcb'),b)
 b=p.LoadBoard(str(OUT/'o2-probe.kicad_pcb'));b.BuildConnectivity();p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(OUT/'o2-probe.kicad_pcb'),b)
 report={'baseline_sha256':BASE_SHA,'schematic_sha256':hashlib.sha256((ROOT/'o2-probe.kicad_sch').read_bytes()).hexdigest(),'footprints':len(comps),'removed_refs':sorted(set(old)-set(comps)),'replaced_or_new':replaced,'removed_copper_items':len(removed),'retained_copper_items':len(retained),'retained_copper_uuids':retained}
 # Nominal 1.6 mm copper/core build; soldermask thickness is an additional
 # illustrative model, not measured manufacturing stackup evidence.
 boardpath=OUT/'o2-probe.kicad_pcb'
 text=boardpath.read_text()
 old_core='(layer "dielectric 1"\n\t\t\t\t(type "core")\n\t\t\t\t(thickness 0.93)'
 if text.count(old_core)!=1:raise ValueError('Unexpected source dielectric model')
 boardpath.write_text(text.replace(old_core,old_core.replace('0.93','1.53')))
 (OUT/'migration.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='retained_copper_uuids'}))
if __name__=='__main__':migrate()
