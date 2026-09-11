#!/usr/bin/env python3
"""SerialLink.exchange() against MEASURED replies, and against the late replies
a node that relays in order produces. No hardware, no real time.

    python3 tools/test_serial_capture.py
    O2P_UPDATE_PY=/tmp/old_o2p_update.py python3 tools/test_serial_capture.py

The second form runs the same cases against another revision of o2p_update.py.
A case that passes against both the fix and the code before it is not testing
the fix, so the late-reply cases are meant to be run both ways.

TWO KINDS OF CASE, kept apart and labelled.

MEASURED: tools/fixtures/modbus_captures.json is a byte-identical copy of
node-prototype test/fixtures/modbus_captures.json (farming repo), which the
node's C++ resync test and farm-node-decoder.js's test also read. Its sha256 is
pinned below; if the canonical file gains a capture, copy it here and update
the pin in BOTH places. Every capture needs an expectation in EXPECT, so a new
one fails here until someone decides what this tool should do with it.

SYNTHETIC: the late-reply scenarios are MODELS, not measurements. Their one
structural assumption is taken from node-prototype source, not from a capture:
the node relays one request at a time and answers in the order they were
written (serbus_tick(): "ONE EXCHANGE PER LOOP PASS"), and it can stop
servicing the console for seconds at a time, because loop() does not gate the
LoRaWAN uplink on a serial bus claim and sendReceive() "blocks through RX1 and
RX2 - well over a second at DR3" (main.cpp). The stall lengths below are
chosen to straddle this tool's own timeouts, and are not measured.
"""
import hashlib
import importlib.util
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "modbus_captures.json")
FIXTURE_SHA256 = "995b714612544bd517837e510c2f6ac0859c492f3f61722c10dfa48a7566b07f"

failures = 0
checks = 0


def check(name, cond, detail=""):
    global failures, checks
    checks += 1
    print("  %-4s %s%s" % ("ok" if cond else "FAIL", name,
                           "" if cond or not detail else "  <- %s" % (detail,)))
    if not cond:
        failures += 1


# ---- the module under test, from this directory or O2P_UPDATE_PY -----------

path = os.environ.get("O2P_UPDATE_PY") or os.path.join(HERE, "o2p_update.py")
spec = importlib.util.spec_from_file_location("o2p_update_under_test", path)
U = importlib.util.module_from_spec(spec)
sys.path.insert(0, HERE)
spec.loader.exec_module(U)
print("testing %s" % path)


# ---- an independent CRC, not o2p_update's -----------------------------------

_T = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xA001 if _c & 1 else _c >> 1
    _T.append(_c)


def crc(data):
    c = 0xFFFF
    for b in data:
        c = (c >> 8) ^ _T[(c ^ b) & 0xFF]
    return c


assert crc(b"123456789") == 0x4B37, "independent CRC-16/MODBUS check value"


def adu(body):
    return bytes(body) + struct.pack("<H", crc(bytes(body)))


# ---- fake time and a fake port ----------------------------------------------

class Clock:
    """Stands in for the `time` module inside o2p_update while a test runs."""

    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)


class Port:
    """Bytes that ARRIVE at a time, read with pyserial's timeout semantics as
    far as exchange() depends on them: a read returns what has arrived, and
    waits up to `timeout` for the first byte if nothing has."""

    def __init__(self, clock, responder=None):
        self.clock = clock
        self.timeout = 1.0
        self.chunks = []                       # [arrive_t, bytearray], sorted
        self.responder = responder
        self.writes = []

    def add(self, t, data):
        self.chunks.append([t, bytearray(data)])
        self.chunks.sort(key=lambda c: c[0])

    def _take(self, n):
        out = bytearray()
        while self.chunks and self.chunks[0][0] <= self.clock.t and len(out) < n:
            buf = self.chunks[0][1]
            k = min(n - len(out), len(buf))
            out += buf[:k]
            del buf[:k]
            if not buf:
                self.chunks.pop(0)
        return bytes(out)

    def read(self, n):
        got = self._take(n)
        if got:
            return got
        future = [c[0] for c in self.chunks if c[0] > self.clock.t]
        to = self.timeout or 0.0
        if future and min(future) <= self.clock.t + to:
            self.clock.t = min(future)
            return self._take(n)
        self.clock.t += to
        return b""

    def reset_input_buffer(self):
        self.chunks = [c for c in self.chunks if c[0] > self.clock.t]

    def write(self, data):
        self.writes.append((self.clock.t, bytes(data)))
        if self.responder:
            self.responder(self, bytes(data), self.clock.t)
        return len(data)

    def flush(self):
        pass


def make_link(clock, port, timeout):
    """A SerialLink without its __init__, which would open a real port."""
    link = U.SerialLink.__new__(U.SerialLink)
    link.ser = port
    link.baud = 9600
    link.gap = max(3.5 * 11 / 9600, 0.001750)
    link._suspect = False       # harmless on revisions that predate it
    port.timeout = timeout
    return link


