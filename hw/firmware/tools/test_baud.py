#!/usr/bin/env python3
"""Exercise o2p_update.py's baud negotiation against a fake probe and a fake
line, on the host, with no hardware and no bus.

    python3 tools/test_baud.py

What is being guarded is not the speed-up - that either works or the push runs
at 9600 and nobody is hurt. It is the FALLBACK. The tool writes a config
register on a probe that may be potted into a compost pile at the end of a lead
that cannot reset it, and every way that write can go sideways has to end with
the probe reachable again:

  * the write is refused,
  * the write lands but its acknowledgement is lost, so the tool does not know
    which rate the probe is on,
  * the RETRACTION is the frame that is lost - the case that costs the most,
    because by then the probe is already at the rate it must be talked down
    from,
  * the write lands and the cable will not carry the new rate,
  * a bench bridge is in the path, whose bus rate is compiled in and cannot
    follow the probe anywhere,
  * a previous run left the probe somewhere and this one has to find it.

The fake line drops every frame whose rate does not match the probe's, which is
what a real UART does with a mistimed frame, and it applies a baud change only
AFTER the reply has been handed back - which is what src/main.c does, and the
reason the switch is safe at all. A tool that retimed before the reply would
send its write into the void and fail every case here.

WHAT THIS FILE CANNOT TEST: whether `settle` is long enough for a real probe.
The fake's deferred switch is instantaneous, so a settle of zero passes here.

The real bound is NOT 0.2 s. serial_reconfig_pending is serviced first WITHIN
the deferred block, but the block also contains a flash page erase and the
SHT45 decreep pulse (`o2p_sht4x_heater_pulse`, over a second), and those delay
entry to the NEXT pass - so the probe can be up to a second or so late in
switching. What actually covers that is confirm_baud's retry budget:
VERIFY_ATTEMPTS tries per frame at the link timeout, about 3 s for the first
frame alone. `settle` only buys the common case a clean first attempt. Saying
"80 ms" here, as this file first did, quoted the wrong number by about 15x and
made a margin look designed that is in fact carried by the retries.

The frames are real: the fake speaks ADUs, so the tool's own Bus does the CRC,
the address check and the FC16 echo check exactly as it does on a cable.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import o2p_update as u                                        # noqa: E402

PROBE_ADDR = 3
SLOW, FAST = 9600, 38400
SLOW_CODE, FAST_CODE = 0, 2


class FakeProbe:
    """The three config registers the negotiation touches, and nothing else."""

    def __init__(self, baud_code=SLOW_CODE, refuse=False, deaf_at=None,
                 drop_write_acks=0, drop_writes=0, drop_reads=0,
                 silent=False):
        self.baud_code = baud_code
        self.addr = PROBE_ADDR
        self.parity_code = 2
        self.refuse = refuse            # answer exception 03 to a baud write
        self.deaf_at = deaf_at          # a rate at which it hears nothing
        # An ack lost AFTER the write took effect, versus a request lost
        # BEFORE it did. From the tool's end the two look identical, and they
        # leave the probe in opposite states - which is the entire reason the
        # recovery asks instead of assuming.
        self.drop_write_acks = drop_write_acks
        self.drop_writes = drop_writes
        self.drop_reads = drop_reads
        self.silent = silent            # never answers anything
        self.writes = []

    def frame(self, pdu):
        """Serve one PDU. Returns a response PDU, or None for silence."""
        if self.silent:
            return None
        func = pdu[0]
        if func == 3:
            if self.drop_reads > 0:
                self.drop_reads -= 1
                return None
            addr, count = struct.unpack(">HH", pdu[1:5])
            regs = []
            for a in range(addr, addr + count):
                if a == u.R_SLAVE_ADDR:
                    regs.append(self.addr)
                elif a == u.R_BAUD_CODE:
                    regs.append(self.baud_code)
                elif a == u.R_PARITY_CODE:
                    regs.append(self.parity_code)
                elif a == u.R_STATUS:
                    regs.append(0)
                else:
                    return bytes([0x83, 2])
            return (bytes([3, 2 * count])
                    + b"".join(struct.pack(">H", v) for v in regs))
        if func == 16:
            addr, count = struct.unpack(">HH", pdu[1:5])
            values = [struct.unpack(">H", pdu[6 + 2 * i:8 + 2 * i])[0]
                      for i in range(count)]
            if addr != u.R_BAUD_CODE or count != 1:
                return bytes([0x90, 2])
            if self.refuse:
                return bytes([0x90, 3])
            if self.drop_writes > 0:
                self.drop_writes -= 1
                return None            # never arrived: nothing changes at all
            self.writes.append(values[0])
            # The reply goes out at the OLD rate and the change takes effect
            # after it - src/main.c defers it until the transmitter is idle.
            # A fake that switched first would let a tool that retimes too
            # early pass.
            self.pending_code = values[0]
            return struct.pack(">BHH", 16, addr, count)
        return bytes([func | 0x80, 1])


class FakeLine:
    """A serial line with a rate, carrying frames only when both ends agree."""

    def __init__(self, probe, baud=SLOW, bridge=False, bridge_lost=0,
                 bridge_garbage=False, bridge_short=False):
        self.probe = probe
        self.baud = baud
        self.bridge = bridge
        self.bridge_lost = bridge_lost        # first N bridge replies dropped
        self.bridge_garbage = bridge_garbage  # answers, but not as a bridge
        self.bridge_short = bridge_short      # answers with a fragment
        self.retimes = []

    def set_baud(self, baud):
        self.baud = baud
        self.retimes.append(baud)

    def _bridge_reply(self, addr):
        if self.bridge_short:
            # Two bytes. Not silence - something on 250 began to answer - and
            # for a while this arrived as NoReply and was read as "no bridge".
            return b"\x01\x02"
        if self.bridge_garbage:
            # A well-formed frame from the right address whose CRC is wrong:
            # something IS on 250 and it is not a bridge this tool knows.
            rsp = bytes([addr, 3, 2]) + b"\x00\x00"
            return rsp + b"\xde\xad"
        if not self.bridge:
            return b""
        if self.bridge_lost > 0:
            self.bridge_lost -= 1
            return b""
        regs = [u.BRIDGE_IDENT, 1, 0, 0, 0, 0, SLOW // 100, 0x0202]
        rsp = (bytes([addr, 3, 2 * len(regs)])
               + b"".join(struct.pack(">H", v) for v in regs))
        return rsp + struct.pack("<H", u.crc16(rsp))

    def exchange(self, adu, expect_len):
        del expect_len
        addr, pdu = adu[0], adu[1:-2]
        if addr == u.BRIDGE_ADDR:
            return self._bridge_reply(addr)
        if addr != self.probe.addr:
            return b""
        # The rate is the wire. A frame sent at the wrong one is not heard,
        # and the probe's reply to a frame it never heard does not exist.
        if self.baud != u.BAUD_CODES[self.probe.baud_code]:
            return b""
        if self.probe.deaf_at is not None and self.baud == self.probe.deaf_at:
            return b""
        rsp_pdu = self.probe.frame(pdu)
        pending = None
        if hasattr(self.probe, "pending_code"):
            pending = self.probe.pending_code
            del self.probe.pending_code
        out = b""
        if rsp_pdu is not None:
            # Dropping the ACK of a baud WRITE specifically: that is the loss
            # the tool cannot resolve by assumption, because the probe has
            # already acted on the frame it is not confirming.
            if self.probe.drop_write_acks > 0 and rsp_pdu[0] == 16:
                self.probe.drop_write_acks -= 1
            else:
                rsp = bytes([addr]) + rsp_pdu
                out = rsp + struct.pack("<H", u.crc16(rsp))
        if pending is not None:
            self.probe.baud_code = pending
        return out

    def close(self):
        pass


class SwdLikeLine(FakeLine):
    """No set_baud, the way SwdLink has none."""
    set_baud = None


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def negotiate(link, home_code=SLOW_CODE):
    return u.negotiate_baud(link, u.Bus(link, PROBE_ADDR), home_code,
                            settle=0.0)


def case(name, probe, link, want_line, want_code, want_restore,
         home_code=SLOW_CODE):
    print("-- %s" % name)
    restore = negotiate(link, home_code)
    check("%s: line at %d" % (name, want_line), link.baud == want_line,
          "line is at %d" % link.baud)
    check("%s: probe at code %d" % (name, want_code),
          probe.baud_code == want_code, "probe is at %d" % probe.baud_code)
    check("%s: restore %s" % (name, "offered" if want_restore else "withheld"),
          (restore is not None) == want_restore)
    return restore


def main():
    # The one that pays for the change: 9600 up to 38400, confirmed by
    # content, and put back afterwards.
    p = FakeProbe()
    line = FakeLine(p)
    restore = case("plain speed-up", p, line, FAST, FAST_CODE, True)
    check("plain speed-up: restore reports the rate", restore() == SLOW)
    check("plain speed-up: line back at 9600", line.baud == SLOW,
          "line is at %d" % line.baud)
    check("plain speed-up: probe back at code 0", p.baud_code == SLOW_CODE)
    check("plain speed-up: wrote both codes, in order",
          p.writes == [FAST_CODE, SLOW_CODE], "wrote %r" % (p.writes,))

    # A lost acknowledgement. The write LANDED; the tool cannot know that from
    # the silence, so it must ask rather than assume - and asking finds the
    # probe at the new rate, which is a success, not a fallback.
    p = FakeProbe(drop_write_acks=1)
    line = FakeLine(p)
    restore = case("lost ack, switch landed", p, line, FAST, FAST_CODE, True)
    restore()
    check("lost ack: ends back at 9600",
          line.baud == SLOW and p.baud_code == SLOW_CODE)

    # THE EXPENSIVE ONE. The retraction's REQUEST is lost, so the probe never
    # sees it and stays at 38400 while this end has already retimed to 9600. A
    # single unretried write leaves it there. The cable has just carried 30 KiB
    # at 38400, so the rate is known good and one more try recovers.
    p = FakeProbe()
    line = FakeLine(p)
    restore = case("lost retraction request", p, line, FAST, FAST_CODE, True)
    p.drop_writes = 1
    check("lost retraction: recovered to 9600", restore() == SLOW)
    check("lost retraction: probe back at code 0", p.baud_code == SLOW_CODE)
    check("lost retraction: line back at 9600", line.baud == SLOW)

    # The retraction's ACK is lost instead. The probe DID move; a tool that
    # believed its own silence would report a stranded probe that is fine.
    p = FakeProbe()
    line = FakeLine(p)
    restore = case("lost retraction ack", p, line, FAST, FAST_CODE, True)
    p.drop_write_acks = 1
    check("lost retraction ack: still reports 9600", restore() == SLOW)
    check("lost retraction ack: probe is at code 0", p.baud_code == SLOW_CODE)

    # A cable that carries 9600 and not 38400. THIS IS THE RESIDUAL RISK, and
    # the test asserts the honest outcome rather than the comfortable one: the
    # probe took the write, it cannot hear the retraction at a rate it cannot
    # hear, and no fallback this end can reach it. What the tool owes here is
    # not a recovery it does not have - it is to stop, put its own line back
    # on 9600, and say that a reset undoes it, which is true only because the
    # change was never committed.
    #
    # src/serial_probation.h closes this from the firmware side: a probe from
    # 2026-09-08 onwards reverts by itself after ten seconds of silence. The
    # tool must still behave correctly against an older one, which is what is
    # asserted here.
    p = FakeProbe(deaf_at=FAST)
    line = FakeLine(p)
    case("cable will not hold 38400", p, line, SLOW, FAST_CODE, False)
    check("cable will not hold 38400: the retraction was attempted",
          p.writes == [FAST_CODE], "wrote %r" % (p.writes,))

    # A probe that refuses the write outright changed nothing, so neither may
    # this end.
    p = FakeProbe(refuse=True)
    line = FakeLine(p)
    case("probe refuses the write", p, line, SLOW, SLOW_CODE, False)

    # A bridge forwards at a rate compiled into it. Nothing may move.
    p = FakeProbe()
    line = FakeLine(p, bridge=True)
    case("bridge in the path", p, line, SLOW, SLOW_CODE, False)
    check("bridge in the path: no write was attempted", p.writes == [],
          "wrote %r" % (p.writes,))

    # ONE LOST FRAME MUST NOT LOOK LIKE "no bridge". A bridge is asked
    # BRIDGE_PROBES times before its silence is believed, because the cost of
    # getting this wrong is a probe stranded behind a 9600-only bridge.
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_lost=u.BRIDGE_PROBES - 1)
    case("bridge whose first replies are lost", p, line, SLOW, SLOW_CODE,
         False)
    check("bridge with lost replies: no write was attempted", p.writes == [])

    # Something on address 250 that is not a bridge. show_bridge() calls this
    # "something else is on that address" and refuses to proceed; this check
    # must not be more permissive than the diagnostic.
    p = FakeProbe()
    line = FakeLine(p, bridge_garbage=True)
    case("garbage on the bridge address", p, line, SLOW, SLOW_CODE, False)
    check("garbage on the bridge address: no write was attempted",
          p.writes == [])

    # A FRAGMENT on address 250. Two bytes is too short to carry a CRC, so it
    # used to be classified as silence alongside a genuine timeout - and
    # silence is what grants permission to write the baud register. Only a
    # zero-byte read is silence now.
    p = FakeProbe()
    line = FakeLine(p, bridge_short=True)
    case("a fragment on the bridge address", p, line, SLOW, SLOW_CODE, False)
    check("fragment on the bridge address: no write was attempted",
          p.writes == [], "wrote %r" % (p.writes,))

    # No set_baud at all: the --swd transport.
    p = FakeProbe()
    line = SwdLikeLine(p)
    case("no retimable transport", p, line, SLOW, SLOW_CODE, False)
    check("no retimable transport: no write was attempted", p.writes == [])

    # A probe that says nothing. An unreadable baud code is not permission to
    # write one.
    p = FakeProbe(silent=True)
    line = FakeLine(p)
    case("probe will not report its baud", p, line, SLOW, SLOW_CODE, False)
    check("silent probe: no write was attempted", p.writes == [])

    # Already fast AND already home: genuinely nothing to do.
    p = FakeProbe(baud_code=FAST_CODE)
    line = FakeLine(p, baud=FAST)
    case("already fast and already home", p, line, FAST, FAST_CODE, False,
         home_code=FAST_CODE)
    check("already fast and home: no write was attempted", p.writes == [])

    # Already fast but NOT home - an earlier run left it there. The speed-up
    # is a no-op, but the probe still has to be walked back to the bus rate,
    # so a restore must be offered.
    p = FakeProbe(baud_code=FAST_CODE)
    line = FakeLine(p, baud=FAST)
    restore = case("already fast, not home", p, line, FAST, FAST_CODE, True)
    check("already fast, not home: restore brings it home", restore() == SLOW)
    check("already fast, not home: probe at code 0", p.baud_code == SLOW_CODE)

    # A stranded probe, found. The operator runs the tool again with the
    # default --baud 9600 and the probe is not there; without this the run
    # dies with "no reply" and says nothing about the rate.
    p = FakeProbe(baud_code=FAST_CODE)
    line = FakeLine(p, baud=SLOW)
    print("-- rediscovering a stranded probe")
    found = u.find_probe(line, u.Bus(line, PROBE_ADDR), settle=0.0)
    check("stranded probe: found", found)
    check("stranded probe: line moved to 38400", line.baud == FAST,
          "line is at %d" % line.baud)

    # The whole point of finding it: HOME IS --baud, not wherever find_probe
    # landed. Deriving home from the moved line made this run confirm the
    # stranding it exists to undo - "already at the fastest this firmware
    # offers" - on a cable whose SMT100s are at 9600.
    p = FakeProbe(baud_code=FAST_CODE)
    line = FakeLine(p, baud=SLOW)
    u.find_probe(line, u.Bus(line, PROBE_ADDR), settle=0.0)
    restore = negotiate(line, home_code=SLOW_CODE)     # home from args.baud
    check("stranded probe: a restore is offered", restore is not None)
    if restore is not None:
        check("stranded probe: put back to 9600", restore() == SLOW)
        check("stranded probe: probe at code 0", p.baud_code == SLOW_CODE)

    # And not found: the line must be left where the operator put it, so the
    # next error message is about the settings they passed.
    p = FakeProbe(silent=True)
    line = FakeLine(p, baud=SLOW)
    found = u.find_probe(line, u.Bus(line, PROBE_ADDR), settle=0.0)
    check("no probe anywhere: reported not found", not found)
    check("no probe anywhere: line left at 9600", line.baud == SLOW,
          "line is at %d" % line.baud)

    # confirm_baud must survive routine noise. Requiring VERIFY_FRAMES
    # unblemished first-tries turns one dropped frame on a live cable into
    # "the probe did not come back", whose printed remedy is a power cycle.
    print("-- confirmation tolerates a lost frame")
    p = FakeProbe(drop_reads=1)
    line = FakeLine(p)
    check("one lost read does not fail the confirmation",
          u.confirm_baud(u.Bus(line, PROBE_ADDR), SLOW_CODE))
    # A WRONG value is not noise and is never retried.
    p = FakeProbe(baud_code=FAST_CODE)
    line = FakeLine(p, baud=FAST)
    check("a wrong value fails the confirmation immediately",
          not u.confirm_baud(u.Bus(line, PROBE_ADDR), SLOW_CODE))

    # "Fastest" is the highest RATE, not the highest CODE. A firmware that
    # appends a SLOWER code - src/modbus_rtu.c's transmit backstop already
    # warns about a 4800 entry - must not make this tool speed up to 4800.
    print("-- fastest is by rate, not by code")
    saved = u.BAUD_CODES
    try:
        u.BAUD_CODES = {0: 9600, 1: 19200, 2: 38400, 3: 4800}
        check("fastest_code ignores a slower high code",
              u.fastest_code() == 2, "picked %d" % u.fastest_code())
    finally:
        u.BAUD_CODES = saved

    # restore() runs from a finally. If it raised, it would replace whatever
    # actually went wrong with the push.
    print("-- restore over a dead probe")
    p = FakeProbe()
    line = FakeLine(p)
    restore = negotiate(line)
    p.silent = True
    try:
        check("restore over a dead probe does not raise", restore() is None)
    except BaseException as e:                               # noqa: BLE001
        check("restore over a dead probe does not raise", False, repr(e))

    print("all passed" if not FAILURES
          else "%d FAILED: %s" % (len(FAILURES), ", ".join(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
