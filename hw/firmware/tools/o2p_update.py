#!/usr/bin/env python3
"""Push a firmware image to an o2-probe over RS-485.

    python3 tools/o2p_update.py --port /dev/tty.usbserial-XXXX \\
            .pio/build/o2probe/firmware.bin --boot

Two transports. `--port` is a serial line: a USB-RS485 dongle, or a USB-TTL
lead into a bench bridge. `--swd` is the same bench bridge reached through its
SRAM mailbox over OpenOCD, which needs no lead at all - the debugger is
already attached, because that is how the bridge was flashed.

This is the executable copy of the protocol in `src/update.h`. It speaks plain
Modbus RTU - FC03 and FC16, nothing else - so everything it does can also be
done by hand, or by a Dragino `A8` downlink at 24 bytes a block.

If a push is interrupted - a dropped BLE link to the node is the usual way -
just run it again. The transfer is self-addressing, so the tool reads back what
the probe already has and carries on from there whenever the probe's declared
length, CRC and byte count prove the slot holds a prefix of this exact image.
When anything about that is unclear it erases and starts over instead;
`--no-resume` forces that.

Two things worth knowing before running it against a live bus:

  * The Dragino node is the master on the farm cable. Two masters collide, so
    stretch its `AT+TDC` or power it down for the duration.
  * The image must be the APPLICATION build, linked at 0x08004000. Pushing
    the bootloader's own binary is refused by the probe (its reset vector
    points outside the run slot), but it wastes a transfer.

Speed. The cable runs at 9600 8E1 because that is what the SMT100s on it need,
and a 30 KiB image at 9600 is about four minutes. The probe's baud is a
writable register, so for the duration of a transfer this tool moves it to the
fastest rate the firmware offers - 38400, four times faster - and puts it back
afterwards. It does so only when it can PROVE the new rate works, and the
change is never committed to flash, so the probe returns to the bus rate on
any reset even if this tool dies mid-push - and a probe running firmware from
2026-09-08 onwards reverts on its own after ten seconds of silence
(src/serial_probation.h), which this tool does not assume, because the probe
in front of it may be older. `--no-speedup` skips it entirely;
negotiate_baud() documents what it refuses to try, and why.
"""
import argparse
import binascii
import struct
import sys
import time

import os
import socket
import subprocess

try:
    import serial
except ImportError:                                  # pragma: no cover
    serial = None                     # only --port needs it; --swd does not

# Register addresses, from src/update.h. Kept as literals rather than parsed
# out of the header, because this tool has to work from a laptop that has no
# checkout - but check_update_tool.py verifies them against the header.
R_STATUS = 0x0050
R_BLOCK_MAX = 0x0051
R_SLOT_HI = 0x0052
R_CMD = 0x0054
R_LEN_HI = 0x0055
R_CRC_HI = 0x0057
R_RECV_HI = 0x0059
R_NEXT_SEQ = 0x005B
R_LOADER_VER = 0x005C
R_IMAGE_VER = 0x005D
R_INSTALLS = 0x005E
R_DATA = 0x0080

# The first three registers of the config block, from src/regmap.h. Literals
# for the same reason and checked the same way. They are read as one FC03 of
# three: what the probe says its own address, baud and parity are is the only
# honest starting point for changing one of them.
R_SLAVE_ADDR = 0x0030
R_BAUD_CODE = 0x0031
R_PARITY_CODE = 0x0032

# BAUD_CODE value -> real rate, from the O2P_BAUD_* enum in src/regmap.h. The
# tool asks for max(), so a firmware that gains a faster code speeds this tool
# up as soon as the two are re-synced - and check_update_tool.py fails the
# build if they are not.
BAUD_CODES = {0: 9600, 1: 19200, 2: 38400, 3: 115200}

CMD_BEGIN = 0xB001
CMD_COMMIT = 0xB002
CMD_BOOT = 0xB003
CMD_ABORT = 0xB004
CMD_STAY = 0xB005

STATES = ["IDLE", "ERASING", "READY", "RECEIVING", "VERIFYING", "STAGED",
          "ERROR"]
ERRORS = ["NONE", "STATE", "LENGTH", "SEQUENCE", "ALIGN", "FLASH", "CRC",
          "IMAGE", "NOIMAGE"]
LOADER_BIT = 0x8000

# The identity a bootloader falls back to when it cannot read the probe's
# stored transport settings: read_serial()'s defaults in src/loader_main.c.
# A loader potted before 2026-09-08 cannot read the frozen transport block
# (src/transport_record.h), so on a probe whose configuration layout has since
# moved past that loader's, this is where it answers - whatever address the
# probe was commissioned at. See FIRMWARE.md, "How the loader knows where the
# probe is on the bus".
LOADER_FALLBACK_ADDR = 3
LOADER_FALLBACK_BAUD = 9600

ALIGN = 8
IMAGE_MIN = 256

# The bench bridge (src/bridge_main.c) answers FC03 at its own reserved
# address with these eight registers. Reading them proves the laptop, the lead,
# the baud rate and the parity before any probe is blamed for the silence.
# The bridge's SWD mailbox, from src/bridge_mailbox.h. Literals for the same
# reason the register addresses are - and checked by check_update_tool.py.
MBX_BASE = 0x20000000
MBX_MAGIC = 0x4F324D42
MBX_OFF_HOST_SEQ = 0x08
MBX_OFF_TARGET_SEQ = 0x0C
MBX_OFF_TX_LEN = 0x10
MBX_OFF_RX_LEN = 0x14
MBX_OFF_STATUS = 0x18
MBX_OFF_TX = 0x20
MBX_OFF_RX = 0x120
MBX_STATUS = ["IDLE", "REPLIED", "SILENT", "LOCAL", "REJECTED"]

BRIDGE_ADDR = 250
BRIDGE_IDENT = 0xB21D
# BR_REG_BUS_BAUD, in baud/100 so 38400 fits a register (src/bridge_main.c).
BRIDGE_REG_BUS_BAUD = 6
# The bridge version at which that register became WRITABLE. A v1 bridge
# answers every read identically, so nothing about a read distinguishes it -
# and moving the probe in front of one leaves the probe talking a rate the
# bridge cannot follow. The version is the discriminator; a trial write is not,
# because the failure it would probe for is the one that strands the probe.
BRIDGE_VERSION_RERATEABLE = 2
BRIDGE_FIELDS = ["ident", "version", "frames from host", "frames from bus",
                 "host frames dropped", "bus frames dropped", "bus baud/100",
                 "parity bus:host"]


def crc16(buf):
    """CRC-16/MODBUS."""
    crc = 0xFFFF
    for b in buf:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class SerialLink:
    """A serial line: a USB-RS485 dongle, or a USB-TTL lead into a bridge."""

    def __init__(self, port, baud, parity, timeout):
        if serial is None:                           # pragma: no cover
            sys.exit("!! pyserial is required for --port: pip install pyserial")
        self.ser = serial.Serial(port, baud, parity=parity, stopbits=1,
                                 bytesize=8, timeout=timeout)
        self.baud = baud
        # 3.5 character times of silence between frames, per RTU. The probe
        # frames on the same rule in hardware (USART RTOR), so a master that
        # runs frames together is the one that breaks it.
        self.gap = 3.5 * 11 / baud

    def exchange(self, adu, expect_len):
        time.sleep(self.gap)
        self.ser.reset_input_buffer()
        self.ser.write(adu)
        return self.ser.read(expect_len)

    def set_baud(self, baud):
        """Re-time this end of the line, in place.

        Not a close/reopen: opening a port toggles DTR and RTS, and on an
        adapter that derives DE from RTS that pulse drives the cable for as
        long as the open takes - which is long enough to swallow the reply the
        tool is about to listen for. Draining first matters for the same
        reason the probe defers its own switch to after the response: bytes
        still sitting in the FIFO would leave at the new rate and arrive as
        noise.

        Only the SERIAL transport has this. SwdLink deliberately does not, and
        negotiate_baud() tests for the method rather than the class, because
        over the mailbox the cable's rate is the one the bridge was BUILT
        with and nothing this end does can change it.
        """
        self.ser.flush()
        self.ser.baudrate = baud
        self.baud = baud
        self.gap = 3.5 * 11 / baud

    def close(self):
        self.ser.close()


