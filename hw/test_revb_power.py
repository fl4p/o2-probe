#!/usr/bin/env python3
"""Known-bad calibration of the 89 mm power-placement profile."""
import subprocess,tempfile,shutil,unittest
from pathlib import Path
from make_fab import KIPY
from revb_fab_checks import check_drc,check_gerbers
ROOT=Path(__file__).resolve().parent
BOARD=ROOT/'routing/revb-89/o2-probe.kicad_pcb'
class PowerCompaction(unittest.TestCase):
 def run_check(self,board,power=4):
  with tempfile.TemporaryDirectory() as d:
   return subprocess.run([str(KIPY),str(ROOT/'verify_revb_95.py'),str(board),str(Path(d)/'result.json'),'--tip-trim-mm','2','--power-compact-mm',str(power)],capture_output=True,text=True)
 def test_real_candidate(self):
  r=self.run_check(BOARD);self.assertEqual(r.returncode,0,r.stderr)
 def test_native_profiles_cannot_be_confused(self):
  for b,p in [(BOARD,0),(ROOT/'routing/revb-93/o2-probe.kicad_pcb',4)]:
   r=self.run_check(b,p);self.assertNotEqual(r.returncode,0);self.assertIn('Outline is not',r.stderr)
 def test_changed_mirror_pad_and_buck_are_rejected(self):
  for code,message in [
   ("f=next(f for f in b.GetFootprints() if f.GetReference()=='U3'); p=f.FindPadByNumber('1'); p.SetOffset(pcbnew.VECTOR2I_MM(.2,0))",'Power compaction mirrored pad: U3.1'),
   ("f=next(f for f in b.GetFootprints() if f.GetReference()=='U3'); f.SetLayer(pcbnew.F_Cu)",'Power compaction footprint side: U3'),
   ("t=next(t for t in b.GetTracks() if t.GetNetname()=='/BUCK_SW'); b.Remove(t)",'Buck copper changed: /BUCK_SW')]:
   with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'o2-probe.kicad_pcb'
    for ext in ['.kicad_pcb','.kicad_pro','.kicad_dru']:shutil.copy2(BOARD.with_suffix(ext),p.with_suffix(ext))
    r=subprocess.run([str(KIPY),'-c','import wx; app=wx.AppConsole(); import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); '+code+'; pcbnew.SaveBoard(sys.argv[1],b)',str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
    r=self.run_check(p);self.assertNotEqual(r.returncode,0);self.assertIn(message,r.stderr)
 def test_export_profiles_and_courtyards(self):
  r=BOARD.parent/'review';self.assertEqual(check_gerbers(r,compact_95=True,tip_trim_mm=2,power_compact_mm=4)['outline_mm'],[20,89]);self.assertEqual(check_drc(r/'drc-refill.json',compact_95=True,power_compact_mm=4)['manual_assembly_courtyard_warnings'],15)
  with self.assertRaises(ValueError):check_gerbers(r,compact_95=True,tip_trim_mm=2)
  with self.assertRaises(ValueError):check_drc(r/'drc-refill.json',compact_95=True)
if __name__=='__main__':unittest.main()
