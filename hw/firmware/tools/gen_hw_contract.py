#!/usr/bin/env python3
"""Derive the firmware's hardware contract from the schematic generator.

`../gen_sch.py` is the declared source of truth for this board (DESIGN.md
"Status and source of truth"), and FAB-READINESS.md states plainly that
firmware must use its final pin map. This script is what makes that
mechanical instead of aspirational: it imports the generator, extracts every
value the firmware converts with, and emits `src/hw_contract.h`.

    python3 tools/gen_hw_contract.py            # write src/hw_contract.h
    python3 tools/gen_hw_contract.py --check    # fail if it is out of date

`--check` runs as a PlatformIO pre-build action, so a schematic change that
moves a pin or rescales a divider breaks the firmware build instead of
silently rescaling every reported value. That is not hypothetical: the VIN
divider was already changed from 130k/20k to 82k/10k, and gen_sch.py:520
carries a "FIRMWARE:" note about it precisely because nothing enforced it.

Importing the generator is side-effect free - it only populates dictionaries;
the file writes live behind `if __name__ == "__main__"`.
"""
import argparse
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
FW = HERE.parent
HW = FW.parent
OUT = FW / "src" / "hw_contract.h"

# Nets the firmware actually touches. A pin appearing in MCU_NETS but not here
# is emitted anyway (the contract is the whole map); this list only names the
# ones board_pins.h is required to bind.
# 2026-09-12: ADC_DRDY LEFT this set because the ADS1119 left the schematic
# (docs/2026-09-12-revb-decision-delete-ads1119.md). The four analog channels it
# used to carry arrive here instead, and they are REQUIRED rather than merely
# emitted so that board_pins.h has to bind each one to a pin the schematic
# actually assigns - the ADC channel a conversion reads is exactly the kind of
# number that is wrong silently.
REQUIRED_NETS = {
    "VA_MON", "VIN_MON", "CE_MON", "AFE_MENB", "HEATER_PWM",
    "RS485_TX", "RS485_RX", "RS485_DE", "RS485_RE", "I2C_SCL", "I2C_SDA",
    "ADC_WE_BUF", "ADC_RE_BUF", "ADC_AFE_VOUT", "VREF_TRIM",
}


