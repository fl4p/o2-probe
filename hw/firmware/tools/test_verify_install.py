#!/usr/bin/env python3
"""boot_and_verify(): `--boot` must not exit 0 on the BOOT write alone.

    python3 tools/test_verify_install.py

The BOOT write is answered before the probe resets, so its reply proves the
command arrived and nothing else. Until 2026-09-10 every --boot exited 0 on
it - including the runs where the install failed, rolled back, or the probe
never came back. These cases are the ways an install can look fine from the
BOOT reply and not be:

  installed         the new image runs                     -> 0
  rolled back       installs unchanged, old image back     -> 1
  wrong image       installs advanced, BUILD_ID mismatch   -> 1
  loader error      application answers with error set     -> 1
  never answers     nothing within the timeout             -> 2, never 0
  stuck in loader   only the bootloader answers            -> 2, never 0
  no proof          install count unreadable, no expected
                    BUILD_ID given                          -> 2, never 0

The probe here is a FAKE: the registers verify_install() reads, and a BOOT that
takes a while and ends in a chosen outcome. It stands in for the register map
(update.h, regmap.h); it is not a recording. Time is faked, so the timeouts cost
nothing.
"""
import argparse
import binascii
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_update as U  # noqa: E402

failures = 0
checks = 0


def check(name, cond, detail=""):
    global failures, checks
    checks += 1
    print("  %-4s %s%s" % ("ok" if cond else "FAIL", name,
                           "" if cond or not detail else "  <- %s" % (detail,)))
    if not cond:
        failures += 1


class Clock:
    def __init__(self):
        self.t = 5000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)


OLD_ID = 0x475162FA          # v0.11 as measured in telemetry, 2026-09-10
NEW_ID = 0x0E7220EF          # e7220ef, clean
IMAGE = b"e7220ef application image - fake bytes for the staged-slot check " * 40
STAGED_OK = (len(IMAGE), binascii.crc32(IMAGE) & 0xFFFFFFFF)


class Probe:
    """The few registers verify_install() touches, and a BOOT with an outcome."""

    def __init__(self, clock, outcome, reboot_s=25.0, installs=4,
                 unreadable_before_boot=False, build_id=OLD_ID,
                 new_build_id=NEW_ID, staged=STAGED_OK, state_before=5,
                 boot_write_silent=False):
        self.clock = clock
        self.outcome = outcome
        self.reboot_s = reboot_s
        self.installs = installs
        self.build_id = build_id
        self.new_build_id = new_build_id
        self.staged = staged
        self.state = state_before
        self.err = 0
        self.in_loader = False
        self.down_until = None
        self.dead = False
        self.booted = False
        self.unreadable_before_boot = unreadable_before_boot
        # 2026-09-10 bench case: the BOOT write LANDS (all effects below are
        # applied) and the echo is lost - bus silence after a write that went
        # through. The fake raises NoReply AFTER applying the effects, which
        # is the only honest way to model it.
        self.boot_write_silent = boot_write_silent
        self.boots = 0

    def _up(self):
        if self.dead:
            return False
        return self.down_until is None or self.clock.t >= self.down_until

    def read(self, addr, count):
        if not self._up():
            raise U.NoReply("no reply")
        if addr == U.R_STATUS and count == 1:
            v = (self.state << 8) | self.err | (U.LOADER_BIT if self.in_loader else 0)
            return [v]
        if addr == U.R_LOADER_VER and count == 3:
            if self.unreadable_before_boot and not self.booted:
                raise U.NoReply("no reply")
            return [1, 12, self.installs]
        if addr == U.R_BUILD_ID_HI and count == 2 and not self.in_loader:
            return [self.build_id >> 16, self.build_id & 0xFFFF]
        if addr in (U.R_LEN_HI, U.R_CRC_HI) and count == 2:
            ln, cr = self.staged if self.staged else (0, 0)
            v = ln if addr == U.R_LEN_HI else cr
            return [v >> 16, v & 0xFFFF]
        raise U.ModbusException(2)

    def write(self, addr, values):
        if addr == U.R_CMD and values[0] == U.CMD_STAY:
            self.in_loader = True            # stays in the loader, installs nothing
            if self.boot_write_silent:
                raise U.NoReply("no reply")
            return
        if addr != U.R_CMD or values[0] != U.CMD_BOOT:
            raise AssertionError("unexpected write %r %r" % (addr, values))
        self.boots += 1
        self.booted = True
        self.state = 0
        self.down_until = self.clock.t + self.reboot_s
        o = self.outcome
        if o == "installed":
            self.installs = min(self.installs + 1, U.INSTALLS_MAX)
            self.build_id = self.new_build_id
        elif o == "rolled_back":
            pass
        elif o == "wrong_image":
            self.installs = min(self.installs + 1, U.INSTALLS_MAX)
            self.build_id = 0x0DEADBEE
        elif o == "loader_error":
            self.installs = min(self.installs + 1, U.INSTALLS_MAX)
            self.build_id = self.new_build_id
            self.err = U.ERRORS.index("CRC")
        elif o == "dead":
            self.dead = True
        elif o == "stuck_in_loader":
            self.in_loader = True
        else:
            raise AssertionError(o)
        if self.boot_write_silent:
            # The write landed (every effect above is applied); the echo
            # never came back. Raised LAST, which is the only honest order.
            raise U.NoReply("no reply")


