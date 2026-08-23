#!/usr/bin/env python3
"""Own and verify the fabrication constraints in o2-probe.kicad_pro.

pcbnew saves can rewrite the adjacent project file.  Apply these values after
any generated board save, then verify by re-reading the file from disk.
"""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = HERE / "o2-probe.kicad_pro"

RULES = {
    "min_clearance": 0.15,
    "min_track_width": 0.09,
    "min_copper_edge_clearance": 0.25,
    "min_silk_clearance": 0.15,
    "min_hole_clearance": 0.20,
    "min_hole_to_hole": 0.25,
    "min_through_hole_diameter": 0.15,
    "min_via_diameter": 0.25,
    "min_via_annular_width": 0.05,
    "min_text_height": 0.8,
    "min_text_thickness": 0.12,
    "min_resolved_spokes": 2,
}

# Courtyard overlap is an assembly-density review item, not a bare-board
# manufacturing error.  The exact 28-pair allowlist is checked by audit_pcb.py.
# Every check remains enabled: values KiCad normally ignores are warnings here.
SEVERITY = {
    "clearance": "error",
    "copper_edge_clearance": "error",
    "drill_out_of_range": "error",
    "footprint": "error",
    "footprint_filters_mismatch": "warning",
    "footprint_type_mismatch": "warning",
    "hole_clearance": "error",
    "hole_to_hole": "error",
    "invalid_outline": "error",
    "lib_footprint_issues": "error",
    "lib_footprint_mismatch": "error",
    "malformed_courtyard": "error",
    "missing_courtyard": "error",
    "npth_inside_courtyard": "error",
    "pth_inside_courtyard": "error",
    "shorting_items": "error",
    "solder_mask_bridge": "error",
    "starved_thermal": "error",
    "text_height": "error",
    "text_thickness": "error",
    "track_not_centered_on_via": "warning",
    "track_width": "error",
    "tracks_crossing": "error",
    "tuning_profile_track_geometries": "warning",
    "unconnected_items": "error",
    "via_dangling": "warning",
    "zones_intersect": "error",
    "courtyards_overlap": "warning",
}

DEFAULT_CLASS = {
    "clearance": 0.15,
    "track_width": 0.18,
    "via_diameter": 0.45,
    "via_drill": 0.25,
}
TRACK_WIDTHS = [0.0, 0.09, 0.15, 0.18, 0.20, 0.25, 0.40]
VIA_DIMENSIONS = [
    {"diameter": 0.0, "drill": 0.0},
    {"diameter": 0.45, "drill": 0.25},
    {"diameter": 0.25, "drill": 0.15},
]


def apply(path: Path = PROJECT) -> None:
    data = json.loads(path.read_text())
    settings = data.setdefault("board", {}).setdefault("design_settings", {})
    settings.setdefault("rules", {}).update(RULES)
    settings.setdefault("rule_severities", {}).update(SEVERITY)
    settings["track_widths"] = list(TRACK_WIDTHS)
    settings["via_dimensions"] = [dict(value) for value in VIA_DIMENSIONS]

    classes = data.setdefault("net_settings", {}).setdefault("classes", [])
    default = next((value for value in classes if value.get("name") == "Default"), None)
    if default is None:
        default = {"name": "Default"}
        classes.append(default)
    default.update(DEFAULT_CLASS)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def verify(path: Path = PROJECT) -> str:
    data = json.loads(path.read_text())
    settings = data["board"]["design_settings"]
    problems: list[str] = []
    for key, wanted in RULES.items():
        actual = settings["rules"].get(key)
        if actual != wanted:
            problems.append(f"rules.{key}={actual!r}, want {wanted!r}")
    for key, wanted in SEVERITY.items():
        actual = settings["rule_severities"].get(key)
        if actual != wanted:
            problems.append(f"severity.{key}={actual!r}, want {wanted!r}")
    ignored = sorted(
        key for key, value in settings["rule_severities"].items() if value == "ignore"
    )
    if ignored:
        problems.append(f"DRC checks disabled with 'ignore': {ignored}")
    default = next(
        value for value in data["net_settings"]["classes"] if value.get("name") == "Default"
    )
    for key, wanted in DEFAULT_CLASS.items():
        if default.get(key) != wanted:
            problems.append(f"Default.{key}={default.get(key)!r}, want {wanted!r}")
    if problems:
        raise SystemExit(f"{path.name} settings did not stick:\n  " + "\n  ".join(problems))
    return (
        f"{len(RULES)} process rules; {len(settings['rule_severities'])} enabled "
        f"DRC severities; Default {DEFAULT_CLASS['clearance']:.2f} mm clearance"
    )


if __name__ == "__main__":
    apply()
    print(verify())
