"""Mutate actual native copies; verify only exact top-trim geometry is accepted."""
import sys,time,json,shutil,hashlib
from pathlib import Path
p=Path(__file__).resolve().parent;root=p.parents[1];sys.path.insert(0,str(root))
import wx
app=wx.AppConsole()
import pcbnew as k
import verify_revb_86 as v
source=root/'routing/revb-86/o2-probe.kicad_pcb';reference=root/'routing/revb-current/o2-probe.kicad_pcb';out=p/'lifecycle.json';results=[]
def run(label,board,want):
 t=time.monotonic();rc=v.run(board,reference,out);r=json.loads(out.read_text());assert r['status']==want,(label,r);assert bool(rc)==(want!='PASS');
 if want!='PASS':assert 'edge_primitives' not in r
 results.append({'case':label,'status':r['status'],'seconds':time.monotonic()-t,'exception':r.get('exception')})
run('real_frozen_86_positive',source,'PASS')
for label in ['outline','copper','pad','hole','DNP','outline_far']:
 b=k.LoadBoard(str(source));case=p/label;case.mkdir(exist_ok=True);board=case/'o2-probe.kicad_pcb'
 if label.startswith('outline'):
  q=next(x for x in b.GetDrawings() if x.m_Uuid.AsString()=='42935040-3c92-56f0-85c9-ada5c91405bd');q.Move(k.VECTOR2I(0,k.FromMM(10 if label=='outline_far' else .01)))
 elif label=='copper':
  q=next(x for x in b.GetTracks() if isinstance(x,k.PCB_TRACK) and not isinstance(x,k.PCB_VIA));q.SetWidth(q.GetWidth()+k.FromMM(.01))
 elif label=='pad':
  q=next(iter(next(iter(b.GetFootprints())).Pads()));q.SetPosition(q.GetPosition()+k.VECTOR2I(k.FromMM(.01),0))
 elif label=='hole':
  q=next(x for x in b.GetTracks() if isinstance(x,k.PCB_VIA));q.SetDrill(q.GetDrillValue()+k.FromMM(.01))
 elif label=='DNP':
  q=next(iter(b.GetFootprints()));q.SetDNP(not q.IsDNP())
 k.SaveBoard(str(board),b)
 for ext in ['.kicad_pro','.kicad_dru','.kicad_sch']:shutil.copy2(source.with_suffix(ext),board.with_suffix(ext))
 run('native_'+label+'_mutation',board,'UNVERIFIED')
run('valid_before_missing_input',source,'PASS')
run('same_output_missing_board',p/'missing.kicad_pcb','UNVERIFIED')
result={'status':'PASS_CALIBRATION','tests':results,'producer_sha256':v.sha(root/'verify_revb_86.py'),'calibration_sha256':v.sha(Path(__file__))};(p/'calibration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
