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
        expected = ("Device", "R" if ref == "F3" else "Polyfuse")
    elif ref.startswith("L"):
        expected = ("Device", "L")
    elif ref == "Q1":
        expected = ("Transistor_FET", "Q_PMOS_GSD")
    elif ref == "Q2":
        expected = ("Transistor_FET", "Q_NMOS_GSD")
    elif ref.startswith("TP"):
        expected = ("Connector", "TestPoint")
    elif ref == "J5":
        expected = ("o2-probe", "RING_PCB_FORK_TIP")
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
    "VREF_TRIM": {"R31.2", "U7.11", "U8.7", "TP4.1", "R34.1"},
    "ADC_VREF_MON": {"U8.8", "R36.2", "C29.1"},
    "ADC_AFE_VOUT": {"U8.9", "R33.2", "C28.1", "R39.1"},
    # Cell bias telemetry replaced the two rail monitors on the ADS1119, and both
    # legs must stay matched -- see gen_sch.py verify().
    "ADC_WE_BUF": {"U8.5", "R37.2", "C30.1"},
    "ADC_RE_BUF": {"U8.4", "R38.2", "C31.1"},
    # Electrometer followers. The cell electrodes reach the ADC only through
    # these buffers; a direct ADS1119 tap on CELL_RE is the failure this guards.
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
    "VIN_MON": {"R26.2", "R27.1", "C32.1", "U6.17"},
    "BUCK_BST": {"U1.6", "C2.1"},
    "BUCK_SW": {"U1.5", "C2.2", "L1.1"},
    # The heat source stays on this board (Fab, 2026-09-04): RH1/RH2 bridge
    # +12V_SW to HEATER_LOW, Q2 pulls it down, and J5 carries the same pair
    # forward so a ring PCB parallels the elements rather than replacing them.
    "+12V_SW": {"RH1.1", "RH2.1", "F3.1"},
    "HEATER_LOW": {"Q2.3", "J5.2", "RH1.2", "RH2.2"},
    "+12V_HTR": {"F3.2", "J5.1"},
    # AZ431 two-terminal shunt: REF (pin 1) strapped to the cathode (pin 2).
    # If the pin-number remap in gen_sch.py ever fails to apply, the exported
    # netlist lands the TI numbering here and this check fires.
    "VREF_SHUNT": {"U15.1", "U15.2", "R41.2", "C9.1", "R31.1"},
    "+5V_ANALOG": {"R32.2", "C7.1", "C27.1", "U3.1", "U3.3"},
}
for name, wanted in required.items():
    actual = nets.get(name, set())
    missing = sorted(wanted - actual)
    if missing:
        errors.append(f"{name} missing: {', '.join(missing)}")

expected_mcu_pin_nets = {
    "U6.17": "VIN_MON",
    "U6.18": "VA_MON",
    "U6.30": "RS485_DE",
    "U6.31": "RS485_RE",   # PC7, DS12232 Rev 1 Table 12 LQFP48 column
    "U6.15": "CE_MON",
    "U6.11": "unconnected-(U6-PA0-Pad11)",
    "U6.12": "unconnected-(U6-PA1-Pad12)",
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
