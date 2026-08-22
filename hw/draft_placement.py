#!/usr/bin/env python3
"""Generate the unrouted Rev-A footprint-placement study.

This is deliberately a mechanical/placement artefact, not a schematic-derived
PCB.  Every part is unnetted and routing it would be an error.  The placement
exists to test the 20 x 125 mm envelope, zone partition, cell/AFE distance,
thermal slots, tube-height risks, and rework access before schematic capture.

Run with KiCad's bundled Python:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 draft_placement.py
"""

from pathlib import Path
import sys

try:
    import pcbnew
except ImportError:
    sys.exit("pcbnew unavailable; run with KiCad's bundled Python")

HERE = Path(__file__).resolve().parent
OUT = HERE / "o2-probe-placement.kicad_pcb"
KI_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PROJECT_FP = HERE / "lib" / "o2-probe.pretty"
TMP117_FP = HERE.parent / "tmp117-probe" / "lib" / "tmp117-probe.pretty"

# KiCad-page origin; all placement coordinates below are board-local millimetres.
ORG = pcbnew.VECTOR2I_MM(100, 50)
W, L, R = 20.0, 125.0, 2.0
POT_Y, GAS_Y = 82.0, 86.0
CELL_X, CELL_Y = 10.0, 93.5


def mm(value):
    return pcbnew.FromMM(value)


def point(x, y):
    return pcbnew.VECTOR2I(ORG.x + mm(x), ORG.y + mm(y))


# ref, value, library:footprint, x, y, rotation, side, DNP
PLACEMENT = [
    # Cable and protection
    # This library footprint's origin is pad 1, not the row centre.
    ("J1", "FARM BUS", "Connector_Wire:SolderWire-0.25sqmm_1x04_P4.2mm_D0.65mm_OD1.7mm", 3.7, 5.0, 0, "F", False),
    ("F1", "PTC", "Fuse:Fuse_1206_3216Metric", 3.5, 13.0, 90, "F", False),
    ("D1", "VIN TVS", "Diode_SMD:D_SMA", 8.0, 13.0, 90, "F", False),
    ("Q1", "REV-POL PFET", "Package_SO:PowerPAK_SO-8_Single", 14.5, 13.0, 90, "F", False),
    # Buck and rails
    ("U1", "12V->5V BUCK", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 5.0, 23.0, 90, "F", False),
    ("L1", "SHIELDED", "Inductor_SMD:L_6.3x6.3_H3", 13.0, 23.0, 0, "F", False),
    ("C1", "VIN BULK", "Capacitor_SMD:C_1206_3216Metric", 3.0, 29.0, 90, "F", False),
    ("C2", "5V BULK", "Capacitor_SMD:C_1206_3216Metric", 17.0, 29.0, 90, "F", False),
    ("U2", "3V3D LDO", "Package_TO_SOT_SMD:SOT-23-5", 4.0, 34.0, 0, "F", False),
    ("U3", "3V3A LDO", "Package_TO_SOT_SMD:SOT-23-5", 10.0, 34.0, 0, "F", False),
    ("U4", "TRIM VREF", "Package_TO_SOT_SMD:SOT-23-5", 16.0, 34.0, 0, "F", False),
    # Communications and MCU
    ("U5", "RS485", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 4.0, 43.0, 90, "F", False),
    ("R1", "TERM DNP", "Resistor_SMD:R_0603_1608Metric", 3.0, 51.0, 0, "B", True),
    ("R2", "BIAS+ DNP", "Resistor_SMD:R_0603_1608Metric", 6.0, 51.0, 0, "B", True),
    ("R3", "BIAS- DNP", "Resistor_SMD:R_0603_1608Metric", 9.0, 51.0, 0, "B", True),
    ("U6", "STM32G071CB", "Package_QFP:LQFP-48_7x7mm_P0.5mm", 13.5, 47.0, 0, "F", False),
    ("J3", "SWD TC2030", "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", 6.0, 57.0, 0, "F", False),
    # Expansion connector and protection. Actual connector height remains a gate.
    ("J2", "EXPANSION", "Connector_Molex:Molex_Micro-Fit_3.0_43045-0815_2x04_P3.00mm_Vertical", 10.0, 69.0, 0, "F", False),
    ("D2", "EXP TVS", "Package_SO:TSSOP-8_3x3mm_P0.65mm", 3.0, 64.0, 90, "B", False),
    # AFE row, hard against the potted side of the dam.
    ("Q2", "HEATER FET", "Package_TO_SOT_SMD:SOT-23", 2.0, 79.0, 90, "F", False),
    ("U9", "GUARD BUFFER", "Package_TO_SOT_SMD:SOT-23-5", 5.5, 79.0, 90, "F", False),
    ("U7", "LMP91000", "Package_DFN_QFN:OnSemi_DFN-14-1EP_4x4mm_P0.5mm_EP2.7x3.4mm", 10.5, 79.5, 0, "F", False),
    ("U8", "ADS1119", "Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm", 16.0, 79.0, 0, "F", False),
    ("TP1", "WE", "TestPoint:TestPoint_Pad_D1.0mm", 4.0, 75.0, 0, "B", False),
    ("TP2", "RE", "TestPoint:TestPoint_Pad_D1.0mm", 7.0, 75.0, 0, "B", False),
    ("TP3", "CE", "TestPoint:TestPoint_Pad_D1.0mm", 10.0, 75.0, 0, "B", False),
    # Gas/heater zone. Pin row of U11 faces cable/AFe (negative local y).
    ("U11", "SGX-OX-ROHS-Mini", "o2-probe:SGX-OX-ROHS-Mini_DRAFT", CELL_X, CELL_Y, 0, "F", False),
    ("RH1", "140R 2512", "Resistor_SMD:R_2512_6332Metric", 4.5, 105.0, 0, "B", False),
    ("RH2", "140R 2512", "Resistor_SMD:R_2512_6332Metric", 15.5, 105.0, 0, "B", False),
    ("U10", "TMP117 CELL", "tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI", 10.0, 105.0, 90, "B", False),
    ("U12", "SHT45-AD1F", "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad", 10.0, 110.0, 0, "F", False),
    # Inlet/reference tab
    ("U13", "TMP117 GAS", "tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI", 9.0, 120.0, 90, "F", False),
    ("U14", "BMP390 DNP / FP TBD", "Package_LGA:Rohm_MLGA010V020A_LGA-10_2x2mm_P0.45mm_LayoutBorder2x3y", 16.2, 120.0, 0, "F", True),
]


