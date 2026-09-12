#!/usr/bin/env python3
"""Derive the 86 mm Rev B from the accepted 89 mm board; no copper relocation."""
from pathlib import Path
import hashlib,json,shutil,sys
import wx
APP=wx.AppConsole()
import pcbnew as p
ROOT=Path(__file__).resolve().parent
SOURCE_SHA='3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665'
TOP_IDS={'ea06dc41-11e6-594d-baab-da6250d792e7','42935040-3c92-56f0-85c9-ada5c91405bd','8a7edcbb-f470-5578-9193-2c238760b099'}
SIDE_IDS={'ae686e5e-e0e3-5956-a5ee-2629db626bb1','44fcae7e-d934-5b11-a976-d306df3e3d78'}
LABEL='50cb1b95-414f-55da-86b0-24bfc55b5569'
def main():
 source=ROOT/'routing/revb-current/o2-probe.kicad_pcb';out=ROOT/'routing/revb-86'
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('Accepted 89 mm source changed')
 if out.exists():raise ValueError('New output directory required; do not overwrite an open/reviewed PCB')
 out.mkdir();b=p.LoadBoard(str(source));delta=p.VECTOR2I(0,p.FromMM(3));seen=set()
 for q in b.GetDrawings():
  uid=q.m_Uuid.AsString()
  if uid in TOP_IDS:q.Move(delta);seen.add(uid)
  elif uid in SIDE_IDS:
   for end in ['Start','End']:
    pt=getattr(q,'Get'+end)()
    if pt.y==p.FromMM(52):getattr(q,'Set'+end)(pt+delta);seen.add(uid)
  elif uid==LABEL:
   if q.GetText()!='CABLE':raise ValueError('Cable label changed')
   q.SetPosition(p.VECTOR2I(p.FromMM(110),p.FromMM(57)));q.SetTextAngle(p.EDA_ANGLE(90,p.DEGREES_T));seen.add(uid)
 if seen!=TOP_IDS|SIDE_IDS|{LABEL}:raise ValueError('Expected outline/label objects missing')
 for ext in ['.kicad_pro','.kicad_sch','.kicad_dru']:shutil.copy2(source.with_suffix(ext),out/('o2-probe'+ext))
 shutil.copy2(source.parent/'fp-lib-table',out/'fp-lib-table');p.SaveBoard(str(out/'o2-probe.kicad_pcb'),b)
 (out/'trim-receipt.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'source_sha256':SOURCE_SHA,'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'trim_mm':3,'outline_mm':[20,86],'modified_drawing_uuids':sorted(seen),'scope':'Top outline and CABLE annotation only; native refill and independent comparison pending'},indent=2)+'\n')
 print(out/'o2-probe.kicad_pcb')
if __name__=='__main__':main()
