#!/usr/bin/env python3
"""Calibrate ring-removal guards against the real generated candidate.

Each probe uses a fresh KiCad process, as the production export does.
Run with ordinary Python after regenerating routing/revb-interfaces.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from make_fab import KIPY

ROOT = Path(__file__).resolve().parent
BOARD = ROOT/'routing/revb-interfaces/o2-probe.kicad_pcb'


class RingRetirement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'o2-probe.kicad_pcb'
        for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
            shutil.copy2(BOARD.with_suffix(suffix), self.path.with_suffix(suffix))

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([str(a) for a in args], cwd=ROOT, text=True, capture_output=True)

    def mutate(self, code):
        result = self.run_tool(KIPY, '-c',
            'import wx; app=wx.AppConsole(); import pcbnew,sys; '
            'b=pcbnew.LoadBoard(sys.argv[1]); '+code+'; pcbnew.SaveBoard(sys.argv[2],b)',
            BOARD, self.path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_generated_candidate(self):
        for args in [(sys.executable, 'verify_revb_interfaces.py', self.path),
                     (KIPY, 'verify_critical.py', self.path, '--rev-b', '--expect-locked'),
                     (KIPY, 'inspect_revb_board.py', self.path, self.path.with_suffix('.json'))]:
            result = self.run_tool(*args)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_reintroduced_ring_reference_is_rejected(self):
        for ref in ('J5', 'F3'):
            self.mutate(f"next(f for f in b.GetFootprints() if f.GetReference()=='C1').SetReference('{ref}')")
            with self.subTest(ref=ref):
                for args in [(sys.executable, 'verify_revb_interfaces.py', self.path),
                             (KIPY, 'inspect_revb_board.py', self.path, self.path.with_suffix('.json'))]:
                    result = self.run_tool(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('ValueError', result.stderr)

    def test_main_heater_and_analog_routes_remain_required(self):
        for net, extra in [('/HEATER_LOW', ' and t.GetStart().x==110000000 and t.GetStart().y==148959999'),
                           ('/CELL_RE', '')]:
            self.mutate("item=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' "
                        f"and t.GetNetname()=='{net}'{extra}); b.Remove(item)")
            result = self.run_tool(KIPY, 'verify_critical.py', self.path, '--rev-b', '--expect-locked')
            with self.subTest(net=net):
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertIn('MISSING track '+net, result.stdout)

    def test_incomplete_retirement_input_is_rejected(self):
        for source in ['pcbnew.BOARD()', 'pcbnew.LoadBoard(sys.argv[1])']:
            result = self.run_tool(KIPY, '-c',
                'import wx; app=wx.AppConsole(); import pcbnew,sys; '
                'from retire_revb_ring import retire; retire('+source+')', BOARD)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Ring retirement input is incomplete', result.stderr)


    def test_damaged_pinned_branch_is_rejected_before_edit(self):
        source = ROOT/'routing/2layer-bom39/o2-probe.kicad_pcb'
        for mutation, message in [
            ('b.Remove(item)', 'copper differs'),
            ('[b.Remove(t) for t in tracks]', 'copper differs'),
            ("item.SetNet(next(f for f in b.GetFootprints() if f.GetReference()=='Q2').FindPadByNumber('2').GetNet())", 'unexpected net'),
        ]:
            result = self.run_tool(KIPY, '-c',
                'import wx; app=wx.AppConsole(); import pcbnew,sys; '
                'from retire_revb_ring import retire,RETIRED_COPPER; '
                'b=pcbnew.LoadBoard(sys.argv[1]); fps=list(b.GetFootprints()); tracks=list(b.GetTracks()); '
                'item=next(t for t in tracks if t.m_Uuid.AsString() in RETIRED_COPPER); '
                +mutation+'; retire(b)', source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)


if __name__ == '__main__':
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RingRetirement)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f'Ring retirement calibration runtime: {time.monotonic()-started:.3f}s')
    raise SystemExit(0 if result.wasSuccessful() else 1)