class SwdLink:
    """Frames through the bench bridge's SRAM mailbox, over OpenOCD.

    The target is NEVER halted. `read_memory`/`write_memory` reach SRAM
    through the MEM-AP while the core runs, and halting a running bridge can
    stop it between asserting and releasing DE - which leaves the transceiver
    driving the cable, and every other node on it mute, until the debugger
    resumes.

    Ordering is the protocol: the payload and length are written first and the
    host sequence word last, so the bridge can never act on a half-written
    frame. The bridge does the same with its own sequence word.
    """

    @staticmethod
    def openocd_args(adapter_serial=None, backend=None):
        """OpenOCD arguments, optionally bound to one named probe.

        `adapter serial` has to come AFTER the interface file, because that
        file is what selects the cmsis-dap driver the setting belongs to.
        Without it OpenOCD binds to whichever probe enumerates first, and an
        install can then be pushed into the wrong board - on 2026-09-05 the
        bench had two probes attached (CMSIS_DAP and DAPLINK-S3-2) running
        different images.
        """
        args = ["-f", "interface/cmsis-dap.cfg"]
        if backend:
            # The Debug Mate is HID-only; `auto` tries usb_bulk and fails
            # with "unable to open CMSIS-DAP device". See o2p_capture.py.
            args += ["-c", "cmsis-dap backend %s" % backend]
        if adapter_serial:
            args += ["-c", "adapter serial %s" % adapter_serial]
        args += ["-c", "transport select swd",
                 "-c", "adapter speed 400",
                 "-f", "target/stm32g0x.cfg",
                 "-c", "init", "-c", "reset run"]
        return args

    def __init__(self, host, port, base, timeout, launch=True, verbose=False,
                 adapter_serial=None, backend=None):
        self.base = base
        self.timeout = timeout
        self.verbose = verbose
        self.adapter_serial = adapter_serial
        self.backend = backend
        self.proc = None
        self.sock = None
        try:
            self.sock = self._connect(host, port, launch)
            self._handshake(base)
        except BaseException:
            # Anything at all: the caller never receives this object, so its
            # `finally: link.close()` cannot run, and an OpenOCD we launched
            # would be left holding the debugger and the TCL port.
            self.close()
            raise

    def _handshake(self, base):
        magic, _version, host_seq, target_seq = self._read32(0, 4)
        if magic != MBX_MAGIC:
            raise IOError("no bridge mailbox at 0x%08X: magic is 0x%08X, not "
                          "0x%08X. Either the board is not running the bridge "
                          "image, or OpenOCD attached to the wrong target."
                          % (base, magic, MBX_MAGIC))
        if target_seq != host_seq:
            # Someone else's transaction is in flight - a second debugger, or
            # this tool restarted after a timeout it believed was fatal.
            # Writing now would rewrite the buffer the bridge is copying.
            raise IOError("a transaction is already in flight (host_seq %d, "
                          "target_seq %d). Another host is using this bridge, "
                          "or a previous run was interrupted mid-frame; wait "
                          "for it to finish or reset the bridge board."
                          % (host_seq, target_seq))
        self.seq = host_seq                          # continue from where it is

    # -- OpenOCD's TCL RPC: a command, 0x1a, a reply, 0x1a.
    def _connect(self, host, port, launch):
        try:
            return socket.create_connection((host, port), timeout=5.0)
        except OSError:
            if not launch:
                raise
        cmd = [self._openocd_bin(), "-s", self._openocd_scripts()]
        cmd += self.openocd_args(self.adapter_serial, self.backend)
        print("   launching: %s" % " ".join(cmd))
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        for _ in range(50):
            time.sleep(0.2)
            try:
                return socket.create_connection((host, port), timeout=5.0)
            except OSError:
                if self.proc.poll() is not None:
                    raise IOError("OpenOCD exited immediately; run the "
                                  "command above by hand to see why")
        raise IOError("OpenOCD did not open its TCL port at %s:%d"
                      % (host, port))

    @staticmethod
    def _pio_openocd():
        return os.path.expanduser("~/.platformio/packages/tool-openocd")

    def _openocd_bin(self):
        local = os.path.join(self._pio_openocd(), "bin", "openocd")
        return local if os.path.exists(local) else "openocd"

    def _openocd_scripts(self):
        return os.path.join(self._pio_openocd(), "openocd", "scripts")

    def _tcl(self, command):
        self.sock.sendall(command.encode() + b"\x1a")
        buf = b""
        while not buf.endswith(b"\x1a"):
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("OpenOCD closed the TCL connection")
            buf += chunk
        out = buf[:-1].decode(errors="replace").strip()
        if self.verbose:
            print("   %s -> %s" % (command, out[:120]))
        return out

    def _read(self, offset, width, count):
        out = self._tcl("read_memory 0x%08X %d %d"
                        % (self.base + offset, width, count))
        try:
            values = [int(v, 0) for v in out.split()]
        except ValueError:
            raise IOError("read_memory at +0x%X answered with something that "
                          "is not a list of words: %r" % (offset, out[:120]))
        # The count is the check that matters. OpenOCD reports some failures
        # as prose, and prose that happens to contain no digits parses as an
        # empty list - which would otherwise surface as an IndexError three
        # frames away from the cause.
        if len(values) != count:
            raise IOError("read_memory at +0x%X returned %d words, not %d: %r"
                          % (offset, len(values), count, out[:120]))
        return values

    def _read32(self, offset, count):
        return self._read(offset, 32, count)

    def _write(self, offset, width, values):
        vals = " ".join(str(v) for v in values)
        out = self._tcl("write_memory 0x%08X %d {%s}"
                        % (self.base + offset, width, vals))
        # A successful write_memory returns nothing at all. Matching on the
        # word "error" would let every other failure phrasing through, and it
        # is the only thing standing between a silently unwritten frame and a
        # timeout blamed on the probe.
        if out:
            raise IOError("write_memory at +0x%X failed: %s" % (offset, out[:120]))

    def exchange(self, adu, expect_len):
        del expect_len                    # the mailbox returns a whole frame
        self._write(MBX_OFF_TX, 8, list(adu))
        self._write(MBX_OFF_TX_LEN, 32, [len(adu)])
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        self._write(MBX_OFF_HOST_SEQ, 32, [self.seq])   # published LAST

        deadline = time.time() + self.timeout + 1.0
        while time.time() < deadline:
            if self._read32(MBX_OFF_TARGET_SEQ, 1)[0] == self.seq:
                break
            time.sleep(0.005)
        else:
            raise IOError("the bridge did not pick up the frame - it is not "
                          "running, or it is stuck in a transmission")

        rx_len, status = self._read32(MBX_OFF_RX_LEN, 2)
        name = MBX_STATUS[status] if status < len(MBX_STATUS) else status
        if status == MBX_STATUS.index("REJECTED"):
            raise IOError("the bridge refused a %d-byte frame" % len(adu))
        if rx_len == 0:
            return b""                    # SILENT: the caller's timeout path
        if rx_len > 256:
            raise IOError("the bridge reported a %d-byte reply (status %s)"
                          % (rx_len, name))
        return bytes(self._read(MBX_OFF_RX, 8, rx_len))

    def close(self):
        try:
            if self.sock is not None:
                self.sock.close()
        finally:
            if self.proc is not None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    # An OpenOCD that will not leave keeps the debug adapter
                    # claimed, and the next run cannot attach at all.
                    self.proc.kill()
                    self.proc.wait(timeout=5.0)
                self.proc = None


