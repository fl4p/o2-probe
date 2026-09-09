#!/usr/bin/env python3
"""Read pad -> net assignments out of a fabricated .kicad_pcb.

WHY THIS EXISTS. `gen_sch.py` is the source of truth for the board being
DESIGNED. It is not, and cannot be, the truth about a board that was
manufactured from an earlier revision of it and is now on the bench: the
schematic moves on, the copper does not. Deriving a firmware contract for a
fabricated article from the current schematic is how the 2026-09-09 session
spent an afternoon judging two power rails against a commanded electrode bias
on a probe that was working correctly - see docs/2026-09-09-afe-rework-debug.md.

So a fabricated revision gets its contract from the artifact that was actually
made. This module is the reader for that artifact.

FORMAT NOTE, measured rather than assumed. In KiCad 10's board format a pad
carries its net as `(net "/NAME")` - a bare name, with NO net index. Several
earlier attempts at this used `\\(net \\d+ "..."`, which is the NETLIST/schematic
spelling, and silently matched nothing: an empty result that looks exactly like
"this part has no connections". Any change here must be checked against a pad
whose net is known, which is what test_pcb_netlist.py does.

Reading is deliberately structural rather than regex-over-the-whole-file: pads
are collected per footprint block so a pad can never be attributed to the wrong
reference designator. PIN-IDENTITY-POSTMORTEM.md is what happens when pin
identity is got wrong by one step.
"""
import pathlib
import re
import sys

_FOOTPRINT = re.compile(r'\(footprint\s')
_REFERENCE = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
# A pad: its number, then - anywhere inside that pad's own block - a net name.
# The lazy span stops at the next `(pad ` so a pad with no net cannot borrow
# the next pad's.
_PAD = re.compile(r'\(pad\s+"([^"]+)"(.*?)(?=\(pad\s+"|\Z)', re.S)
_NET = re.compile(r'\(net\s+"([^"]+)"\s*\)')


def _footprint_blocks(text: str):
    """Yield (reference, block_text) for every footprint in the board."""
    starts = [m.start() for m in _FOOTPRINT.finditer(text)]
    for a, b in zip(starts, starts[1:] + [len(text)]):
        block = text[a:b]
        ref = _REFERENCE.search(block)
        if ref:
            yield ref.group(1), block


def load(path) -> dict:
    """{(reference, pad): net} for every pad that has a net.

    Pads with no net are omitted rather than mapped to None: "not connected"
    and "we failed to parse it" must not share a representation, because the
    caller's whole job is deciding what a pin is wired to.
    """
    text = pathlib.Path(path).read_text()
    out = {}
    for ref, block in _footprint_blocks(text):
        for pad in _PAD.finditer(block):
            net = _NET.search(pad.group(2))
            if net:
                out[(ref, pad.group(1))] = net.group(1)
    if not out:
        raise SystemExit(f"{path}: no pad/net pairs found - the board format "
                         f"has changed and this parser is reading nothing. "
                         f"Do NOT treat this as an unconnected board.")
    return out


def net_of(pads: dict, ref: str, pin) -> str:
    """The net on one pad, or a hard failure.

    No default and no None. A missing pad means the caller's assumption about
    the part is wrong, and continuing from that produces a contract that is
    confidently incorrect - the exact failure mode this whole file exists to
    prevent.
    """
    key = (ref, str(pin))
    if key not in pads:
        raise SystemExit(f"{ref} pad {pin} is not connected, or does not exist "
                         f"on this board. Refusing to guess.")
    return pads[key]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: pcb_netlist.py <board.kicad_pcb> [REF ...]")
    pads = load(sys.argv[1])
    wanted = set(sys.argv[2:])
    for (ref, pad), net in sorted(pads.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if not wanted or ref in wanted:
            print(f"{ref:>5} pad {pad:>3} -> {net}")