def library_path(nickname):
    if nickname == "o2-probe":
        return PROJECT_FP
    if nickname == "tmp117-probe":
        return TMP117_FP
    return KI_FP / f"{nickname}.pretty"


def add_text(board, text, x, y, layer=pcbnew.F_SilkS, size=0.8, rotation=0):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(point(x, y))
    item.SetLayer(layer)
    item.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    item.SetTextThickness(mm(0.15 if size >= 0.8 else 0.12))
    item.SetTextAngle(pcbnew.EDA_ANGLE(rotation, pcbnew.DEGREES_T))
    if layer in (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_CrtYd):
        item.SetMirrored(True)
    item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    board.Add(item)


def add_line(board, x1, y1, x2, y2, layer, width=0.15):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(point(x1, y1))
    shape.SetEnd(point(x2, y2))
    shape.SetLayer(layer)
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_arc(board, sx, sy, mx, my, ex, ey, layer, width=0.05):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(point(sx, sy), point(mx, my), point(ex, ey))
    shape.SetLayer(layer)
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_round_outline(board):
    # Clockwise closed 20 x 125 mm outline, R2 corners.
    add_line(board, R, 0, W - R, 0, pcbnew.Edge_Cuts, 0.05)
    add_arc(board, W - R, 0, W - 0.586, 0.586, W, R, pcbnew.Edge_Cuts)
    add_line(board, W, R, W, L - R, pcbnew.Edge_Cuts, 0.05)
    add_arc(board, W, L - R, W - 0.586, L - 0.586, W - R, L, pcbnew.Edge_Cuts)
    add_line(board, W - R, L, R, L, pcbnew.Edge_Cuts, 0.05)
    add_arc(board, R, L, 0.586, L - 0.586, 0, L - R, pcbnew.Edge_Cuts)
    add_line(board, 0, L - R, 0, R, pcbnew.Edge_Cuts, 0.05)
    add_arc(board, 0, R, 0.586, 0.586, R, 0, pcbnew.Edge_Cuts)


def add_mechanical_slot(board, ref, x, y, length, width, vertical=False):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(f"NPTH SLOT {length:g}x{width:g}")
    fp.SetPosition(point(x, y))
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    pad = pcbnew.PAD(fp)
    pad.SetNumber("")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
    size = pcbnew.VECTOR2I_MM(length, width)
    pad.SetSize(size)
    pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    pad.SetDrillSize(size)
    if vertical:
        pad.SetOrientationDegrees(90)
    fp.Add(pad)
    for prop in (fp.Reference(), fp.Value()):
        prop.SetLayer(pcbnew.Cmts_User)
        prop.SetTextSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
        prop.SetTextThickness(mm(0.1))
    board.Add(fp)


def add_region_box(board, x0, y0, x1, y1, label):
    for a, b, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1),
                       (x1, y1, x0, y1), (x0, y1, x0, y0)):
        add_line(board, a, b, c, d, pcbnew.Cmts_User, 0.2)
    add_text(board, label, (x0 + x1) / 2, y0 + 1.0, pcbnew.Cmts_User, 0.65)


