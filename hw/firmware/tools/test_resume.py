#!/usr/bin/env python3
"""Exercise o2p_update.py's resume decision against a fake probe, on the host,
with no hardware and no bus.

The decision this file guards is cheap to get wrong and expensive to get wrong:
resuming into a staging slot that holds a DIFFERENT image splices two binaries.
COMMIT's CRC would catch the splice, but only after the entire transfer has
been spent - about four minutes on the wire, and days on the `A8` downlink the
protocol was shaped for. So the interesting tests here are not the happy
resume; they are the five ways the tool must decline one.

The fake is a re-implementation of src/update.c's register model, not a
recording: the tests assert on what the tool WRITES (was BEGIN sent? which
sequence numbers went out? how many payload bytes?), which is the only part
that matters to a probe.

    python3 tools/test_resume.py
"""
import binascii
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import o2p_update as u                                        # noqa: E402

BLOCK = 240
IMAGE = bytes((i * 7 + 3) & 0xFF for i in range(30 * 1024))   # 30720, 128 blocks


def crc_of(image):
    if len(image) % u.ALIGN:
        image += b"\xff" * (u.ALIGN - len(image) % u.ALIGN)
    return len(image), binascii.crc32(image) & 0xFFFFFFFF


class FakeProbe:
    """src/update.c's register model, enough of it to drive the tool.

    Erase is instant here. On the probe it is one page per service pass so the
    bus stays served; the tool's only view of that is wait_for() polling
    STATUS, and a fake that reaches READY on the first poll exercises the same
    code path in the tool.
    """

    def __init__(self, state=u.STATES.index("IDLE"), pending_len=0,
                 pending_crc=0, received=0, next_seq=0, raise_on=None,
                 raises=1):
        self.state = state
        self.error = 0
        self.pending_len = pending_len
        self.pending_crc = pending_crc
        self.declared_len = pending_len
        self.declared_crc = pending_crc
        self.received = received
        self.next_seq = next_seq
        self.last_block_bytes = 0
        # A register address that refuses to be read, `raises` times. One-shot
        # by default: a probe that never answers STATUS again is a dead link,
        # not a resume decision, and the tool is right to sit in wait_for()
        # until it times out. What is being tested here is the DECISION.
        self.raise_on = raise_on
        self.raises_left = raises
        self.begins = 0
        self.commits = 0
        self.seqs = []                    # sequence number of every block
        self.payload_bytes = 0

    # ---- the 0x0050 block, as read_reg() computes it
    def _reg(self, a):
        if a == u.R_STATUS:
            return (self.state << 8) | self.error
        if a == u.R_BLOCK_MAX:
            return 120                              # O2P_REG_UPD_DATA_MAX
        if a == u.R_CMD:
            return 0                                # an edge, not state
        if a == u.R_LEN_HI:
            return self.pending_len >> 16
        if a == u.R_LEN_HI + 1:
            return self.pending_len & 0xFFFF
        if a == u.R_CRC_HI:
            return self.pending_crc >> 16
        if a == u.R_CRC_HI + 1:
            return self.pending_crc & 0xFFFF
        if a == u.R_RECV_HI:
            return self.received >> 16
        if a == u.R_RECV_HI + 1:
            return self.received & 0xFFFF
        if a == u.R_NEXT_SEQ:
            return self.next_seq
        return 0

    def read(self, addr, count):
        for i in range(count):
            if (self.raise_on is not None and addr + i == self.raise_on
                    and self.raises_left > 0):
                self.raises_left -= 1
                raise IOError("no reply (got 0 bytes)")
        return [self._reg(addr + i) for i in range(count)]

    def write(self, addr, values):
        if addr >= u.R_DATA:
            return self._write_data(addr, values)
        return self._write_control(addr, values)

    def _write_control(self, addr, values):
        cmd = None
        pend_len, pend_crc = self.pending_len, self.pending_crc
        for i, v in enumerate(values):
            a = addr + i
            if a == u.R_CMD:
                cmd = v
            elif a == u.R_LEN_HI:
                pend_len = (v << 16) | (pend_len & 0xFFFF)
            elif a == u.R_LEN_HI + 1:
                pend_len = (pend_len & 0xFFFF0000) | v
            elif a == u.R_CRC_HI:
                pend_crc = (v << 16) | (pend_crc & 0xFFFF)
            elif a == u.R_CRC_HI + 1:
                pend_crc = (pend_crc & 0xFFFF0000) | v
            else:
                raise u.ModbusException(2)
        # Two passes: the numbers land before the command that consumes them,
        # whatever order they fall in the frame.
        self.pending_len, self.pending_crc = pend_len, pend_crc
        if cmd is None:
            return
        if cmd == u.CMD_BEGIN:
            self.begins += 1
            self.declared_len = self.pending_len
            self.declared_crc = self.pending_crc
            self.received = 0
            self.next_seq = 0
            self.last_block_bytes = 0
            self.state = u.STATES.index("READY")     # erase, instantly
            self.error = 0
        elif cmd == u.CMD_COMMIT:
            if self.state != u.STATES.index("RECEIVING"):
                raise u.ModbusException(3)
            if self.received != self.declared_len:
                self.error = u.ERRORS.index("LENGTH")
                raise u.ModbusException(3)
            self.commits += 1
            self.state = u.STATES.index("STAGED")
            self.error = 0
        elif cmd in (u.CMD_BOOT, u.CMD_ABORT, u.CMD_STAY):
            pass
        else:
            raise u.ModbusException(3)

    def _write_data(self, addr, values):
        if addr != u.R_DATA:
            raise u.ModbusException(2)
        if self.state not in (u.STATES.index("READY"),
                              u.STATES.index("RECEIVING")):
            self.error = u.ERRORS.index("STATE")
            raise u.ModbusException(3)
        seq = values[0]
        payload = (len(values) - 1) * 2
        if self.next_seq > 0 and seq == (self.next_seq - 1) & 0xFFFF:
            if payload != self.last_block_bytes:
                self.error = u.ERRORS.index("SEQUENCE")
                raise u.ModbusException(3)
            return                                   # a lost ACK, not an error
        if seq != self.next_seq:
            self.error = u.ERRORS.index("SEQUENCE")
            raise u.ModbusException(3)
        if payload > self.declared_len - self.received:
            self.error = u.ERRORS.index("LENGTH")
            raise u.ModbusException(3)
        self.seqs.append(seq)
        self.payload_bytes += payload
        self.received += payload
        self.last_block_bytes = payload
        self.next_seq += 1
        self.state = u.STATES.index("RECEIVING")
        self.error = 0


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def run_push(probe, image=IMAGE, block_bytes=BLOCK, no_resume=False):
    u.push(probe, bytes(image), block_bytes, 3, no_resume=no_resume)


