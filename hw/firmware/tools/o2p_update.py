#!/usr/bin/env python3
"""Push a firmware image to an o2-probe over RS-485.

    python3 tools/o2p_update.py --port /dev/tty.usbserial-XXXX \\
            .pio/build/o2probe/firmware.bin --boot

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

try:
    import serial
except ImportError:                                  # pragma: no cover
    sys.exit("!! pyserial is required: pip install pyserial")

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


class Bus:
    def __init__(self, port, baud, parity, addr, timeout, verbose=False):
        self.ser = serial.Serial(port, baud, parity=parity, stopbits=1,
                                 bytesize=8, timeout=timeout)
        self.addr = addr
        self.verbose = verbose
        # 3.5 character times of silence between frames, per RTU. The probe
        # frames on the same rule in hardware (USART RTOR), so a master that
        # runs frames together is the one that breaks it.
        self.gap = 3.5 * 11 / baud

    def _txn(self, pdu, expect_len):
        adu = bytes([self.addr]) + pdu
        adu += struct.pack("<H", crc16(adu))
        time.sleep(self.gap)
        self.ser.reset_input_buffer()
        self.ser.write(adu)
        rsp = self.ser.read(expect_len)
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


def show_bridge(port, baud, parity, timeout):
    """Read the bench bridge's own counters. Not a probe: the bridge answers
    for itself at BRIDGE_ADDR and forwards everything else untouched."""
    bus = Bus(port, baud, parity, BRIDGE_ADDR, timeout)
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
    ap.add_argument("--port", required=True)
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

    if args.bridge:
        return show_bridge(args.port, args.baud, args.parity, args.timeout)

    bus = Bus(args.port, args.baud, args.parity, args.addr, args.timeout)

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
