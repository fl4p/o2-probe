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
REQUIRED_NETS = {
    "VA_MON", "AFE_MENB", "ADC_DRDY", "HEATER_PWM",
    "RS485_TX", "RS485_RX", "RS485_DE", "I2C_SCL", "I2C_SDA",
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

    Accepts '82k 1%', '280R 1W', '2k 10-turn', '100k'. Raises on anything it
    does not fully understand rather than guessing - a misparsed divider leg
    is exactly the silent rescale this file exists to prevent.
    """
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([kKmMrR]?)", value)
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
    # ADS1119 AIN3: +12V_SW through R26 (top) / R27 (bottom).
    r26, r27 = val("R26"), val("R27")
    # ADS1119 AIN2 and MCU ADC1_IN7: 3V3A through R24 / R25.
    r24, r25 = val("R24"), val("R25")
    # ADS1119 AIN1: VREF_TRIM through R34 / R35.
    r34, r35 = val("R34"), val("R35")
    # Driven guard replica around CELL_RE: VREF_TRIM through R22 / R23.
    r22, r23 = val("R22"), val("R23")

    # --- VREF trim network: R20 + RV1 (rheostat) + R21 to GND -------------
    r20, r21, rv1 = val("R20"), val("R21"), val("RV1")
    vdda_mv = 3300.0
    vref_max_mv = vdda_mv * r21 / (r20 + r21)               # RV1 at 0 ohm
    vref_min_mv = vdda_mv * r21 / (r20 + rv1 + r21)         # RV1 at full scale
    # Wiper position that lands on the 2.500 V target the generator asserts.
    vref_target_mv = 2500.0
    rv1_at_target = vdda_mv * r21 / vref_target_mv - r20 - r21

    # --- heater -----------------------------------------------------------
    rh = 1.0 / (1.0 / val("RH1") + 1.0 / val("RH2"))
    r28, r29 = val("R28"), val("R29")

    # --- strapping that fixes the I2C addresses ---------------------------
    # These are the ADDRESS STRAP pins, and getting the numbers right matters:
    # this check used to read U8.2/U8.3 (DGND/AGND) and U10.5 (V+), which are
    # not strap pins at all. It passed only because those power pins happen to
    # sit on the same nets the straps do, so it would have gone on passing
    # while a real strap change silently invalidated the hard-coded 0x40/0x49
    # addresses below. Per gen_sch.py's own symbol definitions, ADS1119 A0/A1
    # are pins 15/16 and TMP117 ADD0 is pin 4. Found by the fifth review,
    # 2026-09-08; the strapping itself was and is correct.
    straps = {
        "ADS1119 A0 (U8.15)": net_of("U8", 15),
        "ADS1119 A1 (U8.16)": net_of("U8", 16),
        "TMP117 ADD0 (U10.4)": net_of("U10", 4),
    }
    if straps["ADS1119 A0 (U8.15)"] != "GND" or straps["ADS1119 A1 (U8.16)"] != "GND":
        raise SystemExit(f"ADS1119 address strapping moved: {straps}")
    if straps["TMP117 ADD0 (U10.4)"] != "3V3D":
        raise SystemExit(f"TMP117 ADD0 strapping moved: {straps}")

    # --- the heater gate is a wired-OR with the TMP117 ALERT --------------
    if net_of("Q2", 1) != "HEATER_GATE" or net_of("U10", 3) != "HEATER_GATE":
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
    a("/* ADS1119 AIN3 <- +12V_SW: R26 %g / R27 %g */" % (r26, r27))
    a(f"#define O2P_HW_DIV_VIN_NUM   {r27:.0f}")
    a(f"#define O2P_HW_DIV_VIN_DEN   {r26 + r27:.0f}")
    a("/* ADS1119 AIN2 and MCU ADC1_IN7 <- 3V3A: R24 %g / R25 %g */" % (r24, r25))
    a(f"#define O2P_HW_DIV_VA_NUM    {r25:.0f}")
    a(f"#define O2P_HW_DIV_VA_DEN    {r24 + r25:.0f}")
    a("/* ADS1119 AIN1 <- VREF_TRIM: R34 %g / R35 %g */" % (r34, r35))
    a(f"#define O2P_HW_DIV_VREF_NUM  {r35:.0f}")
    a(f"#define O2P_HW_DIV_VREF_DEN  {r34 + r35:.0f}")
    a("/* Driven guard replica of CELL_RE: R22 %g / R23 %g */" % (r22, r23))
    a(f"#define O2P_HW_DIV_GUARD_NUM {r23:.0f}")
    a(f"#define O2P_HW_DIV_GUARD_DEN {r22 + r23:.0f}")
    a("")
    a("/* ---- VREF_TRIM adjustment range (R20 + RV1 rheostat + R21, 3V3A) ---- */")
    a("/* Bench trim target is 2.500 V: the LMP91000's 24 % bias step must land on")
    a(" * the SGX cell's -600 +/- 10 mV window, so VREF is a MANUAL bench step that")
    a(" * firmware can only verify, never set. */")
    a(f"#define O2P_HW_VREF_MIN_MV     {vref_min_mv:.0f}")
    a(f"#define O2P_HW_VREF_MAX_MV     {vref_max_mv:.0f}")
    a(f"#define O2P_HW_VREF_TARGET_MV  {vref_target_mv:.0f}")
    a(f"/* 2.500 V lands at RV1 = {rv1_at_target:.0f} ohm of {rv1:.0f} ohm travel */")
    a("")
    a("/* ---- Membrane-ring heater ---- */")
    a(f"#define O2P_HW_HEATER_OHM      {rh:.0f}   /* RH1 || RH2 */")
    a(f"#define O2P_HW_HEATER_GATE_R_SERIES {r28:.0f}   /* R28, PA8 -> gate */")
    a(f"#define O2P_HW_HEATER_GATE_R_PULLDN {r29:.0f}   /* R29, passive default-off */")
    a("")
    a("/* ---- I2C addresses, fixed by the strapping asserted above ---- */")
    a("#define O2P_HW_I2C_ADDR_ADS1119  0x40")
    a("#define O2P_HW_I2C_ADDR_SHT45    0x44")
    a("#define O2P_HW_I2C_ADDR_LMP91000 0x48")
    a("#define O2P_HW_I2C_ADDR_TMP117   0x49")
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
