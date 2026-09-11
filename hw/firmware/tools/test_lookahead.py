#!/usr/bin/env python3
"""Depth-1 lookahead staging, 2026-09-11.

The node's BLE bus queue is two deep (bleota.cpp bus_service): one exchange
runs on the wire while a second request may sit queued behind it, a third
is refused, and a failed exchange DROPS what was queued with a
"BUS FLUSH n queued dropped" line for the host to resend. o2p_update's
one-at-a-time loop never used it, paying the ATT round trip and the node's
~50 ms service cadence per block IN SERIES - measured ~280 ms per 240-B
block at 115200/MTU 517, 51 s to stage a 43 kB image whose wire time is
under 4 s. _push_lookahead() writes block N+1 while N is on the wire.

The model below lands a write when the node SERVES it, not when the host
sends it - that is the node's own FIFO discipline, and it is what makes
the flush semantics testable: a failed collect leaves the failed block
unserved and drops the one queued behind it.

These tests pin, against that model:
  happy path          -> every block lands once, at most TWO in flight (a
                         third raises), ADUs byte-identical to the serial
                         loop's
  a silence mid-run   -> resync asks R_NEXT_SEQ, resends the failed block
                         AND the flushed one behind it, still completes
  a lost reply        -> R_NEXT_SEQ says it landed; it is never resent;
                         the speculative resend behind it is harmless
                         (idempotent by block sequence)
  retries exhausted   -> SystemExit naming the block
  no bus_queue_depth  -> push() dispatches to the serial loop (absent
                         means one-at-a-time)
"""

import struct

import o2p_update as U

ADDR = 0x11
BB = 240                       # the bench block size
N_BLOCKS = 5
IMAGE = bytes((i * 7 + 3) & 0xFF for i in range(N_BLOCKS * BB))
IMG = U.padded_image(IMAGE)


def echo_write(reg, count):
    """A CRC-valid FC16 echo, exactly what the probe sends for R_DATA."""
    body = struct.pack(">BBHH", ADDR, 16, reg, count)
    return body + struct.pack("<H", U.crc16(body))


def echo_read(reg, value):
    """A CRC-valid FC03 reply carrying one register."""
    body = struct.pack(">BBBH", ADDR, 3, 2, value)
    return body + struct.pack("<H", U.crc16(body))


def adu_data(adu):
    """(seq, data bytes) out of a staged R_DATA write ADU."""
    count = struct.unpack(">H", adu[4:6])[0]
    seq = struct.unpack(">H", adu[7:9])[0]
    vals = struct.unpack(">%dH" % (count - 1), adu[9:-2])
    return seq, b"".join(struct.pack(">H", v) for v in vals)


