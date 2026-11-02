#!/usr/bin/env python3
"""Mutation checks for the scoped TMP302 geometry guard (run with KiCad Python)."""
import tempfile,time,subprocess,sys
from pathlib import Path
import verify_tmp302 as v
p=v.p
board=v.ROOT/'routing/revb-89-tmp302/o2-probe.kicad_pcb'
start=time.monotonic();v.check(board)
with tempfile.TemporaryDirectory(prefix='tmp302-mutations-') as tmp:
 for kind in ['variant','strap','land','retained_copper','missing_part']:
  b=p.LoadBoard(str(board));fs={f.GetReference():f for f in b.GetFootprints()};u=fs['U16']
  if kind=='variant':u.SetValue('TMP302ADRLR')
  elif kind=='strap':next(a for a in u.Pads() if a.GetNumber()=='1').SetNet(b.FindNet('/GND'))
  elif kind=='land':next(iter(u.Pads())).SetSize(p.VECTOR2I_MM(.67,.35))
  elif kind=='retained_copper':
   t=next(t for t in b.GetTracks() if t.GetNetname()=='/CELL_RE');t.SetWidth(t.GetWidth()+p.FromMM(.1))
  else:b.Remove(u)
  path=Path(tmp)/(kind+'.kicad_pcb');p.SaveBoard(str(path),b)
  try:v.check(path)
  except ValueError as e:print('REJECT',kind,str(e))
  else:raise RuntimeError('Guard accepted '+kind)
print('PASS: baseline and five known-bad mutations; seconds',round(time.monotonic()-start,3))

# A refused replay must be read-only, including the canonical footprint library.
fp=v.ROOT/'lib/o2-probe.pretty/TMP302_DRL6_TI.kicad_mod'
before=fp.read_bytes()
for args in [[],[str(board.parent)]]:
 result=subprocess.run([sys.executable,str(v.ROOT/'add_tmp302.py'),*args],capture_output=True)
 if result.returncode==0 or fp.read_bytes()!=before:raise RuntimeError('Refused replay modified source')
print('PASS: refused replay leaves canonical footprint unchanged')
