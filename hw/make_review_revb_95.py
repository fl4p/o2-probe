#!/usr/bin/env python3
"""Validate and export the committed 95 mm routed candidate for engineering review.

This exports an authored PCB snapshot. compact_revb_95.py creates a placement
seed, not a deterministic reconstruction of subsequent interactive routing.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys,tempfile,shutil,time
from make_fab import KICAD,KIPY,sha256
from make_fab_revb import RULE_HASHES
from revb_fab_checks import LAYERS,check_drc,check_gerbers,check_drills
ROOT=Path(__file__).resolve().parent
CANDIDATE=ROOT/'routing/revb-95'

def main():
 start=time.monotonic();board=CANDIDATE/'o2-probe.kicad_pcb'
 for name,h in RULE_HASHES.items():
  if sha256(CANDIDATE/name)!=h:raise ValueError('Reviewed rules changed: '+name)
 inputs=[p for p in CANDIDATE.rglob('*') if p.is_file() and 'review' not in p.relative_to(CANDIDATE).parts and not p.name.endswith('.kicad_prl') and not p.name.startswith('~')]
 inputs += [ROOT/n for n in ['make_review_revb_95.py','make_fab.py','make_fab_revb.py','revb_fab_checks.py','verify_critical.py','verify_revb_95.py','verify_revb_interfaces.py','inspect_revb_board.py','critical_routes.py','retire_revb_ring.py','thermal_design.py','compact_revb_95.py','gen_sch.py','firmware/tools/pcb_netlist.py','routing/2layer-bom39/critical_routes.py','test_revb_95.py','test_revb_95_provenance.py','docs/REVB-95-REVIEW.md','plans/REVB-95MM.md']]
 inputs += [ROOT/'routing/revb-interfaces/o2-probe.kicad_pcb']
 import gen_sch
 external=sorted({Path(v["source_path"]) for v in gen_sch.SYMS.values() if "source_path" in v})
 def fingerprints():
  return {**{str(p.relative_to(ROOT)):sha256(p) for p in inputs},**{str(p):sha256(p) for p in external}}
 before=fingerprints()
 work=Path(tempfile.mkdtemp(prefix='o2-95-review-'));out=work/'review';out.mkdir();commands=[]
 def run(*args):
  args=list(map(str,args));t=time.monotonic();r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
  commands.append({'command':args,'returncode':r.returncode,'seconds':round(time.monotonic()-t,3)})
  with (out/'build.log').open('a') as f:f.write('$ '+' '.join(args)+'\n'+r.stdout+r.stderr+'\n')
  if r.returncode:raise ValueError(f'Command failed; see {out}/build.log')
  return r.stdout
 version=run(KICAD,'--version').strip()
 if version!='10.0.5':raise ValueError('Review KiCad version change: '+version)
 (out/'interface-check.txt').write_text(run(sys.executable,ROOT/'verify_revb_interfaces.py',board))
 run(KIPY,ROOT/'verify_revb_95.py',board,out/'geometry-check.json')
 run(KIPY,ROOT/'inspect_revb_board.py',board,out/'board-geometry.json')
 for refill,name in [(False,'drc-saved-fill.json'),(True,'drc-refill.json')]:
  flags=['--refill-zones'] if refill else []
  run(KICAD,'pcb','drc','--severity-all','--schematic-parity',*flags,'--format','json','-o',out/name,board)
  check_drc(out/name,compact_95=True)
 run(KICAD,'sch','erc','--severity-all','--exit-code-violations','--format','json','-o',out/'erc.json',CANDIDATE/'o2-probe.kicad_sch')
 run(KICAD,'pcb','export','gerbers','-o',out,'--layers',','.join(LAYERS),'--no-protel-ext','--check-zones',board)
 run(KICAD,'pcb','export','drill','-o',out,'--format','excellon','--excellon-units','mm','--excellon-zeros-format','decimal','--excellon-oval-format','route','--excellon-separate-th','--generate-map','--map-format','pdf','--generate-report','--report-path',out/'o2-probe-drill-report.txt',board)
 for side in ['front','back']:
  layers='F.Fab,F.Silkscreen,Edge.Cuts,Dwgs.User,Cmts.User' if side=='front' else 'B.Fab,B.Silkscreen,Edge.Cuts'
  flags=['--mirror'] if side=='back' else []
  run(KICAD,'pcb','export','pdf','-o',out/f'o2-probe-assembly-{side}.pdf','--layers',layers,'--mode-single','--black-and-white','--scale','0','--sketch-pads-on-fab-layers','--crossout-DNP-footprints-on-fab-layers','--check-zones',*flags,board)
 checks={**check_gerbers(out,compact_95=True),**check_drills(out,json.loads((out/'board-geometry.json').read_text())),'drc':check_drc(out/'drc-refill.json',compact_95=True)}
 if fingerprints()!=before:raise ValueError('Validation inputs changed during build; review output not promoted')
 manifest={'purpose':'engineering review','revision':'B, 95 mm candidate','order_ready':False,'qualification_scope':'CAD/export validation only; existing procurement, heater/input-protection and physical qualification gates remain open. J5/F3 remain optional Rev C work.','generated_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'kicad_cli':version,'board_sha256':sha256(board),'inputs_sha256':before,'validation':checks,'commands':commands,'elapsed_seconds':round(time.monotonic()-start,3)}
 (out/'validation-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 (out/'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file()))
 destination=CANDIDATE/'review'
 if destination.exists():shutil.rmtree(destination)
 shutil.copytree(out,destination);shutil.rmtree(work)
 print('PASS: 20 x 95 mm; 0 DRC errors, 0 opens, 0 parity findings; 16 documented courtyard warnings. Engineering review, not order-ready.')
 print(destination)

if __name__=='__main__':main()
