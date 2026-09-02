#!/usr/bin/env python3
"""Fail if FIRMWARE.md's transport estimates do not follow from each other.

The estimates in "Field updates" are all proportional to the image, so they go
stale on their own every time the firmware changes size. Chasing that with a
check that recomputes from the built `.bin` would fail every build that touched
a line of C, which is not a bug and would train people to ignore it.

What has actually gone wrong, twice, in two independent reviews, is different
and worth catching: the chain stopped following from its own stated premise.
One review found a block count computed from the unpadded size, and an A8
figure computed from a 30-byte payload the engine rejects for being unaligned.
The other found a size that had moved and a downlink figure that had not.

So this checks the arithmetic, not the measurement: given the image size the
document states, are its own derived numbers right? The size is the one input
a person has to keep honest, and it is labelled with the build it came from.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)

ALIGN = 8          # src/update.h: images are programmed as doublewords
WIRE_BLOCK = 240   # 120 payload registers
A8_BLOCK = 24      # 12 payload registers, the aligned part of A8's 30 bytes
TDC_S = 300
BITS = 11          # 8E1
RUN_SLOT = 53248


def one(text, pattern, what):
    m = re.search(pattern, text)
    if not m:
        raise SystemExit("!! FIRMWARE.md no longer states %s" % what)
    return int(m.group(1).replace(",", ""))


def close(got, want, tol):
    return abs(got - want) <= tol


def main():
    md = open(os.path.join(FW, "FIRMWARE.md"), encoding="utf-8").read()

    size = one(md, r"`firmware\.bin` is \*\*([\d,]+) bytes\*\*", "the image size")
    padded = one(md, r"so\s+\*\*([\d,]+) bytes\*\*\s+go over the wire",
                 "the padded size")
    a8 = one(md, r"\| downlinks for [\d,]+ bytes \| \*\*([\d,]+)\*\* \|",
             "the downlink count")
    a8_for = one(md, r"\| downlinks for ([\d,]+) bytes \|",
                 "which size the downlink count is for")
    blocks = one(md, r"a ([\d,]+)-byte image is \d+ blocks", "the wire size")
    nblocks = one(md, r"a [\d,]+-byte image is (\d+) blocks", "the block count")
    pct = re.search(r"([\d.]+) % of the \*\*([\d,]+)-byte run slot", md)

    problems = []
    want_padded = (size + ALIGN - 1) // ALIGN * ALIGN
    if padded != want_padded:
        problems.append("%d bytes padded to %d is %d, not %d"
                        % (size, ALIGN, want_padded, padded))
    for name, stated in (("the A8 table", a8_for), ("the wire estimate", blocks)):
        if stated != padded:
            problems.append("%s works from %d bytes, but the image goes over "
                            "the wire as %d" % (name, stated, padded))

    want_a8 = -(-padded // A8_BLOCK)
    if a8 != want_a8:
        problems.append("%d bytes in %d-byte blocks is %d downlinks, not %d"
                        % (padded, A8_BLOCK, want_a8, a8))
    want_blocks = -(-padded // WIRE_BLOCK)
    if nblocks != want_blocks:
        problems.append("%d bytes in %d-byte blocks is %d blocks, not %d"
                        % (padded, WIRE_BLOCK, want_blocks, nblocks))

    hours = re.search(r"\| at `AT\+TDC` = %d s \| \*\*([\d.]+) h\*\* \|" % TDC_S,
                      md)
    if not hours:
        problems.append("FIRMWARE.md no longer states the A8 wall time")
    else:
        want_h = want_a8 * TDC_S / 3600.0
        if not close(float(hours.group(1)), want_h, 0.15):
            problems.append("%d downlinks at %d s is %.1f h, not %s"
                            % (want_a8, TDC_S, want_h, hours.group(1)))

    secs = re.search(r"so 872\.7 B/s and \*\*([\d.]+) s\*\* for the whole image",
                     md)
    if not secs:
        problems.append("FIRMWARE.md no longer states the 9600-baud line time")
    else:
        want_s = padded / (9600.0 / BITS)
        if not close(float(secs.group(1)), want_s, 0.15):
            problems.append("%d bytes at 9600 8E1 is %.1f s, not %s"
                            % (padded, want_s, secs.group(1)))

    if not pct:
        problems.append("FIRMWARE.md no longer states the run-slot fraction")
    else:
        slot = int(pct.group(2).replace(",", ""))
        if slot != RUN_SLOT:
            problems.append("the run slot is %d bytes, not %d"
                            % (RUN_SLOT, slot))
        want_pct = 100.0 * size / slot
        if not close(float(pct.group(1)), want_pct, 0.15):
            problems.append("%d of %d is %.1f %%, not %s"
                            % (size, slot, want_pct, pct.group(1)))

    if problems:
        print("!! FIRMWARE.md's transport arithmetic does not follow from "
              "its own stated image size (%d bytes):" % size)
        for p in problems:
            print("   -", p)
        print("   If the image has changed size, restate the size AND every "
              "number derived from it.")
        return 1
    print("transport arithmetic is consistent: %d bytes -> %d padded, "
          "%d wire blocks, %d downlinks" % (size, padded, want_blocks, want_a8))
    return 0


if __name__ == "__main__":
    sys.exit(main())
