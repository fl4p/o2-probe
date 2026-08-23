#!/usr/bin/env python3
"""Fabrication gate for the accepted O2-probe PCB.

This audit checks the schematic/PCB contract, the high-impedance cell-input
geometry, the guarded potting transition, the split ground plane, process
limits, and KiCad DRC.  ``--calibrate`` also mutates fresh in-memory copies of
the board and proves that the load-bearing checks reject known-bad variants.
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
        ("C11", "C12"), ("C3", "L1"), ("RH1", "U10"), ("RH2", "U10"),
        ("TP3", "U4"), ("J104", "R3"), ("C5", "U2"), ("D6", "J2"),
        ("J2", "TP1"), ("J2", "TP5"), ("C14", "C26"), ("D2", "J103"),
        ("J103", "R2"), ("D4", "R12"), ("R10", "R11"), ("R22", "R23"),
        ("D1", "J102"), ("C31", "RV1"), ("R20", "RV1"), ("R38", "RV1"),
        ("C15", "R8"), ("C15", "R9"), ("D2", "J104"), ("D5", "R14"),
    }
}


def mm(value: int) -> float:
    return pcbnew.ToMM(value)


def xy(point) -> tuple[float, float]:
    return mm(point.x), mm(point.y)


def near(actual: float, wanted: float, tolerance: float = 0.01) -> bool:
    return abs(actual - wanted) <= tolerance


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
    check(errors, near(mm(bbox.GetHeight()), 125.05), "OUTLINE_HEIGHT",
          f"edge bounding box is {mm(bbox.GetHeight()):.3f} mm, want 125.05 including stroke")
    check(errors, near(mm(board.GetDesignSettings().GetBoardThickness()), 1.0),
          "BOARD_THICKNESS", "board is not 1.00 mm")
    check(errors, board.GetCopperLayerCount() == 4, "COPPER_LAYERS",
          f"found {board.GetCopperLayerCount()}, want four")
    edge_items = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    check(errors, len(edge_items) == 32, "EDGE_ITEM_COUNT",
          f"found {len(edge_items)}, want 8 outline + 24 routed-slot items")

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
    check(errors, len(gnd_zones) == 2, "GND_ZONE_SPLIT",
          f"found {len(gnd_zones)} In2 GND zones, want potted and gas-side zones")
    if len(gnd_zones) == 2:
        ranges = []
        for zone in gnd_zones:
            ys = [xy(zone.GetCornerPosition(index))[1] for index in range(zone.GetNumCorners())]
            ranges.append((round(min(ys), 2), round(max(ys), 2)))
        check(errors, sorted(ranges) == [(50.25, 131.75), (135.25, 174.75)],
              "GND_TRANSITION_GAP", f"In2 zone y-ranges are {sorted(ranges)}")
    gnd_bridges = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != "/GND" or item.GetLayer() != pcbnew.In2_Cu:
            continue
        start, end = xy(item.GetStart()), xy(item.GetEnd())
        if min(start[1], end[1]) <= 131.75 and max(start[1], end[1]) >= 135.25:
            gnd_bridges.append(item)
    check(errors, len(gnd_bridges) == 1, "GND_BRIDGE_COUNT",
          f"found {len(gnd_bridges)} GND connections across the potting transition")
    if len(gnd_bridges) == 1:
        bridge = gnd_bridges[0]
        start, end = xy(bridge.GetStart()), xy(bridge.GetEnd())
        check(errors, near(start[0], 100.55) and near(end[0], 100.55)
              and near(mm(bridge.GetWidth()), 0.25), "GND_BRIDGE_GEOMETRY",
              f"bridge is {start}->{end}, width {mm(bridge.GetWidth()):.3f} mm")

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

    def narrow_track(board) -> None:
        track = next(item for item in board.GetTracks() if not isinstance(item, pcbnew.PCB_VIA))
        track.SetWidth(pcbnew.FromMM(0.08))

    def move_u7(board) -> None:
        footprint = next(fp for fp in board.Footprints() if fp.GetReference() == "U7")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(110.0, 120.0))

    expect("CELL_RE via", "CELL_RE_VIA", add_cell_via)
    expect("missing guard", "GUARD_ZONE", remove_guard)
    expect("continuous/unsplit plane regression", "GND_ZONE_SPLIT", remove_gnd_zone)
    expect("sub-process-width trace", "MIN_TRACK_WIDTH", narrow_track)
    expect("remote AFE", "U7_PLACEMENT", move_u7)
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

    calibrated = "6/6 known-bad variants rejected" if args.calibrate else "not requested"
    report.write_text(
        "PASS: O2 probe fabrication audit\n"
        f"- 109 schematic footprints; 20.00 x 125.00 x 1.00 mm; four copper layers\n"
        f"- CELL_RE: {metrics['cell_re_trace_length_mm']:.3f} mm single F.Cu segment, no via/testpoint; "
        f"U7-to-cell pin distance {metrics['cell_re_pin_distance_mm']:.3f} mm\n"
        "- driven F.Cu guard present; In2 GND split at potting boundary with one 0.25 mm bridge\n"
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
