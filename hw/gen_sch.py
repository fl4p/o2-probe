#!/usr/bin/env python3
"""Generate the Rev-B O2 probe schematic and its project symbol library.

The generator is the source of truth.  The emitted schematic connects functional subcircuits with explicit wires,
junctions, and net stubs for human readability,
while an audit below proves that every package pin is either assigned exactly
one net or explicitly marked no-connect.
"""

from __future__ import annotations

import hashlib
import math
import re
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "o2-probe"
OUT = HERE / f"{NAME}.kicad_sch"
LIB_OUT = HERE / "lib" / f"{NAME}.kicad_sym"
GRID = 1.27


def uid(*parts: object) -> str:
    h = hashlib.sha1((NAME + "/" + "/".join(map(str, parts))).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-5{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", r"\n")


SYMS: dict[str, dict] = {}
INST: dict[str, dict] = {}
WIRES: list[tuple[float, float, float, float]] = []
JUNCTIONS: set[tuple[float, float]] = set()
LABELS: list[tuple[str, float, float, int]] = []


def snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 6)


def wire(x1: float, y1: float, x2: float, y2: float) -> None:
    x1, y1, x2, y2 = snap(x1), snap(y1), snap(x2), snap(y2)
    if x1 == x2 and y1 == y2:
        return
    if x1 != x2 and y1 != y2:
        raise ValueError(f"Non-orthogonal wire: ({x1}, {y1}) to ({x2}, {y2})")
    if (x1, y1) > (x2, y2):
        x1, y1, x2, y2 = x2, y2, x1, y1
    WIRES.append((x1, y1, x2, y2))


def wire_path(pts: list[tuple[float, float]]) -> None:
    for pt1, pt2 in zip(pts[:-1], pts[1:]):
        x1, y1 = snap(pt1[0]), snap(pt1[1])
        x2, y2 = snap(pt2[0]), snap(pt2[1])
        if x1 != x2 and y1 != y2:
            wire(x1, y1, x2, y1)
            wire(x2, y1, x2, y2)
        else:
            wire(x1, y1, x2, y2)


def junc(pt: tuple[float, float]) -> None:
    JUNCTIONS.add((snap(pt[0]), snap(pt[1])))


def pin_xy(ref: str, pin_id: str | int) -> tuple[float, float]:
    pos = pin_pos(ref, str(pin_id))
    return (snap(pos[0]), snap(pos[1]))
NOCONN: list[tuple[float, float]] = []
ASSIGNED: dict[tuple[str, str], str] = {}


def symbol(name: str, pins: list[tuple[str, str, str]], ref_prefix="U", description="", pitch=2.54) -> str:
    """Register a simple rectangular symbol.

    pins are (number, name, electrical_type).  Odd list entries are placed on
    the left and even entries on the right.  Pin geometry is retained for the
    instance connector/audit code.
    """
    lib_id = f"o2-probe:{name}"
    left = pins[::2]
    right = pins[1::2]
    rows = max(len(left), len(right), 2)
    half_h = max(5.08, (rows - 1) * pitch / 2 + 2.54)
    geom = {}
    for side, entries in (("L", left), ("R", right)):
        for i, (num, pin_name, etype) in enumerate(entries):
            y = (len(entries) - 1) * pitch / 2 - i * pitch
            x, angle = (-7.62, 0) if side == "L" else (7.62, 180)
            geom[str(num)] = (x, y, angle, pin_name, etype)
    SYMS[lib_id] = {
        "name": name, "pins": pins, "geom": geom, "ref_prefix": ref_prefix,
        "half_h": half_h, "half_w": 5.08, "pin_len": 2.54,
        "description": description,
    }
    return lib_id


CONN4 = symbol("CONN_01x04", [(str(i), f"Pin_{i}", "passive") for i in range(1, 5)], "J", pitch=5.08)
CONN6 = symbol("CONN_02x03", [(str(i), f"Pin_{i}", "passive") for i in range(1, 7)], "J", pitch=5.08)
CONN8 = symbol("CONN_02x04", [(str(i), f"Pin_{i}", "passive") for i in range(1, 9)], "J", pitch=5.08)

# Connector pins are drawn on one side in physical pin order.  Besides reading
# like the cable pinout, this prevents long adjacent right-side labels from
# sharing the same connection stroke in KiCad's label renderer.
for _lid in (CONN4, CONN6, CONN8):
    _pins = SYMS[_lid]["pins"]
    for _i, (_num, _name, _etype) in enumerate(_pins):
        SYMS[_lid]["geom"][_num] = (-7.62, (len(_pins)-1)*2.54 - _i*5.08, 0, _name, _etype)
HEATED_RING = symbol(
    "HEATED_MEMBRANE_RING", [("1", "HEATER_LOW", "passive")], "J",
    description="Manual-solder metal membrane carrier and heat spreader",
)
CABLE4 = symbol("FARM_CABLE_4", [(str(i), f"Wire_{i}", "passive") for i in range(1,5)], "J", pitch=5.08)
SYMS[CABLE4]["geom"] = {
    "1": (-7.62, 3.81, 0, "Wire_1", "passive"),
    "2": (-7.62, 1.27, 0, "Wire_2", "passive"),
    "3": (-7.62,-1.27, 0, "Wire_3", "passive"),
    "4": (-7.62,-3.81, 0, "Wire_4", "passive"),
}
SYMS[CABLE4]["half_w"] = 2.54
SYMS[CABLE4]["pin_len"] = 5.08
FET_PINS = [("1", "G", "input"), ("2", "S", "passive"), ("3", "D", "passive")]


def _balanced_symbol_block(text: str, symbol_name: str) -> str:
    marker = f'\n\t(symbol "{symbol_name}"'
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"symbol {symbol_name!r} not found")
    start += 2
    depth = 0
    quoted = False
    escaped = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    raise ValueError(f"unterminated symbol {symbol_name!r}")


def _symbol_library_path(filename: str) -> Path:
    roots = []
    if os.environ.get("KICAD_SYMBOL_DIR"):
        roots.append(Path(os.environ["KICAD_SYMBOL_DIR"]))
    roots.extend([
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
        Path("/usr/share/kicad/symbols"),
        Path("/usr/local/share/kicad/symbols"),
    ])
    for root in roots:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"cannot locate authoritative KiCad symbol library {filename}")


def authoritative_symbol(lib_id: str, library_file: str, symbol_name: str,
                         pins: list[tuple[str, str, str]],
                         geom: dict[str, tuple[float, float, int, str, str]], *,
                         ref_prefix: str, half_w: float, half_h: float,
                         pin_len: float) -> str:
    source_path = _symbol_library_path(library_file)
    source = _balanced_symbol_block(source_path.read_text(), symbol_name)
    source = source.replace(f'(symbol "{symbol_name}"', f'(symbol "{lib_id}"', 1)
    SYMS[lib_id] = {
        "name": symbol_name, "pins": pins, "geom": geom,
        "ref_prefix": ref_prefix, "half_h": half_h, "half_w": half_w,
        "pin_len": pin_len, "description": f"Authoritative {lib_id}",
        "source_block": source, "source_path": str(source_path),
    }
    return lib_id


# Embed the exact installed KiCad library definitions.  The explicit geometry
# mirrors those definitions and remains the single source used by connection
# placement and audits.
RES2 = authoritative_symbol(
    "Device:R", "Device.kicad_sym", "R",
    [("1", "", "passive"), ("2", "", "passive")],
    {"1": (0, 3.81, 270, "", "passive"),
     "2": (0, -3.81, 90, "", "passive")},
    ref_prefix="R", half_w=1.016, half_h=2.54, pin_len=1.27)
CAP2 = authoritative_symbol(
    "Device:C", "Device.kicad_sym", "C",
    [("1", "", "passive"), ("2", "", "passive")],
    {"1": (0, 3.81, 270, "", "passive"),
     "2": (0, -3.81, 90, "", "passive")},
    ref_prefix="C", half_w=2.032, half_h=0.762, pin_len=2.794)
POLYFUSE2 = authoritative_symbol(
    "Device:Polyfuse", "Device.kicad_sym", "Polyfuse",
    [("1", "", "passive"), ("2", "", "passive")],
    {"1": (0, 3.81, 270, "", "passive"),
     "2": (0, -3.81, 90, "", "passive")},
    ref_prefix="F", half_w=1.016, half_h=2.54, pin_len=1.27)
INDUCTOR2 = authoritative_symbol(
    "Device:L", "Device.kicad_sym", "L",
    [("1", "1", "passive"), ("2", "2", "passive")],
    {"1": (0, 3.81, 270, "1", "passive"),
     "2": (0, -3.81, 90, "2", "passive")},
    ref_prefix="L", half_w=1.27, half_h=2.54, pin_len=1.27)
ZENER2 = authoritative_symbol(
    "Device:D_Zener", "Device.kicad_sym", "D_Zener",
    [("1", "K", "passive"), ("2", "A", "passive")],
    {"1": (-3.81, 0, 0, "K", "passive"),
     "2": (3.81, 0, 180, "A", "passive")},
    ref_prefix="D", half_w=1.778, half_h=1.27, pin_len=2.54)
# KiCad's Device:D_TVS is the bidirectional graphic.  The fitted SMBJ15A is
# unidirectional, so its correct conventional graphic is the Zener form.
TVS2 = ZENER2
# The series reverse-polarity Schottky gets the Schottky GRAPHIC, not a zener's.
# Pin 1 is the cathode and pin 2 the anode, matching every other two-terminal
# diode on this sheet, so the direction of a series part is readable rather than
# inferred from its net names.
# Ground stops being TEXT.  52 of the sheet's labels said "GND", which is the
# definition of label-soup: the reader has to match strings to see a connection
# that a conventional graphic states at a glance.  KiCad's own power symbol has
# its connection point at the origin (pin at 0,0, length 0), so it drops
# straight onto a pin with no stub.
RAILSYM = authoritative_symbol(
    "power:+3V3", "power.kicad_sym", "+3V3",
    [("1", "+3V3", "power_in")], {"1": (0.0, 0.0, 90, "+3V3", "power_in")},
    ref_prefix="#PWR", half_w=1.6, half_h=1.6, pin_len=0.0)
GNDSYM = authoritative_symbol(
    "power:GND", "power.kicad_sym", "GND",
    [("1", "GND", "power_in")], {"1": (0.0, 0.0, 270, "GND", "power_in")},
    ref_prefix="#PWR", half_w=1.6, half_h=1.6, pin_len=0.0)

SCHOTTKY2 = authoritative_symbol(
    "Device:D_Schottky", "Device.kicad_sym", "D_Schottky",
    [("1", "K", "passive"), ("2", "A", "passive")],
    {"1": (-3.81, 0, 0, "K", "passive"),
     "2": (3.81, 0, 180, "A", "passive")},
    ref_prefix="D", half_w=1.778, half_h=1.27, pin_len=2.54)
POT = authoritative_symbol(
    "Device:R_Potentiometer", "Device.kicad_sym", "R_Potentiometer",
    [("1", "1", "passive"), ("2", "2", "passive"), ("3", "3", "passive")],
    {"1": (0, 3.81, 270, "1", "passive"),
     "2": (3.81, 0, 180, "2", "passive"),
     "3": (0, -3.81, 90, "3", "passive")},
    ref_prefix="RV", half_w=2.54, half_h=2.54, pin_len=1.27)
PMOS = authoritative_symbol(
    "Transistor_FET:Q_PMOS_GSD", "Transistor_FET.kicad_sym", "Q_PMOS_GSD",
    FET_PINS,
    {"1": (-5.08, 0, 0, "G", "input"),
     "2": (2.54, -5.08, 90, "S", "passive"),
     "3": (2.54, 5.08, 270, "D", "passive")},
    ref_prefix="Q", half_w=4.445, half_h=5.08, pin_len=2.54)
NMOS = authoritative_symbol(
    "Transistor_FET:Q_NMOS_GSD", "Transistor_FET.kicad_sym", "Q_NMOS_GSD",
    FET_PINS,
    {"1": (-5.08, 0, 0, "G", "input"),
     "2": (2.54, -5.08, 90, "S", "passive"),
     "3": (2.54, 5.08, 270, "D", "passive")},
    ref_prefix="Q", half_w=4.445, half_h=5.08, pin_len=2.54)
TESTPOINT = authoritative_symbol(
    "Connector:TestPoint", "Connector.kicad_sym", "TestPoint",
    [("1", "1", "passive")], {"1": (0, 0, 90, "1", "passive")},
    ref_prefix="TP", half_w=1.27, half_h=2.54, pin_len=2.54)
PWRFLAG = authoritative_symbol(
    "power:PWR_FLAG", "power.kicad_sym", "PWR_FLAG",
    [("1", "", "power_out")], {"1": (0, 0, 90, "", "power_out")},
    ref_prefix="#FLG", half_w=1.016, half_h=2.54, pin_len=0)
CONN1 = authoritative_symbol(
    "Connector_Generic:Conn_01x01", "Connector_Generic.kicad_sym", "Conn_01x01",
    [("1", "Pin_1", "passive")], {"1": (-5.08, 0, 0, "Pin_1", "passive")},
    ref_prefix="J", half_w=1.27, half_h=1.27, pin_len=3.81)
# Same conventional single-pin graphic, with a project identity and the exact
# accepted solder-wire land patterns. These are solder wires, not headers.
WIRE_LAND = authoritative_symbol(
    "o2-probe:WIRE_LAND", "Connector_Generic.kicad_sym", "Conn_01x01",
    [("1", "Pin_1", "passive")], {"1": (-5.08, 0, 0, "Pin_1", "passive")},
    ref_prefix="J", half_w=1.27, half_h=1.27, pin_len=3.81)
SYMS[WIRE_LAND]["name"] = "WIRE_LAND"
SYMS[WIRE_LAND]["source_block"] = SYMS[WIRE_LAND]["source_block"].replace(
    '(symbol "Conn_01x01_', '(symbol "WIRE_LAND_').replace(
    '"Connector*:*_1x??_*"',
    '"o2-probe:SolderWireNoRelief_J105 o2-probe:SolderWireNoRelief_J106 o2-probe:SolderWire_RaisedRelief_1x01"')
# Diodes/BCD AZ431-A in the N (SOT-23) package is pinned 1 REF, 2 CATHODE,
# 3 ANODE -- AZ431-A datasheet Rev 3.4, "Pin Configuration", N Package figure.
# NO KiCad TL431 variant carries that map: TL431DBZ is 1 K / 2 REF / 3 A, and
# TL431LP and TL431KTP are 1 REF / 2 A / 3 K. Dropping in TL431DBZ would have
# silently transposed REF and the cathode. So the shunt-regulator GRAPHIC is
# taken from TL431DBZ and only its pin NUMBERS are remapped onto the package we
# actually buy; pin positions are untouched, so the drawing stays correct.
# verify() pins the emitted result, and audit_schematic.py re-reads it from the
# exported netlist rather than from this table.
# The lib_id is deliberately NOT "Reference_Voltage:TL431DBZ". Renumbering the
# pins makes this no longer that library's symbol, and claiming otherwise earns
# a real ERC [lib_symbol_mismatch] -- KiCad compares the embedded copy against
# the system library and correctly objects. Naming it as a project symbol states
# the truth: a TL431 graphic carrying the Diodes AZ431 package pinout.
AZ431 = authoritative_symbol(
    "o2-probe:AZ431_SOT23", "Reference_Voltage.kicad_sym", "TL431DBZ",
    [("1", "REF", "passive"), ("2", "K", "passive"), ("3", "A", "passive")],
    {"1": (0, 2.54, 270, "REF", "passive"),
     "2": (2.54, 0, 180, "K", "passive"),
     "3": (-2.54, 0, 0, "A", "passive")},
    ref_prefix="U", half_w=2.54, half_h=2.54, pin_len=2.54)


def _remap_pin_numbers(lib_id: str, by_name: dict[str, str]) -> None:
    """Renumber an embedded library symbol's pins by pin NAME, in place.

    Raises unless each name matches exactly once, so a library revision that
    renames or duplicates a pin fails the build instead of silently emitting
    the donor package's numbering.
    """
    blk = SYMS[lib_id]["source_block"]
    for name, num in by_name.items():
        pat = re.compile(r'(\(name "' + re.escape(name) + r'"(?:.(?!\(pin ))*?\(number ")[^"]+(")', re.S)
        blk, hits = pat.subn(r'\g<1>' + num + r'\g<2>', blk)
        if hits != 1:
            raise ValueError(f"{lib_id}: pin name {name!r} matched {hits} times, expected 1")
    SYMS[lib_id]["source_block"] = blk


# KiCad requires a symbol's child units to be named "<symbol>_<unit>_<style>",
# so renaming the parent means renaming TL431DBZ_0_1 / _1_1 too. Without this
# the schematic fails to load outright rather than degrading quietly.
SYMS[AZ431]["source_block"] = SYMS[AZ431]["source_block"].replace(
    '"TL431DBZ_', '"AZ431_SOT23_')
# emit_library() renames each entry back to SYMS[k]["name"], so that must follow
# the children or the project library emits a parent/child name mismatch and
# fails to parse -- which surfaces as EVERY project symbol reporting a missing
# library, not as an error pointing at this one.
SYMS[AZ431]["name"] = "AZ431_SOT23"
if '"TL431DBZ_' in SYMS[AZ431]["source_block"]:
    raise ValueError("AZ431 child symbols still carry the donor name")
_remap_pin_numbers(AZ431, {"REF": "1", "K": "2", "A": "3"})


TVS3 = symbol("TVS_ARRAY_2CH", [("1", "IO1", "passive"), ("2", "IO2", "passive"), ("3", "GND", "passive")], "D")
SM712 = symbol("SM712", [("1", "LINE_A", "passive"), ("2", "LINE_B", "passive"), ("3", "GND", "passive")], "D",
               description="Littelfuse SM712-02HTG asymmetric RS-485 TVS, SOT-23")

