#!/usr/bin/env python3
"""Compare the candidate's physical pad assignments/values with the live schematic.

This does not substitute for ERC, a fresh DRC refill, or bench qualification.
No cached reports are read. Run with ordinary Python; KiCad is not required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

import gen_sch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'firmware/tools'))
import pcb_netlist


def blocks_of(text, token):
    """Read complete KiCad blocks, respecting quoted/escaped parentheses."""
    for match in re.finditer(r'\(' + re.escape(token) + r'\s', text):
        depth = 0
        quoted = escaped = False
        for end in range(match.start(), len(text)):
            char = text[end]
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    yield text[match.start():end + 1]
                    break
        else:
            raise ValueError(f'Unterminated {token} block')


def check(board):
    gen_sch.verify()
    text = board.read_text()
    pads = pcb_netlist.load(board)
    entries = []
    for block in blocks_of(text, 'footprint'):
        ref = pcb_netlist._REFERENCE.search(block)
        if ref is None:
            raise ValueError('Footprint without a reference')
        entries.append((ref.group(1), block))
    refs = [ref for ref, _ in entries]
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate footprint references')
    for ref, block in entries:
        # Rev B has no duplicated electrical pads after retiring J5.
        seen = {}
        for pad_body in blocks_of(block, 'pad'):
            match = re.match(r'\(pad\s+"([^"]*)"', pad_body)
            if match is None:
                raise ValueError(f'{ref}: malformed pad')
            pin = match.group(1)
            if not pin:
                continue  # mechanical, unnumbered holes
            names = pcb_netlist._NET.findall(pad_body)
            if len(names) != 1:
                raise ValueError(f'{ref}.{pin}: missing or ambiguous pad net')
            if pin in seen:
                raise ValueError(f'{ref}.{pin}: duplicate electrical pad')
            seen[pin] = names[0]
    blocks = dict(entries)
    expected = {r: i for r, i in gen_sch.INST.items() if i['footprint']}
    if set(blocks) != set(expected):
        raise ValueError(f'Footprints differ: missing={set(expected)-set(blocks)}, '
                         f'extra={set(blocks)-set(expected)}')
    checked = 0
    for (ref, pin), name in gen_sch.ASSIGNED.items():
        if ref not in expected:
            continue
        got = pcb_netlist.net_of(pads, ref, pin)
        if name == '(NC)':
            good = got.startswith(f'unconnected-({ref}-') and got.endswith(f'-Pad{pin})')
        else:
            good = got == '/' + name
        if not good:
            raise ValueError(f'{ref}.{pin}: board={got!r}, schematic={name!r}')
        checked += 1
    for ref, inst in expected.items():
        for key, want in [('Value', inst['value']), ('MPN', inst['mpn'])]:
            if key == 'MPN' and not want:
                continue
            match = re.search(r'\(property\s+"' + key + r'"\s+("(?:[^"\\]|\\.)*")',
                              blocks[ref])
            if match is None or json.loads(match.group(1)) != want:
                raise ValueError(f'{ref}: {key} differs from schematic ({want!r})')
    return checked, len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', nargs='?', type=Path,
                        default=HERE/'routing/revb-interfaces/o2-probe.kicad_pcb')
    args = parser.parse_args()
    pins, parts = check(args.board)
    print(f'PASS: {pins} package pins and {parts} part values match the live schematic')
    for path in [args.board, HERE/'gen_sch.py', Path(__file__),
                 HERE/'firmware/tools/pcb_netlist.py']:
        print(f'SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}  {path}')
    print('Electrical connectivity/clearance requires a fresh KiCad DRC; bench qualification is separate.')


if __name__ == '__main__':
    main()
