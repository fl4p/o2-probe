#!/usr/bin/env python3
"""Fail if the linker scripts, the board JSON or the flash map disagree.

`src/flash_map.h` says where the bootloader, the run slot, the staging slot,
the boot descriptor and the configuration live. Three other files repeat those
numbers because they cannot include a C header:

  * ldscript/o2probe_app.ld     FLASH ORIGIN/LENGTH for the application
  * ldscript/o2probe_loader.ld  FLASH ORIGIN/LENGTH for the bootloader
  * platformio.ini              board_upload.maximum_size per environment

The bench bridge (ldscript/o2probe_bridge.ld) is checked too, for the opposite
property: it must be the WHOLE part and no slot at all. It is the only image on
its board, and a bridge that had quietly acquired the application's origin
would link at 0x08004000 and boot into nothing.

Drift in any of them is silent until the build that first grows large enough
to reach the region next door - at which point the application overwrites the
staging slot, or the bootloader overwrites the application, and the probe that
finds out is buried.

Also checks the regions actually tile the part with no overlap and no gap,
which is the property a page number typo breaks first.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)


def defines(text):
    out = {}
    for m in re.finditer(r"#define\s+(O2P_[A-Z0-9_]+)\s+(0x[0-9A-Fa-f]+|\d+)u?\b",
                         text):
        out[m.group(1)] = int(m.group(2), 0)
    return out


def ld_flash(path):
    """(origin, length_bytes) from a linker script's FLASH memory line."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"FLASH\s*\(\s*rx\s*\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+)\s*,"
                  r"\s*LENGTH\s*=\s*(\d+)([KM]?)", text)
    if not m:
        raise SystemExit("!! %s: no FLASH line I can read" % path)
    scale = {"": 1, "K": 1024, "M": 1024 * 1024}[m.group(3)]
    return int(m.group(1), 0), int(m.group(2)) * scale


def ini_max_sizes(path):
    """{env: board_upload.maximum_size} for the environments that set one."""
    out = {}
    env = None
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\[env:([^\]]+)\]", line.strip())
        if m:
            env = m.group(1)
            continue
        m = re.match(r"board_upload\.maximum_size\s*=\s*(\d+)\s*$", line.strip())
        if m and env:
            out[env] = int(m.group(1))
    return out


def main():
    d = defines(open(os.path.join(FW, "src", "flash_map.h"),
                     encoding="utf-8").read())
    page = d["O2P_FLASH_PAGE_BYTES"]
    origin = d["O2P_FLASH_ORIGIN"]

    def addr(pg):
        return origin + pg * page

    regions = [
        ("bootloader",  d["O2P_BOOT_PAGE"],  d["O2P_BOOT_PAGES"]),
        ("run slot",    d["O2P_APP_PAGE"],   d["O2P_APP_PAGES"]),
        ("staging",     d["O2P_STAGE_PAGE"], d["O2P_STAGE_PAGES"]),
        ("descriptor A", d["O2P_DESC_PAGE_A"], 1),
        ("descriptor B", d["O2P_DESC_PAGE_B"], 1),
        ("config A",     d["O2P_CONFIG_PAGE_A"], 1),
        ("config B",     d["O2P_CONFIG_PAGE_B"], 1),
    ]

    problems = []

    # Each A/B pair is listed as two SEPARATE one-page regions on purpose.
    # Modelling them as "A plus two pages" never reads O2P_DESC_PAGE_B or
    # O2P_CONFIG_PAGE_B at all, so either B page could be moved onto another
    # region's flash and this check would still pass - while boot_desc.c and
    # config_flash.c went on erasing it.
    #
    # The regions must tile pages 0..63 exactly. A gap is wasted flash and is
    # allowed to exist, but an overlap is two owners for the same page.
    nxt = 0
    for name, first, count in regions:
        if first < nxt:
            problems.append("%s starts at page %d, inside the previous region "
                            "(which ends at page %d)" % (name, first, nxt))
        nxt = first + count
    if nxt != d["O2P_FLASH_PAGES"]:
        problems.append("the regions end at page %d, not %d - the last region "
                        "either overruns the part or leaves it unaccounted for"
                        % (nxt, d["O2P_FLASH_PAGES"]))

    checks = [
        ("ldscript/o2probe_loader.ld", addr(d["O2P_BOOT_PAGE"]),
         d["O2P_BOOT_PAGES"] * page),
        ("ldscript/o2probe_app.ld", addr(d["O2P_APP_PAGE"]),
         d["O2P_APP_PAGES"] * page),
        ("ldscript/o2probe_bridge.ld", origin, d["O2P_FLASH_PAGES"] * page),
    ]
    for rel, want_origin, want_len in checks:
        got_origin, got_len = ld_flash(os.path.join(FW, rel))
        if got_origin != want_origin:
            problems.append("%s: FLASH ORIGIN is 0x%08X, flash_map.h says "
                            "0x%08X" % (rel, got_origin, want_origin))
        if got_len != want_len:
            problems.append("%s: FLASH LENGTH is %d bytes, flash_map.h says %d"
                            % (rel, got_len, want_len))

    sizes = ini_max_sizes(os.path.join(FW, "platformio.ini"))
    for env, want in (("o2probe", d["O2P_APP_PAGES"] * page),
                      ("loader", d["O2P_BOOT_PAGES"] * page),
                      ("bridge", d["O2P_FLASH_PAGES"] * page)):
        if env not in sizes:
            problems.append("platformio.ini: [env:%s] sets no "
                            "board_upload.maximum_size, so an image that "
                            "outgrows its slot would link and flash silently"
                            % env)
        elif sizes[env] != want:
            problems.append("platformio.ini: [env:%s] maximum_size is %d, "
                            "flash_map.h says %d" % (env, sizes[env], want))

    if problems:
        print("!! flash map is inconsistent (src/flash_map.h is the source of "
              "truth):")
        for p in problems:
            print("   -", p)
        return 1

    print("flash map agrees: loader 0x%08X+%dK, app 0x%08X+%dK, "
          "staging 0x%08X+%dK"
          % (addr(d["O2P_BOOT_PAGE"]), d["O2P_BOOT_PAGES"] * page // 1024,
             addr(d["O2P_APP_PAGE"]), d["O2P_APP_PAGES"] * page // 1024,
             addr(d["O2P_STAGE_PAGE"]), d["O2P_STAGE_PAGES"] * page // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
