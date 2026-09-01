#!/usr/bin/env python3
"""Procurement audit: derive the orderable BOM and fail on anything unbuyable.

`audit_schematic.py` proves the design is wired correctly.  Nothing proved it
could be *bought*.  The Rev A basket was transcribed by hand from the schematic,
which selects on MPN strings, so the components carrying a value family instead
of an MPN (L1 `4.7u SHIELDED`, DZ1 `12V ZENER`, F1 `0.75A PTC`) produced nothing
to paste and were silently absent from both purchase orders.

This audit inverts that.  Every non-DNP component must resolve to exactly one of:

  * an exact `MPN` property in the schematic, or
  * one explicitly declared sourcing class in `sourcing.json`.

A component resolving to neither is an ERROR, never silence.  The class is
checked against a closed vocabulary held here rather than against the names the
audited file happens to declare, and the rule forbidding a specified value from
being bought to its family name keys on whether the class buys to value, not on
one class's spelling.

It then reconciles the resolved BOM against a purchase-order snapshot, which is
REQUIRED and defaults to `purchase-orders.json`: this catches a substituted MPN
(Q1 `DMP3010L-7` in the schematic vs `DMP3130L-7` on PO-0010) as well as one
that reached no order at all.  That check used to be optional, which put the
audit's own boundary one step short of where Rev A failed -- the parts went
missing during transcription into orders, and a default run never looked.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCH = ROOT / "o2-probe.kicad_sch"
XML = ROOT / "o2-probe.xml"
SOURCING = ROOT / "sourcing.json"
BOM_CSV = ROOT / "o2-probe-bom.csv"
REPORT = ROOT / "bom-audit.rpt"
KICAD = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# Tokens that make a value a specification rather than a shelf item.  A part
# whose value carries one of these cannot be bought to the value alone, so it
# may not be declared generic-stock -- that would be a mute button, not a fix.
SPEC_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?\s*%|X7R|X5R|X6S|C0G|NP0|Y5V|\b\d+(?:\.\d+)?\s*V\b|SHIELDED"
    r"|ZENER|\bPTC\b|\bTVS\b|\bA\s+PTC\b|\bW\b|SAT|\bLDO\b)",
    re.IGNORECASE,
)
NEAR_MISS_RATIO = 0.85

# The closed set of sourcing classes.  A class is a claim about HOW a part is
# bought, so the vocabulary belongs to the audit, not to the file under audit.
# Reading it out of that file (`known = set(raw["classes"])`) let any new name
# declare itself legitimate: adding "prototype-stock" bought to value walked
# past the SPEC_TOKEN check below, which only ever fired on the literal string
# "generic-stock".  `buys_to_value` is what that check keys on now, so a class
# meaning "bought from reel stock" cannot be renamed out of its own rule.
CLASS_RULES: dict[str, dict[str, bool]] = {
    "generic-stock": {"buys_to_value": True, "wildcard_value": False},
    "not-purchased": {"buys_to_value": False, "wildcard_value": True},
    "custom": {"buys_to_value": False, "wildcard_value": False},
}

# Where the order snapshot lives when --purchase-orders is not given.  It is
# not optional: the Rev A parts went missing during hand transcription from
# basket to order, so an audit that skips the order check passes over the exact
# step that failed.  No snapshot is an unevaluable input, and unevaluable is
# not OK -- to audit a design with nothing ordered yet, write a snapshot with
# an empty `lines` list and read the resulting list of everything outstanding.
ORDERS = ROOT / "purchase-orders.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


class Component:
    __slots__ = ("ref", "value", "footprint", "mpn", "dnp", "note")

    def __init__(self, comp: ET.Element) -> None:
        self.ref = comp.attrib.get("ref", "")
        self.value = (comp.findtext("value") or "").strip()
        self.footprint = (comp.findtext("footprint") or "").strip()
        fields = comp.find("fields")
        table = {f.attrib.get("name"): (f.text or "").strip()
                 for f in (list(fields) if fields is not None else [])}
        self.mpn = table.get("MPN", "")
        self.note = table.get("Design Note", "")
        # KiCad emits <property name="dnp"/> with no value.  Read the property,
        # never the value string: J2 is DNP and says so nowhere in its value.
        self.dnp = any(p.attrib.get("name") == "dnp"
                       for p in comp.findall("property"))

    @property
    def key(self) -> str:
        return f"{self.footprint}|{self.value}"

    @property
    def wildcard_key(self) -> str:
        return f"{self.footprint}|*"


def export_netlist() -> None:
    subprocess.run(
        [KICAD, "sch", "export", "netlist", "--format", "kicadxml",
         "-o", str(XML), str(SCH)],
        check=True, capture_output=True,
    )


def load_sourcing(errors: list[str]) -> dict[str, dict]:
    if not SOURCING.is_file():
        errors.append(f"sourcing declaration missing: {SOURCING.name}")
        return {}
    try:
        raw = json.loads(SOURCING.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"sourcing declaration is not valid JSON: {exc}")
        return {}
    declared = raw.get("classes", {})
    for klass in sorted(set(declared) - set(CLASS_RULES)):
        errors.append(
            f"sourcing declaration defines class {klass!r}, which this audit does not "
            f"know; the vocabulary is closed to {sorted(CLASS_RULES)}. A new way of "
            "buying a part needs a rule here saying what it may and may not cover, "
            "not just a name and a description")
    entries = raw.get("entries", {})
    for key, entry in sorted(entries.items()):
        klass = entry.get("class", "")
        rules = CLASS_RULES.get(klass)
        if rules is None:
            errors.append(f"sourcing entry {key!r} declares unknown class {klass!r}")
            continue
        if klass not in declared:
            errors.append(f"sourcing entry {key!r} uses class {klass!r}, which this "
                          "file never declares or explains")
        if not entry.get("rationale"):
            errors.append(f"sourcing entry {key!r} has no rationale")
        _, _, value = key.partition("|")
        if value == "*" and not rules["wildcard_value"]:
            errors.append(
                f"sourcing entry {key!r} uses a wildcard value for class {klass!r}; "
                "only a not-purchased land may claim a whole footprint")
        if rules["buys_to_value"]:
            hit = SPEC_TOKEN.search(value)
            if hit:
                errors.append(
                    f"sourcing entry {key!r} declares {klass!r}, which buys to value, "
                    f"but its value carries the specification {hit.group(0)!r}; a "
                    "specified part needs an exact MPN, not a family name")
    return entries


def resolve(components: list[Component], entries: dict[str, dict],
            errors: list[str]) -> tuple[dict[str, str], set[str]]:
    """Map each ref to its sourcing state.  Unresolved is an error, not a gap."""
    state: dict[str, str] = {}
    used: set[str] = set()
    for comp in sorted(components, key=lambda c: c.ref):
        if comp.ref.startswith("#"):          # power flags carry no footprint
            state[comp.ref] = "not-a-component"
            continue
        # Value-string DNP and the real dnp property must agree, or one of the
        # two lies to whoever reads the schematic.
        says_dnp = "DNP" in comp.value.upper()
        if says_dnp != comp.dnp:
            errors.append(
                f"{comp.ref} DNP mismatch: value {comp.value!r} says "
                f"{'DNP' if says_dnp else 'fitted'} but the dnp property says "
                f"{'DNP' if comp.dnp else 'fitted'}")
        if comp.dnp:
            state[comp.ref] = "dnp"
            continue
        if comp.mpn:
            state[comp.ref] = "mpn"
            continue
        entry = entries.get(comp.key) or entries.get(comp.wildcard_key)
        if entry is None:
            state[comp.ref] = "unsourced"
            errors.append(
                f"{comp.ref} is fitted but unbuyable: value {comp.value!r} "
                f"footprint {comp.footprint!r} has no MPN and no declared "
                "sourcing class")
            continue
        used.add(comp.key if comp.key in entries else comp.wildcard_key)
        state[comp.ref] = entry["class"]
    stale = sorted(set(entries) - used)
    for key in stale:
        errors.append(
            f"sourcing entry {key!r} matches no fitted component; a declaration "
            "that no longer describes the board must be removed, not carried")
    return state, used


def build_rows(components: list[Component],
               state: dict[str, str]) -> list[dict[str, object]]:
    groups: dict[tuple, list[Component]] = defaultdict(list)
    for comp in components:
        if state.get(comp.ref) == "not-a-component":
            continue
        groups[(comp.mpn, comp.value, comp.footprint,
                state.get(comp.ref, "unsourced"))].append(comp)
    rows = []
    for (mpn, value, footprint, sourcing), members in groups.items():
        refs = sorted(m.ref for m in members)
        rows.append({
            "mpn": mpn,
            "value": value,
            "footprint": footprint,
            "qty_per_board": 0 if sourcing == "dnp" else len(members),
            "fitted": "no" if sourcing == "dnp" else "yes",
            "sourcing": sourcing,
            "refs": " ".join(refs),
        })
    rows.sort(key=lambda r: (r["sourcing"] != "unsourced", r["sourcing"],
                             r["mpn"] or r["value"], r["refs"]))
    return rows


def diff_purchase_orders(rows: list[dict[str, object]], path: Path,
                         errors: list[str], notes: list[str]) -> None:
    try:
        snapshot = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"purchase-order snapshot unreadable ({exc}); "
                      "an unreadable snapshot cannot clear the order check")
        return
    lines = snapshot.get("lines", [])
    notes.append(f"purchase orders: {path.name} captured "
                 f"{snapshot.get('captured_utc', 'unknown')}, {len(lines)} lines")
    ordered: dict[str, float] = defaultdict(float)
    for line in lines:
        ordered[normalize(line.get("mpn"))] += float(line.get("quantity") or 0)

    required = {normalize(r["mpn"]): r for r in rows
                if r["mpn"] and r["fitted"] == "yes"}

    # The reciprocal of a missing part is an unrelated one bought in its place.
    # TPS7A2033PDBVR (LDO) was never ordered while TPS3840DL49DBVR (supervisor,
    # same SOT-23-5 DBV package) was.  String similarity cannot pair those, so
    # when a required MPN is absent entirely, also offer any ordered line that
    # shares its manufacturer-family prefix and sits on no BOM row.  Listing
    # every unmatched line instead is useless: these orders are shared with
    # other projects and that set runs to three figures.
    unrelated = [line for line in lines
                 if normalize(line.get("mpn")) not in required]
    for norm, row in sorted(required.items()):
        have = ordered.get(norm, 0.0)
        if have <= 0:
            match = difflib.get_close_matches(norm, list(ordered), n=1,
                                              cutoff=NEAR_MISS_RATIO)
            if match:
                actual = next(l["mpn"] for l in lines
                              if normalize(l.get("mpn")) == match[0])
                errors.append(
                    f"{row['refs']} needs {row['mpn']!r} but no order has it; "
                    f"the orders do contain the near-identical {actual!r} "
                    "-- confirm the substitution and write it back to the "
                    "schematic, or reorder")
                continue
            prefix = re.match(r"[A-Z]+", norm)
            family = sorted({
                f"{l['mpn']} on {l['order']}" for l in unrelated
                if prefix and len(prefix.group(0)) >= 2
                and normalize(l.get("mpn")).startswith(prefix.group(0))})
            hint = ("; the same orders carry unrelated " + prefix.group(0)
                    + "-family lines that are on no BOM row, in case one was "
                    "bought in its place: " + ", ".join(family)) if family else ""
            errors.append(
                f"{row['refs']} needs {row['mpn']!r} (qty {row['qty_per_board']}) "
                f"but it appears on no purchase order{hint}")
        elif have < float(row["qty_per_board"]):
            errors.append(
                f"{row['refs']} needs {row['mpn']!r} qty {row['qty_per_board']} "
                f"but only {have:g} was ordered")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purchase-orders", type=Path, default=ORDERS,
                        help=f"JSON snapshot of purchase-order lines to diff against "
                             f"(default {ORDERS.name}; required, see module docstring)")
    parser.add_argument("--no-export", action="store_true",
                        help="reuse the existing netlist instead of re-exporting")
    args = parser.parse_args()

    if not args.no_export:
        export_netlist()
    if not XML.is_file():
        raise SystemExit(f"netlist not found: {XML}")

    errors: list[str] = []
    notes: list[str] = []
    root = ET.parse(XML).getroot()
    components = [Component(c) for c in root.findall("./components/comp")]
    entries = load_sourcing(errors)
    state, _ = resolve(components, entries, errors)
    rows = build_rows(components, state)

    if not args.purchase_orders.is_file():
        errors.append(
            f"purchase-order snapshot missing: {args.purchase_orders}. The order check "
            "is not optional -- the parts this audit exists to catch went missing while "
            "the basket was transcribed into orders, so skipping it skips the step that "
            "failed. With nothing ordered yet, write a snapshot whose 'lines' is empty "
            "and read off everything outstanding")
    else:
        diff_purchase_orders(rows, args.purchase_orders, errors, notes)

    with BOM_CSV.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "mpn", "value", "footprint", "qty_per_board", "fitted",
            "sourcing", "refs"])
        writer.writeheader()
        writer.writerows(rows)

    tally: dict[str, int] = defaultdict(int)
    for ref, klass in state.items():
        tally[klass] += 1
    unsourced = sorted(r for r, k in state.items() if k == "unsourced")

    lines = [
        "O2 probe procurement (BOM) audit",
        f"schematic sha256: {sha256(SCH)}",
        f"components: {len(components)}; bom rows: {len(rows)}",
        "sourcing: " + ", ".join(f"{k}={tally[k]}" for k in sorted(tally)),
        f"unsourced fitted components: {len(unsourced)}"
        + (f" ({', '.join(unsourced)})" if unsourced else ""),
    ]
    lines.extend(notes)
    lines.append(f"result: {'FAIL' if errors else 'PASS'}")
    lines.extend(f"ERROR: {e}" for e in errors)
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