BUCK = symbol("AP63203WU", [
    ("1", "FB", "input"), ("2", "EN", "input"), ("3", "VIN", "power_in"),
    ("4", "GND", "power_in"), ("5", "SW", "power_out"), ("6", "BST", "passive"),
], description="AP63203 fixed 3.3 V synchronous buck, TSOT-23-6")
# Pin GEOMETRY is overridden so the sheet reads left-to-right as the power
# actually flows: 12 V and EN in on the left, SW/BST out on the right, FB
# returning from the rail it regulates.  Pin NUMBERS are untouched -- this is
# a drawing change, and DS41326's map (1 FB, 2 EN, 3 VIN, 4 GND, 5 SW, 6 BST)
# is still what verify() pins.
SYMS[BUCK]["geom"] = {
    "3": (-7.62,  2.54,   0, "VIN", "power_in"),
    "2": (-7.62,  0.0,    0, "EN",  "input"),
    "4": (-7.62, -2.54,   0, "GND", "power_in"),
    "5": ( 7.62,  2.54, 180, "SW",  "power_out"),
    "6": ( 7.62,  0.0,  180, "BST", "passive"),
    "1": ( 7.62, -2.54, 180, "FB",  "input"),
}
# TI REF34xx, DBV 6-pin SOT-23, KELVIN-SENSED: 1 GND_F, 2 GND_S, 3 EN, 4 IN,
# 5 OUT_S, 6 OUT_F (SBAS804G Figure 5-1 and Table 5-1, read 2026-09-12).  This
# is NOT the 3-terminal part it is easy to assume: the REF34xxT variant is the
# simple one (1/3/5 NC) and LCSC stocks 8 of it against 8012 of this one.  Force
# and sense are separate pins and both must be connected.
REF34 = symbol("REF3425IDBV", [
    ("4", "IN", "power_in"), ("6", "OUT_F", "power_out"),
    ("3", "EN", "input"), ("5", "OUT_S", "input"),
    ("1", "GND_F", "power_in"), ("2", "GND_S", "power_in"),
], description="TI REF3425 2.5 V series voltage reference, SOT-23-6 (DBV)")
LDO = symbol("TPS7A2033PDBV", [
    ("1", "IN", "power_in"), ("2", "GND", "power_in"), ("3", "EN", "input"),
    ("4", "NC", "no_connect"), ("5", "OUT", "power_out"),
], description="TPS7A20 3.3 V fixed low-noise LDO, SOT-23-5")
OPAMP2 = symbol("OPA2333", [
    ("1", "OUT_A", "output"), ("2", "IN-_A", "input"), ("3", "IN+_A", "input"),
    ("4", "V-", "power_in"), ("5", "IN+_B", "input"), ("6", "IN-_B", "input"),
    ("7", "OUT_B", "output"), ("8", "V+", "power_in"),
], description="Dual zero-drift rail-to-rail op amp")
RS485 = symbol("THVD1410DR", [
    ("1", "R", "output"), ("2", "~RE", "input"), ("3", "DE", "input"),
    ("4", "D", "input"), ("5", "GND", "power_in"), ("6", "A", "bidirectional"),
    ("7", "B", "bidirectional"), ("8", "VCC", "power_in"),
], description="3.3 V to 5 V half-duplex RS-485 transceiver, SOIC-8")
LMP = symbol("LMP91000", [
    ("1", "DGND", "power_in"), ("2", "MENB", "input"), ("3", "SCL", "input"),
    ("4", "SDA", "bidirectional"), ("5", "NC", "no_connect"), ("6", "VDD", "power_in"),
    ("7", "AGND", "power_in"), ("8", "VOUT", "output"), ("9", "C2", "passive"),
    ("10", "C1", "passive"), ("11", "VREF", "input"), ("12", "WE", "bidirectional"),
    ("13", "RE", "input"), ("14", "CE", "output"), ("15", "DAP", "power_in"),
], description="Configurable potentiostat AFE, TI NHK WSON-14")
# (The ADS1119 symbol is DELETED with U8 on 2026-09-12. An unused symbol still
# emits into lib/o2-probe.kicad_sym, where it reads as a part this board has.)
TMP117 = symbol("TMP117", [
    ("1", "SCL", "input"), ("2", "GND", "power_in"), ("3", "ALERT", "open_collector"),
    ("4", "ADD0", "input"), ("5", "V+", "power_in"), ("6", "SDA", "bidirectional"),
    ("7", "EP", "passive"),
], description="High-accuracy I2C temperature sensor; EP is not internally grounded")
SHT45 = symbol("SHT45_AD1F", [
    ("1", "SDA", "bidirectional"), ("2", "SCL", "input"),
    ("3", "VDD", "power_in"), ("4", "VSS", "power_in"),
], description="Polyimide-membrane humidity and temperature sensor")
BMP390 = symbol("BMP390", [
    ("1", "VDDIO", "power_in"), ("2", "SCK/SCL", "input"),
    ("3", "VSS", "power_in"), ("4", "SDI/SDA", "bidirectional"),
    ("5", "SDO/SA0", "input"), ("6", "CSB", "input"),
    ("7", "INT", "output"), ("8", "VSS", "power_in"),
    ("9", "VSS", "power_in"), ("10", "VDD", "power_in"),
], description="DNP barometric pressure sensor; I2C address 0x76")
CELL = symbol("SGX_OX_MINI", [("1", "CE", "passive"), ("2", "RE", "passive"), ("3", "WE", "passive")], "U")

# LQFP48 package pinout from ST DS12232 Figure 5.  GPIO electrical types are
# bidirectional; supply pins retain power-input semantics.
MCU_PIN_NAMES = {
    1:"PC13",2:"PC14",3:"PC15",4:"VBAT",5:"VREF+",6:"VDD/VDDA",7:"VSS/VSSA",8:"PF0",9:"PF1",10:"PF2-NRST",
    11:"PA0",12:"PA1",13:"PA2",14:"PA3",15:"PA4",16:"PA5",17:"PA6",18:"PA7",19:"PB0",20:"PB1",21:"PB2",22:"PB10",23:"PB11",24:"PB12",
    25:"PB13",26:"PB14",27:"PB15",28:"PA8",29:"PA9",30:"PC6",31:"PC7",32:"PA10",33:"PA11",34:"PA12",35:"PA13",36:"PA14-BOOT0",
    37:"PA15",38:"PD0",39:"PD1",40:"PD2",41:"PD3",42:"PB3",43:"PB4",44:"PB5",45:"PB6",46:"PB7",47:"PB8",48:"PB9",
}
MCU_OUTPUTS = {13, 19, 28, 29}
# 11, 12, 15, 16, 17, 18 and 20 are the ANALOG inputs. Declaring them "input"
# rather than "bidirectional" is not cosmetic: an ADC pin on a reference or
# regulator output is a Power-output-to-Bidirectional ERC violation, and muting
# that with an exclusion would also mute a real GPIO driving into a rail.
# Pin 12 (PA1) left MCU_OUTPUTS here -- it was never an output, only unassigned.
MCU_INPUTS = {10, 11, 12, 14, 15, 16, 17, 18, 20, 21, 22, 32}
MCU = symbol("STM32G071CBT7", [
    (str(n), MCU_PIN_NAMES[n], "power_in" if n in (4,5,6,7) else ("output" if n in MCU_OUTPUTS else ("input" if n in MCU_INPUTS else "bidirectional")))
    for n in range(1, 49)
], description="128 KiB Cortex-M0+, -40..+105 C ambient suffix 7, LQFP48")


def place(ref: str, lib_id: str, x: float, y: float, *, value: str, footprint: str,
          mpn: str = "", dnp: bool = False, in_bom: bool = True, note: str = "",
          angle: int = 0) -> str:
    assert ref not in INST
    assert abs(x / GRID - round(x / GRID)) < 1e-6 and abs(y / GRID - round(y / GRID)) < 1e-6
    assert angle in (0, 90, 180, 270)
    INST[ref] = dict(lib_id=lib_id, x=x, y=y, value=value, footprint=footprint,
                     mpn=mpn, dnp=dnp, in_bom=in_bom, note=note, angle=angle)
    return ref


def pin_pos(ref: str, pin: str) -> tuple[float, float, int]:
    inst = INST[ref]
    x, y, pin_angle, _, _ = SYMS[inst["lib_id"]]["geom"][str(pin)]
    theta = math.radians(inst["angle"])
    rx = x * math.cos(theta) - y * math.sin(theta)
    ry = x * math.sin(theta) + y * math.cos(theta)
    return (round(inst["x"] + rx, 6), round(inst["y"] - ry, 6),
            (pin_angle + inst["angle"]) % 360)


def net(ref: str, pin: str | int, name: str, stub: float = 0.0) -> None:
    # Ground is drawn, not spelled. Every GND pin gets the conventional symbol
    # (see gnd()); nothing on this sheet should carry the string "GND" as a net
    # label any more.
    # PWR_FLAGs are annotation, not signal: they must keep a text label. Giving
    # one a power SYMBOL puts two power ports on the same point and merges the
    # rails, which is exactly what happened on the first attempt.
    if not ref.startswith("#"):
        if name == "GND":
            gnd(ref, pin, drop=stub)
            return
        if name in RAIL_NETS:
            rail_pin(ref, pin, name)
            return
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED, f"duplicate assignment {ref}.{pin}"
    x, y, angle = pin_pos(ref, pin)
    # Put the label directly on the package-pin connection point.  This avoids
    # accidental junctions between label stubs when dense review blocks sit on
    # the same row; KiCad treats the label anchor itself as the connection.
    if stub:
        dx = -stub if angle == 0 else stub
        WIRES.append((x, y, x + dx, y))
        x += dx
    # Justify the label AWAY from the body, decided by where the pin actually
    # sits relative to the symbol centre rather than by the pin's stored angle.
    # The old rule read the angle alone, so every ROTATED symbol -- which is
    # every horizontal R, C and L on this sheet -- justified its left-hand pin
    # rightwards and printed the net name back across its own part. That is the
    # "ADCAFEVOUT" mash, and it was a label-placement bug, not a spacing one.
    cx = INST[ref]["x"]
    LABELS.append((name, x, y, 180 if x < cx - 0.01 else 0))
    ASSIGNED[key] = name


_GND_PENDING: list[tuple[str, str, float]] = []
_RAIL_PENDING: list[tuple[str, str, str]] = []
# EMPTY, and this is a finding rather than a preference: a KiCad power symbol
# takes its net from the hidden power pin's NAME, not from the instance value.
# Placing the "+3V3" graphic with value "3V3D" therefore does NOT create a 3V3D
# net -- every rail symbol lands on +3V3 and the rails merge. Measured
# 2026-09-12: 3V3D swallowed 59 parts including every ground. Ground symbols are
# safe precisely because their pin name already IS "GND". Named rails would need
# custom library symbols whose pin name is the rail name; until then rails keep
# their text labels.
RAIL_NETS: tuple[str, ...] = ()


def rail_pin(ref: str, pin: str | int, name: str) -> None:
    """A supply pin gets the conventional power symbol, not a text label."""
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED, f"duplicate assignment {ref}.{pin}"
    ASSIGNED[key] = name
    _RAIL_PENDING.append((ref, pin, name))


def gnd(ref: str, pin: str | int, drop: float = 0.0) -> None:
    """Connect a pin to ground with a ground SYMBOL rather than a label.

    The symbol's POSITION is deferred: where it can sit without landing on a
    neighbour is not knowable while the sheet is still being built, and a fixed
    offset just moves the collision somewhere else -- measured, twice. See
    place_grounds().
    """
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED, f"duplicate assignment {ref}.{pin}"
    ASSIGNED[key] = "GND"
    _GND_PENDING.append((ref, pin, drop))


def _occupied() -> list[tuple[float, float, float, float]]:
    """Boxes a ground symbol must not land on: bodies and visible text."""
    boxes = []
    for ref, i in INST.items():
        sym = SYMS[i["lib_id"]]
        hw, hh = sym["half_w"], sym["half_h"]
        if i.get("angle") in (90, 270):
            hw, hh = hh, hw
        boxes.append((i["x"] - hw, i["y"] - hh, i["x"] + hw, i["y"] + hh))
        if ref.startswith("#PWR"):
            continue
        for t, dy in ((ref, -hh - 1.8), (str(i.get("value", "")), -hh - 3.6)):
            if t:
                w = len(t) * 1.08 / 2
                boxes.append((i["x"] - w, i["y"] + dy - 0.7, i["x"] + w, i["y"] + dy + 0.7))
    for text, x, y, ang in LABELS:
        w = len(text) * 1.08
        x0 = x - w if ang == 180 else x
        boxes.append((x0, y - 0.7, x0 + w, y + 0.7))
    return boxes


def _seg_hits(ax1, ay1, ax2, ay2, segs) -> bool:
    """True if segment A touches any existing wire segment.

    A power symbol dropped onto a foreign wire JOINS it -- that is how the
    first rail pass shorted 3V3D to GND while every box-based check passed.
    Geometry, not boxes, is what decides connectivity.
    """
    lo_x, hi_x = min(ax1, ax2) - 0.05, max(ax1, ax2) + 0.05
    lo_y, hi_y = min(ay1, ay2) - 0.05, max(ay1, ay2) + 0.05
    for bx1, by1, bx2, by2 in segs:
        if (min(bx1, bx2) <= hi_x and max(bx1, bx2) >= lo_x and
                min(by1, by2) <= hi_y and max(by1, by2) >= lo_y):
            return True
    return False


_BUS_RAILS: list[tuple[float, float, str]] = []
_BANK_GND: list[tuple[float, float]] = []


def rail_pin_at(anchor_pin, y: float, name: str) -> None:
    """Name a wired bus with ONE power symbol, placed above it."""
    _BUS_RAILS.append((pin_xy(*anchor_pin)[0], snap(y), name))


_BYPASS: list[tuple[str, str, str, float]] = []


def bypass_at(cap: str, ic: str, pin: str, side: float = -1.0) -> None:
    """Park a bypass capacitor beside the supply pin it actually serves.

    Fab, 2026-09-12: "put bypass caps near the components they are supplying."
    On a schematic this buys no electrons, but it is how the drawing states
    WHICH pin a capacitor is for -- and this sheet had 100 nF parts sitting
    30-40 mm from their own IC, which says nothing at all.
    """
    _BYPASS.append((cap, ic, pin, side))


def apply_bypass() -> None:
    for cap, ic, pin, side in _BYPASS:
        if ASSIGNED.get((cap, "2")) == "GND" and not any(
                t[0] == cap and t[1] == "2" for t in _GND_PENDING):
            _GND_PENDING.append((cap, "2", 0.0))
        px, py, _ = pin_pos(ic, pin)
        cx = snap(px + side * 7.62)
        INST[cap]["x"], INST[cap]["y"] = cx, snap(py + 6.35)
        INST[cap]["angle"] = 0
        wire_path([(snap(px), snap(py)), (cx, snap(py)), pin_xy(cap, 1)])


def place_grounds() -> None:
    """Give every deferred power pin a symbol, in the first free direction."""
    boxes = _occupied()
    half = 1.6
    for n, (bx, by) in enumerate(_BANK_GND, start=1):
        tag = f"#PWRG{n}"
        WIRES.append((snap(bx), snap(by), snap(bx), snap(by + 5.08)))
        place(tag, GNDSYM, snap(bx), snap(by + 5.08), value="GND",
              footprint="", in_bom=False)
        ASSIGNED[(tag, "1")] = "GND"
    for bx, by, bname in _BUS_RAILS:
        seq = len(_BUS_RAILS) + 900 + _BUS_RAILS.index((bx, by, bname))
        tag = f"#PWR{seq}"
        WIRES.append((snap(bx), snap(by), snap(bx), snap(by - 5.08)))
        place(tag, RAILSYM, snap(bx), snap(by - 5.08), value=bname,
              footprint="", in_bom=False)
        ASSIGNED[(tag, "1")] = bname
    # A part with several ground pins gets ONE symbol: the pins are bussed out
    # to a common column first. Six separate ground graphics on an ADS1119
    # would be six chances to collide and would say nothing extra.
    groups: dict[tuple[str, float], list[tuple[str, str, float]]] = {}
    for r, pin_, d in _GND_PENDING:
        px_, py_, _ = pin_pos(r, pin_)
        side_ = 1.0 if px_ > INST[r]["x"] + 0.01 else (-1.0 if px_ < INST[r]["x"] - 0.01 else 0.0)
        groups.setdefault((r, side_), []).append((r, pin_, d))
    work = []
    for (r, side_), members in groups.items():
        members.sort(key=lambda t: pin_pos(t[0], t[1])[1])
        if len(members) > 1 and side_:
            col = snap(pin_pos(members[0][0], members[0][1])[0] + side_ * 2.54)
            ys = [snap(pin_pos(m[0], m[1])[1]) for m in members]
            mine = [(snap(pin_pos(m[0], m[1])[0]), yy, col, yy)
                    for m, yy in zip(members, ys)]
            mine.append((col, min(ys), col, max(ys)))
            WIRES.extend(mine)
            # A tap onto the bus is a T: without a junction dot KiCad treats the
            # middle pins as unconnected, which is exactly what ERC reported.
            for yy in ys[1:-1]:
                junc((col, yy))
            work.append((r, members[-1][1], 0.0, None, col, max(ys), mine))
        else:
            for m in members:
                work.append((m[0], m[1], m[2], None, None, None, []))
    work += [(r, p, 0.0, n, None, None, []) for r, p, n in _RAIL_PENDING]
    for seq, (ref, pin, drop, railname, bus_x, bus_y, own_bus) in enumerate(work, start=1):
        px, py, _ = pin_pos(ref, pin)
        if bus_x is not None:
            px, py, drop = bus_x, bus_y, 0.0
        cx = INST[ref]["x"]
        side = 1.0 if px > cx + 0.01 else (-1.0 if px < cx - 0.01 else 0.0)
        if bus_x is not None:
            side = 1.0 if px > cx else -1.0
        sgn = -1.0 if railname else 1.0      # rails go up, grounds go down
        # Candidates ordered by how far they take the symbol from its pin, with
        # the part's own outward side preferred so the stub never crosses the body.
        cands = []
        for down in (2.54, 5.08, 7.62, 10.16, 12.7, 15.24, 17.78, 20.32, 25.4):
            for dx in (0.0, side * 2.54, side * 5.08, -side * 2.54,
                       2.54, -2.54, 5.08, -5.08, 7.62, -7.62,
                       10.16, -10.16, 12.7, -12.7, 15.24, -15.24):
                cands.append((dx, sgn * down))
        seen = set()
        cands = [c for c in cands if not (c in seen or seen.add(c))]
        # A group's own bus must not count as an obstacle to its own symbol.
        others = [w for w in WIRES if w not in own_bus]
        # Anything a wire can CONNECT to on contact: other pins and label
        # anchors. Boxes are about legibility; these are about connectivity.
        pts = []
        for oref, oi in INST.items():
            for opin in SYMS[oi["lib_id"]]["geom"]:
                if oref == ref and opin == pin:
                    continue      # the pin we are connecting, obviously
                # ...but NOT the rest of this part's pins: a ground dropped
                # 2.54 mm off U6.7 landed exactly on U6.9, a no-connect.
                pts.append(pin_xy(oref, opin))
        pts += [(snap(lx), snap(ly)) for _t, lx, ly, _a in LABELS]
        def _safe(dx, down):
            """Connectivity-safe: the stub touches no other wire, pin or label."""
            gx, gy = snap(px + dx), snap(py + down)
            own = [(snap(px), snap(py), snap(px + dx), snap(py))] if abs(dx) > 0.01 else []
            own.append((snap(px + dx), snap(py), snap(px + dx), gy))
            if any(_seg_hits(*seg, others) for seg in own):
                return None
            if any(min(sx1, sx2) - 0.05 <= qx <= max(sx1, sx2) + 0.05 and
                   min(sy1, sy2) - 0.05 <= qy <= max(sy1, sy2) + 0.05
                   for sx1, sy1, sx2, sy2 in own for qx, qy in pts):
                return None
            return gx, gy

        def _clear(gx, gy):
            return not any(min(gx + half, b2) - max(gx - half, b0) > 0.3 and
                           min(gy + half, b3) - max(gy - half, b1) > 0.3
                           for b0, b1, b2, b3 in boxes)

        # Pass 1 wants a spot that is both safe and legible. Pass 2 drops the
        # legibility requirement but NEVER the connectivity one -- a text
        # overlap is a finding audit_layout.py will report; a stub touching a
        # foreign wire is a silent short.
        chosen = None
        for dx, down in cands:
            got = _safe(dx, down)
            if got and _clear(*got):
                chosen = (dx, down, got)
                break
        if chosen is None:
            for dx, down in cands:
                got = _safe(dx, down)
                if got:
                    chosen = (dx, down, got)
                    break
        if chosen is None:
            # Nowhere safe for a graphic: fall back to the TEXT label rather
            # than force a symbol into a spot that would join a foreign net.
            # Correctness first, convention second; audit_layout.py counts what
            # is left so the fallback can never hide.
            LABELS.append((railname or "GND", snap(px), snap(py),
                           180 if px < INST[ref]["x"] - 0.01 else 0))
            continue
        dx, down, (gx, gy) = chosen
        tag = f"#PWR{seq:02d}"
        if abs(dx) > 0.01:
            WIRES.append((snap(px), snap(py), snap(px + dx), snap(py)))
        WIRES.append((snap(px + dx), snap(py), snap(px + dx), snap(gy)))
        place(tag, RAILSYM if railname else GNDSYM, gx, gy,
              value=railname or "GND", footprint="", in_bom=False)
        ASSIGNED[(tag, "1")] = railname or "GND"
        boxes.append((gx - half, gy - half, gx + half, gy + half))