def load_generator():
    spec = importlib.util.spec_from_file_location("o2probe_gen_sch", HW / "gen_sch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HW))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def ohms(value: str) -> float:
    """Parse the leading resistance token of a KiCad value string.

    Accepts '91k 1%', '280R 1W', '2k 10-turn', '100k'. Raises on anything it
    does not fully understand rather than guessing - a misparsed divider leg
    is exactly the silent rescale this file exists to prevent.

    The docstring said that before this function did it. re.match anchors only
    the START, so the TRAILER was never checked and '91k nonsense' parsed as
    91k -- caught by a reviewer's mutation test, 2026-09-05. The trailer is now
    a closed vocabulary: a tolerance, a power rating, a turns count, or nothing.
    """
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([kKmMrR]?)"
                 r"(?:\s+(?:[0-9]*\.?[0-9]+\s*%"
                 r"|[0-9]*\.?[0-9]+\s*[munpMK]?[WV]"
                 r"|[0-9]+-turn))*\s*$", value)
    if not m:
        raise ValueError(f"cannot parse resistance from {value!r}")
    mult = {"": 1.0, "r": 1.0, "R": 1.0, "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}[m.group(2)]
    return float(m.group(1)) * mult


def build(g) -> str:
    inst, assigned = g.INST, g.ASSIGNED

    def val(ref):
        return ohms(inst[ref]["value"])

    def net_of(ref, pin):
        return assigned[(ref, str(pin))]

    def pin_named(ref, name):
        """Pad number of `ref`'s pin called `name`, from the generator's symbol.

        Strap checks resolve pins by NAME. A hand-typed pad number was wrong
        here until 2026-10-22: "TMP117 ADD0 (U10.5)" read pad 5, which is V+,
        so the check tested V+ == 3V3D and could never fail (ADD0 is pad 4).
        """
        pads = [num for num, pname, _t in g.SYMS[inst[ref]["lib_id"]]["pins"] if pname == name]
        if len(pads) != 1:
            raise SystemExit(f"{ref} has {len(pads)} pins named {name!r}; expected exactly one")
        return pads[0]

    # --- pin map ----------------------------------------------------------
    mcu = dict(g.MCU_NETS)
    by_net = {}
    for pin, net in mcu.items():
        by_net.setdefault(net, []).append(pin)
    missing = sorted(n for n in REQUIRED_NETS if n not in by_net)
    if missing:
        raise SystemExit(f"gen_sch.py MCU_NETS no longer carries: {', '.join(missing)}")
    dup = sorted(n for n in REQUIRED_NETS if len(by_net[n]) != 1)
    if dup:
        raise SystemExit(f"nets bound to more than one MCU pin: {', '.join(dup)}")

    # --- dividers ---------------------------------------------------------
    # MCU ADC1_IN6 (PA6): +12V_SW through R26 (top) / R27 (bottom).  Moved off
    # the ADS1119 when AIN3 was taken for cell bias telemetry.
    r26, r27 = val("R26"), val("R27")
    # MCU ADC1_IN7 (PA7): 3V3A through R24 / R25.  Also moved off the ADS1119.
    r24, r25 = val("R24"), val("R25")
    # The VREF monitor's scale factor USED to be derived here, from R34/R35.
    # It moved to hw_caps_rev_*.h on 2026-09-12, when Rev B deleted that divider
    # and measured /VREF_TRIM directly: a scale factor for a FABRICATED board
    # must not follow the drawing. See O2P_HW_DIV_VREF_MON_* there.
    # MCU ADC1_IN4 (PA4): the LMP91000's CE DRIVE PIN through R43 / R44.  Not the
    # electrode -- SNAS506 6.5 bounds A1's drive at the device pin, so the pin is
    # the node whose compliance can be exceeded.  100k/100k rather than the 10k
    # pairs above because this divider loads A1's output directly.
    r43, r44 = val("R43"), val("R44")
    # R42 is the CE fault-current limit.  The firmware does not convert with it --
    # it is inside the control loop, so it does not scale any measurement -- but a
    # change here moves the compliance budget, so it is emitted to be asserted on.
    r42 = val("R42")

    # --- fixed reference: U15 AZ431B shunt, no adjustable part ------------
    # POTTING.md 1.2 deleted R20/RV1/R21: the cell is swappable with the board
    # potted, so nothing on the potted side may need trimming.  The window below
    # is therefore the REFERENCE's guaranteed tolerance, not a pot's travel --
    # a tighter check than the one it replaces.  AZ431-A Rev 3.4, B grade (the
    # 0.4 % bin): VREF 2.490 / 2.500 / 2.510 at 25 C, plus "Deviation of
    # Reference Voltage Over Full Temperature Range" of 10 mV MAX across
    # -40..85 C.  Worst case is therefore 2.480..2.520 V.  The macro names are
    # unchanged so main.c's health check keeps compiling, but they now mean "is
    # the reference within spec", not "is the pot somewhere in range".
    vref_target_mv = 2500.0
    vref_tol_mv = 10.0 + 10.0
    vref_min_mv = vref_target_mv - vref_tol_mv
    vref_max_mv = vref_target_mv + vref_tol_mv

    # --- heater -----------------------------------------------------------
    # RH1/RH2 are ON this board (Fab, 2026-09-04, "the heater stays where it is").
    # An earlier pass deleted them, moved the heat source to the ring PCB, and
    # suppressed O2P_HW_HEATER_OHM so that "anything that used it must fail to
    # compile rather than silently assume 140 ohm".  That inverted the contract
    # relative to the hardware: the parts were never removed from the board the
    # bench was measuring.  Derive the constant from the schematic instead of
    # asserting either state.
    rh1, rh2 = val("RH1"), val("RH2")
    heater_ohm = 1.0 / (1.0 / rh1 + 1.0 / rh2)
    # Cross-check against the bench, o2probe-bench session 2026-09-04: VIN fell
    # 11960 -> 11914 mV between 0 and 93 % duty, ~46 mV for the predicted ~80 mA,
    # confirming the 140 ohm main-board load (1.02 W at full duty on 12 V).
    if not 139.0 <= heater_ohm <= 141.0:
        raise SystemExit(
            f"heater is {heater_ohm:.1f} ohm from RH1={rh1}/RH2={rh2}; the bench "
            "measured 140 ohm on the first article, so either the schematic "
            "changed deliberately or a value is wrong -- do not emit silently"
        )
    r28, r29 = val("R28"), val("R29")

    # --- strapping that fixes the I2C addresses ---------------------------
    # U8, the ADS1119, left the schematic on 2026-09-12, and with it its address
    # straps. Checked by PRESENCE rather than dropped: if a future revision puts
    # an ADS back, its strapping must be re-checked, not inherited silently.
    add0 = pin_named("U10", "ADD0")
    straps = {f"TMP117 ADD0 (U10.{add0})": net_of("U10", add0)}
    if "U8" in inst:
        a0, a1 = pin_named("U8", "A0"), pin_named("U8", "A1")
        straps[f"ADS1119 A0 (U8.{a0})"] = net_of("U8", a0)
        straps[f"ADS1119 A1 (U8.{a1})"] = net_of("U8", a1)
        if net_of("U8", a0) != "GND" or net_of("U8", a1) != "GND":
            raise SystemExit(f"ADS1119 address strapping moved: {straps}")
    if net_of("U10", add0) != "3V3D":
        raise SystemExit(f"TMP117 ADD0 strapping moved: {straps}")

    # --- the heater gate is a wired-OR with the TMP117 ALERT --------------
    if net_of("Q2", 1) != "HEATER_GATE" or net_of("U10", pin_named("U10", "ALERT")) != "HEATER_GATE":
        raise SystemExit("TMP117 ALERT is no longer wired to the heater gate")

    L = []
    a = L.append
    a("/* GENERATED by tools/gen_hw_contract.py from ../gen_sch.py - DO NOT EDIT. */")
    a("/*")
    a(" * The schematic generator is this board's source of truth. Every constant")
    a(" * here is derived from it, so a hardware change that rescales a divider or")
    a(" * moves a pin fails the build rather than silently rescaling telemetry.")
    a(" * Regenerate with: python3 tools/gen_hw_contract.py")
    a(" */")
    a("#ifndef O2P_HW_CONTRACT_H")
    a("#define O2P_HW_CONTRACT_H")
    a("")
    a("/* ---- STM32G071CBT7 LQFP-48 pin map (gen_sch.py MCU_NETS) ---- */")
    for pin in sorted(mcu):
        a(f'#define O2P_HW_PIN_{pin:02d}_NET "{mcu[pin]}"')
    a("")
    for net in sorted(by_net):
        a(f"#define O2P_HW_NET_{net}_PIN {by_net[net][0]}")
    a("")
    a("/* ---- Resistive dividers the firmware converts with ---- */")
    a("/* MCU ADC1_IN6 (PA6) <- +12V_SW: R26 %g / R27 %g */" % (r26, r27))
    a(f"#define O2P_HW_DIV_VIN_NUM   {r27:.0f}")
    a(f"#define O2P_HW_DIV_VIN_DEN   {r26 + r27:.0f}")
    a("/* MCU ADC1_IN7 (PA7) <- 3V3A: R24 %g / R25 %g */" % (r24, r25))
    a(f"#define O2P_HW_DIV_VA_NUM    {r25:.0f}")
    a(f"#define O2P_HW_DIV_VA_DEN    {r24 + r25:.0f}")
    a("/* MCU ADC1_IN4 (PA4) <- CELL_CE_DRV (U7 pin 14): R43 %g / R44 %g */" % (r43, r44))
    a(f"#define O2P_HW_DIV_CE_NUM    {r44:.0f}")
    a(f"#define O2P_HW_DIV_CE_DEN    {r43 + r44:.0f}")
    a("/* CE fault-current limit, in the loop; scales nothing, bounds the budget. */")
    a(f"#define O2P_HW_CE_SERIES_OHM {r42:.0f}")
    a("/* SNAS506 6.5 characterises A1's drive only over 300 mV <= VCE <= VS-300 mV.")
    a(" * Outside this the amplifier is simply not specified, so treat it as a")
    a(" * fault, not as a reading.  VS is 3V3A, whose WORST-CASE LOW corner is")
    a(" * 3234 mV (DESIGN.md), so the characterised ceiling is 2934 mV -- not the")
    a(" * 3000 mV this used to hard-code, which sat 66 mV outside the specified")
    a(" * range whenever the rail was at its low limit. */")
    a("#define O2P_HW_CE_COMPLIANCE_MIN_MV 300")
    a(f"#define O2P_HW_CE_COMPLIANCE_MAX_MV {3234 - 300}")
    a("/* No guard divider: the guard is driven from the RE follower U4B through")
    a(" * R40, so it tracks the real electrode instead of a 0.909 x VREF replica. */")
    a("")
    a("/* ---- Cell bias telemetry (ADS1119 AIN2/AIN3, differential) ---- */")
    a("/* CORRECTED 2026-09-04. The old note here claimed the bias step carries")
    a(" * +/-2 % of VREF, about +/-50 mV against a +/-10 mV cell window. That")
    a(" * misreads SNAS506I: the +/-2 % figure is Bias Programming RESOLUTION, not")
    a(" * accuracy. The accuracy parameter is VOS_RW, +/-1750 uV MAX at 24 % bias,")
    a(" * which is INSIDE the SGX window -- confirmed on the bench 2026-09-04 at")
    a(" * 597 mV measured against 598.56 mV commanded.")
    a(" * So this pair is not a trim aid and never was. It is an EXISTENCE check:")
    a(" * is the cell biased at all. On 2026-09-04 the LMP91000's control amplifier")
    a(" * A1 failed outright and no converter on the board could see it. Read")
    a(" * AIN2-AIN3 differentially, and compare against the COMMANDED bias with a")
    a(" * window -- a floating input converts cleanly and in range, so a clip check")
    a(" * does not catch it. */")
    a("#define O2P_HW_BIAS_ADC_CH_WE  2")
    a("#define O2P_HW_BIAS_ADC_CH_RE  3")
    a("")
    a("/* ---- VREF: U15 AZ431B 2.5 V shunt reference, NOT adjustable ---- */")
    a("/* There is no trimmer. Firmware verifies the reference is within its own")
    a(" * guaranteed window and reports the measured cell bias separately; it can")
    a(" * neither set VREF nor correct the bias by moving it. */")
    a(f"#define O2P_HW_VREF_MIN_MV     {vref_min_mv:.0f}")
    a(f"#define O2P_HW_VREF_MAX_MV     {vref_max_mv:.0f}")
    a(f"#define O2P_HW_VREF_TARGET_MV  {vref_target_mv:.0f}")
    a("")
    a("/* ---- Membrane-ring heater ---- */")
    a("/* Main-board heater: RH1||RH2, bench-confirmed 140 ohm / 1.02 W at 12 V.")
    a(" * A ring PCB, when it exists, PARALLELS these through J5 -- it does not")
    a(" * replace them, so this is the floor of the load, not the whole of it. */")
    a(f"#define O2P_HW_HEATER_OHM    {heater_ohm:.0f}")
    a(f"#define O2P_HW_HEATER_GATE_R_SERIES {r28:.0f}   /* R28, PA8 -> gate */")
    a(f"#define O2P_HW_HEATER_GATE_R_PULLDN {r29:.0f}   /* R29, passive default-off */")
    a("")
    a("/* ---- I2C addresses, fixed by the strapping asserted above ---- */")
    a("#define O2P_HW_I2C_ADDR_ADS1119  0x40")
    a("#define O2P_HW_I2C_ADDR_SHT45    0x44")
    a("#define O2P_HW_I2C_ADDR_LMP91000 0x48")
    a("#define O2P_HW_I2C_ADDR_TMP117   0x49")
    a("#define O2P_HW_I2C_ADDR_TMP117_EXT 0x4A")
    a("#define O2P_HW_I2C_ADDR_BMP390   0x76  /* DNP */")
    a("")
    a("#endif /* O2P_HW_CONTRACT_H */")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if src/hw_contract.h is stale")
    args = ap.parse_args()

    text = build(load_generator())
    if not args.check:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
        print(f"wrote {OUT}")
        return 0

    if not OUT.exists():
        print(f"hw contract missing: {OUT}", file=sys.stderr)
        return 1
    if OUT.read_text() != text:
        import difflib
        sys.stderr.write("".join(difflib.unified_diff(
            OUT.read_text().splitlines(True), text.splitlines(True),
            fromfile="src/hw_contract.h (checked in)",
            tofile="derived from gen_sch.py")))
        sys.stderr.write(
            "\nHardware contract is stale. The schematic changed under the "
            "firmware.\nRun: python3 tools/gen_hw_contract.py\n"
            "Then re-check every conversion that uses the changed value.\n")
        return 1
    print("hw contract: up to date with gen_sch.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