class Bus:
    def __init__(self, link, addr, verbose=False):
        self.link = link
        self.addr = addr
        self.verbose = verbose

    def _txn(self, pdu, expect_len):
        adu = bytes([self.addr]) + pdu
        adu += struct.pack("<H", crc16(adu))
        rsp = self.link.exchange(adu, expect_len)
        if len(rsp) < 3:
            if not rsp:
                raise NoReply("no reply")
            # 1 or 2 bytes is NOT silence. Something on this address started
            # to answer, and the bridge check must not read the fragment as
            # "nobody is there" and take that for permission.
            raise IOError("truncated reply (%d bytes): %s"
                          % (len(rsp), rsp.hex()))
        if crc16(rsp[:-2]) != struct.unpack("<H", rsp[-2:])[0]:
            raise IOError("bad CRC in reply: %s" % rsp.hex())
        if rsp[0] != self.addr:
            raise IOError("reply from address %d, not %d" % (rsp[0], self.addr))
        if rsp[1] & 0x80:
            raise ModbusException(rsp[2])
        return rsp

    def read(self, addr, count):
        rsp = self._txn(struct.pack(">BHH", 3, addr, count), 5 + 2 * count)
        # Check the SHAPE, not just the CRC. A reply one register short still
        # passes CRC and address, and slicing it blind unpacks the two CRC
        # bytes as the last register - a plausible-looking number that is
        # actually a checksum. Other short lengths raise struct.error out of
        # the middle of a caller that promised to log a failed row instead.
        if rsp[1] != 3:
            raise IOError("reply is function %d, not FC03" % rsp[1])
        if rsp[2] != 2 * count:
            raise IOError("reply declares %d data bytes, asked for %d"
                          % (rsp[2], 2 * count))
        if len(rsp) != 5 + 2 * count:
            raise IOError("reply is %d bytes, expected %d"
                          % (len(rsp), 5 + 2 * count))
        return list(struct.unpack(">%dH" % count, rsp[3:3 + 2 * count]))

    def write(self, addr, values):
        pdu = struct.pack(">BHHB", 16, addr, len(values), 2 * len(values))
        pdu += b"".join(struct.pack(">H", v) for v in values)
        rsp = self._txn(pdu, 8)
        # FC16 echoes the address and count it actually applied. A device that
        # wrote somewhere else, or wrote fewer registers, says so here - and a
        # config write that silently landed elsewhere is exactly the failure
        # that must not be mistaken for success.
        if rsp[1] != 16:
            raise IOError("reply is function %d, not FC16" % rsp[1])
        if len(rsp) != 8:
            # Exact, not a minimum. SwdLink.exchange() ignores expect_len, so a
            # long reply is not truncated for us the way SerialLink truncates
            # it - and a trailing byte means the framing is not what we think.
            raise IOError("FC16 reply is %d bytes, expected 8" % len(rsp))
        echo_addr, echo_count = struct.unpack(">HH", rsp[2:6])
        if echo_addr != addr or echo_count != len(values):
            raise IOError("FC16 echoed addr 0x%04X count %d, wrote 0x%04X "
                          "count %d" % (echo_addr, echo_count, addr,
                                        len(values)))


class NoReply(IOError):
    """Nothing came back at all.

    Raised ONLY for a zero-byte read. A one- or two-byte fragment is a
    malformed answer, not silence, and goes out as a plain IOError.

    Its own type because SILENCE and A MALFORMED ANSWER mean opposite things
    to the bridge check: silence at address 250 is evidence there is no bridge
    there, while a bad CRC, a reply from another address or a short frame all
    mean something IS answering and this tool does not understand it. Both used
    to arrive as a bare IOError, and the bridge check read the second as the
    first - which is permission to write a baud register the bridge cannot
    follow.
    """


class ModbusException(Exception):
    NAMES = {1: "illegal function", 2: "illegal address", 3: "illegal value",
             4: "device failure"}

    def __init__(self, code):
        super().__init__("Modbus exception %d (%s)"
                         % (code, self.NAMES.get(code, "?")))
        self.code = code


def status(bus):
    v = bus.read(R_STATUS, 1)[0]
    return (v >> 8) & 0x7F, v & 0xFF, bool(v & LOADER_BIT)


def show_status(bus):
    st, err, loader = status(bus)
    recv = bus.read(R_RECV_HI, 2)
    ident = bus.read(R_LOADER_VER, 3)
    print("state %s, error %s, answered by %s"
          % (STATES[st] if st < len(STATES) else st,
             ERRORS[err] if err < len(ERRORS) else err,
             "the BOOTLOADER" if loader else "the application"))
    print("received %d bytes, loader v%d, image v%d, %d installs"
          % ((recv[0] << 16) | recv[1], ident[0], ident[1], ident[2]))


def wait_for(bus, want, timeout, what):
    """Poll the state register until it reaches `want`.

    Silence is EXPECTED here and is not an error. The thing being waited for
    is usually a flash erase, and the probe cannot answer Modbus while its
    flash controller has the bus - so a bare "no reply" during the wait means
    the operation is in progress, which is precisely the case this function
    exists to sit through. Raising on it aborted a push whose erase had in
    fact succeeded (observed 2026-09-06: the probe was left in READY while the
    tool exited with a traceback).

    Only the TIMEOUT is failure. A transport error is remembered so that a
    timeout can say what it kept hitting rather than just "timed out".
    """
    t0 = time.time()
    last_exc = None
    while time.time() - t0 < timeout:
        try:
            st, err, _ = status(bus)
            last_exc = None
        except (ModbusException, IOError, OSError) as exc:
            last_exc = exc
            time.sleep(0.1)
            continue
        if st == want:
            return
        if st == STATES.index("ERROR"):
            raise SystemExit("!! probe reports ERROR/%s while waiting for %s"
                             % (ERRORS[err] if err < len(ERRORS) else err, what))
        time.sleep(0.05)
    raise SystemExit("!! timed out waiting for %s%s"
                     % (what, "" if last_exc is None
                        else " (last transport error: %s)" % last_exc))


def show_bridge(link):
    """Read the bench bridge's own counters. Not a probe: the bridge answers
    for itself at BRIDGE_ADDR and forwards everything else untouched.

    Over --swd this also proves the mailbox end to end without a single frame
    reaching the cable, which is the cheapest possible first test of a new
    bridge board."""
    bus = Bus(link, BRIDGE_ADDR)
    try:
        r = bus.read(0, len(BRIDGE_FIELDS))
    except (IOError, ModbusException) as e:
        print("!! no bridge answered at address %d: %s" % (BRIDGE_ADDR, e))
        print("   That is the laptop, the lead, the baud rate or the parity - "
              "the bridge answers this before it has ever seen the cable.")
        return 1
    if r[0] != BRIDGE_IDENT:
        print("!! address %d answered with ident 0x%04X, not 0x%04X: something "
              "else is on that address" % (BRIDGE_ADDR, r[0], BRIDGE_IDENT))
        return 1
    print("bridge v%d, bus %d baud, parity %d bus / %d host"
          % (r[1], r[6] * 100, r[7] >> 8, r[7] & 0xFF))
    for name, v in zip(BRIDGE_FIELDS[2:6], r[2:6]):
        print("   %-22s %d" % (name, v))
    if r[5]:
        print("   bus frames are being dropped: line errors or a host link "
              "slower than the cable.")
    return 0


# Confirmation is k successes out of n attempts, not n first-tries. A single
# lost frame on a live cable is routine; requiring five in a row to be
# unblemished turns routine noise into "the probe did not come back", whose
# printed remedy is a power cycle. Five successes with three attempts each is
# still ~2**-80 against noise passing Bus.read's CRC, address, function, byte
# count and length checks with the value we asked for.
VERIFY_FRAMES = 5
VERIFY_ATTEMPTS = 3

# How many times the bridge probe must come back SILENT before "no bridge" is
# believed. One timeout is a dropped frame.
BRIDGE_PROBES = 3

# The retraction gets the same treatment the data path gives block 47: retry,
# then resolve the lost-reply/lost-request ambiguity by asking. It is the most
# consequential write this tool makes.
RESTORE_ATTEMPTS = 3

# How many times a bridge read-back is asked for before the rate is called
# unknown. Reads are idempotent, so this is free; see BridgeRetimer.set_baud.
READBACK_ATTEMPTS = 3

# Everything a re-timing can fail with. ModbusException belongs in here and was
# missing: Bus.write raises it for a refusal, it does NOT derive from IOError,
# and an uncaught one from a bridge write escapes as a traceback out of a
# restore path whose entire job is not to raise.
LINE_ERRORS = (ModbusException, IOError, OSError)


def fastest_code():
    """The code with the highest RATE, which is not the highest code.

    `max(BAUD_CODES)` would be the highest key, and the two coincide only
    because the current table happens to be ordered. A firmware that appends
    `O2P_BAUD_4800 = 3` - the exact addition src/modbus_rtu.c's transmit
    backstop already warns about - would make this tool "speed up" to half the
    bus rate, and check_update_tool.py could not see it: both sides would
    agree, and agreeing on 4800 is the bug.
    """
    return max(BAUD_CODES, key=lambda c: BAUD_CODES[c])