class Using:
    """Run with o2p_update's `time` replaced by a fake clock."""

    def __init__(self, clock):
        self.clock = clock

    def __enter__(self):
        self.saved = U.time
        U.time = self.clock
        return self.clock

    def __exit__(self, *exc):
        U.time = self.saved


def unhex(s):
    return bytes.fromhex(s.replace(" ", "")) if s else b""


# ---- MEASURED ----------------------------------------------------------------

print("\nthe fixture is the canonical one")
with open(FIXTURE, "rb") as f:
    raw_fixture = f.read()
check("sha256 matches the pinned canonical fixture",
      hashlib.sha256(raw_fixture).hexdigest() == FIXTURE_SHA256,
      hashlib.sha256(raw_fixture).hexdigest())
captures = json.loads(raw_fixture)["captures"]
check("the fixture holds captures", len(captures) > 0)

# What THIS TOOL must do with each capture, as the reply to the request the
# capture records. `returns` is what exchange() hands back; `verdict` is what
# Bus.read() makes of it.
EXPECT = {
    "glitch_lead_trail_fc03": dict(
        returns="frame", verdict="values",
        why="the CRC-valid 21-byte reply is found behind the turnaround zero"),
    "lagged_short_reply": dict(
        returns="raw", verdict="IOError",
        why="a CRC-valid 7-byte frame inside a 9-byte read is not the "
            "2-register reply that was asked for, and is NOT returned as one"),
    "lone_zero": dict(
        returns="raw", verdict="IOError",
        why="a lone zero is a fragment - a truncated reply, not silence"),
    "console_text_as_reply": dict(
        returns="raw", verdict="IOError",
        why="console text is never mistaken for a frame"),
}

print("\nmeasured captures as replies")
for cap in captures:
    cid = cap["id"]
    raw, frame = unhex(cap["raw_hex"]), unhex(cap["frame_hex"])
    if frame:
        check("%s: frame_hex is CRC-valid (independent CRC)" % cid,
              crc(frame[:-2]) == struct.unpack("<H", frame[-2:])[0])
        check("%s: frame_hex occurs inside raw_hex" % cid, frame in raw)
    exp = EXPECT.get(cid)
    check("%s: has an expectation in this test" % cid, exp is not None)
    if exp is None:
        continue
    req = adu(struct.pack(">BBHH", cap["slave"], cap["function"],
                          cap["register"], cap["count"]))
    expect_len = 5 + 2 * cap["count"]

    clock = Clock()
    port = Port(clock, responder=lambda p, d, t, raw=raw: p.add(t + 0.05, raw))
    with Using(clock):
        link = make_link(clock, port, timeout=1.0)
        got = link.exchange(req, expect_len)
    want = frame if exp["returns"] == "frame" else raw
    check("%s: exchange() returns the %s  (%s)" % (cid, exp["returns"], exp["why"]),
          got == want, got.hex(" "))

    clock = Clock()
    port = Port(clock, responder=lambda p, d, t, raw=raw: p.add(t + 0.05, raw))
    with Using(clock):
        bus = U.Bus(make_link(clock, port, timeout=1.0), cap["slave"])
        try:
            vals = bus.read(cap["register"], cap["count"])
            verdict = "values"
        except U.NoReply:
            verdict = "NoReply"
        except IOError:
            verdict = "IOError"
    check("%s: Bus.read() gives %s" % (cid, exp["verdict"]),
          verdict == exp["verdict"], verdict)
    if exp["verdict"] == "values" and verdict == "values":
        check("%s: and the values are the frame's registers" % cid,
              list(vals) == [struct.unpack(">H", frame[3 + 2 * i:5 + 2 * i])[0]
                             for i in range(cap["count"])], vals)
for cid in EXPECT:
    check("expectation %r matches a capture" % cid,
          any(c["id"] == cid for c in captures))


# ---- SYNTHETIC: a node that answers in order, and sometimes stalls ----------

class Node:
    """Answers each request once, strictly in the order written, never before
    `free_at`, and never inside a stall. Register values encode the index of
    the request being answered, so a stale reply is recognisable."""

    def __init__(self, latency=0.12, stalls=()):
        self.latency = latency
        self.stalls = list(stalls)
        self.free_at = 0.0
        self.n = 0

    def __call__(self, port, data, t):
        slave, fc = data[0], data[1]
        start = max(t, self.free_at)
        for s0, s1 in self.stalls:
            if s0 <= start < s1:
                start = s1
        idx = self.n
        self.n += 1
        if fc == 3:
            _reg, count = struct.unpack(">HH", data[2:6])
            body = bytes([slave, 3, 2 * count]) + b"".join(
                struct.pack(">H", (0x100 * (idx + 1) + i) & 0xFFFF)
                for i in range(count))
        else:
            body = data[:6]                        # FC16 echo
        arrive = start + self.latency
        self.free_at = arrive
        port.add(arrive, adu(body))


