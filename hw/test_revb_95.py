#!/usr/bin/env python3
"""Known-bad calibration for the compact-board acceptance gates."""
import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from make_fab import KIPY
from revb_fab_checks import check_drc,check_gerbers
ROOT=Path(__file__).resolve().parent
BOARD=ROOT/'routing/revb-95/o2-probe.kicad_pcb'
REVIEW=BOARD.parent/'review'
class CompactBoard(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'o2-probe.kicad_pcb'
  for suffix in ['.kicad_pcb','.kicad_pro','.kicad_dru']:shutil.copy2(BOARD.with_suffix(suffix),self.path.with_suffix(suffix))
 def tearDown(self):self.tmp.cleanup()
 def verify(self):
  return subprocess.run([str(KIPY),str(ROOT/'verify_revb_95.py'),str(self.path),str(self.path.with_suffix('.json'))],cwd=ROOT,capture_output=True,text=True)
 def mutate(self,code):
  p=subprocess.run([str(KIPY),'-c','import wx; app=wx.AppConsole(); import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); '+code+'; pcbnew.SaveBoard(sys.argv[2],b)',str(BOARD),str(self.path)],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_real_candidate(self):
  r=self.verify();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_new_via_near_miss_and_far_tail(self):
  for y in [113.325,112.89]:
   self.mutate("v=next(t for t in b.GetTracks() if t.m_Uuid.AsString()=='902a8721-b212-4f7e-98a5-147a3a66f9d9'); v.SetPosition(pcbnew.VECTOR2I_MM(111.6,"+str(y)+"))")
   r=self.verify();self.assertNotEqual(r.returncode,0);self.assertTrue('CELL_RE gap' in r.stderr or 'CELL_RE carries via(s)' in r.stderr,r.stderr)
 def test_missing_critical_tracks_and_guard_are_rejected(self):
  for net in ['/CELL_RE','/GUARD_REPLICA','/HEATER_LOW']:
   self.mutate("removed=[t for t in b.GetTracks() if t.GetNetname()=='"+net+"']; [b.Remove(t) for t in removed]")
   r=self.verify();self.assertNotEqual(r.returncode,0,r.stdout)
 def test_displaced_cell_rejected(self):
  self.mutate("f=next(f for f in b.GetFootprints() if f.GetReference()=='U11'); f.Move(pcbnew.VECTOR2I_MM(0,1))")
  r=self.verify();self.assertNotEqual(r.returncode,0);self.assertIn('Lower footprint moved nonrigidly: U11',r.stderr)
 def test_changed_cell_aperture_rejected(self):
  self.mutate("f=next(f for f in b.GetFootprints() if f.GetReference()=='U11'); p=next(p for p in f.Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH); p.SetDrillSize(pcbnew.VECTOR2I_MM(3,7))")
  r=self.verify();self.assertNotEqual(r.returncode,0);self.assertIn('Lower pad/drill geometry changed: U11',r.stderr)
 def test_missing_and_malformed_board_rejected(self):
  for text in ['', '(kicad_pcb (version 20241229) (generator pcbnew))']:
   self.path.write_text(text);self.assertNotEqual(self.verify().returncode,0)
 def test_full_drc_and_unverified_report(self):
  report=json.loads((REVIEW/'drc-refill.json').read_text());path=Path(self.tmp.name)/'drc.json'
  for key in ['violations','ignored_checks','unconnected_items','schematic_parity','included_severities']:
   j=dict(report);j.pop(key);path.write_text(json.dumps(j))
   with self.assertRaises(ValueError):check_drc(path,compact_95=True)
  for key in ['unconnected_items','ignored_checks','schematic_parity']:
   j=dict(report);j[key]=[{'unexpected':True}];path.write_text(json.dumps(j))
   with self.assertRaises(ValueError):check_drc(path,compact_95=True)
  self.assertEqual(check_drc(REVIEW/'drc-refill.json',compact_95=True)['errors'],0)
 def test_export_profile_cannot_be_confused_with_107mm(self):
  self.assertEqual(check_gerbers(REVIEW,compact_95=True)['outline_mm'],[20,95])
  with self.assertRaises(ValueError):check_gerbers(REVIEW)
  out=Path(self.tmp.name)/'gerbers';out.mkdir()
  for p in REVIEW.glob('*.gbr'):shutil.copy2(p,out/p.name)
  edge=out/'o2-probe-Edge_Cuts.gbr';text=edge.read_text();self.assertIn('Y-145000000',text)
  for value in ['Y-145100000','Y-155000000']:
   edge.write_text(text.replace('Y-145000000',value))
   with self.assertRaises(ValueError):check_gerbers(out,compact_95=True)
if __name__=='__main__':unittest.main()