def run(outcome, **kw):
    ns = dict(boot=True, stay=False, no_verify=False, expect_build_id=None,
              verify_timeout=180.0)
    probe_kw = {}
    for k in ("unreadable_before_boot", "reboot_s", "installs", "build_id",
              "new_build_id", "staged", "state_before", "boot_write_silent"):
        if k in kw:
            probe_kw[k] = kw.pop(k)
    drop_stay = kw.pop("drop_stay", False)
    image = kw.pop("image", IMAGE)
    ns.update(kw)
    args = argparse.Namespace(**ns)
    if drop_stay:
        del args.stay
    clock = Clock()
    probe = Probe(clock, outcome, **probe_kw)
    saved = U.time
    U.time = clock
    try:
        rc = U.boot_and_verify(probe, args, image)
    finally:
        U.time = saved
    return rc, probe


print("\nthe outcomes")
rc, p = run("installed", expect_build_id=NEW_ID)
check("installed, BUILD_ID as expected -> 0", rc == 0, rc)
check("  ...and BOOT was sent exactly once", p.boots == 1, p.boots)
rc, _ = run("installed")
check("installed, no expected BUILD_ID: the install count alone proves it -> 0",
      rc == 0, rc)
rc, _ = run("rolled_back")
check("rolled back (installs unchanged) -> 1", rc == 1, rc)
rc, _ = run("rolled_back", expect_build_id=NEW_ID)
check("rolled back with an expected BUILD_ID -> 1", rc == 1, rc)
rc, _ = run("wrong_image", expect_build_id=NEW_ID)
check("installs advanced but the WRONG image runs -> 1", rc == 1, rc)
rc, _ = run("loader_error", expect_build_id=NEW_ID)
check("the application answers with an error set -> 1", rc == 1, rc)

print("\nunverifiable is never 0")
rc, _ = run("dead")
check("the probe never comes back -> 2 (the old --boot exited 0 here)",
      rc == 2, rc)
rc, _ = run("stuck_in_loader")
check("only the bootloader ever answers -> 2", rc == 2, rc)
rc, _ = run("installed", unreadable_before_boot=True)
check("install count unreadable before BOOT and no expected BUILD_ID -> 2: "
      "the application answering proves nothing about WHICH image", rc == 2, rc)
rc, _ = run("installed", unreadable_before_boot=True, expect_build_id=NEW_ID)
check("install count unreadable, BUILD_ID matches -> 2: a matching stamp alone "
      "does not show an install happened (review 2026-09-10)", rc == 2, rc)
rc, _ = run("rolled_back", build_id=NEW_ID, unreadable_before_boot=True,
            expect_build_id=NEW_ID)
check("known-bad (review): the expected image was ALREADY running, nothing "
      "installed, count unreadable -> 2, never 0", rc == 2, rc)
rc, _ = run("rolled_back", build_id=NEW_ID, expect_build_id=NEW_ID)
check("the expected image was already running and the count did not move -> 1",
      rc == 1, rc)
rc, _ = run("installed", installs=0xFFFF, expect_build_id=NEW_ID)
check("a saturated install counter cannot show an install -> 2, not a false 1",
      rc == 2, rc)
rc, _ = run("installed", new_build_id=NEW_ID | 0x80000000,
            expect_build_id=NEW_ID | 0x80000000)
check("a dirty-stamped image that installed is verified (and said to be dirty)",
      rc == 0, rc)

# THE DEBUG BIT, and why this case had to exist. Bit 30 is set by regmap.c at
# RUNTIME on an O2P_DEBUG_ENABLE=1 image and is never stamped by
# pio_build_id.py, so the value a probe PUBLISHES differs from the builder's
# by that bit alone. env:o2probe defines -DO2P_DEBUG_ENABLE=1
# (platformio.ini:92), so this is not an exotic configuration - it is the only
# kind of image the probe has ever run. Until 2026-09-13 the comparison was a
# bare equality, so --expect-build-id reported EVERY successful install of a
# probe image as a failure. This suite missed it because every case above uses
# a build id with bit 30 clear, i.e. an image that does not exist.
rc, _ = run("installed", new_build_id=NEW_ID | 0x40000000,
            expect_build_id=NEW_ID)
