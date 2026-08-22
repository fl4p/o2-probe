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
add_passive("F1", 40.64, 30.48, "0.75A PTC", "Fuse:Fuse_1206_3216Metric", "+12V_RAW", "+12V_FUSED")
add_passive("D1", 40.64, 43.18, "SMBJ15A-13-F", "Diode_SMD:D_SMB", "+12V_FUSED", "GND", mpn="SMBJ15A-13-F")
place("Q1", PMOS, 62.23, 30.48, value="DMP3010L", footprint="Package_TO_SOT_SMD:SOT-23", mpn="DMP3010L-7")
net("Q1",1,"VIN_GATE"); net("Q1",2,"+12V_SW"); net("Q1",3,"+12V_FUSED")
add_passive("R1", 60.96, 43.18, "100k", "Resistor_SMD:R_0603_1608Metric", "VIN_GATE", "GND")
add_passive("DZ1", 78.74, 43.18, "12V ZENER", "Diode_SMD:D_SOD-123", "+12V_SW", "VIN_GATE")
place("#FLG01", PWRFLAG, 20.32, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG01",1,"+12V_RAW")
place("#FLG02", PWRFLAG, 35.56, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG02",1,"GND")
place("#FLG03", PWRFLAG, 50.8, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG03",1,"+12V_SW")
place("#FLG04", PWRFLAG, 66.04, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG04",1,"+5V")
place("#FLG05", PWRFLAG, 81.28, 50.8, value="PWR_FLAG", footprint="", in_bom=False); net("#FLG05",1,"+5V_ANALOG")

place("U1", BUCK, 106.68, 33.02, value="AP63205WU-7", footprint="Package_TO_SOT_SMD:TSOT-23-6", mpn="AP63205WU-7")
for p,n in {1:"+5V",2:"+12V_SW",3:"+12V_SW",4:"GND",5:"BUCK_SW",6:"BUCK_BST"}.items(): net("U1",p,n)
add_passive("C1", 88.9, 43.18, "10u 25V", "Capacitor_SMD:C_1206_3216Metric", "+12V_SW", "GND")
add_passive("C2", 106.68, 48.26, "100n", "Capacitor_SMD:C_0603_1608Metric", "BUCK_BST", "BUCK_SW")
add_passive("L1", 129.54, 30.48, "4.7u SHIELDED", "Inductor_SMD:L_6.3x6.3_H3", "BUCK_SW", "+5V")
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

place("U4",OPAMP2,246.38,35.56,value="OPA2333AIDGKR",footprint="Package_SO:VSSOP-8_3x3mm_P0.65mm",mpn="OPA2333AIDGKR")
for p,n in {1:"VREF_BUF",2:"VREF_BUF",3:"VREF_WIPER",4:"GND",5:"GUARD_DIV",6:"GUARD_REPLICA",7:"GUARD_REPLICA",8:"3V3A"}.items(): net("U4",p,n)
add_passive("R20",226.06,27.94,"1.91k 0.1%","Resistor_SMD:R_0603_1608Metric","3V3A","VREF_TOP")
place("RV1",POT,226.06,40.64,value="2k 10-turn",footprint="Potentiometer_SMD:Potentiometer_Bourns_3224W_Vertical",mpn="3224W-1-202E")
net("RV1",1,"VREF_TOP"); net("RV1",2,"VREF_WIPER"); net("RV1",3,"VREF_WIPER")
add_passive("R21",226.06,53.34,"9.10k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_WIPER","GND",
            note="Pot wiper is strapped to the low/output terminal for open-wiper fail safety")
add_passive("C9",243.84,53.34,"100n","Capacitor_SMD:C_0603_1608Metric","VREF_WIPER","GND")
add_passive("R31",246.38,60.96,"47R","Resistor_SMD:R_0603_1608Metric","VREF_BUF","VREF_TRIM",
            note="OPA2333 capacitive-load isolation; feedback remains at op-amp output")
add_passive("C10",264.16,60.96,"4.7u","Capacitor_SMD:C_0603_1608Metric","VREF_TRIM","GND")
add_passive("C25",284.48,55.88,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND",
            note="Place at U4 pins 8/4")
add_passive("R22",269.24,27.94,"10k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_TRIM","GUARD_DIV")
add_passive("R23",269.24,43.18,"100k 0.1%","Resistor_SMD:R_0603_1608Metric","GUARD_DIV","GND")
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
add_passive("C11",73.66,82.55,"100n","Capacitor_SMD:C_0603_1608Metric","3V3D","GND")

place("U6",MCU,111.76,99.06,value="STM32G071CBT7",footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",mpn="STM32G071CBT7")
MCU_NETS = {4:"3V3D",5:"3V3D",6:"3V3D",7:"GND",10:"NRST",11:"VA_MON",12:"RS485_DE",13:"UART2_TX",14:"UART2_RX",19:"AFE_MENB",20:"ADC_DRDY",21:"EXP_INT",22:"TGAS_ALERT",28:"HEATER_PWM",29:"RS485_TX",32:"RS485_RX",35:"SWDIO",36:"SWCLK_BOOT0",42:"SWO",45:"I2C_SCL",46:"I2C_SDA"}
for p in range(1,49):
    if p in MCU_NETS: net("U6",p,MCU_NETS[p])
    else: nc("U6",p)
add_passive("C12",139.7,83.82,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C13",139.7,93.98,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C14",139.7,104.14,"4.7u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND")
add_passive("C26",139.7,114.3,"1u","Capacitor_SMD:C_0603_1608Metric","3V3D","GND",
            note="Place at MCU VREF+ pin 5")
add_passive("R8",160.02,83.82,"10k","Resistor_SMD:R_0603_1608Metric","NRST","3V3D")
add_passive("C15",160.02,93.98,"100n","Capacitor_SMD:C_0603_1608Metric","NRST","GND")
add_passive("R9",160.02,104.14,"100k","Resistor_SMD:R_0603_1608Metric","SWCLK_BOOT0","GND")
add_passive("R10",177.8,83.82,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SCL","3V3D")
add_passive("R11",177.8,93.98,"4.7k","Resistor_SMD:R_0603_1608Metric","I2C_SDA","3V3D")

place("J3",CONN6,203.2,88.9,value="TC2030 SWD PRE-POT",footprint="Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",note="1=VTREF 2=SWDIO 3=NRST 4=SWCLK 5=GND 6=SWO")
for p,n in enumerate(("3V3D","SWDIO","NRST","SWCLK_BOOT0","GND","SWO"),1): net("J3",p,n)

# --------------------------------------------------------------------------- expansion connector
place("J2",CONN8,274.32,91.44,value="EXPANSION / K33",footprint="Connector_Molex:Molex_Micro-Fit_3.0_43045-0815_2x04_P3.00mm_Vertical",dnp=True,note="Tube-height gate; pad-field fallback permitted")
for p,n in enumerate(("+12V_SW","GND","EXP_3V3","EXP_SDA","EXP_SCL","EXP_INT_OUT","EXP_TX","EXP_RX"),1): net("J2",p,n)
add_passive("F2",251.46,78.74,"0.20A PTC DNP","Fuse:Fuse_1206_3216Metric","3V3D","EXP_3V3",dnp=True)
for ref,y,a,b in (("R12",86.36,"I2C_SDA","EXP_SDA"),("R13",96.52,"I2C_SCL","EXP_SCL"),("R14",106.68,"EXP_INT","EXP_INT_OUT"),("R15",116.84,"UART2_TX","EXP_TX"),("R16",127.0,"UART2_RX","EXP_RX")):
    add_passive(ref,251.46,y,"33R DNP","Resistor_SMD:R_0603_1608Metric",a,b,dnp=True)
place("D4",TVS3,302.26,86.36,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D4",1,"EXP_SDA"); net("D4",2,"GND"); net("D4",3,"EXP_SCL")
place("D5",TVS3,302.26,101.6,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D5",1,"EXP_TX"); net("D5",2,"GND"); net("D5",3,"EXP_RX")
place("D6",TVS3,302.26,116.84,value="TPD2E2U06 DNP",footprint="Package_TO_SOT_SMD:SOT-23",mpn="TPD2E2U06QDBZR",dnp=True)
net("D6",1,"EXP_INT_OUT"); net("D6",2,"GND"); nc("D6",3)

# --------------------------------------------------------------------------- AFE / ADC / cell
place("U7",LMP,50.8,162.56,value="LMP91000SD/NOPB",footprint="Package_SON:WSON-14-1EP_4.0x4.0mm_P0.5mm_EP2.6x2.6mm",mpn="LMP91000SDE/NOPB")
for p,n in {1:"GND",2:"AFE_MENB",3:"I2C_SCL",4:"I2C_SDA",6:"3V3A",7:"GND",8:"AFE_VOUT",9:"LMP_C2",10:"LMP_C1",11:"VREF_TRIM",12:"CELL_WE",13:"CELL_RE",14:"CELL_CE",15:"GND"}.items(): net("U7",p,n)
nc("U7",5)
add_passive("R17",20.32,149.86,"100k","Resistor_SMD:R_0603_1608Metric","AFE_MENB","GND")
add_passive("C16",20.32,160.02,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND")
add_passive("C17",20.32,170.18,"10n","Capacitor_SMD:C_0603_1608Metric","LMP_C1","LMP_C2")
for ref,y,n in (("TP1",149.86,"CELL_WE"),("TP2",160.02,"CELL_RE"),("TP3",170.18,"CELL_CE")):
    place(ref,TESTPOINT,76.2,y,value=n,footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net(ref,1,n)

place("U8",ADS,111.76,162.56,value="ADS1119IRTER",footprint="Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm",mpn="ADS1119IRTER")
for p,n in {1:"ADC_RESET",2:"GND",3:"GND",4:"ADC_VIN_MON",5:"ADC_VA_MON",6:"GND",7:"VREF_TRIM",8:"ADC_VREF_MON",9:"ADC_AFE_VOUT",10:"3V3A",11:"3V3D",12:"ADC_DRDY",13:"I2C_SDA",14:"I2C_SCL",15:"GND",16:"GND",17:"GND"}.items(): net("U8",p,n)
add_passive("R18",144.78,147.32,"10k","Resistor_SMD:R_0603_1608Metric","ADC_RESET","3V3D")
add_passive("R19",144.78,157.48,"10k","Resistor_SMD:R_0603_1608Metric","ADC_DRDY","3V3D")
add_passive("C18",144.78,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","3V3A","GND")
add_passive("C19",144.78,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("R24",165.1,147.32,"10k 0.1%","Resistor_SMD:R_0603_1608Metric","3V3A","VA_MON")
add_passive("R25",165.1,157.48,"10k 0.1%","Resistor_SMD:R_0603_1608Metric","VA_MON","GND")
add_passive("R26",165.1,167.64,"130k 0.1%","Resistor_SMD:R_0603_1608Metric","+12V_SW","VIN_MON")
add_passive("R27",165.1,177.8,"20k 0.1%","Resistor_SMD:R_0603_1608Metric","VIN_MON","GND")
add_passive("R33",190.5,147.32,"1k","Resistor_SMD:R_0603_1608Metric","AFE_VOUT","ADC_AFE_VOUT",
            note="ADC anti-alias/input-kickback filter; place with C28 at U8 AIN0")
add_passive("C28",208.28,147.32,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_AFE_VOUT","GND")
add_passive("R39",208.28,157.48,"DNP 100k","Resistor_SMD:R_0603_1608Metric","ADC_AFE_VOUT","GND",dnp=True,
            note="Optional AFE attenuation pad; bench headroom gate selects value")
add_passive("R37",190.5,167.64,"1k","Resistor_SMD:R_0603_1608Metric","VA_MON","ADC_VA_MON")
add_passive("C30",208.28,167.64,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_VA_MON","GND")
add_passive("R38",190.5,177.8,"1k","Resistor_SMD:R_0603_1608Metric","VIN_MON","ADC_VIN_MON")
add_passive("C31",208.28,177.8,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_VIN_MON","GND")
add_passive("R34",190.5,187.96,"47k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_TRIM","VREF_MON_RAW")
add_passive("R35",208.28,187.96,"47k 0.1%","Resistor_SMD:R_0603_1608Metric","VREF_MON_RAW","GND")
add_passive("R36",190.5,198.12,"1k","Resistor_SMD:R_0603_1608Metric","VREF_MON_RAW","ADC_VREF_MON")
add_passive("C29",208.28,198.12,"100n","Capacitor_SMD:C_0402_1005Metric","ADC_VREF_MON","GND",
            note="Measure AIN1 with ADS1119 internal reference for VREF health diagnostics")

place("U11",CELL,203.2,160.02,value="SGX-OX-ROHS-Mini",footprint="o2-probe:SGX-OX-ROHS-Mini_DRAFT",note="DRAFT footprint: rear port and sample fit remain a physical gate")
net("U11",1,"CELL_CE"); net("U11",2,"CELL_RE"); net("U11",3,"CELL_WE")

# --------------------------------------------------------------------------- chamber sensors / heater
place("U10",TMP117,246.38,154.94,value="TMP117 CELL",footprint="tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI",mpn="TMP117AIDRVR")
for p,n in {1:"I2C_SCL",2:"GND",3:"HEATER_GATE",4:"3V3D",5:"3V3D",6:"I2C_SDA",7:"TMP_CELL_EP"}.items(): net("U10",p,n)
place("U13",TMP117,246.38,180.34,value="TMP117 GAS",footprint="tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI",mpn="TMP117AIDRVR")
for p,n in {1:"I2C_SCL",2:"GND",3:"TGAS_ALERT",4:"I2C_SDA",5:"3V3D",6:"I2C_SDA",7:"TMP_GAS_EP"}.items(): net("U13",p,n)
place("U12",SHT45,281.94,154.94,value="SHT45-AD1F",footprint="Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",mpn="SHT45-AD1F-R2")
for p,n in {1:"I2C_SDA",2:"I2C_SCL",3:"3V3D",4:"GND"}.items(): net("U12",p,n)
add_passive("C20",281.94,172.72,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C21",261.62,195.58,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("C22",281.94,195.58,"100n","Capacitor_SMD:C_0402_1005Metric","3V3D","GND")
add_passive("R30",302.26,195.58,"10k","Resistor_SMD:R_0603_1608Metric","TGAS_ALERT","3V3D")

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
add_passive("RH1",350.52,149.86,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
add_passive("RH2",350.52,165.1,"280R 1W","Resistor_SMD:R_2512_6332Metric","+12V_SW","HEATER_LOW",mpn="CRCW2512280RFKEG")
place("TP6",TESTPOINT,350.52,180.34,value="TMP_CELL_EP",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP6",1,"TMP_CELL_EP")
place("TP7",TESTPOINT,368.3,180.34,value="TMP_GAS_EP",footprint="TestPoint:TestPoint_Pad_D1.0mm",in_bom=False); net("TP7",1,"TMP_GAS_EP")


def symbol_block(lib_id: str) -> str:
    s = SYMS[lib_id]
    if s.get("source_block"):
        return s["source_block"]
    name = s["name"]; hh = s["half_h"]; hw = s["half_w"]
    out = [f'(symbol "{lib_id}"', '\t(pin_names (offset 0.508))', '\t(exclude_from_sim no)', '\t(in_bom yes)', '\t(on_board yes)',
           f'\t(property "Reference" "{s["ref_prefix"]}" (at -5.08 {hh + 2.54:g} 0) (effects (font (size 1.27 1.27))))',
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
                  f'\t\t(property "Reference" "{ref}" (at {x-5.08:g} {y-s["half_h"]-2.54:g} 0) (effects (font (size 1.0 1.0))))',
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
    assert ASSIGNED[("U13","4")] == "I2C_SDA"                         # TMP117 0x4A
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
    assert ASSIGNED[("U4", "1")] == ASSIGNED[("U4", "2")] == "VREF_BUF"
    assert ASSIGNED[("R31", "2")] == "VREF_TRIM"
    assert ASSIGNED[("R32", "1")] == "+5V" and ASSIGNED[("R32", "2")] == "+5V_ANALOG"
    assert ASSIGNED[("U3", "1")] == ASSIGNED[("U3", "3")] == "+5V_ANALOG"
    assert ASSIGNED[("C7", "1")] == ASSIGNED[("C27", "1")] == "+5V_ANALOG"
    assert ASSIGNED[("RV1", "2")] == ASSIGNED[("RV1", "3")] == "VREF_WIPER"
    assert ASSIGNED[("U8", "7")] == "VREF_TRIM" and ASSIGNED[("U8", "8")] == "ADC_VREF_MON"
    assert ASSIGNED[("U8", "9")] == "ADC_AFE_VOUT"
    assert ASSIGNED[("R26", "2")] == "VIN_MON" and INST["R26"]["value"].startswith("130k")


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
