#!/usr/bin/env python3
"""Rebuild and validate the two-layer Rev B engineering-review package."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from make_fab import KICAD, KIPY, sha256
from revb_fab_checks import (LAYERS, check_drc, check_drills, check_gerbers,
                             normalized_board)

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE/'routing/revb-interfaces'
RULE_HASHES = {
    'o2-probe.kicad_pro': 'e700a1602dc434a0e7d2aedc0dd21e118d8251adc94c2df266343612ae374b2c',
    'o2-probe.kicad_dru': 'b1fe200efe5fc9d531438535ce0c1230b8972c03a14bfb571651b9448d46717a',
}
SCRIPTS = ['gen_sch.py', 'adopt_revb_interfaces.py', 'finish_revb_layout.py',
           'verify_revb_interfaces.py', 'inspect_revb_board.py', 'audit_schematic.py',
           'audit_bom.py', 'make_fab.py', 'make_fab_revb.py', 'revb_fab_checks.py',
           'retire_revb_ring.py', 'verify_critical.py', 'critical_routes.py', 'thermal_design.py']
DOCS = ['REVB-FAB.md', 'REVB-ASSEMBLY.md', 'REVB-SCOPE.md']


def main():
    started = time.monotonic()
    for path in (KICAD, KIPY):
        if not path.is_file():
            raise ValueError(f'Missing KiCad dependency: {path}')
    for name, expected in RULE_HASHES.items():
        if sha256(CANDIDATE/name) != expected:
            raise ValueError(f'{name}: reviewed Rev B constraints changed; review required')
    fab = HERE/'fab'
    fab.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.rev-b-build-', dir=fab))
    src = work/'source'; src.mkdir()
    out = work/'package'; out.mkdir()
    inputs = {}
    def copy(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inputs[str(source.relative_to(HERE))] = sha256(target)
    for name in SCRIPTS + ['sourcing.json', 'purchase-orders.json', 'sym-lib-table']:
        copy(HERE/name, src/name)
    for name in ['o2-probe.kicad_pro', 'o2-probe.kicad_dru', 'fp-lib-table']:
        copy(CANDIDATE/name, src/name)
    for path in sorted((HERE/'lib').rglob('*')):
        if path.is_file():
            copy(path, src/path.relative_to(HERE))
    # This reviewed external-library snapshot is part of the self-contained
    # candidate; no sibling checkout or user-global library mapping is needed.
    for path in sorted((CANDIDATE/'lib/tmp117-probe.pretty').rglob('*')):
        if path.is_file():
            copy(path, src/path.relative_to(CANDIDATE))
    for name in ['o2-probe.kicad_pcb', 'o2-probe.kicad_pro', 'o2-probe.kicad_dru',
                 'verify_critical.py', 'critical_routes.py', 'thermal_design.py']:
        rel = Path('routing/2layer-bom39')/name
        copy(HERE/rel, src/rel)
    rel = Path('firmware/tools/pcb_netlist.py')
    copy(HERE/rel, src/rel)
    for name in DOCS:
        copy(HERE/'docs'/name, out/name)
    # Preserve the deferred design in both repository and review ZIP. Resolve
    # package navigation against the ZIP layout rather than the source tree.
    for name in ['README.md', 'REVC-HEATED-RING.md']:
        copy(HERE/'plans'/name, out/'plans'/name)
    scope = out/'REVB-SCOPE.md'
    scope.write_text(scope.read_text().replace('](../plans/', '](plans/'))
    plan = out/'plans/REVC-HEATED-RING.md'
    text = plan.read_text().replace(
        '[BOM39 route](../routing/2layer-bom39/PROVENANCE.md)',
        'BOM39 route (`routing/2layer-bom39/PROVENANCE.md` in the source repository)')
    text = text.replace('](../lib/', '](../source/lib/').replace(
        '[retire_revb_ring.py](../retire_revb_ring.py)',
        '`retire_revb_ring.py` in the source repository')
    plan.write_text(text)
    index = out/'plans/README.md'
    index.write_text(index.read_text().replace(
        '[Archived earlier PCB plans](../docs/archive/2026-09-09-pcb-plans/README.md)',
        'Earlier PCB plans: `docs/archive/2026-09-09-pcb-plans/README.md` in the source repository'))
    accepted = work/'accepted.kicad_pcb'
    copy(CANDIDATE/'o2-probe.kicad_pcb', accepted)
    commands = []
    def run(*args, allowed=(0,)):
        args = [str(v) for v in args]
        start = time.monotonic()
        result = subprocess.run(args, cwd=src, text=True, capture_output=True)
        commands.append({'command': args, 'returncode': result.returncode,
                         'seconds': round(time.monotonic()-start, 3)})
        with (out/'build.log').open('a') as log:
            log.write('\n$ '+ ' '.join(args)+'\n'+result.stdout+result.stderr)
        if result.returncode not in allowed:
            raise ValueError(f'Build command failed ({result.returncode}); see {out}/build.log')
        return result
    version = run(KICAD, '--version').stdout.strip()
    if version != '10.0.5':
        raise ValueError(f'Validated with KiCad 10.0.5, found {version}; review tool change')
    run(sys.executable, 'gen_sch.py')
    board = src/'o2-probe.kicad_pcb'
    run(KIPY, 'adopt_revb_interfaces.py', board)
    run(KIPY, 'finish_revb_layout.py', board)
    normalized = normalized_board(board)
    if normalized != normalized_board(accepted):
        raise ValueError(f'Rebuilt board differs from accepted candidate; inspect {board}')
    result = run(KIPY, 'verify_critical.py', board, '--rev-b', '--expect-locked')
    (out/'critical-check.txt').write_text(result.stdout)
    result = run(sys.executable, 'verify_revb_interfaces.py', board)
    (out/'interface-check.txt').write_text(result.stdout)
    run(KICAD, 'sch', 'erc', '--severity-all', '--exit-code-violations',
        '--format', 'json', '-o', out/'erc.json', src/'o2-probe.kicad_sch')
    run(sys.executable, 'audit_schematic.py')
    copy_output = lambda name: shutil.copy2(src/name, out/name)
    copy_output('schematic-audit.rpt')
    for refill, name in [(False, 'drc-saved-fill.json'), (True, 'drc-refill.json')]:
        flags = ['--refill-zones'] if refill else []
        run(KICAD, 'pcb', 'drc', '--severity-all', '--schematic-parity',
            *flags, '--format', 'json', '-o', out/name, board)
        check_drc(out/name)
    drc = check_drc(out/'drc-refill.json')
    run(KIPY, 'inspect_revb_board.py', board, out/'board-geometry.json')
    witness = json.loads((out/'board-geometry.json').read_text())
    # A procurement failure is evidence to package, not a clean assembly BOM.
    result = run(sys.executable, 'audit_bom.py', '--no-export', allowed=(0, 1))
    report = (src/'bom-audit.rpt').read_text()
    errors = [line for line in report.splitlines() if line.startswith('ERROR:')]
    expected_result = 'FAIL' if result.returncode else 'PASS'
    if f'result: {expected_result}\n' not in report or bool(errors) != bool(result.returncode):
        raise ValueError('BOM audit exit status/report is inconsistent')
    for name in ['bom-audit.rpt', 'o2-probe-bom.csv']:
        copy_output(name)
    run(KICAD, 'pcb', 'export', 'gerbers', '-o', out, '--layers', ','.join(LAYERS),
        '--no-protel-ext', '--check-zones', board)
    run(KICAD, 'pcb', 'export', 'drill', '-o', out, '--format', 'excellon',
        '--excellon-units', 'mm', '--excellon-zeros-format', 'decimal',
        '--excellon-oval-format', 'route', '--excellon-separate-th',
        '--generate-map', '--map-format', 'pdf', '--generate-report',
        '--report-path', out/'o2-probe-drill-report.txt', board)
    for side in ('front', 'back'):
        layers = ('F.Fab,F.Silkscreen,Edge.Cuts,Dwgs.User,Cmts.User' if side == 'front'
                  else 'B.Fab,B.Silkscreen,Edge.Cuts')
        flags = ['--mirror'] if side == 'back' else []
        run(KICAD, 'pcb', 'export', 'pdf', '-o', out/f'o2-probe-assembly-{side}.pdf',
            '--layers', layers, '--mode-single', '--black-and-white', '--scale', '0',
            '--sketch-pads-on-fab-layers', '--crossout-DNP-footprints-on-fab-layers',
            '--check-zones', *flags, board)
    validation = {**check_gerbers(out), **check_drills(out, witness), 'drc': drc}
    source_out = out/'source'; source_out.mkdir()
    for name in ['o2-probe.kicad_pcb', 'o2-probe.kicad_pro', 'o2-probe.kicad_dru',
                 'o2-probe.kicad_sch', 'o2-probe.xml', 'fp-lib-table', 'sym-lib-table']:
        shutil.copy2(src/name, source_out/name)
    shutil.copytree(src/'lib', source_out/'lib')
    manifest = {
        'revision': 'B', 'purpose': 'engineering review', 'order_ready': False,
        'qualification_scope': 'CAD/export validation only; main-board heater/input protection, '
                               'procurement and physical qualification gates remain open; '
                               'J5 and the external ring are optional Rev C work',
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'kicad_cli': version, 'inputs_sha256': inputs,
        'board_sha256': sha256(board),
        'normalized_board_sha256': hashlib.sha256(normalized.encode()).hexdigest(),
        'validation': validation,
        'bom': {'result': expected_result, 'error_count': len(errors)},
        'commands': commands, 'elapsed_seconds': round(time.monotonic()-started, 3),
    }
    (out/'fab-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    # Verify the archive's bytes, not merely its filenames, before publishing
    # this local review artifact. Failed builds leave their staging evidence.
    files = sorted(p for p in out.rglob('*') if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.relative_to(out)}\n' for p in files))
    files.append(out/'SHA256SUMS')
    archive_path = work/'o2-probe-rev-b-review.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in files:
            archive.write(p, str(p.relative_to(out)))
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != {str(p.relative_to(out)) for p in files}:
            raise ValueError('ZIP inventory mismatch')
        for p in files:
            if hashlib.sha256(archive.read(str(p.relative_to(out)))).hexdigest() != sha256(p):
                raise ValueError(f'ZIP content mismatch: {p}')
    # Keep each successful review package immutable under its ZIP hash.
    digest = sha256(archive_path)
    release = fab/f'o2-probe-rev-b-{digest[:16]}'
    if release.exists():
        raise ValueError(f'Output collision: {release}')
    out.rename(release)
    destination = release/archive_path.name
    archive_path.rename(destination)
    (release/(destination.name+'.sha256')).write_text(f'{digest}  {destination.name}\n')
    # A pointer is updated only after the new package has passed every check.
    (fab/'rev-b-latest.json').write_text(json.dumps({'directory': release.name,
          'zip': destination.name, 'sha256': digest, 'order_ready': False}, indent=2)+'\n')
    shutil.rmtree(work)
    print(f'PASS: Rev B CAD/export checks; {drc["manual_assembly_courtyard_warnings"]} documented assembly warnings')
    print(f'BOM: {expected_result} ({len(errors)} procurement errors); engineering review, not order-ready')
    print(destination)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