check("a DEBUG image matches the builder's stamp (bit 30 is runtime-set, not "
      "part of the identity) -> 0", rc == 0, rc)
rc, _ = run("installed", new_build_id=NEW_ID | 0xC0000000,
            expect_build_id=NEW_ID | 0x80000000)
check("debug and dirty together still match a dirty stamp -> 0", rc == 0, rc)
rc, _ = run("installed", new_build_id=(NEW_ID ^ 1) | 0x40000000,
            expect_build_id=NEW_ID)
check("known-bad calibration: masking bit 30 must NOT mask a real sha "
      "difference -> 1", rc == 1, rc)

rc, _ = run("installed", reboot_s=400.0, verify_timeout=180.0)
check("a reboot longer than --verify-timeout -> 2, not a guess", rc == 2, rc)
rc, _ = run("installed", reboot_s=170.0, verify_timeout=180.0,
            expect_build_id=NEW_ID)
check("a slow reboot inside the timeout is still verified -> 0", rc == 0, rc)

print("\nthe escape hatch says what it is")
rc, _ = run("dead", no_verify=True)
check("--no-verify returns 0 without checking (and prints that it did not)",
      rc == 0, rc)

print("\nthe staged slot must hold THIS image before BOOT (review round two)")
rc, p = run("installed", staged=(len(IMAGE), 0x12345678), expect_build_id=NEW_ID)
check("known-bad (review): another image is staged -> 1, and BOOT is NOT sent",
      rc == 1 and p.boots == 0, (rc, p.boots))
rc, p = run("installed", state_before=0, expect_build_id=NEW_ID)
check("nothing is staged (IDLE) -> 1, and BOOT is NOT sent",
      rc == 1 and p.boots == 0, (rc, p.boots))
rc, p = run("installed", image=None, expect_build_id=NEW_ID)
check("no image to compare -> 2: an install happened, but not provably this one",
      rc == 2 and p.boots == 1, (rc, p.boots))

print("\ncallers")
rc, _ = run("installed", expect_build_id=NEW_ID, drop_stay=True)
check("a namespace with no --stay (the LoRaWAN and BLE push tools) works",
      rc == 0, rc)
rc, p = run("installed", boot=False, stay=True)
check("--stay sends STAY and does not verify an install", rc == 0, rc)

print("\nbus silence after the BOOT write (measured 2026-09-10: the BOOT "
      "usually lands; the reply races the reset)")
import contextlib                                                     # noqa: E402
import io                                                             # noqa: E402


def run_silent(**kw):
    ns = dict(boot=True, stay=False, no_verify=False, expect_build_id=None,
              verify_timeout=180.0)
    ns.update(kw)
    args = argparse.Namespace(**ns)
    clock = Clock()
    probe = Probe(clock, "installed", boot_write_silent=True)
    saved = U.time
    U.time = clock
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = U.boot_and_verify(probe, args, IMAGE)
    finally:
        U.time = saved
    return rc, probe, out.getvalue()


rc, p, text = run_silent()
check("BOOT write silent -> 2, never 0: unverifiable, not verified", rc == 2, rc)
check("  ...and BOOT was sent exactly once (no blind re-send)", p.boots == 1,
      p.boots)
check("  ...and the model is honest: the write DID land (installs advanced)",
      p.installs == 5, p.installs)
check("  ...and the text says the reply races the reset",
      "races the reset" in text, text)
check("  ...and it names where to look: R_STATUS 0x0050 and R_INSTALLS 0x005E",
      "0x0050" in text and "0x005E" in text, text)
check("  ...and it warns against re-sending BOOT blind",
      "re-send" in text, text)

rc, p, text = run_silent(expect_build_id=NEW_ID)
check("BOOT write silent with an expected BUILD_ID is still 2, not a guess",
      rc == 2, rc)

# STAY has no reset to race: silence after STAY is an ordinary failure and
# must keep raising, not take the BOOT path.
clock = Clock()
probe = Probe(clock, "installed", boot_write_silent=True)
args = argparse.Namespace(boot=False, stay=True, no_verify=False,
                          expect_build_id=None, verify_timeout=180.0)
saved = U.time
U.time = clock
try:
    with contextlib.redirect_stdout(io.StringIO()):
        U.boot_and_verify(probe, args, IMAGE)
    raised = None
except U.NoReply as exc:
    raised = exc
finally:
    U.time = saved
check("silence after STAY still RAISES (no reset to race)", raised is not None)

print("\n%d checks, %d failure(s)" % (checks, failures))
sys.exit(1 if failures else 0)
