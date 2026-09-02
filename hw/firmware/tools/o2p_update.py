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

Two things worth knowing before running it against a live bus:

  * The Dragino node is the master on the farm cable. Two masters collide, so
    stretch its `AT+TDC` or power it down for the duration.
  * The image must be the APPLICATION build, linked at 0x08004000. Pushing
    the bootloader's own binary is refused by the probe (its reset vector
    points outside the run slot), but it wastes a transfer.
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
        # 3.5 character times of silence between frames, per RTU. The probe
        # frames on the same rule in hardware (USART RTOR), so a master that
        # runs frames together is the one that breaks it.
        self.gap = 3.5 * 11 / baud

    def exchange(self, adu, expect_len):
        time.sleep(self.gap)
        self.ser.reset_input_buffer()
        self.ser.write(adu)
        return self.ser.read(expect_len)

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

    OPENOCD_ARGS = ["-f", "interface/cmsis-dap.cfg",
                    "-c", "transport select swd",
                    "-c", "adapter speed 400",
                    "-f", "target/stm32g0x.cfg",
                    "-c", "init", "-c", "reset run"]

    def __init__(self, host, port, base, timeout, launch=True, verbose=False):
        self.base = base
        self.timeout = timeout
        self.verbose = verbose
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
        cmd += self.OPENOCD_ARGS
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
            raise IOError("no reply (got %d bytes)" % len(rsp))
        if crc16(rsp[:-2]) != struct.unpack("<H", rsp[-2:])[0]:
            raise IOError("bad CRC in reply: %s" % rsp.hex())
        if rsp[0] != self.addr:
            raise IOError("reply from address %d, not %d" % (rsp[0], self.addr))
        if rsp[1] & 0x80:
            raise ModbusException(rsp[2])
        return rsp

    def read(self, addr, count):
        rsp = self._txn(struct.pack(">BHH", 3, addr, count), 5 + 2 * count)
        return list(struct.unpack(">%dH" % count, rsp[3:3 + 2 * count]))

    def write(self, addr, values):
        pdu = struct.pack(">BHHB", 16, addr, len(values), 2 * len(values))
        pdu += b"".join(struct.pack(">H", v) for v in values)
        self._txn(pdu, 8)


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
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, err, _ = status(bus)
        if st == want:
            return
        if st == STATES.index("ERROR"):
            raise SystemExit("!! probe reports ERROR/%s while waiting for %s"
                             % (ERRORS[err] if err < len(ERRORS) else err, what))
        time.sleep(0.05)
    raise SystemExit("!! timed out waiting for %s" % what)


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


def push(bus, image, block_bytes, retries):
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

    # Length, CRC and BEGIN in one frame - the form that also fits a 40-byte
    # `A8` downlink. The probe applies the command after the numbers.
    bus.write(R_CMD, [CMD_BEGIN,
                      len(image) >> 16, len(image) & 0xFFFF,
                      crc >> 16, crc & 0xFFFF])
    wait_for(bus, STATES.index("READY"), 10.0, "the staging-slot erase")

    seq = 0
    sent = 0
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
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="E", choices=["N", "E", "O"])
    ap.add_argument("--addr", type=int, default=3)
    ap.add_argument("--block-bytes", type=int, default=240,
                    help="240 on a wire; 24 through a Dragino A8 downlink")
    ap.add_argument("--retries", type=int, default=3)
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
                           launch=not args.swd_attach)
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
        ap.error("an image is required unless --status/--abort/--stay is given")

    show_status(bus)
    with open(args.image, "rb") as f:
        push(bus, f.read(), args.block_bytes, args.retries)

    if args.boot or args.stay:
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
