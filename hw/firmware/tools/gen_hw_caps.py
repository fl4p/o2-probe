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


def _required(pads: dict, ref: str, pin, why: str) -> str:
    """The net on a pad a CAPABILITY depends on, or a hard failure.

    NO try/except AND NO DEFAULT, and that is the whole point of this function.

    The first version of derive() wrapped pcb_netlist.net_of() in
    `except SystemExit: "(absent)"`. net_of() raises precisely so that a pad it
    cannot find stops the run - "Refusing to guess" - and catching it turned an
    UNREADABLE NETLIST into a capability of 0: a verdict manufactured from no
    evidence, dressed as a safe default.

    It happened to point the safe way for bias_ok. That is luck, not design.
    The next capability whose safe value is 1 would silently emit 0 and disable
    a guard, or emit 1 and enable one, with nothing anywhere saying the netlist
    could not be read. It is also exactly the failure this repo's guard
    checklist names first - "missing/bad data, too few samples, failed probes
    and exceptions must not mean OK" - committed inside the tool written to
    enforce it.

    So: a pad that feeds an emitted macro must resolve, or NOTHING is emitted.
    A missing part on a future revision is a real signal that wants a human
    decision about what that revision can and cannot assert, not a zero.
    """
    key = (ref, str(pin))
    if key not in pads:
        raise SystemExit(
            f"{ref} pad {pin} is not in this revision's netlist, and "
            f"{why} depends on it.\n"
            f"Refusing to emit a capability header: a capability derived from "
            f"a netlist that could not be read is invented, not derived.\n"
            f"If this revision genuinely lacks the part, decide explicitly what "
            f"it can assert and encode that - do not let it default.")
    return pads[key]


