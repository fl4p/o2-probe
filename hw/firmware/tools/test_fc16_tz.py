#!/usr/bin/env python3
"""Bus.write()'s trailing-0x00 tolerance flag, 2026-09-11.

The node appends one untrimmed 0x00 after a fast FC16 echo (BEGIN/COMMIT) -
confirmed 2026-09-10 with the instrumented repro (o2p_update.py's long
comment at the write() site has the full story). The node-side trim
(mbresync.h step 3) is written and host-tested but not flashed; until every
node on the bench runs it, the host needs an opt-in: O2P_FC16_TOLERATE_TZ=1.

These tests pin the SHAPE of what the flag permits - exactly the frame the
node-side trim removes, nothing broader:
  9 bytes, last one 0x00, first 8 the CRC-valid echo -> accepted
  the same frame WITHOUT the flag                          -> still strict
  9 bytes whose last is NOT 0x00, flag or not              -> refused
  10 bytes, flag or not                                    -> refused
  8 bytes                                                  -> unchanged
  a CRC-VALID echo of the WRONG register                   -> still caught

2026-09-11 02:20 (codex review finding 9): the first version of this file
never recorded what write() SENT, so its "the write landed" check was
vacuously true, and its wrong-register fixture carried a broken CRC while
bypassing the CRC check - proving nothing. This version records the exact
request PDU and builds every mismatched echo with a VALID CRC-16/MODBUS, so
each refusal is attributable to the check it exercises, not to a malformed
frame.
"""

import binascii
import os
import struct
import sys

import o2p_update as u                                    # noqa: E402

FAILURES = []


def check(name, ok):
    print("%-56s %s" % (name, "ok" if ok else "FAIL"))
    if not ok:
        FAILURES.append(name)


def crc16(payload):
    """CRC-16/MODBUS, as the wire protocol frames use."""
    crc = 0xFFFF
    for b in payload:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def fc16_request(addr, values):
    pdu = struct.pack(">BHHB", 16, addr, len(values), 2 * len(values))
    pdu += b"".join(struct.pack(">H", v) for v in values)
    return pdu


def echo_frame(addr, count):
    """A CRC-VALID 8-byte FC16 echo for (addr, count): slave 0x03, FC16,
    echoed addr and count, CRC-16/MODBUS over the six payload bytes - the
    same shape as the confirmed artifact 031000540005403800."""
    body = struct.pack(">BBHH", 0x03, 16, addr, count)
    return body + crc16(body)


class ArtifactBus(u.Bus):
    """A Bus whose _txn records the request and returns a fixed reply."""

    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def _txn(self, pdu, expect_len):
        self.requests.append(pdu)
        return self.reply


VALUES = [0xB001, 0, 43, 0x49, 0x40]                       # a BEGIN, once
ARTIFACT = echo_frame(u.R_CMD, len(VALUES)) + b"\x00"      # the confirmed shape
NINE_NOT_ZERO = echo_frame(u.R_CMD, len(VALUES)) + b"\x01"
TEN_BYTES = ARTIFACT + b"\x00"
WRONG_ADDR = echo_frame(0x0035, len(VALUES)) + b"\x00"     # CRC-valid, wrong reg
WRONG_COUNT = echo_frame(u.R_CMD, 4) + b"\x00"             # CRC-valid, short echo


def main():
    saved = os.environ.pop("O2P_FC16_TOLERATE_TZ", None)
    try:
        # 1. the artifact, flag off: strict refusal - the default must not
        #    move for anyone who does not ask.
        try:
            ArtifactBus(ARTIFACT).write(u.R_CMD, VALUES)
            strict_refused = False
        except IOError as e:
            strict_refused = "expected 8" in str(e)
        check("artifact without the flag is refused (strict default)",
              strict_refused)

        os.environ["O2P_FC16_TOLERATE_TZ"] = "1"
        # 2. the artifact, flag on: accepted, AND the request that went out
        #    is byte-exactly the FC16 write it should be (finding 9: the old
        #    test never looked at the request at all).
        bus = ArtifactBus(ARTIFACT)
        bus.write(u.R_CMD, VALUES)
        check("artifact with the flag is accepted", True)
        check("and the request is the exact FC16 write PDU",
              bus.requests == [fc16_request(u.R_CMD, VALUES)])

        # 3. flag on but the 9th byte is not 0x00: not the known artifact.
        try:
            ArtifactBus(NINE_NOT_ZERO).write(u.R_CMD, VALUES)
            nonzero_refused = False
        except IOError:
            nonzero_refused = True
        check("9 bytes ending 0x01 refused even with the flag",
              nonzero_refused)

        # 4. flag on, 10 bytes: two trailing bytes is a different disease.
        try:
            ArtifactBus(TEN_BYTES).write(u.R_CMD, VALUES)
            ten_refused = False
        except IOError:
            ten_refused = True
        check("10 bytes refused even with the flag", ten_refused)

        # 5. flag on, clean 8-byte echo: unchanged path.
        ArtifactBus(echo_frame(u.R_CMD, len(VALUES))).write(u.R_CMD, VALUES)
        check("clean 8-byte echo accepted with the flag", True)

        # 6. CRC-VALID echo of the WRONG register: the tolerance must not
        #    mask a write that landed somewhere else.
        try:
            ArtifactBus(WRONG_ADDR).write(u.R_CMD, VALUES)
            wrong_addr_caught = False
        except IOError as e:
            wrong_addr_caught = "echoed addr" in str(e)
        check("CRC-valid wrong-register echo still caught",
              wrong_addr_caught)

        # 7. CRC-VALID echo with a short count: same, for the count check.
        try:
            ArtifactBus(WRONG_COUNT).write(u.R_CMD, VALUES)
            wrong_count_caught = False
        except IOError as e:
            wrong_count_caught = "echoed addr" in str(e) or "count" in str(e)
        check("CRC-valid short-count echo still caught",
              wrong_count_caught)
    finally:
        if saved is None:
            os.environ.pop("O2P_FC16_TOLERATE_TZ", None)
        else:
            os.environ["O2P_FC16_TOLERATE_TZ"] = saved

    if FAILURES:
        print("!! %d failed" % len(FAILURES))
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
