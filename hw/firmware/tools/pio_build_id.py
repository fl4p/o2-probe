"""PlatformIO pre-build action: stamp the git commit into the image.

O2P_FW_VERSION is a hand-edited constant. It said 0x0001 on every probe ever
built, across every install, so telemetry could never answer "which binary is
this?" - and on 2026-09-07 that was the question: O2_RAW stepped 0.51 %vol
across a firmware install and nothing on the wire identified either side of
the step. A version number a human has to remember to bump is not provenance.

This is: the 28-bit prefix of the commit the image was built from, plus a
dirty bit, published as BUILD_ID_HI/LO (0x0028/0x0029).

  bit  31     working tree was dirty at build time
  bit  30     NOT set here: src/regmap.c sets it on an O2P_DEBUG_ENABLE=1
              image and clears it otherwise (O2P_BUILD_ID_FLAG_DEBUG, since
              faf52d8), so a master can tell a debug build from the register
  bits 29..28 reserved, zero
  bits 27..0  `git rev-parse --short=7 HEAD`

A dirty build is stamped, not refused - bench iteration is the normal case -
but it is stamped as dirty, because the SHA alone would be a lie about a tree
that does not match it.

Git failing is FATAL for a target build. A build with no provenance is the
exact condition this file exists to prevent, and defaulting to 0 would put an
unidentifiable image on a probe that is potted in a jar. The host test build
(env:native) does not run this script and keeps the 0 = unknown default.
"""
import subprocess
import sys

Import("env")  # noqa: F821 - injected by SCons


def _git(args):
    return subprocess.run(
        ["git"] + args,
        cwd=env.subst("$PROJECT_DIR"),  # noqa: F821
        capture_output=True,
        text=True,
    )


def _fail(msg):
    sys.stderr.write("*** build id: %s\n" % msg)
    env.Exit(1)  # noqa: F821


head = _git(["rev-parse", "--short=7", "HEAD"])
if head.returncode != 0:
    _fail("`git rev-parse HEAD` failed (%s). The image would carry no "
          "provenance; refusing to build.\n    %s"
          % (head.returncode, head.stderr.strip()))

sha = head.stdout.strip()
try:
    build_id = int(sha, 16)
except ValueError:
    _fail("`git rev-parse --short=7 HEAD` returned %r, not 7 hex digits." % sha)

if build_id > 0x0FFFFFFF:
    _fail("short SHA %r does not fit the 28 bits reserved for it." % sha)

# --quiet exits 1 on any tracked change; --exit-code is implied. Untracked
# files are deliberately NOT counted: they cannot be in the image.
#
# SCOPED TO THE BUILD INPUTS, 2026-09-13. This used to diff the WHOLE
# REPOSITORY, and ~/dev/ee is a monorepo that several agent sessions and
# several unrelated projects share - pv/ee, vibe, crypto, .idea, submodule
# gitlinks. It is essentially never clean, so every image was stamped dirty
# whatever the firmware's own state, and a guard that is permanently red
# trains everyone to wave it through. Measured 2026-09-13: the firmware
# sources all committed at 8bb8802, seventeen unrelated paths dirty, and the
# image refused by o2p_flash.py for a tree state it did not have.
#
# The scope below is the same argument the untracked-file line above makes:
# a file that cannot be in the image must not be evidence about the image.
# The inputs are this PlatformIO project and ../gen_sch.py, which
# pio_hw_contract.py regenerates src/hw_contract.h from (its docstring calls
# it "the declared source of truth"). Nothing else is compiled or generated
# into these bits.
#
# Deliberately NOT widened to the whole o2-probe directory: the KiCad files,
# the docs and the audit reports beside it churn constantly and are not build
# inputs either. If a future build starts consuming one, add it HERE - this
# list IS the claim about what the SHA covers.
_INPUTS = [".", "../gen_sch.py"]
dirty = _git(["diff", "--quiet", "HEAD", "--"] + _INPUTS).returncode != 0
if dirty:
    build_id |= 0x80000000

env.Append(CPPDEFINES=[("O2P_BUILD_ID", "0x%08XUL" % build_id)])  # noqa: F821
print("build id: %08X (%s%s)" % (build_id, sha, ", dirty" if dirty else ""))
