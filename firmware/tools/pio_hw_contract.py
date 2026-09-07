"""PlatformIO pre-build actions: fail the build if a contract is stale.

Two contracts, both checked here rather than trusted to a human:

`src/hw_contract.h` is generated from `../gen_sch.py`, the declared source of
truth for this board. Checking it here is what makes FAB-READINESS.md's
"firmware must use this final pin map" mandate mechanical.

`src/regmap.h` is the wire contract with a Dragino node and a ChirpStack codec
that cannot see this header, and its prose copies drifted three times in one
day. A stale copy is how someone points AT+COMMAND at addresses that moved.
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

rc = subprocess.call([sys.executable, "tools/check_regmap_docs.py"],
                     cwd=PROJECT_DIR)
if rc != 0:
    print("*** Register-map documentation is stale - refusing to build. "
          "src/regmap.h is the source of truth; update FIRMWARE.md and "
          "../DESIGN.md to match.")
    env.Exit(1)  # noqa: F821
