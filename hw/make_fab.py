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

LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "Edge.Cuts"]
GERBERS = {f"o2-probe-{layer.replace('.', '_')}.gbr" for layer in LAYERS}
FILE_FUNCTIONS = {
    "o2-probe-F_Cu.gbr": "Copper,L1,Top",
    "o2-probe-In1_Cu.gbr": "Copper,L2,Inr",
    "o2-probe-In2_Cu.gbr": "Copper,L3,Inr",
    "o2-probe-B_Cu.gbr": "Copper,L4,Bot",
    "o2-probe-F_Mask.gbr": "Soldermask,Top",
    "o2-probe-B_Mask.gbr": "Soldermask,Bot",
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
    """Exact Gerber primitives for the outer 20 x 107 mm R2 contour."""
    expected = Counter()

    def point(x: float, y: float):
        return round(100.0 + x, 3), round(-(50.0 + y), 3)

    def line(start, end):
        expected[("line", frozenset((point(*start), point(*end))))] += 1

    def arc(start, center, end):
        expected[("arc", frozenset((point(*start), point(*end))), point(*center))] += 1

    line((2.0, 0.0), (18.0, 0.0))
    arc((18.0, 0.0), (17.999, 2.001), (20.0, 2.0))
    line((20.0, 2.0), (20.0, 105.0))
    arc((20.0, 105.0), (17.999, 104.999), (18.0, 107.0))
    line((18.0, 107.0), (2.0, 107.0))
    arc((2.0, 107.0), (2.001, 104.999), (0.0, 105.0))
    line((0.0, 105.0), (0.0, 2.0))
    arc((0.0, 2.0), (2.001, 2.001), (2.0, 0.0))
    return expected


def expected_thermal_slot_primitives() -> Counter:
    """Exact Gerber primitives for the two Y=134 mm thermal-break slots."""
    expected = Counter()

    def point(x: float, y: float):
        return round(x, 3), round(-y, 3)

    def line(start, end):
        expected[("line", frozenset((point(*start), point(*end))))] += 1

    def arc(start, center, end):
        expected[("arc", frozenset((point(*start), point(*end))), point(*center))] += 1

    for x in (103.75, 116.25):
        x0, x1 = x - 2.75, x + 2.75
        line((x0 + 0.5, 133.5), (x1 - 0.5, 133.5))
        arc((x1 - 0.5, 133.5), (x1 - 0.5, 134.0), (x1 - 0.5, 134.5))
        line((x1 - 0.5, 134.5), (x0 + 0.5, 134.5))
        arc((x0 + 0.5, 134.5), (x0 + 0.5, 134.0), (x0 + 0.5, 133.5))
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

    front_copper = (directory / "o2-probe-F_Cu.gbr").read_text()
    front_format = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", front_copper)
    if not front_format:
        raise SystemExit("cannot parse F.Cu Gerber coordinate format")
    guard_regions = parse_gerber_regions(
        front_copper, int(front_format.group(2)), int(front_format.group(4))
    )
    actual_guard_regions = Counter(
        (len(region), tuple(round(value, 6) for value in (
            min(point[0] for point in region), min(point[1] for point in region),
            max(point[0] for point in region), max(point[1] for point in region),
        )))
        for region in guard_regions
    )
    expected_guard_regions = Counter({
        (81, (110.323477, -141.65, 112.145819, -131.75)): 1,
        (82, (108.974715, -140.878865, 110.466013, -133.934844)): 1,
        (38, (109.220228, -132.9745, 110.405022, -131.971835)): 1,
    })
    if actual_guard_regions != expected_guard_regions:
        raise SystemExit(
            "F.Cu Gerber driven-guard regions differ: "
            f"added/changed={list((actual_guard_regions - expected_guard_regions).elements())}; "
            f"missing={list((expected_guard_regions - actual_guard_regions).elements())}"
        )
    guard_samples = (
        (110.25, -135.0), (110.10, -136.0), (109.95, -138.0), (109.60, -140.0),
        (110.95, -135.0), (110.90, -136.0), (110.65, -138.0), (110.70, -140.0),
    )
    missing_guard_samples = [
        point for point in guard_samples
        if not any(point_in_polygon(point, region) for region in guard_regions)
    ]
    if missing_guard_samples:
        raise SystemExit(f"F.Cu Gerber guard misses samples {missing_guard_samples}")
    return {
        "gerber_layers": sorted(actual),
        "plotted_outline_mm": [width, height],
        "edge_cuts_primitives": sum(primitives.values()),
        "outer_outline_primitives": sum(expected_outline.values()),
        "board_native_routed_slot_contours": 2,
        "thermal_slot_centers_mm": [[103.75, 134.0], [116.25, 134.0]],
        "thermal_slot_finished_size_mm": [5.5, 1.0],
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
    if "METRIC" not in pth_text or "METRIC" not in npth_text:
        raise SystemExit("drill outputs are not metric Excellon")
    tool_match = re.search(r"T(\d+)C3(?:\.0+)?", npth_text)
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
    expected_endpoints = {(110.0, -144.5), (110.0, -147.5)}
    matching_routes = [route for route in routes
                       if route[0] == slot_tool and {route[1], route[2]} == expected_endpoints]
    if len(routes) != 1 or len(matching_routes) != 1:
        raise SystemExit(f"SGX routed slot geometry differs: routes={routes}")
    return {
        "drill_files": [pth.name, npth.name],
        "npth_routed_slot_commands": True,
        "sgx_slot_tool_mm": 3.0,
        "sgx_slot_route_endpoints_mm": [[110.0, -144.5], [110.0, -147.5]],
        "sgx_slot_finished_size_mm": [3.0, 6.0],
    }


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
    for source in ("FAB-NOTES.md", "FAB-READINESS.md", "ASSEMBLY-EXCEPTIONS.md",
                   "pcb-audit.rpt", "schematic-audit.rpt", "erc.rpt",
                   "pcb-drc-release.json", "pcb-drc-warnings.json"):
        shutil.copy2(HERE / source, TEMP / source)

    version = run(KICAD, "--version").strip()
    manifest = {
        "release": "o2-probe Rev A bare-board first article",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kicad_cli": version,
        "input": {"file": BOARD.name, "sha256": sha256(BOARD)},
        "schematic": {"file": SCHEMATIC.name, "sha256": sha256(SCHEMATIC)},
        "layers": LAYERS,
        "silkscreen_exported": False,
        "drawing_layers": ["F.Fab", "B.Fab", "F.Silkscreen", "B.Silkscreen",
                           "Edge.Cuts", "Dwgs.User", "Cmts.User"],
        "validation": validation,
        "qualification_scope": "bare-board first article; not automated PCBA or production qualified",
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
    print(f"PASS: {ZIP}")
    print(f"SHA-256: {sha256(ZIP)}")
    print(f"files: {len(expected)}; Gerber outline: {validation['plotted_outline_mm'][0]:.2f} x "
          f"{validation['plotted_outline_mm'][1]:.2f} mm; two exact Y=134 Edge.Cuts slots "
          "and SGX routed NPTH verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
