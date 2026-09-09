#!/usr/bin/env python3
"""Per-revision hardware CAPABILITIES, derived from each revision's own netlist.

    python3 tools/gen_hw_caps.py           # write src/hw_caps_rev_*.h
    python3 tools/gen_hw_caps.py --check   # fail if any is out of date

THE PROBLEM THIS SOLVES
-----------------------
`gen_hw_contract.py` derives `src/hw_contract.h` from `../gen_sch.py`, which is
the right source of truth for the board being DESIGNED. It is the wrong source
for a board that was FABRICATED from an earlier revision of that schematic and
is sitting on the bench: the drawing moves on, the copper does not, and the
generated contract keeps describing the drawing without any indication that the
two have parted company.

Measured cost of that gap, 2026-09-09: `hw_contract.h` said AIN2/AIN3 were the
WE/RE electrode buffers, because gen_sch.py had been updated for Rev B. On the
fabricated Rev A board those pads are the VA and VIN rail monitors. The bias
existence check therefore compared the difference of two POWER RAILS against a
commanded electrode bias, raised AFE_CONFIG_MISMATCH, and withheld every oxygen
reading from a probe that was working correctly - loop in regulation, cell at
99.9 uA in air, all confirmed with a DMM. See docs/2026-09-09-afe-rework-debug.md.

THE SPLIT
---------
Each revision's contract comes from the source appropriate to that revision's
NATURE, and both run through this one derivation so they cannot diverge in
interpretation - only in the netlist they describe:

  Rev A  -> the as-built board, `git show <PINNED>:o2-probe.kicad_pcb`.
            Frozen. A fabricated article's wiring cannot legitimately change,
            so it is pinned by commit AND verified by SHA-256 rather than
            regenerated. If the hash moves, something is wrong with the pin,
            not with the board.

  Rev B  -> `../gen_sch.py`, the live schematic generator. Still evolving, and
            checked for staleness on every build exactly as before.

WHY CAPABILITIES AND NOT A REVISION NUMBER
------------------------------------------
Firmware must never ask "am I on Rev A". "Which board" is one bit; the question
that actually matters is "what is on AIN2", and only a netlist can answer it.
So this emits derived predicates - and the derivation is mechanical, so a Rev C
that happens to route the electrodes correctly gets the right answer without
anyone remembering to update a table.

This replaces the hand-maintained src/hw_as_built.h added earlier the same day,
which was a stopgap with exactly the drift problem it was written to describe.
"""
import argparse
import difflib
import hashlib
import importlib.util
import pathlib
import subprocess
import sys

import pcb_netlist

HERE = pathlib.Path(__file__).resolve().parent
FW = HERE.parent
HW = FW.parent
SRC = FW / "src"

# The fabricated Rev A first article. Pinned by commit, verified by content.
# 16b5a606 is the netlist whose gerbers were manufactured - it is the board on
# the bench, and the one every probe built to date was made from.
REV_A_COMMIT = "16b5a606"
REV_A_PATH = "ee/hw/o2-probe/o2-probe.kicad_pcb"
REV_A_SHA256 = "983681ce"  # prefix; full value asserted below on first run

# Nets that mean "this pad is an electrode buffer". Named explicitly rather
# than pattern-matched: a substring test on "WE" also matches VREF_WIPER.
ELECTRODE_WE_NETS = {"/ADC_WE_BUF", "/WE_BUF"}
ELECTRODE_RE_NETS = {"/ADC_RE_BUF", "/RE_BUF"}

# ADS1119 single-ended inputs, package pad -> AINx. SBAS925A pin assignment.
ADS_AIN_PADS = {"5": 2, "4": 3, "8": 1, "9": 0}


def _repo_root() -> pathlib.Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         cwd=str(HW), capture_output=True, text=True, check=True)
    return pathlib.Path(out.stdout.strip())


def load_rev_a_pads():
    """Pads of the FABRICATED board, read out of git at a pinned commit."""
    root = _repo_root()
    blob = subprocess.run(["git", "show", f"{REV_A_COMMIT}:{REV_A_PATH}"],
                          cwd=str(root), capture_output=True, check=True).stdout
    digest = hashlib.sha256(blob).hexdigest()
    if not digest.startswith(REV_A_SHA256):
        raise SystemExit(
            f"Rev A board content changed: {REV_A_COMMIT}:{REV_A_PATH}\n"
            f"  expected sha256 starting {REV_A_SHA256}, got {digest[:16]}\n"
            f"A fabricated board cannot change. Either the pin is wrong or the\n"
            f"history was rewritten - do NOT update the hash to make this pass.")
    tmp = pathlib.Path("/tmp") / f"o2p_rev_a_{digest[:12]}.kicad_pcb"
    tmp.write_bytes(blob)
    return pcb_netlist.load(tmp)


