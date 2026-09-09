#!/usr/bin/env python3
"""Calibrate Rev B export guards against a freshly generated review package."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

from revb_fab_checks import (check_drc, check_drills, check_gerbers,
                             clipped_area, normalized_board)

PACKAGE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class ExportCalibration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for path in PACKAGE.iterdir():
            if path.is_file() and path.suffix in ('.gbr', '.drl', '.json'):
                shutil.copy2(path, self.root/path.name)
        self.report = self.root/'drc-refill.json'
        self.witness = json.loads((self.root/'board-geometry.json').read_text())

    def tearDown(self):
        self.temp.cleanup()

    def reject_report(self, report):
        self.report.write_text(json.dumps(report))
        with self.assertRaises((ValueError, KeyError, TypeError)):
            check_drc(self.report)

    def test_real_package(self):
        check_drc(self.report)
        check_gerbers(self.root)
        check_drills(self.root, self.witness)

    def test_missing_report_data(self):
        report = json.loads(self.report.read_text())
        for key in ('violations','unconnected_items','schematic_parity','ignored_checks','included_severities'):
            changed = copy.deepcopy(report); changed.pop(key)
            with self.subTest(key=key): self.reject_report(changed)
        self.reject_report({})

    def test_unverified_and_errors_never_pass(self):
        report = json.loads(self.report.read_text())
        for key in ('ignored_checks', 'unconnected_items', 'schematic_parity'):
            changed = copy.deepcopy(report); changed[key] = [{'type': 'calibration'}]
            with self.subTest(key=key): self.reject_report(changed)
        for severity in ('error', 'exclusion', 'ignore', None):
            changed = copy.deepcopy(report); changed['violations'][0]['severity'] = severity
            with self.subTest(severity=severity): self.reject_report(changed)

    def test_changed_courtyard_set(self):
        report = json.loads(self.report.read_text())
        for operation in ('remove', 'duplicate', 'replace'):
            changed = copy.deepcopy(report)
            if operation == 'remove': changed['violations'].pop()
            elif operation == 'duplicate': changed['violations'].append(changed['violations'][0])
            else: changed['violations'][0]['items'][0]['description'] = 'Footprint R999'
            with self.subTest(operation=operation): self.reject_report(changed)

    def test_near_and_far_bad_drc(self):
        report = json.loads(self.report.read_text())
        for gap in (0.149, 0.0, -100):
            changed = copy.deepcopy(report)
            changed['violations'].append({'type':'clearance','severity':'error',
                                         'description':f'gap {gap}', 'items':[]})
            with self.subTest(gap=gap): self.reject_report(changed)

    def test_missing_paste_and_extra_inner_layer(self):
        paste = self.root/'o2-probe-F_Paste.gbr'
        data = paste.read_bytes(); paste.unlink()
        with self.assertRaises(ValueError): check_gerbers(self.root)
        paste.write_bytes(data)
        (self.root/'o2-probe-In1_Cu.gbr').write_bytes(data)
        with self.assertRaises(ValueError): check_gerbers(self.root)

    def test_wrong_layer_identity_and_truncated_output(self):
        path = self.root/'o2-probe-B_Cu.gbr'; original = path.read_text()
        for text in (original.replace('Copper,L2,Bot','Copper,L4,Bot'),
                     original.replace('M02*',''), ''):
            path.write_text(text)
            with self.assertRaises(ValueError): check_gerbers(self.root)

    def test_moved_drill_near_and_far(self):
        for delta in (0.01, 1.0, 100.0):
            changed = copy.deepcopy(self.witness)
            record = next(r for r in changed['drills']['PTH'] if r[0]=='hit')
            record[2][0] += delta
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                check_drills(self.root, changed)
        with self.assertRaises(ValueError): check_drills(self.root, {})

    def test_malformed_drill_source_is_unverified(self):
        for broken in (['slot', 3, []], ['slot', 3, [[110], [110]]],
                       ['slot', float('nan'), [[110,-143.8],[110,-146.8]]],
                       ['slot', 3, [[110,float('inf')],[110,-146.8]]],
                       ['slot', 0, [[110,-143.8],[110,-146.8]]],
                       ['slot', -3, [[110,-143.8],[110,-146.8]]],
                       ['slot', 3, [[110,-143.8],[110,-143.8]]]):
            changed = copy.deepcopy(self.witness)
            index = next(i for i,r in enumerate(changed['drills']['NPTH']) if r[0]=='slot')
            changed['drills']['NPTH'][index] = broken
            with self.subTest(record=broken), self.assertRaises(ValueError):
                check_drills(self.root, changed)

    def test_changed_drill_diameter(self):
        changed = copy.deepcopy(self.witness)
        changed['drills']['PTH'][0][1] += .01
        with self.assertRaises(ValueError): check_drills(self.root, changed)

    def test_unsupported_region_command(self):
        path = self.root/'o2-probe-F_Cu.gbr'
        path.write_text(path.read_text().replace('G36*', 'G36*\nG02*', 1))
        with self.assertRaises(ValueError): check_gerbers(self.root)

    def test_missing_and_malformed_drills(self):
        path = self.root/'o2-probe-NPTH.drl'; original = path.read_text()
        for text in ('', original.replace('M30',''), original.replace('M15','')):
            path.write_text(text)
            with self.assertRaises(ValueError): check_drills(self.root, self.witness)
        path.unlink()
        with self.assertRaises(ValueError): check_drills(self.root, self.witness)

    def test_thermal_gap_far_tail_and_hole(self):
        bounds=(100,-135,120,-133)
        for width in (0.001, .15, 2, 200):
            points=[(110-width/2,-136),(110+width/2,-136),
                    (110+width/2,-132),(110-width/2,-132)]
            self.assertGreater(clipped_area(points,bounds), 0)
        self.assertEqual(clipped_area([(100,-133),(120,-133),(120,-132)], bounds),0)

    def test_board_comparator_preserves_geometry_and_vertex_order(self):
        path=self.root/'board.kicad_pcb'
        original='(kicad_pcb (uuid "one") (segment (start 1 2) (end 3 4)) (pts (xy 0 0) (xy 1 0) (xy 1 1)))'
        path.write_text(original); baseline=normalized_board(path)
        path.write_text(original.replace('"one"','"two"'))
        self.assertEqual(baseline,normalized_board(path))
        path.write_text(original.replace('(xy 0 0) (xy 1 0)', '(xy 0 0) (xy 0.5 0) (xy 1 0)'))
        self.assertEqual(baseline, normalized_board(path))
        for text in (original.replace('(start 1 2)','(start 1 2.001)'),
                     original.replace('(xy 0 0) (xy 1 0)','(xy 1 0) (xy 0 0)')):
            path.write_text(text); self.assertNotEqual(baseline,normalized_board(path))
        path.write_text(original[:-1])
        with self.assertRaises(ValueError): normalized_board(path)

if __name__ == '__main__':
    if PACKAGE is None or not (PACKAGE/'fab-manifest.json').is_file():
        raise SystemExit('usage: test_revb_fab_checks.py VALIDATED_PACKAGE_DIRECTORY')
    start = time.monotonic()
    result = unittest.main(exit=False)
    print(f'Calibration runtime: {time.monotonic()-start:.3f}s')
    raise SystemExit(not result.result.wasSuccessful())