def code_for_baud(baud):
    """The code for a real rate, or None if this firmware has no such rate."""
    for code, rate in BAUD_CODES.items():
        if rate == baud:
            return code
    return None


def probe_baud_code(bus):
    """The probe's own view of its baud code, or None if it will not say.

    None is NOT "the default". A read that fails, or answers with a code this
    tool has no rate for, means the settings are unknown - and the whole point
    of reading them is that the tool must not write a baud register on top of
    a configuration it has not seen. The two are distinguished for the CALLER's
    message, because "no answer" and "a firmware I do not recognise" send an
    operator to opposite ends of the bench.
    """
    try:
        code = bus.read(R_BAUD_CODE, 1)[0]
    except (ModbusException, IOError, OSError):
        return None
    return code if code in BAUD_CODES else None


class BridgeRetimer(object):
    """A bench bridge's BUS side, wearing a serial link's `set_baud`/`.baud`.

    The negotiation has to move whatever this end of the cable is, and that is
    not always the same object. On a direct RS-485 dongle it is the dongle, and
    the link retimes itself. Through a bench bridge the dongle (or the BLE
    node) talks to the bridge's HOST lead, which must not move at all - the
    thing that has to follow the probe is the bridge's own bus port, one
    Modbus register away. Presenting both as the same two names keeps that
    difference out of negotiate_baud, _restore_baud and resync.

    It is also the better-instrumented of the two: a dongle cannot be asked
    what rate it is on, while the bridge reports its live rate in the same
    register, so every change here is read back rather than assumed.
    """

    def __init__(self, link, baud):
        self.bus = Bus(link, BRIDGE_ADDR)
        self.baud = baud

    def set_baud(self, baud):
        """Move the cable. Raises if it cannot be established that it moved.

        Deliberately loud where SerialLink.set_baud cannot fail: this one is a
        frame over the wire and can be lost or refused, and a caller that
        believed a silent failure would go on to talk into a cable running at
        a rate it is not using. The read-back is what turns FC16's echo - which
        confirms the address and count but never the value - into a fact.

        THE READ-BACK IS RETRIED, and the write is not. Re-reading a register
        changes nothing, so a lost read-back costs another frame and no risk;
        re-sending the write would be a second state change while the first is
        still unaccounted for. Nearly every failure here is one lost frame, and
        this is what stops that becoming a wrong answer.

        Raising does NOT mean nothing happened. The write may have landed and
        only its confirmation been lost, so self.baud is left at the last rate
        actually READ - never at the one that was asked for - and callers must
        treat the cable's rate as unknown rather than as unchanged. That is why
        resync() still probes a candidate whose set_baud raised.
        """
        self.bus.write(BRIDGE_REG_BUS_BAUD, [baud // 100])
        last = None
        for _ in range(READBACK_ATTEMPTS):
            try:
                got = self.bus.read(BRIDGE_REG_BUS_BAUD, 1)[0] * 100
            except (ModbusException, IOError, OSError) as e:
                last = e
                continue
            if got == baud:
                self.baud = baud
                return
            self.baud = got
            raise IOError("the bridge reports %d baud after being asked for "
                          "%d" % (got, baud))
        raise IOError("the bridge did not confirm %d baud (%s); the cable may "
                      "or may not have moved" % (baud, last))


def bridge_status(link, probe_addr):
    """(is_a_bridge, version, bus_baud) for whatever is at BRIDGE_ADDR.

    `is_a_bridge` follows bridge_in_the_path exactly - True, False or None for
    unknowable - and the other two are None unless it is True.
    """
    if probe_addr == BRIDGE_ADDR:
        return None, None, None
    bus = Bus(link, BRIDGE_ADDR)
    for _ in range(BRIDGE_PROBES):
        try:
            r = bus.read(0, len(BRIDGE_FIELDS))
        except NoReply:
            continue
        except ModbusException:
            return None, None, None
        except (IOError, OSError):
            return None, None, None
        if r[0] != BRIDGE_IDENT:
            return False, None, None
        return True, r[1], r[BRIDGE_REG_BUS_BAUD] * 100
    # SILENCE IS TREATED AS ABSENCE, and it is worth being explicit that this
    # is the one place here that does that.
    #
    # The guard rule says unevaluable input must not read as a pass, and
    # BRIDGE_PROBES timeouts in a row is not proof that nothing is there. It is
    # kept because the alternative is worse: returning "unknown" would refuse
    # the speed-up on every DIRECT RS-485 dongle, which is the ordinary bench
    # setup and the case where retiming the link is exactly right.
    #
    # What bounds the mistake is the probe's own timer. If a v1 bridge IS there
    # and all its replies are lost, this end retimes the host lead, the probe
    # takes the write and switches, the cable does not follow, and the probe is
    # unreachable -- for ten seconds, after which serial_probation.h puts it
    # back. The cost is a failed speed-up and a hiccup, not a stranded probe.
    # BRIDGE_PROBES is what makes it unlikely; the timer is what makes it
    # survivable. Do not remove the second and keep believing the first.
    return False, None, None


def retimable_line(link, probe_addr):
    """(line, why_not): the end of the cable that must follow the probe.

    `line` is an object with `set_baud` and `.baud`, or None - in which case
    `why_not` is the sentence to print. Nothing here changes anything; it only
    establishes which of the three situations we are in.
    """
    is_bridge, version, bus_baud = bridge_status(link, probe_addr)

    if is_bridge is None:
        return None, ("could not rule out a bridge in the path")
    if is_bridge:
        if version is None or version < BRIDGE_VERSION_RERATEABLE:
            return None, ("a bench bridge v%s is forwarding, and its bus rate "
                          "is compiled in - reflash it to move the cable"
                          % ("?" if version is None else version))
        if code_for_baud(bus_baud) is None:
            # The bridge is on a rate this firmware has no code for, so there
            # is no way to say where it should be put back to.
            return None, ("the bridge reports %d baud, which this tool has no "
                          "code for" % bus_baud)
        return BridgeRetimer(link, bus_baud), None

    # No bridge. The link itself is the cable, if it can be retimed at all.
    if getattr(link, "set_baud", None) is None:
        return None, ("this transport cannot be retimed and no bridge "
                      "answered, so nothing here can follow the probe")
    return link, None


def bridge_in_the_path(link, probe_addr):
    """True if a bench bridge is forwarding for us, None if unknowable.

    Kept for --bridge and for callers that only want the yes/no; the baud
    negotiation uses bridge_status()/retimable_line(), which need the version
    as well. Both must answer the same way about presence.

    The bridge's BUS side was compiled in before BRIDGE_VERSION_RERATEABLE
    (`O2P_BRIDGE_BUS_BAUD`, src/bridge_main.c) and it defaults to the same 9600
    as its host side, so a mismatch between this end's rate and the probe's
    declared rate does NOT detect it: on the standard bench setup both legs are
    9600 and the two agree. Raising the probe in front of an OLD bridge leaves
    it talking 38400 to one that only ever speaks 9600 - unreachable until its
    next reset, over a lead that cannot reset it.

    So it is asked directly, the same way `--bridge` asks: the bridge answers
    for ITSELF at its reserved address and forwards everything else.

    ONLY SILENCE IS A NO, and only repeated silence. A bad CRC, a reply from
    the wrong address, a short frame or an unexpected ident are all evidence
    that something IS there - `show_bridge()` calls the last of those "something
    else is on that address" and refuses to go on, and this must not be more
    permissive than the diagnostic. Anything unevaluable returns None, which
    the caller treats as "do not touch the baud".
    """
    if probe_addr == BRIDGE_ADDR:
        # The probe has been put on the bridge's reserved address. Anything
        # answering there is the probe, so this test cannot distinguish
        # anything - and an unevaluable test is not permission.
        return None
    bus = Bus(link, BRIDGE_ADDR)
    for _ in range(BRIDGE_PROBES):
        try:
            r = bus.read(0, len(BRIDGE_FIELDS))
        except NoReply:
            continue                      # keep asking; one timeout is noise
        except ModbusException:
            return None                   # something answered, but not a bridge
        except (IOError, OSError):
            return None                   # malformed: something IS there
        return r[0] == BRIDGE_IDENT
    return False                          # silent every time: a direct line


def confirm_baud(bus, want_code):
    """Prove the link at the current rate, by CONTENT and repeatedly.

    Reading the baud register back is what separates "the line works" from
    "the line works AND we are talking to the probe we just retimed": noise at
    the wrong rate does not produce well-formed FC03 replies carrying the code
    we asked for. A Modbus exception is a failure here, unlike a liveness test
    - the register exists, so a probe that refuses it is not the probe this
    tool understands.

    Each of the VERIFY_FRAMES successes may take up to VERIFY_ATTEMPTS tries.
    A WRONG value fails immediately and is never retried: that is not noise,
    it is the probe telling us it is somewhere else.
    """
    for _ in range(VERIFY_FRAMES):
        for attempt in range(VERIFY_ATTEMPTS):
            try:
                if bus.read(R_BAUD_CODE, 1)[0] != want_code:
                    return False
                break
            except (ModbusException, IOError, OSError):
                if attempt == VERIFY_ATTEMPTS - 1:
                    return False
    return True


def resync(line, bus, candidates, settle):
    """Find the rate the probe is actually on, and return it, or None.

    Called whenever a switch did not land the way it was asked to. The
    ambiguous case is a write whose REPLY was lost: from here that is
    indistinguishable from a write that never arrived, but the probe is in one
    of exactly two states, so both are tried rather than assumed. `candidates`
    is ordered most-likely first only to save time; correctness does not
    depend on it.
    """
    for baud in candidates:
        try:
            line.set_baud(baud)
        except LINE_ERRORS:
            # NOT `continue`. A raise here means the change was not CONFIRMED,
            # which is not the same as not made: the write may have landed and
            # only its read-back been lost. Skipping the probe would then walk
            # past the rate the cable is actually on and finish with a
            # confident "found nowhere" - the wrong answer, arrived at by
            # assuming a failure had no effect. Asking the probe costs one
            # frame and settles it either way.
            pass
        time.sleep(settle)
        code = probe_baud_code(bus)
        if code is not None and BAUD_CODES[code] == baud:
            return baud
    return None


def rate_candidates(*preferred):
    """Every rate this firmware knows, the given ones first, no duplicates."""
    out = []
    for baud in list(preferred) + sorted(BAUD_CODES.values()):
        if baud is not None and baud not in out:
            out.append(baud)
    return out


def looks_like_o2p(bus):
    """Is the thing answering on this address one of OUR probes?

    Asked before an address sweep is allowed to conclude anything, because the
    fallback address is 3 and address 3 on a farm cable may well be somebody
    else's instrument. A well-formed FC03 reply is not identification: it says
    a Modbus device exists, not which one. So the update block is read and its
    fields are required to be in range - a state and an error this tool has
    names for, and a loader version that is a plausible small integer. A
    device that has some unrelated meaning for 0x0050 will almost always fail
    one of them, and one that passes all of them is answering the update
    block's contract, which is the only definition of "our probe" this tool
    has.

    Errs towards NO. A false yes here starts a firmware push at a stranger.
    """
    try:
        st, err, _ = status(bus)
        ident = bus.read(R_LOADER_VER, 3)
    except (ModbusException, IOError, OSError):
        return False
    return st < len(STATES) and err < len(ERRORS) and ident[0] <= 16


def sweep_identity(line, bus, addr, rates, settle):
    """Try one address at each rate in turn, using the UPDATE block.

    Deliberately not the config block. The bootloader refuses every register
    outside the update window (loader_main.c's loader_read), so a probe
    sitting in its bootloader - the entire population this hunt exists for -
    answers R_STATUS and is silent on R_BAUD_CODE. A sweep built on the config
    registers therefore cannot see the one thing it was written to find.

    Leaves the bus and the link on the identity that answered, and returns
    True; otherwise restores both and returns False.
    """
    started_addr, started_baud = bus.addr, line.baud
    bus.addr = addr
    for baud in rates:
        try:
            line.set_baud(baud)
        except LINE_ERRORS:
            # Through a bridge this is a frame. Unconfirmed is not unchanged,
            # so the identity is still asked for at this candidate.
            pass
        if settle:
            time.sleep(settle)
        if looks_like_o2p(bus):
            return True
    bus.addr = started_addr
    try:
        line.set_baud(started_baud)
    except LINE_ERRORS:
        pass                      # reported by whoever asked for the sweep
    return False


def find_at_fallback_identity(line, bus, settle=0.2):
    """Look for the probe at the BOOTLOADER's default identity.

    The last resort of find_probe(), and it exists for one specific failure:
    an old bootloader that cannot read the probe's stored transport settings
    falls back to address 3 / 9600 / even parity, silently, on exactly the
    probe whose application is broken enough to need the bootloader. Sweeping
    the configured identity alone would report such a probe unreachable when
    it is sitting there answering, at an address the operator never chose.

    Only address and baud are swept. Parity is not: this end has no way to
    change it mid-run, and the fallback parity is even, which is both the
    default and what every probe on this cable is provisioned with.

    On success the bus and the link are LEFT at the identity that answered, so
    the caller can go on to talk to it, and both the address and the rate are
    printed - an operator who did not know the probe had fallen back needs to
    be told, not quietly rescued.
    """
    if bus.addr == LOADER_FALLBACK_ADDR:
        return False
    if line is None:
        # Nothing here can be retimed -- no bridge answered and this transport
        # has no rate of its own -- so there is no hunt to make. Through a
        # BRIDGE this is not `link`: hunting on the host lead would only break
        # the one connection that is working, and would never reach the cable
        # the probe is actually on.
        return False
    started_addr = bus.addr
    print("   no answer at address %d; trying the bootloader's fallback "
          "identity (address %d)" % (started_addr, LOADER_FALLBACK_ADDR))
    if not sweep_identity(line, bus, LOADER_FALLBACK_ADDR,
                          rate_candidates(LOADER_FALLBACK_BAUD), settle):
        return False
    print("!! answering at address %d, %d baud - not the %d you asked for. A "
          "bootloader that cannot read the stored transport settings falls "
          "back to this identity; see FIRMWARE.md."
          % (LOADER_FALLBACK_ADDR, line.baud, started_addr))
    return True


def find_probe(line, bus, settle=0.2):
    """Make contact, hunting for the probe's rate if the given one is wrong.

    An interrupted earlier run - or the one unrecoverable case in
    negotiate_baud - can leave a probe sitting at a rate nobody asked for. The
    tool put it there, so the tool is the thing that should find it again;
    without this the next invocation dies in show_status() with "no reply",
    which says nothing about baud and sends the operator looking at the lead.

    Returns True if the probe is now reachable at this end's current rate.
    """
    if probe_baud_code(bus) is not None:
        return True
    # The config register is silent. That is what a WRONG RATE looks like, and
    # it is also what a probe sitting in its BOOTLOADER looks like at exactly
    # the right one - the loader refuses every register outside the update
    # block. Ask the update block before concluding anything about the rate,
    # or the hunt below walks away from a probe it is already talking to.
    if looks_like_o2p(bus):
        return True
    if line is None:
        # Nothing here can be retimed -- no bridge answered and this transport
        # has no rate of its own -- so there is no hunt to make. Through a
        # BRIDGE this is not `link`: hunting on the host lead would only break
        # the one connection that is working, and would never reach the cable
        # the probe is actually on.
        return False
    started = line.baud
    print("   no answer at %d; trying the other rates this firmware supports"
          % started)
    others = [b for b in rate_candidates() if b != started]
    at = resync(line, bus, others, settle)
    if at is None:
        try:
            line.set_baud(started)        # leave it where the operator put it
        except LINE_ERRORS as e:
            print("   could not put this end back to %d (%s)" % (started, e))
        # Same question again for a bootloader: resync() asks the config
        # block, so it cannot see one at any rate.
        if sweep_identity(line, bus, bus.addr, others, settle):
            print("!! the probe is at %d, not %d, and is answering from its "
                  "BOOTLOADER." % (line.baud, started))
            return True
        return find_at_fallback_identity(line, bus, settle)
    print("!! the probe is at %d, not %d - an interrupted run probably left "
          "it there." % (at, started))
    return True


def negotiate_baud(link, bus, home_code, settle=0.2, line=None,
                   why_not=None):
    """Move the probe to the fastest rate it offers, for this transfer only.

    `home_code` is where the probe must be LEFT: normally the rate the cable
    is provisioned at, which is what --baud names and what the SMT100s on the
    same cable need. Returns a restore callable, or None when there is nothing
    to put back - so the caller's `finally` is `if restore: restore()` either
    way. The callable returns the rate the probe ended on, or None if it could
    not be reached at all, because `--boot` can still rescue the second case
    and needs to know.

    THE CHANGE IS NEVER COMMITTED. It lives in the probe's RAM config, and
    every path that leaves this tool holding a probe at the wrong rate - a
    crash, a killed terminal, a lead pulled out mid-push - is ended by the next
    reset, which reloads the flash config. Firmware from 2026-09-08 onwards
    goes further and reverts on its own after ten seconds of silence
    (src/serial_probation.h); this tool must still behave as though it is
    talking to an older probe, because it may be.

    WHICH END FOLLOWS THE PROBE is not always this process. Through a bench
    bridge the serial handle here is the HOST lead, which must not move at all;
    the thing that has to follow is the bridge's own bus port, one register
    away (BridgeRetimer). retimable_line() decides which of the two it is
    holding, and that is also where the refusals live.

    It declines, and says so, whenever it cannot establish that the switch is
    safe AND reversible:

      * a bench bridge older than v%d: its bus rate is compiled in, so moving
        the probe in front of it strands the probe,
      * anything on the bridge address that cannot be read as a bridge,
      * no bridge AND a transport with no set_baud - nothing here can follow,
      * a bridge already on a rate this tool has no code for: nowhere defined
        to put it back,
      * when the probe will not report a baud code this tool has a rate for.

    None of those are failures of the push; they just leave it at 9600.

    Nor is a bridge that will not take the write. That is a frame over a wire
    and it can be refused, lost, or answered without being acted on, so it is
    reported and unwound like any other rate that did not verify - never raised
    at a caller that only asked for a push.
    """ % BRIDGE_VERSION_RERATEABLE
    # WHICH END has to follow the probe is settled first, because the answer
    # decides whether any of the rest may happen at all. Through a bench bridge
    # it is the bridge's bus port, not this process's serial handle.
    if line is None and why_not is None:
        line, why_not = retimable_line(link, bus.addr)
    if line is None:
        print("   baud: left as built - %s" % why_not)
        return None
    retime = line.set_baud

    fast_code = fastest_code()
    fast = BAUD_CODES[fast_code]

    was = probe_baud_code(bus)
    if was is None:
        print("   baud: staying at %d - no usable answer from the probe's "
              "BAUD_CODE register" % line.baud)
        return None
    if was == fast_code and was == home_code:
        print("   baud: already at %d, the fastest this firmware offers" % fast)
        return None

    restore = _restore_baud(line, bus, home_code, settle)

    if was == fast_code:
        # Already fast, but not where it must be left. Nothing to raise; the
        # only work is the restore, and the caller's finally will do it.
        print("   baud: running at %d, and it will be left at %d"
              % (fast, BAUD_CODES[home_code]))
        return restore

    print("   baud: asking for %d -> %d for the transfer (not committed; any "
          "reset puts it back)" % (BAUD_CODES[was], fast))

    try:
        bus.write(R_BAUD_CODE, [fast_code])
    except ModbusException as e:
        # A well-formed refusal. The probe did not change anything, and this
        # end must not either.
        print("   baud: the probe refused %d (%s); staying at %d"
              % (fast, e, BAUD_CODES[was]))
        return restore if was != home_code else None
    except (IOError, OSError):
        # The reply was lost, which says nothing about whether the WRITE
        # arrived. Not a failure and not a success: carry on to the same
        # verification, which asks the probe instead of assuming either.
        pass

    # From HERE the probe may be at the new rate, so everything below runs
    # under the restore. A KeyboardInterrupt during a settle, or a pyserial
    # error out of set_baud, used to escape before the caller had been given
    # anything to put the probe back with - silently, because the only thing
    # printed so far is a statement of intent.
    try:
        # The probe applies a serial change only once its reply is off the
        # wire (src/main.c, the deferred-work block), so this end must not
        # retime into the middle of that.
        time.sleep(settle)
        # This can FAIL where a dongle's set_baud cannot: through a bridge it
        # is a frame over the wire, and the bridge may refuse it, lose it, or
        # answer without acting. That is a condition of the cable, not a bug,
        # so it lands in the same "did not verify" path as everything else
        # here rather than being raised at a caller who only asked for a push.
        try:
            retime(fast)
        except (IOError, OSError) as e:
            print("   baud: this end would not follow (%s)" % e)
        else:
            time.sleep(settle)
        if confirm_baud(bus, fast_code):
            print("   baud: %d confirmed over %d frames" % (fast, VERIFY_FRAMES))
            return restore
    except BaseException:
        restore()
        raise

    # Either the acknowledgement was lost, or the cable will not hold the new
    # rate. Same recovery either way, and the restore knows how to find it.
    print("   baud: %d did not verify" % fast)
    if restore() is None:
        return None                       # already said so, loudly
    return restore


def _restore_baud(line, bus, home_code, settle):
    """Put the probe back on `home_code`, and this end with it.

    Returns the rate the probe ended on, or None if it could not be found at
    any rate this firmware supports. Never raises: it runs from a `finally`,
    where the exception it would raise is one that hides whatever actually
    went wrong with the push.

    Idempotent - the caller may invoke it on the failure path and again from
    its `finally`, and a probe already home is confirmed rather than rewritten.
    """
    home = BAUD_CODES[home_code]

    def restore():
        try:
            for attempt in range(RESTORE_ATTEMPTS):
                del attempt
                if line.baud == home and confirm_baud(bus, home_code):
                    print("   baud: back at %d" % home)
                    return home
                # Find the probe first: writing the retraction at a rate it
                # cannot hear is what makes the failure permanent, and a
                # single unretried write is how a lost REQUEST - as opposed to
                # a lost reply - strands it.
                at = resync(line, bus, rate_candidates(home, line.baud), settle)
                if at is None:
                    break
                if at == home:
                    continue              # confirmed on the next lap
                try:
                    bus.write(R_BAUD_CODE, [home_code])
                except LINE_ERRORS:
                    pass                  # asked again next lap, or verified
                time.sleep(settle)
                try:
                    line.set_baud(home)
                except LINE_ERRORS:
                    # One lap's worth of failure, not the end of the restore.
                    # Unguarded this jumped straight to the outer handler and
                    # threw away every remaining attempt -- on the one path
                    # whose whole purpose is to keep trying.
                    pass
                time.sleep(settle)

            at = resync(line, bus, rate_candidates(home, line.baud), settle)
            if at == home:
                print("   baud: back at %d" % home)
                return home
            if at is not None:
                print("!! baud: the probe is at %d and will not go back to "
                      "%d. NOTHING WAS COMMITTED - a reset returns it to its "
                      "stored rate, and firmware from 2026-09-08 does that by "
                      "itself after ten seconds of silence." % (at, home))
                if isinstance(line, BridgeRetimer) and line.baud != at:
                    print("   the cable is at %d and the probe at %d. The "
                          "bridge has no revert of its own; it is reachable "
                          "over the host lead, and the next run's rate sweep "
                          "moves it." % (line.baud, at))
                return at
            # Found nowhere. Leave THIS end on the rate the operator asked
            # for, so every message from here on is about the settings they
            # passed rather than about one of this tool's guesses. (The other
            # branch above deliberately does the opposite: there the probe was
            # found, and the line is left where it is so `--boot` can reach
            # it.)
            try:
                line.set_baud(home)
            except LINE_ERRORS as e:
                # Through a bridge this is a frame and can fail. Say so rather
                # than losing the diagnosis below to the outer handler.
                print("!! baud: this end could not be put back to %d either "
                      "(%s)" % (home, e))
            print("!! baud: the probe answers at no rate this firmware "
                  "supports. NOTHING WAS COMMITTED - reset or power-cycle it "
                  "and it returns to its stored rate; firmware from "
                  "2026-09-08 does it by itself after ten seconds of silence.")
            if isinstance(line, BridgeRetimer):
                print("   the BRIDGE has no such timer and keeps whatever "
                      "rate it was last set to (now %d). If the probe reverts "
                      "underneath it the two are mismatched until something "
                      "moves the cable back - which is what the rate sweep at "
                      "the start of the next run does, through the bridge."
                      % line.baud)
            return None
        except BaseException as e:                           # noqa: BLE001
            print("!! baud: the restore itself failed (%r). NOTHING WAS "
                  "COMMITTED - a reset returns the probe to its stored rate."
                  % (e,))
            return None
    return restore


def resume_point(bus, image_len, crc, block_bytes):
    """Decide whether the probe's staging slot already holds a PREFIX OF THIS
    EXACT IMAGE, and if so where the transfer left off.

    Returns (seq, received) to carry on from, or None to start with a clean
    BEGIN. Either way it says why, because "it re-erased" and "it resumed"
    are both surprising if you expected the other one.

    The protocol is self-addressing on purpose - src/update.h explains that
    the sequence number rides in every block precisely so a transfer is
    recoverable rather than a stream - so a dropped BLE link mid-push does not
    have to cost the 126 blocks already in the slot. What it must never cost
    is correctness: resuming into a slot holding a DIFFERENT image splices two
    binaries. COMMIT's CRC catches that, but only after the whole transfer has
    been spent, so the decision is made here and made conservatively.

    Every one of these must hold. Anything that raises, reads short, or reads
    back something that is not a number is NOT a maybe - it is a no. An
    unevaluable check is never permission.

      * state is RECEIVING (a transfer in flight) or READY (erased, nothing
        written yet - see below),
      * the length the probe declares equals the padded length of this image,
      * the CRC-32 it declares equals this image's,
      * RECEIVED is exactly what NEXT_SEQ blocks of THIS block size would
        have put in the slot.

    That last one is the one that catches a previous run started with a
    different --block-bytes: 24-byte `A8` blocks and 240-byte wire blocks
    declare the same length and CRC, so len+CRC alone would happily resume at
    "block 40" meaning byte 960 while the slot holds byte 9600. It is written
    as min(NEXT_SEQ * block_bytes, image_len) rather than the bare product
    because only the FINAL block of an image may be short: a run that got
    every block in but died before COMMIT sits in RECEIVING with
    RECEIVED == declared length, and the bare product would decline exactly
    the resume that costs the most to redo.

    READY is included because update.c's write_data() accepts a block in
    READY as well as RECEIVING, and READY is reached only from ERASING once
    every staging page has been erased - so a READY probe whose declared
    numbers match this image is an erased slot waiting for block 0, and a
    fresh BEGIN would erase it again for nothing.

    One limit is worth naming: 0x0055..0x0058 read back `pending_len` and
    `pending_crc`, not `declared_len`/`declared_crc` (update.c read_reg()).
    Those are the same during a transfer that only this tool has touched -
    they are latched at BEGIN and write_control() cannot move the target of a
    transfer in flight - but a second master that wrote LEN/CRC without a
    command would move the READBACK. The farm cable has one master at a time
    by rule; if that were ever untrue, COMMIT's CRC is still the backstop.
    """
    try:
        st, err, _ = status(bus)
        state_name = STATES[st] if st < len(STATES) else str(st)
        if st not in (STATES.index("READY"), STATES.index("RECEIVING")):
            print("   starting fresh: the probe is in %s, which holds no "
                  "transfer to continue" % state_name)
            return None

        # 0x0055..0x0058 in one frame: LEN_HI, LEN_LO, CRC_HI, CRC_LO.
        lc = bus.read(R_LEN_HI, 4)
        rc = bus.read(R_RECV_HI, 2)
        nxt = bus.read(R_NEXT_SEQ, 1)
        if len(lc) != 4 or len(rc) != 2 or len(nxt) != 1:
            print("   starting fresh: the probe's transfer registers read "
                  "short")
            return None
        their_len = (int(lc[0]) << 16) | int(lc[1])
        their_crc = (int(lc[2]) << 16) | int(lc[3])
        received = (int(rc[0]) << 16) | int(rc[1])
        next_seq = int(nxt[0])
    except Exception as e:              # noqa: BLE001 - see the docstring
        # Deliberately everything. A resume is an optimisation and a wrong
        # one costs a whole transfer, so any question this function cannot
        # answer is answered "no".
        print("   starting fresh: could not read the probe's transfer state "
              "(%s)" % e)
        return None

    if their_len != image_len:
        print("   starting fresh: the probe declares %d bytes, this image is "
              "%d - the slot holds a different image" % (their_len, image_len))
        return None
    if their_crc != crc:
        print("   starting fresh: declared CRC %08X differs from this image's "
              "%08X - the slot holds a different image"
              % (their_crc, crc))
        return None

    expected = min(next_seq * block_bytes, image_len)
    if received != expected:
        print("   starting fresh: the probe holds %d bytes but %d blocks of "
              "%d would be %d - the previous run used a different block size"
              % (received, next_seq, block_bytes, expected))
        return None

    if st == STATES.index("READY"):
        if next_seq != 0 or received != 0:
            print("   starting fresh: READY with %d bytes already received is "
                  "not a state this tool can explain" % received)
            return None
        print("   the staging slot is already erased for this exact image; "
              "skipping the re-erase and starting at block 0")
        return (0, 0)

    if next_seq == 0:
        print("   starting fresh: the probe is RECEIVING but has nothing in "
              "the slot yet")
        return None

    print("   resuming at block %d, %d of %d bytes already in the slot"
          % (next_seq, received, image_len))
    return (next_seq, received)


def push(bus, image, block_bytes, retries, no_resume=False):
    if block_bytes % ALIGN or block_bytes < ALIGN:
        raise SystemExit("!! block size must be a multiple of %d bytes" % ALIGN)
    advertised = bus.read(R_BLOCK_MAX, 1)[0] * 2
    if block_bytes > advertised:
        raise SystemExit("!! probe accepts at most %d bytes per block"
                         % advertised)

    # Pad to a whole number of doublewords. The padding is inside the declared
    # length, so the CRC covers it and both sides compute the same number.
    if len(image) % ALIGN:
        image += b"\xff" * (ALIGN - len(image) % ALIGN)
    if len(image) < IMAGE_MIN:
        raise SystemExit("!! image is only %d bytes" % len(image))

    crc = binascii.crc32(image) & 0xFFFFFFFF
    print("image %d bytes, CRC-32 %08X, %d blocks of %d"
          % (len(image), crc, (len(image) + block_bytes - 1) // block_bytes,
             block_bytes))

    if no_resume:
        print("   --no-resume: erasing and starting from block 0")
        start = None
    else:
        start = resume_point(bus, len(image), crc, block_bytes)

    if start is None:
        # Length, CRC and BEGIN in one frame - the form that also fits a
        # 40-byte `A8` downlink. The probe applies the command after the
        # numbers.
        bus.write(R_CMD, [CMD_BEGIN,
                          len(image) >> 16, len(image) & 0xFFFF,
                          crc >> 16, crc & 0xFFFF])
        wait_for(bus, STATES.index("READY"), 10.0, "the staging-slot erase")
        seq, sent = 0, 0
    else:
        seq, sent = start

    t0 = time.time()
    while sent < len(image):
        chunk = image[sent:sent + block_bytes]
        regs = [seq] + [int.from_bytes(chunk[i:i + 2], "big")
                        for i in range(0, len(chunk), 2)]
        for attempt in range(retries + 1):
            try:
                bus.write(R_DATA, regs)
                break
            except (IOError, ModbusException) as e:
                if attempt == retries:
                    raise SystemExit("!! block %d failed: %s" % (seq, e))
                # Resynchronise rather than guess: the probe knows which block
                # it wants next, and a lost REPLY looks exactly like a lost
                # request from here.
                nxt = bus.read(R_NEXT_SEQ, 1)[0]
                if nxt == seq + 1:
                    break          # it did land; the reply was lost
                print("   retrying block %d (%s)" % (seq, e))
        sent += len(chunk)
        seq += 1
        if seq % 10 == 0 or sent == len(image):
            print("   %d/%d bytes" % (sent, len(image)), end="\r", flush=True)
    print("\n   sent in %.1f s" % (time.time() - t0))

    bus.write(R_CMD, [CMD_COMMIT])
    wait_for(bus, STATES.index("STAGED"), 30.0, "the image verify")
    print("staged and verified")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="firmware.bin for the run slot")
    ap.add_argument("--port", help="serial line: a USB-RS485 dongle, or a "
                                   "USB-TTL lead into a bench bridge")
    ap.add_argument("--swd", action="store_true",
                    help="reach a bench bridge through its SRAM mailbox over "
                         "OpenOCD instead of a serial line")
    ap.add_argument("--swd-tcl", default="127.0.0.1:6666",
                    help="OpenOCD's TCL RPC port (default 127.0.0.1:6666)")
    ap.add_argument("--swd-attach", action="store_true",
                    help="require an OpenOCD that is already running, rather "
                         "than launching one")
    ap.add_argument("--adapter-backend",
                    default=os.environ.get("O2P_ADAPTER_BACKEND"),
                    choices=[None, "hid", "usb_bulk", "tcp", "auto"],
                    help="CMSIS-DAP backend (env O2P_ADAPTER_BACKEND). The "
                         "Debug Mate needs 'hid'; auto fails on it.")
    ap.add_argument("--adapter-serial",
                    default=os.environ.get("O2P_ADAPTER_SERIAL"),
                    help="CMSIS-DAP serial to bind to (env "
                         "O2P_ADAPTER_SERIAL). Pass it whenever more than "
                         "one probe is attached; without it OpenOCD takes "
                         "the first it finds, which may be another board.")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="E", choices=["N", "E", "O"])
    ap.add_argument("--addr", type=int, default=3)
    ap.add_argument("--block-bytes", type=int, default=240,
                    help="240 on a wire; 24 through a Dragino A8 downlink")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--no-speedup", action="store_true",
                    help="push at --baud instead of raising the probe to the "
                         "fastest rate its firmware offers for the duration "
                         "of the transfer")
    ap.add_argument("--no-resume", action="store_true",
                    help="always erase and push from block 0, even when the "
                         "probe is holding a verified prefix of this exact "
                         "image from an interrupted run")
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--status", action="store_true", help="report and exit")
    ap.add_argument("--bridge", action="store_true",
                    help="ask the bench bridge about itself, not a probe")
    ap.add_argument("--boot", action="store_true",
                    help="reset into the bootloader to install what was staged")
    ap.add_argument("--stay", action="store_true",
                    help="reset into the bootloader and stay there")
    ap.add_argument("--abort", action="store_true",
                    help="discard any transfer and retract a staged image")
    args = ap.parse_args()

    if bool(args.port) == bool(args.swd):
        ap.error("give exactly one of --port and --swd")

    if args.swd:
        host, _, port = args.swd_tcl.partition(":")
        try:
            link = SwdLink(host, int(port or 6666), MBX_BASE, args.timeout,
                           launch=not args.swd_attach,
                           adapter_serial=args.adapter_serial,
                           backend=args.adapter_backend)
        except (OSError, IOError) as e:
            return "!! %s" % e
        # --baud/--parity describe the CABLE, and over SWD the cable settings
        # are the ones the bridge was BUILT with. Saying so beats letting
        # someone believe they changed them.
        if args.baud != 9600 or args.parity != "E":
            print("   note: --baud/--parity are ignored over --swd; the "
                  "bridge's bus settings are compiled in")
    else:
        link = SerialLink(args.port, args.baud, args.parity, args.timeout)

    try:
        return run(args, link)
    finally:
        link.close()