def build():
    board = pcbnew.CreateEmptyBoard()
    board.GetDesignSettings().SetBoardThickness(mm(1.0))
    add_round_outline(board)

    # Pot boundary and placement envelopes.
    add_line(board, 0.5, POT_Y, 19.5, POT_Y, pcbnew.F_SilkS, 0.3)
    add_line(board, 0.5, POT_Y, 19.5, POT_Y, pcbnew.B_SilkS, 0.3)
    add_text(board, "POT TO HERE", 10.0, POT_Y - 6.0, pcbnew.F_SilkS, 0.8)
    add_text(board, "POT TO HERE", 10.0, POT_Y - 10.0, pcbnew.B_SilkS, 0.8)
    add_text(board, "CABLE / POTTED", 10.0, 10.0, pcbnew.Cmts_User, 0.8)
    add_text(board, "GAS / DO NOT POT", 10.0, 113.8, pcbnew.F_SilkS, 0.8)
    add_region_box(board, 1.0, 0.8, 19.0, 8.5, "CABLE / STRAIN RELIEF")
    add_region_box(board, 1.0, 86.0, 19.0, 108.0, "HEATED ISLAND")
    add_region_box(board, 5.5, 116.0, 12.5, 123.0, "TGAS TAB")

    # Provisional pot/thermal slots and isolation slots.
    add_mechanical_slot(board, "MS1", 4.25, 84.0, 6.5, 1.0)
    add_mechanical_slot(board, "MS2", 15.75, 84.0, 6.5, 1.0)
    add_mechanical_slot(board, "MS3", 1.0, 94.25, 16.5, 1.0, vertical=True)
    add_mechanical_slot(board, "MS4", 19.0, 94.25, 16.5, 1.0, vertical=True)
    add_mechanical_slot(board, "MS5", 5.0, 119.5, 7.0, 0.8, vertical=True)
    add_mechanical_slot(board, "MS6", 13.0, 119.5, 7.0, 0.8, vertical=True)

    for ref, value, footprint, x, y, rotation, side, dnp in PLACEMENT:
        nickname, name = footprint.split(":", 1)
        fp = pcbnew.FootprintLoad(str(library_path(nickname)), name)
        if fp is None:
            raise SystemExit(f"missing footprint {footprint}")
        board.Add(fp)
        fp.SetFPID(pcbnew.LIB_ID(nickname, name))
        fp.SetPosition(point(x, y))
        fp.SetOrientationDegrees(rotation)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetDNP(dnp)
        if side == "B":
            fp.Flip(fp.GetPosition(), False)
        # References and values stay on Fab: this is a placement study and
        # crowding production silk with every refdes conceals real clearances.
        fp.Reference().SetLayer(pcbnew.B_Fab if side == "B" else pcbnew.F_Fab)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        fp.Reference().SetTextThickness(mm(0.12))
        fp.Value().SetLayer(pcbnew.B_Fab if side == "B" else pcbnew.F_Fab)
        fp.Value().SetTextSize(pcbnew.VECTOR2I_MM(0.55, 0.55))
        fp.Value().SetTextThickness(mm(0.09))

    # Cell-to-AFE placement fact, called out on the drawing layer.
    add_line(board, 10.5, 79.5, 10.0, CELL_Y - 2.5, pcbnew.Dwgs_User, 0.15)
    add_text(board, "LMP centre -> cell pin row 11.5 mm", 18.8, 85.8,
             pcbnew.Dwgs_User, 0.55, 90)
    add_text(board, "REV-A PLACEMENT ONLY - UNROUTED", 10.0, 124.0,
             pcbnew.Cmts_User, 0.8)
    return board


def main():
    board = build()
    board.Save(str(OUT))
    # A load/save round trip is the minimum proof that the result is real KiCad.
    check = pcbnew.LoadBoard(str(OUT))
    # KiCad's unnetted-placement DRC does not reliably report an unnetted pad
    # beyond Edge.Cuts, so enforce the rectangular envelope independently.
    for fp in check.Footprints():
        if fp.GetReference().startswith("MS"):
            continue
        for pad in fp.Pads():
            box = pad.GetBoundingBox()
            x0 = pcbnew.ToMM(box.GetX() - ORG.x)
            y0 = pcbnew.ToMM(box.GetY() - ORG.y)
            x1 = x0 + pcbnew.ToMM(box.GetWidth())
            y1 = y0 + pcbnew.ToMM(box.GetHeight())
            if x0 < 0.5 or x1 > W - 0.5 or y0 < 0.5 or y1 > L - 0.5:
                raise SystemExit(
                    f"{fp.GetReference()}.{pad.GetNumber()}: pad bbox "
                    f"({x0:.2f},{y0:.2f})..({x1:.2f},{y1:.2f}) outside 0.5 mm envelope"
                )
    check.Save(str(OUT))
    print(f"wrote {OUT}")
    print(f"footprints: {len(list(check.Footprints()))} incl. 6 mechanical slots")
    print(f"outline: {W:g} x {L:g} mm, R{R:g}; thickness 1.0 mm")
    print(f"cell datum changed to ({CELL_X:g}, {CELL_Y:g}) to shorten AFE traces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
