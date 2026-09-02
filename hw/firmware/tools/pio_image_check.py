"""Post-build check: would the bootloader accept the image we just built?

The loader verifies a staged image by its CRC and then by its vector table -
initial stack pointer in SRAM, Thumb bit set, reset vector inside the run slot.
That check exists to catch the wrong image being pushed, but it also catches a
build that has quietly moved: a linker script edited to the wrong origin
produces a perfectly valid ELF whose failure mode is "the update never
installs, and the probe you cannot reach says ERR_IMAGE".

So the same rule runs here, at the point where the .bin appears, against the
real artifact. An application whose reset vector is not in the run slot, or a
bootloader whose reset vector is not in the bootloader region, fails the build.

The bridge gets one more check. Its SWD host transport is a block of SRAM at a
literal address that tools/o2p_update.py types out - there is no symbol lookup
at the far end of a debugger - so a linker script edit that moved the mailbox
would point the host at whatever landed there instead, and the failure would
look like a bridge that has stopped answering.
"""
import os
import re
import struct
import subprocess

Import("env")  # noqa: F821

PAGE = 2048
FLASH = 0x08000000
BOOT_BASE, BOOT_BYTES = FLASH, 8 * PAGE
APP_BASE, APP_BYTES = FLASH + 8 * PAGE, 26 * PAGE
SRAM_BASE, SRAM_BYTES = 0x20000000, 36 * 1024

# Which region each environment's reset vector must land in. The bench bridge
# is not part of the field flash map at all - it is the only image on its
# board and takes the whole part - so it is checked against the whole part.
REGIONS = {
    "loader": (BOOT_BASE, BOOT_BYTES),
    "bridge": (FLASH, 64 * PAGE),
}


def check_mailbox(env, elf):
    """The bridge's SWD mailbox must be exactly where the host tool types."""
    hdr = os.path.join(env.subst("$PROJECT_DIR"), "src", "bridge_mailbox.h")
    with open(hdr, encoding="utf-8") as f:
        m = re.search(r"#define O2P_MBX_BASE\s+(0x[0-9A-Fa-f]+)u", f.read())
    if not m:
        print("*** src/bridge_mailbox.h no longer defines O2P_MBX_BASE")
        env.Exit(1)
    want = int(m.group(1), 0)

    nm = env.subst("$CC").replace("gcc", "nm")
    try:
        out = subprocess.check_output([nm, elf], text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print("*** could not read symbols from %s: %s" % (elf, e))
        env.Exit(1)
        return
    got = None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == "g_o2p_mailbox":
            got = int(parts[0], 16)
    if got is None:
        print("*** %s has no g_o2p_mailbox symbol - the .mailbox section was "
              "dropped, and the SWD transport would read whatever is at "
              "0x%08X instead" % (elf, want))
        env.Exit(1)
    elif got != want:
        print("*** g_o2p_mailbox is at 0x%08X, src/bridge_mailbox.h and "
              "tools/o2p_update.py say 0x%08X - check the MAILBOX region in "
              "ldscript/o2probe_bridge.ld" % (got, want))
        env.Exit(1)
    else:
        print("image check: SWD mailbox at 0x%08X" % got)


def check_image(source, target, env):  # noqa: ARG001 - SCons signature
    path = str(target[0])
    with open(path, "rb") as f:
        head = f.read(8)
    if len(head) < 8:
        print("*** %s is too short to hold a vector table." % path)
        env.Exit(1)
    msp, reset = struct.unpack("<II", head)

    name = env.subst("$PIOENV")
    base, size = REGIONS.get(name, (APP_BASE, APP_BYTES))
    problems = []
    if not SRAM_BASE <= msp <= SRAM_BASE + SRAM_BYTES:
        problems.append("initial stack pointer 0x%08X is not in SRAM" % msp)
    if not reset & 1:
        problems.append("reset vector 0x%08X has no Thumb bit" % reset)
    entry = reset & ~1
    if not base <= entry < base + size:
        problems.append("reset vector 0x%08X is outside the 0x%08X region this "
                        "environment links into - check "
                        "board_build.ldscript" % (reset, base))
    if problems:
        print("*** %s would be refused by the bootloader:" % path)
        for p in problems:
            print("   -", p)
        env.Exit(1)
    print("image check: %s MSP 0x%08X, reset 0x%08X, inside 0x%08X+%dK"
          % (name, msp, reset, base, size // 1024))
    if name == "bridge":
        check_mailbox(env, str(source[0]))


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", check_image)  # noqa: F821
