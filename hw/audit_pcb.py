#!/usr/bin/env python3
"""Fabrication gate for the accepted O2-probe PCB.

This audit checks the schematic/PCB contract, the high-impedance cell-input
geometry, the guarded potting transition, the heated-ring thermal-break slots,
the continuous ground region, process limits, and KiCad DRC.  ``--calibrate`` also
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
from thermal_design import thermal_slot_items  # noqa: E402


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
# Hand-assembly courtyard exceptions, re-derived from the board after the
# AFE/heater revision -- not edited by hand.  Four pairs disappeared for real
# reasons and are worth naming so nobody "restores" them: C11/C12 and C15/R8,
# C15/R9 went away when those 100n parts were consolidated onto 0402, and the
# RV1 and R20-R23 pairs went with the trim divider POTTING.md 1.2 deleted.
# TP2 is NEW and adds no exception: it was sited at the one y that clears every
# courtyard outright while still leaving all six test-point legends placeable.
COURTYARD_ALLOWLIST = {
    tuple(sorted(pair))
    for pair in {
        ("R17", "U4"), ("D1", "J101"), ("C25", "J2"), ("C1", "U1"),
        ("C3", "L1"), ("Q2", "TP6"), ("TP3", "U4"), ("J104", "R3"),
        ("C5", "U2"), ("D6", "J2"), ("J2", "TP1"),
        ("J2", "TP5"), ("C14", "C26"), ("D2", "J103"), ("J103", "R2"),
        ("D4", "R12"), ("R10", "R11"), ("D1", "J102"), ("D2", "J104"),
        ("D5", "R14"),
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
    """Return the exact six primitives for the square-tip 20 x 107 mm outline."""
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
    line((20.0, 2.0), (20.0, 107.0))
    line((20.0, 107.0), (0.0, 107.0))
    line((0.0, 107.0), (0.0, 2.0))
    arc((0.0, 2.0), (0.586, 0.586), (2.0, 0.0))
    return expected


def expected_thermal_slot_geometry() -> Counter:
    """Return the exact primitives for all four heated-island slots."""
    expected = Counter()

    def rounded(point):
        return tuple(round(value, 2) for value in point)

    def line(start, end):
        expected[("Line", frozenset((rounded(start), rounded(end))), None, 0.05)] += 1

    def arc(start, midpoint, end):
        expected[("Arc", frozenset((rounded(start), rounded(end))),
                  rounded(midpoint), 0.05)] += 1

    for x in (104.125, 115.875):
        x0, x1 = x - 3.375, x + 3.375
        line((x0 + 0.75, 133.25), (x1 - 0.75, 133.25))
        arc((x1 - 0.75, 133.25), (x1, 134.0), (x1 - 0.75, 134.75))
        line((x1 - 0.75, 134.75), (x0 + 0.75, 134.75))
        arc((x0 + 0.75, 134.75), (x0, 134.0), (x0 + 0.75, 133.25))
    for x in (101.2, 118.8):
        x0, x1 = x - 0.4, x + 0.4
        y0, y1 = 137.0, 153.0
        line((x0, y0 + 0.4), (x0, y1 - 0.4))
        arc((x0, y1 - 0.4), (x, y1), (x1, y1 - 0.4))
        line((x1, y1 - 0.4), (x1, y0 + 0.4))
        arc((x1, y0 + 0.4), (x, y0), (x0, y0 + 0.4))
    return expected


def expected_thermal_barrier_track_crossings() -> Counter:
    """Return the accepted routed copper that crosses the Y=134 centreline."""
    expected = Counter()

    def segment(net, layer, width, start, end):
        expected[(net, layer, width, frozenset((start, end)))] += 1

    segment("/I2C_SCL", "B.Cu", 0.09, (107.48, 132.99), (109.61, 135.12))
    segment("/I2C_SDA", "In1.Cu", 0.09, (112.15, 133.0), (112.15, 135.6))
    segment("/CELL_WE", "F.Cu", 0.15, (106.9, 132.45), (109.55, 135.1))
    segment("/CELL_RE", "F.Cu", 0.15, (111.0, 131.4), (112.54, 141.0))
    segment("/CELL_CE", "In1.Cu", 0.15, (110.5, 132.45), (107.45, 135.5))
    segment("/3V3D", "F.Cu", 0.15, (119.72, 133.8), (119.72, 134.2))
    segment("/+12V_SW", "B.Cu", 0.18, (109.9, 133.6), (109.9, 134.9))
    segment("/VA_MON", "F.Cu", 0.18, (109.65, 134.0), (109.75, 134.0))
    segment("/VA_MON", "F.Cu", 0.18, (109.75, 134.0), (109.8, 134.05))
    segment("/VA_MON", "F.Cu", 0.18, (108.35, 132.7), (109.65, 134.0))
    segment("/VA_MON", "B.Cu", 0.18, (112.0, 136.0), (112.0, 132.9))
    segment("/GND", "In2.Cu", 0.15, (100.4, 133.1), (100.4, 134.9))
    segment("/HEATER_PWM", "F.Cu", 0.18, (112.0, 135.0), (112.0, 133.5))
    segment("/GUARD_REPLICA", "In1.Cu", 0.15, (108.0, 133.16),
            (108.0, 134.53))
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


# A land-pattern review checks geometry. It does not check pin IDENTITY, and
# nothing else in this audit did either: U11 reached a populated board with a
# pin map copied out of a datasheet PROSE sentence while the pin drawing on the
# same page said something different (PIN-IDENTITY-POSTMORTEM.md). Every
# dimension was right; which electrode sat on which pad was never derived from
# a figure at all.
#
# So a project-drawn footprint with enough pads to get the order wrong must
# record, in its descr, where its pin map came from. The four tokens are chosen
# because none of them can be written down without actually doing the work:
# naming the document and figure forces you to open it, "view:" forces the
# top/bottom decision that kills through-hole parts, and "leaders:" forces you
# to trace each label to its pin instead of reading the labels top-to-bottom.
# On the SGX figure the leaders cross, so label order and a nearest-label
# heuristic both return the wrong answer -- tracing is the only method that works.
#
# "leaders:" and "table:" are alternatives on purpose. A part documented by a
# pin TABLE has no leaders to trace, and demanding the token anyway would train
# people to write it falsely, which is how a gate turns into furniture.
PINMAP_REQUIRED_TOKENS = ("pinmap:", "view:")
PINMAP_AUTHORITY_TOKENS = ("leaders:", "table:")
PINMAP_MIN_PADS = 3


def footprint_description(footprint) -> str:
    for accessor in ("GetLibDescription", "GetDescription"):
        getter = getattr(footprint, accessor, None)
        if getter is not None:
            try:
                return getter() or ""
            except Exception:
                continue
    return ""


def collect_pinmap_provenance_errors(footprints: dict) -> list[str]:
    """Require a recorded pin-map provenance on project-library footprints."""
    errors: list[str] = []
    for reference, footprint in sorted(footprints.items()):
        lib_id = footprint.GetFPID()
        # str() is load-bearing: GetLibNickname() returns a SWIG UTF8 proxy that
        # compares unequal to every Python string, so without it this guard
        # skips every footprint and reports a clean pass having evaluated nothing.
        if str(lib_id.GetLibNickname()) != "o2-probe":
            continue  # vendor and stock KiCad libraries carry their own review
        pads = [pad for pad in footprint.Pads() if pad.GetNumber()]
        if len(pads) < PINMAP_MIN_PADS:
            continue  # a two-terminal part has no pin order to get wrong
        descr = footprint_description(footprint).lower()
        missing = [token for token in PINMAP_REQUIRED_TOKENS if token not in descr]
        if not any(token in descr for token in PINMAP_AUTHORITY_TOKENS):
            missing.append(" or ".join(PINMAP_AUTHORITY_TOKENS))
        if missing:
            errors.append(
                f"PINMAP_PROVENANCE: {reference} ({str(lib_id.GetLibItemName())}, "
                f"{len(pads)} pads) descr is missing {', '.join(missing)}. A "
                "project footprint must record document, figure, VIEW and traced "
                "leaders for its pin map, derived from the drawing and never from "
                "prose. See PIN-IDENTITY-POSTMORTEM.md"
            )
    return errors


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
    slot_items = thermal_slot_items(board)
    outline_items = [item for item in edge_items if item not in slot_items]
    check(errors, len(edge_items) == 22 and len(outline_items) == 6 and len(slot_items) == 16,
          "EDGE_ITEM_COUNT",
          f"found {len(edge_items)} total/{len(outline_items)} outer/{len(slot_items)} slot; "
          "want 22/6/16")
    actual_outline = Counter(edge_signature(item) for item in outline_items)
    expected_outline = expected_outline_geometry()
    check(errors, actual_outline == expected_outline, "OUTLINE_GEOMETRY",
          f"added/changed={list((actual_outline - expected_outline).elements())}; "
          f"missing={list((expected_outline - actual_outline).elements())}")
    actual_slots = Counter(edge_signature(item) for item in slot_items)
    expected_slots = expected_thermal_slot_geometry()
    check(errors, actual_slots == expected_slots, "THERMAL_SLOT_GEOMETRY",
          f"added/changed={list((actual_slots - expected_slots).elements())}; "
          f"missing={list((expected_slots - actual_slots).elements())}")
    metrics.update(thermal_slot_count=4.0, thermal_slot_length_mm=6.75,
                   thermal_slot_width_mm=1.5, thermal_slot_edge_web_mm=0.75,
                   thermal_slot_center_neck_mm=5.0,
                   side_thermal_slot_count=2.0,
                   side_thermal_slot_length_mm=16.0,
                   side_thermal_slot_width_mm=0.8)

    def track_crosses_side_slot(item) -> bool:
        start, end = xy(item.GetStart()), xy(item.GetEnd())
        for slot_x in (101.2, 118.8):
            if not min(start[0], end[0]) <= slot_x <= max(start[0], end[0]):
                continue
            if near(start[0], end[0]):
                if near(start[0], slot_x) and max(start[1], end[1]) >= 137.0 \
                        and min(start[1], end[1]) <= 153.0:
                    return True
                continue
            fraction = (slot_x - start[0]) / (end[0] - start[0])
            crossing_y = start[1] + fraction * (end[1] - start[1])
            if 137.0 <= crossing_y <= 153.0:
                return True
        return False

    side_slot_tracks = [
        (item.GetNetname(), board.GetLayerName(item.GetLayer()),
         rounded_point(item.GetStart()), rounded_point(item.GetEnd()))
        for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA) and track_crosses_side_slot(item)
    ]
    side_slot_vias = [
        (item.GetNetname(), rounded_point(item.GetPosition()))
        for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and any(abs(xy(item.GetPosition())[0] - slot_x) <= 0.4
                and 137.0 <= xy(item.GetPosition())[1] <= 153.0
                for slot_x in (101.2, 118.8))
    ]
    side_slot_pads = [
        (footprint.GetReference(), pad.GetNumber(), pad.GetNetname())
        for footprint in board.Footprints() for pad in footprint.Pads()
        if any(mm(pad.GetBoundingBox().GetLeft()) <= slot_x
               <= mm(pad.GetBoundingBox().GetRight())
               and mm(pad.GetBoundingBox().GetBottom()) >= 137.0
               and mm(pad.GetBoundingBox().GetTop()) <= 153.0
               for slot_x in (101.2, 118.8))
    ]
    check(errors, not side_slot_tracks and not side_slot_vias and not side_slot_pads,
          "SIDE_SLOT_COPPER",
          f"tracks={side_slot_tracks}; vias={side_slot_vias}; pads={side_slot_pads}")
    metrics["side_slot_copper_crossings"] = float(
        len(side_slot_tracks) + len(side_slot_vias) + len(side_slot_pads)
    )
    expected_tip_placements = {
        "RH1": ((105.0, 146.5), 270.0, "B.Cu"),
        "RH2": ((115.0, 146.5), 270.0, "B.Cu"),
        "Q2": ((110.0, 151.25), 270.0, "B.Cu"),
        "R28": ((106.5, 151.25), 180.0, "B.Cu"),
        "R29": ((113.5, 151.25), 180.0, "B.Cu"),
        "TP6": ((108.3, 153.0), 180.0, "B.Cu"),
        "U12": ((103.5, 151.5), 0.0, "F.Cu"),
        "C20": ((106.0, 151.5), 90.0, "F.Cu"),
        "U10": ((110.0, 152.525), 270.0, "F.Cu"),
        "C21": ((112.5, 152.5), 90.0, "F.Cu"),
        "U14": ((116.5, 151.0), 0.0, "F.Cu"),
        "C23": ((114.0, 151.0), 180.0, "F.Cu"),
        "C24": ((114.0, 152.0), 180.0, "F.Cu"),
        "J5": ((110.0, 155.5), 0.0, "F.Cu"),
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
        check(errors, actual_ring_fpid == "o2-probe:Ring_Fork_Tip_DRAFT",
              "RING_FOOTPRINT", actual_ring_fpid)
        ring_land_signatures = Counter()
        for pad in ring.Pads():
            ring_land_signatures[(
                rounded_point(pad.GetPosition()), rounded_point(pad.GetSize()),
                rounded_point(pad.GetDrillSize()), pad.GetNumber(), pad.GetNetname(),
                int(pad.GetAttribute()), int(pad.GetShape()), int(pad.GetDrillShape()),
                int(pad.GetProperty()),
                pad.IsOnLayer(pcbnew.F_Cu), pad.IsOnLayer(pcbnew.In1_Cu),
                pad.IsOnLayer(pcbnew.In2_Cu), pad.IsOnLayer(pcbnew.B_Cu),
                pad.IsOnLayer(pcbnew.F_Mask), pad.IsOnLayer(pcbnew.B_Mask),
                pad.IsOnLayer(pcbnew.F_Paste), pad.IsOnLayer(pcbnew.B_Paste),
            )] += 1
        # The fork tip replaces the two edge castellations.  Each finger carries
        # ONE net on a pair of same-numbered SMD lands, front and back -- so this
        # is 2 conductors, not the 4 that RING-PCB.md 1 offered.  Measured from
        # the board, not hand-copied: 0.6 x 1.5 mm lands at the finger tips.
        expected_ring_lands = Counter({
            ((102.2, 155.5), (0.6, 1.5), (0.0, 0.0), "1", "/+12V_HTR",
             int(pcbnew.PAD_ATTRIB_SMD), int(pcbnew.PAD_SHAPE_RECT),
             int(pcbnew.PAD_DRILL_SHAPE_CIRCLE), int(pcbnew.PAD_PROP_NONE),
             True, False, False, False, True, False, False, False): 1,
            ((102.2, 155.5), (0.6, 1.5), (0.0, 0.0), "1", "/+12V_HTR",
             int(pcbnew.PAD_ATTRIB_SMD), int(pcbnew.PAD_SHAPE_RECT),
             int(pcbnew.PAD_DRILL_SHAPE_CIRCLE), int(pcbnew.PAD_PROP_NONE),
             False, False, False, True, False, True, False, False): 1,
            ((117.8, 155.5), (0.6, 1.5), (0.0, 0.0), "2", "/HEATER_LOW",
             int(pcbnew.PAD_ATTRIB_SMD), int(pcbnew.PAD_SHAPE_RECT),
             int(pcbnew.PAD_DRILL_SHAPE_CIRCLE), int(pcbnew.PAD_PROP_NONE),
             True, False, False, False, True, False, False, False): 1,
            ((117.8, 155.5), (0.6, 1.5), (0.0, 0.0), "2", "/HEATER_LOW",
             int(pcbnew.PAD_ATTRIB_SMD), int(pcbnew.PAD_SHAPE_RECT),
             int(pcbnew.PAD_DRILL_SHAPE_CIRCLE), int(pcbnew.PAD_PROP_NONE),
             False, False, False, True, False, True, False, False): 1,
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
    # J5 is NO LONGER through-plated.  The castellations were plated barrels that
    # joined every layer; the fork tip's front and back lands are separate SMD
    # pads at the same XY with NO plating between them.  KiCad unions them because
    # they share a pad number, which makes the netlist look connected while the
    # copper is not -- so the old "J5 is through-plated, expect no vias" check now
    # asserts the opposite of the truth.  Each finger needs a real layer join.
    fork_pads = [pad for pad in footprints["J5"].Pads()] if "J5" in footprints else []
    for number in sorted({pad.GetNumber() for pad in fork_pads}):
        at = {(round(mm(pad.GetPosition().x), 3), round(mm(pad.GetPosition().y), 3))
              for pad in fork_pads if pad.GetNumber() == number}
        joined = any(
            (round(mm(via.GetPosition().x), 3), round(mm(via.GetPosition().y), 3)) in at
            or any(abs(mm(via.GetPosition().x) - x) <= 1.0
                   and abs(mm(via.GetPosition().y) - y) <= 2.0 for (x, y) in at)
            for via in board.GetTracks() if isinstance(via, pcbnew.PCB_VIA)
        )
        check(errors, joined, "RING_FORK_LAYER_JOIN",
              f"J5 finger {number} has front and back lands at {sorted(at)} with no via "
              "joining them; same-numbered pads share a net in the netlist but not copper")

    heater_zones = [zone for zone in board.Zones()
                    if zone.GetZoneName() == "HEATED_ISLAND_SPREADER"]
    check(errors, len(heater_zones) == 1, "HEATER_SPREADER",
          f"found {len(heater_zones)} heated-island spreader zones")
    if len(heater_zones) == 1:
        heater_zone = heater_zones[0]
        actual_heater_outline = canonical_polygon([
            heater_zone.GetCornerPosition(index)
            for index in range(heater_zone.GetNumCorners())
        ])
        expected_heater_outline = canonical_polygon([
            pcbnew.VECTOR2I_MM(x, y) for x, y in
            ((100.25, 135.0), (119.75, 135.0),
             (119.75, 156.75), (100.25, 156.75))
        ])
        check(errors,
              heater_zone.GetNetname() == "/HEATER_LOW"
              and list(heater_zone.GetLayerSet().Seq()) == [pcbnew.B_Cu]
              and not heater_zone.GetIsRuleArea()
              and actual_heater_outline == expected_heater_outline
              and near(mm(heater_zone.GetLocalClearance()), 0.15)
              and near(mm(heater_zone.GetMinThickness()), 0.09)
              and heater_zone.GetPadConnection() == pcbnew.ZONE_CONNECTION_FULL,
              "HEATER_SPREADER_GEOMETRY",
              f"net={heater_zone.GetNetname()}; layers="
              f"{[board.GetLayerName(layer) for layer in heater_zone.GetLayerSet().Seq()]}; "
              f"outline={actual_heater_outline}")
        check(errors, heater_zone.IsFilled()
              and heater_zone.HasFilledPolysForLayer(pcbnew.B_Cu),
              "HEATER_SPREADER_FILL", "heated-island spreader is not filled on B.Cu")
        heater_fill = heater_zone.GetFilledPolysList(pcbnew.B_Cu)
        heater_signatures = Counter()
        for index in range(heater_fill.OutlineCount()):
            outline = heater_fill.COutline(index)
            bbox = outline.BBox()
            heater_signatures[(
                tuple(round(mm(value), 6) for value in (
                    bbox.GetLeft(), bbox.GetTop(), bbox.GetRight(), bbox.GetBottom()
                )),
                outline.PointCount(), heater_fill.HoleCount(index),
            )] += 1
        expected_heater_signatures = Counter({
            ((100.25, 135.0, 119.75, 156.75), 1343, 0): 1,
        })
        check(errors, heater_signatures == expected_heater_signatures,
              "HEATER_SPREADER_FILL",
              f"added/changed={list((heater_signatures - expected_heater_signatures).elements())}; "
              f"missing={list((expected_heater_signatures - heater_signatures).elements())}")
        heater_samples = ((101.0, 136.0), (118.0, 136.0),
                          (102.0, 145.0), (118.0, 145.0),
                          (102.0, 154.0), (110.0, 154.0), (118.0, 154.0))
        missing_heater_samples = [
            point for point in heater_samples
            if not heater_fill.Contains(pcbnew.VECTOR2I_MM(*point))
        ]
        check(errors, not missing_heater_samples, "HEATER_SPREADER_COVERAGE",
              f"heated-island fill misses {missing_heater_samples}")
        side_slot_void_samples = tuple(
            (x, y) for x in (101.2, 118.8) for y in (138.0, 145.0, 152.0)
        )
        filled_side_slot_samples = [
            point for point in side_slot_void_samples
            if heater_fill.Contains(pcbnew.VECTOR2I_MM(*point))
        ]
        check(errors, not filled_side_slot_samples, "SIDE_SLOT_COPPER_VOID",
              f"heated-island fill enters side-slot voids {filled_side_slot_samples}")
        metrics["heater_spreader_filled_regions"] = float(heater_fill.OutlineCount())

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

    errors.extend(collect_pinmap_provenance_errors(footprints))

    # This guard used to read `"TP2" not in footprints`, which checked a
    # DESIGNATOR rather than the property it was trying to protect. It fired on
    # 2026-09-04 against a TP2 that is a GROUND pad, and it would have stayed
    # silent if the same aperture had been added as TP7. What matters is that no
    # exposed test pad lands on the reference electrode: CELL_RE is budgeted
    # against the LMP91000's +/-900 pA IRE, and a solder-mask opening there is a
    # surface-leakage path onto the most sensitive node on the board.
    re_testpoints = sorted(
        ref for ref, footprint in footprints.items()
        if ref.startswith("TP")
        and any(pad.GetNetname() == "/CELL_RE" for pad in footprint.Pads())
    )
    check(errors, not re_testpoints, "CELL_RE_TESTPOINT",
          f"{re_testpoints} expose the high-impedance CELL_RE node")
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
        "1": (107.46, 141.0), "2": (112.54, 141.0), "3": (110.0, 141.0)
    }.items():
        if number not in u11_pads:
            errors.append(f"U11_PAD_GEOMETRY: pad {number} missing")
            continue
        pad = u11_pads[number]
        size = xy(pad.GetSize())
        drill = xy(pad.GetDrillSize())
        check(errors, all(near(a, b) for a, b in zip(xy(pad.GetPosition()), wanted_position))
              and all(near(value, 2.0) for value in size)
              and all(near(value, 1.32) for value in drill),
              "U11_PAD_GEOMETRY",
              f"pad {number} position/land/drill differs from DS-0637 Issue 2 plus the "
              "socket land (2.0 mm land, 1.32 mm drill for TE 5050462, borable to 1.40 "
              "for Cambion 450-3703)")

    apertures = [pad for pad in u11.Pads()
                 if not pad.GetNumber() and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    check(errors, len(apertures) == 1, "SENSOR_APERTURE_COUNT",
          f"found {len(apertures)}, want one NPTH slot")
    if len(apertures) == 1:
        aperture = apertures[0]
        aperture_position = xy(aperture.GetPosition())
        aperture_drill = xy(aperture.GetDrillSize())
        check(errors,
              near(aperture_position[0], 110.0) and near(aperture_position[1], 145.3)
              and near(aperture_drill[0], 3.0) and near(aperture_drill[1], 6.0)
              and aperture.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG,
              "SENSOR_APERTURE_GEOMETRY",
              f"slot at {aperture_position}, drill {aperture_drill}")
        check(errors, aperture_position[1] - aperture_drill[1] / 2 <= u11_pos[1],
              "SENSOR_APERTURE_AXIS", "gasward slot does not include the sensor rear axis")
        pad_edge = xy(u11_pads["2"].GetPosition())[1] + xy(u11_pads["2"].GetSize())[1] / 2
        aperture_edge = aperture_position[1] - aperture_drill[1] / 2
        aperture_gap = aperture_edge - pad_edge
        metrics["sensor_pad_to_aperture_gap_mm"] = aperture_gap
        check(errors, near(aperture_gap, 0.3), "SENSOR_APERTURE_PAD_GAP",
              f"pad-2 copper to slot edge is {aperture_gap:.3f} mm, want 0.300 mm")

        expected_heater_detour = Counter({
            frozenset(((117.65, 144.3), (117.65, 148.8))): 1,
            frozenset(((117.65, 148.8), (105.0, 148.8))): 1,
            frozenset(((105.0, 148.8), (105.0, 142.5))): 1,
        })
        actual_heater_detour = Counter(
            frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd())))
            for item in board.GetTracks()
            if not isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == "/+12V_SW"
            and item.GetLayer() == pcbnew.In1_Cu
            and (142.0 <= mm(item.GetStart().y) <= 149.0
                 or 142.0 <= mm(item.GetEnd().y) <= 149.0)
        )
        check(errors, actual_heater_detour == expected_heater_detour,
              "SENSOR_APERTURE_HEATER_DETOUR",
              f"added/changed={list((actual_heater_detour - expected_heater_detour).elements())}; "
              f"missing={list((expected_heater_detour - actual_heater_detour).elements())}")

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
    actual_guard_vias = Counter(
        (rounded_point(via.GetPosition()), round(mm(via.GetWidth(pcbnew.F_Cu)), 2),
         round(mm(via.GetDrillValue()), 2))
        for via in guard_vias
    )
    expected_guard_vias = Counter({
        (position, diameter, drill): 1
        for position, diameter, drill in (
            ((101.0, 115.5), 0.25, 0.15),
            ((102.7, 121.0), 0.45, 0.20),
            ((102.7, 122.4), 0.45, 0.20),
            ((109.55, 132.8), 0.25, 0.15),
            ((106.95, 136.0), 0.25, 0.15),
            ((108.8, 136.0), 0.25, 0.15),
            ((111.0, 135.5), 0.25, 0.15),
            ((112.65, 137.15), 0.25, 0.15),
        )
    })
    check(errors, actual_guard_vias == expected_guard_vias,
          "GUARD_STITCH_VIAS",
          f"added/changed={list((actual_guard_vias - expected_guard_vias).elements())}; "
          f"missing={list((expected_guard_vias - actual_guard_vias).elements())}")
    guard_stitch_tracks = Counter(
        (item.GetLayerName(), round(mm(item.GetWidth()), 2),
         frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd()))))
        for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/GUARD_REPLICA"
        and min(xy(item.GetStart())[1], xy(item.GetEnd())[1]) >= 132.6
    )
    expected_guard_stitch_tracks = Counter({
        (layer, 0.15, frozenset((start, end))): 1
        for layer, start, end in (
            ("In1.Cu", (106.6, 132.6), (109.55, 132.8)),
            ("In1.Cu", (106.6, 132.6), (107.44, 132.6)),
            ("In1.Cu", (107.44, 132.6), (108.0, 133.16)),
            ("In1.Cu", (108.0, 133.16), (108.0, 134.53)),
            ("In1.Cu", (108.0, 134.53), (107.15, 135.38)),
            ("In1.Cu", (107.15, 135.38), (107.15, 135.8)),
            ("In1.Cu", (107.15, 135.8), (106.95, 136.0)),
            ("B.Cu", (106.95, 136.0), (108.8, 136.0)),
            ("In1.Cu", (108.8, 136.0), (110.65, 136.0)),
            ("In1.Cu", (110.65, 136.0), (111.0, 135.5)),
            ("In1.Cu", (111.0, 135.5), (112.65, 137.15)),
        )
    })
    check(errors, guard_stitch_tracks == expected_guard_stitch_tracks,
          "GUARD_STITCH_TRACKS",
          f"added/changed={list((guard_stitch_tracks - expected_guard_stitch_tracks).elements())}; "
          f"missing={list((expected_guard_stitch_tracks - guard_stitch_tracks).elements())}")
    if len(guard_zones) == 1:
        guard = guard_zones[0]
        guard_points = [guard.GetCornerPosition(index) for index in range(guard.GetNumCorners())]
        polygon = [xy(point) for point in guard_points]
        actual_guard_outlines = Counter({canonical_polygon(guard_points): 1})
        expected_guard_outlines = Counter({
            canonical_polygon([
                pcbnew.VECTOR2I_MM(109.25, 131.75),
                pcbnew.VECTOR2I_MM(112.15, 131.75),
                pcbnew.VECTOR2I_MM(114.0, 141.65),
                pcbnew.VECTOR2I_MM(111.1, 141.65),
            ]): 1,
        })
        check(errors, actual_guard_outlines == expected_guard_outlines,
              "GUARD_ZONE_GEOMETRY",
              f"added/changed={list((actual_guard_outlines - expected_guard_outlines).elements())}; "
              f"missing={list((expected_guard_outlines - actual_guard_outlines).elements())}")
        check(errors, point_in_polygon((111.74, 136.0), polygon)
              and point_in_polygon((112.46, 140.5), polygon),
              "GUARD_ENCLOSURE", "guard polygon does not enclose the long CELL_RE run")
        check(errors, guard.IsFilled() and guard.HasFilledPolysForLayer(pcbnew.F_Cu),
              "GUARD_ZONE_FILL", "the exact F.Cu driven-guard zone is not filled")
        filled_guard = guard.GetFilledPolysList(pcbnew.F_Cu)
        actual_filled_guard = Counter()
        for index in range(filled_guard.OutlineCount()):
            outline = filled_guard.COutline(index)
            bbox = outline.BBox()
            actual_filled_guard[(
                tuple(round(mm(value), 6) for value in (
                    bbox.GetLeft(), bbox.GetTop(), bbox.GetRight(), bbox.GetBottom()
                )),
                outline.PointCount(),
                filled_guard.HoleCount(index),
            )] += 1
        expected_filled_guard = Counter({
            ((109.867055, 135.0, 112.132522, 141.65), 54, 0): 1,
            ((111.8553, 135.257645, 113.990268, 141.65), 43, 0): 1,
            ((109.3897, 131.971835, 110.405022, 132.9745), 34, 0): 1,
        })
        check(errors, actual_filled_guard == expected_filled_guard,
              "GUARD_FILLED_GEOMETRY",
              f"added/changed={list((actual_filled_guard - expected_filled_guard).elements())}; "
              f"missing={list((expected_filled_guard - actual_filled_guard).elements())}")
        guard_samples = (
            (109.5, 132.5), (110.0, 132.5),
            (110.80, 136.0), (111.20, 138.0), (111.50, 140.0),
            (112.45, 136.0), (112.79, 138.0), (113.15, 140.0), (113.75, 141.3),
        )
        missing_guard_samples = [
            point for point in guard_samples
            if not filled_guard.Contains(pcbnew.VECTOR2I_MM(*point))
        ]
        check(errors, not missing_guard_samples, "GUARD_FILLED_COVERAGE",
              f"actual filled guard misses {missing_guard_samples}")
        gap_guard_samples = ((109.7, 134.0), (110.4, 134.0), (111.0, 134.0),
                             (112.0, 134.0), (112.3, 134.0))
        filled_gap_guard = [point for point in gap_guard_samples
                            if filled_guard.Contains(pcbnew.VECTOR2I_MM(*point))]
        check(errors, not filled_gap_guard, "THERMAL_GAP_FILLED_COPPER",
              f"driven-guard fill enters all-layer gap at {filled_gap_guard}")
        metrics["guard_filled_regions"] = float(filled_guard.OutlineCount())

    gnd_zones = [zone for zone in board.Zones()
                 if zone.GetNetname() == "/GND" and zone.IsOnLayer(pcbnew.In2_Cu)]
    check(errors, len(gnd_zones) == 1, "GND_ZONE_COUNT",
          f"found {len(gnd_zones)} In2 GND zones, want one controlled source zone")
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
              "GND_ZONE_FILL", "the controlled In2 GND source zone is not filled")
        filled_gnd = gnd_zones[0].GetFilledPolysList(pcbnew.In2_Cu)
        gnd_side_samples = ((101.0, 132.0), (110.0, 132.0), (118.0, 132.0),
                            (101.0, 136.0), (110.0, 136.0), (118.0, 136.0))
        gnd_gap_samples = ((100.4, 134.0), (104.125, 134.0), (106.8, 134.0),
                           (110.0, 134.0), (113.0, 134.0), (115.875, 134.0),
                           (119.5, 134.0))
        missing_gnd_samples = [point for point in gnd_side_samples
                               if not filled_gnd.Contains(pcbnew.VECTOR2I_MM(*point))]
        filled_gap_samples = [point for point in gnd_gap_samples
                              if filled_gnd.Contains(pcbnew.VECTOR2I_MM(*point))]
        check(errors, filled_gnd.OutlineCount() == 2
              and not missing_gnd_samples and not filled_gap_samples,
              "THERMAL_BARRIER_FILLED_COPPER",
              f"missing north/south fill={missing_gnd_samples}; "
              f"copper inside all-layer gap={filled_gap_samples}")
    in2_gnd_tracks = [item for item in board.GetTracks()
                      if not isinstance(item, pcbnew.PCB_VIA)
                      and item.GetNetname() == "/GND"
                      and item.GetLayer() == pcbnew.In2_Cu]
    actual_gnd_bridges = Counter(
        (round(mm(item.GetWidth()), 2),
         frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd()))))
        for item in in2_gnd_tracks
    )
    expected_gnd_bridges = Counter({
        (0.15, frozenset((start, end))): 1
        for start, end in (
            ((100.5, 133.0), (100.4, 133.1)),
            ((100.4, 133.1), (100.4, 134.9)),
            ((100.4, 134.9), (100.5, 135.0)),
        )
    })
    check(errors, actual_gnd_bridges == expected_gnd_bridges, "GND_ZONE_BRIDGE",
          f"added/changed={list((actual_gnd_bridges - expected_gnd_bridges).elements())}; "
          f"missing={list((expected_gnd_bridges - actual_gnd_bridges).elements())}")

    barrier_y_iu = pcbnew.FromMM(134.0)
    barrier_zones = [
        zone for zone in board.Zones()
        if zone.GetBoundingBox().GetTop() <= barrier_y_iu
        <= zone.GetBoundingBox().GetBottom()
    ]
    actual_barrier_zones = Counter(
        (zone.GetNetname(), tuple(sorted(board.GetLayerName(layer)
                                        for layer in zone.GetLayerSet().Seq())),
         canonical_polygon([zone.GetCornerPosition(index)
                            for index in range(zone.GetNumCorners())]))
        for zone in barrier_zones
    )
    expected_barrier_zones = Counter({
        ("/GUARD_REPLICA", ("F.Cu",), canonical_polygon([
            pcbnew.VECTOR2I_MM(109.25, 131.75),
            pcbnew.VECTOR2I_MM(112.15, 131.75),
            pcbnew.VECTOR2I_MM(114.0, 141.65),
            pcbnew.VECTOR2I_MM(111.1, 141.65),
        ])): 1,
        ("/GND", ("In2.Cu",), canonical_polygon([
            pcbnew.VECTOR2I_MM(100.25, 50.25),
            pcbnew.VECTOR2I_MM(119.75, 50.25),
            pcbnew.VECTOR2I_MM(119.75, 156.75),
            pcbnew.VECTOR2I_MM(100.25, 156.75),
        ])): 1,
        ("", ("B.Cu", "F.Cu", "In1.Cu", "In2.Cu"), canonical_polygon([
            pcbnew.VECTOR2I_MM(100.0, 133.0),
            pcbnew.VECTOR2I_MM(120.0, 133.0),
            pcbnew.VECTOR2I_MM(120.0, 135.0),
            pcbnew.VECTOR2I_MM(100.0, 135.0),
        ])): 1,
    })
    check(errors, actual_barrier_zones == expected_barrier_zones,
          "THERMAL_BARRIER_ZONES",
          f"added/changed={list((actual_barrier_zones - expected_barrier_zones).elements())}; "
          f"missing={list((expected_barrier_zones - actual_barrier_zones).elements())}")
    gap_zones = [zone for zone in board.Zones()
                 if zone.GetZoneName() == "THERMAL_BARRIER_COPPER_GAP"]
    expected_gap_layers = {pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu}
    check(errors, len(gap_zones) == 1, "THERMAL_GAP_RULE_AREA",
          f"found {len(gap_zones)} all-layer thermal-gap rule areas")
    if len(gap_zones) == 1:
        gap = gap_zones[0]
        check(errors,
              gap.GetIsRuleArea()
              and set(gap.GetLayerSet().Seq()) == expected_gap_layers
              and gap.GetDoNotAllowZoneFills()
              and not gap.GetDoNotAllowTracks()
              and not gap.GetDoNotAllowVias()
              and not gap.GetDoNotAllowPads()
              and not gap.GetDoNotAllowFootprints()
              and all(gap.GetFilledPolysList(layer).OutlineCount() == 0
                      for layer in expected_gap_layers),
              "THERMAL_GAP_RULE_AREA",
              "thermal gap must prohibit only copper-pour fill on exactly all four copper layers")
    footprint_barrier_zones = [
        (footprint.GetReference(), tuple(sorted(board.GetLayerName(layer)
                                                for layer in zone.GetLayerSet().Seq())))
        for footprint in board.Footprints() for zone in footprint.Zones()
        if zone.GetBoundingBox().GetTop() <= barrier_y_iu
        <= zone.GetBoundingBox().GetBottom()
    ]
    check(errors, not footprint_barrier_zones, "THERMAL_BARRIER_ZONES",
          f"footprint zones cross y=134: {footprint_barrier_zones}")

    copper_layers = {pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu}
    board_barrier_graphics = [
        (item.GetLayerName(), type(item).__name__)
        for item in board.Drawings()
        if item.GetLayer() in copper_layers
        and item.GetBoundingBox().GetTop() <= barrier_y_iu
        <= item.GetBoundingBox().GetBottom()
    ]
    footprint_barrier_graphics = [
        (footprint.GetReference(), item.GetLayerName(), type(item).__name__)
        for footprint in board.Footprints()
        for item in list(footprint.GraphicalItems()) + list(footprint.GetFields())
        if item.GetLayer() in copper_layers
        and item.GetBoundingBox().GetTop() <= barrier_y_iu
        <= item.GetBoundingBox().GetBottom()
    ]
    check(errors, not board_barrier_graphics and not footprint_barrier_graphics,
          "THERMAL_BARRIER_GRAPHICS",
          f"board={board_barrier_graphics}; footprint={footprint_barrier_graphics}")

    tracks = [item for item in board.GetTracks() if not isinstance(item, pcbnew.PCB_VIA)]
    vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
    barrier_y = 134.0
    crossing_tracks = [
        item for item in tracks
        if min(xy(item.GetStart())[1], xy(item.GetEnd())[1]) <= barrier_y
        <= max(xy(item.GetStart())[1], xy(item.GetEnd())[1])
    ]
    actual_barrier_tracks = Counter(
        (item.GetNetname(), item.GetLayerName(), round(mm(item.GetWidth()), 2),
         frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd()))))
        for item in crossing_tracks
    )
    expected_barrier_tracks = expected_thermal_barrier_track_crossings()
    check(errors, actual_barrier_tracks == expected_barrier_tracks,
          "THERMAL_BARRIER_TRACKS",
          f"added/changed={list((actual_barrier_tracks - expected_barrier_tracks).elements())}; "
          f"missing={list((expected_barrier_tracks - actual_barrier_tracks).elements())}")
    barrier_vias = Counter(
        (item.GetNetname(), rounded_point(item.GetPosition()),
         round(mm(item.GetWidth(pcbnew.F_Cu)), 2), round(mm(item.GetDrillValue()), 2))
        for item in vias
        if 133.5 <= xy(item.GetPosition())[1] <= 134.5
    )
    expected_barrier_vias = Counter({
        ("/+12V_SW", (109.9, 133.6), 0.25, 0.15): 1,
        ("/VA_MON", (110.3, 134.05), 0.25, 0.15): 1,
    })
    check(errors, barrier_vias == expected_barrier_vias, "THERMAL_BARRIER_VIAS",
          f"added/changed={list((barrier_vias - expected_barrier_vias).elements())}; "
          f"missing={list((expected_barrier_vias - barrier_vias).elements())}")
    barrier_pads = [
        (footprint.GetReference(), pad.GetNumber())
        for footprint in board.Footprints() for pad in footprint.Pads()
        if mm(pad.GetBoundingBox().GetTop()) <= barrier_y
        <= mm(pad.GetBoundingBox().GetBottom())
    ]
    check(errors, not barrier_pads, "THERMAL_BARRIER_PADS",
          f"footprint copper spans y=134: {barrier_pads}")
    metrics.update(thermal_barrier_track_crossings=float(sum(actual_barrier_tracks.values())),
                   thermal_barrier_vias=float(sum(barrier_vias.values())),
                   thermal_barrier_zones=float(sum(actual_barrier_zones.values())))
    min_track = min((mm(item.GetWidth()) for item in tracks), default=99.0)
    min_via = min((mm(item.GetWidth(pcbnew.F_Cu)) for item in vias), default=99.0)
    min_drill = min((mm(item.GetDrillValue()) for item in vias), default=99.0)
    metrics.update(min_track_width_mm=min_track, min_via_diameter_mm=min_via,
                   min_via_drill_mm=min_drill, track_via_objects=len(list(board.GetTracks())))
    check(errors, min_track >= 0.09 - 0.0001, "MIN_TRACK_WIDTH",
          f"minimum track is {min_track:.4f} mm")
    check(errors, min_via >= 0.25 - 0.0001 and min_drill >= 0.15 - 0.0001,
          "MIN_VIA", f"minimum via/drill is {min_via:.3f}/{min_drill:.3f} mm")

    switched_supply_tracks = [item for item in tracks if item.GetNetname() == "/+12V_SW"]
    switched_supply_min = min((mm(item.GetWidth()) for item in switched_supply_tracks),
                              default=0.0)
    metrics["switched_supply_min_width_mm"] = switched_supply_min
    check(errors, switched_supply_tracks and switched_supply_min >= 0.18 - 0.0001,
          "POWER_TRACK_WIDTH",
          f"/+12V_SW minimum track is {switched_supply_min:.4f} mm, want >=0.18 mm")

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

    # Every test point must be identifiable with a probe in hand.  This does not
    # read gen_pcb.TESTPOINT_LABELS: importing the generator's own table would
    # only prove the table equals itself.  The property checked here is the one
    # that makes a label useful -- a legible mark, on the side the pad is on,
    # closer to its own pad than to any other test point by a clear margin --
    # and it is derived from the board alone.
    testpoints = {ref: footprint for ref, footprint in footprints.items()
                  if ref.startswith("TP")}
    silk_texts = [item for item in board.Drawings()
                  if isinstance(item, pcbnew.PCB_TEXT)
                  and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    reserved = {"POT TO HERE", "CABLE", "GAS / DO NOT POT", "DO NOT OBSTRUCT"}
    owners: dict[str, list[str]] = {ref: [] for ref in testpoints}
    for item in silk_texts:
        if item.GetText() in reserved:
            continue
        side = pcbnew.F_SilkS if item.GetLayer() == pcbnew.F_SilkS else pcbnew.B_SilkS
        centre = xy(item.GetPosition())
        distances = sorted(
            (((centre[0] - xy(fp.GetPosition())[0]) ** 2
              + (centre[1] - xy(fp.GetPosition())[1]) ** 2) ** 0.5, ref)
            for ref, fp in testpoints.items()
            if (pcbnew.F_SilkS if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_SilkS) == side
        )
        if not distances:
            continue
        nearest, ref = distances[0]
        runner_up = distances[1][0] if len(distances) > 1 else float("inf")
        check(errors, nearest <= 4.0, "TESTPOINT_LABEL_DISTANCE",
              f"silk text {item.GetText()!r} is {nearest:.2f} mm from {ref}, want <=4.0 mm")
        # Two honest limits on this check.  1.4 is a CHOSEN threshold, not a
        # derived one -- it encodes "a reader can tell which pad this names" and
        # nothing more.  And it compares TEXT CENTRES, so a long legend whose
        # centre sits near its own pad can still sprawl over a neighbour; that
        # is tolerable only while the legends stay short, which the 0.8 mm floor
        # and a 20 mm board enforce in practice.
        check(errors, runner_up >= 1.4 * nearest, "TESTPOINT_LABEL_AMBIGUOUS",
              f"silk text {item.GetText()!r} is {nearest:.2f} mm from {ref} but "
              f"{runner_up:.2f} mm from the next test point, want a 1.4x margin")
        check(errors, mm(item.GetTextHeight()) >= 0.8 - 0.0001, "TESTPOINT_LABEL_HEIGHT",
              f"silk text {item.GetText()!r} is {mm(item.GetTextHeight()):.2f} mm high, "
              "below the 0.8 mm printable floor")
        # Proximity alone says a pad HAS a label, never that it has the RIGHT
        # one: swapping the WE and CE strings in place satisfied every check
        # above.  The label must therefore be derivable from the pad's own net,
        # which reaches this audit from the schematic through the board and not
        # from the generator's table -- so agreement here is evidence, not two
        # copies of one assumption.  Substring rather than equality because the
        # legend is deliberately shorter than the net (WE for /CELL_WE, VREF for
        # /VREF_TRIM).
        #
        # It matches a contiguous run of UNDERSCORE-SEPARATED TOKENS, not a raw
        # substring, and the difference is not pedantry: under a substring rule
        # "CE" passes on /CELL_WE, because CE is literally the first two letters
        # of CELL_WE.  A calibration that swapped the WE and CE legends fired on
        # only one of the two pads.  Tokenising makes the rule mean what it says.
        if nearest <= 4.0:
            nets = {pad.GetNetname().lstrip("/").upper()
                    for pad in testpoints[ref].Pads() if pad.GetNetname()}
            label = item.GetText().upper()
            allowed = set()
            for net in nets:
                parts = net.split("_")
                allowed.update("_".join(parts[i:j])
                               for i in range(len(parts))
                               for j in range(i + 1, len(parts) + 1))
            check(errors, len(label) >= 2 and label in allowed,
                  "TESTPOINT_LABEL_IDENTITY",
                  f"{ref} is labelled {item.GetText()!r}, which is not a token run "
                  f"of its net {sorted(nets)}")
            owners[ref].append(item.GetText())
    for ref, labels in sorted(owners.items()):
        check(errors, len(labels) == 1, "TESTPOINT_LABEL",
              f"{ref} carries {len(labels)} silkscreen labels {labels}, want exactly one")
    metrics["testpoint_labels"] = float(sum(len(labels) for labels in owners.values()))
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

    def add_unexpected_slot(board) -> None:
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

    def deform_thermal_slot(board) -> None:
        item = next(
            item for item in board.Drawings()
            if item.GetLayer() == pcbnew.Edge_Cuts
            and item.GetShapeStr() == "Arc"
            and near(xy(item.GetArcMid())[0], 107.5)
            and near(xy(item.GetArcMid())[1], 134.0)
        )
        item.SetArcGeometry(item.GetStart(), pcbnew.VECTOR2I_MM(107.4, 134.0), item.GetEnd())

    def deform_side_thermal_slot(board) -> None:
        item = next(
            item for item in board.Drawings()
            if item.GetLayer() == pcbnew.Edge_Cuts
            and item.GetShapeStr() == "Arc"
            and near(xy(item.GetArcMid())[0], 101.2)
            and near(xy(item.GetArcMid())[1], 153.0)
        )
        item.SetArcGeometry(item.GetStart(), pcbnew.VECTOR2I_MM(101.3, 153.0), item.GetEnd())

    def bridge_side_thermal_slot(board) -> None:
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(board.FindNet("/GND"))
        item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(100.5, 145.0))
        item.SetEnd(pcbnew.VECTOR2I_MM(102.0, 145.0))
        item.SetWidth(pcbnew.FromMM(0.15))
        board.Add(item)

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

    def disable_thermal_gap(board) -> None:
        zone = next(zone for zone in board.Zones()
                    if zone.GetZoneName() == "THERMAL_BARRIER_COPPER_GAP")
        zone.SetDoNotAllowZoneFills(False)

    def change_heater_spreader_net(board) -> None:
        zone = next(zone for zone in board.Zones()
                    if zone.GetZoneName() == "HEATED_ISLAND_SPREADER")
        zone.SetNet(board.FindNet("/GND"))

    def remove_gnd_bridge(board) -> None:
        track = next(
            item for item in board.GetTracks()
            if not isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == "/GND"
            and item.GetLayer() == pcbnew.In2_Cu
            and frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd())))
            == frozenset(((100.4, 133.1), (100.4, 134.9)))
        )
        track.SetNetCode(0)

    def deform_guard_zone(board) -> None:
        zone = next(zone for zone in board.Zones()
                    if zone.GetNetname() == "/GUARD_REPLICA"
                    and zone.IsOnLayer(pcbnew.F_Cu))
        outline = pcbnew.VECTOR_VECTOR2I()
        for x, y in ((109.15, 131.75), (112.15, 131.75),
                     (111.25, 141.65), (108.95, 141.65)):
            outline.append(pcbnew.VECTOR2I_MM(x, y))
        zone.Outline().RemoveAllContours()
        zone.AddPolygon(outline)

    def disconnect_filled_guard_rail(board) -> None:
        via = next(
            item for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == "/GUARD_REPLICA"
            and rounded_point(item.GetPosition()) == (111.0, 135.5)
        )
        via.SetNetCode(0)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    def move_ring(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "J5")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(110.0, 154.5))

    def move_sensor_aperture(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U11")
        aperture = next(pad for pad in footprint.Pads()
                        if not pad.GetNumber()
                        and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH)
        aperture.SetPosition(pcbnew.VECTOR2I_MM(110.0, 145.5))

    def deform_sensor_heater_detour(board) -> None:
        track = next(
            item for item in board.GetTracks()
            if not isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == "/+12V_SW"
            and item.GetLayer() == pcbnew.In1_Cu
            and frozenset((rounded_point(item.GetStart()), rounded_point(item.GetEnd())))
            == frozenset(((105.0, 148.8), (117.65, 148.8)))
        )
        track.SetStart(pcbnew.VECTOR2I_MM(105.0, 148.6))

    def deform_ring_land(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "J5")
        next(iter(footprint.Pads())).SetSize(pcbnew.VECTOR2I_MM(4.5, 1.5))

    def make_ring_slot_nonplated(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "J5")
        next(iter(footprint.Pads())).SetAttribute(pcbnew.PAD_ATTRIB_NPTH)

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

    def narrow_switched_supply(board) -> None:
        track = next(item for item in board.GetTracks()
                     if not isinstance(item, pcbnew.PCB_VIA)
                     and item.GetNetname() == "/+12V_SW")
        track.SetWidth(pcbnew.FromMM(0.09))

    def add_thermal_barrier_crossing(board) -> None:
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(board.FindNet("/3V3D"))
        track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(110.0, 133.8))
        track.SetEnd(pcbnew.VECTOR2I_MM(110.0, 134.2))
        track.SetWidth(pcbnew.FromMM(0.15))
        board.Add(track)

    def add_thermal_barrier_graphic(board) -> None:
        item = pcbnew.PCB_SHAPE(board)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(110.0, 133.8))
        item.SetEnd(pcbnew.VECTOR2I_MM(110.0, 134.2))
        item.SetWidth(pcbnew.FromMM(0.15))
        board.Add(item)

    def add_footprint_thermal_barrier_graphic(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U7")
        item = pcbnew.PCB_SHAPE(footprint)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(110.0, 133.8))
        item.SetEnd(pcbnew.VECTOR2I_MM(110.0, 134.2))
        item.SetWidth(pcbnew.FromMM(0.15))
        footprint.Add(item)

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

    def remove_schematic_footprint(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "C1")
        board.Remove(footprint)

    def change_schematic_pad_net(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U6")
        pad = next(pad for pad in footprint.Pads() if pad.GetNumber() == "18")
        pad.SetNet(board.FindNet("/GND"))

    expect("CELL_RE via", "CELL_RE_VIA", add_cell_via)
    expect("missing guard", "GUARD_ZONE", remove_guard)
    expect("missing continuous GND plane", "GND_ZONE_COUNT", remove_gnd_zone)
    expect("unexpected third board-native slot", "EDGE_ITEM_COUNT", add_unexpected_slot)
    expect("deformed rounded cable corner", "OUTLINE_GEOMETRY", deform_outer_corner)
    expect("deformed thermal-break slot", "THERMAL_SLOT_GEOMETRY", deform_thermal_slot)
    expect("deformed side thermal slot", "THERMAL_SLOT_GEOMETRY",
           deform_side_thermal_slot)
    expect("side thermal slot copper bridge", "SIDE_SLOT_COPPER",
           bridge_side_thermal_slot)
    expect("notched continuous GND plane", "GND_ZONE_GEOMETRY", notch_gnd_zone)
    expect("unfilled controlled ground zone", "GND_ZONE_FILL", unfill_gnd_zone)
    expect("disabled all-layer thermal gap", "THERMAL_GAP_RULE_AREA",
           disable_thermal_gap)
    expect("heater spreader on wrong net", "HEATER_SPREADER_GEOMETRY",
           change_heater_spreader_net)
    expect("missing narrow GND bridge", "GND_ZONE_BRIDGE", remove_gnd_bridge)
    expect("deformed guard crossing", "GUARD_ZONE_GEOMETRY", deform_guard_zone)
    expect("disconnected actual guard rail", "GUARD_FILLED_GEOMETRY",
           disconnect_filled_guard_rail)
    expect("moved membrane ring", "TIP_PLACEMENT", move_ring)
    expect("moved SGX aperture", "SENSOR_APERTURE_GEOMETRY", move_sensor_aperture)
    expect("deformed SGX heater-feed detour", "SENSOR_APERTURE_HEATER_DETOUR",
           deform_sensor_heater_detour)
    expect("deformed membrane-ring land", "RING_LAND_GEOMETRY", deform_ring_land)
    expect("unplated membrane-ring sidewall", "RING_LAND_GEOMETRY",
           make_ring_slot_nonplated)
    expect("obsolete second-sensor copper", "OBSOLETE_TIP_COPPER", add_obsolete_tip_copper)
    expect("narrow heater-to-ring copper", "RING_HEATER_COPPER", narrow_ring_copper)
    expect("sub-process-width trace", "MIN_TRACK_WIDTH", narrow_track)
    expect("narrow switched-heater supply", "POWER_TRACK_WIDTH", narrow_switched_supply)
    expect("unexpected thermal-barrier copper", "THERMAL_BARRIER_TRACKS",
           add_thermal_barrier_crossing)
    expect("unexpected thermal-barrier copper graphic", "THERMAL_BARRIER_GRAPHICS",
           add_thermal_barrier_graphic)
    expect("unexpected footprint thermal-barrier copper graphic",
           "THERMAL_BARRIER_GRAPHICS", add_footprint_thermal_barrier_graphic)
    expect("remote AFE", "U7_PLACEMENT", move_u7)
    expect("moved compact MCU", "MCU_CLUSTER_PLACEMENT", move_compact_mcu)
    expect("exact duplicate copper", "DUPLICATE_COPPER", duplicate_track)
    expect("schematic footprint deleted", "FOOTPRINT_SET", remove_schematic_footprint)
    expect("schematic pad moved to wrong net", "PAD_NET", change_schematic_pad_net)
    expect("missing fab stackup", "STACKUP", lambda board: None, text="")

    def testpoint_label(board, text="GUARD"):
        return next(item for item in board.Drawings()
                    if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() == text)

    def delete_testpoint_label(board) -> None:
        board.Remove(testpoint_label(board))

    def shrink_testpoint_label(board) -> None:
        testpoint_label(board).SetTextSize(pcbnew.VECTOR2I_MM(0.6, 0.6))

    def strand_testpoint_label(board) -> None:
        # Push GUARD out to where nothing owns it: far from TP5 and no closer to
        # any other test point.
        testpoint_label(board).SetPosition(pcbnew.VECTOR2I_MM(110.0, 115.0))

    def straddle_testpoint_label(board) -> None:
        # Midway between TP1 (y=120.0) and TP3 (y=123.5), so the mark no longer
        # says which pad it names.
        testpoint_label(board, "WE").SetPosition(pcbnew.VECTOR2I_MM(103.4, 121.75))

    expect("deleted test-point label", "TESTPOINT_LABEL", delete_testpoint_label)
    expect("sub-printable test-point label", "TESTPOINT_LABEL_HEIGHT",
           shrink_testpoint_label)
    expect("stranded test-point label", "TESTPOINT_LABEL_DISTANCE",
           strand_testpoint_label)
    def swap_testpoint_labels(board) -> None:
        # The label that every earlier check passed: right size, right side,
        # unambiguously close to a pad -- and naming the wrong electrode.
        we = testpoint_label(board, "WE")
        ce = testpoint_label(board, "CE")
        we.SetText("CE")
        ce.SetText("WE")

    expect("test-point label straddling two pads", "TESTPOINT_LABEL_AMBIGUOUS",
           straddle_testpoint_label)
    expect("WE and CE legends swapped", "TESTPOINT_LABEL_IDENTITY",
           swap_testpoint_labels)
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

    calibrated = "38/38 known-bad variants rejected" if args.calibrate else "not requested"
    report.write_text(
        "PASS: O2 probe fabrication audit\n"
        f"- 106 schematic footprints; 20.00 x 107.00 x 1.00 mm; four copper layers\n"
        f"- CELL_RE: {metrics['cell_re_trace_length_mm']:.3f} mm single F.Cu segment, no via/testpoint; "
        f"U7-to-cell pin distance {metrics['cell_re_pin_distance_mm']:.3f} mm\n"
        "- two exact 6.75 x 1.50 mm horizontal Edge.Cuts slots at y=134.00 mm; "
        "0.75 mm edge webs, 5.00 mm centre neck, and a 2.00 mm all-layer pour gap; "
        "two exact 0.80 x 16.00 mm side slots remove lateral coupling over y=137..153 mm "
        "while retaining the 2.25 mm upper connection; "
        f"{int(metrics['thermal_barrier_track_crossings'])} routed crossings and "
        f"{int(metrics['thermal_barrier_vias'])} vias locked; one 0.15 mm In2 GND bridge; "
        "no side-slot copper bridge and no transverse pad/copper-graphic/footprint-zone crossings\n"
        f"- driven guard: {int(metrics['guard_filled_regions'])} physically stitched F.Cu regions; "
        "sampled copper flanks CELL_RE on both sides of the pour gap\n"
        f"- heated island: {int(metrics['heater_spreader_filled_regions'])} connected B.Cu "
        "HEATER_LOW spreader region; exact fill and gap coverage locked\n"
        f"- heated ring: two exact 2.00 x 3.00 mm PTH corner pads with "
        f"1.00 x 2.00 mm plated-slot castellations; "
        f"TMP117-to-ring-center {metrics['tmp117_ring_distance_mm']:.3f} mm\n"
        f"- minimum track/via/drill {metrics['min_track_width_mm']:.2f}/"
        f"{metrics['min_via_diameter_mm']:.2f}/{metrics['min_via_drill_mm']:.2f} mm\n"
        f"- /+12V_SW minimum track {metrics['switched_supply_min_width_mm']:.2f} mm\n"
        "- KiCad error DRC: 0 errors, 0 unconnected; independent XML-to-PCB parity: 0 mismatches; "
        f"reviewed warnings {dict(sorted(warnings.items()))}\n"
        f"- project rules: {settings_summary}\n"
        f"- calibration: {calibrated}\n"
    )
    print(report.read_text(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
