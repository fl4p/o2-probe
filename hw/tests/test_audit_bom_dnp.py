#!/usr/bin/env python3
"""Run the real BOM CLI on isolated XML/file fixtures; never edits the project BOM."""
import csv,hashlib,json,shutil,subprocess,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=Path(sys.argv[1]).resolve();OUT.mkdir(parents=True,exist_ok=False)
CODE=ROOT/'audit_bom.py';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r={'status':'UNVERIFIED','audit_sha256':sha(CODE),'fixture_sha256':sha(Path(__file__)),'cases':[]};start=time.monotonic()
def save():(OUT/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
save()
def xml(value='22u',dnp=True,mpn='TEST-DNP',empty=False):
 root=ET.Element('export');cs=ET.SubElement(root,'components')
 if not empty:
  c=ET.SubElement(cs,'comp',ref='C1');ET.SubElement(c,'value').text=value;ET.SubElement(c,'footprint').text='Capacitor_SMD:C_1206_3216Metric';fs=ET.SubElement(c,'fields')
  if mpn:ET.SubElement(fs,'field',name='MPN').text=mpn
  if dnp:ET.SubElement(c,'property',name='dnp')
 return ET.tostring(root)
def fixture(name,value='22u',dnp=True,mpn='TEST-DNP',ordered=False):
 d=OUT/name;d.mkdir();shutil.copyfile(CODE,d/'audit_bom.py');shutil.copyfile(ROOT/'o2-probe.kicad_sch',d/'o2-probe.kicad_sch')
 (d/'o2-probe.xml').write_bytes(xml(value,dnp,mpn));(d/'sourcing.json').write_text(json.dumps({'classes':{},'entries':{}}));(d/'purchase-orders.json').write_text(json.dumps({'captured_utc':'fixture','lines':[{'mpn':mpn,'quantity':1}] if ordered else []}));return d
def run(name,d,expected,export=False,driver=False):
 args=[sys.executable,str(d/('driver.py' if driver else 'audit_bom.py'))]
 if not export:args.append('--no-export')
 t=time.monotonic();p=subprocess.run(args,cwd=d,text=True,capture_output=True);seconds=time.monotonic()-t;(d/(name+'.log')).write_text(p.stdout+p.stderr)
 report=(d/'bom-audit.rpt').read_text() if (d/'bom-audit.rpt').exists() else ''
 actual='PASS' if 'result: PASS' in report else 'FAIL' if 'result: FAIL' in report else 'UNVERIFIED'
 row={'name':name,'expected':expected,'observed':actual,'returncode':p.returncode,'seconds':seconds};r['cases'].append(row);save()
 assert actual==expected and ((expected=='PASS')==(p.returncode==0)),row
 return report
try:
 d=fixture('numeric_dnp');run('numeric_dnp',d,'PASS');rows=list(csv.DictReader((d/'o2-probe-bom.csv').open()));assert len(rows)==1 and rows[0]['fitted']=='no' and rows[0]['qty_per_board']=='0' and rows[0]['sourcing']=='dnp'
 d=fixture('labelled_dnp','22u DNP');run('labelled_dnp',d,'PASS')
 d=fixture('label_without_flag','22u DNP',False,ordered=True);report=run('label_without_flag',d,'FAIL');assert 'DNP mismatch' in report
 d=fixture('numeric_fitted_unsourced',dnp=False,mpn='');report=run('numeric_fitted_unsourced',d,'FAIL');assert 'fitted but unbuyable' in report
 d=fixture('numeric_fitted_sourced',dnp=False,ordered=True);run('numeric_fitted_sourced',d,'PASS');row=next(csv.DictReader((d/'o2-probe-bom.csv').open()));assert row['qty_per_board']=='1' and row['fitted']=='yes'
 d=fixture('fitted_unordered',dnp=False);report=run('fitted_unordered',d,'FAIL');assert 'no purchase order' in report
 for name,kind in [('missing_xml','missing'),('malformed_xml','malformed'),('empty_xml','empty'),('duplicate_ref','duplicate')]:
  d=fixture(name);run(name+'_prior_pass',d,'PASS')
  if kind=='missing':(d/'o2-probe.xml').unlink()
  elif kind=='malformed':(d/'o2-probe.xml').write_text('<export')
  elif kind=='empty':(d/'o2-probe.xml').write_bytes(xml(empty=True))
  else:
   root=ET.fromstring(xml());cs=root.find('components');cs.append(ET.fromstring(ET.tostring(cs[0])));(d/'o2-probe.xml').write_bytes(ET.tostring(root))
  run(name,d,'UNVERIFIED');assert not (d/'o2-probe-bom.csv').exists()
 for name,file in [('missing_sourcing','sourcing.json'),('malformed_sourcing','sourcing.json'),('missing_orders','purchase-orders.json'),('malformed_orders','purchase-orders.json')]:
  d=fixture(name)
  if name.startswith('missing'):(d/file).unlink()
  else:(d/file).write_text('{')
  run(name,d,'FAIL')
 d=fixture('failed_native_export');run('failed_native_export_prior_pass',d,'PASS');(d/'o2-probe.kicad_sch').write_text('(kicad_sch')
 run('failed_native_export',d,'UNVERIFIED',export=True);assert not (d/'o2-probe.xml').exists() and not (d/'o2-probe-bom.csv').exists()
 d=fixture('midrun_source_change');(d/'driver.py').write_text('import audit_bom as a\noriginal=a.diff_purchase_orders\ndef changed(*args):\n original(*args)\n with a.SOURCING.open("a") as f:f.write(" ")\na.diff_purchase_orders=changed\nraise SystemExit(a.main())\n');report=run('midrun_source_change',d,'FAIL',driver=True);assert 'input changed during evaluation' in report
 # Compare the former implementation on the same genuine DNP-property fixture.
 old=subprocess.run(['git','show','HEAD:ee/hw/o2-probe/audit_bom.py'],cwd=ROOT,text=True,capture_output=True,check=True).stdout
 d=fixture('legacy_numeric_dnp');(d/'audit_bom.py').write_text(old);report=run('legacy_numeric_dnp',d,'FAIL');assert 'DNP mismatch' in report
 assert sha(CODE)==r['audit_sha256'];r.update(status='PASS',seconds=time.monotonic()-start);save()
except Exception as e:r.update(status='FAIL',error=repr(e),seconds=time.monotonic()-start);save();raise
print(json.dumps({'status':r['status'],'cases':len(r['cases']),'seconds':r['seconds']}))