def run_reads(node, timeout, n, stall_after=None, stall_s=0.0):
    """n equal-shape reads of 2 registers. Returns [(index_answered or None,
    exception name or None)] per exchange. A stall starts the moment request
    `stall_after` is written."""
    clock = Clock()
    port = Port(clock, responder=None)

    def responder(p, data, t):
        if stall_after is not None and node.n == stall_after:
            node.stalls.append((t, t + stall_s))
        node(p, data, t)

    port.responder = responder
    out = []
    with Using(clock):
        bus = U.Bus(make_link(clock, port, timeout), 3)
        for _ in range(n):
            try:
                vals = bus.read(0x0059, 2)
                out.append(((vals[0] >> 8) - 1, None))
            except (U.NoReply, IOError) as exc:
                out.append((None, type(exc).__name__))
    return out


def no_stale(results):
    """Every exchange that returned values returned ITS OWN request's reply."""
    return all(ix is None or ix == k for k, (ix, _e) in enumerate(results))


print("\nSYNTHETIC late replies (modelled, not measured - see the docstring)")
r = run_reads(Node(), timeout=0.5, n=6)
check("healthy: every read gets its own reply",
      [ix for ix, _ in r] == list(range(6)), r)

# A stall that outlasts one exchange (0.5 s + 2 s) but not the following
# drain: the late reply lands while the next exchange is draining.
r = run_reads(Node(), timeout=0.5, n=6, stall_after=1, stall_s=2.6)
check("a reply that lands DURING the next drain is never taken as that "
      "exchange's answer", no_stale(r), r)
check("  ...and reads after it recover their own replies",
      r[-1][0] == 5, r)

# The same, but the stall also outlasts the 300 ms quiet window: the late reply
# arrives AFTER the next request was written.
r = run_reads(Node(), timeout=0.5, n=6, stall_after=1, stall_s=3.4)
check("a reply that lands AFTER the next write is never taken as that "
      "exchange's answer", no_stale(r), r)
check("  ...and reads after it recover their own replies",
      r[-1][0] == 5, r)

# KNOWN-BAD CALIBRATION. The same scenarios with the drain switched off must
# produce a stale answer; if they do not, the cases above pass for some other
# reason and are not testing the drain at all. (Against a revision older than
# the drain the old code fails differently - it never catches the late reply
# at all - so those late-reply checks pass there vacuously. This is the check
# that is not vacuous.)
if hasattr(U.SerialLink, "_drain_quiet"):
    saved_drain = U.SerialLink._drain_quiet
    U.SerialLink._drain_quiet = lambda self, *a, **k: None
    try:
        r = run_reads(Node(), timeout=0.5, n=6, stall_after=1, stall_s=2.6)
        check("calibration: drain OFF, a reply landing in the gap IS taken as "
              "the next exchange's answer", not no_stale(r), r)
        r = run_reads(Node(), timeout=0.5, n=6, stall_after=1, stall_s=3.4)
        check("calibration: drain OFF, a reply landing after the next write "
              "IS taken too", not no_stale(r), r)
    finally:
        U.SerialLink._drain_quiet = saved_drain
else:
    check("calibration: this revision has no _drain_quiet to switch off", False)

# THE BOUND IS A BOUND. A stall longer than LATE_REPLY_S is not covered, and
# saying so here is better than a docstring that implies otherwise.
late = getattr(U, "LATE_REPLY_S", None)
if late is not None:
    r = run_reads(Node(), timeout=0.5, n=6, stall_after=1, stall_s=late + 4.0)
    check("DOCUMENTED LIMIT: a stall of LATE_REPLY_S + 4 s (%.0f s) still "
          "yields a stale answer" % (late + 4.0), not no_stale(r), r)

# ---- SYNTHETIC: a request left queued by a PREVIOUS process ----------------
# Review 2026-09-10: a new SerialLink started unsuspecting, settled for 2 s of
# quiet, and took the dead process's queued reply as its first answer.

class _SerialModule:
    """Stands in for pyserial inside o2p_update so the REAL __init__ runs."""

    def __init__(self, port):
        self.port = port

    def Serial(self, *a, **kw):
        self.port.timeout = kw.get("timeout", 1.0)
        return self.port


