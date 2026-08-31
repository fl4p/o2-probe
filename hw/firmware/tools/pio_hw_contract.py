"""PlatformIO pre-build action: fail the build if the hardware contract is stale.

`src/hw_contract.h` is generated from `../gen_sch.py`, the declared source of
truth for this board. Checking it here - rather than trusting a human to
re-run a script - is what makes FAB-READINESS.md's "firmware must use this
final pin map" mandate mechanical.
"""
import subprocess
import sys

Import("env")  # noqa: F821 - injected by SCons

rc = subprocess.call([sys.executable, "tools/gen_hw_contract.py", "--check"],
                     cwd=env.subst("$PROJECT_DIR"))  # noqa: F821
if rc != 0:
    print("*** Hardware contract check failed - refusing to build.")
    env.Exit(1)  # noqa: F821
