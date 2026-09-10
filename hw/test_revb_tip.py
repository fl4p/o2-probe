#!/usr/bin/env python3
"""Calibrate explicit 93/95 mm profiles and unchanged component geometry."""
import subprocess,tempfile,shutil,unittest
from pathlib import Path
from make_fab import KIPY
from revb_fab_checks import check_gerbers
ROOT=Path(__file__).resolve().parent
BOARD=ROOT/'routing/revb-93/o2-probe.kicad_pcb'
class TipTrim(unittest.TestCase):
 def run_check(self,board,trim):
  with tempfile.TemporaryDirectory() as d:
   return subprocess.run([str(KIPY),str(ROOT/'verify_revb_95.py'),str(board),str(Path(d)/'result.json'),'--tip-trim-mm',str(trim)],capture_output=True,text=True)
 def test_real_93mm_candidate(self):
  r=self.run_check(BOARD,2);self.assertEqual(r.returncode,0,r.stderr)
 def test_native_profiles_cannot_be_confused(self):
  for board,trim in [(BOARD,0),(ROOT/'routing/revb-95/o2-probe.kicad_pcb',2)]:
   r=self.run_check(board,trim);self.assertNotEqual(r.returncode,0);self.assertIn('Outline is not',r.stderr)
 def test_upper_component_movement_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'o2-probe.kicad_pcb'
   for ext in ['.kicad_pcb','.kicad_pro','.kicad_dru']:shutil.copy2(BOARD.with_suffix(ext),p.with_suffix(ext))
   r=subprocess.run([str(KIPY),'-c',"import wx; app=wx.AppConsole(); import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); f=next(f for f in b.GetFootprints() if f.GetReference()=='U1'); f.Move(pcbnew.VECTOR2I_MM(0,1)); pcbnew.SaveBoard(sys.argv[1],b)",str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   r=self.run_check(p,2);self.assertNotEqual(r.returncode,0);self.assertIn('Tip trim changed footprint/pads: U1',r.stderr)
 def test_export_profiles_cannot_be_confused(self):
  review=BOARD.parent/'review';self.assertEqual(check_gerbers(review,compact_95=True,tip_trim_mm=2)['outline_mm'],[20,93])
  with self.assertRaises(ValueError):check_gerbers(review,compact_95=True)
  with self.assertRaises(ValueError):check_gerbers(ROOT/'routing/revb-95/review',compact_95=True,tip_trim_mm=2)
if __name__=='__main__':unittest.main()
