#!/usr/bin/env python3
"""Host test for pcb_netlist.py and the capability derivation.

WHY THIS IS NOT OPTIONAL. The parser's failure mode is not an exception, it is
an EMPTY RESULT that looks exactly like an unconnected board - and a capability
derived from an empty netlist says "AIN2 is not an electrode buffer", which is
a plausible answer that happens to be produced from nothing. A regex that
matched the schematic's `(net 12 "NAME")` spelling instead of the board's
`(net "NAME")` did precisely that during development: zero pads, no error.

So this asserts against pads whose nets are known INDEPENDENTLY - from the
2026-09-09 bench session, where U7 and U8 were probed with a DMM and the
netlist was read by hand to explain what the meter showed.

    python3 tools/test_pcb_netlist.py
"""
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gen_hw_caps          # noqa: E402
import pcb_netlist          # noqa: E402

FAILED = []


def check(name, got, want):
    if got != want:
        FAILED.append(f"{name}: got {got!r}, want {want!r}")
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


def main() -> int:
    pads = gen_hw_caps.load_rev_a_pads()

    # The parser found something at all. Item 1 of the guard checklist: an
    # unevaluable input must not read as a clean answer.
    if len(pads) < 100:
        print(f"FAIL parser returned only {len(pads)} pads - it is reading "
              f"almost nothing, and every capability derived from this is "
              f"invented. Do not 'fix' the expectations below.")
        return 1
    print(f"ok   parser found {len(pads)} pads on the fabricated board")

    # KNOWN PADS, from the bench. These are the ones that mattered on
    # 2026-09-09 and they were confirmed with a meter, not just read here.
    check("U7.11 (AFE reference)",  pcb_netlist.net_of(pads, "U7", 11), "/VREF_TRIM")
    check("U7.12 (working)",        pcb_netlist.net_of(pads, "U7", 12), "/CELL_WE")
    check("U7.13 (reference)",      pcb_netlist.net_of(pads, "U7", 13), "/CELL_RE")
    check("U7.14 (counter)",        pcb_netlist.net_of(pads, "U7", 14), "/CELL_CE")
    check("U7.2  (MENB)",           pcb_netlist.net_of(pads, "U7", 2),  "/AFE_MENB")

    # THE FAULT ITSELF. AIN2/AIN3 are rail monitors on the fabricated board,
    # which is what made the bias guard judge two power rails.
    check("U8.5 = AIN2",            pcb_netlist.net_of(pads, "U8", 5),  "/ADC_VA_MON")
    check("U8.4 = AIN3",            pcb_netlist.net_of(pads, "U8", 4),  "/ADC_VIN_MON")
    check("U8.9 = AIN0",            pcb_netlist.net_of(pads, "U8", 9),  "/ADC_AFE_VOUT")
    check("U8.8 = AIN1",            pcb_netlist.net_of(pads, "U8", 8),  "/ADC_VREF_MON")

    # The Rev A reference chain, established 2026-09-09. RV1 is a real trimmer
    # on this revision - it is gone in Rev B, and confusing the two is how the
    # first explanation of the pin-11 failure came out wrong twice.
    check("RV1.1 (trimmer top)",    pcb_netlist.net_of(pads, "RV1", 1), "/VREF_TOP")
    check("RV1.2 (wiper)",          pcb_netlist.net_of(pads, "RV1", 2), "/VREF_WIPER")
    # ...and the trimmer is NOT between the monitor and the AFE: U7.11 and the
    # ADS reference pin are the same node, and the monitor divider R34/R35 taps
    # it. So no amount of monitoring detects an open joint AT THE PIN.
    check("U8.7 (ADS reference)",   pcb_netlist.net_of(pads, "U8", 7),  "/VREF_TRIM")
    check("R34.1 (monitor tap)",    pcb_netlist.net_of(pads, "R34", 1), "/VREF_TRIM")

    # A pad that does not exist must FAIL, not return None. A silent None here
    # would flow straight into a capability as "not connected".
    try:
        pcb_netlist.net_of(pads, "U7", 99)
        FAILED.append("net_of returned for a nonexistent pad instead of failing")
        print("FAIL net_of(U7, 99) should have refused")
    except SystemExit:
        print("ok   net_of refuses a pad that does not exist")

    # THE DERIVATION, both directions. Same code, opposite answers, because the
    # netlists differ - that is the whole point of the split.
    check("Rev A bias capability", gen_hw_caps.derive(pads, "A")["bias_ok"], False)
    check("Rev B bias capability",
          gen_hw_caps.derive(gen_hw_caps.load_rev_b_pads(), "B")["bias_ok"], True)

    # UNEVALUABLE INPUT MUST NOT PRODUCE A VERDICT (guard checklist item 1).
    #
    # derive() used to wrap net_of() in `except SystemExit: "(absent)"`, which
    # turned an unreadable netlist into bias_ok = False - a capability computed
    # from no evidence. It pointed the safe way by luck; the next capability
    # whose safe value is 1 would have been silently wrong. Remove a pad a
    # macro depends on and the generator must REFUSE, not default.
    import copy
    for ref, pad, label in (("U8", "5", "AIN2 / bias capability"),
                            ("U8", "4", "AIN3 / bias capability"),
                            ("U7", "11", "AFE reference net")):
        broken = copy.deepcopy(pads)
        del broken[(ref, pad)]
        try:
            gen_hw_caps.derive(broken, "A")
            FAILED.append(f"derive() invented a capability with {ref}.{pad} "
                          f"missing ({label})")
            print(f"FAIL derive() should refuse when {ref}.{pad} is missing")
        except SystemExit:
            print(f"ok   derive() refuses when {ref}.{pad} is missing ({label})")

    if FAILED:
        print(f"\n{len(FAILED)} failure(s):")
        for f in FAILED:
            print("  " + f)
        return 1
    print("\npcb netlist + capability derivation: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
