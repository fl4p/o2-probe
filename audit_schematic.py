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
    "RS485_A": {"U5.6", "R2.1", "R4.1", "R5.2"},
    "RS485_B": {"U5.7", "R3.1", "R4.2", "R6.1"},
    "CELL_WE": {"U7.12", "U11.3", "TP1.1"},
    "CELL_RE": {"U7.13", "U11.2", "TP2.1"},
    "CELL_CE": {"U7.14", "U11.1", "TP3.1"},
    "VREF_TRIM": {"R31.2", "U7.11", "U8.7", "TP4.1", "R34.1"},
    "ADC_VREF_MON": {"U8.8", "R36.2", "C29.1"},
    "ADC_AFE_VOUT": {"U8.9", "R33.2", "C28.1", "R39.1"},
    "ADC_VA_MON": {"U8.5", "R37.2", "C30.1"},
    "ADC_VIN_MON": {"U8.4", "R38.2", "C31.1"},
    "VREF_WIPER": {"RV1.2", "RV1.3", "R21.1", "C9.1", "U4.3"},
    "SWDIO": {"U6.35", "J3.2"},
    "SWCLK_BOOT0": {"U6.36", "J3.4", "J4.1", "R9.1"},
    "BUCK_BST": {"U1.6", "C2.1"},
    "BUCK_SW": {"U1.5", "C2.2", "L1.1"},
    "VREF_BUF": {"U4.1", "U4.2", "R31.1"},
    "+5V_ANALOG": {"R32.2", "C7.1", "C27.1", "U3.1", "U3.3"},
}
for name, wanted in required.items():
    actual = nets.get(name, set())
    missing = sorted(wanted - actual)
    if missing:
        errors.append(f"{name} missing: {', '.join(missing)}")

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
