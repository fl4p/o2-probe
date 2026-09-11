#!/usr/bin/env python3
"""Build and inspect the Rev A first-article bare-board release."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
BOARD = HERE / "o2-probe.kicad_pcb"
SCHEMATIC = HERE / "o2-probe.kicad_sch"
KICAD = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KIPY = Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
FAB_ROOT = HERE / "fab"
RELEASE = FAB_ROOT / "o2-probe-rev-a"
TEMP = FAB_ROOT / ".o2-probe-rev-a.tmp"
ZIP = FAB_ROOT / "o2-probe-rev-a-fab.zip"

# The stencil layers are here because leaving them out is not a decision anyone
# made.  The KiCad footprints carry real paste engineering -- Texas_RTE0016D's
# exposed pad, for one, is deliberately NOT 1:1: pad 17 gets copper and mask
# only, and four separate 0.32 x 0.32 mm roundrect apertures (rratio 0.25, so
# r = 0.08) supply 0.3876 of its 0.64 mm2 -- a segmented 60.6%, verified by
# plotting the layer and measuring the emitted D16 aperture rather than by
# multiplying nominal pad sizes, which ignores the corner radius and overstates
# it as 64%. The pattern exists to stop the part floating on molten paste and
# starving its perimeter joints.  Omitting F.Paste threw that away silently: an
# assembler with no paste layer cuts a stencil from the copper, which on that pad
# is exactly the 1:1 aperture the footprint was drawn to avoid.  U8 pin 5 reached
# a bench with an open joint on 2026-09-04 -- hand-fitted, so not this mechanism,
# but it is the failure this omission would have produced at scale.
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask",
          "F.Paste", "B.Paste", "Edge.Cuts"]
# Set to None once the 33 legend violations are cleared and the silk layers are
# added to LAYERS above; main() refuses to build if the two disagree.
SILKSCREEN_WAIVER = "33 unresolved legend violations; see FAB-READINESS.md"
GERBERS = {f"o2-probe-{layer.replace('.', '_')}.gbr" for layer in LAYERS}
FILE_FUNCTIONS = {
    "o2-probe-F_Cu.gbr": "Copper,L1,Top",
    "o2-probe-In1_Cu.gbr": "Copper,L2,Inr",
    "o2-probe-In2_Cu.gbr": "Copper,L3,Inr",
    "o2-probe-B_Cu.gbr": "Copper,L4,Bot",
    "o2-probe-F_Mask.gbr": "Soldermask,Top",
    "o2-probe-B_Mask.gbr": "Soldermask,Bot",
    "o2-probe-F_Paste.gbr": "Paste,Top",
    "o2-probe-B_Paste.gbr": "Paste,Bot",
    "o2-probe-Edge_Cuts.gbr": "Profile,NP",
}


def run(*command: str | Path) -> str:
    result = subprocess.run([str(value) for value in command], cwd=HERE,
                            text=True, capture_output=True)
    if result.returncode:
        print(result.stdout, end="", file=sys.stderr)
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(map(str, command))}")
    return result.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_outline_primitives() -> Counter:
    """Exact Gerber primitives for the square-tip 20 x 107 mm contour."""
    expected = Counter()

    def point(x: float, y: float):
        return round(100.0 + x, 3), round(-(50.0 + y), 3)

    def line(start, end):
        expected[("line", frozenset((point(*start), point(*end))))] += 1

    def arc(start, center, end):
        expected[("arc", frozenset((point(*start), point(*end))), point(*center))] += 1

    line((2.0, 0.0), (18.0, 0.0))
    arc((18.0, 0.0), (17.999, 2.001), (20.0, 2.0))
    line((20.0, 2.0), (20.0, 107.0))
    line((20.0, 107.0), (0.0, 107.0))
    line((0.0, 107.0), (0.0, 2.0))
    arc((0.0, 2.0), (2.001, 2.001), (2.0, 0.0))
    return expected


def expected_thermal_slot_primitives() -> Counter:
    """Exact Gerber primitives for all four heated-island thermal slots."""
    expected = Counter()

    def point(x: float, y: float):
        return round(x, 3), round(-y, 3)

    def line(start, end):
        expected[("line", frozenset((point(*start), point(*end))))] += 1

    def arc(start, center, end):
        expected[("arc", frozenset((point(*start), point(*end))), point(*center))] += 1

    for x in (104.125, 115.875):
        x0, x1 = x - 3.375, x + 3.375
        line((x0 + 0.75, 133.25), (x1 - 0.75, 133.25))
        arc((x1 - 0.75, 133.25), (x1 - 0.75, 134.0), (x1 - 0.75, 134.75))
        line((x1 - 0.75, 134.75), (x0 + 0.75, 134.75))
        arc((x0 + 0.75, 134.75), (x0 + 0.75, 134.0), (x0 + 0.75, 133.25))
    for x in (101.2, 118.8):
        x0, x1 = x - 0.4, x + 0.4
        y0, y1 = 137.0, 153.0
        line((x0, y0 + 0.4), (x0, y1 - 0.4))
        arc((x0, y1 - 0.4), (x, y1 - 0.4), (x1, y1 - 0.4))
        line((x1, y1 - 0.4), (x1, y0 + 0.4))
        arc((x1, y0 + 0.4), (x, y0 + 0.4), (x0, y0 + 0.4))
    return expected


def parse_gerber_primitives(text: str, x_fraction: int, y_fraction: int) -> Counter:
    """Parse the simple modal line/arc records emitted by KiCad Edge.Cuts."""
    primitives = Counter()
    mode = "line"
    current = None
    coordinate = re.compile(
        r"X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([12])\*"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "G01*":
            mode = "line"
            continue
        if line in ("G02*", "G03*"):
            mode = "arc"
            continue
        match = coordinate.fullmatch(line)
        if not match:
            continue
        x, y, i, j, operation = match.groups()
        target = (int(x) / 10**x_fraction, int(y) / 10**y_fraction)
        if operation == "2":
            current = target
            continue
        if current is None:
            raise SystemExit("Edge.Cuts Gerber draws before setting a position")
        start = tuple(round(value, 3) for value in current)
        end = tuple(round(value, 3) for value in target)
        if mode == "line":
            primitives[("line", frozenset((start, end)))] += 1
        else:
            if i is None or j is None:
                raise SystemExit("Edge.Cuts Gerber arc lacks I/J centre offsets")
            center = (round(current[0] + int(i) / 10**x_fraction, 3),
                      round(current[1] + int(j) / 10**y_fraction, 3))
            primitives[("arc", frozenset((start, end)), center)] += 1
        current = target
    return primitives


def parse_gerber_regions(text: str, x_fraction: int,
                         y_fraction: int) -> list[list[tuple[float, float]]]:
    """Parse the linear G36/G37 regions emitted for the F.Cu guard fill."""
    regions: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    coordinate = re.compile(r"X(-?\d+)Y(-?\d+)(?:D0[12])?\*")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "G36*":
            if current is not None:
                raise SystemExit("nested Gerber regions are unsupported")
            current = []
            continue
        if line == "G37*":
            if not current:
                raise SystemExit("empty or unmatched Gerber region")
            regions.append(current)
            current = None
            continue
        if current is None:
            continue
        match = coordinate.fullmatch(line)
        if match:
            current.append((int(match.group(1)) / 10**x_fraction,
                            int(match.group(2)) / 10**y_fraction))
    if current is not None:
        raise SystemExit("unterminated Gerber region")
    return regions


def point_in_polygon(point: tuple[float, float],
                     polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def check_silkscreen_policy(layers, waiver) -> bool:
    """Keep the waiver and the plotted layer set from drifting apart.

    While the waiver stands, neither silk layer may be plotted; when someone
    clears the legend violations and adds them, they must retire the waiver in
    the same edit.  Without this the manifest can say silkscreen was withheld
    while the Gerbers contain it, which is a provenance claim with nothing
    behind it -- the same class of defect as the missing paste layer.
    """
    exported = any(layer.endswith(".Silkscreen") for layer in layers)
    if exported and waiver:
        raise SystemExit(
            "silkscreen is in LAYERS but SILKSCREEN_WAIVER still stands: clear the "
            "legend violations and set SILKSCREEN_WAIVER = None, or drop the layers")
    if not exported and not waiver:
        raise SystemExit("silkscreen is withheld from LAYERS with no recorded waiver")
    return exported


def validate_gerbers(directory: Path) -> dict[str, object]:
    actual = {path.name for path in directory.glob("*.gbr")}
    missing = GERBERS - actual
    extra = actual - GERBERS
    if missing or extra:
        raise SystemExit(f"Gerber layer set differs: missing={sorted(missing)}, extra={sorted(extra)}")
    for filename, file_function in FILE_FUNCTIONS.items():
        text = (directory / filename).read_text(errors="replace")
        if file_function not in text:
            raise SystemExit(f"{filename} lacks X2 file function {file_function}")
        if len(text) < 500:
            raise SystemExit(f"{filename} is unexpectedly small")

    outline = (directory / "o2-probe-Edge_Cuts.gbr").read_text()
    format_match = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", outline)
    if not format_match:
        raise SystemExit("cannot parse Edge.Cuts Gerber coordinate format")
    x_frac = int(format_match.group(2))
    y_frac = int(format_match.group(4))
    points = [(int(x) / 10**x_frac, int(y) / 10**y_frac)
              for x, y in re.findall(r"^X(-?\d+)Y(-?\d+)", outline, re.MULTILINE)]
    if not points:
        raise SystemExit("Edge.Cuts Gerber has no coordinate records")
    xs, ys = zip(*points)
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if abs(width - 20.0) > 0.01 or abs(height - 107.0) > 0.01:
        raise SystemExit(f"plotted outline is {width:.3f} x {height:.3f} mm")
    primitives = parse_gerber_primitives(outline, x_frac, y_frac)
    expected_outline = expected_outline_primitives()
    expected_slots = expected_thermal_slot_primitives()
    expected_edge_cuts = expected_outline + expected_slots
    if primitives != expected_edge_cuts:
        raise SystemExit(
            "Edge.Cuts outer/thermal-slot contour differs: "
            f"primitive_count={sum(primitives.values())}; "
            f"added/changed={list((primitives - expected_edge_cuts).elements())}; "
            f"missing={list((expected_edge_cuts - primitives).elements())}"
        )

    copper_regions = {}
    for layer in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu"):
        text = (directory / f"o2-probe-{layer}.gbr").read_text()
        coordinate_format = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
        if not coordinate_format:
            raise SystemExit(f"cannot parse {layer.replace('_', '.')} Gerber coordinate format")
        copper_regions[layer] = parse_gerber_regions(
            text, int(coordinate_format.group(2)), int(coordinate_format.group(4))
        )

    guard_regions = copper_regions["F_Cu"]
    actual_guard_regions = Counter(
        (len(region), tuple(round(value, 6) for value in (
            min(point[0] for point in region), min(point[1] for point in region),
            max(point[0] for point in region), max(point[1] for point in region),
        )))
        for region in guard_regions
    )
    expected_guard_regions = Counter({
        (69, (110.323477, -141.65, 111.6045, -135.0)): 1,
        (60, (108.974715, -140.878865, 110.393458, -135.0)): 1,
        (38, (109.220228, -132.9745, 110.405022, -131.971835)): 1,
    })
    if actual_guard_regions != expected_guard_regions:
        raise SystemExit(
            "F.Cu Gerber driven-guard regions differ: "
            f"added/changed={list((actual_guard_regions - expected_guard_regions).elements())}; "
            f"missing={list((expected_guard_regions - actual_guard_regions).elements())}"
        )
    guard_samples = (
        (110.25, -135.1), (110.10, -136.0), (109.95, -138.0), (109.60, -140.0),
        (110.95, -135.1), (110.90, -136.0), (110.65, -138.0), (110.70, -140.0),
    )
    missing_guard_samples = [
        point for point in guard_samples
        if not any(point_in_polygon(point, region) for region in guard_regions)
    ]
    if missing_guard_samples:
        raise SystemExit(f"F.Cu Gerber guard misses samples {missing_guard_samples}")

    expected_zone_regions = {
        "In1_Cu": Counter(),
        "In2_Cu": Counter({
            (1114, (100.25, -156.75, 119.75, -135.0)): 1,
            (7433, (100.25, -133.0, 119.75, -50.25)): 1,
        }),
        "B_Cu": Counter({
            (1303, (100.25, -156.75, 119.75, -135.0)): 1,
        }),
    }
    for layer, expected_regions in expected_zone_regions.items():
        actual_regions = Counter(
            (len(region), tuple(round(value, 6) for value in (
                min(point[0] for point in region), min(point[1] for point in region),
                max(point[0] for point in region), max(point[1] for point in region),
            )))
            for region in copper_regions[layer]
        )
        if actual_regions != expected_regions:
            raise SystemExit(
                f"{layer.replace('_', '.')} Gerber zone regions differ: "
                f"added/changed={list((actual_regions - expected_regions).elements())}; "
                f"missing={list((expected_regions - actual_regions).elements())}"
            )

    # Gerber regions represent poured copper.  Tracks are intentionally allowed
    # through the barrier, but no zone fill may bridge it on any copper layer.
    thermal_gap_samples = tuple((x, -134.0) for x in (101.0, 104.125, 107.0,
                                                       110.0, 113.0, 115.875,
                                                       119.0))
    gap_fill_hits = {
        layer.replace("_", "."): [
            sample for sample in thermal_gap_samples
            if any(point_in_polygon(sample, region) for region in regions)
        ]
        for layer, regions in copper_regions.items()
    }
    gap_fill_hits = {layer: hits for layer, hits in gap_fill_hits.items() if hits}
    if gap_fill_hits:
        raise SystemExit(f"thermal-barrier Gerber region crosses the 2 mm gap: {gap_fill_hits}")

    side_slot_samples = tuple(
        (x, -y) for x in (101.2, 118.8) for y in (138.0, 145.0, 152.0)
    )
    side_slot_fill_hits = {
        layer.replace("_", "."): [
            sample for sample in side_slot_samples
            if any(point_in_polygon(sample, region) for region in regions)
        ]
        for layer, regions in copper_regions.items()
    }
    side_slot_fill_hits = {
        layer: hits for layer, hits in side_slot_fill_hits.items() if hits
    }
    if side_slot_fill_hits:
        raise SystemExit(
            f"copper Gerber region enters side-slot voids: {side_slot_fill_hits}"
        )

    heater_samples = ((102.0, -140.0), (110.0, -150.0), (118.0, -140.0))
    missing_heater_samples = [
        point for point in heater_samples
        if not any(point_in_polygon(point, region) for region in copper_regions["B_Cu"])
    ]
    if missing_heater_samples:
        raise SystemExit(f"B.Cu heater-spreader Gerber misses samples {missing_heater_samples}")

    gnd_plane_samples = ((102.0, -132.0), (110.0, -150.0), (118.0, -140.0))
    missing_gnd_samples = [
        point for point in gnd_plane_samples
        if not any(point_in_polygon(point, region) for region in copper_regions["In2_Cu"])
    ]
    if missing_gnd_samples:
        raise SystemExit(f"In2.Cu GND Gerber misses samples {missing_gnd_samples}")
    return {
        "gerber_layers": sorted(actual),
        "plotted_outline_mm": [width, height],
        "edge_cuts_primitives": sum(primitives.values()),
        "outer_outline_primitives": sum(expected_outline.values()),
        "board_native_routed_slot_contours": 4,
        "thermal_slot_centers_mm": [[104.125, 134.0], [115.875, 134.0]],
        "thermal_slot_finished_size_mm": [6.75, 1.5],
        "side_thermal_slot_centers_mm": [[101.2, 145.0], [118.8, 145.0]],
        "side_thermal_slot_finished_size_mm": [0.8, 16.0],
        "thermal_copper_fill_gap_y_mm": [133.0, 135.0],
        "thermal_copper_fill_gap_layers": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
        "thermal_gap_gerber_samples_verified_per_layer": len(thermal_gap_samples),
        "side_thermal_slot_void_samples_verified_per_layer": len(side_slot_samples),
        "heated_island_spreader_layer": "B.Cu",
        "heated_island_spreader_net": "/HEATER_LOW",
        "heated_island_spreader_samples_verified": len(heater_samples),
        "gnd_plane_regions_across_barrier": 2,
        "f_cu_driven_guard_regions": len(guard_regions),
        "f_cu_guard_samples_verified": len(guard_samples),
    }


def validate_drills(directory: Path) -> dict[str, object]:
    pth = directory / "o2-probe-PTH.drl"
    npth = directory / "o2-probe-NPTH.drl"
    if not pth.is_file() or not npth.is_file():
        raise SystemExit("separate PTH/NPTH Excellon outputs are missing")
    pth_text = pth.read_text()
    npth_text = npth.read_text()
    drill_report = (directory / "o2-probe-drill-report.txt").read_text()
    if "METRIC" not in pth_text or "METRIC" not in npth_text:
        raise SystemExit("drill outputs are not metric Excellon")
    tool_match = re.search(r"^T(\d+)C3(?:\.0+)?$", npth_text, re.MULTILINE)
    if not tool_match:
        raise SystemExit("NPTH data does not contain the 3.00 mm SGX slot tool")
    if "M15" not in npth_text or "G01" not in npth_text:
        raise SystemExit("NPTH oblongs are not emitted as routed slots")
    slot_tool = f"T{int(tool_match.group(1))}"
    selected_tool = ""
    route_start = None
    routing = False
    routes = []
    coordinate = re.compile(r"X(-?\d+(?:\.\d+)?)Y(-?\d+(?:\.\d+)?)")
    for line in npth_text.splitlines():
        if re.fullmatch(r"T\d+", line):
            selected_tool = line
        match = coordinate.search(line)
        if line.startswith("G00") and match:
            route_start = tuple(map(float, match.groups()))
        elif line == "M15":
            routing = True
        elif line.startswith("G01") and match and routing and route_start is not None:
            routes.append((selected_tool, route_start, tuple(map(float, match.groups()))))
        elif line == "M16":
            routing = False
    expected_endpoints = {(110.0, -143.8), (110.0, -146.8)}
    matching_routes = [route for route in routes
                       if route[0] == slot_tool and {route[1], route[2]} == expected_endpoints]
    if len(routes) != 1 or len(matching_routes) != 1:
        raise SystemExit(f"SGX routed slot geometry differs: routes={routes}")

    ring_tool_match = re.search(r"^T(\d+)C1(?:\.0+)?$", pth_text, re.MULTILINE)
    if not ring_tool_match:
        raise SystemExit("PTH data does not contain the 1.00 mm ring-castellation tool")
    ring_tool = f"T{int(ring_tool_match.group(1))}"
    selected_tool = ""
    route_start = None
    routing = False
    pth_routes = []
    for line in pth_text.splitlines():
        if re.fullmatch(r"T\d+", line):
            selected_tool = line
        match = coordinate.search(line)
        if line.startswith("G00") and match:
            route_start = tuple(map(float, match.groups()))
        elif line == "M15":
            routing = True
        elif line.startswith("G01") and match and routing and route_start is not None:
            pth_routes.append((selected_tool, route_start, tuple(map(float, match.groups()))))
        elif line == "M16":
            routing = False
    expected_ring_routes = {
        frozenset(((100.0, -155.0), (100.0, -156.0))),
        frozenset(((120.0, -155.0), (120.0, -156.0))),
    }
    actual_ring_routes = {
        frozenset((route[1], route[2]))
        for route in pth_routes if route[0] == ring_tool
    }
    if len(pth_routes) != 2 or actual_ring_routes != expected_ring_routes:
        raise SystemExit(f"ring PTH castellated-slot geometry differs: routes={pth_routes}")
    if not re.search(
        r"1\.000mm\s+0\.0394\"\s+\(2 holes\)\s+\(with 2 slots, castellated\)",
        drill_report,
    ):
        raise SystemExit("drill report does not identify both 1.00 mm ring slots as castellated")
    return {
        "drill_files": [pth.name, npth.name],
        "npth_routed_slot_commands": True,
        "sgx_slot_tool_mm": 3.0,
        "sgx_slot_route_endpoints_mm": [[110.0, -143.8], [110.0, -146.8]],
        "sgx_slot_finished_size_mm": [3.0, 6.0],
        "ring_castellation_plated_slot_commands": True,
        "ring_castellation_tool_mm": 1.0,
        "ring_castellation_route_endpoints_mm": [
            [[100.0, -155.0], [100.0, -156.0]],
            [[120.0, -155.0], [120.0, -156.0]],
        ],
        "ring_castellation_finished_size_mm": [1.0, 2.0],
    }


def audit_bom() -> dict[str, object]:
    """Run the procurement audit and return its verdict.

    A bare board genuinely does not need MPNs, so an unsourced part must not
    block this release.  What it must not do is vanish: L1, DZ1 and F1 reached
    neither purchase order because their unsourced state lived only in prose in
    SCHEMATIC-REVIEW.md while the release declared itself ready.  The verdict
    therefore travels inside the release and inside the manifest's own
    qualification scope, where anyone building a basket has to meet it.

    An audit that cannot be evaluated is not a pass: a missing report or a
    report without a verdict aborts the build rather than defaulting to clean.
    """
    command = [sys.executable, "audit_bom.py"]
    snapshot = HERE / "purchase-orders.json"
    if snapshot.is_file():
        command += ["--purchase-orders", str(snapshot)]
    result = subprocess.run([str(c) for c in command], cwd=HERE,
                            text=True, capture_output=True)
    report = HERE / "bom-audit.rpt"
    if not report.is_file():
        print(result.stdout, end="", file=sys.stderr)
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit("BOM audit produced no report; procurement state is unknown")
    lines = report.read_text().splitlines()
    verdict = next((line.split(": ", 1)[1] for line in lines
                    if line.startswith("result: ")), "")
    if verdict not in ("PASS", "FAIL"):
        raise SystemExit(f"BOM audit report carries no usable verdict ({verdict!r})")
    errors = [line.removeprefix("ERROR: ") for line in lines
              if line.startswith("ERROR: ")]
    unsourced = next((line.split(": ", 1)[1] for line in lines
                      if line.startswith("unsourced fitted components: ")), "")
    if verdict == "FAIL" and not errors:
        raise SystemExit("BOM audit reports FAIL with no errors listed")
    if not (HERE / "o2-probe-bom.csv").is_file():
        raise SystemExit("BOM audit produced no o2-probe-bom.csv")
    return {"result": verdict, "unsourced": unsourced,
            "error_count": len(errors), "errors": errors,
            "purchase_orders_checked": snapshot.is_file()}


def main() -> int:
    if not KICAD.is_file() or not KIPY.is_file():
        raise SystemExit("KiCad 10 CLI/bundled Python not found at the recorded macOS paths")

    # Validate sources before producing any orderable output.
    run(sys.executable, "project_settings.py")
    run(sys.executable, "gen_sch.py")
    run(KICAD, "sch", "export", "netlist", "--format", "kicadxml",
        "-o", "o2-probe.xml", SCHEMATIC)
    run(KICAD, "sch", "erc", "--exit-code-violations", "-o", "erc.rpt", SCHEMATIC)
    run(sys.executable, "audit_schematic.py")
    bom = audit_bom()
    run(KICAD, "pcb", "drc", "--severity-error", "--schematic-parity",
        "--exit-code-violations", "--format", "json", "-o", "pcb-drc-release.json", BOARD)
    run(KICAD, "pcb", "drc", "--severity-warning", "--severity-error",
        "--schematic-parity", "--format", "json", "-o", "pcb-drc-warnings.json", BOARD)
    run(KIPY, "audit_pcb.py", "--calibrate")

    FAB_ROOT.mkdir(exist_ok=True)
    if TEMP.exists():
        shutil.rmtree(TEMP)
    TEMP.mkdir()

    run(KICAD, "pcb", "export", "gerbers", "-o", TEMP,
        "--layers", ",".join(LAYERS), "--no-protel-ext", "--check-zones", BOARD)
    run(KICAD, "pcb", "export", "drill", "-o", TEMP, "--format", "excellon",
        "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
        "--excellon-oval-format", "route", "--excellon-separate-th",
        "--generate-map", "--map-format", "pdf", "--generate-report",
        "--report-path", TEMP / "o2-probe-drill-report.txt", BOARD)
    run(KICAD, "pcb", "export", "pdf", "-o", TEMP / "o2-probe-fab-drawing.pdf",
        "--layers", "F.Fab,B.Fab,F.Silkscreen,B.Silkscreen,Edge.Cuts,Dwgs.User,Cmts.User",
        "--mode-multipage", "--black-and-white", "--check-zones", BOARD)

    validation = {}
    validation.update(validate_gerbers(TEMP))
    validation.update(validate_drills(TEMP))
    for source in ("FAB-NOTES.md", "FAB-READINESS.md", "THERMAL-BARRIER.md",
                   "ASSEMBLY-EXCEPTIONS.md", "pcb-audit.rpt",
                   "schematic-audit.rpt", "erc.rpt", "pcb-drc-release.json",
                   "pcb-drc-warnings.json", "bom-audit.rpt", "o2-probe-bom.csv"):
        shutil.copy2(HERE / source, TEMP / source)

    silkscreen_exported = check_silkscreen_policy(LAYERS, SILKSCREEN_WAIVER)

    version = run(KICAD, "--version").strip()
    scope = "bare-board first article; not automated PCBA or production qualified"
    if bom["result"] != "PASS":
        scope += (f"; BOM audit FAIL ({bom['error_count']} procurement errors, "
                  f"unsourced {bom['unsourced']}). Do not build a parts basket "
                  "from this release until bom-audit.rpt is clean")
    manifest = {
        "release": "o2-probe Rev A bare-board first article",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kicad_cli": version,
        "input": {"file": BOARD.name, "sha256": sha256(BOARD)},
        "schematic": {"file": SCHEMATIC.name, "sha256": sha256(SCHEMATIC)},
        "layers": LAYERS,
        # DERIVED, not asserted.  These were hardcoded literals, which meant the
        # manifest could have claimed silkscreen was withheld while LAYERS
        # exported it -- a provenance claim with nothing behind it, which is the
        # same class of defect as the missing layer itself.
        "paste_exported": any(layer.endswith(".Paste") for layer in LAYERS),
        # Silkscreen stays out of the Gerber set, but as a WAIVER with a lifting
        # condition, not an omission: the board carries 33 legend violations
        # (18 overlaps, 14 silk-on-exposed-copper, 1 silk-to-edge) that are
        # harmless only while nothing is printed.  Lift this when those are
        # cleared -- several offenders are deleted by the pending AFE/fork
        # revision anyway.  FAB-READINESS.md holds the detail.
        "silkscreen_exported": silkscreen_exported,
        "silkscreen_waiver": None if silkscreen_exported else SILKSCREEN_WAIVER,
        "drawing_layers": ["F.Fab", "B.Fab", "F.Silkscreen", "B.Silkscreen",
                           "Edge.Cuts", "Dwgs.User", "Cmts.User"],
        "validation": validation,
        "bom": bom,
        "qualification_scope": scope,
    }
    (TEMP / "fab-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    checksum_paths = sorted(path for path in TEMP.iterdir() if path.is_file())
    (TEMP / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in checksum_paths)
    )

    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    TEMP.rename(RELEASE)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted(RELEASE.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    with zipfile.ZipFile(ZIP) as archive:
        archived = set(archive.namelist())
    expected = {path.name for path in RELEASE.iterdir() if path.is_file()}
    if archived != expected:
        raise SystemExit(f"ZIP inventory mismatch: {sorted(archived ^ expected)}")
    (FAB_ROOT / "o2-probe-rev-a-fab.zip.sha256").write_text(
        f"{sha256(ZIP)}  {ZIP.name}\n"
    )
    print(f"BOM: {bom['result']} ({bom['error_count']} procurement errors); "
          f"unsourced {bom['unsourced'] or 'none'}")
    if bom["result"] != "PASS":
        print("BOM: bare boards are unaffected; the parts basket is NOT clear "
              "-- see bom-audit.rpt before ordering", file=sys.stderr)
    print(f"PASS: {ZIP}")
    print(f"SHA-256: {sha256(ZIP)}")
    print(f"files: {len(expected)}; Gerber outline: {validation['plotted_outline_mm'][0]:.2f} x "
          f"{validation['plotted_outline_mm'][1]:.2f} mm; two exact Y=134 Edge.Cuts slots "
          "plus two exact 0.8 x 16 mm side slots "
          "plus two plated-slot ring castellations and SGX routed NPTH verified")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build a revision-specific O2 probe fabrication package")
    parser.add_argument("--revision", choices=("rev-a", "rev-b"), default="rev-b",
                        help="default: rev-b engineering review; rev-a retains the historical exporter")
    args = parser.parse_args()
    if args.revision == "rev-b":
        from make_fab_revb import main as build_revb
        raise SystemExit(build_revb())
    raise SystemExit(main())