def conn(ref: str, pin: str | int, name: str) -> None:
    """Record connectivity WITHOUT emitting a net label.

    The power section is drawn as real wires (Fab, 2026-09-12: "use wires, no
    label-soup"), so the net NAME is carried by exactly one label placed on the
    rail, not by a label on every pin.  ASSIGNED still gets the entry, so
    verify() and audit_schematic.py see the same netlist they always did.
    """
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED, f"duplicate assignment {ref}.{pin}"
    ASSIGNED[key] = name


def rail(name: str, pt: tuple[float, float], angle: int = 0) -> None:
    """The single naming label for a wired rail."""
    LABELS.append((name, snap(pt[0]), snap(pt[1]), angle))


def nc(ref: str, pin: str | int) -> None:
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED
    x, y, _ = pin_pos(ref, pin)
    NOCONN.append((x, y))
    ASSIGNED[key] = "(NC)"


def add_passive(ref: str, x: float, y: float, value: str, fp: str, a: str, b: str,
                *, mpn: str = "", dnp: bool = False, note: str = "",
                wired: bool = False, angle: int | None = None,
                lib: str | None = None) -> None:
    if lib is not None:
        lib_id = lib
    elif ref.startswith("C"):
        lib_id = CAP2
    elif ref.startswith("R"):
        lib_id = RES2
    elif ref.startswith("F"):
        lib_id = POLYFUSE2
    elif ref.startswith("DZ"):
        lib_id = ZENER2
    elif ref.startswith("D"):
        lib_id = TVS2
    elif ref.startswith("L"):
        lib_id = INDUCTOR2
    else:
        raise ValueError(f"no designated two-terminal symbol for {ref}")
    if angle is None:
        angle = 90 if lib_id in (RES2, CAP2, POLYFUSE2, INDUCTOR2) else 0
    place(ref, lib_id, x, y, value=value, footprint=fp,
          mpn=mpn, dnp=dnp, note=note, angle=angle)
    if wired:
        # Drawn with real wires by the caller; the rail carries ONE label.
        conn(ref, 1, a); conn(ref, 2, b)
    else:
        net(ref, 1, a); net(ref, 2, b)


# --------------------------------------------------------------------------- power input / buck
# The four cable lands read as ONE column at a 10.16 mm pitch, not two columns
# at 5.08.  Their value strings are long on purpose (wire colour is how the pad
# is identified at the farm), and at the old pitch those strings overlapped each
# other, the net labels and F1/D1 -- Fab, 2026-09-12: "fix that overlapping text".
for ref,y,value,n in (
    ("J101",25.40,"J1.1 BROWN +12V","+12V_RAW"),
    ("J102",35.56,"J1.2 WHITE GND","GND"),
    ("J103",45.72,"J1.3 GREEN A","RS485_A_CABLE"),
    ("J104",55.88,"J1.4 YELLOW B","RS485_B_CABLE"),
):
    place(ref, WIRE_LAND if ref in ("J103", "J104") else CONN1, 20.32, y, value=value,
          footprint=("o2-probe:SolderWire_RaisedRelief_1x01" if ref in ("J103", "J104") else
                     "Connector_Wire:SolderWire-0.25sqmm_1x01_D0.65mm_OD1.7mm_Relief"),
          note="One of four independent farm-bus cable solder pads")
    net(ref,1,n)
add_passive("F1", 48.26, 25.40, "0.75A PTC", "o2-probe:PTC_1206_3216Metric", "+12V_RAW", "+12V_FUSED",
            mpn="0ZCJ0075AF2E",
            note="Bel Fuse 0ZCJ 1206 PPTC: IH 0.75A, IT 1.5A, Vmax 16Vdc, Imax 100A. "
                 "Vmax leaves 1V over the 15V input maximum; do not raise the input range "
                 "without re-rating. IH derates to 0.52A at 60C and 0.36A at 85C")
add_passive("D1", 60.96, 38.10, "SMBJ15A-13-F", "Diode_SMD:D_SMB", "+12V_FUSED", "GND", mpn="SMBJ15A-13-F")
# REV B, 2026-09-12 (Fab's call): the DMP3130L reverse-polarity PMOS, its 100k
# gate pull-down R1 and its BZT52C10 VGS clamp DZ1 are REPLACED by one series
# Schottky.  Three parts become one.
#
# Why not just let D1 do it: a shunt clamp -- TVS, zener or Schottky alike --
# conducts as a forward-biased junction under reverse polarity and holds the
# rail at about -0.8 V.  DS41326 gives the AP63203's VIN absolute maximum as
# -0.3 V, so that is an abs-max violation, not a rating.  Worse, F1 is a PPTC:
# it does not blow, it trips and RESETS, so a cable left reversed cycles and
# re-applies that violation indefinitely -- on an assembly that is potted and
# buried and cannot be opened to replace the buck.  A SERIES element blocks
# instead of clamping, so nothing downstream ever sees negative voltage.
#
# The cost is explicit and lands on the HEATER, not the electronics: RH1/RH2
# hang off +12V_SW, so heater current passes through this diode.  At the
# datasheet's 390 mV worst case at 100 mA the ring sees 11.61 V instead of
# 12.00 V, i.e. 0.963 W against 1.029 W -- 6.4% less heating authority.  That
# was weighed against the dew-margin work, not against the BOM; HEATED-SPREADER.md
# records the coupling coefficient as unmeasured, so revisit this if the loop
# turns out to need its ceiling.  VF falls with temperature, so the worst case
# is a cold start, not the pile.
#
# D1 STAYS and is now doing two jobs: surge, and clamping this diode's reverse
# leakage (6 uA typ / 50 uA max at 40 V, 25 C, and Schottky leakage climbs
# steeply with temperature) so a reversed cable cannot drag the rail negative
# through the leakage path.
add_passive("D3", 66.04, 25.40, "PMEG4010CEH", "Diode_SMD:D_SOD-123F",
            "+12V_SW", "+12V_FUSED", mpn="PMEG4010CEH,115", lib=SCHOTTKY2,
            wired=True, angle=180,
            note="Series reverse-polarity Schottky, cathode to the load. Nexperia "
                 "PMEG4010CEH: 40 V VRRM against a 15 V specified input and D1's 24.4 V "
                 "clamp; 1 A IF against ~90 mA of heater plus 3 mA of board. VF is "
                 "340 mV typ / 390 mV max at 100 mA (Table 7), which is the 6.4 % of "
                 "heater authority this part costs. Pin 1 is the CATHODE and faces "
                 "+12V_SW -- reversing it does not fail ERC, it fails the probe")