def run(args, link):
    if args.bridge:
        return show_bridge(link)

    bus = Bus(link, args.addr)

    # WHICH OBJECT IS THE CABLE, resolved once and used everywhere below.
    # Through a bench bridge it is NOT `link`: `link` is then the host lead,
    # and retiming that to follow the probe would cut the only connection that
    # still works. Everything from here on that moves a rate moves this.
    line, why_not = retimable_line(link, bus.addr)

    # Before anything is diagnosed as a dead probe or a bad lead: an earlier
    # run of THIS tool may have left it at a rate nobody asked for.
    #
    # THIS MUST FOLLOW retimable_line(), not precede it. It was written above
    # that call and referenced `line` before assignment, so EVERY path through
    # run() raised UnboundLocalError - both --port and --swd, on the first
    # statement that does any work. Reproduced against the pre-fix order with a
    # stub link, 2026-09-08; found by a review, not by a test, because nothing
    # here calls run() at all: the tool suites drive the module's functions
    # directly and the BLE push imports the Bus helpers. test_run_smoke.py now
    # closes that, and it is the whole of what it checks.
    if not args.bridge:
        find_probe(line, bus)

    # --status/--abort/--stay do their one thing and return before any
    # restore exists, so a probe found off the provisioned rate is REPORTED
    # rather than silently accepted. Only a push has a reason to move it, and
    # only a push puts it back.
    if line is not None and line.baud != args.baud and (
            args.status or args.abort or args.stay):
        print("!! this run leaves the probe at %d. Push an image, or set it "
              "back by hand: it is register 0x%04X, and nothing here has been "
              "committed to flash." % (line.baud, R_BAUD_CODE))

    if args.status:
        show_status(bus)
        return 0
    if args.abort:
        bus.write(R_CMD, [CMD_ABORT])
        show_status(bus)
        return 0
    if args.stay and not args.image:
        bus.write(R_CMD, [CMD_STAY])
        print("asked the probe to reset into its bootloader and stay there; "
              "it will not be measuring until it is started again")
        return 0

    if not args.image:
        # NOT ap.error(): `ap` lives in main() and this is run(), so that
        # line raised NameError instead of printing usage - the tool crashed
        # on its own argument check. SystemExit is what the rest of this file
        # raises anyway.
        raise SystemExit("!! an image is required unless --status/--abort/"
                         "--stay is given")

    show_status(bus)
    with open(args.image, "rb") as f:
        image = f.read()

    # Where the probe must be LEFT: ARGS.BAUD, and never link.baud.
    #
    # find_probe() may have just moved this end onto a rate an interrupted run
    # stranded the probe at. Deriving home from the line would then make the
    # stranded rate the destination - so the run that exists to rescue a probe
    # from 38400 would confirm it there, on a cable whose SMT100s are at 9600,
    # and print "already at the fastest this firmware offers" while doing it.
    # --baud is the operator's statement of what the cable runs at, and it is
    # the only thing here that a previous failure cannot have corrupted.
    # `line`, not `link`. Gating on the LINK's own set_baud refused the whole
    # speed-up over --swd -- where the transport deliberately has none and the
    # cable is the bridge's bus port, which is precisely the case the bridge
    # re-rate exists for. retimable_line() has already decided whether anything
    # here can follow the probe; this only asks where it must be left.
    home_code = code_for_baud(args.baud) if line is not None else None

    # Negotiated after the status read, which is deliberately done at the rate
    # the operator asked for: if anything about the link is wrong, it should
    # be reported against the settings they passed and not against one this
    # tool chose for them.
    restore = None
    if args.no_speedup:
        pass
    elif home_code is None:
        print("   baud: staying at %d - this firmware has no code for that "
              "rate, so there would be nothing to put the probe back to"
              % args.baud)
    else:
        restore = negotiate_baud(link, bus, home_code, line=line,
                                 why_not=why_not)

    ended_at = None
    try:
        push(bus, image, args.block_bytes, args.retries,
             no_resume=args.no_resume)
    finally:
        # Before BOOT, not after: the boot command has to go out at the rate
        # the probe will still be on when the next tool talks to it, and after
        # the reset there is no probe listening to be put back.
        if restore is not None:
            ended_at = restore()

    if args.boot or args.stay:
        # A BOOT that lands is a complete recovery from a failed restore: the
        # probe resets, and src/loader_main.c reads its baud from the FLASH
        # config, which nothing here committed to. So it is sent at the rate
        # the probe is ACTUALLY on - the one the restore just reported - and
        # not at the one it was supposed to be put back to. Sending it into
        # the void instead would throw away the fix.
        if (restore is not None and line is not None and ended_at is not None
                and ended_at != line.baud):
            print("   sending the boot command at %d, where the probe "
                  "actually is; the reset returns it to its stored rate"
                  % ended_at)
            line.set_baud(ended_at)
        bus.write(R_CMD, [CMD_STAY if args.stay else CMD_BOOT])
        # The probe resets while this reply is on the wire, so there is
        # nothing further to read; give it the settling time before anyone
        # believes the oxygen number it publishes next.
        print("rebooting into the bootloader to install it. The cell needs "
              "15 minutes of settling afterwards before O2_COMP means "
              "anything.")
    else:
        print("staged but NOT installed. Run again with --boot when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