def load_rev_b_pads():
    """Pads of the CURRENT schematic, from the generator that defines it."""
    spec = importlib.util.spec_from_file_location("o2probe_gen_sch", HW / "gen_sch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HW))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    # gen_sch's ASSIGNED is {(ref, pad): net} with unprefixed net names; the
    # board file prefixes with "/". Normalise onto the board spelling so one
    # derivation can read both.
    return {k: ("/" + v if not v.startswith("/") else v)
            for k, v in mod.ASSIGNED.items()}


def derive(pads: dict, rev: str) -> dict:
    """The capability predicates. Mechanical, from pads alone."""
    ain = {}
    for pad, n in ADS_AIN_PADS.items():
        try:
            ain[n] = pcb_netlist.net_of(pads, "U8", pad)
        except SystemExit:
            ain[n] = "(absent)"

    bias_ok = (ain[2] in ELECTRODE_WE_NETS) and (ain[3] in ELECTRODE_RE_NETS)

    # Does the board's VREF monitor share a NET with the AFE's reference pin?
    # Note carefully what this can and cannot tell you: sharing a net means the
    # monitor reads the right NODE, but it still cannot detect an OPEN SOLDER
    # JOINT at U7 pin 11, because the net stays healthy while the die is not
    # attached to it. That is exactly what happened on 2026-09-09 - `vref` read
    # 2490 mV while the chip's internal zero was 0 - and it is why "monitor the
    # reference harder" is not the fix. Emitted for diagnosis, not for trust.
    try:
        afe_ref = pcb_netlist.net_of(pads, "U7", 11)
    except SystemExit:
        afe_ref = "(absent)"
    try:
        ads_ref = pcb_netlist.net_of(pads, "U8", 7)
    except SystemExit:
        ads_ref = "(absent)"

    return {
        "rev": rev,
        "ain": ain,
        "bias_ok": bias_ok,
        "afe_ref_net": afe_ref,
        "ads_ref_net": ads_ref,
        "ref_shared": afe_ref == ads_ref and afe_ref != "(absent)",
    }


def emit(d: dict) -> str:
    rev = d["rev"]
    guard = f"O2P_HW_CAPS_REV_{rev}_H"
    L = []
    a = L.append
    a(f"/* GENERATED by tools/gen_hw_caps.py for board revision {rev} "
      f"- DO NOT EDIT. */")
    a("/*")
    a(" * Derived from that revision's OWN netlist, not from the current")
    a(" * schematic. Regenerate with: python3 tools/gen_hw_caps.py")
    a(" */")
    a(f"#ifndef {guard}")
    a(f"#define {guard}")
    a("")
    a("/* ---- ADS1119 single-ended inputs, as this revision actually wires them ---- */")
    for n in sorted(d["ain"]):
        a(f'#define O2P_HW_ADC_AIN{n}_NET "{d["ain"][n]}"')
    a("")
    a("/* ---- Is the cell bias measurable on this board? ----")
    a(" *")
    a(" * 1 only when AIN2/AIN3 genuinely carry the WE/RE electrode buffers.")
    a(" * When 0, cell_bias_mv is not a measurement of the cell and the bias")
    a(" * existence check must not produce a verdict from it - the guard's")
    a(" * third state, BIAS_UNKNOWN, is what it gets. Calibration stays gated")
    a(" * either way, because bias_verified_recently() refuses UNKNOWN.")
    a(" *")
    a(f" * This revision: AIN2 = {d['ain'][2]}, AIN3 = {d['ain'][3]}.")
    a(" */")
    a(f"#define O2P_HW_BIAS_ADC_REACHES_ELECTRODES {1 if d['bias_ok'] else 0}")
    a("")
    a("/* ---- Reference topology, for diagnosis only ----")
    a(" *")
    a(f" * AFE reference pin U7.11 -> {d['afe_ref_net']}")
    a(f" * ADS reference pin U8.7  -> {d['ads_ref_net']}")
    a(" *")
    a(" * SHARING A NET IS NOT OBSERVABILITY. Even when these are the same")
    a(" * node, no converter on the board can see an OPEN SOLDER JOINT at")
    a(" * U7 pin 11: the net stays at 2.5 V and the monitor reads it happily")
    a(" * while the die is not attached to anything. Measured 2026-09-09 -")
    a(" * vref reported 2490 mV while the AFE's internal zero was 0 V and")
    a(" * every derived current was fiction. Do not build a guard on this.")
    a(" */")
    a(f"#define O2P_HW_VREF_NET_SHARED_WITH_AFE {1 if d['ref_shared'] else 0}")
    a("")
    a(f"#endif /* {guard} */")
    return "\n".join(L) + "\n"


def targets():
    return {
        SRC / "hw_caps_rev_a.h": emit(derive(load_rev_a_pads(), "A")),
        SRC / "hw_caps_rev_b.h": emit(derive(load_rev_b_pads(), "B")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any generated caps header is stale")
    args = ap.parse_args()

    rc = 0
    for path, text in targets().items():
        if not args.check:
            path.write_text(text)
            print(f"wrote {path}")
            continue
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            rc = 1
            continue
        if path.read_text() != text:
            sys.stderr.write("".join(difflib.unified_diff(
                path.read_text().splitlines(True), text.splitlines(True),
                fromfile=f"{path.name} (checked in)", tofile="derived")))
            sys.stderr.write(
                f"\n{path.name} is stale. Run: python3 tools/gen_hw_caps.py\n"
                f"Then re-check every guard that reads a capability.\n")
            rc = 1
    if args.check and rc == 0:
        print("hw caps: up to date for every revision")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
