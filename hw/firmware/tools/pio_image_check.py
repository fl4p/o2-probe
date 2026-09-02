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
"""
import struct

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


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", check_image)  # noqa: F821
