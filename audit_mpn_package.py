#!/usr/bin/env python3
"""Package audit: prove every fitted MPN is a real part in the assigned package.

`audit_schematic.py` proves the design is wired correctly.  `audit_bom.py`
proves every fitted component resolves to something buyable.  Neither proves
that the MPN string names a part which actually exists in the package its
footprint draws.

Q1 carried `DMP3010L-7` on `Package_TO_SOT_SMD:SOT-23` through ERC, the
connectivity audit, an independent review and a fabrication release.  Diodes
DS35716 Rev. 5-2 p.1 shows the DMP3010L family as TO-252 (`DMP3010LK3-13`) and
DS32239 Rev. 13-3 p.1 as PowerDI5060-8 (`DMP3010LPS-13`); no SOT-23 variant
appears anywhere in the inspected primary and current-distributor corpus, and
`-7` is Diodes' SOT-23 tape suffix.  That is a bounded absence claim, not a
closed all-time catalogue.  The part actually purchased, `DMP3130L-7`
(DS31524 Rev. 7-3 p.1), *is* SOT-23.

A populated MPN field is a completeness fact.  It was read as a correctness
fact.  This audit supplies the missing half.

SCOPE, stated plainly so this gate is not mistaken for more than it is: it
compares the *package identity* a distributor ships the MPN in against the
identity the footprint declares -- family, pin count and body size.  It does
NOT compare land geometry.  L1 `SRN6028C-4R7M` passes here and its land is
still wrong: Bourns Rev. 04/23 p.1 recommends 2.0 x 6.5 mm pads at +/-2.25 mm
while `L_6.3x6.3_H3` draws 1.5 x 2.4 mm at +/-2.75 mm, covering 2.40 mm^2 of a
9.28 mm^2 terminal (25.9%).  Pad size, pad centres and pin-1 corner remain a
separate manual comparison against the datasheet drawing.  Passing this audit
is not evidence about pads.

Identity comparison, NOT token matching.  An earlier version split distributor
strings into words and accepted any intersection.  That admitted real wrong
packages: `"0201 (0603 Metric)"` yielded the word `0603`, so a 0201 chip
satisfied an imperial-0603 land (imperial 0201 *is* metric 0603), and a 4.40 mm
`8-TSSOP` satisfied a 3.00 mm VSSOP land.  Chip sizes are therefore matched as
an (imperial, metric) PAIR that must both agree, and leaded families are
matched on alias group plus pin count plus every body dimension the footprint
declares.  A dimension the footprint requires and the distributor does not
publish is `indeterminate`, never a pass.

Verdicts.  Every one except `ok` and `waived` fails the gate:

  ok             resolved, and the shipped identity matches the footprint
  mismatch       resolved, and the shipped identity contradicts the footprint
  unstated       resolved, but the distributor publishes no package at all
  indeterminate  resolved, but the distributor omits a dimension needed to decide
  unresolved     no distributor listing for this exact MPN
  unmapped       the footprint declares no expected identity here
  unverified     the probe could not answer
  waived         a human verified it against a cited datasheet (see below)

`mismatch` is never waivable: when the distributor states a package that
contradicts the footprint, the remedy is to fix the design or the map, not to
silence the finding.  `unmapped` is not waivable either, because with no
expected identity there is nothing for a waiver to be checked against; extend
`FOOTPRINT_PACKAGES` instead.  The distinction is evidence that CONTRADICTS
versus evidence that is ABSENT: a waiver may supply what is missing, never
overrule what is stated.

`unresolved`, `unverified`, `unstated` and `indeterminate` may be waived in `sourcing.json` under
`package_waivers`, keyed exactly `"<ref>|<mpn>|<footprint>"`.  A waiver must
record the `package` the human read, a `rationale`, and a `source` -- and that
declared package IS PARSED AND COMPARED against the footprint's expected
identity exactly as a distributor answer would be.  A waiver substitutes the
*source* of the evidence, never the comparison; a waiver naming a package the
footprint does not accept fails.  Because the key binds ref, MPN and footprint
together, changing any of them retires the waiver and re-opens the finding.

Provenance.  The netlist is always exported fresh to a temporary file and that
exact file is parsed and hashed; there is no flag to audit a netlist unbound
from the schematic it claims to describe.  Both hashes are reported.

Emptiness is not cleanliness.  Zero fitted MPN-bearing components is an error,
not a pass: a broken export or parser must not look like a clean board.

Probe failure is never silence.  If the distributor probe cannot answer, every
component becomes `unverified` and the gate fails.  A positive control runs
before the sweep, so an empty result set is distinguished from a working probe
that found nothing.  The control is one instant and one MPN: it cannot detect a
probe that degrades mid-sweep into confident wrong answers, so cached entries
carry their raw source fields, locale, endpoint and timestamp, and expire.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCH = ROOT / "o2-probe.kicad_sch"
SOURCING = ROOT / "sourcing.json"
CACHE = ROOT / "mpn-package-cache.json"
REPORT = ROOT / "mpn-package-audit.rpt"
KICAD = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

CLIENT_ROOT = Path(os.environ.get("DK_CLIENT_ROOT", "/Users/fab/dk-import"))
CRED_FILE = os.environ.get("DK_CRED_FILE", "data/.digikey-api3")
REQUEST_DELAY_S = 0.3
CACHE_TTL_S = 30 * 24 * 3600            # a "no such part" answer must not be forever

CONTROL_MPN = "SMBJ15A-13-F"
CONTROL_PACKAGE = "SMB"
WIDTH_TOLERANCE_MM = 0.25


# --------------------------------------------------------------------------- identities

@dataclass(frozen=True)
class Chip:
    """Two-terminal chip size.  Imperial AND metric must agree.

    Imperial 0201 is metric 0603 and imperial 0603 is metric 1608, so matching
    on either code alone lets a 0201 part satisfy a 0603 land.
    """
    imperial: str
    metric: str

    def accepts(self, other: "Identity") -> bool:
        return isinstance(other, Chip) and (self.imperial, self.metric) == (other.imperial, other.metric)

    def __str__(self) -> str:
        return f"{self.imperial}/{self.metric}metric"


@dataclass(frozen=True)
class Leaded:
    """Pin-count-prefixed family, e.g. 8-SOIC, 48-LQFP, 16-WQFN.

    `group` collapses vendor spellings of one physical family (VSSOP/MSOP/TSSOP
    are all names for a shrink small-outline body) so the DIMENSIONS, not the
    marketing name, do the discriminating.
    """
    group: str
    pins: int
    width_mm: float | None = None
    body: tuple[float, float] | None = None

    def accepts(self, other: "Identity") -> bool:
        if not isinstance(other, Leaded):
            return False
        if (self.group, self.pins) != (other.group, other.pins):
            return False
        # Every dimension this footprint declares must be present and agree.
        if self.width_mm is not None:
            if other.width_mm is None:
                return False
            if abs(self.width_mm - other.width_mm) > WIDTH_TOLERANCE_MM:
                return False
        if self.body is not None:
            if other.body is None:
                return False
            if any(abs(a - b) > WIDTH_TOLERANCE_MM for a, b in zip(sorted(self.body), sorted(other.body))):
                return False
        return True

    def requires_dimension(self) -> bool:
        return self.width_mm is not None or self.body is not None

    def __str__(self) -> str:
        bits = [f"{self.pins}-{self.group}"]
        if self.width_mm is not None:
            bits.append(f"{self.width_mm:.2f}mm wide")
        if self.body is not None:
            bits.append(f"{self.body[0]}x{self.body[1]}")
        return " ".join(bits)


@dataclass(frozen=True)
class Named:
    """A package name that already encodes pin count and body: SOD-123, SMB,
    SOT-23-3, TSOT-23-6, TO-252-3, PowerDI5060-8.  Matched exactly, so
    SOT-23-3, SOT-23-5 and SOT-23-6 can never satisfy each other."""
    name: str

    def accepts(self, other: "Identity") -> bool:
        return isinstance(other, Named) and self.name == other.name

    def __str__(self) -> str:
        return self.name


Identity = Chip | Leaded | Named

# Vendor spellings that denote one physical family.  Membership here means the
# names are interchangeable ONLY once pin count and body dimensions agree.
FAMILY_GROUPS = {
    "VSSOP": "SSOP", "MSOP": "SSOP", "TSSOP": "SSOP", "SSOP": "SSOP",
    "SOIC": "SOIC", "SO": "SOIC",
    "WQFN": "QFN", "WFQFN": "QFN", "QFN": "QFN", "VQFN": "QFN", "UQFN": "QFN",
    "WSON": "SON", "WFDFN": "SON", "SON": "SON", "DFN": "SON", "WDFN": "SON",
    "LQFP": "QFP", "TQFP": "QFP", "QFP": "QFP",
}

CHIP_RE = re.compile(r"\b(\d{4})\s*\(\s*(\d{4})\s*metric\s*\)", re.IGNORECASE)
LEADED_RE = re.compile(r"\b(\d{1,3})\s*-\s*([A-Za-z]{2,6})\b")
WIDTH_RE = re.compile(r"([\d.]+)\s*mm\s*width", re.IGNORECASE)
BODY_RE = re.compile(r"\(\s*([\d.]+)\s*x\s*([\d.]+)\s*\)")


def parse_identities(*fields: str) -> set[Identity]:
    """Parse distributor package strings into structured identities.

    Dimensions stated anywhere in a field apply to every family named in that
    field: DigiKey writes `'8-TSSOP, 8-MSOP (0.118", 3.00mm Width)'` meaning one
    part that is both, 3.00 mm wide.
    """
    found: set[Identity] = set()
    for field in fields:
        text = str(field or "").strip()
        if not text or text == "-":
            continue
        width = WIDTH_RE.search(text)
        width_mm = float(width.group(1)) if width else None
        body = BODY_RE.search(text)
        body_mm = (float(body.group(1)), float(body.group(2))) if body else None

        for chip in CHIP_RE.finditer(text):
            found.add(Chip(chip.group(1), chip.group(2)))
        for lead in LEADED_RE.finditer(text):
            family = lead.group(2).upper()
            if family not in FAMILY_GROUPS:
                continue
            found.add(Leaded(FAMILY_GROUPS[family], int(lead.group(1)), width_mm, body_mm))

        # Whatever is left, comma-separated and outside parentheses, is a name.
        remainder = re.sub(r"\([^)]*\)", " ", text)
        for piece in re.split(r"[,;]", remainder):
            piece = piece.strip().rstrip(".")
            if not piece or CHIP_RE.search(piece) or LEADED_RE.search(piece):
                continue
            if re.fullmatch(r"[\d.\"']+|metric|variant|thin|exposed pad|concave", piece, re.IGNORECASE):
                continue
            found.add(Named(re.sub(r"\s+", "", piece).upper()))
    return found


# Footprint -> the identities that may legitimately ship in it.  Each entry was
# read from a live distributor record for a part on this board or from the
# part's own drawing; a map built from memory fails open.
FOOTPRINT_PACKAGES: dict[str, set[Identity]] = {
    "Diode_SMD:D_SMA": {Named("SMA"), Named("DO-214AC")},
    "Diode_SMD:D_SMB": {Named("SMB"), Named("DO-214AA")},
    "Diode_SMD:D_SOD-123": {Named("SOD-123")},
    "Package_TO_SOT_SMD:SOT-23": {Named("SOT-23-3"), Named("TO-236-3"), Named("SC-59"), Named("3-SMD")},
    "Package_TO_SOT_SMD:SOT-23-5": {Named("SOT-23-5"), Named("SC-74A"), Named("SOT-753")},
    "Package_TO_SOT_SMD:TSOT-23-6": {Named("TSOT-23-6"), Named("SOT-23-6")},
    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm": {Leaded("SOIC", 8, width_mm=3.90)},
    "Package_SO:VSSOP-8_3x3mm_P0.65mm": {Leaded("SSOP", 8, width_mm=3.00)},
    "Package_SON:WSON-14-1EP_4.0x4.0mm_P0.5mm_EP2.6x2.6mm": {Leaded("SON", 14, body=(4.0, 4.0))},
    "Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm":
        {Leaded("QFN", 16, body=(3.0, 3.0))},
    "Package_QFP:LQFP-48_7x7mm_P0.5mm": {Leaded("QFP", 48, body=(7.0, 7.0))},
    "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad":
        {Leaded("SON", 4, body=(1.5, 1.5))},
    "tmp117-probe:TMP117_WSON-6-1EP_2x2mm_TI": {Leaded("SON", 6, body=(2.0, 2.0))},
    # Bourns describes the SRN6028C body as 2424 imperial / 6060 metric and its
    # supplier package as the series code 6028.
    "Inductor_SMD:L_6.3x6.3_H3": {Chip("2424", "6060"), Named("6028")},
    "Resistor_SMD:R_0603_1608Metric": {Chip("0603", "1608")},
    "Resistor_SMD:R_0805_2012Metric": {Chip("0805", "2012")},
    "Resistor_SMD:R_2512_6332Metric": {Chip("2512", "6332")},
    "Capacitor_SMD:C_0402_1005Metric": {Chip("0402", "1005")},
    "Capacitor_SMD:C_0603_1608Metric": {Chip("0603", "1608")},
    "Capacitor_SMD:C_0805_2012Metric": {Chip("0805", "2012")},
    "Capacitor_SMD:C_1206_3216Metric": {Chip("1206", "3216")},
    "o2-probe:PTC_1206_3216Metric": {Chip("1206", "3216")},
    # No distributor publishes a package parametric for these two.  The land is
    # part-specific, so the expected identity is the part's own body name and a
    # waiver must declare exactly it, sourced from the drawing.
    "Potentiometer_SMD:Potentiometer_Bourns_3224W_Vertical": {Named("3224W")},
    "o2-probe:SGX-OX-ROHS-Mini_ISS2": {Named("SGX-OX-ROHS-MINI")},
}

FAIL_STATES = {"mismatch", "unstated", "indeterminate", "unresolved", "unmapped", "unverified"}
WAIVABLE = {"unresolved", "unverified", "unstated", "indeterminate"}


class ProbeUnavailable(RuntimeError):
    """The distributor could not be asked.  Never a verdict about a part."""


def normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint() -> str:
    """Hash this module's source and its map together.

    Fingerprint the code that derives the value, not only its input: editing
    FOOTPRINT_PACKAGES must invalidate every cached verdict it could change, or
    a loosened map silently keeps its old passes.
    """
    digest = hashlib.sha256()
    digest.update(Path(__file__).read_bytes())
    digest.update(repr(sorted((k, sorted(map(str, v))) for k, v in FOOTPRINT_PACKAGES.items())).encode())
    return digest.hexdigest()[:16]


class Component:
    """Mirrors audit_bom.Component so the two audits agree on what is fitted."""

    __slots__ = ("ref", "value", "footprint", "mpn", "manufacturer", "dnp")

    def __init__(self, comp: ET.Element) -> None:
        self.ref = comp.attrib.get("ref", "")
        self.value = (comp.findtext("value") or "").strip()
        self.footprint = (comp.findtext("footprint") or "").strip()
        fields = comp.find("fields")
        table = {f.attrib.get("name"): (f.text or "").strip()
                 for f in (list(fields) if fields is not None else [])}
        self.mpn = table.get("MPN", "")
        self.manufacturer = table.get("Manufacturer", "")
        self.dnp = any(p.attrib.get("name") == "dnp" for p in comp.findall("property"))

    @property
    def waiver_key(self) -> str:
        return f"{self.ref}|{self.mpn}|{self.footprint}"


class DigiKeyProbe:
    """Exact-MPN package lookup.  Raises rather than guessing."""

    def __init__(self) -> None:
        try:
            sys.path.insert(0, str(CLIENT_ROOT))
            from order_sync.digikey import DigiKeyApp, SEARCH_URL, LOCALE
        except Exception as exc:                                # noqa: BLE001
            raise ProbeUnavailable(f"distributor client not importable: {exc}") from exc
        try:
            self._app = DigiKeyApp(CRED_FILE)
            self._token = self._app.search_token()
        except Exception as exc:                                # noqa: BLE001
            raise ProbeUnavailable(f"distributor authentication failed: {exc}") from exc
        self._url = SEARCH_URL
        self._locale = LOCALE
        self.calls = 0

    @property
    def context(self) -> dict:
        """Retrieval context stored beside every cached answer."""
        return {"endpoint": self._url, "locale": dict(self._locale), "client": "digikey-v4"}

    def _post(self, keywords: str, limit: int) -> dict:
        body = json.dumps({"Keywords": keywords, "Limit": limit}).encode()
        headers = {"Authorization": f"Bearer {self._token}",
                   "X-DIGIKEY-Client-Id": self._app.client_id,
                   "Content-Type": "application/json", **self._locale}
        request = urllib.request.Request(self._url, data=body, headers=headers, method="POST")
        try:
            self.calls += 1
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ProbeUnavailable(f"{keywords}: distributor returned HTTP {exc.code}") from exc
        except Exception as exc:                                # noqa: BLE001
            raise ProbeUnavailable(f"{keywords}: distributor request failed: {exc}") from exc

    def lookup(self, mpn: str) -> dict:
        """Return the raw evidence for an exact MPN match.

        Raw package fields are kept, not just the parsed result, so a cached
        answer can be re-parsed by a later version of this module and audited
        by a human.  Transport, auth and quota failures raise: 'I could not
        ask' is not 'there is nothing'.
        """
        payload = self._post(mpn, 10)
        wanted = normalize(mpn)
        products = payload.get("Products") or []
        exact = next((p for p in products
                      if normalize(p.get("ManufacturerProductNumber")) == wanted), None)
        if exact is None:
            # Near misses are reported, never accepted: searching a bad MPN
            # returns its plausible relatives, and treating one as the answer is
            # how a DPAK part gets blessed for a SOT-23 land.
            return {"found": False,
                    "near": [p.get("ManufacturerProductNumber", "?") for p in products[:5]]}
        parameters = {x.get("ParameterText"): x.get("ValueText")
                      for x in (exact.get("Parameters") or [])}
        return {"found": True,
                "manufacturer": (exact.get("Manufacturer") or {}).get("Name", ""),
                "case": parameters.get("Package / Case", ""),
                "supplier_package": parameters.get("Supplier Device Package", "")}

    def family_hint(self, mpn: str) -> list[str]:
        """Describe the family an unresolvable MPN belongs to.

        `DMP3010L-7` returns nothing at all, which reads as 'unknown' when the
        truth is specific: the family exists and ships only as TO-252 and
        PowerDI5060-8.  Naming the packages the family *does* come in turns a
        shrug into the diagnosis.  Only called for an already failing part.
        """
        base = mpn
        for _ in range(2):
            trimmed = re.sub(r"[-/][A-Za-z0-9]{1,4}$", "", base)
            if trimmed == base or len(trimmed) < 4:
                break
            base = trimmed
            try:
                payload = self._post(base, 6)
            except ProbeUnavailable:
                return []               # a hint is a courtesy, never a verdict
            hints = []
            for product in (payload.get("Products") or []):
                parameters = {x.get("ParameterText"): x.get("ValueText")
                              for x in (product.get("Parameters") or [])}
                package = (parameters.get("Supplier Device Package")
                           or parameters.get("Package / Case") or "?")
                hints.append(f"{product.get('ManufacturerProductNumber', '?')} ({package})")
            if hints:
                return hints
        return []


# --------------------------------------------------------------------------- cache

def load_cache() -> dict[str, dict]:
    if not CACHE.is_file():
        return {}
    try:
        raw = json.loads(CACHE.read_text())
    except json.JSONDecodeError:
        return {}
    if raw.get("fingerprint") != fingerprint():
        return {}
    now = time.time()
    return {k: v for k, v in raw.get("entries", {}).items()
            if now - float(v.get("fetched_at", 0)) < CACHE_TTL_S}


def save_cache(entries: dict[str, dict]) -> None:
    CACHE.write_text(json.dumps(
        {"fingerprint": fingerprint(), "entries": entries}, indent=2, sort_keys=True) + "\n")


def load_waivers(errors: list[str]) -> dict[str, dict]:
    if not SOURCING.is_file():
        return {}
    try:
        raw = json.loads(SOURCING.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"sourcing declaration is not valid JSON: {exc}")
        return {}
    waivers = raw.get("package_waivers", {})
    for key, waiver in sorted(waivers.items()):
        for field in ("package", "rationale", "source"):
            if not waiver.get(field):
                errors.append(
                    f"package waiver {key!r} has no {field!r}; a waiver without the "
                    "package a human read, why, and where they read it is a mute "
                    "button, not a verification")
    return waivers


# --------------------------------------------------------------------------- verdicts

def compare(accepted: set[Identity], actual: set[Identity]) -> tuple[bool, bool]:
    """Return (matched, blocked_on_missing_dimension)."""
    if any(exp.accepts(act) for exp in accepted for act in actual):
        return True, False
    blocked = any(
        isinstance(exp, Leaded) and exp.requires_dimension()
        and isinstance(act, Leaded) and (exp.group, exp.pins) == (act.group, act.pins)
        for exp in accepted for act in actual)
    return False, blocked


def classify(comp: Component, probe: DigiKeyProbe | None,
             cache: dict[str, dict], probe_error: str) -> dict:
    """Decide one component's verdict.  Never returns ok on absent evidence."""
    accepted = FOOTPRINT_PACKAGES.get(comp.footprint)
    if accepted is None:
        return {"verdict": "unmapped", "detail":
                f"footprint {comp.footprint!r} declares no expected package identity; "
                "extend FOOTPRINT_PACKAGES (this is not waivable -- a waiver would "
                "have nothing to be checked against)"}
    if probe is None:
        return {"verdict": "unverified", "detail": probe_error}

    key = normalize(comp.mpn)
    hit = cache.get(key)
    cached = hit is not None
    if not cached:
        try:
            hit = probe.lookup(comp.mpn)
        except ProbeUnavailable as exc:
            # A failed probe must never persist as a clean verdict: return
            # without writing the cache.
            return {"verdict": "unverified", "detail": str(exc)}
        hit |= {"fetched_at": time.time(), **probe.context}
        cache[key] = hit
        time.sleep(REQUEST_DELAY_S)

    if not hit.get("found"):
        if "family" not in hit and probe is not None:
            hit["family"] = probe.family_hint(comp.mpn)
        evidence = ", ".join(hit.get("family") or hit.get("near") or []) or "nothing"
        return {"verdict": "unresolved", "cached": cached, "detail":
                f"no distributor listing for exact MPN {comp.mpn!r}; "
                f"the family ships as: {evidence}"}

    actual = parse_identities(hit.get("case", ""), hit.get("supplier_package", ""))
    manufacturer = hit.get("manufacturer", "")
    if comp.manufacturer and normalize(comp.manufacturer) not in normalize(manufacturer):
        return {"verdict": "mismatch", "cached": cached, "manufacturer": manufacturer,
                "detail": f"{comp.mpn!r} is listed by {manufacturer!r} but the schematic "
                          f"declares manufacturer {comp.manufacturer!r}"}
    if not actual:
        # The distributor answered and published no package field.  That is
        # absent evidence, not contradicting evidence, so a human datasheet
        # reading may supply it through a waiver.
        return {"verdict": "unstated", "cached": cached, "manufacturer": manufacturer,
                "detail": f"{comp.mpn!r} is listed but the distributor publishes no package "
                          f"parametric; {comp.footprint!r} needs "
                          f"{', '.join(sorted(map(str, accepted)))} -- verify against the "
                          "part drawing and record a package_waiver"}
    matched, blocked = compare(accepted, actual)
    if matched:
        return {"verdict": "ok", "cached": cached, "manufacturer": manufacturer,
                "detail": ", ".join(sorted(map(str, actual)))}
    if blocked:
        return {"verdict": "indeterminate", "cached": cached, "manufacturer": manufacturer,
                "detail": f"{comp.mpn!r} is the right family and pin count but the "
                          f"distributor publishes no body dimension to separate it from a "
                          f"different body in the same family; footprint needs "
                          f"{', '.join(sorted(map(str, accepted)))}"}
    return {"verdict": "mismatch", "cached": cached, "manufacturer": manufacturer,
            "detail": f"{comp.mpn!r} ships as {', '.join(sorted(map(str, actual))) or 'no stated package'} "
                      f"but {comp.footprint!r} needs {', '.join(sorted(map(str, accepted)))}"}