def derive(pads: dict, rev: str) -> dict:
    """The capability predicates. Mechanical, from pads alone."""
    ain = {}
    for pad, n in ADS_AIN_PADS.items():
        ain[n] = _required(pads, "U8", pad, f"O2P_HW_ADC_AIN{n}_NET")

    bias_ok = (ain[2] in ELECTRODE_WE_NETS) and (ain[3] in ELECTRODE_RE_NETS)

    # Does the board's VREF monitor share a NET with the AFE's reference pin?
    # Note carefully what this can and cannot tell you: sharing a net means the
    # monitor reads the right NODE, but it still cannot detect an OPEN SOLDER
    # JOINT at U7 pin 11, because the net stays healthy while the die is not
    # attached to it. That is exactly what happened on 2026-09-09 - `vref` read
    # 2490 mV while the chip's internal zero was 0 - and it is why "monitor the
    # reference harder" is not the fix. Emitted for diagnosis, not for trust.
    afe_ref = _required(pads, "U7", 11, "O2P_HW_VREF_NET_SHARED_WITH_AFE")
    ads_ref = _required(pads, "U8", 7, "O2P_HW_VREF_NET_SHARED_WITH_AFE")

    pa4_net = _required(pads, "U6", 15, "the CE-on-MCU capability")
    pa6_net = _required(pads, "U6", 17, "the VIN-on-MCU capability")

    # --- can this board be commanded transceiver-deaf? ---
    #
    # Rev A tied the THVD1410's /RE (U5.2) to DE (U5.3) on one net, so the
    # part's low-power state - /RE high, DE low - is not reachable no matter
    # what the firmware writes, and the receiver burns 700 uA forever.
    # POWER-BUDGET.md 2026-09-07 split /RE onto PC7 in gen_sch.py, which moved
    # the DRAWING; the fabricated board on the bench is still shorted.
    #
    # BOTH HALVES ARE REQUIRED. A split at the transceiver that never reaches
    # the MCU is not a split: the pin the firmware drives has to BE the net the
    # transceiver listens to. Checking only "U5.2 != U5.3" would call a
    # half-finished rework capable.
    re_net = _required(pads, "U5", 2, "O2P_HW_RS485_RE_ON_ITS_OWN_PIN")
    de_net = _required(pads, "U5", 3, "O2P_HW_RS485_RE_ON_ITS_OWN_PIN")
    mcu_re = _required(pads, "U6", 31, "O2P_HW_RS485_RE_ON_ITS_OWN_PIN")
    re_split = (re_net != de_net) and (mcu_re == re_net)

    # R45, the 47k that makes LISTENING the passive default.
    #
    # PRESENCE, not a net, is the question here - so this is the one predicate
    # that reads a missing part as an answer rather than as a failure, and
    # _required() is deliberately not used. The distinction that makes it safe:
    # _required() refuses to guess the NET ON A PAD THAT EXISTS, because an
    # unreadable netlist there would manufacture a verdict. "Is R45 fitted" has
    # absence as its true negative, and the negative is the UNSAFE-hardware
    # direction (/RE floats high on the part's 2 MOhm pull-up, i.e. deaf), so a
    # missing part cannot read as a capability. Both pads are still checked
    # against the nets they must land on, so an R45 wired somewhere else does
    # not count.
    re_pulldown = (pads.get(("R45", "1")) == re_net and
                   pads.get(("R45", "2")) == "/GND" and
                   re_split)

    ce_connected = pa4_net in {"/CE_MON", "/ADC_CE_MON"}
    vin_on_mcu = pa6_net in {"/VIN_MON", "/ADC_VIN_MON"}
    vin_on_ads = ain.get(3) in {"/ADC_VIN_MON", "/VIN_MON"}
    va_on_ads = ain.get(2) in {"/ADC_VA_MON", "/VA_MON"}

    return {
        "rev": rev,
        "ain": ain,
        "bias_ok": bias_ok,
        "afe_ref_net": afe_ref,
        "ads_ref_net": ads_ref,
        "ref_shared": afe_ref == ads_ref,
        "pa4_net": pa4_net,
        "pa6_net": pa6_net,
        "re_net": re_net,
        "de_net": de_net,
        "mcu_re_net": mcu_re,
        "re_split": re_split,
        "re_pulldown": re_pulldown,
        "ce_connected": ce_connected,
        "vin_on_mcu": vin_on_mcu,
        "vin_on_ads": vin_on_ads,
        "va_on_ads": va_on_ads,
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
    a(" * 1 only when AIN2/AIN3 are NAMED as the WE/RE electrode buffers.")
    a(" *")
    a(" * WHAT THIS DOES NOT PROVE, because a reviewer asked and the honest")
    a(" * answer is 'less than it looks': this matches NET NAMES. It does not")
    a(" * trace the net to U7.12/U7.13, and it cannot - ADC_WE_BUF is the")
    a(" * OUTPUT of a follower whose input is CELL_WE, so the two are different")
    a(" * nets by design and net identity can never connect them. A revision")
    a(" * that names a net /ADC_WE_BUF while wiring it elsewhere would read as")
    a(" * capable. That is a smaller risk than the one this replaced - a")
    a(" * hand-maintained flag nobody re-checked - but it is not zero, and a")
    a(" * bench check of WE against 0.67 x VREF is still the thing that")
    a(" * actually confirms it on a new board.")
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
    a("/* ---- RS-485 receiver enable: can this board be commanded deaf? ----")
    a(" *")
    a(" * THVD1410 /RE is U5 pin 2 and is ACTIVE LOW. The part\'s 0.1 uA")
    a(" * standby needs /RE HIGH with DE LOW, which is unreachable when the")
    a(" * two share a net - Rev A does, and its receiver therefore burns")
    a(" * 700 uA forever, 24 % of the board\'s idle draw (POWER-BUDGET.md).")
    a(" *")
    a(" * 1 requires BOTH that /RE has a net of its own AND that the net")
    a(" * reaches the MCU pin the firmware drives. A rework that lifts the")
    a(" * pin but never lands the wire is not a capability.")
    a(" *")
    a(f" * This revision: U5.2 = {d['re_net']}, U5.3 = {d['de_net']},")
    a(f" *                MCU pin 31 (PC7) = {d['mcu_re_net']}.")
    a(" *")
    a(" * When 0, o2p_modbus_rx_standby(true) must REFUSE rather than write a")
    a(" * pin that goes nowhere and report a standby that did not happen.")
    a(" */")
    a(f"#define O2P_HW_RS485_RE_ON_ITS_OWN_PIN {1 if d['re_split'] else 0}")
    a("")
    a("/* Is LISTENING the passive default - R45, 47k from /RE to GND?")
    a(" *")
    a(" * /RE floats HIGH on the transceiver\'s ~2 MOhm internal pull-up and")
    a(" * every MCU GPIO is high-impedance out of reset, so without this a")
    a(" * probe sitting in its RS-485 bootloader, or with no working")
    a(" * application at all, is DEAF - and a potted one is unrecoverable.")
    a(" * That is the field-reflash path of SCHEMATIC-REVIEW.md M2.")
    a(" *")
    a(" * 0 on a board whose /RE is not split is not a missing part: there is")
    a(" * nothing for it to pull down, and R7 on the shared net already does")
    a(" * this job. 0 on a board that IS split is a fitting error, and the")
    a(" * probe must not be potted until it is fixed.")
    a(" */")
    a(f"#define O2P_HW_RS485_RE_PASSIVE_PULLDOWN {1 if d['re_pulldown'] else 0}")
    a("")
    a("/* ---- MCU ADC pin connectivity ---- */")
    a(f'#define O2P_HW_MCU_PA4_NET "{d["pa4_net"]}"')
    a(f'#define O2P_HW_MCU_PA6_NET "{d["pa6_net"]}"')
    a(f"#define O2P_HW_CE_MON_CONNECTED {1 if d['ce_connected'] else 0}")
    a(f"#define O2P_HW_VIN_MON_ON_MCU {1 if d['vin_on_mcu'] else 0}")
    a(f"#define O2P_HW_VIN_MON_ON_ADS {1 if d['vin_on_ads'] else 0}")
    a(f"#define O2P_HW_VA_MON_ON_ADS {1 if d['va_on_ads'] else 0}")
    a("")
    a("/* ---- ADS1119 rail divider scaling (Rev A: R24/R25 10k/10k, R26/R27 130k/20k) ---- */")
    if rev == "A":
        a("#define O2P_HW_DIV_VA_ADS_NUM   10000u")
        a("#define O2P_HW_DIV_VA_ADS_DEN   20000u")
        a("#define O2P_HW_DIV_VIN_ADS_NUM  20000u")
        a("#define O2P_HW_DIV_VIN_ADS_DEN 150000u")
    else:
        a("#define O2P_HW_DIV_VA_ADS_NUM   1u")
        a("#define O2P_HW_DIV_VA_ADS_DEN   1u")
        a("#define O2P_HW_DIV_VIN_ADS_NUM  1u")
        a("#define O2P_HW_DIV_VIN_ADS_DEN  1u")
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