def first_read_after_orphan(unsuspect):
    clock = Clock()
    node = Node()
    port = Port(clock, responder=node)
    node.stalls.append((clock.t, clock.t + 4.0))
    port.write(adu(struct.pack(">BBHH", 3, 3, 0x0059, 2)))   # the orphan, idx 0
    saved = U.serial
    U.serial = _SerialModule(port)
    try:
        with Using(clock):
            link = U.SerialLink("/dev/fake", 9600, "E", 0.5)
            if unsuspect:
                link._suspect = False
            try:
                vals = U.Bus(link, 3).read(0x0059, 2)
                return (vals[0] >> 8) - 1
            except (U.NoReply, IOError):
                return None
    finally:
        U.serial = saved


print("\nSYNTHETIC: a reply queued by a previous process")
got = first_read_after_orphan(False)
check("a fresh link's first read gets ITS OWN reply (index 1), not the orphan's",
      got == 1, got)
got = first_read_after_orphan(True)
check("calibration: starting unsuspecting takes the orphan's reply (index 0)",
      got == 0, got)

print("\nafter a host retime the drain clears the wire, not a node stall")


def first_write_delay(retime):
    clock = Clock()
    port = Port(clock, responder=Node())
    with Using(clock):
        link = make_link(clock, port, timeout=0.5)
        link._suspect = True
        link.late_reply_s = 8.0
        if retime:
            link.set_baud(38400)
        t0 = clock.t
        link.exchange(adu(struct.pack(">BBHH", 3, 3, 0x0050, 1)), 7)
    return port.writes[0][0] - t0 if port.writes else None


d = first_write_delay(True)
check("a suspect exchange straight after set_baud() drains well under the "
      "probe's 10 s probation", d is not None and d < 1.0, d)
d = first_write_delay(False)
check("without a retime it still waits out LATE_REPLY_S", d is not None and d >= 8.0, d)

# ---- round two ----------------------------------------------------------------

print("\nround two: an exception mid-read leaves the link suspect")


class RaisingPort(Port):
    def __init__(self, *a, **kw):
        Port.__init__(self, *a, **kw)
        self.raise_next = False

    def read(self, n):
        if self.raise_next:
            self.raise_next = False
            raise OSError(6, "Device not configured")
        return Port.read(self, n)


def retry_after_exception(clear_suspect):
    clock = Clock()
    port = RaisingPort(clock, responder=Node())
    with Using(clock):
        link = make_link(clock, port, timeout=0.5)
        link.late_reply_s = 8.0
        req = adu(struct.pack(">BBHH", 3, 3, 0x0059, 2))
        port.raise_next = True
        try:
            link.exchange(req, 9)
        except OSError:
            pass
        suspect = link._suspect
        if clear_suspect:
            link._suspect = False
        vals = U.Bus(link, 3).read(0x0059, 2)
    return suspect, (vals[0] >> 8) - 1


suspect, got = retry_after_exception(False)
check("known-bad (review): after an OSError from the read, the link is suspect",
      suspect is True, suspect)
check("  ...and the retry gets its own reply (index 1)", got == 1, got)
suspect, got = retry_after_exception(True)
check("calibration: with the flag cleared, the retry takes the late reply (0)",
      got == 0, got)

print("\nround two: set_baud() earns the short drain")


def delay_after_retime(start, to, via_jtag):
    clock = Clock()
    port = Port(clock, responder=Node())
    with Using(clock):
        link = make_link(clock, port, timeout=0.5)
        link.baud = start
        link.via_usb_serial_jtag = via_jtag
        link._suspect = True
        link.late_reply_s = 8.0
        link.set_baud(to)
        t0 = clock.t
        link.exchange(adu(struct.pack(">BBHH", 3, 3, 0x0050, 1)), 7)
    return port.writes[0][0] - t0 if port.writes else None


d = delay_after_retime(9600, 9600, False)
check("known-bad (review): a same-rate set_baud() does NOT shorten the drain",
      d is not None and d >= 8.0, d)
d = delay_after_retime(9600, 38400, True)
check("known-bad (review): a retime through the node's USB Serial/JTAG does NOT",
      d is not None and d >= 8.0, d)
d = delay_after_retime(9600, 38400, False)
check("a real rate change on a dongle still does", d is not None and d < 1.0, d)


class _P:
    def __init__(self, device, vid, pid):
        self.device, self.vid, self.pid = device, vid, pid


ports = [_P("/dev/cu.usbmodem1101", 0x303A, 0x1001),
         _P("/dev/cu.usbserial-X", 0x0403, 0x6001)]
check("the node's USB Serial/JTAG is recognised by VID/PID, under both macOS names",
      U.is_usb_serial_jtag("/dev/cu.usbmodem1101", ports)
      and U.is_usb_serial_jtag("/dev/tty.usbmodem1101", ports))
check("a dongle is not mistaken for it",
      not U.is_usb_serial_jtag("/dev/cu.usbserial-X", ports))
check("an unlisted port is not it", not U.is_usb_serial_jtag("/dev/cu.nope", ports))

print("\n%d checks, %d failure(s)" % (checks, failures))
sys.exit(1 if failures else 0)