def export_netlist(destination: Path) -> None:
    subprocess.run(
        [KICAD, "sch", "export", "netlist", "--format", "kicadxml",
         "-o", str(destination), str(SCH)],
        check=True, capture_output=True,
    )


def audit(components: list[Component], errors: list[str], notes: list[str],
          refresh: bool, require_manufacturer: bool) -> list[dict]:
    waivers = load_waivers(errors)
    cache = {} if refresh else load_cache()

    probe: DigiKeyProbe | None = None
    probe_error = ""
    try:
        probe = DigiKeyProbe()
        control = probe.lookup(CONTROL_MPN)
        identities = parse_identities(control.get("case", ""), control.get("supplier_package", ""))
        if Named(CONTROL_PACKAGE) not in identities:
            raise ProbeUnavailable(
                f"positive control {CONTROL_MPN} parsed as "
                f"{sorted(map(str, identities)) or 'nothing'}, expected {CONTROL_PACKAGE}")
    except ProbeUnavailable as exc:
        probe, probe_error = None, str(exc)
        errors.append(f"distributor probe unusable: {probe_error}")

    fitted = [c for c in components
              if c.mpn and not c.dnp and not c.ref.startswith("#")]
    if not fitted:
        errors.append(
            "no fitted component carries an MPN; an empty audit population is a "
            "broken export or parser, not a clean board")

    findings: list[dict] = []
    used: set[str] = set()
    unbound: list[str] = []

    for comp in sorted(fitted, key=lambda c: c.ref):
        result = classify(comp, probe, cache, probe_error)
        verdict = result["verdict"]
        if not comp.manufacturer:
            unbound.append(comp.ref)
        waiver = waivers.get(comp.waiver_key)
        if waiver:
            used.add(comp.waiver_key)
            if verdict in WAIVABLE:
                # The waiver replaces the SOURCE of the package evidence, never
                # the comparison: its declared package is parsed and checked
                # against the footprint exactly as a distributor answer is.
                declared = parse_identities(waiver["package"])
                matched, _ = compare(FOOTPRINT_PACKAGES[comp.footprint], declared)
                if matched:
                    result = {"verdict": "waived", "detail":
                              f"{verdict} waived: package {waiver['package']!r} verified "
                              f"against {waiver['source']} -- {waiver['rationale']}"}
                else:
                    errors.append(
                        f"{comp.ref} waiver declares package {waiver['package']!r}, which "
                        f"parses as {sorted(map(str, declared)) or 'nothing recognisable'} "
                        f"and does not satisfy {comp.footprint!r}; a waiver substitutes the "
                        "source of the evidence, not the comparison")
            elif verdict in FAIL_STATES:
                errors.append(
                    f"{comp.ref} carries a package waiver but its verdict is {verdict!r}, "
                    f"which is not waivable; fix the design, the map, or the evidence. "
                    f"{result['detail']}")
        findings.append({"ref": comp.ref, "mpn": comp.mpn,
                         "footprint": comp.footprint, **result})

    for key in sorted(set(waivers) - used):
        errors.append(
            f"package waiver {key!r} matches no fitted component; the ref, MPN or "
            "footprint it was written about has changed, so the verification behind "
            "it no longer applies and must be redone")

    for finding in findings:
        if finding["verdict"] in FAIL_STATES:
            errors.append(f"{finding['ref']} {finding['verdict']}: {finding['detail']}")

    if unbound:
        message = (f"{len(unbound)} components declare no Manufacturer field, so an "
                   f"MPN collision between two manufacturers cannot be detected: "
                   f"{', '.join(unbound)}")
        (errors if require_manufacturer else notes).append(
            message + ("" if require_manufacturer else " (advisory; --require-manufacturer to enforce)"))

    if probe is not None:
        cached = sum(1 for f in findings if f.get("cached"))
        notes.append(f"probe: live, {probe.calls} distributor calls, "
                     f"{cached}/{len(findings)} verdicts from cache "
                     f"(TTL {CACHE_TTL_S // 86400} days)")
        save_cache(cache)
        # A result that condemns everything deserves the same suspicion as one
        # that finds nothing.
        bad = sum(1 for f in findings if f["verdict"] in FAIL_STATES)
        if findings and bad > len(findings) * 0.5:
            notes.append(
                f"SUSPECT: {bad} of {len(findings)} components failed. Confirm the map "
                "and probe before believing this is the board's fault")
    else:
        notes.append("probe: UNUSABLE -- every verdict is unverified, not clean")
    notes.append("scope: package identity only; land geometry (pad size, centres, "
                 "pin-1) is NOT checked here -- see FOOTPRINTS.md")
    return findings


