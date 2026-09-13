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
# FAST is the fastest rate the tool knows. It read 38400/code 2 here long
# after 115200 (code 3) joined BAUD_CODES on 2026-09-09, and this whole file
# failed 30 checks unnoticed until 2026-09-13.
SLOW, FAST = 9600, 115200
SLOW_CODE, FAST_CODE = 0, 3


class FakeProbe:
    """The three config registers the negotiation touches, and nothing else."""

    def __init__(self, baud_code=SLOW_CODE, refuse=False, deaf_at=None,
                 drop_write_acks=0, drop_writes=0, drop_reads=0,
                 silent=False, two_way=True):
        # FW 0x001D's probation: a nonce published at each switch, confirmed
        # only by its echo. two_way=False is the older firmware, which has no
        # such register and confirms on any frame arriving.
        self.two_way = two_way
        self.nonce = 0
        self.acked = False
        self.probation = False
        self.nonces_issued = 0
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

    def arm(self):
        """A switch went live: publish a fresh nonce, forget any old proof."""
        self.nonces_issued += 1
        self.nonce = 0x1230 + self.nonces_issued
        self.acked = False
        self.probation = True

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
                elif a in (u.R_PROBATION_NONCE, u.R_PROBATION_ACK) \
                        and self.two_way:
                    regs.append(self.nonce if a == u.R_PROBATION_NONCE
                                else (1 if self.acked else 0))
                else:
                    return bytes([0x83, 2])
            return (bytes([3, 2 * count])
                    + b"".join(struct.pack(">H", v) for v in regs))
        if func == 16:
            addr, count = struct.unpack(">HH", pdu[1:5])
            values = [struct.unpack(">H", pdu[6 + 2 * i:8 + 2 * i])[0]
                      for i in range(count)]
            if addr == u.R_PROBATION_ACK and count == 1 and self.two_way:
                if not (self.probation and self.nonce
                        and values[0] == self.nonce):
                    return bytes([0x90, 3])
                # Confirmed: the firmware closes the question at once here;
                # the real probe does it on its next main-loop pass.
                self.acked = True
                self.probation = False
                self.nonce = 0
                return struct.pack(">BHH", 16, addr, count)
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
                 bridge_garbage=False, bridge_short=False, bridge_version=1,
                 bridge_deaf=False, bridge_readback_lost=0):
        self.probe = probe
        # `baud` is THIS END of the lead. With a bridge in the path that is the
        # host lead, which must never move; the cable is `bus_baud`, and only
        # the bridge can move it.
        self.baud = baud
        self.bridge = bridge
        self.bridge_version = bridge_version
        self.bridge_deaf = bridge_deaf    # accepts the write, does not act
        # First N read-backs of the bus-rate register are lost. The write still
        # ACTS -- this is the case where a failure does not mean no change.
        self.bridge_readback_lost = bridge_readback_lost
        self.bus_baud = baud
        self.bridge_retimes = []
        self.bridge_lost = bridge_lost        # first N bridge replies dropped
        self.bridge_garbage = bridge_garbage  # answers, but not as a bridge
        self.bridge_short = bridge_short      # answers with a fragment
        self.retimes = []
        # A rate at which the probe HEARS but its replies never arrive: the
        # one-way link of 2026-09-13 13:09 on probe 3.
        self.mute_at = None
        # Drop the reply to the first N probation ACK writes (the write lands).
        self.drop_ack_replies = 0

    def set_baud(self, baud):
        self.baud = baud
        self.retimes.append(baud)

    def wire_baud(self):
        """The rate the PROBE actually sees. Not the same object as this end
        once a bridge is forwarding, which is the whole point of the case."""
        return self.bus_baud if self.bridge else self.baud

    def _bridge_reply(self, addr, pdu=b""):
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
        if pdu[:1] == b"\x10":
            # FC16 to the bridge: the only writable register is the bus rate.
            reg, count = struct.unpack(">HH", pdu[1:5])
            val = struct.unpack(">H", pdu[6:8])[0]
            if reg != u.BRIDGE_REG_BUS_BAUD or count != 1:
                rsp = bytes([addr, 0x90, 2])
                return rsp + struct.pack("<H", u.crc16(rsp))
            if self.bridge_version < u.BRIDGE_VERSION_RERATEABLE:
                rsp = bytes([addr, 0x90, 1])   # illegal function, as v1 does
                return rsp + struct.pack("<H", u.crc16(rsp))
            if not self.bridge_deaf:
                self.bus_baud = val * 100
                self.bridge_retimes.append(self.bus_baud)
            rsp = bytes([addr, 0x10]) + pdu[1:5]
            return rsp + struct.pack("<H", u.crc16(rsp))
        regs = [u.BRIDGE_IDENT, self.bridge_version, 0, 0, 0, 0,
                self.bus_baud // 100, 0x0202]
        # Honour the requested window rather than always sending the whole
        # block: the retimer reads back ONE register, and a fake that answered
        # a one-register read with eight would fail Bus.read's shape check for
        # a reason the real bridge never produces.
        first, count = 0, len(regs)
        if len(pdu) >= 5 and pdu[0] == 3:
            first, count = struct.unpack(">HH", pdu[1:5])
            if (first == u.BRIDGE_REG_BUS_BAUD and count == 1
                    and self.bridge_readback_lost > 0):
                self.bridge_readback_lost -= 1
                return b""
        if first + count > len(regs):
            rsp = bytes([addr, 0x83, 2])
            return rsp + struct.pack("<H", u.crc16(rsp))
        window = regs[first:first + count]
        rsp = (bytes([addr, 3, 2 * len(window)])
               + b"".join(struct.pack(">H", v) for v in window))
        return rsp + struct.pack("<H", u.crc16(rsp))

    def exchange(self, adu, expect_len):
        del expect_len
        addr, pdu = adu[0], adu[1:-2]
        if addr == u.BRIDGE_ADDR:
            return self._bridge_reply(addr, pdu)
        if addr != self.probe.addr:
            return b""
        # The rate is the wire. A frame sent at the wrong one is not heard,
        # and the probe's reply to a frame it never heard does not exist.
        if self.wire_baud() != u.BAUD_CODES[self.probe.baud_code]:
            return b""
        if (self.probe.deaf_at is not None
                and self.wire_baud() == self.probe.deaf_at):
            return b""
        rsp_pdu = self.probe.frame(pdu)
        pending = None
        if hasattr(self.probe, "pending_code"):
            pending = self.probe.pending_code
            del self.probe.pending_code
        out = b""
        is_ack = (pdu[:1] == b"\x10" and len(pdu) >= 3
                  and struct.unpack(">H", pdu[1:3])[0] == u.R_PROBATION_ACK)
        if rsp_pdu is not None:
            # Dropping the ACK of a baud WRITE specifically: that is the loss
            # the tool cannot resolve by assumption, because the probe has
            # already acted on the frame it is not confirming.
            if self.mute_at is not None and self.wire_baud() == self.mute_at:
                pass                   # heard, served, the reply lost
            elif is_ack and self.drop_ack_replies > 0:
                self.drop_ack_replies -= 1
            elif self.probe.drop_write_acks > 0 and rsp_pdu[0] == 16:
                self.probe.drop_write_acks -= 1
            else:
                rsp = bytes([addr]) + rsp_pdu
                out = rsp + struct.pack("<H", u.crc16(rsp))
        if pending is not None:
            self.probe.baud_code = pending
            if self.probe.two_way:
                self.probe.arm()
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
    # The bridge probe is off by default since 2026-09-13 ("there will be no
    # more bridge"). A fake line that MODELS a bridge asks for the legacy
    # probe, so those cases still test what they were written to test.
    models_bridge = any(getattr(link, k, False)
                        for k in ("bridge", "bridge_garbage", "bridge_short"))
    return u.negotiate_baud(link, u.Bus(link, PROBE_ADDR), home_code,
                            settle=0.0, assume_no_bridge=not models_bridge)


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

    # A v1 bridge forwards at a rate compiled into it. Nothing may move.
    p = FakeProbe()
    line = FakeLine(p, bridge=True)
    case("v1 bridge in the path", p, line, SLOW, SLOW_CODE, False)
    check("v1 bridge in the path: no write was attempted", p.writes == [],
          "wrote %r" % (p.writes,))

    # A v2 bridge CAN be moved, and this is the case the change exists for.
    # What has to be true is not merely that the probe ends up fast: it is that
    # the cable moved and THIS END DID NOT. Retiming the host lead to follow
    # the probe would cut the only connection that still works.
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_version=2)
    restore = case("v2 bridge is re-rated", p, line, SLOW, FAST_CODE, True)
    check("v2 bridge: the cable moved to %d" % FAST, line.bus_baud == FAST,
          "cable is at %d" % line.bus_baud)
    check("v2 bridge: the host lead never moved",
          line.retimes == [], "host lead retimed %r" % (line.retimes,))
    check("v2 bridge: the bridge was told once, going up",
          line.bridge_retimes == [FAST], "%r" % (line.bridge_retimes,))
    restore()
    check("v2 bridge: the probe is back at %d" % SLOW,
          p.baud_code == SLOW_CODE, "probe at %d" % p.baud_code)
    check("v2 bridge: the cable is back at %d" % SLOW,
          line.bus_baud == SLOW, "cable at %d" % line.bus_baud)

    # A bridge that ACCEPTS the write and does not act on it. The FC16 echo
    # confirms the address and the count, never the value, so a bridge that
    # answered and stayed put would look identical to one that moved -- and the
    # tool would then push into a cable at a rate nothing on it is using. The
    # read-back is what makes the two distinguishable; the probe must be found
    # and put back, not left fast behind a slow cable.
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_version=2, bridge_deaf=True)
    # The probe ends up fast behind a slow cable and cannot be reached to be put
    # back -- the one outcome this design cannot avoid from here, and the exact
    # reason serial_probation.h exists. Two things are required of it: that the
    # restore has already been RUN and reported (so no callable is handed back
    # for a caller to run again), and that nothing was raised -- the caller
    # asked for a push, not for a cable diagnosis.
    restore = case("v2 bridge that does not act", p, line, SLOW, FAST_CODE,
                   False)
    check("deaf bridge: the cable never moved", line.bus_baud == SLOW,
          "cable at %d" % line.bus_baud)
    check("deaf bridge: nothing was raised at the caller", restore is None)

    # A LOST READ-BACK IS NOT A FAILED WRITE. The bridge acts, and only the
    # confirmation is lost. Re-reading is idempotent, so set_baud asks again
    # rather than reporting a failure that would send the restore hunting for a
    # probe at a rate the cable is no longer on.
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_version=2,
                    bridge_readback_lost=u.READBACK_ATTEMPTS - 1)
    case("v2 bridge whose read-back is lost", p, line, SLOW, FAST_CODE, True)
    check("lost read-back: the cable still moved", line.bus_baud == FAST,
          "cable at %d" % line.bus_baud)
    check("lost read-back: the retimer knows where it is", line.bridge_retimes
          == [FAST], "%r" % (line.bridge_retimes,))

    # And when the read-back never comes back, set_baud raises -- but the write
    # may still have acted, so resync must PROBE the candidate rather than skip
    # it. Skipping is how an unconfirmed success becomes "found nowhere".
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_version=2,
                    bridge_readback_lost=99)
    restore = case("v2 bridge whose read-back never returns", p, line, SLOW,
                   FAST_CODE, True)
    check("read-back never returns: the cable did move anyway",
          line.bus_baud == FAST, "cable at %d" % line.bus_baud)
    # And the transfer goes ahead at the fast rate. Nothing here trusted the
    # unconfirmed write: confirm_baud() asked the PROBE, which is the only end
    # whose answer settles what rate the cable is actually running at. An
    # earlier draft of this case expected the speed-up to be abandoned, which
    # is what skipping the probe would have produced.
    restore()
    check("read-back never returns: the restore still finds the probe",
          p.baud_code == SLOW_CODE, "probe at %d" % p.baud_code)
    check("read-back never returns: and puts the cable back",
          line.bus_baud == SLOW, "cable at %d" % line.bus_baud)

    # A bridge running at a rate this firmware has no code for. There would be
    # nowhere defined to put the cable back, so it is not touched.
    p = FakeProbe()
    line = FakeLine(p, bridge=True, bridge_version=2)
    line.bus_baud = 57600
    case("v2 bridge on an unknown rate", p, line, SLOW, SLOW_CODE, False)
    check("unknown bridge rate: no write was attempted", p.writes == [],
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

    # No set_baud at all: the --swd transport, with nothing else to move.
    p = FakeProbe()
    line = SwdLikeLine(p)
    case("no retimable transport", p, line, SLOW, SLOW_CODE, False)
    check("no retimable transport: no write was attempted", p.writes == [])

    # --swd THROUGH a v2 bridge is retimable after all: the mailbox answers the
    # bridge's own address, so the cable can be moved by a register write even
    # though this transport has no rate of its own. This is the one case whose
    # answer the change reverses, and it used to be refused before the bridge
    # was ever asked.
    #
    # NOTE WHAT THIS DOES NOT REACH. It calls the negotiation helper directly
    # with a home code already in hand, so it says nothing about whether run()
    # gets that far -- and run() did NOT, because it derived home_code from
    # `hasattr(link, "set_baud")`, which SwdLink has none of. Found by review,
    # 2026-09-08. run() now derives it from `line`; test_run_smoke.py covers
    # that run() is reachable at all, and this stays a helper-level case.
    p = FakeProbe()
    line = SwdLikeLine(p, bridge=True, bridge_version=2)
    case("swd through a v2 bridge", p, line, SLOW, FAST_CODE, True)
    check("swd through a v2 bridge: the cable moved", line.bus_baud == FAST,
          "cable is at %d" % line.bus_baud)

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

    # -- the two-way probation (FW 0x001D) --------------------------------
    # The speed-up proves the new rate BOTH ways: this end hears the probe,
    # and the probe learns it was heard by the echo of its nonce.
    print("-- two-way probation: a clean speed-up echoes the nonce")
    p = FakeProbe()
    line = FakeLine(p)
    restore = case("two-way speed-up", p, line, FAST, FAST_CODE, True)
    check("two-way speed-up: the fast rate's nonce was echoed",
          p.acked and not p.probation, "acked %r probation %r"
          % (p.acked, p.probation))

    # OLD FIRMWARE: no nonce register. The tool must not retime at all - on
    # that firmware one arriving frame confirms, so a one-way rate strands it.
    print("-- old firmware: no speed-up")
    p = FakeProbe(two_way=False)
    line = FakeLine(p)
    case("one-way firmware refused", p, line, SLOW, SLOW_CODE, False)
    check("one-way firmware: no baud write went out", p.writes == [],
          "wrote %r" % (p.writes,))

    # THE 13:09 LINK: at the fast rate the probe hears and its replies are
    # lost. The tool must never echo the nonce - it never read it - so on the
    # real firmware the probe reverts by itself in 10 s. The fake has no
    # timer, so the assertion is on the proof, which is the thing that was
    # wrong on 2026-09-13.
    print("-- a one-way fast rate is never proven")
    p = FakeProbe()
    line = FakeLine(p)
    line.mute_at = FAST
    restore = negotiate(line)
    check("one-way fast rate: the probe was never given the proof",
          not p.acked and p.probation,
          "acked %r probation %r" % (p.acked, p.probation))
    check("one-way fast rate: no restore promises a verified speed-up",
          restore is None or line.baud == SLOW, "line at %d" % line.baud)

    # The echo's REPLY is lost, but the write landed: resolved by asking, and
    # the speed-up still counts.
    print("-- a lost echo reply is resolved by asking")
    p = FakeProbe()
    line = FakeLine(p)
    line.drop_ack_replies = 1
    case("lost echo reply", p, line, FAST, FAST_CODE, True)
    check("lost echo reply: the probe holds the proof", p.acked)

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
