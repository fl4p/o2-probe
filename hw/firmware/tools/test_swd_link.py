#!/usr/bin/env python3
"""Exercise o2p_update.py's SWD transport against a fake OpenOCD and a fake
bridge, on the host, with no hardware.

The mailbox protocol is all ordering: the host writes the payload and length
before the sequence word, the bridge writes rx_len and status before its own.
None of that can be checked by reading the code - "written last" is a claim
about what a debugger observes - so this stands a real TCL RPC server up on a
socket, records the order of every memory access, and asserts it.

    python3 tools/test_swd_link.py
"""
import os
import socket
import struct
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import o2p_update as u                                        # noqa: E402


class FakeBridge:
    """A mailbox in a bytearray, plus a target that answers one register."""

    def __init__(self, reply=None, status=None):
        self.mem = bytearray(0x220)
        self.log = []                     # ("r"/"w", offset, width, count)
        self.target_writes = []           # what the BRIDGE publishes, in order
        self.reply = reply
        self.forced_status = status
        struct.pack_into("<I", self.mem, 0x00, u.MBX_MAGIC)
        struct.pack_into("<I", self.mem, 0x04, 1)

    def read(self, off, width, count):
        self.log.append(("r", off, width, count))
        n = width // 8
        return [int.from_bytes(self.mem[off + i * n:off + (i + 1) * n], "little")
                for i in range(count)]

    def write(self, off, width, values):
        self.log.append(("w", off, width, len(values)))
        n = width // 8
        for i, v in enumerate(values):
            self.mem[off + i * n:off + (i + 1) * n] = int(v).to_bytes(n, "little")
        if off == u.MBX_OFF_HOST_SEQ:
            self._run()

    def _publish(self, off, value):
        struct.pack_into("<I", self.mem, off, value)
        self.target_writes.append(off)

    def _run(self):
        """What bridge_main.c's mailbox_run() does, in the same order."""
        tx_len = struct.unpack_from("<I", self.mem, u.MBX_OFF_TX_LEN)[0]
        if not (4 <= tx_len <= 256):
            self._publish(u.MBX_OFF_RX_LEN, 0)
            self._publish(u.MBX_OFF_STATUS, 4)                      # REJECTED
        else:
            rsp = self.reply if self.reply is not None else b""
            self.mem[u.MBX_OFF_RX:u.MBX_OFF_RX + len(rsp)] = rsp
            self._publish(u.MBX_OFF_RX_LEN, len(rsp))
            self._publish(u.MBX_OFF_STATUS,
                          self.forced_status if self.forced_status is not None
                          else (1 if rsp else 2))
        # LAST, as the firmware does it.
        seq = struct.unpack_from("<I", self.mem, u.MBX_OFF_HOST_SEQ)[0]
        self._publish(u.MBX_OFF_TARGET_SEQ, seq)


class FakeOpenOCD(threading.Thread):
    """OpenOCD's TCL RPC: a command, 0x1a, a reply, 0x1a."""

    def __init__(self, bridge):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.commands = []                # every TCL command, verbatim
        self.closed = threading.Event()
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]

    def run(self):
        conn, _ = self.srv.accept()
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                self.closed.set()
                return
            buf += chunk
            while b"\x1a" in buf:
                cmd, _, buf = buf.partition(b"\x1a")
                conn.sendall(self.handle(cmd.decode()).encode() + b"\x1a")

    def handle(self, cmd):
        self.commands.append(cmd)
        parts = cmd.split(None, 3)
        addr = int(parts[1], 0) - u.MBX_BASE
        width = int(parts[2])
        if parts[0] == "read_memory":
            return " ".join(str(v) for v in
                            self.bridge.read(addr, width, int(parts[3])))
        if parts[0] == "write_memory":
            vals = [int(v) for v in parts[3].strip("{}").split()]
            self.bridge.write(addr, width, vals)
            return ""
        return "error: unknown command %s" % parts[0]


def link_to(bridge, keep=None):
    server = FakeOpenOCD(bridge)
    server.start()
    if keep is not None:
        keep.append(server)
    return u.SwdLink("127.0.0.1", server.port, u.MBX_BASE, 1.0, launch=False)