def mid_transfer(seq, length=None, crc=None, block_bytes=BLOCK,
                 received=None):
    """A probe that is RECEIVING, `seq` blocks into this exact image."""
    n, c = crc_of(IMAGE)
    return FakeProbe(state=u.STATES.index("RECEIVING"),
                     pending_len=n if length is None else length,
                     pending_crc=c if crc is None else crc,
                     received=(seq * block_bytes) if received is None
                              else received,
                     next_seq=seq)


# ---------------------------------------------------------------- the tests

def test_a_clean_first_push_still_begins():
    p = FakeProbe()
    run_push(p)
    n, _ = crc_of(IMAGE)
    check("a clean push sends BEGIN", p.begins == 1, p.begins)
    check("a clean push starts at block 0", p.seqs[:1] == [0], p.seqs[:1])
    check("a clean push sends the whole image",
          p.payload_bytes == n, p.payload_bytes)
    check("a clean push commits", p.commits == 1, p.commits)


def test_a_matching_prefix_is_resumed():
    n, _ = crc_of(IMAGE)
    p = mid_transfer(40)
    run_push(p)
    check("a genuine resume does NOT send BEGIN", p.begins == 0, p.begins)
    check("a genuine resume starts at the block the probe wants",
          p.seqs[:1] == [40], p.seqs[:1])
    check("a genuine resume sends only the remainder",
          p.payload_bytes == n - 40 * BLOCK,
          "%d, wanted %d" % (p.payload_bytes, n - 40 * BLOCK))
    check("a genuine resume still commits", p.commits == 1, p.commits)


def test_a_different_crc_starts_fresh():
    p = mid_transfer(40, crc=0xDEADBEEF)
    run_push(p)
    n, _ = crc_of(IMAGE)
    check("a mismatched CRC sends BEGIN", p.begins == 1, p.begins)
    check("a mismatched CRC restarts at 0", p.seqs[:1] == [0], p.seqs[:1])
    check("a mismatched CRC re-sends everything",
          p.payload_bytes == n, p.payload_bytes)


def test_a_different_length_starts_fresh():
    n, _ = crc_of(IMAGE)
    p = mid_transfer(40, length=n - 8)
    run_push(p)
    check("a mismatched length sends BEGIN", p.begins == 1, p.begins)
    check("a mismatched length restarts at 0", p.seqs[:1] == [0], p.seqs[:1])


