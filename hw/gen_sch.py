#!/usr/bin/env python3
"""Generate the Rev-A O2 probe schematic and its project symbol library.

The generator is the source of truth.  The emitted schematic is deliberately
flat and label-connected: each functional block can be reviewed independently,
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
LABELS: list[tuple[str, float, float, int]] = []
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
RING_FORK = symbol(
    "RING_PCB_FORK_TIP", [("1", "HTR_HI", "passive"), ("2", "HTR_LO", "passive")], "J",
    description="Solder lands at the two fork-finger tips for the perpendicular heater ring PCB",
)

# Connector pins are drawn on one side in physical pin order.  Besides reading
# like the cable pinout, this prevents long adjacent right-side labels from
# sharing the same connection stroke in KiCad's label renderer.
for _lid in (CONN4, CONN6, CONN8):
    _pins = SYMS[_lid]["pins"]
    for _i, (_num, _name, _etype) in enumerate(_pins):
        SYMS[_lid]["geom"][_num] = (-7.62, (len(_pins)-1)*2.54 - _i*5.08, 0, _name, _etype)
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


TVS3 = symbol("TVS_ARRAY_2CH", [("1", "IO1", "passive"), ("2", "GND", "passive"), ("3", "IO2", "passive")], "D")
SM712 = symbol("SM712", [("1", "LINE_A", "passive"), ("2", "LINE_B", "passive"), ("3", "GND", "passive")], "D",
               description="Littelfuse SM712-02HTG asymmetric RS-485 TVS, SOT-23")

BUCK = symbol("AP63205WU", [
    ("1", "FB", "input"), ("2", "EN", "input"), ("3", "VIN", "power_in"),
    ("4", "GND", "power_in"), ("5", "SW", "power_out"), ("6", "BST", "passive"),
], description="AP63205 fixed 5 V synchronous buck, TSOT-23-6")
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
ADS = symbol("ADS1119", [
    ("1", "RESET", "input"), ("2", "DGND", "power_in"), ("3", "AGND", "power_in"),
    ("4", "AIN3", "input"), ("5", "AIN2", "input"), ("6", "REFN", "input"),
    ("7", "REFP", "input"), ("8", "AIN1", "input"), ("9", "AIN0", "input"),
    ("10", "AVDD", "power_in"), ("11", "DVDD", "power_in"), ("12", "DRDY", "open_collector"),
    ("13", "SDA", "bidirectional"), ("14", "SCL", "input"), ("15", "A0", "input"),
    ("16", "A1", "input"), ("17", "EP", "power_in"),
], description="16-bit four-channel delta-sigma ADC, external reference, WQFN-16")
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
MCU_OUTPUTS = {12, 13, 19, 28, 29}
MCU_INPUTS = {10, 14, 20, 21, 22, 32}
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
    LABELS.append((name, x, y, 180 if angle == 0 else 0))
    ASSIGNED[key] = name


def nc(ref: str, pin: str | int) -> None:
    pin = str(pin)
    key = (ref, pin)
    assert key not in ASSIGNED
    x, y, _ = pin_pos(ref, pin)
    NOCONN.append((x, y))
    ASSIGNED[key] = "(NC)"


def add_passive(ref: str, x: float, y: float, value: str, fp: str, a: str, b: str,
                *, mpn: str = "", dnp: bool = False, note: str = "") -> None:
    if ref.startswith("C"):
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
    angle = 90 if lib_id in (RES2, CAP2, POLYFUSE2, INDUCTOR2) else 0
    place(ref, lib_id, x, y, value=value, footprint=fp,
          mpn=mpn, dnp=dnp, note=note, angle=angle)
    net(ref, 1, a); net(ref, 2, b)


# --------------------------------------------------------------------------- power input / buck
for ref,y,value,n in (
    ("J101",27.94,"J1.1 BROWN +12V","+12V_RAW"),
    ("J102",33.02,"J1.2 WHITE GND","GND"),
    ("J103",38.10,"J1.3 GREEN A","RS485_A_CABLE"),
    ("J104",43.18,"J1.4 YELLOW B","RS485_B_CABLE"),
):
    place(ref, CONN1, 38.10 if ref in ("J103","J104") else 20.32, y, value=value,
          footprint="Connector_Wire:SolderWire-0.25sqmm_1x01_D0.65mm_OD1.7mm_Relief",
          note="One of four independent farm-bus cable solder pads")
    net(ref,1,n)
add_passive("F1", 40.64, 30.48, "0.75A PTC", "o2-probe:PTC_1206_3216Metric", "+12V_RAW", "+12V_FUSED",
            mpn="0ZCJ0075AF2E",
            note="Bel Fuse 0ZCJ 1206 PPTC: IH 0.75A, IT 1.5A, Vmax 16Vdc, Imax 100A. "
                 "Vmax leaves 1V over the 15V input maximum; do not raise the input range "
                 "without re-rating. IH derates to 0.52A at 60C and 0.36A at 85C")
add_passive("D1", 40.64, 43.18, "SMBJ15A-13-F", "Diode_SMD:D_SMB", "+12V_FUSED", "GND", mpn="SMBJ15A-13-F")
place("Q1", PMOS, 62.23, 30.48, value="DMP3130L", footprint="Package_TO_SOT_SMD:SOT-23",
      mpn="DMP3130L-7",
      note="Reverse-polarity PMOS, drain to input, source to load. Was labelled 'DMP3010L-7', which names no orderable part: DS35716 shows the DMP3010L family as TO-252 and DS32239 as PowerDI5060-8, neither of which fits this SOT-23 land. DS31524 Rev 7-3 p.2 rates VGSS at +/-12 V ONLY, so DZ1 is mandatory, not optional")
net("Q1",1,"VIN_GATE"); net("Q1",2,"+12V_SW"); net("Q1",3,"+12V_FUSED")
add_passive("R1", 60.96, 43.18, "100k", "Resistor_SMD:R_0603_1608Metric", "VIN_GATE", "GND")
add_passive("DZ1", 78.74, 43.18, "10V ZENER", "Diode_SMD:D_SOD-123", "+12V_SW", "VIN_GATE",
            mpn="BZT52C10-E3-08",
            note="Q1 VGS clamp, K to the PMOS source; 10V SOD-123. Was a 12V BZT52C12, whose "
                 "GUARANTEED max VZ of 12.7 V at 5 mA (DS18004) exceeds the DMP3130L +/-12 V "
                 "VGSS absolute maximum -- the old part never bounded VGS. Vishay doc 86342 "
                 "gives BZT52C10 as 9.50/10/10.50 V at IZT 5 mA with aVZ +5..+8 mV/C. VZ rises "
                 "with current, so VZ(30 uA) <= VZ(5 mA) <= 10.50 V; at +85 C the bound is "
                 "10.50 + 0.008*60 = 10.98 V, inside 12 V with ~1.0 V margin. Cold end: "
                 "9.50 - 0.52 = 8.98 V, still far above Q1 threshold. Clamp dissipation at "
                 "15 V in is (15-10.5)/100k = 45 uA, 0.5 mW in a 410 mW part")
place("#FLG01", PWRFLAG, 20.32, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG01",1,"+12V_RAW")
place("#FLG02", PWRFLAG, 35.56, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG02",1,"GND")
place("#FLG03", PWRFLAG, 50.8, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG03",1,"+12V_SW")
place("#FLG04", PWRFLAG, 66.04, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG04",1,"+5V")
place("#FLG05", PWRFLAG, 81.28, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG05",1,"+5V_ANALOG")

place("U1", BUCK, 106.68, 33.02, value="AP63205WU-7", footprint="Package_TO_SOT_SMD:TSOT-23-6", mpn="AP63205WU-7")
for p,n in {1:"+5V",2:"+12V_SW",3:"+12V_SW",4:"GND",5:"BUCK_SW",6:"BUCK_BST"}.items(): net("U1",p,n)
add_passive("C1", 88.9, 43.18, "10u 25V", "Capacitor_SMD:C_1206_3216Metric", "+12V_SW", "GND")
add_passive("C2", 106.68, 48.26, "100n", "Capacitor_SMD:C_0402_1005Metric", "BUCK_BST", "BUCK_SW",
            note="AP63205 bootstrap. Was 0603; consolidated onto the one 100n land the rest of "
                 "the board uses. It only ever sees the BST-SW differential of about 5 V "
                 "despite riding the switching node, so a 0402 is amply rated, and the shorter "
                 "loop is marginally better for gate drive")
add_passive("L1", 129.54, 30.48, "4.7u SHIELDED", "Inductor_SMD:L_6.3x6.3_H3", "BUCK_SW", "+5V",
            mpn="SRN6028C-4R7M",
            note="AP63205 DS41326 Table 3 value for 5V out. Bourns 4.7uH +/-20%, Isat 3.2A, "
                 "Irms 3.1A, DCR 30mOhm, 6.0x6.0x2.8mm. LAND MISMATCH: the generic "
                 "L_6.3x6.3_H3 pads (1.5x2.4mm at +/-2.75) cover only ~2.4mm2 of this "
                 "part's 5.8x1.6mm terminal; Bourns recommends 2.0x6.5mm pads at +/-2.25. "
                 "Solderable for a first article, reduced shear strength -- see FAB-NOTES")
add_passive("C3", 129.54, 43.18, "22u", "Capacitor_SMD:C_1206_3216Metric", "+5V", "GND")
add_passive("C4", 147.32, 43.18, "22u", "Capacitor_SMD:C_1206_3216Metric", "+5V", "GND")

# --------------------------------------------------------------------------- digital/analog rails and trimmed reference
for ref,x,rail in (("U2",175.26,"3V3D"),("U3",203.2,"3V3A")):
    place(ref,LDO,x,33.02,value="TPS7A2033PDBVR",footprint="Package_TO_SOT_SMD:SOT-23-5",mpn="TPS7A2033PDBVR")
    ldo_input = "+5V_ANALOG" if ref == "U3" else "+5V"
    for p,n in {1:ldo_input,2:"GND",3:ldo_input,5:rail}.items(): net(ref,p,n)
    nc(ref,4)
add_passive("C5",165.1,45.72,"1u","Capacitor_SMD:C_0603_1608Metric","+5V","GND")
add_passive("C6",182.88,45.72,"1u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND")
add_passive("R32",190.5,20.32,"10R","Resistor_SMD:R_0805_2012Metric","+5V","+5V_ANALOG",
            note="Fitted damped analog prefilter; footprint may take 0R or characterized bead after bench validation")
add_passive("C7",190.5,58.42,"10u 10V X7R","Capacitor_SMD:C_0805_2012Metric","+5V_ANALOG","GND",
            note="Place directly at U3 IN/GND; include DC-bias derating in effective capacitance")
add_passive("C27",210.82,60.96,"100n","Capacitor_SMD:C_0402_1005Metric","+5V_ANALOG","GND",
            note="High-frequency U3 input bypass; place directly at pins 1/2")
add_passive("C8",213.36,45.72,"1u","Capacitor_SMD:C_0603_1608Metric","3V3A","GND")

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
place("U15",AZ431,215.9,101.6,value="AZ431BN-ATRG1",footprint="Package_TO_SOT_SMD:SOT-23",
      mpn="AZ431BN-ATRG1",
      note="2.5 V reference, wired as a two-terminal shunt (REF strapped to the cathode). "
           "REPLACES the deleted R20 / RV1 / R21 trim divider: POTTING.md section 1.2 "
           "(../../../ha/farming/compostlab/o2-probe/) requires the cell to be swappable with "
           "the board potted, so no adjustable part may set the bias. AZ431-A datasheet "
           "Rev 3.4: B grade is the 0.4% bin, 2.490/2.500/2.510 V, and deviation over "
           "-40..85 C is 4.5 mV typ / 10 mV max, so the worst-case window is 2.480..2.520 V. "
           "PACKAGE PIN MAP IS NOT THE TI ONE -- N package is 1 REF, 2 CATHODE, 3 ANODE, "
           "where TI's TL431DBZ is 1 K, 2 REF, 3 A; see the symbol comment. Biased from "
           "+5V_ANALOG through R41 and NOT from 3V3A: the part needs IKA >= 1.0 mA "
           "(recommended operating conditions) and 3V3A leaves only 3.234 - 2.510 = 0.724 V "
           "of headroom, about 6% margin over that minimum, where +5V_ANALOG leaves 2.5 V")
net("U15",1,"VREF_SHUNT"); net("U15",2,"VREF_SHUNT"); net("U15",3,"GND")
add_passive("R41",215.9,86.36,"1.5k 1%","Resistor_SMD:R_0603_1608Metric","+5V_ANALOG","VREF_SHUNT",
            mpn="RC0603FR-071K5L",
            note="AZ431 bias resistor. (5.0 - 2.5)/1.5k = 1.67 mA nominal; at a -2% rail and "
                 "the 2.510 V grade limit it is still 1.59 mA, comfortably over the 1.0 mA "
                 "IKA minimum, and the ~27 uA drawn by the reference node is negligible "
                 "beside it. Costs 1.67 mA on +5V_ANALOG, which is 17 mV more drop across "
                 "R32 -- U3 still has ample headroom for 3.3 V out")
add_passive("C9",233.68,86.36,"1n","Capacitor_SMD:C_0603_1608Metric","VREF_SHUNT","GND",
            note="Cathode HF decoupling, deliberately SMALL. AZ431-A Figure 15 (stability "
                 "boundary vs load capacitance, VKA=VREF curve) shows two stable regions with "
                 "an unstable band between them; at our ~1.6 mA cathode current the lower "
                 "stable region runs to roughly 10 nF. 1 n sits well inside it. The bulk "
                 "capacitance is C10, held OFF the cathode by R31 on purpose -- DO NOT move a "
                 "microfarad-scale cap onto this node, and do not raise this value, without "
                 "re-reading that figure. Chart reading, not a specified number: confirm on "
                 "the bench before release")
add_passive("R31",233.68,101.6,"47R","Resistor_SMD:R_0603_1608Metric","VREF_SHUNT","VREF_TRIM",
            note="Isolates C10's bulk capacitance from the AZ431 cathode, which is what keeps "
                 "the shunt out of its unstable band (see C9). It was originally the OPA2333's "
                 "capacitive-load isolation and happens to be exactly right here -- note it "
                 "would have been WRONG for a series reference like the REF33xx, which "
                 "requires 0.1-10 uF ON its output pin. The 26.9 uA drawn by R34/R35 across "
                 "47R is a 1.25 mV offset that does not matter: it lands on VREF_TRIM, which is "
                 "BOTH the LMP91000 bias reference and the ADS1119 external reference, so it "
                 "cancels ratiometrically. Net name VREF_TRIM is retained despite there no "
                 "longer being a trimmer -- firmware/src/lmp91000.h and "
                 "firmware/tools/gen_hw_contract.py key off it")
add_passive("C10",215.9,116.84,"4.7u","Capacitor_SMD:C_0603_1608Metric","VREF_TRIM","GND")
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
place("TP4",TESTPOINT,289.56,30.48,value="VREF",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP4",1,"VREF_TRIM")
place("TP5",TESTPOINT,289.56,43.18,value="GUARD",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP5",1,"GUARD_REPLICA")

# --------------------------------------------------------------------------- RS-485 and MCU
place("U5",RS485,35.56,91.44,value="THVD1410DR",footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",mpn="THVD1410DR")
for p,n in {1:"RS485_RX",2:"RS485_DE",3:"RS485_DE",4:"RS485_TX",5:"GND",6:"RS485_A",7:"RS485_B",8:"3V3D"}.items(): net("U5",p,n)
add_passive("R2",15.24,82.55,"10R","Resistor_SMD:R_0603_1608Metric","RS485_A","RS485_A_CABLE")
add_passive("R3",15.24,93.98,"10R","Resistor_SMD:R_0603_1608Metric","RS485_B","RS485_B_CABLE")
place("D2",SM712,25.40,105.41,value="SM712-02HTG",footprint="Package_TO_SOT_SMD:SOT-23",mpn="SM712-02HTG",
      note="Littelfuse asymmetric RS-485 TVS; locate cable-side of R2/R3")
net("D2",1,"RS485_A_CABLE"); net("D2",2,"RS485_B_CABLE"); net("D2",3,"GND")
add_passive("R4",55.88,82.55,"120R DNP","Resistor_SMD:R_0603_1608Metric","RS485_A","RS485_B",dnp=True)
add_passive("R5",55.88,93.98,"680R DNP","Resistor_SMD:R_0603_1608Metric","3V3D","RS485_A",dnp=True)
add_passive("R6",55.88,105.41,"680R DNP","Resistor_SMD:R_0603_1608Metric","RS485_B","GND",dnp=True)
add_passive("R7",73.66,105.41,"47k","Resistor_SMD:R_0603_1608Metric","RS485_DE","GND")
add_passive("C11",73.66,82.55,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")

place("U6",MCU,111.76,99.06,value="STM32G071CBT7",footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",mpn="STM32G071CBT7")
# Group the three RS-485 controls at the MCU's left edge and bring BOTH rail
# monitors into PA6/ADC_IN6 (VIN) and PA7/ADC_IN7 (VA).  VIN_MON moved here from
# ADS1119 AIN3, which the cell bias telemetry now occupies. These generator-owned assignments materially
# shorten the compact placement's routes without changing functionality.
# Pin 15 is PA4 = ADC1_IN4, one of four ADC-capable pins (11/12/15/16 =
# PA0/PA1/PA4/PA5) left nc() on this part. CE telemetry costs one of them and no
# ADS1119 channel.
MCU_NETS = {4:"3V3D",5:"3V3D",6:"3V3D",7:"GND",10:"NRST",13:"UART2_TX",14:"UART2_RX",15:"CE_MON",17:"VIN_MON",18:"VA_MON",19:"AFE_MENB",20:"ADC_DRDY",21:"EXP_INT",28:"HEATER_PWM",29:"RS485_TX",30:"RS485_DE",32:"RS485_RX",35:"SWDIO",36:"SWCLK_BOOT0",42:"SWO",45:"I2C_SCL",46:"I2C_SDA"}
for p in range(1,49):
    if p in MCU_NETS: net("U6",p,MCU_NETS[p])
    else: nc("U6",p)
add_passive("C12",139.7,83.82,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C13",139.7,93.98,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C14",139.7,104.14,"4.7u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND")
add_passive("C26",139.7,114.3,"1u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND",
            note="Place at MCU VREF+ pin 5")
add_passive("R8",160.02,83.82,"10k","Resistor_SMD:R_0603_1608Metric","NRST","3V3D")
add_passive("C15",160.02,93.98,"100n","Capacitor_SMD:C_0402_1005Metric","NRST","GND")
add_passive("R9",160.02,104.14,"100k","Resistor_SMD:R_0603_1608Metric","SWCLK_BOOT0","GND")
add_passive("R10",177.8,83.82,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SCL","3V3D")
add_passive("R11",177.8,93.98,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SDA","3V3D")

place("J3",CONN6,203.2,88.9,value="TC2030 SWD PRE-POT",footprint="Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",note="1=VTREF 2=SWDIO 3=NRST 4=SWCLK 5=GND 6=SWO")
for p,n in enumerate(("3V3D","SWDIO","NRST","SWCLK_BOOT0","GND","SWO"),1): net("J3",p,n)

# --------------------------------------------------------------------------- expansion connector
place("J2",CONN8,274.32,91.44,value="EXPANSION / K33",footprint="Connector_Molex:Molex_Micro-Fit_3.0_43045-0815_2x04_P3.00mm_Vertical",dnp=True,note="Tube-height gate; pad-field fallback permitted")
for p,n in enumerate(("+12V_SW","GND","EXP_3V3","EXP_SDA","EXP_SCL","EXP_INT_OUT","EXP_TX","EXP_RX"),1): net("J2",p,n)
add_passive("F2",251.46,78.74,"0.20A PTC DNP","o2-probe:PTC_1206_3216Metric","3V3D","EXP_3V3",dnp=True)
for ref,y,a,b in (("R12",86.36,"I2C_SDA","EXP_SDA"),("R13",96.52,"I2C_SCL","EXP_SCL"),("R14",106.68,"EXP_INT","EXP_INT_OUT"),("R15",116.84,"UART2_TX","EXP_TX"),("R16",127.0,"UART2_RX","EXP_RX")):
    add_passive(ref,251.46,y,"33R DNP","Resistor_SMD:R_0603_1608Metric",a,b,dnp=True)
place("D4",TVS3,302.26,86.36,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D4",1,"EXP_SDA"); net("D4",2,"GND"); net("D4",3,"EXP_SCL")
place("D5",TVS3,302.26,101.6,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D5",1,"EXP_TX"); net("D5",2,"GND"); net("D5",3,"EXP_RX")
place("D6",TVS3,302.26,116.84,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D6",1,"EXP_INT_OUT"); net("D6",2,"GND"); nc("D6",3)

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
for ref,y,n in (("TP1",149.86,"CELL_WE"),("TP3",170.18,"CELL_CE")):
    place(ref,TESTPOINT,76.2,y,value=n,footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net(ref,1,n)

# --------------------------------------------------------------------------- CE branch: limit, watch, clamp
# A1 died on 2026-09-04 (AFE-BRING-UP-POSTMORTEM.md) and nothing on the board
# could say so: the bench needed an evening with a DMM on chip leads to decide
# which of four parts was guilty, and once potted that method does not exist.
# CELL_CE therefore stops being a bare wire from pin 14 to the cell.
#
# R42 caps the current A1 can deliver into a fault. It sits INSIDE the control
# loop -- RE is sensed separately, so A1 servos out the drop and DC accuracy is
# untouched. 100R, not the 1k that the postmortem's 100R-1k range also allows:
# the drop is added to what pin 14 must produce. SNAS506 6.5's
# 300 mV <= VCE <= VS-300 mV is the condition under which A1's OPEN-LOOP GAIN is
# characterised, not a hard output-compliance limit -- outside it the amplifier
# is unspecified rather than guaranteed broken -- but "unspecified" is not a
# region to design a buried, unrepairable probe into, so treat 3000 mV at 3.3 V
# as the working ceiling and spend as little of it as possible. At the measured 99.09 uA cell current 1k costs 99 mV
# and 100R costs 9.9 mV; during the polarisation transient the same bench
# measured (>607 uA before the TIA saturated) 1k costs over 600 mV and 100R
# costs 61 mV.
#
# The sentence that used to sit here claimed "100R limits to 33 mA at full rail,
# still well under A1's 10 mA charging spec". That is backwards and was caught in
# review: 3.3 V / 100 ohm is 33 mA, which is ABOVE 10 mA, not below. So 100R does
# NOT impose a ceiling under the device's own charging capability -- 1k would give
# 3.3 mA and 330R about 10 mA. The real position: neither value has been derived
# from a defined maximum fault current, source impedance, pulse energy and
# loop-stability limit, because none of those is characterised for this cell.
# 100R is the LOW-REGRET choice under that uncertainty, not the optimum -- it
# costs at most 13 mV at DS-0637's 130 uA maximum, so it cannot meaningfully
# erode a compliance margin we have not yet measured, whereas 1k costs up to
# 130 mV and could. Characterise the real-cell CE operating point -- which
# R43/R44 now make possible -- and then derive the value properly.
#
# NOTE the earlier arithmetic that justified this was WRONG and is not repeated
# here: the "125 mV of margin" figure comes from CE at 2875 mV, measured with a
# 1M/1M DUMMY drawing 0.6 uA, while 99.09 uA is the REAL cell. Those are
# different operating points and the drop at one cannot be subtracted from the
# margin at the other. What survives is the transient case, which needs no
# baseline at all. The real cell's CE operating point has never been measured --
# R43/R44 exist partly to measure it.
add_passive("R42",25.4,187.96,"100R","Resistor_SMD:R_0603_1608Metric","CELL_CE_DRV","CELL_CE",
            mpn="RC0603FR-07100RL",
            note="CE fault-current limit, inside the control loop so it costs no DC accuracy. "
                 "Do NOT raise toward 1k without re-checking the CE compliance budget: the drop "
                 "is spent from SNAS506 6.5's 300 mV..VS-300 mV window")

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
            note="CE monitor divider bottom leg. 200k total keeps the load on A1's output at "
                 "~16 uA of its 750 uA drive spec; a 10k pair would take 144 uA. The value is set "
                 "by the ADC's 50 kohm max source impedance AT TOLERANCE, not by the load")
add_passive("C34",121.92,198.12,"100n","Capacitor_SMD:C_0402_1005Metric","CE_MON","GND",
            note="Sampling reservoir for the ~50k divider source. The STM32G0 ADC samples onto a "
                 "small S&H capacitor; this supplies that charge locally so the long sampling "
                 "time the bare divider would need is not the only thing holding the reading up")

# ESD, partially. CELL_CE and CELL_WE and CELL_RE are handled by a person, in a
# field, with the board potted -- POTTING.md requires the cell to be swappable --
# and they run straight into a 3.3 V front end with no protection of any kind.
# What killed A1 is unknown and will stay unknown; ESD is the cheapest candidate
# to defend against.
#
# Only CE is defended HERE, and the reason is a leakage budget, not laziness:
#   CE  driven output. Leakage is irrelevant. Protect it now.
#   WE  carries the cell current INTO the TIA, so clamp leakage adds directly to
#       the measurand. It sits at 1.678 V, so a reverse-biased clamp does leak.
#       The bound is ~70 nA for 0.1% of the 70 uA minimum signal -- plausible for
#       this part but NOT verified against SBAS/TPD data, so it is not fitted on
#       a guess. Sourcing gate, not a design gate.
#   RE  budgeted in picoamps against the LMP91000's own +/-900 pA IRE. A general
#       -purpose TVS leaks orders of magnitude more, hot. Needs a part with a
#       stated leakage figure over -40..80 C entered into that budget.
# TPD2E2U06 is reused rather than newly chosen: it is already qualified and
# stocked in this design (D4/D5/D6), and D6 already demonstrates the one-channel
# -unused pattern.
#
# OPEN QUALIFICATION, recorded rather than assumed away: clamping CE to board
# ground while RE and WE float is a partial protection NETWORK, and a partial
# network is not automatically better than none. A common-mode strike arriving at
# RE can in principle be converted into differential current through the cell
# toward the one clamp that exists. Whether that is worse than leaving all three
# open is unverified -- it needs the sensor's transient model, the protection
# return geometry, clamp curves, and pin-to-pin plus common-mode ESD testing.
# Do not describe this as "the cell electrodes are protected".
place("D7",TVS3,45.72,187.96,value="TPD2E2U06",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",
      note="Cell-electrode ESD clamp, CE channel only. The second channel is deliberately "
           "unused: WE needs a verified leakage figure before it may be clamped, and RE needs "
           "a picoamp-class part. Do not casually wire either to the spare pin")
net("D7",1,"CELL_CE"); net("D7",2,"GND"); nc("D7",3)

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
place("TP2",TESTPOINT,76.2,190.5,value="GND",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False)
net("TP2",1,"GND")

place("U8",ADS,111.76,162.56,value="ADS1119IRTER",footprint="Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm",
      mpn="ADS1119IRTER",
      note="Buy from MOUSER (595-ADS1119IRTER), which sells this reel in single units. "
           "DigiKey DOES list RTER (296-ADS1119IRTERTR-ND, EUR 3.03) but only as a full "
           "3000-piece reel, MOQ 3000 and 0 on hand, so it is unbuyable in prototype "
           "quantity there. ADS1119IRTET is an approved alternate -- same die, same "
           "16-WQFN 3x3 RTE package, reel quantity only (250 vs 3000) -- and is DigiKey's "
           "small-quantity option at EUR 6.29 cut tape (296-53016-1-ND), about 2x the RTER "
           "reel unit price. Use RTET only when sourcing from DigiKey")
# AIN2/AIN3 are the bias-telemetry pair, read DIFFERENTIALLY as V_WE - V_RE.
# POTTING.md section 1.1: VREF is NOT where the LMP91000's +/-2% bias step error
# lives, so measuring VREF cannot substitute -- the differential is the only node
# carrying the real information. SBAS925 permits this directly: absolute input
# range is AGND-0.1 to AVDD+0.1 at gain 1 AND gain 4, so the common mode is
# unconstrained. (It is 1.975 V, the MEAN of 1.675 and 2.275; an earlier note
# here said 2.27 V, which is just V_RE.) BUT MIND THE PEDESTAL: with REFCN = 0xCD the internal zero is
# 67% VREF and the bias step 24%, so V_WE = 1.675 V, V_RE = 2.275 V and their
# DIFFERENCE IS -600 mV BY DESIGN -- 96% of the +/-625 mV full scale at gain 4,
# not a small signal near zero. It does not clip only because the LMP91000 ladder
# and the ADS1119 FSR are both referred to this same VREF_TRIM node, making the
# ratio VREF-independent to first order -- NOT exact: the LMP91000 ladder/offset
# and the ADS1119 gain/offset errors do not cancel. Two consequences: firmware must NOT convert
# this channel against the ADS1119 internal 2.048 V reference the way
# finish_vref() does for AIN1 (FSR becomes +/-512 mV and -600 mV hard-clips), and
# gain 1 is the safer setting -- 76 uV/LSB is still far finer than the quantity
# measured, and -600 mV then sits 1.9 V clear of the nearer full-scale rail
# (2494 - 600), not the 2.5 V an earlier note claimed. The two rail monitors this displaces move to
# the MCU's own ADC, which already carried VA_MON.
for p,n in {1:"ADC_RESET",2:"GND",3:"GND",4:"ADC_RE_BUF",5:"ADC_WE_BUF",6:"GND",7:"VREF_TRIM",8:"ADC_VREF_MON",9:"ADC_AFE_VOUT",10:"3V3A",11:"3V3D",12:"ADC_DRDY",13:"I2C_SDA",14:"I2C_SCL",15:"GND",16:"GND",17:"GND"}.items(): net("U8",p,n)
add_passive("R18",144.78,147.32,"10k","Resistor_SMD:R_0603_1608Metric","ADC_RESET","3V3D")
add_passive("R19",144.78,157.48,"10k","Resistor_SMD:R_0603_1608Metric","ADC_DRDY","3V3D")
add_passive("C18",144.78,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND")
add_passive("C19",144.78,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("R24",165.1,147.32,"10k 0.1%","Resistor_SMD:R_0603_1608Metric","3V3A","VA_MON",
            mpn="P2TC0603D1002LNTA",
            note="3V3A rail monitor divider, 1:2 into MCU PA7/ADC_IN7 and (via R37) ADS1119 "
                 "AIN. FIRMWARE: VA_MON_MV = 2 x ADC. Like the R26/R27 VIN monitor this is a "
                 "supply health check, so 1% would do; it uses the precision 10k only because "
                 "R25 shares the position. NOTE the other two users of that stock position, R21 "
                 "and R22, were deleted with the trim divider and the guard divider, so R24/R25 "
                 "are now the only ones; revisit the grade at the next sourcing pass")
add_passive("R25",165.1,157.48,"10k 0.1%","Resistor_SMD:R_0603_1608Metric","VA_MON","GND",
            mpn="P2TC0603D1002LNTA",
            note="3V3A rail monitor divider bottom leg; see R24")
add_passive("R26",165.1,167.64,"82k 1%","Resistor_SMD:R_0603_1608Metric","+12V_SW","VIN_MON",
            mpn="RC0603FR-1082KL",
            note="VIN monitor divider, was 130k/20k. FIRMWARE: ratio is now 10/92 = 0.1087, "
                 "not 0.1333 -- 15V maps to 1.63V. More ADC headroom than the old 2.00V and "
                 "source impedance drops from 17.3k to 8.9k. 1% is adequate for a supply monitor")
add_passive("R27",165.1,177.8,"10k 1%","Resistor_SMD:R_0603_1608Metric","VIN_MON","GND",
            mpn="RC0603FR-0710KL",
            note="VIN monitor divider bottom leg; see R26 for the firmware ratio change")
add_passive("R33",190.5,147.32,"1k","Resistor_SMD:R_0603_1608Metric","AFE_VOUT","ADC_AFE_VOUT",
            note="ADC anti-alias/input-kickback filter; place with C28 at U8 AIN0")
add_passive("C28",208.28,147.32,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_AFE_VOUT","GND")
add_passive("R39",208.28,157.48,"DNP 100k","Resistor_SMD:R_0603_1608Metric","ADC_AFE_VOUT","GND",dnp=True,
            note="Optional AFE attenuation pad; bench headroom gate selects value")
add_passive("R37",190.5,167.64,"1k","Resistor_SMD:R_0603_1608Metric","WE_BUF","ADC_WE_BUF",
            note="Bias-telemetry filter, WE leg. Matched with R38/C31 on the RE leg so the "
                 "differential pair sees equal source impedance; was the VA_MON feed")
add_passive("C30",208.28,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_WE_BUF","GND")
add_passive("R38",190.5,177.8,"1k","Resistor_SMD:R_0603_1608Metric","RE_BUF","ADC_RE_BUF",
            note="Bias-telemetry filter, RE leg; must match R37/C30 exactly. Note this taps the "
                 "BUFFER output, never CELL_RE itself -- the ADS1119's switched-cap input may "
                 "not sit on the sub-uA electrode, which is the whole reason U4B exists")
add_passive("C31",208.28,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_RE_BUF","GND")
add_passive("C32",226.06,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","VIN_MON","GND",
            note="VIN monitor reservoir at the MCU PA6 pin. VIN_MON lost its R38/C31 ADC filter "
                 "when AIN3 was taken for bias telemetry; source impedance is R26||R27 = 8.9k, "
                 "so the STM32G071 sampling cap needs this and the LONGEST sampling time")
add_passive("C33",226.06,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","VA_MON","GND",
            note="VA monitor reservoir at the MCU PA7 pin; same reason as C32, source R24||R25 = 5k")
add_passive("R34",190.5,187.96,"47k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_TRIM","VREF_MON_RAW",
            mpn="RT0603BRD0747KL",
            note="VREF health diagnostic divider, 1:2 into ADS1119 AIN1 measured against the "
                 "chip's INTERNAL 2.048V reference, so 2.500V arrives as 1.250V. FIRMWARE: "
                 "VREF_MON_MV = 2 x ADC. 0.1%/25ppm thin film is the right grade -- the "
                 "ADS1119 internal reference is itself 0.2% and ~25ppm/C, so a 0.05%/10ppm "
                 "part (10x the price) would be measuring behind a coarser ruler")
add_passive("R35",208.28,187.96,"47k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_MON_RAW","GND",
            mpn="RT0603BRD0747KL",
            note="VREF health diagnostic divider bottom leg; see R34. Same MPN as R34 on "
                 "purpose: one stock position, and same-batch TCR tracking cancels most of "
                 "the 25ppm/C in the ratio")
add_passive("R36",190.5,198.12,"1k","Resistor_SMD:R_0603_1608Metric","VREF_MON_RAW","ADC_VREF_MON")
add_passive("C29",208.28,198.12,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_VREF_MON","GND",
            note="Measure AIN1 with ADS1119 internal reference for VREF health diagnostics")

place("U11",CELL,203.2,160.02,value="SGX-OX-ROHS-Mini",footprint="o2-probe:SGX-OX-ROHS-Mini_ISS2",
      mpn="SGX-OX-ROHS-Mini",
      note="DS-0637 Issue 2 pin/body geometry; elongated rear-flow aperture remains a first-article fit gate")
net("U11",1,"CELL_CE"); net("U11",2,"CELL_RE"); net("U11",3,"CELL_WE")

# --------------------------------------------------------------------------- chamber sensors / membrane-ring heater
place("U10",TMP117,246.38,154.94,value="TMP117 CELL",footprint="tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI",mpn="TMP117AIDRVR")
for p,n in {1:"I2C_SCL",2:"GND",3:"HEATER_GATE",4:"3V3D",5:"3V3D",6:"I2C_SDA",7:"TMP_CELL_EP"}.items(): net("U10",p,n)
place("U12",SHT45,281.94,154.94,value="SHT45-AD1F",footprint="Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",mpn="SHT45-AD1F-R2")
for p,n in {1:"I2C_SDA",2:"I2C_SCL",3:"3V3D",4:"GND"}.items(): net("U12",p,n)
add_passive("C20",281.94,172.72,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",
            note="Local SHT45 supply bypass")
add_passive("C21",261.62,195.58,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",
            note="Local TMP117 supply bypass")

place("U14",BMP390,325.12,215.90,value="BMP390 DNP",footprint="o2-probe:BMP390_LGA10_DRAFT",mpn="BMP390",dnp=True,
      note="Optional pressure channel; footprint land geometry remains a release gate")
for p,n in {1:"3V3D",2:"I2C_SCL",3:"GND",4:"I2C_SDA",5:"GND",6:"3V3D",8:"GND",9:"GND",10:"3V3D"}.items(): net("U14",p,n)
nc("U14",7)
add_passive("C23",350.52,210.82,"100n DNP","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",dnp=True)
add_passive("C24",350.52,223.52,"100n DNP","Capacitor_SMD:C_0402_1005Metric","3V3D","GND",dnp=True)

place("Q2",NMOS,327.66,157.48,value="AO3400A",footprint="Package_TO_SOT_SMD:SOT-23",mpn="AO3400A")
net("Q2",1,"HEATER_GATE"); net("Q2",2,"GND"); net("Q2",3,"HEATER_LOW")
add_passive("R28",307.34,147.32,"10k","Resistor_SMD:R_0603_1608Metric","HEATER_PWM","HEATER_GATE",
            note="Limits TMP117 ALERT-vs-PWM contention to <0.33 mA nominal")
add_passive("R29",307.34,160.02,"100k","Resistor_SMD:R_0603_1608Metric","HEATER_GATE","GND")
# RH1/RH2 (2x 280R 2512, ~1 W at 12 V) STAY ON THIS BOARD.  Fab, 2026-09-04:
# "the heater stays where it is".  An earlier pass this session deleted them and
# moved the heat source to the ring PCB on the strength of HEATED-SPREADER.md
# section 0 (18.6 mm from the tip lands to the cartridge heater shelf) and
# RING-PCB.md section 1 (fork conduction only 4.3 mW/K).  That reasoning is about
# where heat must ARRIVE; it is not a licence to delete the only heat source the
# board has.  The delete would have cost a validated subsystem: the bench run in
# FAB-READINESS.md "Heater bench results, 2026-09-04" exercised the PWM, the
# TMP117 interlock with the core halted, the rail monitor, and detect-and-recover
# against RH1/RH2 as the load, and none of it could be re-run on a board whose
# heater lives on an unbuilt ring behind an unmeasured neck bore.  The ring, when
# it exists, parallels these through J5; it does not replace them.
add_passive("RH1",368.3,149.86,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
add_passive("RH2",368.3,165.1,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
add_passive("F3",350.52,149.86,"0R FITTED","Resistor_SMD:R_0603_1608Metric","+12V_SW","+12V_HTR",
            note="FITTED 0R LINK, deliberately not a DNP placeholder -- it sits in SERIES in "
                 "the only supply path to the ring, so leaving it unpopulated would open the "
                 "heater feed and the heater would never run at all. It reserves the position "
                 "for a protective device against a fault path that is NEW: with "
                 "RH1/RH2 sitting in the main-board branch and NOT in the fork feed, "
                 "nothing limits the fork itself, so a short between "
                 "the fork fingers -- which run at 0.20 mm clearance to a metal cell can, "
                 "RING-PCB.md section 1 -- puts +12V_SW across Q2 unlimited, and possibly 12 V "
                 "onto the cell. DO NOT FIT AS DRAWN: a PPTC is likely the wrong device here, "
                 "because F1's own note records IH derating to 0.36 A at 85 C, and a part that "
                 "holds the heater's 83 mA at pile temperature would nuisance-trip. The land "
                 "exists so the option is not designed out; size it once the ring's resistance "
                 "is fixed. A PPTC is likely the wrong device: F1's own note records IH "
                 "derating to 0.36 A at 85 C for a 0.75 A part, so one holding the heater's "
                 "83 mA would nuisance-trip at pile temperature")
place("TP6",TESTPOINT,350.52,180.34,value="TMP_CELL_EP",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP6",1,"TMP_CELL_EP")
place("J5",RING_FORK,368.3,180.34,value="RING PCB FORK TIP",
      footprint="o2-probe:Ring_Fork_Tip_DRAFT",
      note="Solder lands at the tips of the two fork fingers, carrying the heater pair forward "
           "to a perpendicular ring PCB (a soldered T-joint, the way any right-angle "
           "daughterboard mounts). REPLACES the two edge castellations of "
           "Heater_Ring_Solder_Lands, which HEATED-SPREADER.md section 0 showed are orphaned by "
           "the end-window head. One finger per net, both layers of each finger paralleled. "
           "RING-PCB.md section 1 offered 4 conductors; only 2 are used, because Fab dropped "
           "the ring's temperature sensor from this revision -- the second layer of each finger "
           "stays physically free, so a v2 ring can add one with NO main-board change. "
           "FOOTPRINT IS DRAFT: RING-PCB.md section 5.1 forbids freezing the 0.6 mm finger "
           "width before the printed ASA neck bore is measured on a real part")
net("J5",1,"+12V_HTR"); net("J5",2,"HEATER_LOW")


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
         '\t(title_block (title "O2 Probe Rev A — SGX-OX Mini / LMP91000 / STM32G071 / RS-485") (comment 1 "GENERATED by gen_sch.py — edit generator, not schematic") (comment 2 "J3 is PRE-POT ONLY; post-pot update is over RS-485 bootloader") (comment 3 "SGX footprint remains a physical-sample gate"))', '\t(lib_symbols']
    for k in sorted(SYMS): a.extend('\t\t' + ln for ln in symbol_block(k).splitlines())
    a.append('\t)')
    for x1,y1,x2,y2 in WIRES:
        a.append(f'\t(wire (pts (xy {x1:g} {y1:g}) (xy {x2:g} {y2:g})) (stroke (width 0) (type default)) (uuid "{uid("w",x1,y1,x2,y2)}"))')
    for x,y in NOCONN: a.append(f'\t(no_connect (at {x:g} {y:g}) (uuid "{uid("nc",x,y)}"))')
    for text,x,y,ang in LABELS:
        just = "right" if ang == 180 else "left"
        a.append(f'\t(label "{esc(text)}" (at {x:g} {y:g} {ang}) (effects (font (size 1.0 1.0)) (justify {just} bottom)) (uuid "{uid("label",text,x,y)}"))')
    for ref in sorted(INST):
        i=INST[ref]; s=SYMS[i["lib_id"]]; x=i["x"]; y=i["y"]
        a.extend(['\t(symbol',f'\t\t(lib_id "{i["lib_id"]}")',f'\t\t(at {x:g} {y:g} {i["angle"]})','\t\t(unit 1)','\t\t(exclude_from_sim no)',f'\t\t(in_bom {"yes" if i["in_bom"] else "no"})',f'\t\t(on_board {"yes" if i["footprint"] else "no"})',f'\t\t(dnp {"yes" if i["dnp"] else "no"})',f'\t\t(uuid "{uid("sym",ref)}")',
                  f'\t\t(property "Reference" "{ref}" (at {x-5.08:g} {y-s["half_h"]-5.08:g} 0) (effects (font (size 1.0 1.0))))',
                  f'\t\t(property "Value" "{esc(i["value"])}" (at {x+5.08:g} {y-s["half_h"]-2.54:g} 0) (effects (font (size 1.0 1.0)) (justify right)))',
                  f'\t\t(property "Footprint" "{esc(i["footprint"])}" (at {x:g} {y:g} 0) (effects (font (size 1.27 1.27)) hide))'])
        for key,val in (("MPN",i["mpn"]),("Design Note",i["note"])):
            if val: a.append(f'\t\t(property "{key}" "{esc(val)}" (at {x:g} {y:g} 0) (effects (font (size 1.27 1.27)) hide))')
        for num,_,_ in s["pins"]: a.append(f'\t\t(pin "{num}" (uuid "{uid("pin",ref,num)}"))')
        a.extend(['\t\t(instances',f'\t\t\t(project "{NAME}" (path "/{uid("root")}" (reference "{ref}") (unit 1)))','\t\t)','\t)'])
    a.extend(['\t(sheet_instances (path "/" (page "1")))','\t(embedded_fonts no)',')'])
    return "\n".join(a)+"\n"


def verify() -> None:
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
        elif ref.startswith("D"):
            expected_symbol[ref] = TVS3
        elif ref == "Q1":
            expected_symbol[ref] = PMOS
        elif ref == "Q2":
            expected_symbol[ref] = NMOS
        elif ref.startswith("TP"):
            expected_symbol[ref] = TESTPOINT
        elif ref == "J5":
            expected_symbol[ref] = RING_FORK
        elif ref in ("J101", "J102", "J103", "J104"):
            expected_symbol[ref] = CONN1
    for ref, lib_id in expected_symbol.items():
        actual = INST[ref]["lib_id"]
        if actual != lib_id:
            raise ValueError(f"{ref} must use {lib_id}, not {actual}")
        if lib_id in (RES2, CAP2, POLYFUSE2, INDUCTOR2, TVS2, ZENER2,
                      PMOS, NMOS, POT, TESTPOINT, CONN1) and not SYMS[lib_id].get("source_block"):
            raise ValueError(f"{ref} designated symbol {lib_id} is not library-derived")
    forbidden = {"o2-probe:PASSIVE_2", "o2-probe:CAPACITOR_2"}
    used_forbidden = {i["lib_id"] for i in INST.values()} & forbidden
    if used_forbidden:
        raise ValueError(f"generic placeholder symbols are forbidden: {sorted(used_forbidden)}")
    # Locked interface/address facts.
    assert ASSIGNED[("U8","15")] == ASSIGNED[("U8","16")] == "GND"  # ADS1119 0x40
    assert ASSIGNED[("U10","4")] == "3V3D"                            # TMP117 0x49
    # Fork tip to the ring PCB: one finger per net, and they must not be swapped.
    assert ASSIGNED[("J5","1")] == "+12V_HTR" and ASSIGNED[("J5","2")] == "HEATER_LOW"
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
        "1": "+5V", "2": "+12V_SW", "3": "+12V_SW", "4": "GND",
        "5": "BUCK_SW", "6": "BUCK_BST",
    }  # AP63205 DS41326: 1 FB, 2 EN, 3 VIN, 4 GND, 5 SW, 6 BST
    assert {p: ASSIGNED[("D2", p)] for p in ("1", "2", "3")} == {
        "1": "RS485_A_CABLE", "2": "RS485_B_CABLE", "3": "GND",
    }  # Littelfuse SM712-02HTG SOT-23
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
    assert ASSIGNED[("R31", "2")] == "VREF_TRIM"
    assert ASSIGNED[("R32", "1")] == "+5V" and ASSIGNED[("R32", "2")] == "+5V_ANALOG"
    assert ASSIGNED[("U3", "1")] == ASSIGNED[("U3", "3")] == "+5V_ANALOG"
    assert ASSIGNED[("C7", "1")] == ASSIGNED[("C27", "1")] == "+5V_ANALOG"
    # No adjustable part may set the bias: the cell is swappable with the board
    # potted, so a trimmer would be unreachable after cure (POTTING.md 1.2).
    assert not any(ref.startswith("RV") for ref in INST)
    # AZ431-A N package (SOT-23) is 1 REF, 2 CATHODE, 3 ANODE -- NOT the TI
    # TL431DBZ map the donor graphic arrived with. REF strapped to the cathode is
    # what makes this a 2.5 V two-terminal shunt.
    assert {p: ASSIGNED[("U15", p)] for p in ("1", "2", "3")} == {
        "1": "VREF_SHUNT", "2": "VREF_SHUNT", "3": "GND",
    }
    # A pin map is not an identity. REF3320 (2.048 V) or REF3330 (3.0 V) would
    # pass a pin-map check unchanged while silently invalidating the 2500 mV the
    # firmware contract asserts, so pin the part and its bias network too.
    assert INST["U15"]["value"] == "AZ431BN-ATRG1"
    assert INST["R41"]["value"].startswith("1.5k") and ASSIGNED[("R41", "1")] == "+5V_ANALOG"
    # Every 100n decoupling capacitor shares ONE land, so the BOM carries a single
    # 100n line and assembly a single feeder. C2, C11 and C15 were 0603 against
    # seventeen 0402s. Deliberately scoped to 100n: values like 10u legitimately
    # differ by package because they differ by VOLTAGE RATING (C1 is 25 V 1206,
    # C7 is 10 V 0805), and collapsing those would be a downgrade, not a tidy-up.
    hundred_n = {ref: i["footprint"] for ref, i in INST.items()
                 if ref.startswith("C") and i["value"].startswith("100n")}
    assert len(set(hundred_n.values())) == 1, sorted(
        (fp, ref) for ref, fp in hundred_n.items())
    # Bulk capacitance must stay OFF the cathode (AZ431 stability; see C9, R31).
    assert ASSIGNED[("C9", "1")] == "VREF_SHUNT" and INST["C9"]["value"] == "1n"
    assert ASSIGNED[("C10", "1")] == "VREF_TRIM" and ASSIGNED[("R31", "1")] == "VREF_SHUNT"
    assert ASSIGNED[("U8", "7")] == "VREF_TRIM" and ASSIGNED[("U8", "8")] == "ADC_VREF_MON"
    assert ASSIGNED[("U8", "9")] == "ADC_AFE_VOUT"
    # VIN monitor divider. The value is pinned because firmware converts the ADC
    # reading with this exact ratio; changing one leg without the other silently
    # rescales every reported input voltage.
    assert ASSIGNED[("R26", "2")] == "VIN_MON" and INST["R26"]["value"].startswith("82k")
    assert ASSIGNED[("R27", "1")] == "VIN_MON" and INST["R27"]["value"].startswith("10k")
    # Bias telemetry: the ADS1119 pair must read the BUFFERED electrodes, and the
    # two legs must be matched, or the differential measurement acquires a
    # source-impedance error larger than the bias it is there to resolve.
    assert ASSIGNED[("U8", "5")] == "ADC_WE_BUF" and ASSIGNED[("U8", "4")] == "ADC_RE_BUF"
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
