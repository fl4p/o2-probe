#!/usr/bin/env python3
"""Calibrate saved-reference overlap detection using persistent KiCad fixtures.

Usage: python3 test_audit_layout.py OUTPUT_DIRECTORY
Outputs are intentionally retained for review; no source file is modified.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    names = ('gen_sch.py','audit_layout.py','audit_layout_references.py','o2-probe.kicad_sch')
    source = {n:(ROOT/n).read_bytes() for n in names}
    hashes = {n:hashlib.sha256(v).hexdigest() for n,v in source.items()}
    text = source['o2-probe.kicad_sch'].decode()
    anchor = '(property "Reference" "D8" (at 241.3 168.91 0)'
    assert text.count(anchor)==1, 'expected current reviewed D8 field'
    cases = {
        'good': (text,0),
        'original_overlap': (text.replace(anchor,'(property "Reference" "D8" (at 241.3 161.29 0)'),1),
        'deeper_overlap': (text.replace(anchor,'(property "Reference" "D8" (at 246.38 154.94 0)'),1),
        'legal_move': (text.replace(anchor,'(property "Reference" "D8" (at 241.3 170.18 0)'),0),
        'malformed': ('(kicad_sch (broken',2),
        'missing': (None,2),
    }
    results = []
    for name,(sch,want) in cases.items():
        case = out/name
        case.mkdir(exist_ok=True)
        for filename,data in source.items():
            if filename!='o2-probe.kicad_sch':
                (case/filename).write_bytes(data)
        path = case/'o2-probe.kicad_sch'
        path.unlink(missing_ok=True)
        if sch is not None:
            path.write_text(sch)
        start = time.perf_counter()
        run = subprocess.run([sys.executable,str(case/'audit_layout.py')],cwd=case,
                             text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        elapsed = time.perf_counter()-start
        (case/'audit.log').write_text(run.stdout)
        assert run.returncode==want, (name,run.returncode,run.stdout)
        if name in ('original_overlap','deeper_overlap'):
            assert 'D8.ref (saved anchor)  <->  U10 body' in run.stdout,run.stdout
        row = {'case':name,'returncode':run.returncode,'seconds':elapsed,'expected':want}
        if name in ('good','original_overlap'):
            # Real native rendering of the mutated saved field, not a mock
            # glyph image or an XML constructed from the same detector model.
            pdf = case/'schematic.pdf'
            native = subprocess.run([CLI,'sch','export','pdf','--output',str(pdf),str(path)],
                                    text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (case/'native-export.log').write_text(native.stdout)
            assert native.returncode==0 and pdf.read_bytes().startswith(b'%PDF')
            row['native_pdf_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest()
        results.append(row)
        print(json.dumps(row))
    assert all((ROOT/n).read_bytes()==v for n,v in source.items()),'source changed during calibration'
    (out/'calibration.json').write_text(json.dumps({'inputs':hashes,'cases':results,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'all_expected':True},indent=2)+'\n')


if __name__=='__main__':
    main()
