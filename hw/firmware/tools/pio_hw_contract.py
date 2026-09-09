"""PlatformIO pre-build actions: fail the build if a contract is stale.

Two contracts, both checked here rather than trusted to a human:

`src/hw_contract.h` is generated from `../gen_sch.py`, the declared source of
truth for this board. Checking it here is what makes FAB-READINESS.md's
"firmware must use this final pin map" mandate mechanical.

`src/hw_caps_rev_*.h` are the PER-REVISION capability headers, and they are a
different kind of claim: `hw_contract.h` describes the board being designed,
while a fabricated article's wiring is frozen and lives in the copper. Deriving
one from the other is how a Rev B channel map came to run on a Rev A board on
2026-09-09 and withheld every oxygen reading from a healthy probe.

`src/regmap.h` is the wire contract with a Dragino node and a ChirpStack codec
that cannot see this header, and its prose copies drifted three times in one
day. A stale copy is how someone points AT+COMMAND at addresses that moved.

`src/flash_map.h` is the source of truth for where the bootloader, the
application and the staging slot live. The two linker scripts repeat those
numbers because a linker script cannot include a C header, and a script that
drifts lets an image link over the slot next door - silently, at whichever
build first grows large enough to reach it.

The bench bridge's SWD transport is a literal SRAM address and a literal
struct layout typed into a Python tool, driving a debugger that will read
whatever address it is given and report success either way. Nothing about
that fails loudly on its own, so it is checked here too, and the transport
itself is run against a fake OpenOCD and a fake bridge - the ordering rules
it depends on are claims about what a debugger observes, which no amount of
reading the source establishes.
"""
import subprocess
import sys

Import("env")  # noqa: F821 - injected by SCons

PROJECT_DIR = env.subst("$PROJECT_DIR")  # noqa: F821

rc = subprocess.call([sys.executable, "tools/gen_hw_contract.py", "--check"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** Hardware contract check failed - refusing to build.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/test_pcb_netlist.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** The as-built netlist reader failed its host test - refusing to "
          "build. Its failure mode is an EMPTY result that reads as a valid "
          "'nothing is connected', so every capability below it would be "
          "invented. See tools/test_pcb_netlist.py.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/gen_hw_caps.py", "--check"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** Per-revision hardware capabilities are stale - refusing to "
          "build. Each revision's caps come from ITS OWN netlist; run "
          "tools/gen_hw_caps.py and re-check every guard that reads one.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/check_regmap_docs.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** Register-map documentation is stale - refusing to build. "
          "src/regmap.h is the source of truth; update FIRMWARE.md and "
          "../DESIGN.md to match.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/check_flash_map.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** Flash map and linker scripts disagree - refusing to build. "
          "src/flash_map.h is the source of truth.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/check_update_tool.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** The field update tool disagrees with src/update.h - refusing "
          "to build. tools/o2p_update.py is what a technician runs next to a "
          "buried probe; it may not carry stale addresses.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/test_swd_link.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** The bench bridge's SWD transport failed its host test - "
          "refusing to build. See tools/test_swd_link.py.")
    env.Exit(1)  # noqa: F821

rc = subprocess.call([sys.executable, "tools/check_transport_math.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** FIRMWARE.md's transport estimates no longer follow from their "
          "own stated image size - refusing to build.")
    env.Exit(1)  # noqa: F821
