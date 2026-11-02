"""Actual KiCad Gerber mutations for arc side, units and unsupported records."""
import json,re,shutil,sys,time,hashlib
from pathlib import Path
p=Path(__file__).resolve().parent;root=p.parents[1];sys.path.insert(0,str(root))
from make_fab_revb_86 import check_gerbers_86
w=json.loads((root/'checks/revb-86-verified.json').read_text());reports=[]
t=time.monotonic();good=check_gerbers_86(p,w);positive=time.monotonic()-t
edge='o2-probe-Edge_Cuts.gbr';raw=(p/edge).read_text();arc_positions=[m.start() for m in re.finditer('G02\\*',raw)]
cases={
 'reverse_90_to_270':(edge,raw[:arc_positions[0]]+'G03*'+raw[arc_positions[0]+4:]),
 'reverse_semicircle_side':(edge,raw[:arc_positions[1]]+'G03*'+raw[arc_positions[1]+4:]),
 'inch_edge':(edge,raw.replace('%MOMM*%','%MOIN*%')),
 'duplicate_units':(edge,raw.replace('%MOMM*%','%MOMM*%\n%MOIN*%')),
 'missing_units':(edge,raw.replace('%MOMM*%','')),
 'unsupported_draw':(edge,raw.replace('M02*','D03*\nM02*')),
 'unsupported_transform':(edge,raw.replace('%MOMM*%','%MOMM*%\n%SFA2B2*%')),
 'early_end':(edge,raw.replace('D10*','M02*\nD10*')),
 'inch_copper':('o2-probe-F_Cu.gbr',(p/'o2-probe-F_Cu.gbr').read_text().replace('%MOMM*%','%MOIN*%')),
}
for name,(filename,mutated) in cases.items():
 dest=p/('directed-'+name);dest.mkdir(exist_ok=True)
 for f in p.glob('*.gbr'):shutil.copy2(f,dest/f.name)
 (dest/filename).write_text(mutated);t=time.monotonic()
 try:check_gerbers_86(dest,w)
 except (ValueError,TypeError,KeyError) as e:reports.append({'case':name,'rejected':True,'reason':str(e),'seconds':time.monotonic()-t})
 else:raise AssertionError('Mutation accepted: '+name)
r={'status':'PASS_DIRECTED_CONTOUR_CALIBRATION','actual_positive':good,'positive_seconds':positive,'negative_cases':reports,'sha256':{str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [root/'make_fab_revb_86.py',root/'verify_revb_86.py',Path(__file__)]}};(p/'directed-gerber-calibration.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
