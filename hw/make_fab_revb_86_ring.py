#!/usr/bin/env python3
"""Export the exact reviewed 85-part / 86 mm Rev B ring board; never regenerate or reroute.

A sibling of make_fab_revb_86.py for routing/revb-86-ring, the accepted 86 mm
board plus the membrane-ring lands (J5), the external-sensor / UART pads (J107)
and the tip re-route that keeps HEATED_ISLAND_SPREADER one island. What differs,
and why:

- The reference is the accepted routing/revb-86 board (not the 89 mm board);
  verify_revb_86_ring.py pins every permitted change against it.
- The drill witness is taken from the candidate board: this revision adds and
  removes vias, so the reference board's drills are not this board's.
- The schematic audit report must be a PASS whose fingerprints match the live
  schematic, generator, audit script and netlist.

Export is refused unless --review-gate names a REVIEWED gate whose input hashes,
reference, courtyard dispositions, guard endpoints and review record all match.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from make_fab import KICAD, KIPY, sha256
from make_fab_revb_86 import check_gerbers_86
from make_fab_revb_current import PAIRS, check_current_drc
from revb_fab_checks import LAYERS, check_drills

HERE = Path(__file__).resolve().parent
CANDIDATE = Path('routing/revb-86-ring')
REFERENCE = Path('routing/revb-86/o2-probe.kicad_pcb')
ASSEMBLY = Path('docs/2026-09-12-current-assembly-review.md')
AUDIT = Path('schematic-audit.rpt')
COMPONENTS = 85

CODE = ['make_fab_revb_86_ring.py', 'verify_revb_86_ring.py', 'inspect_revb_86_ring_fab.py',
        'make_fab_revb_86.py', 'verify_revb_86.py', 'make_fab_revb_current.py',
        'verify_revb_current.py', 'inspect_revb_current_fab.py', 'revb_fab_checks.py',
        'make_fab.py', 'gen_sch.py', 'audit_schematic.py']


def check_schematic_audit():
    """The committed audit must be a PASS over exactly the live inputs."""
    rows = {}
    for line in (HERE / AUDIT).read_text().splitlines()[1:]:
        if ': ' in line:
            key, value = line.split(': ', 1)
            if key in rows:
                raise ValueError('Duplicate schematic-audit field ' + key)
            rows[key] = value
    if rows.get('result') != 'PASS' or rows.get('components') != str(COMPONENTS):
        raise ValueError('Schematic audit is not an %d-component PASS' % COMPONENTS)
    for name in ('o2-probe.kicad_sch', 'gen_sch.py', 'audit_schematic.py'):
        if rows.get('input ' + name) != sha256(HERE / name):
            raise ValueError('Schematic audit does not fingerprint live ' + name)
    if rows.get('export o2-probe.xml') != sha256(HERE / 'o2-probe.xml'):
        raise ValueError('Schematic audit does not fingerprint the live netlist export')


def source_inventory(reference_board):
    reference_board = reference_board.resolve()
    if reference_board != (HERE / REFERENCE).resolve():
        raise ValueError('Reference must be the accepted ' + str(REFERENCE))
    paths = [HERE / x for x in CODE] + [HERE / ASSEMBLY, HERE / AUDIT, reference_board]
    paths += [reference_board.with_suffix(ext) for ext in ('.kicad_pro', '.kicad_dru', '.kicad_sch')]
    paths += [HERE / CANDIDATE / ('o2-probe.' + ext) for ext in ('kicad_pcb', 'kicad_pro', 'kicad_dru', 'kicad_sch')]
    paths += [HERE / x for x in ('o2-probe.xml', 'o2-probe.kicad_sch', 'sym-lib-table', 'fp-lib-table')]
    paths += [HERE / CANDIDATE / 'fp-lib-table']
    paths += sorted(p for p in (HERE / 'lib').rglob('*') if p.is_file())
    external = HERE.parent / 'tmp117-probe/lib/tmp117-probe.pretty'
    if not external.is_dir() or not any(p.is_file() for p in external.iterdir()):
        raise ValueError('Required TMP117 source footprint library missing')
    paths += sorted(p for p in external.rglob('*') if p.is_file())
    if sha256(HERE / 'o2-probe.kicad_sch') != sha256(HERE / CANDIDATE / 'o2-probe.kicad_sch'):
        raise ValueError('Candidate board-associated schematic differs from current source')
    check_schematic_audit()
    result = {}
    for p in paths:
        if not p.is_file():
            raise ValueError('Missing input: ' + str(p))
        result[str(p.relative_to(HERE.parent))] = sha256(p)
    return dict(sorted(result.items()))


def check_gate(gate, inputs, reference_board):
    if gate.get('schema') != 1 or gate.get('status') != 'REVIEWED':
        raise ValueError('Final review gate is absent or not REVIEWED')
    if gate.get('reference_board') != str(reference_board.resolve().relative_to(HERE)):
        raise ValueError('Final review reference_board differs')
    if gate.get('inputs_sha256') != inputs:
        raise ValueError('Reviewed input/code/library hashes changed')
    if gate.get('assembly_disposition') != str(ASSEMBLY) or gate.get('courtyard_pairs') != [list(x) for x in sorted(PAIRS)]:
        raise ValueError('Ten current assembly dispositions are not explicit')
    dangling = gate.get('reviewed_guard_endpoints')
    if not isinstance(dangling, list):
        raise ValueError('Expected exact individually reviewed guard endpoint warnings')
    board_key = str(Path(HERE.name) / CANDIDATE / 'o2-probe.kicad_pcb')
    for row in dangling:
        if (not isinstance(row, dict) or not re.fullmatch(r'[0-9a-f-]{36}', row.get('uuid', ''))
                or row.get('net') != '/GUARD_REPLICA'
                or row.get('board_sha256') != inputs[board_key]
                or not isinstance(row.get('reason'), str) or not row['reason'].strip()):
            raise ValueError('Guard endpoint disposition needs exact UUID, board hash, net and reason')
    if len({row['uuid'] for row in dangling}) != len(dangling):
        raise ValueError('Duplicate guard endpoint disposition')
    record = gate.get('review_record')
    if not isinstance(record, str) or not record.strip() or Path(record).is_absolute():
        raise ValueError('Final review record must be a repository-relative file')
    record_path = (HERE / record).resolve()
    record_path.relative_to(HERE)
    if not record_path.is_file() or gate.get('review_record_sha256') != sha256(record_path):
        raise ValueError('Final review record missing or its content hash changed')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference-board', type=Path, default=HERE / REFERENCE)
    ap.add_argument('--review-gate', type=Path)
    ap.add_argument('--write-gate-template', type=Path)
    a = ap.parse_args()
    inputs = source_inventory(a.reference_board)
    if a.write_gate_template:
        if a.review_gate or a.write_gate_template.exists():
            raise ValueError('Template output must be new; cannot combine with export')
        a.write_gate_template.parent.mkdir(parents=True, exist_ok=True)
        a.write_gate_template.write_text(json.dumps({'schema': 1, 'status': 'UNREVIEWED',
            'reference_board': str(a.reference_board.resolve().relative_to(HERE)), 'inputs_sha256': inputs,
            'assembly_disposition': str(ASSEMBLY), 'courtyard_pairs': sorted(PAIRS),
            'review_record': '', 'review_record_sha256': '', 'reviewed_guard_endpoints': []}, indent=2) + '\n')
        print('UNREVIEWED template only: ' + str(a.write_gate_template))
        return 0
    if not a.review_gate:
        raise ValueError('--review-gate is required for export')
    gate = json.loads(a.review_gate.read_text())
    check_gate(gate, inputs, a.reference_board)
    for tool in (KICAD, KIPY):
        if not tool.is_file():
            raise ValueError('Missing dependency ' + str(tool))
    start = time.monotonic()
    fab = HERE / 'fab'
    fab.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.revb-86-ring-', dir=fab))
    out = work / 'package'
    out.mkdir()
    source = out / 'source'
    source.mkdir()
    for rel, digest in inputs.items():
        src = HERE.parent / rel
        dst = source / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if sha256(dst) != digest:
            raise ValueError('Source changed while copying ' + rel)
    working = work / 'working-source'
    shutil.copytree(source, working)
    project = working / HERE.name
    board = project / CANDIDATE / 'o2-probe.kicad_pcb'
    # Root schematic uses the same reviewed project settings as the PCB.
    shutil.copy2(board.with_suffix('.kicad_pro'), project / 'o2-probe.kicad_pro')
    xml = project / 'o2-probe.xml'
    reference = project / a.reference_board.resolve().relative_to(HERE)
    shutil.copy2(a.review_gate, out / 'review-gate.json')
    shutil.copy2(HERE / gate['review_record'], out / 'final-review-record.md')
    if sha256(out / 'final-review-record.md') != gate['review_record_sha256']:
        raise ValueError('Final review record changed during copying')
    shutil.copy2(project / ASSEMBLY, out / 'assembly-dispositions.md')
    commands = []

    def run(*args):
        args = [str(x) for x in args]
        tick = time.monotonic()
        r = subprocess.run(args, cwd=project, text=True, capture_output=True)
        commands.append({'command': args, 'returncode': r.returncode, 'seconds': round(time.monotonic() - tick, 3)})
        with (out / 'export.log').open('a') as log:
            log.write('\n$ ' + ' '.join(args) + '\n' + r.stdout + r.stderr)
        if r.returncode:
            raise ValueError('Command failed; see ' + str(out / 'export.log'))
        return r.stdout

    version = run(KICAD, '--version').strip()
    if version != '10.0.5':
        raise ValueError('Reviewed KiCad 10.0.5 required; found ' + version)

    def invariants(label):
        run(KIPY, project / 'verify_revb_86_ring.py', board, '--reference', reference, '--out', out / label)

    invariants('native-before.json')
    drc = None
    for refill, name in ((False, 'drc-saved.json'), (True, 'drc-refill.json')):
        flags = ['--refill-zones', '--save-board'] if refill else []
        run(KICAD, 'pcb', 'drc', '--all-track-errors', '--severity-all', '--schematic-parity',
            *flags, '--format', 'json', '-o', out / name, board)
        drc = check_current_drc(out / name, gate['reviewed_guard_endpoints'])
    invariants('native-after-refill.json')
    shape_witness = json.loads((out / 'native-after-refill.json').read_text())
    if shape_witness.get('status') != 'PASS':
        raise ValueError('Ring invariants did not PASS after refill')
    run(KICAD, 'sch', 'erc', '--severity-all', '--exit-code-violations', '--format', 'json',
        '-o', out / 'erc.json', project / 'o2-probe.kicad_sch')
    run(KIPY, project / 'inspect_revb_86_ring_fab.py', board, xml, out / 'board-geometry.json')
    witness = json.loads((out / 'board-geometry.json').read_text())
    if (witness.get('schema') != 1 or witness.get('status') != 'PASS' or not witness.get('inputs_sha256')
            or witness.get('components') != COMPONENTS):
        raise ValueError('Native fabrication witness is not an explicit fingerprinted %d-part PASS' % COMPONENTS)
    run(KICAD, 'pcb', 'export', 'gerbers', '-o', out, '--layers', ','.join(LAYERS),
        '--no-protel-ext', '--check-zones', board)
    run(KICAD, 'pcb', 'export', 'drill', '-o', out, '--format', 'excellon', '--excellon-units', 'mm',
        '--excellon-zeros-format', 'decimal', '--excellon-oval-format', 'route', '--excellon-separate-th',
        '--generate-map', '--map-format', 'pdf', '--generate-report',
        '--report-path', out / 'o2-probe-drill-report.txt', board)
    for side in ('front', 'back'):
        layers = 'F.Fab,F.Silkscreen,Edge.Cuts,Dwgs.User,Cmts.User' if side == 'front' else 'B.Fab,B.Silkscreen,Edge.Cuts'
        flags = ['--mirror'] if side == 'back' else []
        run(KICAD, 'pcb', 'export', 'pdf', '-o', out / f'o2-probe-assembly-{side}.pdf', '--layers', layers,
            '--mode-single', '--black-and-white', '--scale', '0', '--sketch-pads-on-fab-layers',
            '--crossout-DNP-footprints-on-fab-layers', '--check-zones', *flags, board)
    run(KICAD, 'sch', 'export', 'pdf', '-o', out / 'o2-probe-schematic.pdf', project / 'o2-probe.kicad_sch')
    run(KICAD, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'both',
        '-o', out / 'o2-probe-all-positions.csv', board)
    run(KICAD, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'both', '--exclude-dnp',
        '-o', out / 'o2-probe-fitted-positions.csv', board)
    run(KICAD, 'sch', 'export', 'bom', '--fields', 'Reference,Value,Footprint,MPN,QUANTITY,DNP,EXCLUDE_FROM_BOM,EXCLUDE_FROM_BOARD',
        '--labels', 'Reference,Value,Footprint,MPN,Quantity,DNP,ExcludedFromBOM,ExcludedFromBoard',
        '-o', out / 'o2-probe-bom.csv', project / 'o2-probe.kicad_sch')
    validation = {'drc': drc, **check_gerbers_86(out, shape_witness), **check_drills(out, witness)}
    if source_inventory(a.reference_board) != inputs or json.loads(a.review_gate.read_text()) != gate:
        raise ValueError('Reviewed live inputs or gate changed during export')
    check_gate(gate, inputs, a.reference_board)
    export_state = out / 'export-state'
    export_state.mkdir()
    for ext in ('kicad_pcb', 'kicad_pro', 'kicad_dru', 'kicad_sch'):
        shutil.copy2(board.with_suffix('.' + ext), export_state / ('o2-probe.' + ext))
    manifest = {'schema': 1, 'revision': 'B-86-ring', 'purpose': 'reviewed CAD fabrication export',
        'order_submitted': False, 'production_qualified': False,
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'kicad_cli': version,
        'inputs_sha256': inputs, 'review_gate_sha256': sha256(out / 'review-gate.json'),
        'review_record_sha256': sha256(out / 'final-review-record.md'),
        'export_board_sha256': sha256(board), 'validation': validation,
        'commands': commands, 'elapsed_seconds': round(time.monotonic() - start, 3)}
    (out / 'fab-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    files = sorted(p for p in out.rglob('*') if p.is_file())
    (out / 'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.relative_to(out)}\n' for p in files))
    files.append(out / 'SHA256SUMS')
    archive = work / 'o2-probe-revb-86-ring.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, str(p.relative_to(out)))
    with zipfile.ZipFile(archive) as z:
        if set(z.namelist()) != {str(p.relative_to(out)) for p in files}:
            raise ValueError('ZIP inventory mismatch')
        for p in files:
            if hashlib.sha256(z.read(str(p.relative_to(out)))).hexdigest() != sha256(p):
                raise ValueError('ZIP bytes mismatch ' + str(p))
    digest = sha256(archive)
    release = fab / ('o2-probe-revb-86-ring-' + digest[:16])
    if release.exists():
        raise ValueError('Immutable release path already exists')
    out.rename(release)
    archive.rename(release / archive.name)
    (release / (archive.name + '.sha256')).write_text(digest + '  ' + archive.name + '\n')
    print(release / archive.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
