#!/usr/bin/env python3
"""The push's first exchange settles and asks again, 2026-09-11.

Bench evidence (farmgw keeper.log, seven /update attempts 14:42-17:44): a
bridge-probe write timed out host-side while the node still queued it; the
push's R_BLOCK_MAX read went out behind it, was dropped by the node's flush
("BUS FLUSH 1 queued dropped") and handed the stale zero-length reply -
NoReply at 0 bytes on a healthy probe. See read_block_max in o2p_update.py.

These tests pin:
  silence once, then a real reply     -> the value, after one settle
  silence every time                  -> SystemExit after BLOCK_MAX_ATTEMPTS
                                         exchanges (never an endless loop,
                                         never a made-up block size)
  a refusal-shaped IOError, then reply -> retried too (a stale reply can
                                         arrive as any decode fault)
  a Modbus exception                  -> NOT retried: a real reply
  push() itself goes through the helper (the known-bad: the old direct read
                                         dies on the first silence)
"""

import struct

import o2p_update as U


class FakeLink(object):
    def __init__(self, behavior):
        self.behavior = behavior
        self.exchanges = []
        self._status = []

    def exchange(self, adu, expect_len):
        self.exchanges.append(adu)
        return self.behavior(len(self.exchanges), adu)


def with_crc(payload):
    return payload + struct.pack("<H", U.crc16(payload))


def block_max_reply(addr, words):
    return with_crc(bytes([addr, 3, 2]) + struct.pack(">H", words))


def main():
    ok = [0]

    def check(cond, label):
        print("  %s: %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            ok[0] = 1

    sleeps = []

    def silence_then_reply(nth, adu):
        if nth == 1:
            raise IOError("the probe did not answer (bus silence)")
        return block_max_reply(3, 120)
    link = FakeLink(silence_then_reply)
    got = U.read_block_max(U.Bus(link, 3), sleep=sleeps.append)
    check(got == 240 and len(link.exchanges) == 2
          and sleeps == [U.BLOCK_MAX_SETTLE_S],
          "silence once then a reply -> 240 B after one settle "
          "(got %r, %d exchanges, sleeps %r)"
          % (got, len(link.exchanges), sleeps))

    sleeps = []

    def always_silent(nth, adu):
        raise IOError("the probe did not answer (bus silence)")
    link = FakeLink(always_silent)
    try:
        U.read_block_max(U.Bus(link, 3), sleep=sleeps.append)
        check(False, "persistent silence raises")
    except SystemExit as exc:
        check(len(link.exchanges) == U.BLOCK_MAX_ATTEMPTS
              and len(sleeps) == U.BLOCK_MAX_ATTEMPTS - 1
              and "block-size read" in str(exc.code),
              "persistent silence -> SystemExit after %d exchanges "
              "(got %d)" % (U.BLOCK_MAX_ATTEMPTS, len(link.exchanges)))

    def garbage_then_reply(nth, adu):
        if nth == 1:
            raise IOError("bad CRC in reply: fa02")
        return block_max_reply(3, 120)
    link = FakeLink(garbage_then_reply)
    got = U.read_block_max(U.Bus(link, 3), sleep=lambda s: None)
    check(got == 240, "a decode fault then a reply -> retried (got %r)" % got)

    def exception_reply(nth, adu):
        return with_crc(bytes([3, 0x83, 2]))
    link = FakeLink(exception_reply)
    try:
        U.read_block_max(U.Bus(link, 3), sleep=lambda s: None)
        check(False, "a Modbus exception raises")
    except U.ModbusException:
        check(len(link.exchanges) == 1,
              "a Modbus exception is a real reply - not retried "
              "(%d exchanges)" % len(link.exchanges))

    # push() uses the helper: the first silence no longer kills it. Stop the
    # push right after the block-size check with an oversized block request,
    # which is the first thing push() refuses on the advertised value.
    link = FakeLink(silence_then_reply)
    orig_sleep = U.time.sleep
    U.time.sleep = lambda s: None
    try:
        try:
            U.push(U.Bus(link, 3), b"\xff" * 4096, 480, 0)
            check(False, "push refuses an oversized block")
        except SystemExit as exc:
            check("at most 240 bytes" in str(exc.code),
                  "push survives a first-read silence and reaches the "
                  "block-size check (%r)" % exc.code)
    finally:
        U.time.sleep = orig_sleep

    print("test_push_first_read_settles: %s"
          % ("PASS" if ok[0] == 0 else "FAIL"))
    return ok[0]


if __name__ == "__main__":
    raise SystemExit(main())