place("#FLG01", PWRFLAG, 40.64, 233.68, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG01",1,"+12V_RAW",stub=2.54)
place("#FLG02", PWRFLAG, 71.12, 233.68, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG02",1,"GND",stub=2.54)
place("#FLG03", PWRFLAG, 101.6, 233.68, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG03",1,"+12V_SW",stub=2.54)

place("U1", BUCK, 106.68, 33.02, value="AP63203WU-7", footprint="Package_TO_SOT_SMD:TSOT-23-6",
      mpn="AP63203WU-7",
      note="REV B, 2026-09-12: was AP63205WU-7 (5 V). The 5 V rail existed for ONE reason "
           "-- AZ431 headroom (see the old note on R41) -- and the AZ431 is gone, so the "
           "intermediate rail goes with it. DS41326 covers AP63200/01/03/05 as one family; "
           "only 3.3 V and 5.0 V are FIXED options, everything else needs the adjustable "
           "AP63200 plus a divider. Pin map is unchanged and still asserted in verify()")
for p_, n_ in {1: "3V3D", 2: "+12V_SW", 3: "+12V_SW", 4: "GND", 5: "BUCK_SW", 6: "BUCK_BST"}.items():
    conn("U1", p_, n_)
add_passive("C1", 88.9, 43.18, "10u 25V X7R", "Capacitor_SMD:C_1206_3216Metric", "+12V_SW", "GND",
            mpn="C1206C106K3RACTU", wired=True, angle=0,
            note="Bulk bypass on the unregulated 7-15 V input. X7R is explicit because the "
                 "consolidated 10u 25V value string is shared, and package plus voltage "
                 "rating do not imply a dielectric -- Y5V would meet both")
add_passive("C2", 129.54, 20.32, "100n", "Capacitor_SMD:C_0402_1005Metric", "BUCK_BST", "BUCK_SW",
            wired=True, angle=0,
            note="AP63203 bootstrap, BST to SW. Only ever sees the BST-SW differential of "
                 "about 5 V despite riding the switching node, so an 0402 is amply rated")
add_passive("L1", 147.32, 30.48, "4.7u SHIELDED", "Inductor_SMD:L_6.3x6.3_H3", "BUCK_SW", "3V3D",
            mpn="SRN6028C-4R7M", wired=True, angle=0,
            note="DS41326 Table 2 gives 3.9 uH for the AP63203 at 3.3 V, against Table 3's "
                 "4.7 uH for the AP63205 at 5 V. 4.7 uH is KEPT DELIBERATELY: the datasheet's "
                 "own inductor section recommends 2.2-10 uH and says to USE A LARGER "
                 "INDUCTANCE FOR IMPROVED EFFICIENCY UNDER LIGHT LOAD, which is this board's "
                 "entire operating point (~3 mA). Keeping it also avoids re-opening the "
                 "L_6.3x6.3_H3 land mismatch recorded in FAB-NOTES. Bourns 4.7uH +/-20%, "
                 "Isat 3.2A, Irms 3.1A, DCR 30mOhm")
add_passive("C3", 165.1, 43.18, "22u", "Capacitor_SMD:C_1206_3216Metric", "3V3D", "GND",
            wired=True, angle=0, mpn="EMK316BB7226ML-T",
            note="Taiyo Yuden 22 uF 16 V X7R 1206, already in Fab's stock (50 pcs, checked "
                 "2026-09-12). The voltage rating matters more than the value here: used at "
                 "3.3 V this part sits at 21 % of its rating in a 1206 X7R, the gentle end of "
                 "the DC-bias curve -- against the 10 V X5R 0603 also in stock, which is the "
                 "heavily-derating kind and must NOT be substituted. Eq.10's worst case wants "
                 "9.1 uF EFFECTIVE; confirm against Taiyo Yuden's DC-bias data before release")
add_passive("C4", 177.8, 43.18, "22u", "Capacitor_SMD:C_1206_3216Metric", "3V3D", "GND",
            wired=True, angle=0, dnp=True, mpn="EMK316BB7226ML-T",
            note="DNP, land kept (Fab, 2026-09-12). DS41326 Table 2's 2 x 22 uF is the "
                 "recommendation for the 2 A part at full load; Eq.10 at THIS board's ~3 mA "
                 "wants 1.3 uF (0.3 A PFM peak, 50 mV overshoot) to 9.1 uF (0.8 A peak), and "
                 "one 22 uF covers that. The land stays because C3/C4 carry no MPN yet and "
                 "DC-bias derating is therefore UNKNOWN -- a heavily-derated 22 uF could "
                 "approach the 9.1 uF floor, and on Path A this capacitance is also the "
                 "first thing standing between the buck's PFM bursts and the AFE, which "
                 "reaches it through R32. Populate C4 and C8 before reaching for a bead in "
                 "R32. Check the chosen part's DC-bias curve against 9.1 uF at 3.3 V")

# ---------------------------------------------------------------- analog domain
# REV B, 2026-09-12 -- PATH A. U2 and U3 (both TPS7A2033) are DELETED with the
# 5 V rail. 3V3D comes straight off the buck; the AFE sits on the same rail
# behind R32/C7, and the 2.500 V REFERENCE is now its own precision part.
# The noise cost is explicit and is the release gate: see
# docs/2026-09-12-revb-single-rail-supply.md sections 8.7 and 9.
add_passive("R32", 196.85, 34.29, "10R", "Resistor_SMD:R_0603_1608Metric", "3V3D", "3V3A",
            wired=True,
            note="The ONLY thing between the AFE and the buck now that the analog LDO is "
                 "gone, so it is no longer a nicety. With C7 = 10 uF it is fc ~1.59 kHz, "
                 "which is 0.017 dB at 100 Hz -- it is NOT a filter against PFM burst "
                 "content, and nothing here claims it is. The footprint still takes a "
                 "characterized bead or 0R; choose it from the measured rail spectrum, not "
                 "from this value")
add_passive("C7", 209.55, 43.18, "10u 25V X7R", "Capacitor_SMD:C_1206_3216Metric", "3V3A", "GND",
            mpn="C1206C106K3RACTU", wired=True, angle=0,
            note="Analog-domain bulk, the C in the R32 RC. Include DC-bias derating in the "
                 "effective capacitance before quoting that corner frequency")
add_passive("C8", 222.25, 43.18, "1u", "Capacitor_SMD:C_0603_1608Metric", "3V3A", "GND",
            wired=True, angle=0, dnp=True,
            note="DNP, land kept (Fab, 2026-09-12). Between C7's 10 uF and the three 100 n "
                 "at U4/U7/U8 this 1 uF adds little -- but 3V3A is the rail Path A leaves "
                 "unfiltered in front of the AFE, so the FOOTPRINT stays fitted-able until "
                 "the rail spectrum is actually measured. Populate it before reaching for a "
                 "bead in R32")

place("U15", REF34, 236.22, 76.20, value="REF3425IDBVR",
      footprint="Package_TO_SOT_SMD:SOT-23-6",
      mpn="REF3425IDBVR",
      note="2.500 V series reference, REPLACING the AZ431 shunt and its R41/C9/R31 network. "
           "SBAS804G: +/-0.05% initial accuracy (max), 6 ppm/C max by the BOX method over "
           "-40..125 C -- which permits 990 ppm of TOTAL SPAN, not a 6 ppm/C local slope, so "
           "the bias contribution is ~0.9 mV and NOT the 0.3 mV a naive reading gives. "
           "95 uA max Iq against the AZ431 network's 2.5 mA. Output +/-10 mA against this "
           "board's ~400 uA analog draw. IT IS NOT A 3-TERMINAL PART: pins are 1 GND_F, "
           "2 GND_S, 3 EN, 4 IN, 5 OUT_S, 6 OUT_F and force/sense must BOTH be connected. "
           "EN IS TIED TO IN ON PURPOSE. Do not route it to a GPIO to make the rail "
           "gateable -- POWER-BUDGET.md invites exactly that, and dropping this rail drops "
           "the cell bias and restarts O2P_SETTLE_SECONDS = 900. Input is 3V3D and NOT "
           "+12V_SW: the board input is specified to 15 V and REF34's recommended input "
           "maximum is 12 V")
for p_, n_ in {1: "GND", 2: "GND", 3: "3V3D", 4: "3V3D", 5: "VREF_TRIM", 6: "VREF_TRIM"}.items():
    conn("U15", p_, n_)
add_passive("C36", 220.98, 76.20, "100n", "Capacitor_SMD:C_0402_1005Metric",
            "3V3D", "GND", wired=True, angle=0,
            note="REF3425 INPUT capacitor, and not optional tidiness: EVERY number in "
                 "SBAS804G's electrical and typical-characteristics tables is taken at "
                 "CIN = 0.1 uF (sections 6.5, 6.6), and the reference had no local input "
                 "cap at all -- it was living off whatever the 3V3D rail happened to "
                 "present at the end of R32's neighbourhood. Place at U15 pin 4")
add_passive("C10", 259.08, 76.20, "4.7u", "Capacitor_SMD:C_0603_1608Metric", "VREF_TRIM", "GND",
            wired=True, angle=0,
            note="REF3425 output capacitor. SBAS804G gives a stable CL range of 0.1 to 10 uF, "
                 "so the 4.7 uF already on this node carries over unchanged -- and the R31 "
                 "that used to isolate it from the AZ431 cathode is DELETED, because that "
                 "resistor existed to keep a SHUNT out of its unstable band and would now "
                 "sit in series with a series reference's output, adding IR drop to the one "
                 "node whose accuracy this part exists to provide")

place("U4",OPAMP2,246.38,35.56,value="OPA2333AIDGKR",footprint="Package_SO:VSSOP-8_3x3mm_P0.65mm",mpn="OPA2333AIDGKR",
      note="Both halves are now unity-gain electrometer followers on the cell nodes: A buffers "
           "WE, B buffers RE and drives both the guard (through R40) and the ADC bias "
           "telemetry. Half A was freed by deleting the VREF trim divider. NO FEMTOAMPERE PART "
           "IS NEEDED HERE and this is the reason: SBOS351E gives OPA333 IB as +/-70 pA typ "
           "and +/-200 pA max at 25 C. MIND THE ARITHMETIC: IB is the AVERAGE of the two "
           "inputs, and a follower's electrode sees the non-inverting input alone, so the real "
           "bound is |IB| + |IOS|/2 = 200 + 200 = 400 pA. The RE node is ALREADY loaded by the "
           "LMP91000's own RE pin at +/-90 pA typ and +/-900 pA max over -40..80 C (SNAS506I "
           "IRE, TI's own front-page feature; at this board's 3.3 V the applicable column is "
           "nearer 800 pA). So half B takes RE's worst case from ~900 pA to ~1300 pA, +44%, "
           "and an ADA4530-1 at 20 fA would still leave ~900 pA and buy nothing. UNSTATED "
           "ASSUMPTION, flagged deliberately: SBOS351E gives NO max for IB over temperature, "
           "only +/-150 pA typ, so the claim that a chopper's charge-injection-dominated bias "
           "stays flat to 75 C rests on Figure 8, a typical curve, not a guaranteed limit. "
           "See POTTING.md section 1.3 under ../../../ha/farming/compostlab/o2-probe/")
for p,n in {1:"WE_BUF",2:"WE_BUF",3:"CELL_WE",4:"GND",5:"CELL_RE",6:"RE_BUF",7:"RE_BUF",8:"3V3A"}.items(): net("U4",p,n)
# REV B, 2026-09-12 -- the AZ431 shunt network (U15 AZ431, R41, C9, R31 and its
# C10) stood here. It is REPLACED by the REF3425 in the power section above:
# +/-0.05% against +/-0.8%, 95 uA against 2.5 mA, one part against five, and no
# 5 V rail needed for headroom. VREF_SHUNT no longer exists as a net; VREF_TRIM
# is now the reference output itself. See docs/2026-09-12-revb-single-rail-supply.md.
add_passive("C25",284.48,55.88,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND",
            note="Place at U4 pins 8/4")
add_passive("R40",269.24,27.94,"47R","Resistor_SMD:R_0603_1608Metric","RE_BUF","GUARD_REPLICA",
            note="Guard-plane isolation resistor on the U4B follower output, feedback taken at "
                 "the op-amp output exactly as R31 does -- driving a large guard plane is a "
                 "compensation question, not an afterthought (POTTING.md section 1.3). "
                 "REPLACES the deleted R22/R23 divider: the guard now tracks the REAL RE "
                 "electrode instead of an open-loop 0.909 x VREF prediction of it, which is "
                 "standard guarded-electrometer practice and strictly better guarding. The net "
                 "name GUARD_REPLICA is kept because repair_guard_fill.py, "
                 "route_thermal_barrier.py, audit_pcb.py and THERMAL-BARRIER.md all key off it; "
                 "it is no longer a replica of anything")
place("TP4",TESTPOINT,289.56,30.48,value="VREF",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP4",1,"VREF_TRIM",stub=6.35)
place("TP5",TESTPOINT,289.56,43.18,value="GUARD",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP5",1,"GUARD_REPLICA",stub=6.35)

# --------------------------------------------------------------------------- RS-485 and MCU
place("U5",RS485,35.56,91.44,value="THVD1410DR",footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",mpn="THVD1410DR")
# REV B, 2026-09-07: pin 2 (RE) is SPLIT off RS485_DE onto its own net and its
# own GPIO (PC7, MCU pin 31).  Rev A tied both enables to RS485_DE, and because
# RE is ACTIVE LOW with a 2 MOhm internal pull-UP while DE is ACTIVE HIGH with a
# 2 MOhm internal pull-DOWN (SLLSEY3E "Pin Functions"), one net could only reach
# two of the four states:
#   RS485_DE low  -> RE=0, DE=0 -> receiver on, driver off  -> 700 uA typ
#   RS485_DE high -> RE=1, DE=1 -> receiver off, driver ON   -> 2 mA AND driving
# The 0.1 uA standby (RE=VCC, DE=0 V, D open) was physically uncommandable.
# See POWER-BUDGET.md "The transceiver: the part says yes, Rev A says no".
for p,n in {1:"RS485_RX",2:"RS485_RE",3:"RS485_DE",4:"RS485_TX",5:"GND",6:"RS485_A",7:"RS485_B",8:"3V3D"}.items(): net("U5",p,n)
add_passive("R2",15.24,74.93,"10R","Resistor_SMD:R_0603_1608Metric","RS485_A","RS485_A_CABLE")
add_passive("R3",15.24,100.33,"10R","Resistor_SMD:R_0603_1608Metric","RS485_B","RS485_B_CABLE")
place("D2",SM712,25.40,118.11,value="SM712-02HTG",footprint="Package_TO_SOT_SMD:SOT-23",mpn="SM712-02HTG",
      note="Littelfuse asymmetric RS-485 TVS; locate cable-side of R2/R3")
net("D2",1,"RS485_A_CABLE"); net("D2",2,"RS485_B_CABLE"); net("D2",3,"GND")
add_passive("R4",55.88,82.55,"120R DNP","Resistor_SMD:R_0603_1608Metric","RS485_A","RS485_B",dnp=True)
# R5/R6 (680R DNP RS-485 fail-safe bias) are DELETED.  Not merely unfitted --
# redundant: TI SLLSEY3E 9.3 / 10.2.1.4 gives the THVD1410 receiver open-, short-
# and idle-bus failsafe without external bias, and 10.2.1.3 allows up to 256 of
# these 1/8-unit-load receivers, so the behaviour holds at every MULTIDROP node,
# not only point-to-point. (An earlier draft of this cited "SLLSF11 8.3", which
# is the wrong document; a reviewer caught it.) It does NOT replace end
# termination, which is why R4 stays.  R4 STAYS: 120R end-of-bus termination is a real option
# a farm cable can need, and it is the one DNP on this board that is a decision
# left open rather than an idea left behind.
add_passive("R7",73.66,105.41,"47k","Resistor_SMD:R_0603_1608Metric","RS485_DE","GND")
add_passive("R45",73.66,115.57,"47k","Resistor_SMD:R_0603_1608Metric","RS485_RE","GND",
            note="REV B.  The failsafe that makes the RE split SAFE, and it is the whole "
                 "reason the split is not dangerous.  RE is active low with a 2 MOhm "
                 "internal pull-UP, so an undriven RE pin is a DISABLED receiver -- and "
                 "every MCU GPIO is high-impedance out of reset.  Without this resistor a "
                 "probe that reset into the RS-485 bootloader (loader_main.c / "
                 "loader_uart.c) would come up DEAF, destroying the field-reflash path "
                 "SCHEMATIC-REVIEW.md M2 exists to provide.  A potted probe would be "
                 "unrecoverable.  R45 makes receiver-enabled the passive default exactly "
                 "as R7 makes driver-disabled the passive default.\n"
                 "ARITHMETIC.  Size against the GUARANTEED spec, not the 2 MOhm typical: "
                 "SLLSEY3E gives IIN = +/-6.2 uA max for D, DE and RE over "
                 "3 V <= VCC <= 5.5 V, with VIL max 0.8 V.  So the largest pull-down that "
                 "still guarantees a low is R <= 0.8 V / 6.2 uA = 129k.\n"
                 "  47k: worst case 6.2 uA * 47k = 291 mV, a 2.75x margin to VIL.  (The "
                 "2 MOhm typical would give 76 mV, but a typical is not a guarantee and "
                 "this pin must never come up deaf.)\n"
                 "COST, stated plainly because it bounds the win this split was made for: "
                 "commanding standby means DRIVING RE high, which pushes 3.3 V / 47k = "
                 "70.2 uA through R45.  Standby is therefore ~70 uA, not the part's "
                 "0.1 uA.  Against the 700 uA receiver that is still a 10x cut (630 uA "
                 "saved), but it is NOT the 7000x the datasheet row promises, and at the "
                 "duty-cycled floor of ~29 uA in POWER-BUDGET.md this resistor would be "
                 "the single largest load on the board.\n"
                 "WHY NOT A WEAKER PULL-DOWN: the 129k ceiling above means no resistor "
                 "can better ~26 uA, so 220k/470k do not trade margin for microamps -- "
                 "they are simply OUT OF SPEC (220k worst case = 1.36 V, 470k = 2.9 V, "
                 "both above VIL).  A resistor structurally cannot reach the 0.1 uA this "
                 "split was made for; only omitting R45 and having the loader drive RE "
                 "low early can, and that trades a sub-ms deaf window after reset.  Fab "
                 "chose 47k, 2026-09-07: robust, passive, no init-order dependency.")
add_passive("C11",73.66,82.55,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")

place("U6",MCU,111.76,99.06,value="STM32G071CBT7",footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",mpn="STM32G071CBT7")
# Group the three RS-485 controls at the MCU's left edge and bring BOTH rail
# monitors into PA6/ADC_IN6 (VIN) and PA7/ADC_IN7 (VA).  VIN_MON moved here from
# ADS1119 AIN3, which the cell bias telemetry now occupies. These generator-owned assignments materially
# shorten the compact placement's routes without changing functionality.
# Pin 15 is PA4 = ADC1_IN4, one of four ADC-capable pins (11/12/15/16 =
# PA0/PA1/PA4/PA5) left nc() on this part. CE telemetry costs one of them and no
# ADS1119 channel.
# Pin 21 (EXP_INT) falls to nc() with the expansion connector.  Pins 13/14
# (PA2/PA3, USART2) DO NOT: they keep their nets and land on J105/J106 below.
# Pin 31 is PC7 (REV B, RS485_RE).  Pin identity verified against DS12232 Rev 1
# Figure "LQFP48 pinout" (30 = PC6, 31 = PC7) and Table 12 "Pin assignment and
# description", whose LQFP48/UFQFPN48 column gives PC6 = 30 and PC7 = 31 -- and
# whose "Additional functions" cell for PC7 is empty, so it carries NO ADC
# channel and cannot collide with mcu_adc.c.  PC7 is a plain FT I/O whose only
# alternate functions are UCPD2_FRSTX, TIM3_CH2 and TIM2_CH4, none of them used.
# It is the neighbour of PC6 in the package, which is what the two RS-485
# enables want to be.  PIN-IDENTITY-POSTMORTEM.md is about what happens when a
# pin identity is taken from prose instead of from the pin table; this one came
# from the table.
#
# REV B, 2026-09-12: the ADS1119 is DELETED (docs/2026-09-12-revb-decision-delete-ads1119.md)
# and its four analog channels land here.  Pin identities and ADC channels are
# from DS12232 Rev 5 Table 12, the pin TABLE, not the pinout figure:
#   11 = PA0, ADC_IN0, FT_a      12 = PA1, ADC_IN1, FT_a
#   16 = PA5, ADC_IN5, TT_a      20 = PB1, ADC_IN9, FT_a   (freed by ADC_DRDY)
# PB1 is ADC_IN9 and PB0 is ADC_IN8; the IN17/IN18 numbering belongs to the
# larger packages' rows in the same table and is NOT what this part has.
#
# ADOPTED 2026-09-12 (Fab, "del u8"): VREF+ ON PIN 5 IS DRIVEN FROM /VREF_TRIM,
# not 3V3D.  The ADC's full scale becomes the REF3425's 2.500 V, and VDDA -- a
# BUCK output with no LDO since Path A -- disappears from the oxygen derivation
# entirely.  That is the decisive number: with VREF+ = VDDA the three
# conversions happen at different times on a rail that moves, and the worst pair
# couples 0.718 mV/mV at zero oxygen; with VREF+ = the reference, the coupling
# is not reduced, it is ZERO.
#
# PA5 (pin 16) therefore RETURNS TO THE POOL and is nc().  Converting
# /VREF_TRIM against itself saturates at 4095 and carries no information.
# Reference health is VREFINT against the 2.5 V full scale -- and that is a
# COLLAPSE DETECTOR, NOT A DRIFT MONITOR: VREFINT's own tempco (50 ppm/degC) and
# ACoeff (1000 ppm/1000 h) are 8x and 40x worse than the part it watches.
#
# The allocation is by LEAKAGE, which is the failure mode this revision exists
# to answer.  Table 51: FT_a leaks +/-70 nA, TT_a +/-150 nA.  So the three
# 1 kOhm-sourced filtered signals take the three FT_a pins (70 uV of offset),
# and the reference needs no channel of its own at all.  (A superseded version of
# this comment put /VREF_TRIM on PA5 and justified the TT_a pin by its low source
# impedance; that was correct for the VDDA architecture and is moot in this one.)
#
# Table 50 matters here too and cuts the other way from Table 51: PA0, PA1 and
# PB1 are all in the "all except" group rated -5 mA of negative injection, so
# consolidating four channels onto one converter adds NO exposed pin.  The
# exposed pin is PA6/VIN_MON, and it was exposed before this change -- see D8.  WE_BUF and RE_BUF are additionally placed on ADJACENT FT_a
# pins of identical structure, so their leakage common-modes out of the
# difference, which is the quantity that carries the -600 mV bias.
MCU_NETS = {4:"3V3D",5:"VREF_TRIM",6:"3V3D",7:"GND",10:"NRST",11:"ADC_WE_BUF",12:"ADC_RE_BUF",13:"UART2_TX",14:"UART2_RX",15:"CE_MON",17:"VIN_MON",18:"VA_MON",19:"AFE_MENB",20:"ADC_AFE_VOUT",28:"HEATER_PWM",29:"RS485_TX",30:"RS485_DE",31:"RS485_RE",32:"RS485_RX",35:"SWDIO",36:"SWCLK_BOOT0",42:"SWO",45:"I2C_SCL",46:"I2C_SDA"}
for p in range(1,49):
    if p in MCU_NETS: net("U6",p,MCU_NETS[p])
    else: nc("U6",p)
add_passive("C12",45.72,130.81,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C13",58.42,130.81,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C14",71.12,130.81,"4.7u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND")
add_passive("C26",88.9,71.12,"100n","Capacitor_SMD:C_0402_1005Metric","VREF_TRIM","GND",
            note="Local decoupling AT MCU VREF+ pin 5, which since 2026-09-12 is driven from "
                 "/VREF_TRIM and not 3V3D. It FOLLOWED THE PIN rather than staying on 3V3D: "
                 "its only reason to exist was that pin, and with pin 5 moved its bulk would "
                 "otherwise be C10, 4.7 uF at U15 on the far side of the board. DS12232 "
                 "Table 63 note 4 asks for a 100 nF specifically to cut high-frequency noise "
                 "at this pin. 100n not 1u because the bulk is already at C10 and the total "
                 "load on the REF3425 must stay inside SBAS804G's 0.1..10 uF stable range: "
                 "4.7 + 0.1 = 4.8 uF. 3V3D loses nothing -- C12, C13, C14, C11, C3, C20 and "
                 "C21 are all still on it")
# R8, a 10k NRST pull-up, is DELETED: DS12232 5.3.15 says NRST "is connected to
# a permanent pull-up resistor, RPU", so the external one was duplicating
# silicon. C15 stays -- the capacitor is the part ST's reference design
# actually asks for on this pin.
add_passive("C15",160.02,93.98,"100n","Capacitor_SMD:C_0402_1005Metric","NRST","GND")
add_passive("R9",160.02,104.14,"100k","Resistor_SMD:R_0603_1608Metric","SWCLK_BOOT0","GND")
add_passive("R10",177.8,83.82,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SCL","3V3D")
add_passive("R11",177.8,93.98,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SDA","3V3D")

place("J3",CONN6,203.2,88.9,value="TC2030 SWD PRE-POT",footprint="Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",note="1=VTREF 2=SWDIO 3=NRST 4=SWCLK 5=GND 6=SWO")
for p,n in enumerate(("3V3D","SWDIO","NRST","SWCLK_BOOT0","GND","SWO"),1): net("J3",p,n)

# --------------------------------------------------------------------------- expansion connector: DELETED
# J2 (Micro-Fit 3.0 2x04), F2, R12-R16, D4/D5/D6 are gone -- fourteen never-fitted
# parts.  They cost nothing to buy and that is exactly why they survived four
# revisions.  What they cost is AREA: measured on the Rev A board, the DNP set
# held 329.2 mm2 of courtyard, 20.6% of every courtyard on a 20 x 107 board, and
# J2 alone was 224.8 mm2 of it -- 17.2 x 13.0 mm plus two 2.41 mm NPTH mounting
# holes, sitting at local y 60.5..73.5, the run-up to the local-70..80 AFE band
# the two-layer work is fighting (docs/archive/2026-09-09-pcb-plans/TWO-LAYER-REFLOORPLAN.md).  On two layers an
# NPTH is a hole through both.
#
# 877ac52 measured that deleting the six EXP_ SIGNALS buys one open link, and
# concluded the connector was not worth removing.  That is a different
# experiment: signals are copper the router can move, while the NPTH pair and
# the courtyard are geometry it cannot.  The routing gain from THIS deletion is
# not yet measured; the area and the 16 fewer placements are.
#
# R15/R16 ARE NOT IN THAT LIST, and docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 3 was wrong to put them
# there.  They are not dead options: board_pins.h:56 and bridge_main.c:16 both
# say that on an assembled board PA2/PA3 "reach the MCU-side pad of R15 and R16
# and stop there", and that those 0603 pads -- not the LQFP's 0.5 mm pitch --
# are where the bench bridge's TTL lead is soldered.  Deleting them would have
# removed the attach point of a shipped firmware image (bridge_main.c,
# bridge_uart.c, o2probe_bridge.ld) and broken the O2P_ASSERT_NET static asserts
# on UART2_TX/UART2_RX at compile time.
#
# So the tap SURVIVES and gets better: J105/J106 below are solder-wire lands on
# the same two nets.  A wire land is what that pad was always being used as, it
# is the footprint J101-J104 already use, it carries no BOM line, and two of
# them replace five 33R parts.  PA13/EXP_INT had no user and falls to nc().
#
# WHAT IS STILL LOST: the 2x04 pad field for a future daughterboard, and the
# 0.20 A separately-fused EXP_3V3 that fed it.  J2 was DNP on every board ever
# built, so no built board ever had either.  Fab approved the deletion on
# 2026-09-05 against docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 3.
place("J105",WIRE_LAND,251.46,116.84,value="BRIDGE TX (PA2)",footprint="o2-probe:SolderWireNoRelief_J105",
      note="Bench-bridge TTL tap, MCU side. Laptop TTL RX <- here. 3.3 V logic ONLY: "
           "PA2/PA3 are not 5 V tolerant on this device (bridge_main.c:23)")
net("J105",1,"UART2_TX")
place("J106",WIRE_LAND,251.46,127.0,value="BRIDGE RX (PA3)",footprint="o2-probe:SolderWireNoRelief_J106",
      note="Bench-bridge TTL tap, MCU side. Laptop TTL TX -> here. See J105")
net("J106",1,"UART2_RX")

# --------------------------------------------------------------------------- AFE / ADC / cell
place("U7",LMP,50.8,162.56,value="LMP91000SD/NOPB",footprint="Package_SON:WSON-14-1EP_4.0x4.0mm_P0.5mm_EP2.6x2.6mm",
      mpn="LMP91000SDX/NOPB",
      note="Was LMP91000SDE/NOPB, which DigiKey lists as OBSOLETE. SDX is the same die in "
           "the same 14-WSON 4x4 package and is Active; the suffix is reel quantity only. "
           "PO-0010 (Mouser 926-LMP91000SDX/NOPB) already ordered 5 of these, so the "
           "schematic was naming a part we neither buy nor can re-buy")
for p,n in {1:"GND",2:"AFE_MENB",3:"I2C_SCL",4:"I2C_SDA",6:"3V3A",7:"GND",8:"AFE_VOUT",9:"LMP_C2",10:"LMP_C1",11:"VREF_TRIM",12:"CELL_WE",13:"CELL_RE",14:"CELL_CE_DRV",15:"GND"}.items(): net("U7",p,n)
nc("U7",5)
add_passive("R17",20.32,149.86,"100k","Resistor_SMD:R_0603_1608Metric","AFE_MENB","GND")
add_passive("C16",20.32,160.02,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND")
add_passive("C17",20.32,170.18,"10n","Capacitor_SMD:C_0603_1608Metric","LMP_C1","LMP_C2")
for ref,x,n in (("TP1",50.8,"CELL_WE"),("TP3",71.12,"CELL_CE")):
    place(ref,TESTPOINT,x,213.36,value=n,footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False)
    net(ref,1,n,stub=6.35)

# --------------------------------------------------------------------------- CE branch: limit, watch, clamp
# A1 died on 2026-09-04 (AFE-BRING-UP-POSTMORTEM.md) and nothing on the board
# could say so: the bench needed an evening with a DMM on chip leads to decide
# which of four parts was guilty, and once potted that method does not exist.
# CELL_CE therefore stops being a bare wire from pin 14 to the cell.
#
# R42 limits a CE-to-ground short while the AFE rail is within 3.366 V.
# With 1% tolerance and +/-100 ppm/K over -40..85 C, Rmin = 983.565 ohm:
# 3.366/Rmin = 3.422 mA, below SNAS506I 6.1's 10 mA CE absolute maximum.
# This is a STATIC INTERNAL-RAIL fault bound, not an IEC ESD or 12 V fault rating.
# R43/R44 load the device pin in parallel; their worst-case 18.7 uA still leaves
# total CE current below 3.45 mA under that fault. See the calculation record.
#
# The old 100R did not meet this bound (over 34 mA). The cost is explicit:
# at 130 uA the new resistor drops at most 132.2 mV. A1 can compensate only
# while it retains output headroom. SNAS506I 6.5's 0.3..VS-0.3 V window is an
# open-loop-gain characterisation condition, not a hard compliance limit.
# Test startup and cell bias at the hot/full-scale operating corners before
# deployment. Do not combine the dummy's CE voltage with a real-cell current.
# No cell stability or impulse-energy qualification is claimed from this bound.
add_passive("R42",25.4,187.96,"1k 1%","Resistor_SMD:R_0603_1608Metric","CELL_CE_DRV","CELL_CE",
            mpn="RC0603FR-071KL",
            note="CE series resistor; limits an internal-rail CE short to <3.45 mA incl. "
                 "monitor load at 3V3A <=3.366 V, -40..85 C. Costs <=132.2 mV at 130 uA; "
                 "hot-cell headroom and stability require bench qualification. Not an ESD rating. "
                 "See docs/2026-09-09-revb-protection.md")

# R43/R44 watch pin 14 itself, not the electrode, because the compliance window
# is a limit on the DEVICE PIN. This is the node that distinguishes the failure
# modes: railed means A1 driving into a fault, sitting at the internal zero means
# A1 idle or dead, tracking WE + 2x bias means healthy. RE-WE only says the bias
# is already gone.
#
# CAUTION on reading it. "CE tracking WE + 2x bias means healthy" is TRUE ONLY OF
# THE 1M/1M DUMMY, where both legs carry the same current and so drop the same
# voltage. SNAS506 requires A1 to move CE wherever it must to regulate the
# separately sensed RE-WE bias; it says nothing about CE-RE for a real cell,
# where counter-electrode polarisation and cell impedance set it. Railed and
# stuck-at-internal-zero are diagnostic; the "healthy" BAND has to be
# characterised across real cells, O2, temperature and age before firmware may
# fault on it.
#
# It goes on the MCU's own ADC, not the ADS1119: all four ADS inputs are spent
# (AIN0 AFE_VOUT, AIN1 VREF_MON, AIN2 WE_BUF, AIN3 RE_BUF) and none of them is
# worth trading for this. CE is a low-impedance driven node wanting a divider and
# no precision, which is exactly what the MCU ADC is for -- ~0.8 mV/LSB at 12
# bits on VDDA, against thresholds of 300 mV and 3000 mV.
#
# 91k/91k, not the 10k pairs used by the rail monitors: this divider hangs on
# A1's output, and a 10k pair would draw 144 uA of A1's 750 uA specified drive
# where a 91k pair draws 16 uA. Not 100k/100k either, which was the first choice
# and is wrong by exactly one tolerance band: DS12232 Table 58 gives RAIN(max)
# 50 kohm, a nominal 100k/100k is exactly 50 kohm Thevenin, and at 1 % worst case
# 50.5 kohm -- over the limit with no production margin. 91k/91k is 45.5 kohm
# nominal and stays inside at tolerance. Table 59 then permits it at 12 bits with
# the 160.5-cycle sampling time (4.586 us at 35 MHz). C34 supplies sampling
# charge locally on top of that; its ~4.6 ms time constant means the reading
# needs settling after startup and after a bias change -- a firmware sequencing
# requirement, not a hardware one.
add_passive("R43",101.6,187.96,"91k 1%","Resistor_SMD:R_0603_1608Metric","CELL_CE_DRV","CE_MON",
            mpn="RC0603FR-0791KL",
            note="CE compliance monitor divider, 1:2 into MCU PA4/ADC_IN4. "
                 "FIRMWARE: CE_MV = 2 x ADC. High value on purpose -- see R44")
add_passive("R44",101.6,198.12,"91k 1%","Resistor_SMD:R_0603_1608Metric","CE_MON","GND",
            mpn="RC0603FR-0791KL",
            note="CE monitor divider bottom leg. 182k total keeps the load on A1's output at "
                 "~16 uA of its 750 uA drive spec; a 10k pair would take 144 uA. The value is set "
                 "by the ADC's 50 kohm max source impedance AT TOLERANCE, not by the load")
add_passive("C34",121.92,198.12,"100n","Capacitor_SMD:C_0402_1005Metric","CE_MON","GND",
            note="Sampling reservoir for the ~50k divider source. The STM32G0 ADC samples onto a "
                 "small S&H capacitor; this supplies that charge locally so the long sampling "
                 "time the bare divider would need is not the only thing holding the reading up")

# CE-only ESD shunt on the exposed side of R42. SLLSEJ9E Table 5-1:
# TPD2E2U06-Q1 DBZ is 1=IO1, 2=IO2, 3=GND. The former symbol swapped
# IO2/GND and left the actual ground floating. The full order code ends RQ1.
# IO2 stays NC; WE/RE leakage and common-mode cell stress are outside this
# CE-only implementation. The diode's component-level IEC rating is not a
# qualification of the assembled probe. Its 9.7 V clamp at 1 A is TYPICAL,
# above LMP91000's 6 V pin-to-pin absolute maximum; R42 is not a voltage clamp.
# Whole-system ESD testing remains required; do not claim protected electrodes.
place("D7",TVS3,45.72,187.96,value="TPD2E2U06-Q1",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZRQ1",
      note="CE-only ESD shunt, SLLSEJ9E Table 5-1: 1 IO1, 2 IO2 (unused), 3 GND. "
           "Route CE through pad 1 before R42; keep pad 3's ground return short. "
           "Component ESD rating does not establish probe survival; see protection record")
net("D7",1,"CELL_CE"); nc("D7",2); net("D7",3,"GND")

# CELL_RE STILL GETS NO TEST POINT, and this is a reversal of a reversal worth
# recording. The bench asked for one on 2026-09-04, having spent an evening
# unable to verify that net without metering a 0.5 mm chip lead. That request was
# made against Rev A, where CELL_RE reached no converter at all. It does now:
# U4's follower carries it to ADS1119 AIN3 as ADC_RE_BUF, so "is RE connected and
# at the right potential" is a register read, before potting and after it. The
# pad's remaining value is small, and its cost is not: audit_schematic.py has
# refused an aperture on this net on wet-leakage grounds, and that objection is
# unrebutted for a node whose whole design -- driven guard, potting, a picoamp
# input-current budget -- exists to keep stray current off it. A guard ring would
# intercept most of the leakage, but "most" is the wrong standard for the one
# node where the budget is +/-900 pA.
#
# TP2 is different and is fitted: a local ground costs nothing, sits on no
# sensitive net, and is what makes the other five pads readable single-handed.
place("TP2",TESTPOINT,104.14,213.36,value="GND",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False)
net("TP2",1,"GND",stub=6.35)

# U8, the ADS1119, IS DELETED (Fab, 2026-09-12 --
# docs/2026-09-12-revb-decision-delete-ads1119.md).  Three of its four analog
# inputs died on the Rev A bench board at 22:24 on 09-11 when coating paint plus
# heat was applied, and the five hours it took to see that were spent looking at
# the 2.5 V reference THROUGH the one ADS channel that was lying about it.
# Every analog channel now converts on the STM32G071's own SAR (see MCU_NETS).
#
# VREF+ IS DRIVEN FROM /VREF_TRIM, THE REF3425 -- NOT from VDDA.  The paragraph
# that stood here until 2026-09-12 described the VDDA form, which was PROPOSED
# AND REJECTED, and it must not be read as a description of this board.  It
# argued that the reference's drift would cancel ARITHMETICALLY because
# /VREF_TRIM and /AFE_VOUT are converted on the same converter, so no wiring was
# needed to obtain ratiometry.  THAT ARGUMENT IS WRONG, and the reason it is
# wrong is the whole justification for the adopted design: the two conversions
# do not happen at the same instant, and the rail moves between them.  3V3D
# couples into the oxygen reading at 0.718 mV/mV at zero O2, and 4.63 mV RMS of
# rail motion is 0.1 %O2.  Arithmetic cannot cancel a quantity that changed
# between the two samples; only wiring the ladder and the full scale to the SAME
# node can, which is what driving VREF+ from the REF3425 does.
# See docs/2026-09-12-revb-decision-delete-ads1119.md and
# docs/2026-09-12-revb-cost-of-moving-vref-to-the-ref3425.md.
# Deleted with it: R18 (already gone), R19, C18, C19, the ADC_DRDY net, and the
# I2C traffic to U8.  Deleted separately but for the same reason: R34/R35/R36/C29
# and the nets VREF_MON_RAW and ADC_VREF_MON, per
# docs/2026-09-12-revb-decision-vref-monitor.md -- that divider is where the
# ~800 Ohm leak grew, and measuring VREF_TRIM directly removes the node rather
# than making it less likely to fail.
#
# KEPT, and this is a correction to P0 of the proposals doc, which listed them
# as deletions: R33/C28, R37/C30, R38/C31.  A SAR needs them MORE than a
# delta-sigma does -- the 100 nF sources the charge kick of the ADC's 5 pF
# sample capacitor (CADC, DS12232 Table 58) so the op-amp does not -- and 1 kOhm
# is far inside the 50 kOhm RAIN limit.
#
# The paragraph below is retained because its ELECTRICAL content still governs
# the bias-telemetry pair on the MCU's ADC; only the converter changed.
# WE_BUF/RE_BUF are the bias-telemetry pair, read as V_WE - V_RE.
# POTTING.md section 1.1: VREF is NOT where the LMP91000's +/-2% bias step error
# lives, so measuring VREF cannot substitute -- the differential is the only node
# carrying the real information.
#
# THE PEDESTAL IS THE THING TO KNOW: with REFCN = 0xCD the LMP91000's internal
# zero is 67% of VREF and the bias step 24%, so V_WE = 1.675 V, V_RE = 2.275 V
# and their DIFFERENCE IS -600 mV BY DESIGN -- not a small signal near zero.
#
# On the MCU's SAR this gets EASIER, not harder, and that is worth stating
# because the ADS1119 version of this note was a list of ways to clip.  Both
# legs are now converted SINGLE-ENDED against the REF3425's 2.500 V full scale;
# there is no differential full scale to be 96% of, and no internal-reference
# setting that can hard-clip the pair.
#
# BUT CORRECT THE HEADROOM CLAIM THIS NOTE USED TO MAKE.  It said the two legs
# "sit around mid-scale with a volt of room on either side", which was arithmetic
# against a 3.3 V full scale -- i.e. against the REJECTED VDDA form.  Against
# 2.500 V the real numbers are V_WE = 1.675 V = 0.67 x FS (code 2744) and
# V_RE = 2.275 V = 0.91 x FS (code 3727).  V_RE has 225 mV of headroom, not a
# volt.  That is still workable -- nothing clips, and the pedestal is fixed by
# REFCN rather than by the signal -- but it is tight enough that it must be
# stated honestly, and it is USEFUL: both codes are known constants, so a leg
# that drifts off 2744 or 3727 is a per-channel leak detector for free.
# The cost is that the pedestal no longer cancels
# in hardware -- it is subtracted in firmware from two codes instead of arriving
# pre-subtracted -- and that the two legs' gain errors no longer cancel either.
# Both are absorbed by ADCAL plus the air calibration.  VREF-independence, which
# the old wiring bought by referring the LMP ladder and the ADS FSR to the same
# node, is preserved BY WIRING and not by arithmetic: the LMP91000 ladder and the
# SAR's full scale are both /VREF_TRIM, so the ratio is fixed in copper.  There
# is no "measured /VREF_TRIM code" any more -- PA5 is nc() and the reference is
# never converted, because converting a reference against itself returns full
# scale whatever the reference does.
# R18, a 10k pull-up on the ADS1119 RESET pin, was already deleted; R19 (the
# ADC_DRDY pull-up) and C18/C19 (U8's 3V3A and 3V3D local decoupling) go with
# U8 itself.  C18 was U8's only claim on 3V3A here -- U4 and U7 carry their own.
add_passive("R24",165.1,147.32,"47k","Resistor_SMD:R_0603_1608Metric","3V3A","VA_MON",
            note="3V3A rail monitor divider top leg, into MCU PA7/ADC_IN7. NOT 1:2 any more: "
                 "R25 went 47k -> 27k on 2026-09-12, so the ratio is 27/74 and FIRMWARE is "
                 "VA_MON_MV = ADC x 74/27 = 2.741 x ADC, derived by gen_hw_contract.py as "
                 "O2P_HW_DIV_VA_NUM/DEN rather than written by hand. This IS the sourcing pass "
                 "the old note asked for. The position was 0.1% 10k (P2TC0603D1002LNTA) only "
                 "because R21/R22 once shared it, and those went with the trim and guard "
                 "dividers. Nothing downstream SCALES by this reading -- it is rail health. The "
                 "old note contrasted this pair with R34/R35, the 0.1% VREF_MON divider whose "
                 "ratio main.c promoted into g_cyc.vref_mv: THAT DIVIDER IS DELETED and the "
                 "reference is no longer measured at all, so the contrast no longer exists and "
                 "this pair is simply the only rail divider left that needs no precision. 47k "
                 "rather than 10k also drops the continuous draw on the analog rail feeding "
                 "U4/U7 (U8 is deleted) from 165 uA to 35 uA. Source impedance went 5k -> "
                 "23.5k on that pass and is 17.2k today with the 27k bottom leg, and that is "
                 "CHECKED, "
                 "not assumed: ST DS12232 Table 59 (Maximum ADC RAIN) allows 50k at 12 bits "
                 "and 160.5 sampling cycles, which is what mcu_adc.c already selects -- 2.9x "
                 "margin at 17.2k (it was 2.1x at 23.5k), and more in practice because Table "
                 "59 is quoted at a 35 MHz ADC "
                 "clock where this board runs 16 MHz. DO NOT RAISE THIS DIVIDER FURTHER: 100k "
                 "legs would put the source at exactly the 50k limit. It releases the "
                 "matched-pair placement adjacency the two-layer refloorplan work was holding")
add_passive("R25",165.1,157.48,"27k","Resistor_SMD:R_0603_1608Metric","VA_MON","GND",
            note="3V3A rail monitor divider bottom leg; see R24. 47k -> 27k on 2026-09-12 "
                 "because the ADC full scale became 2.500 V when VREF+ moved to /VREF_TRIM. "
                 "Ratio 27/74 = 0.3649, so 3.3 V reads 1.204 V and the CEILING RISES to "
                 "6.85 V -- BETTER than the 6.60 V this divider had against a 3.3 V full "
                 "scale, so the rail keeps its over-range headroom rather than losing it. "
                 "Source impedance also falls 23.5k -> 17.2k, further inside Table 59's 50k. "
                 "FIRMWARE follows automatically: gen_hw_contract.py derives "
                 "O2P_HW_DIV_VA_NUM/DEN from these two values")
add_passive("R26",165.1,167.64,"91k 1%","Resistor_SMD:R_0603_1608Metric","+12V_SW","VIN_MON",
            mpn="RC0603FR-0791KL",
            note="VIN monitor divider, was 130k/20k, then 82k/10k. 91k is the SAME ORDERED "
                 "LINE as R43/R44 and that is the only reason it is 91k rather than 82k -- "
                 "either is adequate for a supply monitor. FIRMWARE: ratio is 10/101 = 0.0990, "
                 "so 15V maps to 1.485V and 7V to 0.693V, both inside the 3.3V ADC, and source "
                 "impedance is 9.0k. hw_contract.h is GENERATED from these values, so the "
                 "firmware follows the change instead of silently rescaling")
add_passive("R27",165.1,177.8,"10k","Resistor_SMD:R_0603_1608Metric","VIN_MON","GND",
            note="VIN monitor divider bottom leg; see R26 for the firmware ratio. The MPN went "
                 "in a sourcing pass, not a spec change: RC0603FR-0710KL IS a generic 1% 0603 "
                 "10k, and that stock line already exists for R8/R18/R19/R28")
add_passive("R33",185.42,147.32,"1k","Resistor_SMD:R_0603_1608Metric","AFE_VOUT","ADC_AFE_VOUT", wired=True,
            note="ADC anti-alias/input-kickback filter. PLACE WITH C28 AT THE MCU, pin 20 / "
                 "PB1 / ADC_IN9 -- not at U8 AIN0, which is where this note said until "
                 "2026-09-12 and which no longer exists. The 100 nF must be close to the "
                 "SAMPLING pin because what it sources is the charge kick of the SAR's 5 pF "
                 "sample capacitor (DS12232 Table 58); placed at the far end it filters the "
                 "signal but not the kick")
add_passive("C28",208.28,147.32,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_AFE_VOUT","GND", wired=True)
# R39 is KEPT, against docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 3, which listed it for deletion.  The
# reason it was listed was proximity to the BMP390 block, not analysis, and its
# bench headroom gate is NOT closed: ads1119.c still reasons about where the
# oxygen channel sits relative to full scale, and AFE-BRING-UP-POSTMORTEM.md 175
# uses R39's DNP state in a live leakage argument.  4.7 mm2 and no BOM line is
# not worth foreclosing that.  Deleted DNPs on this board are ideas left behind;
# R39 and R4 are decisions left open.
add_passive("R39",208.28,157.48,"DNP 100k","Resistor_SMD:R_0603_1608Metric","ADC_AFE_VOUT","GND",dnp=True, wired=True,
            note="Optional AFE attenuation pad; bench headroom gate selects value")
add_passive("R37",185.42,167.64,"1k","Resistor_SMD:R_0603_1608Metric","WE_BUF","ADC_WE_BUF", wired=True,
            note="Bias-telemetry filter, WE leg. Matched with R38/C31 on the RE leg so the "
                 "differential pair sees equal source impedance; was the VA_MON feed")
add_passive("C30",208.28,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_WE_BUF","GND", wired=True)
add_passive("R38",185.42,177.8,"1k","Resistor_SMD:R_0603_1608Metric","RE_BUF","ADC_RE_BUF", wired=True,
            note="Bias-telemetry filter, RE leg; must match R37/C30 exactly. Note this taps the "
                 "BUFFER output, never CELL_RE itself -- the ADS1119's switched-cap input may "
                 "not sit on the sub-uA electrode, which is the whole reason U4B exists")
add_passive("C31",208.28,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_RE_BUF","GND", wired=True)
# D8 -- Schottky clamp, PA6 (VIN_MON) to AGND.  ADOPTED 2026-09-12.
#
# DS12232 TABLE 50 is the whole reason, and it is a table that must be read
# RENDERED, not through pdftotext, which collapses its merged first row:
#   all except PA4,PA5,PA6,PB0,PB3,PC0 ... negative -5 mA
#   PA4, PA5 ......................... negative -5 mA, positive 0 mA
#   PA6, PB0, PB3, PC0 ............... negative  0 mA
# PA6 tolerates ZERO negative injection, and it is the only analog channel with
# a path to the external supply cable -- R26's 91k from /+12V_SW.
#
# WHAT CHANGED IS NOT THE EXPOSURE, IT IS THE CONSEQUENCE.  PA6 carried VIN_MON
# before U8 was deleted.  What the deletion adds is the coupling: Table 60
# footnote 3 says injection on one analog pin degrades conversion on ANOTHER,
# and oxygen used to be immune by sitting on a different converter.  It no
# longer is.  Pre-existing item, promoted from cosmetic to load-bearing.
#
# SCHOTTKY, NOT THE 1N4148W ALREADY ON A STOCK LINE.  At the ~10 uA this can
# source through 91k a 1N4148W still drops ~0.45 V, and the MCU's own ESD
# structure starts conducting near -0.3 V, so the silicon part would let the
# internal diode share the current -- which is the exact thing being prevented.
# A BAT54 at 10 uA sits near -0.1 V and keeps the pad off.
#
# VIN_MON LEAKAGE ACCEPTANCE, 2026-09-12. Fab's decision relayed by revb-ee
# on channel revB: "relax the gate, record the number"; retain BAT54W-G3-08.
# Retire the earlier arbitrary Ir <= 1 uA at 1.2 V / 85 C selection gate.
# VIN_MON is health telemetry with 7 V / 15 V rail thresholds; it does not
# scale oxygen measurements. The earlier 18 mV budget was not a requirement.
# Provisional dsdig result, pending HUMAN OVERLAY VERIFICATION for the new
# chart class: 8.662 uA at VR=1.3314 V, Tj=85 C; about 78.0 mV at VIN_MON
# through R26||R27=9.0 kohm, about 0.79 V referred to the rail. This is a
# digitized TYPICAL-CURVE ESTIMATE, not a device measurement or maximum.
# 85 C uses log-current interpolation between plotted 75 C and 100 C curves;
# 1.3314 V is the common supported query point, not 1.2 V. Evidence and
# pending verification: datasheets/BAT54W-G-leakage-digitized/README.md.
# Do not use the provisional values as a qualified production error budget.
# Nominal 12 V is 3 V from 15 V and 5 V from 7 V. Reverse D8 leakage pulls the
# monitor DOWN, so its signed error approaches the 7 V undervoltage threshold.
# Typical curves do not guarantee worst-case accuracy at either boundary.
# This node-specific acceptance does not authorize clamps on oxygen inputs.
# Vishay 85885's 2 uA maximum is specified at 25 C / VR=25 V and does not
# bound leakage at 85 C. Fig. 3 shows typical 25/50/75/100/125 C leakage;
# the -40/25/125 C legend belongs to Fig. 1 FORWARD current.
#
# PART AND POLARITY, CORRECTED 2026-09-12 after the Codex PCB session found BOTH
# wrong in the first landing.  Recorded because the shape of the error matters:
#
#   POLARITY.  SCHOTTKY2 is Device:D_Schottky, whose PIN 1 IS THE CATHODE (see
#   its definition above, and D3's note, which says so in as many words).  The
#   first version passed ("GND", "VIN_MON"), putting the ANODE on VIN_MON -- a
#   diode that conducts above ~0.3 V and clamps the monitor permanently low,
#   the precise opposite of the intent stated in its own note.  verify() then
#   asserted ASSIGNED[("D8","1")] == "GND", so THE ASSERTION CONFIRMED THE BUG:
#   it was written from the code, not from the design statement.  The net order
#   below is now (VIN_MON, GND) = (K, A), and the assertion names the roles.
#
#   PACKAGE.  BAT54-7-F is SOT23, not SOD-123 -- Diodes DS11005 Rev 34-2,
#   Ordering Information.  A SOT-23 single needs a THREE-pin symbol, and KiCad
#   ships no authoritative one for that part, so keeping the MPN would have
#   meant hand-authoring a symbol -- exactly what authoritative_symbol() exists
#   to forbid.  Vishay BAT54W-G is the same 30 V / 200 mA single Schottky in
#   SOD-123 (Vishay 85885: Mechanical Data "Case: SOD-123", Parts Table
#   "Single"), so the footprint, the two-pin authoritative symbol and the land
#   pattern all stay as drawn.  BEWARE THE W SUFFIX: it means SOT-323 at Diodes
#   and at Nexperia but SOD-123 at Vishay, which is the likeliest source of the
#   original error.
#
#   ORDERED 2026-09-12 (Fab): DigiKey DE cut tape BAT54W-G3-08GICT-ND, EUR 0.42
#   at qty 1, 45 340 in stock at the time of the query (./dk_query.py, PI v4,
#   currency read back from SearchLocaleUsed rather than assumed).  audit_bom
#   will keep flagging D8 until purchase-orders.json is RE-CAPTURED from
#   InvenTree -- that file is a read-only snapshot of parts.fabi.me
#   /api/order/po-line/, last taken 2026-09-09, and must not be hand-edited.
#
#   THE value/mpn SPLIT BELOW IS DELIBERATE -- DO NOT "FIX" IT.  value carries
#   the family ("BAT54W-G"), mpn the orderable code with its packaging suffix
#   ("BAT54W-G3-08"), exactly as D3 does ("PMEG4010CEH" / "PMEG4010CEH,115").
#   audit_bom reconciles purchase orders against mpn, not value, so the family
#   name in value costs nothing.  I mis-read this as a sourcing defect on
#   2026-09-12 and proposed collapsing the two; that would have broken the
#   convention D3 sets without clearing any flag.
add_passive("D8", 246.38, 175.26, "BAT54W-G", "Diode_SMD:D_SOD-123",
            "VIN_MON", "GND", lib=SCHOTTKY2, angle=180, mpn="BAT54W-G3-08",
            note="Negative-injection clamp on PA6. Pin 1 is the CATHODE and goes to VIN_MON; "
                 "pin 2 is the ANODE and goes to AGND. It therefore sits reverse-biased at "
                 "+1.2 V in normal operation and conducts only when the pin is pulled below "
                 "ground. See the block comment above for the Table 50 rating, the part-class "
                 "argument against the 1N4148W, the leakage budget, and the 2026-09-12 "
                 "correction of both the polarity and the package")
add_passive("C32",226.06,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","VIN_MON","GND",
            note="VIN monitor reservoir at the MCU PA6 pin. VIN_MON lost its R38/C31 ADC filter "
                 "when AIN3 was taken for bias telemetry; source impedance is R26||R27 = 8.9k, "
                 "so the STM32G071 sampling cap needs this and the LONGEST sampling time")
add_passive("C33",226.06,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","VA_MON","GND",
            note="VA monitor reservoir at the MCU PA7 pin; same reason as C32. Source is "
                 "R24||R25 = 17.2k since R25 went 47k -> 27k on 2026-09-12 (it was 23.5k after "
                 "the 2026-09-05 BOM pass and 5k before that). Still far above the 5k this "
                 "note originally assumed, so the conclusion is unchanged: this reservoir is "
                 "MORE load-bearing, not less, because it is what absorbs the ADC's sampling "
                 "kick at the higher source impedance")
# R34/R35/R36/C29 and their monitor nets are deleted. REF3425 drives the
# ADC reference input U6.5/VREF+ directly; PA5/U6.16 remains unused. There is
# no conversion of VREF_TRIM as a signal channel. Reference collapse is
# detected by measuring internal VREFINT against this external full scale;
# this does not measure REF3425 drift. See the adopted 2026-09-12 specification.

place("U11",CELL,85.09,162.56,value="SGX-OX-ROHS-Mini",footprint="o2-probe:SGX-OX-ROHS-Mini_ISS2",
      mpn="SGX-OX-ROHS-Mini",
      note="DS-0637 Issue 2 pin/body geometry; elongated rear-flow aperture remains a first-article fit gate")
net("U11",1,"CELL_CE"); net("U11",2,"CELL_RE"); net("U11",3,"CELL_WE")

# TI SBOS488E: top-view DRL6 pin map, Table 1 and Table 3.
TMP302 = symbol("TMP302B", [("1","TRIPSET0","input"),("3","~{OUT}","open_collector"),
    ("6","TRIPSET1","input"),("2","GND","power_in"),
    ("4","HYSTSET","input"),("5","VS","power_in")],
    description="TMP302B autonomous thermostat; 85 C trip, nominal 75 C reset with all straps high")

# --------------------------------------------------------------------------- chamber sensors / membrane-ring heater
place("U10",TMP117,246.38,154.94,value="TMP117 CELL",footprint="tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI",mpn="TMP117AIDRVR")
for p,n in {1:"I2C_SCL",2:"GND",3:"HEATER_GATE",4:"3V3D",5:"3V3D",6:"I2C_SDA",7:"TMP_CELL_EP"}.items(): net("U10",p,n)
place("U12",SHT45,281.94,154.94,value="SHT45-AD1F",footprint="Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",mpn="SHT45-AD1F-R2")
for p,n in {1:"I2C_SDA",2:"I2C_SCL",3:"3V3D",4:"GND"}.items(): net("U12",p,n)
add_passive("C20",281.94,172.72,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",
            note="Local SHT45 supply bypass")
add_passive("C21",261.62,195.58,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",
            note="Local TMP117 supply bypass")

# U14/C23/C24, the DNP BMP390 pressure channel, are DELETED.  Never fitted, and
# the only user of o2-probe:BMP390_LGA10_DRAFT -- a footprint whose own note
# called its land geometry an open release gate, i.e. an unverified footprint
# carried on a released board.  It leaves the project library with the part.
# I2C address 0x76 is now unused and free for a future pressure channel.

place("Q2",NMOS,327.66,157.48,value="AO3400A",footprint="Package_TO_SOT_SMD:SOT-23",mpn="AO3400A")
net("Q2",1,"HEATER_GATE"); net("Q2",2,"GND",stub=2.54); net("Q2",3,"HEATER_LOW",stub=3.81)
add_passive("R28",307.34,147.32,"10k","Resistor_SMD:R_0603_1608Metric","HEATER_PWM","HEATER_GATE",
            note="Limits TMP117 ALERT-vs-PWM contention to <0.33 mA nominal")
add_passive("R29",307.34,160.02,"100k","Resistor_SMD:R_0603_1608Metric","HEATER_GATE","GND")
# RH1/RH2 stay on the main board (Fab, 2026-09-04).
#
# TWO DIFFERENT PARTS HAVE WORN THE REFERENCE J5, and Rev B removed both when
# only one was meant to go.  The deferred one (2026-09-09, plans/REVC-HEATED-RING.md)
# is the FORK TIP: a perpendicular ring PCB carrying its own heater, fed from
# +12V_HTR through F3, i.e. a second heater load.  That stays deferred, and the
# guard in verify() still forbids F3 and +12V_HTR.
#
# The one below is the Rev A part and a different thing entirely: two castellated
# solder lands that carry the metal membrane-carrier ring.  It adds no load - both
# lands are ONE node on HEATER_LOW, so the ring is a spreader, not a jumper and not
# a heater.  Removing it left RH1/RH2 dissipating into the board with no lands to
# couple them to the thing they exist to warm; the ring they drive was measured at
# 1.224 W and theta = 68 K/W on 2026-09-13 (commit aa6133d).  Restored on Fab's
# instruction, 2026-09-13.
add_passive("RH1",368.3,149.86,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
add_passive("RH2",368.3,165.1,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
place("J5",HEATED_RING,368.3,195.58,value="HEATED MEMBRANE RING",
      footprint="o2-probe:Heater_Ring_Lands",
      note="Manual-soldered dry-side metal membrane-carrier ring. TWO RING LANDS at the "
           "front edge, each present on FRONT AND BACK copper (Fab, 2026-09-13), 2.8 x 2.0 "
           "mm - no drills, no plated slots, no castellations: the ring is soldered flat, "
           "so none of that tooling bought anything. All four pads are number 1, i.e. ONE "
           "HEATER_LOW node, so the ring is a heat spreader and never a conductor. The "
           "back lands sit inside the HEATED_ISLAND_SPREADER pour, which is what connects "
           "them - no track is required, and one added in its place connected nothing; a "
           "via at each land ties the front land down to that pour. Width is 2x the first "
           "attempt; HEIGHT IS CAPPED AT 2.0 by /I2C_SDA reaching Y 136.45 under the left "
           "land, not by choice.")
net("J5",1,"HEATER_LOW")
place("U16",TMP302,327.66,198.12,value="TMP302BDRLR",footprint="o2-probe:TMP302_DRL6_TI",mpn="TMP302BDRLR",
      note="Autonomous HEATER_GATE clamp: TRIPSET1/0=11 gives 85 C; HYSTSET=VS gives nominal 10 C hysteresis. Not supply-failure safe; qualify thermal coupling and restart.")
for p,n in {1:"3V3D",2:"GND",3:"HEATER_GATE",4:"3V3D",5:"3V3D",6:"3V3D"}.items(): net("U16",p,n)
add_passive("C35",350.52,210.82,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",
            note="Local TMP302 supply bypass")
place("TP6",TESTPOINT,350.52,180.34,value="TMP_CELL_EP",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP6",1,"TMP_CELL_EP",stub=6.35)




# --------------------------------------------------------------------------- schematic wiring
def build_wiring() -> None:
    # 1. Power Input & Protection
    wire_path([pin_xy("J101", 1), (snap(30.48), snap(25.40)), pin_xy("F1", 1)])
    # F1 -> D3 -> +12V_SW, one line, one label per node.
    wire_path([pin_xy("F1", 2), pin_xy("D3", 2)])
    wire_path([pin_xy("D3", 1), (snap(88.90), snap(25.40))])
    junc((snap(88.90), snap(25.40)))

    # 2. POWER CHAIN, drawn as wires and read left to right (Fab, 2026-09-12:
    #    "structure it human readable, use wires, no label-soup").  Seven labels
    #    name the seven nets in this block; no pin here carries its own.
    #
    #      +12V_SW -> U1 AP63203 -> L1 -> 3V3D -> R32 -> 3V3A
    #                                       \-> U15 REF3425 -> VREF_TRIM
    gnd_y = snap(60.96)
    rail_y = snap(34.29)          # the height L1, R32 and the rails share
    top_y = snap(22.86)           # the 12 V feed and the reference tap

    # --- 12 V in.  EN strapped to VIN: always on, no sequencing.
    wire_path([pin_xy("C1", 1), (snap(88.90), top_y), (snap(93.98), top_y),
               (snap(93.98), pin_xy("U1", 2)[1])])
    wire_path([(snap(93.98), pin_xy("U1", 3)[1]), pin_xy("U1", 3)])
    wire_path([(snap(93.98), pin_xy("U1", 2)[1]), pin_xy("U1", 2)])
    junc((snap(93.98), pin_xy("U1", 3)[1]))
    rail("+12V_SW", (snap(88.90), top_y), 0)

    # --- switching node and bootstrap
    sw_y = pin_xy("U1", 5)[1]
    wire_path([pin_xy("U1", 5), (snap(147.32), sw_y), pin_xy("L1", 1)])
    wire_path([(snap(129.54), sw_y), pin_xy("C2", 2)])
    junc((snap(129.54), sw_y))
    wire_path([pin_xy("C2", 1), (snap(120.65), pin_xy("C2", 1)[1]),
               (snap(120.65), pin_xy("U1", 6)[1]), pin_xy("U1", 6)])
    rail("BUCK_SW", (snap(116.84), sw_y), 0)
    rail("BUCK_BST", (snap(120.65), pin_xy("C2", 1)[1]), 180)

    # --- 3V3D: buck output.  Feeds its own FB pin, both 22 uF caps, R32 into
    #     the analog domain, and the reference's input.
    wire_path([pin_xy("L1", 2), (pin_xy("R32", 1)[0], rail_y)])
    wire_path([pin_xy("U1", 1), (snap(157.48), pin_xy("U1", 1)[1]), (snap(157.48), rail_y)])
    junc((snap(157.48), rail_y))
    for _ref in ("C3", "C4"):
        wire_path([(pin_xy(_ref, 1)[0], rail_y), pin_xy(_ref, 1)])
        junc((pin_xy(_ref, 1)[0], rail_y))
    wire_path([(snap(187.96), rail_y), (snap(187.96), top_y),
               (pin_xy("U15", 4)[0], top_y), pin_xy("U15", 4)])
    junc((snap(187.96), rail_y))
    rail("3V3D", (snap(152.40), rail_y), 0)
    place("#FLG04", PWRFLAG, snap(170.18), snap(15.24), value="PWR_FLAG", footprint="",
          in_bom=False)
    net("#FLG04", 1, "3V3D", stub=2.54)

    # --- reference, sitting below the rail in its own clear block.  EN strapped
    #     to IN; force AND sense both land on VREF_TRIM.
    feed_x = snap(187.96)
    wire_path([(feed_x, rail_y), (feed_x, snap(73.66)), pin_xy("U15", 4)])
    junc((feed_x, rail_y))
    wire_path([(pin_xy("C36", 1)[0], snap(73.66)), pin_xy("C36", 1)])
    junc((pin_xy("C36", 1)[0], snap(73.66)))
    wire_path([pin_xy("U15", 4), pin_xy("U15", 3)])
    junc(pin_xy("U15", 4))
    wire_path([pin_xy("U15", 6), pin_xy("U15", 5)])
    wire_path([pin_xy("U15", 6), (pin_xy("C10", 1)[0], pin_xy("U15", 6)[1]), pin_xy("C10", 1)])
    junc(pin_xy("U15", 6))
    rail("VREF_TRIM", (snap(256.54), pin_xy("U15", 6)[1]), 180)

    # --- 3V3A: the AFE domain, behind R32 with C7 and C8.
    wire_path([pin_xy("R32", 2), (pin_xy("C8", 1)[0], rail_y)])
    for _ref in ("C7", "C8"):
        wire_path([(pin_xy(_ref, 1)[0], rail_y), pin_xy(_ref, 1)])
        junc((pin_xy(_ref, 1)[0], rail_y))
    rail("3V3A", (snap(218.44), rail_y), 0)
    place("#FLG05", PWRFLAG, snap(213.36), snap(15.24), value="PWR_FLAG", footprint="",
          in_bom=False)
    net("#FLG05", 1, "3V3A", stub=2.54)

    # --- ground bus.  Split either side of the reference feed so the feed
    #     crosses nothing; both segments carry the same label, so they are the
    #     same net -- that is what a label is FOR, as against naming every pin.
    wire_path([(pin_xy("C1", 2)[0], gnd_y), (pin_xy("C4", 2)[0], gnd_y)])
    wire_path([(pin_xy("C7", 2)[0], gnd_y), (pin_xy("C8", 2)[0], gnd_y)])
    for _ref in ("C1", "C3", "C4", "C7", "C8"):
        wire_path([pin_xy(_ref, 2), (pin_xy(_ref, 2)[0], gnd_y)])
        junc((pin_xy(_ref, 2)[0], gnd_y))
    wire_path([pin_xy("U1", 4), (snap(91.44), pin_xy("U1", 4)[1]), (snap(91.44), gnd_y)])
    junc((snap(91.44), gnd_y))
    # The reference block gets its own short ground run BELOW it. Routing its
    # GND pins up to the main bus would drive them straight through U15's own
    # pin column (GND_F shares x with IN and EN) and through VREF_TRIM -- two
    # shorts that ERC caught. Same label, same net; that is what labels are for.
    ref_gnd_y = snap(86.36)
    wire_path([(pin_xy("C36", 2)[0], ref_gnd_y), (pin_xy("C10", 2)[0], ref_gnd_y)])
    for _r, _pin in (("U15", "1"), ("U15", "2"), ("C10", "2"), ("C36", "2")):
        wire_path([pin_xy(_r, _pin), (pin_xy(_r, _pin)[0], ref_gnd_y)])
        junc((pin_xy(_r, _pin)[0], ref_gnd_y))
    rail("GND", (snap(252.73), ref_gnd_y), 0)
    rail("GND", (snap(104.14), gnd_y), 0)
    rail("GND", (snap(216.00), gnd_y), 0)

    filt_gnd_x = snap(218.44)   # shared ground column for both filter stacks
    # BYPASS RELOCATION -- mechanism in place, registrations PARKED.
    # Fab, 2026-09-12: "put bypass caps near the components they are supplying."
    # Correct, and bypass_at()/apply_bypass() below do it. The registrations are
    # commented out because moving a capacitor AFTER net() has already anchored
    # its label leaves the label behind, and the half-finished pass shorted GND
    # to 3V3D. Re-enable only together with: marking each moved cap wired, so
    # the connection is the wire and not a stale label; and re-running ERC,
    # audit_schematic.py and audit_layout.py after EACH cap, not after all of
    # them. Distances to fix, measured: C11 31 mm, C12/C13 36-39 mm, C14 40 mm,
    # C16 38 mm, C19 43 mm, C21 41 mm, C25 35 mm from the pins they decouple.

    # (The MCU bypass BANK that stood here is DELETED. Grouping C12/C13/C14/C26
    # on one bus read tidily and said nothing: the sheet no longer showed which
    # capacitor belonged to which supply pin. They now sit beside U6's VDD,
    # VREF+ and VBAT pins -- see bypass_at() above.)

    # --- ADC input anti-alias filters, drawn as wires.
    #     Each was previously TWO labels of the same net facing each other
    #     across a 10 mm gap, which is where the text collided. One wire, one
    #     label, one ground drop per filter.
    filt_gnd_y = snap(210.82)   # clear of R35/C29, whose own pins sit at 212.09
    for _r, _c, _net, _src in (("R33", "C28", "ADC_AFE_VOUT", "AFE_VOUT"),
                               ("R37", "C30", "ADC_WE_BUF", "WE_BUF"),
                               ("R38", "C31", "ADC_RE_BUF", "RE_BUF")):
        rail(_src, pin_xy(_r, 1), 180)
        wire_path([pin_xy(_r, 2), pin_xy(_c, 1)])
        rail(_net, pin_xy(_r, 2), 0)
        wire_path([pin_xy(_c, 2), (filt_gnd_x, pin_xy(_c, 2)[1])])
        junc((filt_gnd_x, pin_xy(_c, 2)[1]))
    # R39 is the DNP headroom gate; it taps the first filter's output node.
    wire_path([pin_xy("R39", 1), (pin_xy("R39", 1)[0], pin_xy("R33", 2)[1])])
    junc((pin_xy("R39", 1)[0], pin_xy("R33", 2)[1]))
    wire_path([pin_xy("R39", 2), (filt_gnd_x, pin_xy("R39", 2)[1])])
    junc((filt_gnd_x, pin_xy("R39", 2)[1]))
    wire_path([(filt_gnd_x, pin_xy("C28", 2)[1]), (filt_gnd_x, filt_gnd_y)])
    rail("GND", (filt_gnd_x, filt_gnd_y), 0)

    # 4. Precision Reference & Electrometer Buffers
    wire_path([pin_xy("U4", 1), (snap(233.68), snap(31.75)), (snap(233.68), snap(25.40)), (snap(259.08), snap(25.40)), (snap(259.08), snap(31.75)), pin_xy("U4", 2)])
    wire_path([pin_xy("U4", 7), (snap(233.68), snap(39.37)), (snap(233.68), snap(44.45)), (snap(261.62), snap(44.45)), (snap(261.62), snap(36.83)), pin_xy("U4", 6)])
    wire_path([pin_xy("R40", 2), (snap(276.86), snap(27.94)), (snap(276.86), snap(43.18)), pin_xy("TP5", 1)])

    # 5. RS-485
    wire_path([pin_xy("R2", 2), (snap(19.05), snap(87.63)), (snap(17.78), snap(87.63)), pin_xy("D2", 1)])
    wire_path([pin_xy("R3", 2), (snap(19.05), snap(99.06)), (snap(33.02), snap(99.06)), pin_xy("D2", 2)])
    # 6. MCU Decoupling & Debug
    # (C11's link to U5.8 and the C12/C13/C14/C26 chain are DELETED: each of
    # those capacitors is now placed against the supply pin it serves and wired
    # there by apply_bypass(). Chaining them in a row said which caps existed,
    # not which pin each one decouples.)
    nrst_y = snap(80.01)
    wire_path([(snap(152.40), nrst_y), (snap(152.40), snap(93.98)), pin_xy("C15", 1)])
    junc((snap(152.40), nrst_y))
    wire_path([pin_xy("U6", 36), (snap(119.38), snap(119.38)), (snap(152.40), snap(119.38)), (snap(152.40), snap(104.14)), pin_xy("R9", 1)])

    # 7. AFE & Cell
    wire_path([pin_xy("U7", 9), (snap(33.02), snap(163.83)), (snap(33.02), snap(170.18)), pin_xy("C17", 2)])
    wire_path([pin_xy("U7", 2), (snap(60.96), snap(154.94)), (snap(60.96), snap(147.32)), (snap(16.51), snap(147.32)), pin_xy("R17", 1)])
    wire_path([pin_xy("U7", 6), (snap(63.50), snap(160.02)), (snap(63.50), snap(142.24)), (snap(12.70), snap(142.24)), (snap(12.70), snap(160.02)), pin_xy("C16", 1)])
    wire_path([pin_xy("R42", 2), (snap(38.10), snap(187.96)), pin_xy("D7", 1)])
    wire_path([pin_xy("R43", 2), (snap(105.41), snap(193.04)), (snap(97.79), snap(193.04)), pin_xy("R44", 1)])
    wire_path([pin_xy("U7", 12), (snap(50.80), snap(167.64)), pin_xy("TP1", 1)])

    # 8. ADC & Dividers
    wire_path([pin_xy("R33", 2), (snap(200.66), snap(147.32)), pin_xy("C28", 1)])
    wire_path([(snap(200.66), snap(147.32)), (snap(200.66), snap(157.48)), pin_xy("R39", 1)])
    junc((snap(200.66), snap(147.32)))
    wire_path([pin_xy("R37", 2), pin_xy("C30", 1)])
    wire_path([pin_xy("R38", 2), pin_xy("C31", 1)])
    # (The old hard-coded 199.39 routing for this divider is DELETED. It was
    # written against the pre-2026-09-12 positions and, once the block moved,
    # ran straight through R35's ground wire -- shorting VREF_MON_RAW to GND
    # while the connectivity audit still passed, because the generator's own
    # model never saw the stale geometry. Coordinates in wires come from
    # pin_xy(), never from literals.)
    wire_path([pin_xy("R24", 2), (snap(168.91), snap(152.40)), (snap(161.29), snap(152.40)), pin_xy("R25", 1)])
    wire_path([pin_xy("R26", 2), (snap(168.91), snap(172.72)), (snap(161.29), snap(172.72)), pin_xy("R27", 1)])

    # 9. Chamber Sensors & Heater
    # Local straps and bypass. OUT shares HEATER_GATE with TMP117 ALERT.
    wire_path([pin_xy("U16",1),(316.23,195.58),(316.23,198.12),pin_xy("U16",6)])
    wire_path([(316.23,198.12),(316.23,200.66),pin_xy("U16",4)])
    junc((316.23,198.12))
    wire_path([pin_xy("U16",5),(340.36,200.66),(340.36,210.82),pin_xy("C35",1)])
    wire_path([pin_xy("U16",2),(363.22,198.12),(363.22,210.82),pin_xy("C35",2)])
    gate_split = (snap(318.77), snap(157.48))
    wire_path([pin_xy("R28", 2), (snap(318.77), snap(147.32)), gate_split, pin_xy("Q2", 1)])
    wire_path([gate_split, (snap(318.77), snap(165.10)), (snap(303.53), snap(165.10)), pin_xy("R29", 1)])
    junc(gate_split)
    htr_low_split = (snap(375.92), snap(149.86))
    wire_path([pin_xy("Q2", 3), (snap(330.20), snap(144.78)), (snap(375.92), snap(144.78)), htr_low_split, pin_xy("RH1", 2)])
    wire_path([htr_low_split, (snap(375.92), snap(165.10)), pin_xy("RH2", 2)])
    junc(htr_low_split)
    wire_path([pin_xy("RH1", 1), (snap(360.68), snap(149.86)), (snap(360.68), snap(165.10)), pin_xy("RH2", 1)])
    wire_path([pin_xy("U10", 7), (snap(234.95), snap(158.75)), (snap(234.95), snap(180.34)), pin_xy("TP6", 1)])

build_wiring()


def symbol_block(lib_id: str) -> str:
    s = SYMS[lib_id]
    if s.get("source_block"):
        return s["source_block"]
    name = s["name"]; hh = s["half_h"]; hw = s["half_w"]
    out = [f'(symbol "{lib_id}"', '\t(pin_names (offset 0.508))', '\t(exclude_from_sim no)', '\t(in_bom yes)', '\t(on_board yes)',
           f'\t(property "Reference" "{s["ref_prefix"]}" (at -5.08 {hh + 5.08:g} 0) (effects (font (size 1.27 1.27))))',
           f'\t(property "Value" "{name}" (at 5.08 {hh + 2.54:g} 0) (effects (font (size 1.27 1.27)) (justify right)))',
           '\t(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
           '\t(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
           f'\t(property "Description" "{esc(s["description"])}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))']
    graphics = s.get("graphics")
    if graphics is None:
        out.append(f'\t(symbol "{name}_0_1" (rectangle (start {-hw:g} {hh:g}) (end {hw:g} {-hh:g}) (stroke (width 0.254) (type default)) (fill (type background))))')
    else:
        out.append(f'\t(symbol "{name}_0_1"')
        out.extend(f'\t\t{item}' for item in graphics)
        out.append('\t)')
    out.append(f'\t(symbol "{name}_1_1"')
    for num, pin_name, etype in s["pins"]:
        x,y,ang,_,_ = s["geom"][num]
        out.append(f'\t\t(pin {etype} line (at {x:g} {y:g} {ang}) (length {s["pin_len"]:g}) (name "{esc(pin_name)}" (effects (font (size 1.0 1.0)))) (number "{num}" (effects (font (size 1.0 1.0)))))')
    out.extend(['\t)', '\t(embedded_fonts no)', ')'])
    return "\n".join(out)


def emit_library() -> str:
    blocks = []
    for k in sorted(SYMS):
        block = symbol_block(k).replace(f'(symbol "{k}"', f'(symbol "{SYMS[k]["name"]}"', 1)
        blocks.append("\t" + block.replace("\n", "\n\t"))
    return '(kicad_symbol_lib\n\t(version 20231120)\n\t(generator "gen_sch.py")\n\t(generator_version "10.0")\n' + "\n".join(blocks) + '\n)\n'


def emit_schematic() -> str:
    a = ['(kicad_sch', '\t(version 20250114)', '\t(generator "gen_sch.py")', '\t(generator_version "10.0")', f'\t(uuid "{uid("root")}")', '\t(paper "A2")',
         '\t(title_block (title "O2 Probe Rev B — SGX-OX Mini / LMP91000 / STM32G071 / RS-485") (comment 1 "GENERATED by gen_sch.py — edit generator, not schematic") (comment 2 "J3 is PRE-POT ONLY; post-pot update is over RS-485 bootloader") (comment 3 "SGX footprint remains a physical-sample gate"))', '\t(lib_symbols']
    for k in sorted(SYMS): a.extend('\t\t' + ln for ln in symbol_block(k).splitlines())
    a.append('\t)')
    for jx, jy in sorted(JUNCTIONS):
        a.append(f'\t(junction (at {jx:g} {jy:g}) (diameter 0) (color 0 0 0 0) (uuid "{uid("j", jx, jy)}"))')
    for x1,y1,x2,y2 in WIRES:
        a.append(f'\t(wire (pts (xy {x1:g} {y1:g}) (xy {x2:g} {y2:g})) (stroke (width 0) (type default)) (uuid "{uid("w",x1,y1,x2,y2)}"))')
    for x,y in NOCONN: a.append(f'\t(no_connect (at {x:g} {y:g}) (uuid "{uid("nc",x,y)}"))')
    for text,x,y,ang in LABELS:
        just = "right" if ang == 180 else "left"
        a.append(f'\t(label "{esc(text)}" (at {x:g} {y:g} {ang}) (effects (font (size 1.0 1.0)) (justify {just} bottom)) (uuid "{uid("label",text,x,y)}"))')
    for ref in sorted(INST):
        i=INST[ref]; s=SYMS[i["lib_id"]]; x=i["x"]; y=i["y"]
        a.extend(['\t(symbol',f'\t\t(lib_id "{i["lib_id"]}")',f'\t\t(at {x:g} {y:g} {i["angle"]})','\t\t(unit 1)','\t\t(exclude_from_sim no)',f'\t\t(in_bom {"yes" if i["in_bom"] else "no"})',f'\t\t(on_board {"yes" if i["footprint"] else "no"})',f'\t\t(dnp {"yes" if i["dnp"] else "no"})',f'\t\t(uuid "{uid("sym",ref)}")',
                  ])
        # A power symbol IS its own label: the graphic states the net, so its
        # reference and value are HIDDEN. Printing them would put "#PWR07" and
        # "GND" beside every ground on the sheet, which is precisely the text
        # soup this conversion exists to remove.
        ptxt = " hide" if ref.startswith("#PWR") else ""
        a.extend([f'\t\t(property "Reference" "{ref}" (at {x-5.08:g} {y-s["half_h"]-5.08:g} 0) (effects (font (size 1.0 1.0)){ptxt}))',
                  f'\t\t(property "Value" "{esc(i["value"])}" (at {x+5.08:g} {y-s["half_h"]-2.54:g} 0) (effects (font (size 1.0 1.0)) (justify right){ptxt}))',
                  f'\t\t(property "Footprint" "{esc(i["footprint"])}" (at {x:g} {y:g} 0) (effects (font (size 1.27 1.27)) hide))'])
        for key,val in (("MPN",i["mpn"]),("Design Note",i["note"])):
            if val: a.append(f'\t\t(property "{key}" "{esc(val)}" (at {x:g} {y:g} 0) (effects (font (size 1.27 1.27)) hide))')
        for num,_,_ in s["pins"]: a.append(f'\t\t(pin "{num}" (uuid "{uid("pin",ref,num)}"))')
        a.extend(['\t\t(instances',f'\t\t\t(project "{NAME}" (path "/{uid("root")}" (reference "{ref}") (unit 1)))','\t\t)','\t)'])
    a.extend(['\t(sheet_instances (path "/" (page "1")))','\t(embedded_fonts no)',')'])
    return "\n".join(a)+"\n"


def verify() -> None:
    if INST["U16"]["mpn"] != "TMP302BDRLR" or INST["U16"]["dnp"]:
        raise ValueError("U16 must be fitted TMP302BDRLR")
    if {p: ASSIGNED[("U16",p)] for p in "123456"} != dict(zip("123456",["3V3D","GND","HEATER_GATE","3V3D","3V3D","3V3D"])):
        raise ValueError("TMP302 85 C / 10 C hysteresis pin mapping changed")
    expected={(ref,num) for ref,i in INST.items() for num,_,_ in SYMS[i["lib_id"]]["pins"]}
    assert expected == set(ASSIGNED), f"pin assignment mismatch missing={expected-set(ASSIGNED)} extra={set(ASSIGNED)-expected}"
    assert all(i["footprint"] or ref.startswith("#") for ref,i in INST.items())
    assert not any(n == "" for n in ASSIGNED.values())
    # A typed component must carry both the designated library identity and a
    # conventional embedded graphic.  This prevents a generic box from being
    # hidden behind a plausible Device:* name.
    expected_symbol = {}
    for ref in INST:
        if ref.startswith("RV"):
            expected_symbol[ref] = POT
        elif ref.startswith("DZ"):
            expected_symbol[ref] = ZENER2
        elif ref.startswith("R"):
            expected_symbol[ref] = RES2
        elif ref.startswith("C"):
            expected_symbol[ref] = CAP2
        elif ref.startswith("F"):
            expected_symbol[ref] = POLYFUSE2
        elif ref.startswith("L"):
            expected_symbol[ref] = INDUCTOR2
        elif ref == "D1":
            expected_symbol[ref] = TVS2
        elif ref == "D2":
            expected_symbol[ref] = SM712
        elif ref in ("D3", "D8"):
            expected_symbol[ref] = SCHOTTKY2
        elif ref.startswith("D"):
            expected_symbol[ref] = TVS3
        elif ref == "Q2":
            expected_symbol[ref] = NMOS
        elif ref.startswith("TP"):
            expected_symbol[ref] = TESTPOINT
        elif ref in ("J101", "J102", "J103", "J104", "J105", "J106"):
            expected_symbol[ref] = WIRE_LAND if ref in ("J103", "J104", "J105", "J106") else CONN1
    for ref, lib_id in expected_symbol.items():
        actual = INST[ref]["lib_id"]
        if actual != lib_id:
            raise ValueError(f"{ref} must use {lib_id}, not {actual}")
        if lib_id in (RES2, CAP2, POLYFUSE2, INDUCTOR2, TVS2, ZENER2, SCHOTTKY2,
                      PMOS, NMOS, POT, TESTPOINT, CONN1) and not SYMS[lib_id].get("source_block"):
            raise ValueError(f"{ref} designated symbol {lib_id} is not library-derived")
    forbidden = {"o2-probe:PASSIVE_2", "o2-probe:CAPACITOR_2"}
    used_forbidden = {i["lib_id"] for i in INST.values()} & forbidden
    if used_forbidden:
        raise ValueError(f"generic placeholder symbols are forbidden: {sorted(used_forbidden)}")
    # Locked interface/address facts.
    # The ADS1119 is gone and must STAY gone: its address strap, its DRDY net and
    # the VREF divider are all checked by absence, not by inspection.
    assert "U8" not in INST
    assert not ({"R19", "C18", "C19", "R34", "R35", "R36", "C29"} & INST.keys())
    assert not ({"ADC_DRDY", "VREF_MON_RAW", "ADC_VREF_MON"} & set(ASSIGNED.values()))
    assert ASSIGNED[("U10","4")] == "3V3D"                            # TMP117 0x49
    # F3 and its +12V_HTR feed are the optional Rev C FORK-TIP branch - a second
    # heater load - and stay out of Rev B.  J5 is NOT part of that branch: it is
    # the membrane-ring spreader and carries no load, so it is required here.
    # Asserted separately because bundling them is what deleted J5 in the first place.
    assert "F3" not in INST, "F3 is the deferred Rev C ring-feed fuse; see plans/REVC-HEATED-RING.md"
    assert "+12V_HTR" not in ASSIGNED.values()
    assert "J5" in INST, "J5 (membrane-ring lands) missing; RH1/RH2 would heat the board"
    assert ASSIGNED[("J5", "1")] == "HEATER_LOW", \
        f"J5 must be the HEATER_LOW spreader node, got {ASSIGNED[('J5','1')]}"
    assert INST["J5"]["footprint"] == "o2-probe:Heater_Ring_Lands", \
        ("J5 must use the plain SMD ring lands. Heater_Ring_Solder_Lands is the "
         "superseded castellated form and Ring_Fork_Tip_DRAFT the deferred Rev C fork.")
    # The heat source stays on this board (Fab, 2026-09-04).  Both elements must
    # bridge +12V_SW to HEATER_LOW, i.e. sit above Q2, never below it.
    for _rh in ("RH1", "RH2"):
        assert _rh in INST, _rh
        assert ASSIGNED[(_rh, "1")] == "+12V_SW", _rh
        assert ASSIGNED[(_rh, "2")] == "HEATER_LOW", _rh
    assert ASSIGNED[("U7","2")] == "AFE_MENB" and ASSIGNED[("R17","2")] == "GND"
    assert ASSIGNED[("J3","2")] == "SWDIO" and ASSIGNED[("J3","4")] == "SWCLK_BOOT0"
    assert ASSIGNED[("Q2","1")] == ASSIGNED[("U10","3")] == "HEATER_GATE"
    # Load-bearing physical package maps, keyed by package pin number.
    assert {p: ASSIGNED[("U1", p)] for p in map(str, range(1, 7))} == {
        "1": "3V3D", "2": "+12V_SW", "3": "+12V_SW", "4": "GND",
        "5": "BUCK_SW", "6": "BUCK_BST",
    }  # AP63203 DS41326: 1 FB, 2 EN, 3 VIN, 4 GND, 5 SW, 6 BST
    assert {p: ASSIGNED[("D2", p)] for p in ("1", "2", "3")} == {
        "1": "RS485_A_CABLE", "2": "RS485_B_CABLE", "3": "GND",
    }  # Littelfuse SM712-02HTG SOT-23
    # THVD1410 SOIC-8, SLLSEY3E "Pin Functions": 1 R, 2 /RE, 3 DE, 4 D, 5 GND,
    # 6 A, 7 B, 8 VCC.  Pins 2 and 3 are the REV B split and the assertion that
    # matters: they are opposite-polarity enables and Rev A tied them together,
    # which made the 0.1 uA standby state uncommandable.  If they are ever the
    # same net again the split has been undone -- fail here, not on a bench.
    assert {p: ASSIGNED[("U5", p)] for p in map(str, range(1, 9))} == {
        "1": "RS485_RX", "2": "RS485_RE", "3": "RS485_DE", "4": "RS485_TX",
        "5": "GND", "6": "RS485_A", "7": "RS485_B", "8": "3V3D",
    }
    assert ASSIGNED[("U5", "2")] != ASSIGNED[("U5", "3")], \
        "/RE and DE share a net again: THVD1410 standby is uncommandable"
    # Both enables must keep a PASSIVE default, because both GPIOs are
    # high-impedance out of reset.  R7 -> DE low = driver off (main.c's bus-jam
    # release path, which must not depend on this CPU running code).  R45 -> /RE
    # low = receiver ON, so a probe that resets into the bootloader can still
    # hear the bus.  Neither resistor may be deleted or repurposed.
    assert ASSIGNED[("R7", "1")] == "RS485_DE" and ASSIGNED[("R7", "2")] == "GND"
    assert ASSIGNED[("R45", "1")] == "RS485_RE" and ASSIGNED[("R45", "2")] == "GND"
    assert INST["R7"]["value"] == INST["R45"]["value"] == "47k"
    # The split is worthless if RE did not actually reach its own MCU pin.
    assert ASSIGNED[("U6", "30")] == "RS485_DE" and ASSIGNED[("U6", "31")] == "RS485_RE"
    # U4 is two electrometer followers. Each half must be wired as a follower
    # (output strapped to its own inverting input) and sit on the CELL node
    # itself, not on a divider: an input swap here silently turns the guard into
    # a comparator and loses the bias telemetry.
    assert ASSIGNED[("U4", "1")] == ASSIGNED[("U4", "2")] == "WE_BUF"
    assert ASSIGNED[("U4", "3")] == "CELL_WE"
    assert ASSIGNED[("U4", "6")] == ASSIGNED[("U4", "7")] == "RE_BUF"
    assert ASSIGNED[("U4", "5")] == "CELL_RE"
    # The guard is driven from the real RE follower through R40, never from a
    # divider replica (POTTING.md 1.3). GUARD_REPLICA keeps its name only
    # because the PCB guard-fill and thermal-barrier scripts key off it.
    assert ASSIGNED[("R40", "1")] == "RE_BUF" and ASSIGNED[("R40", "2")] == "GUARD_REPLICA"
    assert not any(n == "GUARD_DIV" for n in ASSIGNED.values())
    # REV B, 2026-09-12 (Path A): there is no 5 V rail and no LDO. R32 is the
    # ONLY thing between the buck and the AFE, and the reference is its own part.
    assert not any(n in ("+5V", "+5V_ANALOG", "VREF_SHUNT") for n in ASSIGNED.values())
    assert not ({"U2", "U3", "C5", "C6", "C27", "R41", "C9", "R31"} & INST.keys())
    assert ASSIGNED[("R32", "1")] == "3V3D" and ASSIGNED[("R32", "2")] == "3V3A"
    assert ASSIGNED[("C7", "1")] == ASSIGNED[("C8", "1")] == "3V3A"
    # REF3425 is KELVIN-sensed: force and sense must both land, and EN must be
    # tied to IN.  A future "make the rail gateable" edit has to fail here.
    assert {p: ASSIGNED[("U15", p)] for p in map(str, range(1, 7))} == {
        "1": "GND", "2": "GND", "3": "3V3D", "4": "3V3D",
        "5": "VREF_TRIM", "6": "VREF_TRIM",
    }  # SBAS804G Table 5-1: 1 GND_F, 2 GND_S, 3 EN, 4 IN, 5 OUT_S, 6 OUT_F
    assert INST["U15"]["value"] == "REF3425IDBVR"
    # No adjustable part may set the bias: the cell is swappable with the board
    # potted, so a trimmer would be unreachable after cure (POTTING.md 1.2).
    assert not any(ref.startswith("RV") for ref in INST)
    # AZ431-A N package (SOT-23) is 1 REF, 2 CATHODE, 3 ANODE -- NOT the TI
    # TL431DBZ map the donor graphic arrived with. REF strapped to the cathode is
    # what makes this a 2.5 V two-terminal shunt.
    # A pin map is not an identity. REF3320 (2.048 V) or REF3330 (3.0 V) would
    # pass a pin-map check unchanged while silently invalidating the 2500 mV the
    # firmware contract asserts.  REV B 2026-09-12: the part and its bias
    # network are now the REF3425 asserted above; the AZ431's IKA-window check
    # retires with R41, because a series reference has no bias resistor to get
    # wrong.  What replaces it is the force/sense and EN-tied-to-IN assertion.
    # Every 100n decoupling capacitor shares ONE land, so the BOM carries a single
    # 100n line and assembly a single feeder. C2, C11 and C15 were 0603 against
    # seventeen 0402s. Deliberately scoped to 100n: the rule guards against buying
    # a HIGH-rated position to a LOW-rated line, which is a downgrade rather than
    # a tidy-up. It does not forbid the reverse, and C7 is now the reverse -- it
    # was 10 V 0805 and is now the 25 V 1206 part C1 already buys, which is more
    # derating headroom on a 5 V rail, one line fewer, and the last 0805 off the
    # board. Assert BOTH directions of that below.
    hundred_n = {ref: i["footprint"] for ref, i in INST.items()
                 if ref.startswith("C") and i["value"].startswith("100n")}
    assert len(set(hundred_n.values())) == 1, sorted(
        (fp, ref) for ref, fp in hundred_n.items())
    # 0805 is gone in BOTH families -- R32 and C7 were the sole users, and each
    # was there for a reason that survived the move (a bead option that 0603 also
    # offers; a voltage rating that went UP). A part reappearing in 0805 should
    # have to argue for the land, not inherit it.
    assert not any("0805" in i["footprint"] for i in INST.values()), sorted(
        (r, i["footprint"]) for r, i in INST.items() if "0805" in i["footprint"])
    # The DIELECTRIC is part of the identity, not decoration: C7 carried "X7R"
    # before it was consolidated onto C1's line, and asserting only "10u 25V"
    # would let a Y5V part satisfy both. TPS7A20 (SLVSD95) recommends
    # X5R/X7R/C0G for the LDO input and discourages Y5V.
    assert INST["C7"]["value"] == INST["C1"]["value"] == "10u 25V X7R"
    assert INST["C7"]["footprint"] == INST["C1"]["footprint"]
    # The expansion connector and the BMP390 option are DELETED, not re-drawn
    # smaller: a Micro-Fit or an unverified DRAFT land creeping back is the exact
    # regression this deletion exists to prevent (docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 3).
    # No draft footprint remains in the Rev B design.
    assert not any("Micro-Fit" in i["footprint"] for i in INST.values()), sorted(
        (r, i["footprint"]) for r, i in INST.items() if "Micro-Fit" in i["footprint"])
    assert not any("DRAFT" in i["footprint"] for r, i in INST.items()), sorted(
        (r, i["footprint"]) for r, i in INST.items()
        if "DRAFT" in i["footprint"])
    assert not any(n.startswith("EXP_") for n in ASSIGNED.values())
    # The DNPs survive on argument, never on indecision: a termination a farm
    # cable can need, an AFE headroom gate still open, and (2026-09-12) a 3V3A
    # bypass held unfitted until the Path A rail spectrum is measured.
    assert {r for r, i in INST.items() if i.get("dnp")} == {"R4", "R39", "C8", "C4"}, sorted(
        r for r, i in INST.items() if i.get("dnp"))
    # REV B 2026-09-12: the "keep bulk OFF the cathode" rule (C9 1n, R31 47R)
    # was an AZ431 STABILITY constraint and dies with the shunt.  The REF3425
    # wants the opposite -- SBAS804G gives a stable CL range of 0.1..10 uF ON
    # the output pin -- so C10 now sits directly on VREF_TRIM and must stay
    # inside that window.
    assert ASSIGNED[("C10", "1")] == "VREF_TRIM" and INST["C10"]["value"] == "4.7u"
    # REV B: the analog channels land on the MCU's own SAR, and the ADC's FULL
    # SCALE is the REF3425 -- VREF+ on pin 5 is driven from /VREF_TRIM, which is
    # the single fact the whole 2026-09-12 decision turns on. Assert it directly:
    # if pin 5 ever goes back to 3V3D, VDDA re-enters the oxygen derivation at
    # 0.718 mV/mV and nothing else in this file would notice.
    assert ASSIGNED[("U6", "5")] == "VREF_TRIM"           # VREF+, NOT 3V3D
    assert ASSIGNED[("U6", "20")] == "ADC_AFE_VOUT"       # PB1 / ADC_IN9
    # PA5 returned to the pool: converting the reference against itself saturates
    # at 4095. A channel re-added here would read a constant and look healthy.
    assert ASSIGNED[("U6", "16")] == "(NC)"
    # NO resistor may sit on this net -- it is now the converter's full scale, so
    # a divider here would rescale every channel, not just one reading. The R31
    # exemption this check used to carry was vestigial (a Rev A part verify()
    # already asserts absent); an exemption for a part that cannot exist is a
    # hole with no floor.
    assert not any(r.startswith("R") and n == "VREF_TRIM"
                   for (r, _p), n in ASSIGNED.items())
    # The 100 nF local to pin 5, and the REF3425's stable load range. C10 4.7 uF
    # + C26 100 nF = 4.8 uF, inside SBAS804G's 0.1..10 uF.
    assert ASSIGNED[("C26", "1")] == "VREF_TRIM" and INST["C26"]["value"] == "100n"
    # VA_MON rescaled for the 2.5 V full scale. Exact, because a half-applied
    # change here silently rescales the rail monitor.
    assert INST["R24"]["value"] == "47k" and INST["R25"]["value"] == "27k"
    # The PA6 clamp. Table 50 rates PA6 at 0 mA negative injection and it is the
    # only analog channel with a path to the external supply cable.
    # D8 POLARITY.  Stated in terms of the diode's ROLES, not of whichever net
    # order the add_passive() call happens to use, because the previous form of
    # this assertion was transcribed from the code and so passed on a REVERSED
    # clamp.  Device:D_Schottky pin 1 = K, pin 2 = A; the clamp must be reverse-
    # biased by the +1.2 V that VIN_MON normally sits at, so K is the VIN_MON
    # side.  If these two are ever swapped the diode conducts above ~0.3 V and
    # pins the supply monitor low.
    d8_k, d8_a = ASSIGNED[("D8", "1")], ASSIGNED[("D8", "2")]
    assert (d8_k, d8_a) == ("VIN_MON", "GND"), \
        f"D8 reversed: cathode(pin1)={d8_k} anode(pin2)={d8_a}, want K=VIN_MON A=GND"
    assert INST["D8"]["footprint"] == "Diode_SMD:D_SOD-123", \
        "D8 footprint must match a TWO-terminal part; BAT54-7-F is SOT23, not SOD-123"
    # VIN monitor divider. The value is pinned because firmware converts the ADC
    # reading with this exact ratio; changing one leg without the other silently
    # rescales every reported input voltage.
    # Exact, not startswith: a review mutated R26 to "91k nonsense" and both this
    # check and gen_hw_contract.py's ohms() accepted it.
    assert ASSIGNED[("R26", "2")] == "VIN_MON" and INST["R26"]["value"] == "91k 1%"
    assert ASSIGNED[("R27", "1")] == "VIN_MON" and INST["R27"]["value"] == "10k"
    # Bias telemetry: the ADS1119 pair must read the BUFFERED electrodes, and the
    # two legs must be matched, or the differential measurement acquires a
    # source-impedance error larger than the bias it is there to resolve.
    # PA0 and PA1 -- ADJACENT pins of IDENTICAL I/O structure (FT_a), so the pad
    # leakage that DS12232 Table 51 bounds at +/-70 nA common-modes out of the
    # difference. Splitting this pair across an FT_a and a TT_a pin would put a
    # 2x leakage mismatch straight into the measured bias.
    assert ASSIGNED[("U6", "11")] == "ADC_WE_BUF" and ASSIGNED[("U6", "12")] == "ADC_RE_BUF"
    assert INST["R37"]["value"] == INST["R38"]["value"] == "1k"
    assert INST["C30"]["value"] == INST["C31"]["value"] == "100n"
    # The ADC must never be hung directly on the sub-uA electrode. The earlier
    # form of this was `== "RE_BUF" != "CELL_RE"`, whose tail compares two string
    # literals and is constant-true -- it read like a check and was not one.
    assert ASSIGNED[("R38", "1")] == "RE_BUF"
    # Exact set, not a subset: this fails when a load is ADDED to the reference
    # electrode, which is the direction audit_schematic.py structurally cannot see.
    cell_re_pins = {(r, pn) for (r, pn), n in ASSIGNED.items() if n == "CELL_RE"}
    assert cell_re_pins == {("U7", "13"), ("U11", "2"), ("U4", "5")}, cell_re_pins
    # Exact package identity and ground pin, independently checked against
    # SLLSEJ9E Table 5-1. Grounding IO2 instead leaves the real ground floating.
    assert INST["D7"]["mpn"] == "TPD2E2U06QDBZRQ1"
    assert ASSIGNED[("D7", "1")] == "CELL_CE"
    assert ASSIGNED[("D7", "3")] == "GND"
    assert ASSIGNED[("D7", "2")] == "(NC)"
    assert INST["R42"]["value"] == "1k 1%"
    assert INST["R42"]["mpn"] == "RC0603FR-071KL"
    # CE now reaches the cell through R42, so nothing but R42/R43/D7 may sit on
    # the driven pin, and the electrode side must carry the cell and its pad.
    assert {(r, pn) for (r, pn), n in ASSIGNED.items() if n == "CELL_CE_DRV"} == {
        ("U7", "14"), ("R42", "1"), ("R43", "1")}
    assert {(r, pn) for (r, pn), n in ASSIGNED.items() if n == "CELL_CE"} == {
        ("R42", "2"), ("U11", "1"), ("TP3", "1"), ("D7", "1")}
    assert ASSIGNED[("U6", "15")] == "CE_MON"
    # Both rail monitors now land on the MCU's own ADC.
    assert ASSIGNED[("U6", "17")] == "VIN_MON" and ASSIGNED[("U6", "18")] == "VA_MON"


def main() -> int:
    apply_bypass()
    place_grounds()   # must run before verify(): it creates the #PWR instances
    verify()
    LIB_OUT.parent.mkdir(parents=True, exist_ok=True)
    LIB_OUT.write_text(emit_library())
    OUT.write_text(emit_schematic())
    print(f"wrote {OUT}")
    print(f"wrote {LIB_OUT}")
    print(f"components: {sum(not r.startswith('#') for r in INST)}; pins assigned: {len(ASSIGNED)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