def test_a_different_block_size_starts_fresh():
    """The case len+CRC alone cannot see: the same image, pushed before at 24
    bytes a block through an `A8` downlink. Block 40 then means byte 960, not
    byte 9600, and resuming on the sequence number would write the rest of the
    image 8,640 bytes too early."""
    p = mid_transfer(40, received=40 * 24)
    run_push(p)
    check("RECEIVED inconsistent with NEXT_SEQ x block size sends BEGIN",
          p.begins == 1, p.begins)
    check("RECEIVED inconsistent with NEXT_SEQ x block size restarts at 0",
          p.seqs[:1] == [0], p.seqs[:1])


def test_a_read_that_raises_starts_fresh():
    """Fails safe. An unevaluable check is not permission to resume - it is a
    reason not to."""
    p = mid_transfer(40)
    p.raise_on = u.R_NEXT_SEQ
    run_push(p)
    check("a refused read sends BEGIN", p.begins == 1, p.begins)
    check("a refused read restarts at 0", p.seqs[:1] == [0], p.seqs[:1])


def test_a_status_read_that_raises_starts_fresh():
    p = mid_transfer(40)
    p.raise_on = u.R_STATUS
    run_push(p)
    check("a refused STATUS read sends BEGIN", p.begins == 1, p.begins)


def test_no_resume_forces_a_fresh_begin():
    n, _ = crc_of(IMAGE)
    p = mid_transfer(40)
    run_push(p, no_resume=True)
    check("--no-resume sends BEGIN over a valid resume",
          p.begins == 1, p.begins)
    check("--no-resume restarts at 0", p.seqs[:1] == [0], p.seqs[:1])
    check("--no-resume re-sends everything", p.payload_bytes == n,
          p.payload_bytes)


def test_an_idle_probe_starts_fresh():
    n, c = crc_of(IMAGE)
    p = FakeProbe(state=u.STATES.index("IDLE"), pending_len=n, pending_crc=c,
                  received=40 * BLOCK, next_seq=40)
    run_push(p)
    check("an IDLE probe is not resumed into", p.begins == 1, p.begins)
    check("an IDLE probe restarts at 0", p.seqs[:1] == [0], p.seqs[:1])


def test_an_erased_ready_slot_is_not_re_erased():
    """READY is reached only when every staging page has been erased, and
    write_data() accepts a block in READY. A BEGIN here would erase an already
    erased slot."""
    n, c = crc_of(IMAGE)
    p = FakeProbe(state=u.STATES.index("READY"), pending_len=n, pending_crc=c)
    run_push(p)
    check("a READY slot for this image skips the re-erase",
          p.begins == 0, p.begins)
    check("a READY slot still starts at block 0", p.seqs[:1] == [0], p.seqs[:1])
    check("a READY slot gets the whole image", p.payload_bytes == n,
          p.payload_bytes)


def test_a_ready_slot_for_another_image_is_re_erased():
    n, _ = crc_of(IMAGE)
    p = FakeProbe(state=u.STATES.index("READY"), pending_len=n,
                  pending_crc=0xDEADBEEF)
    run_push(p)
    check("a READY slot declared for another image IS re-erased",
          p.begins == 1, p.begins)


def test_a_transfer_complete_but_uncommitted_is_resumed():
    """Every block landed and then the link died before COMMIT. RECEIVED is
    the full declared length, so `NEXT_SEQ * block_bytes` alone would decline
    the one resume that costs a whole transfer to redo. The final block of an
    image is the only one that may be short."""
    short = IMAGE[:127 * BLOCK + 8]                  # 127 full blocks + 8 bytes
    n, c = crc_of(short)
    nblocks = (n + BLOCK - 1) // BLOCK
    p = FakeProbe(state=u.STATES.index("RECEIVING"), pending_len=n,
                  pending_crc=c, received=n, next_seq=nblocks)
    p.declared_len, p.declared_crc = n, c
    run_push(p, image=short)
    check("a complete-but-uncommitted transfer is not re-sent",
          p.begins == 0 and p.payload_bytes == 0,
          "begins=%d bytes=%d" % (p.begins, p.payload_bytes))
    check("a complete-but-uncommitted transfer is committed",
          p.commits == 1, p.commits)


def main():
    print("resume decision, against a fake probe:")
    test_a_clean_first_push_still_begins()
    test_a_matching_prefix_is_resumed()
    test_a_different_crc_starts_fresh()
    test_a_different_length_starts_fresh()
    test_a_different_block_size_starts_fresh()
    test_a_read_that_raises_starts_fresh()
    test_a_status_read_that_raises_starts_fresh()
    test_no_resume_forces_a_fresh_begin()
    test_an_idle_probe_starts_fresh()
    test_an_erased_ready_slot_is_not_re_erased()
    test_a_ready_slot_for_another_image_is_re_erased()
    test_a_transfer_complete_but_uncommitted_is_resumed()
    if FAILURES:
        print("!! %d failed" % len(FAILURES))
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
