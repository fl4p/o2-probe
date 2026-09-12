#!/usr/bin/env python3
"""Independent connectivity audit for the generated O2 probe schematic."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SCH = ROOT / "o2-probe.kicad_sch"
XML = ROOT / "o2-probe.xml"
REPORT = ROOT / "schematic-audit.rpt"
KICAD = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

subprocess.run(
    [KICAD, "sch", "export", "netlist", "--format", "kicadxml", "-o", str(XML), str(SCH)],
    check=True,
)
root = ET.parse(XML).getroot()

components = root.findall("./components/comp")
refs = [c.attrib.get("ref", "") for c in components]
errors: list[str] = []
if len(refs) != len(set(refs)):
    errors.append("duplicate component references")
bad_refs = sorted(r for r in refs if not re.search(r"\d$", r) and not r.startswith("#FLG"))
if bad_refs:
    errors.append(f"references without numeric suffix: {', '.join(bad_refs)}")

# Semantic symbol inventory: a clean netlist is not sufficient if a typed
# component was rendered as a generic placeholder.  KiCad's ERC separately
# verifies that each embedded standard symbol matches its library source.
for comp in components:
    ref = comp.attrib.get("ref", "")
    source = comp.find("libsource")
    actual = (source.attrib.get("lib", ""), source.attrib.get("part", "")) if source is not None else ("", "")
    expected = None
    if ref.startswith("RV"):
        expected = ("Device", "R_Potentiometer")
    elif ref.startswith("DZ") or ref == "D1":
        expected = ("Device", "D_Zener")
    elif ref.startswith("R"):
        expected = ("Device", "R")
    elif ref.startswith("C"):
        expected = ("Device", "C")
    elif ref.startswith("F"):
        expected = ("Device", "Polyfuse")
    elif ref.startswith("L"):
        expected = ("Device", "L")
    elif ref == "Q1":
        expected = ("Transistor_FET", "Q_PMOS_GSD")
    elif ref == "Q2":
        expected = ("Transistor_FET", "Q_NMOS_GSD")
    elif ref.startswith("TP"):
        expected = ("Connector", "TestPoint")
    elif ref in ("J103", "J104", "J105", "J106"):
        expected = ("o2-probe", "WIRE_LAND")
    elif ref in ("J101", "J102", "J103", "J104"):
        expected = ("Connector_Generic", "Conn_01x01")
    if expected is not None and actual != expected:
        errors.append(f"{ref} uses symbol {actual[0]}:{actual[1]}, expected {expected[0]}:{expected[1]}")

nets: dict[str, set[str]] = {}
pin_to_net: dict[str, str] = {}
for net in root.findall("./nets/net"):
    name = net.attrib["name"].removeprefix("/")
    nodes = {f'{n.attrib["ref"]}.{n.attrib["pin"]}' for n in net.findall("node")}
    nets[name] = nodes
    for node in nodes:
        if node in pin_to_net:
            errors.append(f"{node} appears in both {pin_to_net[node]} and {name}")
        pin_to_net[node] = name

required = {
    "+12V_RAW": {"J101.1", "F1.1"},
    "RS485_A_CABLE": {"J103.1", "R2.2", "D2.1"},
    "RS485_B_CABLE": {"J104.1", "R3.2", "D2.2"},
    # R5/R6, the 680R DNP fail-safe bias pair, are deleted: TI SLLSEY3E 9.3 and
    # 10.2.1.4 give the THVD1410 receiver open/short/idle failsafe without
    # external bias, and it holds per-node on a multidrop bus (10.2.1.3, up to
    # 256 of these 1/8-unit-load receivers). R4, the 120R end-of-bus
    # termination option, stays -- failsafe is not termination.
    "RS485_A": {"U5.6", "R2.1", "R4.1"},
    "RS485_B": {"U5.7", "R3.1", "R4.2"},
    "CELL_WE": {"U7.12", "U11.3", "TP1.1"},
    # CELL_RE deliberately has no exposed test point: a test-point solder-mask
    # aperture would violate the wet-leakage control for this high-impedance net.
    "CELL_RE": {"U7.13", "U11.2", "U4.5"},
    # CE now reaches the cell through R42's fault-current limit, so the driven
    # pin and the electrode are different nets. Watch which one things hang on:
    # the compliance monitor must sit on the PIN (SNAS506 6.5 specifies A1's
    # drive at the device pin), the clamp and the cell on the ELECTRODE.
    "CELL_CE_DRV": {"U7.14", "R42.1", "R43.1"},
    "CELL_CE": {"R42.2", "U11.1", "TP3.1", "D7.1"},
    "CE_MON": {"R43.2", "R44.1", "C34.1", "U6.15"},
    # REV B 2026-09-12: VREF_TRIM is now the REF3425 output itself (force and
    # sense both land on it), not the far side of R31.
    # REV B 2026-09-12: the ADS1119 (U8) is DELETED and every analog channel
    # converts on the MCU's own SAR.  U6.16 (PA5) joining this net IS the
    # decision -- VREF_TRIM is measured DIRECTLY, with no divider, so R34/R35 and
    # the /VREF_MON_RAW and /ADC_VREF_MON nets are gone.  An exact set, so
    # re-adding a divider leg here fails this audit rather than passing quietly.
    "VREF_TRIM": {"U15.5", "U15.6", "C10.1", "U7.11", "TP4.1", "U6.5", "C26.1"},
    "ADC_AFE_VOUT": {"U6.20", "R33.2", "C28.1", "R39.1"},
    # Cell bias telemetry, now on PA0/PA1 -- adjacent FT_a pins, matched legs.
    "ADC_WE_BUF": {"U6.11", "R37.2", "C30.1"},
    "ADC_RE_BUF": {"U6.12", "R38.2", "C31.1"},
    # Electrometer followers. The cell electrodes reach the ADC only through
    # these buffers; a direct ADC tap on CELL_RE is the failure this guards.
    "WE_BUF": {"U4.1", "U4.2", "R37.1"},
    "RE_BUF": {"U4.6", "U4.7", "R38.1", "R40.1"},
    "GUARD_REPLICA": {"R40.2", "TP5.1"},
    "SWDIO": {"U6.35", "J3.2"},
    "SWCLK_BOOT0": {"U6.36", "J3.4", "R9.1"},
    # REV B: the two THVD1410 enables are on SEPARATE nets and separate GPIOs.
    # /RE (U5.2) is active low with a 2 MOhm internal pull-up, DE (U5.3) is
    # active high with a 2 MOhm internal pull-down; tying them together, as Rev
    # A did, made the part's 0.1 uA standby state uncommandable. Each keeps its
    # own 47k pull-down so BOTH defaults are passive: R7 -> driver off (the
    # bus-jam release path main.c leans on), R45 -> receiver ON (what keeps a
    # probe in the bootloader reachable).
    "RS485_DE": {"U5.3", "R7.1", "U6.30"},
    "RS485_RE": {"U5.2", "R45.1", "U6.31"},
    "VA_MON": {"R24.2", "R25.1", "C33.1", "U6.18"},
    # D8.1 is the CATHODE of the negative-injection clamp (Device:D_Schottky
    # pin 1 = K). Naming the cathode here, on an EXACT net, is a second and
    # independent check of D8's polarity: if the diode is flipped, D8.2 lands on
    # VIN_MON instead and this audit reports both a missing D8.1 and an
    # unexpected D8.2. gen_sch.py's verify() checks the same thing from the
    # generator's model; this one checks the EXPORTED NETLIST, which is the
    # artifact the PCB is actually built from.
    "VIN_MON": {"R26.2", "R27.1", "C32.1", "U6.17", "D8.1"},
    "BUCK_BST": {"U1.6", "C2.1"},
    "BUCK_SW": {"U1.5", "C2.2", "L1.1"},
    # Main-board heaters remain; the optional Rev C ring branch is absent.
    "+12V_SW": {"RH1.1", "RH2.1"},
    "HEATER_LOW": {"Q2.3", "RH1.2", "RH2.2"},
    # REV B 2026-09-12, Path A: no 5 V rail, no LDOs, no shunt. The buck feeds
    # 3V3D directly; the AFE hangs off it through R32; the reference is its own
    # part. REF3425 is KELVIN-sensed, so GND_F/GND_S and OUT_F/OUT_S must BOTH
    # land -- a wiring slip that drops the sense leg would otherwise pass.
    "3V3D": {"U1.1", "L1.2", "C3.1", "C4.1", "R32.1", "U15.3", "U15.4"},
    "3V3A": {"R32.2", "C7.1", "C8.1"},
    "BUCK_SW": {"U1.5", "L1.1", "C2.2"},
    "BUCK_BST": {"U1.6", "C2.1"},
}
# EVERY pin the generator assigned must actually appear on that net in the
# EXPORTED netlist. The table below only checks the nets someone thought to
# list, which is why four bypass capacitors sat with their ground pins floating
# on 2026-09-12: ERC passed (their neighbours drove the net), this audit passed
# (no GND row), and only a pin-by-pin comparison found them.
import importlib.util as _il, io as _io, contextlib as _cl, sys as _sys
_spec = _il.spec_from_file_location("_gs", str(Path(__file__).with_name("gen_sch.py")))
_gs = _il.module_from_spec(_spec)
_argv, _sys.argv = _sys.argv, ["gen_sch.py"]
with _cl.redirect_stdout(_io.StringIO()):
    try:
        _spec.loader.exec_module(_gs)
    except SystemExit:
        pass
_sys.argv = _argv
_floating = []
for (_r, _p), _n in _gs.ASSIGNED.items():
    if _r.startswith("#") or _n == "(NC)":
        continue
    # nets maps net -> {"REF.PIN"} strings, not tuples. The first version of
    # this check compared tuples and "found" all 253 pins floating: a guard
    # reporting its own model again. Calibrate against a KNOWN-GOOD pin before
    # trusting a guard that suddenly fails everything.
    if f"{_r}.{_p}" not in nets.get(_n, set()):
        _floating.append(f"{_r}.{_p} should be on {_n}")
errors.extend(f"not connected in the exported netlist: {_f}"
              for _f in sorted(_floating))

# EXACT nets: both directions are checked, so an EXTRA pin is an error too.
#
# Added 2026-09-12 because several comments in `required` above claimed this
# behaviour ("An exact set, so re-adding a divider leg here fails this audit
# rather than passing quietly") while the loop below only ever computed
# `wanted - actual`.  Extras were accepted silently, so the audit would have
# PASSED a re-added VREF_TRIM divider leg -- the one failure the comment said it
# existed to catch.  A guard that overstates itself is worse than no guard,
# because the comment is what the next reader trusts instead of the code.
#
# Kept to the nets whose membership is genuinely closed and load-bearing: the
# reference, the three analog channels that carry oxygen, the electrometer
# outputs, and the two supply monitors.  Everything else stays subset-checked,
# which is at least honest about being a floor rather than a fence.
EXACT = {
    "VREF_TRIM", "ADC_AFE_VOUT", "ADC_WE_BUF", "ADC_RE_BUF",
    "VA_MON", "VIN_MON", "WE_BUF", "RE_BUF",
}

for name, wanted in required.items():
    actual = nets.get(name, set())
    missing = sorted(wanted - actual)
    if missing:
        errors.append(f"{name} missing: {', '.join(missing)}")
    if name in EXACT:
        extra = sorted(actual - wanted)
        if extra:
            errors.append(f"{name} has unexpected pins: {', '.join(extra)}")

expected_mcu_pin_nets = {
    "U6.17": "VIN_MON",
    "U6.18": "VA_MON",
    "U6.30": "RS485_DE",
    "U6.31": "RS485_RE",   # PC7, DS12232 Rev 1 Table 12 LQFP48 column
    "U6.15": "CE_MON",
    "U6.11": "ADC_WE_BUF",   # PA0 / ADC_IN0, FT_a
    "U6.12": "ADC_RE_BUF",   # PA1 / ADC_IN1, FT_a
    # ADOPTED 2026-09-12: VREF+ is the REF3425, and PA5 went back to the pool
    # because converting the reference against itself saturates at 4095.
    "U6.5":  "VREF_TRIM",    # VREF+ -- the ADC full scale. NOT 3V3D.
    "U6.16": "unconnected-(U6-PA5-Pad16)",
    "U6.20": "ADC_AFE_VOUT", # PB1 / ADC_IN9, FT_a -- freed by deleting ADC_DRDY
}
for node, expected_net in expected_mcu_pin_nets.items():
    if pin_to_net.get(node) != expected_net:
        errors.append(f"{node} is on {pin_to_net.get(node)}, expected {expected_net}")

for node in ("J104.1", "D2.2", "J103.1", "D2.1", "U11.1", "U11.2", "U11.3"):
    if pin_to_net.get(node) == "GND":
        errors.append(f"{node} unexpectedly shorted to GND")

lines = [
    "O2 probe schematic connectivity audit",
    f"components: {len(components)}",
    f"nets: {len(nets)}",
    f"result: {'FAIL' if errors else 'PASS'}",
]
lines.extend(f"ERROR: {e}" for e in errors)
REPORT.write_text("\n".join(lines) + "\n")
print(REPORT.read_text(), end="")
sys.exit(bool(errors))
