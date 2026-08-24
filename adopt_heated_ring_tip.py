#!/usr/bin/env python3
"""Adopt the user-authored heated-ring tip floorplan into the routed board.

This one-way migration removes the obsolete gas-reference TMP117 circuit and
obsolete tip-slot set, shortens the board to 107 mm with a square gas-side end,
restores the two intended horizontal thermal-break slots at absolute Y=134 mm,
installs castellated manual-solder ring contacts, compacts the MCU beside the
RS-485 transceiver, aligns the retained
components to ``gen_pcb.py``, and replaces the formerly split In2 GND regions
with one controlled source zone. The final all-layer thermal rule area splits
that zone's fill into two regions joined by one narrow track. Local copper is
completed separately after the mechanical migration is checked.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import (THERMAL_SLOTS, ensure_gnd_bridge,
                            ensure_heater_spreader, ensure_thermal_gap,
                            save_board_preserving_project)
from route_thermal_barrier import apply as route_thermal_barrier


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
XML = HERE / "o2-probe.xml"
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0
NEW_LENGTH_MM = 107.0

PLACEMENT = {
    "C8": (18.0, 37.5, 90.0, "F"),
    "U6": (14.5, 44.5, 180.0, "F"),
    "RH1": (5.0, 96.5, 270.0, "B"),
    "RH2": (15.0, 96.5, 270.0, "B"),
    "Q2": (10.0, 101.25, 270.0, "B"),
    "R28": (6.5, 101.25, 180.0, "B"),
    "R29": (13.5, 101.25, 180.0, "B"),
    "TP6": (8.3, 103.0, 180.0, "B"),
    "U12": (3.5, 101.5, 0.0, "F"),
    "C20": (6.0, 101.5, 90.0, "F"),
    "U10": (10.0, 102.0, 270.0, "F"),
    "C21": (12.5, 102.5, 90.0, "F"),
    "U14": (16.5, 101.0, 0.0, "F"),
    "C23": (14.0, 100.0, 180.0, "F"),
    "C24": (14.0, 102.0, 180.0, "F"),
    "J5": (10.0, 105.5, 0.0, "F"),
}


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def local_xy(position) -> tuple[float, float]:
    return (
        round(pcbnew.ToMM(position.x) - ORIGIN_X_MM, 4),
        round(pcbnew.ToMM(position.y) - ORIGIN_Y_MM, 4),
    )


def edge_line(board, start, end) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(point(*start))
    shape.SetEnd(point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def edge_arc(board, start, midpoint, end) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(point(*start), point(*midpoint), point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def add_outline(board) -> None:
    width, radius, length = 20.0, 2.0, NEW_LENGTH_MM
    edge_line(board, (radius, 0), (width - radius, 0))
    edge_arc(board, (width - radius, 0), (width - 0.586, 0.586), (width, radius))
    edge_line(board, (width, radius), (width, length))
    edge_line(board, (width, length), (0, length))
    edge_line(board, (0, length), (0, radius))
    edge_arc(board, (0, radius), (0.586, 0.586), (radius, 0))


def add_horizontal_slot(board, x, y, length, width) -> None:
    x0, x1 = x - length / 2, x + length / 2
    y0, y1 = y - width / 2, y + width / 2
    radius = width / 2
    edge_line(board, (x0 + radius, y0), (x1 - radius, y0))
    edge_arc(board, (x1 - radius, y0), (x1, y), (x1 - radius, y1))
    edge_line(board, (x1 - radius, y1), (x0 + radius, y1))
    edge_arc(board, (x0 + radius, y1), (x0, y), (x0 + radius, y0))


def replace_zone_outline(zone, corners) -> None:
    outline = pcbnew.VECTOR_VECTOR2I()
    for x, y in corners:
        outline.append(point(x, y))
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(outline)


def schematic_contract():
    root = ET.parse(XML).getroot()
    components = {}
    for component in root.findall("./components/comp"):
        ref = component.attrib["ref"]
        props = {
            prop.attrib["name"]: prop.attrib.get("value", "")
            for prop in component.findall("property")
        }
        components[ref] = {
            "value": component.findtext("value", ""),
            "footprint": component.findtext("footprint", ""),
            "uuid": component.findtext("tstamps", ""),
            "dnp": "dnp" in props,
            "props": props,
        }
    node_nets = {}
    net_names = []
    for net in root.findall("./nets/net"):
        name = net.attrib["name"]
        net_names.append(name)
        for node in net.findall("node"):
            node_nets[(node.attrib["ref"], node.attrib["pin"])] = name
    return components, node_nets, net_names


def ensure_nets(board, names):
    result = {}
    for name in names:
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        result[name] = net
    return result


def set_placement(footprint, spec) -> None:
    x, y, angle, side = spec
    wanted_back = side == "B"
    is_back = footprint.GetLayer() == pcbnew.B_Cu
    footprint.SetPosition(point(x, y))
    if is_back != wanted_back:
        footprint.Flip(footprint.GetPosition(), False)
    footprint.SetOrientationDegrees(angle)
    footprint.Reference().SetLayer(pcbnew.B_Fab if wanted_back else pcbnew.F_Fab)
    for field in footprint.GetFields():
        field.SetVisible(False)


def main() -> int:
    # Clone J5 from a fresh generator seed.  KiCad 10's direct library-loader
    # SWIG proxy is not stable after another board is opened, while a typed
    # BOARD_ITEM duplicate transfers safely and preserves the schematic path.
    seed_context = tempfile.TemporaryDirectory(prefix="o2-ring-seed-")
    seed_path = Path(os.environ.get("O2_PCB_SEED", Path(seed_context.name) / "o2-probe.kicad_pcb"))
    if "O2_PCB_SEED" not in os.environ:
        environment = os.environ.copy()
        environment["O2_PCB_OUT"] = str(seed_path)
        subprocess.run([sys.executable, str(HERE / "gen_pcb.py")], cwd=HERE,
                       env=environment, check=True)
    seed_board = pcbnew.LoadBoard(str(seed_path))
    seed_ring = next(
        footprint for footprint in seed_board.Footprints()
        if footprint.GetReference() == "J5"
    )
    ring = pcbnew.Cast_to_FOOTPRINT(seed_ring.Duplicate(False))
    board = pcbnew.LoadBoard(str(SRC))
    components, node_nets, net_names = schematic_contract()
    nets = ensure_nets(board, net_names)
    footprints = {footprint.GetReference(): footprint for footprint in board.Footprints()}

    # U13 was removed in the user draft.  Its dedicated pull-up, extra bypass,
    # and thermal-pad land are deleted here rather than left as PCB-only parts.
    obsolete = {"U13", "C22", "R30", "TP7"}
    for reference in obsolete:
        footprint = footprints.pop(reference, None)
        if footprint is not None:
            board.Delete(footprint)

    if "J5" in footprints:
        raise SystemExit("J5 already exists; migration is one-way")
    ring_component = components["J5"]
    board.Add(ring)
    ring = next(
        footprint for footprint in board.Footprints()
        if footprint.GetReference() == "J5"
    )
    set_placement(ring, PLACEMENT["J5"])
    for key, value in ring_component["props"].items():
        if key not in ("Sheetname", "Sheetfile", "dnp"):
            ring.SetField(key, value)
    footprints["J5"] = ring

    missing = set(components) - set(footprints)
    extra = set(footprints) - set(components)
    if missing or extra:
        raise SystemExit(f"schematic/PCB footprint set differs: missing={sorted(missing)} extra={sorted(extra)}")

    for reference, spec in PLACEMENT.items():
        set_placement(footprints[reference], spec)

    # Rebind every numbered pad, including both duplicated-number J5 contacts and the
    # new one-node unconnected net on the MCU pin formerly used by U13 ALERT.
    # Also refresh schematic-owned custom fields; C20/C21 changed function in
    # this revision and must not retain their old thermal-sensor design notes.
    for reference, footprint in footprints.items():
        for key, value in components[reference]["props"].items():
            if key not in ("Sheetname", "Sheetfile", "dnp"):
                footprint.SetField(key, value)
        for field in footprint.GetFields():
            field.SetVisible(False)
        for pad in footprint.Pads():
            number = pad.GetNumber()
            if not number:
                continue
            name = node_nets.get((reference, number))
            if name is None:
                raise SystemExit(f"schematic has no net for {reference}.{number}")
            pad.SetNet(nets[name])

    for drawing in board.GetDrawings():
        if isinstance(drawing, pcbnew.PCB_TEXT) and drawing.GetText() == "GAS / DO NOT POT":
            drawing.SetPosition(point(10.0, 86.8))

    # Every obsolete slot and the partially moved draft outline are removed
    # together. Reconstruct the 20 x 107 mm contour with a rounded cable end
    # and square gas end, plus only the two
    # user-requested horizontal thermal-break slots at absolute Y=134 mm.
    old_edges = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    if len(old_edges) != 26:
        raise SystemExit(f"expected 26 draft Edge.Cuts items, found {len(old_edges)}")
    for item in old_edges:
        board.Delete(item)
    add_outline(board)
    for slot_spec in THERMAL_SLOTS:
        add_horizontal_slot(board, *slot_spec)
    ensure_thermal_gap(board)

    # Consolidate the two draft shapes into one controlled In2 GND source zone.
    # The all-layer rule area later splits its fill into two regions, connected
    # only by the explicit narrow bridge.
    gnd_zones = [
        zone for zone in board.Zones()
        if zone.GetNetname() == "/GND" and zone.IsOnLayer(pcbnew.In2_Cu)
    ]
    if len(gnd_zones) != 2:
        raise SystemExit(f"expected two draft In2 GND zones, found {len(gnd_zones)}")
    full_gnd = gnd_zones[0]
    for zone in gnd_zones[1:]:
        board.Delete(zone)
    replace_zone_outline(full_gnd, (
        (0.25, 0.25), (19.75, 0.25),
        (19.75, NEW_LENGTH_MM - 0.25), (0.25, NEW_LENGTH_MM - 0.25),
    ))

    # Remove obsolete gas-reference copper and redundant bridges/fragments in
    # the area that will be deterministically rerouted.
    removed = 0
    for item in list(board.GetTracks()):
        name = item.GetNetname()
        if name in ("/TGAS_ALERT", "/TMP_GAS_EP"):
            board.Delete(item)
            removed += 1
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            if name == "/3V3D" and local_xy(item.GetPosition()) == (14.6, 98.4):
                board.Delete(item)
                removed += 1
            continue
        start, end = local_xy(item.GetStart()), local_xy(item.GetEnd())
        if name == "/GND" and item.GetLayer() == pcbnew.In2_Cu \
                and min(start[1], end[1]) < 82.0 < max(start[1], end[1]):
            board.Delete(item)
            removed += 1
        elif name == "/+12V_SW" and max(start[1], end[1]) > 100.0:
            board.Delete(item)
            removed += 1
        elif name == "/3V3D" and item.GetLayer() == pcbnew.In1_Cu \
                and max(start[1], end[1]) > 100.0:
            board.Delete(item)
            removed += 1

    ensure_heater_spreader(board)
    ensure_gnd_bridge(board)
    route_thermal_barrier(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(
        f"wrote {OUT}: {len(footprints)} footprints, 20 x {NEW_LENGTH_MM:g} mm, "
        f"two 5.5 x 1.5 mm Y=134 slots, all-layer pour gap, heated B.Cu spreader; "
        f"removed {removed} obsolete copper items"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