def selftest() -> int:
    """Known-bad calibration.

    A guard nobody has watched fail is a guard nobody has tested.  These
    fixtures are the historical defect and the collisions an independent review
    found in the previous token-matching implementation.
    """
    offline = [
        ("0201 chip may not satisfy an 0603 land",
         lambda: not compare(FOOTPRINT_PACKAGES["Capacitor_SMD:C_0603_1608Metric"],
                             parse_identities("0201 (0603 Metric)"))[0]),
        ("0603 chip satisfies an 0603 land",
         lambda: compare(FOOTPRINT_PACKAGES["Capacitor_SMD:C_0603_1608Metric"],
                         parse_identities("0603 (1608 Metric)"))[0]),
        ("4.40mm 8-TSSOP may not satisfy a 3.00mm VSSOP land",
         lambda: not compare(FOOTPRINT_PACKAGES["Package_SO:VSSOP-8_3x3mm_P0.65mm"],
                             parse_identities('8-TSSOP (0.173", 4.40mm Width)'))[0]),
        ("3.00mm 8-TSSOP/MSOP satisfies a VSSOP-8 land",
         lambda: compare(FOOTPRINT_PACKAGES["Package_SO:VSSOP-8_3x3mm_P0.65mm"],
                         parse_identities('8-TSSOP, 8-MSOP (0.118", 3.00mm Width)'))[0]),
        ("SOT-23-5 may not satisfy a three-pin SOT-23 land",
         lambda: not compare(FOOTPRINT_PACKAGES["Package_TO_SOT_SMD:SOT-23"],
                             parse_identities("SC-74A, SOT-753"))[0]),
        ("SOT-23-3 satisfies a three-pin SOT-23 land",
         lambda: compare(FOOTPRINT_PACKAGES["Package_TO_SOT_SMD:SOT-23"],
                         parse_identities("TO-236-3, SC-59, SOT-23-3"))[0]),
        ("a family match with no published body dimension is blocked, not passed",
         lambda: compare(FOOTPRINT_PACKAGES["Package_QFP:LQFP-48_7x7mm_P0.5mm"],
                         parse_identities("48-LQFP")) == (False, True)),
    ]
    failures = 0
    for name, check in offline:
        ok = bool(check())
        failures += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    live = [
        ("DMP3130L-7", "Package_TO_SOT_SMD:SOT-23", "ok",
         "the part actually bought, in the land the board draws"),
        ("DMP3130L-7", "Package_TO_SOT_SMD:TSOT-23-6", "mismatch",
         "real part, wrong land: existence alone must not pass"),
        ("DMP3010L-7", "Package_TO_SOT_SMD:SOT-23", "unresolved",
         "the Rev A defect: an MPN naming no orderable part"),
    ]
    try:
        probe = DigiKeyProbe()
    except ProbeUnavailable as exc:
        print(f"  live fixtures INCONCLUSIVE: {exc}")
        print(f"selftest: {'FAIL' if failures else 'INCONCLUSIVE'}")
        return 2                       # never 0: an unrun test is not a pass
    cache: dict[str, dict] = {}
    for mpn, footprint, expected, why in live:
        comp = ET.fromstring(
            f'<comp ref="X1"><value>fixture</value><footprint>{footprint}</footprint>'
            f'<fields><field name="MPN">{mpn}</field></fields></comp>')
        got = classify(Component(comp), probe, cache, "")["verdict"]
        ok = got == expected
        failures += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {mpn} on {footprint}: "
              f"expected {expected}, got {got}  ({why})")
    print(f"selftest: {'PASS' if not failures else f'FAIL ({failures})'}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MPN <-> package audit")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore cached verdicts and re-query the distributor")
    parser.add_argument("--require-manufacturer", action="store_true",
                        help="fail on components with no Manufacturer field")
    parser.add_argument("--selftest", action="store_true",
                        help="run known-bad calibration fixtures and exit")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    started = time.monotonic()
    errors: list[str] = []
    notes: list[str] = []

    # Always export fresh and audit that exact file.  There is deliberately no
    # flag to audit a netlist unbound from the schematic the report attests to.
    with tempfile.TemporaryDirectory() as scratch:
        netlist = Path(scratch) / "netlist.xml"
        export_netlist(netlist)
        netlist_hash = sha256(netlist)
        root = ET.parse(netlist).getroot()
        components = [Component(c) for c in root.findall("./components/comp")]

    findings = audit(components, errors, notes, args.refresh, args.require_manufacturer)

    tally: dict[str, int] = {}
    for finding in findings:
        tally[finding["verdict"]] = tally.get(finding["verdict"], 0) + 1

    lines = [
        "O2 probe MPN/package audit",
        f"run: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"schematic sha256: {sha256(SCH)}",
        f"netlist audited sha256: {netlist_hash} (exported from that schematic in this run)",
        f"map fingerprint: {fingerprint()}",
        f"components with an MPN and fitted: {len(findings)}",
        "verdicts: " + (", ".join(f"{k}={tally[k]}" for k in sorted(tally)) or "none"),
    ]
    lines.extend(notes)
    lines.extend(f"  {f['ref']:5} {f['verdict']:13} {f['mpn']:22} {f['detail']}"
                 for f in findings)
    lines.append(f"elapsed: {time.monotonic() - started:.1f}s")
    lines.append(f"result: {'FAIL' if errors else 'PASS'}")
    lines.extend(f"ERROR: {e}" for e in errors)
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