class Node:
    """The probe as the node sees it: writes land when SERVED, in order.

    serve_q is the one-or-two deep bus queue. R_NEXT_SEQ is one past the
    highest contiguous landed block - the resume contract the retry loops
    rely on. A failed exchange fails its own block and flushes the queue,
    which is bus_service()'s documented contract.
    """

    def __init__(self):
        self.landed = {}
        self.serve_q = []
        self.sent = []               # every (seq, adu) the host wrote

    def next_seq(self):
        n = 0
        while n in self.landed:
            n += 1
        return n

    def serve(self):
        """The next queued exchange: lands the block, returns its echo."""
        seq, data = self.serve_q.pop(0)
        self.landed[seq] = data
        return echo_write(U.R_DATA, 1 + len(data) // 2)

    def flush(self):
        """bus_service's failure contract: drop what was queued behind."""
        self.serve_q = []


class FakeLink:
    """bus_queue_depth 2, the two-deep contract, with injectable failures.

    fail_at maps a collect index -> "lost" (the block landed but its
    notify never arrived) or "silent" (the exchange failed and the node
    flushed the queue behind it).
    """

    bus_queue_depth = 2

    def __init__(self, node, fail_at=None):
        self.node = node
        self.fail_at = fail_at or {}
        self.collects = 0
        self.inflight = 0
        self._status = []

    def bus_send(self, adu):
        assert self.inflight < 2, "a third request - the node refuses it"
        self.inflight += 1
        seq, data = adu_data(adu)
        self.node.sent.append((seq, bytes(adu)))
        self.node.serve_q.append((seq, data))

    def bus_collect(self):
        self.collects += 1
        self.inflight -= 1
        how = self.fail_at.pop(self.collects, None)
        if how == "lost":
            self.node.serve()               # landed; the notify was lost
            raise IOError("no reply within 0.3 s")
        if how == "silent":
            self.node.flush()               # failed; the queue is dropped
            self.inflight = 0              # nothing pending survives a flush
            raise IOError("the probe did not answer (bus silence)")
        return self.node.serve()

    def exchange(self, adu, expect_len):
        """The resync read: R_NEXT_SEQ over FC03, fresh state."""
        self._status = []
        assert adu[1] == 3, "resync is a read, got FC%d" % adu[1]
        reg = struct.unpack(">H", adu[2:4])[0]
        assert reg == U.R_NEXT_SEQ, "resync reads R_NEXT_SEQ, got 0x%04X" % reg
        return echo_read(reg, self.node.next_seq())


def main():
    ok = [0]

    def check(cond, label):
        print("  %s: %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            ok[0] = 1

    n_expect = (len(IMG) + BB - 1) // BB

    # -- happy path -----------------------------------------------------
    node = Node()
    bus = U.Bus(FakeLink(node), ADDR)
    seq, sent = U._push_lookahead(bus, IMG, BB, 2, 0, 0)
    check(seq == n_expect and sent == len(IMG),
          "happy path returns past the last block (seq %d sent %d)"
          % (seq, sent))
    check(sorted(node.landed) == list(range(n_expect)),
          "every block landed exactly once")
    check(len(node.sent) == n_expect,
          "no speculative resends on a clean run (%d sends)" % len(node.sent))
    check(all(node.landed[s] == IMG[s * BB:(s + 1) * BB]
              for s in node.landed),
          "every landed block is the right bytes")

    # -- the ADUs are byte-identical to the serial loop's ----------------
    serial_adus = []
    s = 0
    while s < len(IMG):
        chunk = IMG[s:s + BB]
        regs = [s // BB] + [int.from_bytes(chunk[i:i + 2], "big")
                            for i in range(0, len(chunk), 2)]
        pdu = struct.pack(">BHHB", 16, U.R_DATA, len(regs), 2 * len(regs))
        pdu += b"".join(struct.pack(">H", v) for v in regs)
        adu = bytes([ADDR]) + pdu
        serial_adus.append(adu + struct.pack("<H", U.crc16(adu)))
        s += len(chunk)
    check([a for _, a in node.sent] == serial_adus,
          "lookahead ADUs are byte-identical to the serial loop's")

    # -- silence mid-run: resync, resend the failed AND the flushed ------
    # collect 2 is block 1's reply (1 -> block 0). Block 1 fails on the
    # wire; block 2, queued behind it, is flushed unserved.
    node = Node()
    bus = U.Bus(FakeLink(node, fail_at={2: "silent"}), ADDR)
    seq, sent = U._push_lookahead(bus, IMG, BB, 2, 0, 0)
    seqs = [s[0] for s in node.sent]
    check(node.next_seq() == n_expect and sent == len(IMG),
          "mid-run silence still completes (next %d sent %d)"
          % (node.next_seq(), sent))
    check(seqs.count(1) == 2 and seqs.count(2) == 2,
          "the failed block AND the flushed one are both resent (%s)" % seqs)
    check(seqs.count(0) == 1 and seqs.count(3) == 1,
          "blocks before and after the failure are sent once (%s)" % seqs)

    # -- lost reply: it landed, never resent -----------------------------
    node = Node()
    bus = U.Bus(FakeLink(node, fail_at={1: "lost"}), ADDR)
    seq, sent = U._push_lookahead(bus, IMG, BB, 2, 0, 0)
    seqs = [s[0] for s in node.sent]
    check(seqs.count(0) == 1,
          "a block the probe says landed is never resent (%s)" % seqs)
    check(node.next_seq() == n_expect and sent == len(IMG),
          "lost reply completes with every block landed")

    # -- retries exhausted ----------------------------------------------
    class AlwaysSilent(FakeLink):
        def bus_collect(self):
            self.collects += 1
            self.inflight = 0              # the flush drops the queue
            self.node.flush()
            raise IOError("the probe did not answer (bus silence)")

    node = Node()
    bus = U.Bus(AlwaysSilent(node), ADDR)
    try:
        U._push_lookahead(bus, IMG, BB, 1, 0, 0)
        check(False, "exhausted retries raise SystemExit")
    except SystemExit as e:
        check("block 0 failed" in str(e),
              "exhausted retries raise SystemExit naming the block (%s)" % e)

    # -- no bus_queue_depth: push() takes the serial loop ----------------
    class SerialOnly:
        def exchange(self, adu, expect_len):
            assert adu[1] == 16
            seq, data = adu_data(adu)
            node.landed[seq] = data
            return echo_write(U.R_DATA, 1 + len(data) // 2)

    node = Node()
    bus = U.Bus(SerialOnly(), ADDR)
    check(getattr(getattr(bus, "link", None), "bus_queue_depth", 1) == 1,
          "no bus_queue_depth attribute means one-at-a-time")

    print("test_lookahead: %s" % ("PASS" if ok[0] == 0 else "FAIL"))
    return ok[0]


if __name__ == "__main__":
    raise SystemExit(main())
