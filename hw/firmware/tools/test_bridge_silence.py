#!/usr/bin/env python3
"""BLE mailbox wire-silence maps to NoReply, 2026-09-11.

Bench evidence (farmgw keeper.log 12:37, the bridge probe behind /update):
the node reports WIRE silence - it watched the RS-485 and nothing answered
at slave 250 - back over the BLE mailbox as

    BleBusError("the probe did not answer (bus silence)")

which is an IOError (o2p_ble_link.py:134, and its own comment at the raise
site says exactly this: "Length 0 is the node saying the BUS said nothing,
which is different from the node not answering"). o2p_update.py's Bus._txn
let that IOError surface to bridge_status, which treats IOError as "a reply
came back but did not decode" - and answered "could not rule out a bridge
in the path" on a bench with no bridge on it, keeping the /update speed-up
off with a wrong reason.

The fix maps that one error to NoReply - no bytes came back, nobody is on
that address - which is the semantics the serial path always had.

REFUSALS ARE NOT SILENCE (codex review 2026-09-11, bg-12 P1): the node
sends the same zero-length notification when it REFUSES the exchange (bus
unclaimed, build cannot drive RS-485 - bleota.cpp:791) and the link stamps
those "bus silence" too, with the refusal detail left on its _status
channel. A refused BOOT read as NoReply becomes "BOOT usually LANDS" and a
180-s verify wait. The mapping therefore passes the error through
untouched whenever a BUS FAIL line is pending on the link.

These tests pin:
  the mailbox silence error, no refusal pending  -> NoReply
  the same error WITH a pending BUS FAIL         -> still an IOError
  a decode-fault IOError (not silence)           -> still an IOError
  three silences at the bridge address           -> bridge_status says
                                                    "absent" (the
                                                    direct-line branch),
                                                    in exactly
                                                    BRIDGE_PROBES exchanges
  silence, silence, then a bridge IDENT reply    -> present (the probes
                                                    really run in order)
  silence, then a decode fault                   -> unknowable (a real
                                                    reply that failed)
"""

import struct

import o2p_update as U


class FakeLink(object):
    """Records every exchange; plays back a scripted per-exchange behavior.

    behavior: callable(nth, adu) -> bytes | raises. `nth` is the 1-based
    exchange counter, so scripts can differ by probe. `_status` mimics the
    real link's status channel, which is where refusal evidence sits.
    """

    def __init__(self, behavior, status=()):
        self.behavior = behavior
        self.exchanges = []
        self._status = list(status)

    def exchange(self, adu, expect_len):
        self.exchanges.append(adu)
        return self.behavior(len(self.exchanges), adu)


def with_crc(payload):
    return payload + struct.pack("<H", U.crc16(payload))


def silent(nth, adu):
    raise IOError("the probe did not answer (bus silence)")


