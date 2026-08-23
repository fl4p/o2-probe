#!/usr/bin/env python3
"""Fabrication gate for the accepted O2-probe PCB.

This audit checks the schematic/PCB contract, the high-impedance cell-input
geometry, the guarded potting transition, the slot-free heated-ring tip, the
continuous ground plane, process limits, and KiCad DRC.  ``--calibrate`` also
mutates fresh in-memory copies and proves the load-bearing checks reject
known-bad variants.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import wx

_APP = wx.AppConsole()
import pcbnew  # noqa: E402  (wx.App must exist before pcbnew loads a board)

import project_settings  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_BOARD = HERE / "o2-probe.kicad_pcb"
XML = HERE / "o2-probe.xml"
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
DEFAULT_DRC = HERE / "pcb-drc-warnings.json"

ALLOWED_WARNING_TYPES = {
    "courtyards_overlap",
    "silk_edge_clearance",
    "silk_overlap",
    "silk_over_copper",
}

# These density exceptions are acceptable for hand assembly and are never
# exported as legend layers in the bare-board release.  Any changed pair fails
# the audit and requires a new physical assembly review.
COURTYARD_ALLOWLIST = {
    tuple(sorted(pair))
    for pair in {
        ("R17", "U4"), ("D1", "J101"), ("C25", "J2"), ("C1", "U1"),
        ("C11", "C12"), ("C3", "L1"), ("C23", "U11"), ("Q2", "TP6"),
        ("TP3", "U4"), ("J104", "R3"), ("C5", "U2"), ("D6", "J2"),
        ("J2", "TP1"), ("J2", "TP5"), ("C14", "C26"), ("D2", "J103"),
        ("J103", "R2"), ("D4", "R12"), ("R10", "R11"), ("R22", "R23"),
        ("D1", "J102"), ("C31", "RV1"), ("R20", "RV1"), ("R38", "RV1"),
        ("C15", "R8"), ("C15", "R9"), ("D2", "J104"), ("D5", "R14"),
        ("U10", "U11"),
    }
}


def mm(value: int) -> float:
    return pcbnew.ToMM(value)


def xy(point) -> tuple[float, float]:
    return mm(point.x), mm(point.y)


def near(actual: float, wanted: float, tolerance: float = 0.01) -> bool:
    return abs(actual - wanted) <= tolerance


def rounded_point(point) -> tuple[float, float]:
    return tuple(round(value, 2) for value in xy(point))


def edge_signature(item):
    start = rounded_point(item.GetStart())
    end = rounded_point(item.GetEnd())
    midpoint = rounded_point(item.GetArcMid()) if item.GetShapeStr() == "Arc" else None
    return item.GetShapeStr(), frozenset((start, end)), midpoint, round(mm(item.GetWidth()), 2)


def expected_outline_geometry() -> Counter:
    """Return the exact eight primitives for the 20 x 107 mm R2 outline."""
    expected = Counter()

    def absolute(local_point):
        return round(100.0 + local_point[0], 2), round(50.0 + local_point[1], 2)

    def line(start, end):
        expected[("Line", frozenset((absolute(start), absolute(end))), None, 0.05)] += 1

    def arc(start, midpoint, end):
        expected[("Arc", frozenset((absolute(start), absolute(end))),
                  absolute(midpoint), 0.05)] += 1

    line((2.0, 0.0), (18.0, 0.0))
    arc((18.0, 0.0), (19.414, 0.586), (20.0, 2.0))
    line((20.0, 2.0), (20.0, 105.0))
    arc((20.0, 105.0), (19.414, 106.414), (18.0, 107.0))
    line((18.0, 107.0), (2.0, 107.0))
    arc((2.0, 107.0), (0.586, 106.414), (0.0, 105.0))
    line((0.0, 105.0), (0.0, 2.0))
    arc((0.0, 2.0), (0.586, 0.586), (2.0, 0.0))
    return expected


def canonical_polygon(points) -> tuple[tuple[float, float], ...]:
    """Canonicalize a closed polygon independently of start and winding."""
    vertices = [rounded_point(point) for point in points]
    variants = []
    for sequence in (vertices, list(reversed(vertices))):
        variants.extend(tuple(sequence[index:] + sequence[:index])
                        for index in range(len(sequence)))
    return min(variants)


def check(errors: list[str], condition: bool, code: str, detail: str) -> None:
    if not condition:
        errors.append(f"{code}: {detail}")


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def load_contract() -> tuple[set[str], dict[tuple[str, str], str]]:
    root = ET.parse(XML).getroot()
    references = {component.attrib["ref"] for component in root.find("components")}
    nets: dict[tuple[str, str], str] = {}
    for net in root.find("nets"):
        for node in net:
            nets[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]
    return references, nets


def collect_geometry_errors(board, board_text: str) -> tuple[list[str], dict[str, float]]:
    errors: list[str] = []
    metrics: dict[str, float] = {}
    wanted_refs, wanted_nets = load_contract()
    footprints = {footprint.GetReference(): footprint for footprint in board.Footprints()}

    check(errors, set(footprints) == wanted_refs, "FOOTPRINT_SET",
          f"PCB-only={sorted(set(footprints) - wanted_refs)}; schematic-only={sorted(wanted_refs - set(footprints))}")
    for ref, footprint in footprints.items():
        for pad in footprint.Pads():
            number = pad.GetNumber()
            if not number:
                continue
            key = ref, number
            check(errors, key in wanted_nets, "PAD_NOT_IN_SCHEMATIC", f"{ref}.{number}")
            if key in wanted_nets:
                check(errors, pad.GetNetname() == wanted_nets[key], "PAD_NET",
                      f"{ref}.{number} is {pad.GetNetname()}, want {wanted_nets[key]}")

    bbox = board.GetBoardEdgesBoundingBox()
    check(errors, near(mm(bbox.GetWidth()), 20.05), "OUTLINE_WIDTH",
          f"edge bounding box is {mm(bbox.GetWidth()):.3f} mm, want 20.05 including stroke")
    check(errors, near(mm(bbox.GetHeight()), 107.05), "OUTLINE_HEIGHT",
          f"edge bounding box is {mm(bbox.GetHeight()):.3f} mm, want 107.05 including stroke")
    check(errors, near(mm(board.GetDesignSettings().GetBoardThickness()), 1.0),
          "BOARD_THICKNESS", "board is not 1.00 mm")
    check(errors, board.GetCopperLayerCount() == 4, "COPPER_LAYERS",
          f"found {board.GetCopperLayerCount()}, want four")
    edge_items = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    check(errors, len(edge_items) == 8, "EDGE_ITEM_COUNT",
          f"found {len(edge_items)}, want the eight-item outer outline only")
    actual_outline = Counter(edge_signature(item) for item in edge_items)
    expected_outline = expected_outline_geometry()
    check(errors, actual_outline == expected_outline, "OUTLINE_GEOMETRY",
          f"added/changed={list((actual_outline - expected_outline).elements())}; "
          f"missing={list((expected_outline - actual_outline).elements())}")
    expected_tip_placements = {
        "RH1": ((105.0, 146.5), 270.0, "B.Cu"),
        "RH2": ((115.0, 146.5), 270.0, "B.Cu"),
        "Q2": ((110.0, 151.25), 270.0, "B.Cu"),
        "R28": ((106.5, 151.25), 180.0, "B.Cu"),
        "R29": ((113.5, 151.25), 180.0, "B.Cu"),
        "TP6": ((108.3, 153.0), 180.0, "B.Cu"),
        "U12": ((103.5, 151.5), 0.0, "F.Cu"),
        "C20": ((106.0, 151.5), 90.0, "F.Cu"),
        "U10": ((110.0, 152.0), 270.0, "F.Cu"),
        "C21": ((112.5, 152.5), 90.0, "F.Cu"),
        "U14": ((116.5, 151.0), 0.0, "F.Cu"),
        "C23": ((114.0, 150.0), 180.0, "F.Cu"),
        "C24": ((114.0, 152.0), 180.0, "F.Cu"),
        "J5": ((110.0, 155.75), 0.0, "F.Cu"),
    }
    for ref, (wanted_position, wanted_angle, wanted_layer) in expected_tip_placements.items():
        footprint = footprints.get(ref)
        if footprint is None:
            continue
        position = xy(footprint.GetPosition())
        angle = footprint.GetOrientation().AsDegrees() % 360
        check(errors,
              all(near(actual, wanted) for actual, wanted in zip(position, wanted_position))
              and near(angle, wanted_angle) and footprint.GetLayerName() == wanted_layer,
              "TIP_PLACEMENT",
              f"{ref} at {position}, {angle:g} degrees on {footprint.GetLayerName()}")

    expected_compact_placements = {
        "C8": ((118.0, 87.5), 90.0, "F.Cu"),
        "U6": ((114.5, 94.5), 180.0, "F.Cu"),
    }
    for ref, (wanted_position, wanted_angle, wanted_layer) in expected_compact_placements.items():
        footprint = footprints.get(ref)
        if footprint is None:
            continue
        position = xy(footprint.GetPosition())
        angle = footprint.GetOrientation().AsDegrees() % 360
        check(errors,
              all(near(actual, wanted) for actual, wanted in zip(position, wanted_position))
              and near(angle, wanted_angle) and footprint.GetLayerName() == wanted_layer,
              "MCU_CLUSTER_PLACEMENT",
              f"{ref} at {position}, {angle:g} degrees on {footprint.GetLayerName()}")

    ring = footprints.get("J5")
    if ring is not None:
        ring_id = ring.GetFPID()
        actual_ring_fpid = f"{ring_id.GetLibNickname()}:{ring_id.GetLibItemName()}"
        check(errors, actual_ring_fpid == "o2-probe:Heater_Ring_Solder_Lands",
              "RING_FOOTPRINT", actual_ring_fpid)
        ring_land_signatures = Counter()
        for pad in ring.Pads():
            copper_layer = "F.Cu" if pad.IsOnLayer(pcbnew.F_Cu) else (
                "B.Cu" if pad.IsOnLayer(pcbnew.B_Cu) else "none"
            )
            ring_land_signatures[(
                rounded_point(pad.GetPosition()), rounded_point(pad.GetSize()),
                pad.GetNumber(), pad.GetNetname(), copper_layer,
                pad.IsOnLayer(pcbnew.F_Mask), pad.IsOnLayer(pcbnew.B_Mask),
                pad.IsOnLayer(pcbnew.F_Paste), pad.IsOnLayer(pcbnew.B_Paste),
            )] += 1
        expected_ring_lands = Counter({
            ((104.75, 155.75), (5.0, 1.5), "1", "/HEATER_LOW",
             "F.Cu", True, False, False, False): 1,
            ((104.75, 155.75), (5.0, 1.5), "1", "/HEATER_LOW",
             "B.Cu", False, True, False, False): 1,
            ((115.25, 155.75), (5.0, 1.5), "1", "/HEATER_LOW",
             "F.Cu", True, False, False, False): 1,
            ((115.25, 155.75), (5.0, 1.5), "1", "/HEATER_LOW",
             "B.Cu", False, True, False, False): 1,
        })
        check(errors, ring_land_signatures == expected_ring_lands,
              "RING_LAND_GEOMETRY",
              f"added/changed={list((ring_land_signatures - expected_ring_lands).elements())}; "
              f"missing={list((expected_ring_lands - ring_land_signatures).elements())}")

    heater_low_items = [item for item in board.GetTracks()
                        if item.GetNetname() == "/HEATER_LOW"]
    heater_low_tracks = [item for item in heater_low_items
                         if not isinstance(item, pcbnew.PCB_VIA)]
    heater_low_vias = [item for item in heater_low_items
                       if isinstance(item, pcbnew.PCB_VIA)]
    check(errors, heater_low_tracks and all(
        item.GetLayer() == pcbnew.B_Cu and mm(item.GetWidth()) >= 0.80 - 0.0001
        for item in heater_low_tracks
    ), "RING_HEATER_COPPER",
          "HEATER_LOW must use only >=0.80 mm B.Cu tracks between the elements, switch, and ring")
    ring_via_signature = Counter(
        (rounded_point(item.GetPosition()), round(mm(item.GetWidth(pcbnew.F_Cu)), 2),
         round(mm(item.GetDrillValue()), 2))
        for item in heater_low_vias
    )
    expected_ring_vias = Counter({
        ((104.75, 155.75), 0.60, 0.30): 1,
        ((115.25, 155.75), 0.60, 0.30): 1,
    })
    check(errors, ring_via_signature == expected_ring_vias, "RING_STITCH_VIAS",
          f"added/changed={list((ring_via_signature - expected_ring_vias).elements())}; "
          f"missing={list((expected_ring_vias - ring_via_signature).elements())}")

    obsolete_tip_nets = {"/TGAS_ALERT", "/TMP_GAS_EP"}
    stale_copper = [item.GetNetname() for item in board.GetTracks()
                    if item.GetNetname() in obsolete_tip_nets]
    check(errors, not stale_copper, "OBSOLETE_TIP_COPPER",
          f"obsolete two-temperature-sensor copper remains: {stale_copper}")
    if "U10" in footprints and ring is not None:
        metrics["tmp117_ring_distance_mm"] = math.dist(
            xy(footprints["U10"].GetPosition()), xy(ring.GetPosition())
        )

    # The source owns a complete process stack; the dielectric values are a
    # nominal 1.0 mm model and the fab note authorises vendor adjustment.
    required_stackup = (
        '(stackup', '(layer "F.Cu"', '(thickness 0.035)',
        '(layer "In1.Cu"', '(thickness 0.0175)', '(layer "In2.Cu"',
        '(layer "B.Cu"', '(thickness 0.695)', '(copper_finish "ENIG")',
    )
    check(errors, all(token in board_text for token in required_stackup), "STACKUP",
          "complete four-layer 1.0 mm ENIG stackup is missing")

    check(errors, "TP2" not in footprints, "CELL_RE_TESTPOINT",
          "TP2 exposes the high-impedance CELL_RE node")
    if "U7" not in footprints or "U11" not in footprints:
        return errors, metrics

    u7 = footprints["U7"]
    u11 = footprints["U11"]
    u7_pos = xy(u7.GetPosition())
    u11_pos = xy(u11.GetPosition())
    u7_angle = u7.GetOrientation().AsDegrees() % 360
    check(errors, near(u7_pos[0], 110.0) and near(u7_pos[1], 129.5) and near(u7_angle, 270),
          "U7_PLACEMENT", f"U7 at {u7_pos}, {u7_angle:g} degrees")
    check(errors, u7_pos[1] + 2.0 <= 132.0, "U7_POT_SIDE",
          "U7 body crosses the y=132 potting boundary")
    lib_id = u11.GetFPID()
    actual_fpid = f"{lib_id.GetLibNickname()}:{lib_id.GetLibItemName()}"
    check(errors, actual_fpid == "o2-probe:SGX-OX-ROHS-Mini_ISS2", "U11_FOOTPRINT",
          actual_fpid)
    check(errors, near(u11_pos[0], 110.0) and near(u11_pos[1], 143.5),
          "U11_PLACEMENT", f"U11 at {u11_pos}")

    u7_pads = {pad.GetNumber(): pad for pad in u7.Pads() if pad.GetNumber()}
    u11_pads = {pad.GetNumber(): pad for pad in u11.Pads() if pad.GetNumber()}
    if "13" in u7_pads and "2" in u11_pads:
        re_distance = math.dist(xy(u7_pads["13"].GetPosition()), xy(u11_pads["2"].GetPosition()))
        metrics["cell_re_pin_distance_mm"] = re_distance
        check(errors, re_distance < 10.0, "U7_CELL_DISTANCE",
              f"U7.13 to U11.2 is {re_distance:.3f} mm, must be <10 mm")
    else:
        errors.append("CELL_RE_PADS: U7.13 or U11.2 missing")

    for number, wanted_position in {
        "1": (107.46, 141.0), "2": (110.0, 141.0), "3": (112.54, 141.0)
    }.items():
        if number not in u11_pads:
            errors.append(f"U11_PAD_GEOMETRY: pad {number} missing")
            continue
        pad = u11_pads[number]
        size = xy(pad.GetSize())
        drill = xy(pad.GetDrillSize())
        check(errors, all(near(a, b) for a, b in zip(xy(pad.GetPosition()), wanted_position))
              and all(near(value, 1.6) for value in size)
              and all(near(value, 0.9) for value in drill),
              "U11_PAD_GEOMETRY", f"pad {number} position/land/drill differs from DS-0637 Issue 2")

    apertures = [pad for pad in u11.Pads()
                 if not pad.GetNumber() and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    check(errors, len(apertures) == 1, "SENSOR_APERTURE_COUNT",
          f"found {len(apertures)}, want one NPTH slot")
    if len(apertures) == 1:
        aperture = apertures[0]
        aperture_position = xy(aperture.GetPosition())
        aperture_drill = xy(aperture.GetDrillSize())
        check(errors,
              near(aperture_position[0], 110.0) and near(aperture_position[1], 146.0)
              and near(aperture_drill[0], 3.0) and near(aperture_drill[1], 6.0)
              and aperture.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG,
              "SENSOR_APERTURE_GEOMETRY",
              f"slot at {aperture_position}, drill {aperture_drill}")
        check(errors, aperture_position[1] - aperture_drill[1] / 2 <= u11_pos[1],
              "SENSOR_APERTURE_AXIS", "gasward slot does not include the sensor rear axis")

    # CELL_RE must be a single top-layer, no-via connection with no exposed
    # test feature.  The two component terminations are the only mask openings.
    cell_items = [item for item in board.GetTracks() if item.GetNetname() == "/CELL_RE"]
    cell_vias = [item for item in cell_items if isinstance(item, pcbnew.PCB_VIA)]
    cell_tracks = [item for item in cell_items if not isinstance(item, pcbnew.PCB_VIA)]
    check(errors, not cell_vias, "CELL_RE_VIA", f"found {len(cell_vias)} vias")
    check(errors, len(cell_tracks) == 1, "CELL_RE_ROUTE_COUNT",
          f"found {len(cell_tracks)} trace segments, want one")
    if len(cell_tracks) == 1:
        trace = cell_tracks[0]
        metrics["cell_re_trace_length_mm"] = math.dist(xy(trace.GetStart()), xy(trace.GetEnd()))
        check(errors, trace.GetLayer() == pcbnew.F_Cu and near(mm(trace.GetWidth()), 0.15),
              "CELL_RE_ROUTE", f"CELL_RE is on {trace.GetLayerName()} at {mm(trace.GetWidth()):.3f} mm")
    cell_pads = {(footprint.GetReference(), pad.GetNumber())
                 for footprint in board.Footprints() for pad in footprint.Pads()
                 if pad.GetNetname() == "/CELL_RE"}
    check(errors, cell_pads == {("U7", "13"), ("U11", "2")}, "CELL_RE_APERTURES",
          f"CELL_RE appears on pads {sorted(cell_pads)}")

    guard_zones = [zone for zone in board.Zones()
                   if zone.GetNetname() == "/GUARD_REPLICA" and zone.IsOnLayer(pcbnew.F_Cu)]
    check(errors, len(guard_zones) == 1, "GUARD_ZONE",
          f"found {len(guard_zones)} top-layer guard zones")
    guard_vias = [item for item in board.GetTracks()
                  if isinstance(item, pcbnew.PCB_VIA) and item.GetNetname() == "/GUARD_REPLICA"]
    check(errors, any(math.dist(xy(via.GetPosition()), (109.55, 132.8)) < 0.01 for via in guard_vias),
          "GUARD_TRANSITION_VIA", "driven guard does not enter the cell-route enclosure")
    if len(guard_zones) == 1:
        guard = guard_zones[0]
        polygon = [xy(guard.GetCornerPosition(index)) for index in range(guard.GetNumCorners())]
        check(errors, point_in_polygon((110.2, 136.0), polygon)
              and point_in_polygon((110.1, 140.5), polygon),
              "GUARD_ENCLOSURE", "guard polygon does not enclose the long CELL_RE run")

    gnd_zones = [zone for zone in board.Zones()
                 if zone.GetNetname() == "/GND" and zone.IsOnLayer(pcbnew.In2_Cu)]
    check(errors, len(gnd_zones) == 1, "GND_ZONE_COUNT",
          f"found {len(gnd_zones)} In2 GND zones, want one continuous plane")
    if len(gnd_zones) == 1:
        actual_zone_outlines = Counter(
            canonical_polygon([zone.GetCornerPosition(index)
                               for index in range(zone.GetNumCorners())])
            for zone in gnd_zones
        )
        expected_zone_outlines = Counter({
            canonical_polygon([pcbnew.VECTOR2I_MM(x, y) for x, y in corners]): 1
            for corners in (
                ((100.25, 50.25), (119.75, 50.25),
                 (119.75, 156.75), (100.25, 156.75)),
            )
        })
        check(errors, actual_zone_outlines == expected_zone_outlines,
              "GND_ZONE_GEOMETRY",
              f"added/changed={list((actual_zone_outlines - expected_zone_outlines).elements())}; "
              f"missing={list((expected_zone_outlines - actual_zone_outlines).elements())}")
        check(errors,
              all(zone.IsFilled() and zone.HasFilledPolysForLayer(pcbnew.In2_Cu)
                  for zone in gnd_zones),
              "GND_ZONE_FILL", "the controlled continuous In2 GND plane is not filled")
    in2_gnd_tracks = [item for item in board.GetTracks()
                      if not isinstance(item, pcbnew.PCB_VIA)
                      and item.GetNetname() == "/GND"
                      and item.GetLayer() == pcbnew.In2_Cu]
    check(errors, not in2_gnd_tracks, "GND_ZONE_BRIDGE",
          f"found {len(in2_gnd_tracks)} obsolete narrow In2 GND bridges")

    tracks = [item for item in board.GetTracks() if not isinstance(item, pcbnew.PCB_VIA)]
    vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
    min_track = min((mm(item.GetWidth()) for item in tracks), default=99.0)
    min_via = min((mm(item.GetWidth(pcbnew.F_Cu)) for item in vias), default=99.0)
    min_drill = min((mm(item.GetDrillValue()) for item in vias), default=99.0)
    metrics.update(min_track_width_mm=min_track, min_via_diameter_mm=min_via,
                   min_via_drill_mm=min_drill, track_via_objects=len(list(board.GetTracks())))
    check(errors, min_track >= 0.09 - 0.0001, "MIN_TRACK_WIDTH",
          f"minimum track is {min_track:.4f} mm")
    check(errors, min_via >= 0.25 - 0.0001 and min_drill >= 0.15 - 0.0001,
          "MIN_VIA", f"minimum via/drill is {min_via:.3f}/{min_drill:.3f} mm")

    track_signatures = Counter(
        (item.GetNetname(), item.GetLayer(), item.GetWidth(),
         frozenset(((item.GetStart().x, item.GetStart().y),
                    (item.GetEnd().x, item.GetEnd().y))))
        for item in tracks
    )
    via_signatures = Counter(
        (item.GetNetname(), item.GetPosition().x, item.GetPosition().y,
         item.GetWidth(pcbnew.F_Cu), item.GetDrillValue(),
         item.TopLayer(), item.BottomLayer())
        for item in vias
    )
    duplicate_tracks = [signature for signature, count in track_signatures.items() if count > 1]
    duplicate_vias = [signature for signature, count in via_signatures.items() if count > 1]
    check(errors, not duplicate_tracks and not duplicate_vias, "DUPLICATE_COPPER",
          f"exact duplicate tracks={len(duplicate_tracks)}, vias={len(duplicate_vias)}")

    pot_lines = [item for item in board.Drawings()
                 if isinstance(item, pcbnew.PCB_SHAPE)
                 and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
                 and near(xy(item.GetStart())[1], 132.0)
                 and near(xy(item.GetEnd())[1], 132.0)]
    texts = [item.GetText() for item in board.Drawings() if isinstance(item, pcbnew.PCB_TEXT)]
    check(errors, len(pot_lines) == 2 and texts.count("POT TO HERE") == 2,
          "POT_MARKERS", "front/back y=132 potting markers are missing")
    check(errors, "DO NOT OBSTRUCT" in texts, "APERTURE_MARKER",
          "sensor aperture warning text is missing")
    return errors, metrics


def read_drc(board_path: Path, report: Path) -> tuple[list[str], Counter]:
    errors: list[str] = []
    check(errors, report.is_file(), "DRC_REPORT", f"{report} is missing")
    if not report.is_file():
        return errors, Counter()
    check(errors, report.stat().st_mtime >= board_path.stat().st_mtime, "DRC_STALE",
          f"{report.name} predates {board_path.name}; regenerate it with kicad-cli")
    data = json.loads(report.read_text())
    check(errors, data.get("source") == board_path.name, "DRC_SOURCE",
          f"report source is {data.get('source')!r}, want {board_path.name!r}")

    all_findings = data.get("violations", [])
    for section in ("violations", "unconnected_items", "schematic_parity"):
        for finding in data.get(section, []):
            if finding.get("severity") == "error":
                errors.append(f"DRC_ERROR: {section}: {finding.get('description')}")
    check(errors, not data.get("unconnected_items"), "DRC_UNCONNECTED",
          f"found {len(data.get('unconnected_items', []))} unconnected items")
    check(errors, not data.get("schematic_parity"), "DRC_PARITY",
          f"found {len(data.get('schematic_parity', []))} schematic-parity findings")
    warning_types = Counter(finding.get("type") for finding in all_findings
                            if finding.get("severity") == "warning")
    unexpected = set(warning_types) - ALLOWED_WARNING_TYPES
    check(errors, not unexpected, "DRC_WARNING_TYPE",
          f"unreviewed warning types: {sorted(unexpected)}")

    actual_pairs = set()
    for finding in all_findings:
        if finding.get("type") != "courtyards_overlap":
            continue
        references = []
        for item in finding.get("items", []):
            match = re.search(r"Footprint (\S+)", item.get("description", ""))
            if match:
                references.append(match.group(1))
        if len(references) == 2:
            actual_pairs.add(tuple(sorted(references)))
    check(errors, actual_pairs == COURTYARD_ALLOWLIST, "COURTYARD_ALLOWLIST",
          f"added={sorted(actual_pairs - COURTYARD_ALLOWLIST)}; removed={sorted(COURTYARD_ALLOWLIST - actual_pairs)}")
    return errors, warning_types


def calibrate(board_path: Path, board_text: str) -> list[str]:
    failures: list[str] = []

    def expect(name: str, code: str, mutation, text: str = board_text) -> None:
        board = pcbnew.LoadBoard(str(board_path))
        mutation(board)
        errors, _ = collect_geometry_errors(board, text)
        if not any(error.startswith(code + ":") for error in errors):
            failures.append(f"{name}: expected {code}, got {errors[:4]}")

    def add_cell_via(board) -> None:
        source = next(item for item in board.GetTracks() if item.GetNetname() == "/CELL_RE")
        via = pcbnew.PCB_VIA(board)
        via.SetNet(source.GetNet())
        via.SetPosition(pcbnew.VECTOR2I_MM(110.5, 136.2))
        via.SetWidth(pcbnew.FromMM(0.25))
        via.SetDrill(pcbnew.FromMM(0.15))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)

    def remove_guard(board) -> None:
        zone = next(zone for zone in board.Zones() if zone.GetNetname() == "/GUARD_REPLICA")
        zone.SetNetCode(0)

    def remove_gnd_zone(board) -> None:
        zone = next(zone for zone in board.Zones() if zone.GetNetname() == "/GND")
        zone.SetNetCode(0)

    def add_board_native_slot(board) -> None:
        item = pcbnew.PCB_SHAPE(board)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(pcbnew.VECTOR2I_MM(105.0, 145.0))
        item.SetEnd(pcbnew.VECTOR2I_MM(115.0, 145.0))
        item.SetLayer(pcbnew.Edge_Cuts)
        item.SetWidth(pcbnew.FromMM(0.05))
        board.Add(item)

    def deform_outer_corner(board) -> None:
        item = next(
            item for item in board.Drawings()
            if item.GetLayer() == pcbnew.Edge_Cuts
            and item.GetShapeStr() == "Arc"
            and near(xy(item.GetArcMid())[0], 119.414)
            and near(xy(item.GetArcMid())[1], 50.586)
        )
        item.SetArcGeometry(item.GetStart(), pcbnew.VECTOR2I_MM(119.0, 51.0), item.GetEnd())

    def notch_gnd_zone(board) -> None:
        zone = next(
            zone for zone in board.Zones()
            if zone.GetNetname() == "/GND"
            and zone.IsOnLayer(pcbnew.In2_Cu)
        )
        outline = pcbnew.VECTOR_VECTOR2I()
        for x, y in ((100.25, 50.25), (119.75, 50.25),
                     (119.75, 156.75), (110.0, 156.75),
                     (110.0, 155.5), (100.25, 155.5)):
            outline.append(pcbnew.VECTOR2I_MM(x, y))
        zone.Outline().RemoveAllContours()
        zone.AddPolygon(outline)

    def unfill_gnd_zone(board) -> None:
        zone = next(zone for zone in board.Zones()
                    if zone.GetNetname() == "/GND" and zone.IsOnLayer(pcbnew.In2_Cu))
        zone.UnFill()

    def move_ring(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "J5")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(110.0, 154.5))

    def deform_ring_land(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "J5")
        next(iter(footprint.Pads())).SetSize(pcbnew.VECTOR2I_MM(4.5, 1.5))

    def remove_ring_stitch(board) -> None:
        via = next(item for item in board.GetTracks()
                   if isinstance(item, pcbnew.PCB_VIA)
                   and item.GetNetname() == "/HEATER_LOW")
        via.SetNetCode(0)

    def add_obsolete_tip_copper(board) -> None:
        net = board.FindNet("/TGAS_ALERT")
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, "/TGAS_ALERT")
            board.Add(net)
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(net)
        track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(101.0, 154.0))
        track.SetEnd(pcbnew.VECTOR2I_MM(102.0, 154.0))
        track.SetWidth(pcbnew.FromMM(0.18))
        board.Add(track)

    def narrow_ring_copper(board) -> None:
        track = next(item for item in board.GetTracks()
                     if not isinstance(item, pcbnew.PCB_VIA)
                     and item.GetNetname() == "/HEATER_LOW")
        track.SetWidth(pcbnew.FromMM(0.40))

    def narrow_track(board) -> None:
        track = next(item for item in board.GetTracks() if not isinstance(item, pcbnew.PCB_VIA))
        track.SetWidth(pcbnew.FromMM(0.08))

    def move_u7(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U7")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(110.0, 120.0))

    def move_compact_mcu(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U6")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(113.5, 94.5))

    def duplicate_track(board) -> None:
        source = next(item for item in board.GetTracks()
                      if not isinstance(item, pcbnew.PCB_VIA))
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(source.GetNet())
        item.SetLayer(source.GetLayer())
        item.SetStart(source.GetStart())
        item.SetEnd(source.GetEnd())
        item.SetWidth(source.GetWidth())
        board.Add(item)

    expect("CELL_RE via", "CELL_RE_VIA", add_cell_via)
    expect("missing guard", "GUARD_ZONE", remove_guard)
    expect("missing continuous GND plane", "GND_ZONE_COUNT", remove_gnd_zone)
    expect("reintroduced board-native slot", "EDGE_ITEM_COUNT", add_board_native_slot)
    expect("deformed outer R2 corner", "OUTLINE_GEOMETRY", deform_outer_corner)
    expect("notched continuous GND plane", "GND_ZONE_GEOMETRY", notch_gnd_zone)
    expect("unfilled controlled ground zone", "GND_ZONE_FILL", unfill_gnd_zone)
    expect("moved membrane ring", "TIP_PLACEMENT", move_ring)
    expect("deformed membrane-ring land", "RING_LAND_GEOMETRY", deform_ring_land)
    expect("missing membrane-ring stitch", "RING_STITCH_VIAS", remove_ring_stitch)
    expect("obsolete second-sensor copper", "OBSOLETE_TIP_COPPER", add_obsolete_tip_copper)
    expect("narrow heater-to-ring copper", "RING_HEATER_COPPER", narrow_ring_copper)
    expect("sub-process-width trace", "MIN_TRACK_WIDTH", narrow_track)
    expect("remote AFE", "U7_PLACEMENT", move_u7)
    expect("moved compact MCU", "MCU_CLUSTER_PLACEMENT", move_compact_mcu)
    expect("exact duplicate copper", "DUPLICATE_COPPER", duplicate_track)
    expect("missing fab stackup", "STACKUP", lambda board: None, text="")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--drc-report", type=Path, default=DEFAULT_DRC)
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()

    board_path = args.board.resolve()
    board_text = board_path.read_text()
    board = pcbnew.LoadBoard(str(board_path))
    errors, metrics = collect_geometry_errors(board, board_text)
    settings_summary = project_settings.verify(HERE / "o2-probe.kicad_pro")
    drc_errors, warnings = read_drc(board_path, args.drc_report.resolve())
    errors.extend(drc_errors)

    calibration_failures = calibrate(board_path, board_text) if args.calibrate else []
    errors.extend(f"CALIBRATION: {failure}" for failure in calibration_failures)
    report = HERE / "pcb-audit.rpt"
    if errors:
        report.write_text("FAIL: O2 probe fabrication audit\n" + "\n".join(f"- {error}" for error in errors) + "\n")
        print(report.read_text(), end="")
        return 1

    calibrated = "17/17 known-bad variants rejected" if args.calibrate else "not requested"
    report.write_text(
        "PASS: O2 probe fabrication audit\n"
        f"- 106 schematic footprints; 20.00 x 107.00 x 1.00 mm; four copper layers\n"
        f"- CELL_RE: {metrics['cell_re_trace_length_mm']:.3f} mm single F.Cu segment, no via/testpoint; "
        f"U7-to-cell pin distance {metrics['cell_re_pin_distance_mm']:.3f} mm\n"
        "- no board-native routed slots; one exact filled In2 GND plane across the slot-free board\n"
        f"- heated ring: four exact 5.00 x 1.50 mm mask-only lands, two 0.60/0.30 mm stitches; "
        f"TMP117-to-ring-center {metrics['tmp117_ring_distance_mm']:.3f} mm\n"
        f"- minimum track/via/drill {metrics['min_track_width_mm']:.2f}/"
        f"{metrics['min_via_diameter_mm']:.2f}/{metrics['min_via_drill_mm']:.2f} mm\n"
        "- KiCad: 0 errors, 0 unconnected, 0 parity; "
        f"reviewed warnings {dict(sorted(warnings.items()))}\n"
        f"- project rules: {settings_summary}\n"
        f"- calibration: {calibrated}\n"
    )
    print(report.read_text(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
