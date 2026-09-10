#!/usr/bin/env python3
"""Exercise real KiCad exports, then mutate an input and require no promotion."""
import tempfile,shutil,time
from pathlib import Path
import make_review_revb_95 as build

def main():
 started=time.monotonic();original=build.CANDIDATE
 scratch=Path(tempfile.mkdtemp(prefix='test95-provenance-',dir=build.ROOT/'routing'))
 real_run=build.subprocess.run;changed=[]
 try:
  shutil.copytree(original,scratch,dirs_exist_ok=True,ignore=shutil.ignore_patterns('review','*.kicad_prl'))
  (scratch/'review').mkdir();sentinel=scratch/'review/previous-result';sentinel.write_text('keep previous result')
  build.CANDIDATE=scratch
  def run(args,**kwargs):
   r=real_run(args,**kwargs)
   if r.returncode==0 and any(str(a).endswith('o2-probe-assembly-back.pdf') for a in args):
    p=scratch/'o2-probe.kicad_sch';p.write_bytes(p.read_bytes()+b'\n');changed.append(True)
   return r
  build.subprocess.run=run
  try:build.main()
  except ValueError as exc:
   assert 'Validation inputs changed during build' in str(exc),str(exc)
  else:raise AssertionError('Changed input was promoted as verified')
  assert changed and sentinel.read_text()=='keep previous result'
  assert sorted(p.name for p in sentinel.parent.iterdir())==['previous-result']
 finally:
  build.CANDIDATE=original;build.subprocess.run=real_run;shutil.rmtree(scratch)
 print(f'PASS: real export followed by input mutation is rejected; previous review preserved ({time.monotonic()-started:.3f}s)')

if __name__=='__main__':main()