def main():
    ok = [0]

    def check(cond, label):
        print("  %s: %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            ok[0] = 1

    # Wire silence, nothing refused: NoReply with the evidence message.
    link = FakeLink(silent)
    bus = U.Bus(link, 250)
    try:
        bus.read(0, 4)
        check(False, "silence raises")
    except U.NoReply as exc:
        check("bus silence" in str(exc),
              "mailbox silence -> NoReply with the evidence message")
    except Exception as exc:
        check(False, "mailbox silence -> NoReply (got %r)" % exc)

    # The SAME error with a refusal pending on the status channel is NOT
    # silence - it must pass through as the IOError it is (bg-12 P1).
    link = FakeLink(silent,
                    status=["BUS FAIL bus not claimed - open the session "
                            "with CTRL_F_CLAIM_BUS"])
    bus = U.Bus(link, 250)
    try:
        bus.read(0, 4)
        check(False, "a refusal raises")
    except U.NoReply:
        check(False, "a refusal is not mapped to NoReply")
    except IOError as exc:
        check("bus silence" in str(exc),
              "a pending BUS FAIL keeps the refusal an IOError")

    # Anything else an IOError can mean is a real reply that failed to
    # decode - it must NOT become silence either.
    def crc_garbage(nth, adu):
        raise IOError("bad CRC in reply: fa02")
    bus = U.Bus(FakeLink(crc_garbage), 250)
    try:
        bus.read(0, 4)
        check(False, "a decode fault raises")
    except U.NoReply:
        check(False, "a decode fault stays an IOError, not NoReply")
    except IOError as exc:
        check("bad CRC" in str(exc), "a decode fault stays an IOError")

    # The case that started this: nothing at 250, the node says so three
    # times -> the bridge is ABSENT, not unknowable - and it took exactly
    # BRIDGE_PROBES exchanges to say so (bg-12 P3: the verdict must be
    # earned by the probes, not asserted).
    link = FakeLink(silent)
    is_bridge, version, bus_baud = U.bridge_status(link, 3)
    check(is_bridge is False and len(link.exchanges) == U.BRIDGE_PROBES,
          "wire silence at 250 -> no bridge in exactly %d exchanges "
          "(got %d)" % (U.BRIDGE_PROBES, len(link.exchanges)))

    # Silence, silence, then a real bridge IDENT reply: present - the
    # probes really run in order and a late answer still counts.
    n_fields = len(U.BRIDGE_FIELDS)
    regs = [0] * n_fields
    regs[0] = U.BRIDGE_IDENT
    regs[1] = U.BRIDGE_VERSION_RERATEABLE

    def late_ident(nth, adu):
        if nth < 3:
            raise IOError("the probe did not answer (bus silence)")
        body = bytes([250, 3, 2 * n_fields]) + b"".join(
            struct.pack(">H", r) for r in regs)
        return with_crc(body)
    link = FakeLink(late_ident)
    is_bridge, version, bus_baud = U.bridge_status(link, 3)
    check(is_bridge is True and version == U.BRIDGE_VERSION_RERATEABLE,
          "silence twice then an IDENT reply -> the bridge is present "
          "(got %r, v%s)" % (is_bridge, version))

    # Silence, then a decode fault: unknowable - a reply that failed to
    # decode is evidence, not absence.
    def silent_then_garbage(nth, adu):
        if nth == 1:
            raise IOError("the probe did not answer (bus silence)")
        raise IOError("bad CRC in reply: fa02")
    link = FakeLink(silent_then_garbage)
    is_bridge, version, bus_baud = U.bridge_status(link, 3)
    check(is_bridge is None,
          "silence then a decode fault -> unknowable, not absent")

    # And the direct-line verdict never blames a phantom bridge.
    line, why_not = U.retimable_line(FakeLink(silent), 3)
    # FakeLink has no set_baud, so the honest refusal is about the
    # transport - never "could not rule out a bridge".
    check(line is None and "could not rule out" not in why_not,
          "direct line verdict is the transport's own limit, not a phantom "
          "unknowable bridge (%r)" % why_not)

    # 2026-09-13 (Fab: "there's no bridge, fix the keeper", "there will be no
    # more bridge"): by DEFAULT the slave-250 probe does not run - not one
    # exchange - and a link that can be retimed is the direct line.
    class Retimable(FakeLink):
        baud = 9600

        def set_baud(self, rate):
            self.baud = rate

    def must_not_exchange(nth, adu):
        raise AssertionError("the bridge probe ran")
    link = Retimable(must_not_exchange)
    line, why_not = U.retimable_line(link, 3)
    check(line is link and why_not is None and not link.exchanges,
          "default -> the direct line, with zero exchanges "
          "(%r, %r, %d exchanges)" % (line, why_not, len(link.exchanges)))
    # ...and asking for the legacy probe explicitly still runs it in full.
    link = Retimable(silent)
    line, why_not = U.retimable_line(link, 3, assume_no_bridge=False)
    check(line is link and len(link.exchanges) == U.BRIDGE_PROBES,
          "assume_no_bridge=False still probes %d times before taking the "
          "direct line (got %d)" % (U.BRIDGE_PROBES, len(link.exchanges)))

    print("test_bridge_silence: %s" % ("PASS" if ok[0] == 0 else "FAIL"))
    return ok[0]


if __name__ == "__main__":
    raise SystemExit(main())