def modbus_reply(addr, values):
    body = bytes([addr, 3, 2 * len(values)])
    for v in values:
        body += struct.pack(">H", v)
    return body + struct.pack("<H", u.crc16(body))


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def test_round_trip():
    reply = modbus_reply(u.BRIDGE_ADDR, [u.BRIDGE_IDENT])
    b = FakeBridge(reply=reply)
    bus = u.Bus(link_to(b), u.BRIDGE_ADDR)
    got = bus.read(0, 1)
    check("a register read comes back through the mailbox",
          got == [u.BRIDGE_IDENT], got)

    writes = [e for e in b.log if e[0] == "w"]
    order = [e[1] for e in writes]
    check("payload and length are written before the sequence word",
          order.index(u.MBX_OFF_HOST_SEQ) == len(order) - 1
          and u.MBX_OFF_TX in order and u.MBX_OFF_TX_LEN in order, order)
    check("the frame is written as bytes, not words",
          all(e[2] == 8 for e in writes if e[1] == u.MBX_OFF_TX),
          [e for e in writes if e[1] == u.MBX_OFF_TX])
    check("the bridge publishes its reply before its sequence word",
          b.target_writes[-1] == u.MBX_OFF_TARGET_SEQ
          and u.MBX_OFF_RX_LEN in b.target_writes[:-1]
          and u.MBX_OFF_STATUS in b.target_writes[:-1], b.target_writes)


def test_the_target_is_never_halted():
    """Not "no halt in the memory log" - no halt in ANY command sent."""
    b = FakeBridge(reply=modbus_reply(u.BRIDGE_ADDR, [1]))
    servers = []
    bus = u.Bus(link_to(b, servers), u.BRIDGE_ADDR)
    bus.read(0, 1)
    banned = ("halt", "reset", "step", "shutdown")
    offenders = [c for c in servers[0].commands
                 if any(word in c.split()[0] for word in banned)]
    check("no command halts, resets or steps the target", not offenders,
          offenders)


def test_an_in_flight_transaction_is_refused():
    """target_seq != host_seq means someone else owns the mailbox."""
    b = FakeBridge(reply=b"")
    struct.pack_into("<I", b.mem, u.MBX_OFF_HOST_SEQ, 7)
    struct.pack_into("<I", b.mem, u.MBX_OFF_TARGET_SEQ, 6)
    try:
        link_to(b)
        check("a transaction in flight is refused", False, "connected anyway")
    except IOError as e:
        check("a transaction in flight is refused", "in flight" in str(e), e)


def test_a_failed_handshake_closes_the_socket():
    b = FakeBridge()
    struct.pack_into("<I", b.mem, 0, 0xDEADBEEF)
    servers = []
    try:
        link_to(b, servers)
    except IOError:
        pass
    check("a refused connection is not left open",
          servers[0].closed.wait(2.0))


def test_sequence_advances():
    b = FakeBridge(reply=modbus_reply(u.BRIDGE_ADDR, [1]))
    bus = u.Bus(link_to(b), u.BRIDGE_ADDR)
    bus.read(0, 1)
    first = struct.unpack_from("<I", b.mem, u.MBX_OFF_HOST_SEQ)[0]
    bus.read(0, 1)
    second = struct.unpack_from("<I", b.mem, u.MBX_OFF_HOST_SEQ)[0]
    check("each transaction advances the sequence", second == first + 1,
          (first, second))


def test_silence_is_a_timeout_not_a_crash():
    b = FakeBridge(reply=b"")
    bus = u.Bus(link_to(b), 3)
    try:
        bus.read(0, 1)
        check("a silent bus raises IOError", False, "no exception")
    except IOError as e:
        check("a silent bus raises IOError", "no reply" in str(e), e)


def test_a_rejected_length_is_reported():
    b = FakeBridge(reply=b"", status=4)
    link = link_to(b)
    try:
        link.exchange(b"\x01\x02", 8)
        check("a refused frame is reported", False, "no exception")
    except IOError as e:
        check("a refused frame is reported", "refused" in str(e), e)


def test_a_wrong_magic_is_refused_at_connect():
    b = FakeBridge()
    struct.pack_into("<I", b.mem, 0, 0xDEADBEEF)
    try:
        link_to(b)
        check("a board that is not a bridge is refused", False, "connected")
    except IOError as e:
        check("a board that is not a bridge is refused", "magic" in str(e), e)


def main():
    print("SWD transport, against a fake OpenOCD and a fake bridge:")
    test_round_trip()
    test_the_target_is_never_halted()
    test_an_in_flight_transaction_is_refused()
    test_a_failed_handshake_closes_the_socket()
    test_sequence_advances()
    test_silence_is_a_timeout_not_a_crash()
    test_a_rejected_length_is_reported()
    test_a_wrong_magic_is_refused_at_connect()
    if FAILURES:
        print("!! %d failed" % len(FAILURES))
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
