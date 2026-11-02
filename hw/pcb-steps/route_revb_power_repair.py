#!/usr/bin/env python3
"""Bounded three-net completion: both layers prefer the probe long (Y) axis.
Run in KRT's .venv; existing critical copper is immutable. The project/rules
are restored byte-for-byte even when routing fails. Native DRC is separate.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import hashlib,json,os,runpy,sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
KRT=Path('/Users/fab/dev/tools/KiCadRoutingTools')
EXPECTED='749cfa8333765288a807f825064b68015fd10ea9'
if subprocess.check_output(['git','-C',str(KRT),'rev-parse','HEAD'],text=True).strip()!=EXPECTED:raise SystemExit('Router source revision differs')
board=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'routing/revb-current/o2-probe.kicad_pcb'
files=[board.with_suffix('.kicad_pro'),board.with_suffix('.kicad_dru')]
original={p:p.read_bytes() for p in files}
os.environ['KICAD_INRUN_FLOOR_SYNC']='0'
sys.path.insert(0,str(KRT/'py_router'))
from routing_config import GridRouteConfig
GridRouteConfig.get_layer_direction_preferences=lambda self:[1]*len(self.layers)
args=[str(KRT/'py_router/route.py'),str(board),'--overwrite','--layers','F.Cu','B.Cu','--track-width','0.15','--via-size','0.4','--via-drill','0.2','--grid-step','0.05','--via-cost','150','--turn-cost','1000','--direction-preference-cost','250','--max-ripup','0','--max-iterations','200000','--fab-overrides',str(board.parent/'krt-floor.txt'),'--no-fix-drc-settings','--keep-input-copper','--no-stub-layer-swap','--same-net-pad-clearance','0.2','--no-smoothing','--nets','/+12V_SW','/3V3D','/HEATER_PWM','--net-clearances',str(ROOT/'routing/revb-current/net-clearances.json'),'--power-nets','/+12V_SW','/+12V_FUSED','/+12V_RAW','/3V3D','/3V3A','--power-nets-widths','0.5','0.5','0.5','0.3','0.25','--json-out',str(board.parent/'power-repair-summary.json')]
manifest={'router_commit':EXPECTED,'entrypoint_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'layer_directions':['Y','Y'],'router_files':{str(p.relative_to(KRT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(KRT.rglob('*.so'))},'argv':args,'rules':{p.name:hashlib.sha256(b).hexdigest() for p,b in original.items()},'start':time.time()}
(board.parent/'power-repair-run.json').write_text(json.dumps(manifest,indent=2)+'\n')
sys.argv=args
try:runpy.run_path(str(KRT/'py_router/route.py'),run_name='__main__')
finally:
 for p,b in original.items():p.write_bytes(b)
 manifest.update(end=time.time(),output_sha256=hashlib.sha256(board.read_bytes()).hexdigest())
 (board.parent/'power-repair-run.json').write_text(json.dumps(manifest,indent=2)+'\n')
