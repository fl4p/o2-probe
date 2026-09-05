#!/usr/bin/env python3
"""Flatten an OrcaSlicer BBL profile's `inherits` chain into one self-contained file.

WHY: the OrcaSlicer CLI does NOT walk `inherits`. Hand it
`Bambu ASA @BBL X1C 0.4 nozzle.json` and it sees a file with no `filament_type`,
no plate temperatures and no fan speeds -- every one of those lives in
`Bambu ASA @base`. The measured consequence (kb: orcaslicer-cli-does-not-resolve-
filament-inherits) is a plate sliced as PLA at a 45 C bed while its own G-code
header still names the ASA preset. A preset NAME proves nothing; only resolved
values do.

So: resolve the chain here, write the result out, and let slice-check.sh assert
the resolved values in the emitted G-code.

    flatten_profile.py <filament|process> "<preset name>" [-o out.json] [-s k=v ...]
"""
import argparse, json, os, sys

BBL = os.environ.get(
    "BBL", "/Applications/OrcaSlicer.app/Contents/Resources/profiles/BBL")


def find(kind, name):
    """A preset is addressed by its `name` field, which need not match the
    filename -- so search on the field, never glob the filename."""
    hits = []
    for root, _, files in os.walk(os.path.join(BBL, kind)):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p) as f:
                    d = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if d.get("name") == name:
                hits.append((p, d))
    if not hits:
        sys.exit(f"no {kind} preset named {name!r} under {BBL}")
    if len(hits) > 1:
        sys.exit(f"{len(hits)} presets named {name!r}: " +
                 ", ".join(p for p, _ in hits))
    return hits[0]


def flatten(kind, name, seen=()):
    if name in seen:
        sys.exit(f"inherits cycle: {' -> '.join(seen)} -> {name}")
    path, d = find(kind, name)
    parent = d.get("inherits")
    base = flatten(kind, parent, seen + (name,)) if parent else {}
    base.update({k: v for k, v in d.items()
                 if k not in ("inherits", "from", "setting_id",
                              "instantiation", "description")})
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["filament", "process", "machine"])
    ap.add_argument("name")
    ap.add_argument("-o", "--out")
    ap.add_argument("-s", "--set", action="append", default=[], metavar="K=V",
                    help="override a resolved key; V is JSON, else a string")
    a = ap.parse_args()

    d = flatten(a.kind, a.name)
    for kv in a.set:
        k, _, v = kv.partition("=")
        try:
            d[k] = json.loads(v)
        except json.JSONDecodeError:
            d[k] = v
    d["from"] = "User"
    d["instantiation"] = "true"

    out = a.out or "-"
    text = json.dumps(d, indent=1, sort_keys=True)
    if out == "-":
        print(text)
    else:
        with open(out, "w") as f:
            f.write(text + "\n")
        print(f"{out}: {len(d)} resolved keys from the {a.name!r} chain",
              file=sys.stderr)


if __name__ == "__main__":
    main()
