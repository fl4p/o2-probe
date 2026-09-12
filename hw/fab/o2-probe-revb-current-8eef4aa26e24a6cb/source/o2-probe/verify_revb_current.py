#!/usr/bin/env python3
"""Native current-design invariants; not DRC, return-current or release acceptance.

KiCad Python: snapshot BOARD --netlist XML --baseline PCB --out SNAPSHOT
              check BOARD --netlist XML --baseline PCB --snapshot SNAPSHOT --out REPORT
Snapshot the regenerated authored board BEFORE routing. Check the saved routed
board against that immutable snapshot. A snapshot is a scope record, not approval.
"""
import argparse,hashlib,json,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
import wx
APP=wx.AppConsole()
import pcbnew as p
CODE=Path(__file__).resolve()
BASE_SHA='4520074e475656a14fe82fea1ac86e2004d09b85485ee1155a594fc5e271b303'
PROTECTED={'/CELL_RE','/CELL_WE','/GUARD_REPLICA','/HEATER_LOW','/HEATER_GATE'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def vec(q):return [int(q.x),int(q.y)]
def layers(q):return list(q.GetLayerSet().Seq())
def copper(q):
 row={'uuid':q.m_Uuid.AsString(),'net':q.GetNetname(),'start':vec(q.GetStart()),'end':vec(q.GetEnd()),'locked':q.IsLocked()}
 if isinstance(q,p.PCB_VIA):row.update(kind='via',diameter=q.GetWidth(p.F_Cu),drill=q.GetDrillValue(),layers=layers(q),via_type=int(q.GetViaType()))
 elif isinstance(q,p.PCB_ARC):row.update(kind='arc',width=q.GetWidth(),layer=q.GetLayer(),mid=vec(q.GetMid()))
 else:row.update(kind='track',width=q.GetWidth(),layer=q.GetLayer())
 return row

def edges(b):
 rows=[]
 for q in b.GetDrawings():
  if q.GetLayer()!=p.Edge_Cuts:continue
  row={'shape':int(q.GetShape()),'start':vec(q.GetStart()),'end':vec(q.GetEnd()),'width':q.GetWidth()}
  if q.GetShape()==p.SHAPE_T_ARC:row['mid']=vec(q.GetArcMid())
  rows.append(row)
 if not rows:raise ValueError('Missing native board outline')
 return sorted(rows,key=lambda x:json.dumps(x,sort_keys=True))

def fp_record(f):
 pads=[]
 for q in f.Pads():pads.append({'uuid':q.m_Uuid.AsString(),'number':q.GetNumber(),'net':q.GetNetname(),'position':vec(q.GetPosition()),'size':vec(q.GetSize()),'drill':vec(q.GetDrillSize()),'shape':int(q.GetShape()),'attribute':int(q.GetAttribute()),'layers':layers(q),'angle':q.GetOrientationDegrees()})
 return {'uuid':f.m_Uuid.AsString(),'value':f.GetValue(),'fpid':f.GetFPID().GetUniStringLibId(),'position':vec(f.GetPosition()),'angle':f.GetOrientationDegrees(),'layer':f.GetLayer(),'pads':sorted(pads,key=lambda x:x['uuid'])}

def load_state(board_path,xml_path,baseline_path):
 if sha(baseline_path)!=BASE_SHA:raise ValueError('Unreviewed baseline hash')
 root=ET.parse(xml_path).getroot();comps={}
 for c in root.findall('./components/comp'):
  ref=c.attrib['ref']
  if ref in comps:raise ValueError('Duplicate schematic reference '+ref)
  comps[ref]=(c.findtext('value'),c.findtext('footprint'))
 if len(comps)!=83:raise ValueError('Expected current83-component netlist; got '+str(len(comps)))
 mapping={}
 for n in root.findall('./nets/net'):
  for node in n.findall('node'):
   k=(node.attrib['ref'],node.attrib['pin'])
   if k in mapping:raise ValueError('Duplicate netlist pin '+str(k))
   mapping[k]=n.attrib['name']
 if not mapping:raise ValueError('Empty netlist pads')
 b=p.LoadBoard(str(board_path));base=p.LoadBoard(str(baseline_path));problems=[]
 fps={}
 for f in b.Footprints():
  ref=f.GetReference()
  if ref in fps:raise ValueError('Duplicate native reference '+ref)
  fps[ref]=fp_record(f)
 if set(fps)!=set(comps):problems.append('Native/schematic reference sets differ')
 seen=set()
 for ref,f in fps.items():
  if ref not in comps:continue
  if (f['value'],f['fpid'])!=comps[ref]:problems.append('Value/FPID mismatch '+ref)
  for q in f['pads']:
   if not q['number']:continue
   key=(ref,q['number']);seen.add(key)
   if key not in mapping or q['net']!=mapping[key]:problems.append('Pad net mismatch '+str(key))
 if set(mapping)!=seen:problems.append('Schematic/native numbered pad inventory differs')
 actual_edges=edges(b)
 if actual_edges!=edges(base):problems.append('Outline differs from reviewed89mm baseline')
 all_cu={q.m_Uuid.AsString():copper(q) for q in b.GetTracks()}
 if not all_cu:raise ValueError('No native copper')
 critical={uid:r for uid,r in all_cu.items() if r['locked']}
 if not critical:raise ValueError('No locked critical inventory')
 for net in PROTECTED:
  selected=[r for r in all_cu.values() if r['net']==net]
  if not selected:problems.append('Missing critical net copper '+net)
  if any(not r['locked'] for r in selected):problems.append('Unlocked critical net copper '+net)
 for uid,r in all_cu.items():
  if r['kind']=='via':
   if r['drill']<p.FromMM(.2) or r['diameter']<p.FromMM(.4) or r['diameter']-r['drill']<p.FromMM(.2):problems.append('Via floor '+uid)
   if r['net']=='/CELL_RE':problems.append('CELL_RE via '+uid)
  else:
   if r['width']<p.FromMM(.1):problems.append('Trace floor '+uid)
   if r['net']=='/CELL_RE' and r['layer']!=p.F_Cu:problems.append('CELL_RE off F.Cu '+uid)
 return {'footprints':fps,'edges':actual_edges,'critical_copper':critical},all_cu,problems

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['snapshot','check']);ap.add_argument('board',type=Path);ap.add_argument('--netlist',type=Path,required=True);ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--snapshot',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 reserved=[a.board,a.netlist,a.baseline,CODE,a.board.with_suffix('.kicad_pro'),a.board.with_suffix('.kicad_dru')]
 if a.snapshot:reserved.append(a.snapshot)
 if a.out.resolve() in {x.resolve() for x in reserved}:
  print('Output must not overwrite an input',file=sys.stderr);return 2
 a.out.parent.mkdir(parents=True,exist_ok=True)
 report={'status':'UNVERIFIED','scope':'native parity, outline, minimum copper dimensions and protected inventory only','limitations':['Does not establish native DRC/connectivity, guard shielding, filled-ground topology, thermal performance, return-current coupling or fabrication acceptance.']}
 def save():a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 save();start=time.monotonic()
 try:
  paths=[CODE,a.board.resolve(),a.netlist.resolve(),a.baseline.resolve(),a.board.with_suffix('.kicad_pro').resolve(),a.board.with_suffix('.kicad_dru').resolve()]
  if a.mode=='check':
   if not a.snapshot:raise ValueError('check requires --snapshot')
   paths.append(a.snapshot.resolve())
  inputs={str(x):sha(x) for x in paths};report['inputs']=inputs
  state,all_cu,problems=load_state(a.board,a.netlist,a.baseline)
  if a.mode=='snapshot':
   if a.snapshot:raise ValueError('snapshot mode does not accept --snapshot')
   report.update(schema=1,state=state,checker_sha256=sha(CODE),netlist_sha256=sha(a.netlist),project_sha256=sha(a.board.with_suffix('.kicad_pro')),rules_sha256=sha(a.board.with_suffix('.kicad_dru')))
  else:
   snap=json.loads(a.snapshot.read_text())
   if snap.get('status')!='PASS' or snap.get('schema')!=1 or snap.get('checker_sha256')!=sha(CODE):raise ValueError('Snapshot not valid for this checker')
   for key,path in [('netlist_sha256',a.netlist),('project_sha256',a.board.with_suffix('.kicad_pro')),('rules_sha256',a.board.with_suffix('.kicad_dru'))]:
    if snap.get(key)!=sha(path):problems.append('Input changed: '+key)
   old=snap['state']
   if not old.get('critical_copper') or not old.get('footprints') or not old.get('edges'):raise ValueError('Empty snapshot inventory')
   if old['footprints']!=state['footprints']:problems.append('Native footprint/pad geometry changed after snapshot')
   if old['edges']!=state['edges']:problems.append('Outline changed after snapshot')
   for uid,want in old['critical_copper'].items():
    if all_cu.get(uid)!=want:problems.append('Protected copper changed/missing '+uid)
   if set(state['critical_copper'])!=set(old['critical_copper']):problems.append('Locked inventory changed after snapshot')
  if inputs!={str(x):sha(x) for x in paths}:raise ValueError('Inputs changed during check')
  report.update(status='FAIL' if problems else 'PASS',problems=problems,footprints=len(state['footprints']),protected_items=len(state['critical_copper']),seconds=time.monotonic()-start);save();return int(bool(problems))
 except Exception as e:
  report.update(status='UNVERIFIED',exception=repr(e),seconds=time.monotonic()-start);save();return 2
if __name__=='__main__':sys.exit(main())
