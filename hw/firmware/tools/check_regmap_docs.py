#!/usr/bin/env python3
"""Fail if the prose copies of the register map disagree with regmap.h.

This exists because the copies have already drifted three times in one day:
the diagnostic block grew from 16 to 18 registers, the configuration block
moved from 0x0020 to 0x0030, and a downstream copy of the fault-invalidation
rule kept publishing a value the firmware had decided was untrustworthy.

The map is a wire contract with a Dragino node and a ChirpStack codec that
cannot see this header. A stale prose copy is not a documentation nit: it is
how someone configures `AT+COMMAND` against addresses that moved, and reads a
diagnostic register that is now something else.

`src/regmap.h` is the source of truth, and `src/update.h` for the two blocks
the firmware updater owns - they live there because the same engine answers
them from the bootloader, which links none of the register map. Everything
here is derived from those two headers.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
REGMAP = os.path.join(FW, "src", "regmap.h")
UPDATE = os.path.join(FW, "src", "update.h")

# Prose copies, relative to the firmware directory.
DOCS = ["FIRMWARE.md", os.path.join("..", "DESIGN.md")]


BLOCKS = ("PRIMARY", "DIAG", "CONFIG", "UPDATE", "UPDDATA")


def parse_regmap(text):
    """Block bases/counts and the primary block's register names, from the header."""
    out = {}
    for name in BLOCKS:
        for kind in ("BASE", "COUNT"):
            m = re.search(r"#define\s+O2P_REG_%s_%s\s+(0x[0-9A-Fa-f]+|\d+)u?"
                          % (name, kind), text)
            if not m:
                raise SystemExit("!! regmap.h has no O2P_REG_%s_%s" % (name, kind))
            out["%s_%s" % (name, kind)] = int(m.group(1), 0)
    primary = {}
    every = {}
    for m in re.finditer(r"O2P_REG_(\w+)\s*=\s*(0x[0-9A-Fa-f]+)u", text):
        addr = int(m.group(2), 0)
        every[m.group(1)] = addr
        if out["PRIMARY_BASE"] <= addr < out["PRIMARY_BASE"] + out["PRIMARY_COUNT"]:
            primary[addr] = m.group(1)
    out["primary"] = primary
    out["every"] = every
    return out


def main():
    rm = parse_regmap(open(REGMAP, encoding="utf-8").read() +
                      open(UPDATE, encoding="utf-8").read())
    base, count = rm["PRIMARY_BASE"], rm["PRIMARY_COUNT"]

    problems = []
    for rel in DOCS:
        path = os.path.join(FW, rel)
        if not os.path.exists(path):
            problems.append("%s: missing" % rel)
            continue
        doc = open(path, encoding="utf-8").read()

        # Base address AND size must appear ON THE SAME LINE. Searching the
        # whole document for each independently is too weak to be worth
        # running: this file's own prose mentions every address at least once
        # while explaining the drift, so a heading that moved to the wrong
        # block would still have found its number somewhere else and passed.
        lines = doc.splitlines()
        for name in BLOCKS:
            addr = "0x%04X" % rm["%s_BASE" % name]
            n = rm["%s_COUNT" % name]
            want = re.compile(r"(?i)%s\b.*?\b%d registers?\b|\b%d registers?\b.*?%s\b"
                              % (re.escape(addr), n, n, re.escape(addr)))
            if not any(want.search(ln) for ln in lines):
                problems.append(
                    "%s: no line declares the %s block as %s with %d registers"
                    % (rel, name.lower(), addr, n))

        # The primary block is the one the Dragino reads every cycle, so its
        # register NAMES are checked individually, not just the count. The
        # boundaries matter: without them SETTLE_S matches inside SETTLE_SECS
        # and a renamed register passes.
        for addr in sorted(rm["primary"]):
            nm = rm["primary"][addr]
            if not re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(nm), doc):
                problems.append("%s: primary register %s (0x%04X) not documented"
                                % (rel, nm, addr))

        # EVERY address the prose puts next to a register name must be the
        # address that register actually has. Checking only the block headings
        # and the primary names was not enough: it passed while FIRMWARE.md
        # documented the CAL_TRIGGER and COMMIT magics at 0x002D and 0x002E,
        # which is where they lived before the config block moved to 0x0030.
        # Those addresses now fall in the gap between blocks, so an operator
        # following the document gets exception 02 and the configuration is
        # never committed - a silent failure of the one register whose whole
        # job is to make a change stick.
        #
        # Only hex tokens that could BE an address are considered, so the
        # magics themselves (0xCA11, 0x5AC1) are not mistaken for addresses.
        for i, ln in enumerate(lines, 1):
            hexes = [int(h, 16) for h in re.findall(r"0x([0-9A-Fa-f]{4})\b", ln)]
            hexes = [h for h in hexes if h <= 0xFF]
            if not hexes:
                continue
            for nm, addr in rm["every"].items():
                if not re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])"
                                 % re.escape(nm), ln):
                    continue
                if addr not in hexes:
                    problems.append(
                        "%s:%d: %s is documented at %s but regmap.h puts it at "
                        "0x%04X" % (rel, i, nm,
                                    ", ".join("0x%04X" % h for h in hexes), addr))

        # A read spanning two blocks must be refused; if a doc stops saying so,
        # someone will "simplify" the map into one contiguous range.
        if "exception 02" not in doc:
            problems.append("%s: no longer states that undefined addresses raise "
                            "exception 02" % rel)

    if problems:
        print("!! register-map documentation is stale (src/regmap.h is the "
              "source of truth):")
        for p in problems:
            print("   -", p)
        return 1
    print("register-map docs agree with the headers (" +
          ", ".join("%s 0x%04X x%d" % (n.lower(), rm["%s_BASE" % n],
                                       rm["%s_COUNT" % n]) for n in BLOCKS) +
          ")")
    del base, count
    return 0


if __name__ == "__main__":
    sys.exit(main())
