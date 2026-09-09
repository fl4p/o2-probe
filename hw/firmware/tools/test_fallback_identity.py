#!/usr/bin/env python3
"""Exercise o2p_update.py's bootloader-fallback sweep, on the host.

    python3 tools/test_fallback_identity.py

THE FAILURE BEING GUARDED. The bootloader is never rewritten in the field, so
it reads a configuration record written by applications newer than itself, and
until 2026-09-08 it demanded an exact layout-version match and otherwise fell
back to address 3 / 9600 / even parity - silently, on exactly the probe whose
application was already broken enough to need the bootloader. Firmware from
that date writes the frozen transport block (src/transport_record.h) so it
never happens again, but no already-flashed loader can be told, and a host that
sweeps only the configured identity reports such a probe unreachable while it
is sitting there answering.

So the tool sweeps the fallback identity too, and the two properties that
matter are opposite in direction: it must FIND a probe that has fallen back,
and it must NOT adopt a stranger. Address 3 on a farm cable is a plausible
address for somebody else's instrument, and the cost of a false positive is a
firmware push into it.
"""
import struct
import sys
import types

import o2p_update as u


ok = True


def check(name, cond, detail=""):
    global ok
    print("  %-4s %s%s" % ("ok" if cond else "FAIL", name,
                           "" if not detail or cond else " - " + detail))
    if not cond:
        ok = False


class Device:
    """Something on the cable at one address and one rate.

    `update_block` says whether it answers the update registers the way our
    bootloader does. A device that does not is the stranger case: it answers
    Modbus, it just does not mean the same thing by 0x0050.
    """

    def __init__(self, addr, baud, update_block=True, loader_ver=1,
                 status=u.LOADER_BIT, config_block=False):
        self.addr = addr
        self.baud = baud
        self.update_block = update_block
        self.loader_ver = loader_ver
        self.status = status
        # The bootloader refuses every register outside the update block, so a
        # probe sitting in it answers R_STATUS and NOT R_BAUD_CODE. That
        # asymmetry is why the sweep cannot use the config registers.
        self.config_block = config_block

    def frame(self, pdu):
        if pdu[0] != 3:
            return bytes([pdu[0] | 0x80, 1])
        addr, count = struct.unpack(">HH", pdu[1:5])
        regs = []
        for a in range(addr, addr + count):
            if a == u.R_STATUS and self.update_block:
                regs.append(self.status)
            elif a == u.R_LOADER_VER and self.update_block:
                regs.append(self.loader_ver)
            elif a in (u.R_LOADER_VER + 1, u.R_LOADER_VER + 2) \
                    and self.update_block:
                regs.append(0)
            elif a == u.R_BAUD_CODE and self.config_block:
                regs.append(0)
            elif self.update_block or self.config_block:
                return bytes([0x83, 2])
            else:
                # A device with an entirely different map. It answers, with
                # numbers, and they are not ours.
                regs.append(0xDEAD)
        return bytes([3, 2 * count]) + b"".join(struct.pack(">H", v)
                                                for v in regs)


class Line:
    def __init__(self, devices, baud):
        self.devices = devices
        self.baud = baud

    def set_baud(self, baud):
        self.baud = baud

    def exchange(self, adu, expect_len):
        del expect_len
        addr, pdu = adu[0], adu[1:-2]
        for d in self.devices:
            if d.addr == addr and d.baud == self.baud:
                rsp_pdu = d.frame(pdu)
                rsp = bytes([addr]) + rsp_pdu
                return rsp + struct.pack("<H", u.crc16(rsp))
        return b""      # silence: the wrong address, or the wrong rate

    def close(self):
        pass


def sweep(devices, asked_addr, asked_baud):
    line = Line(devices, asked_baud)
    bus = u.Bus(line, asked_addr)
    found = u.find_probe(line, bus, settle=0.0)
    return found, bus.addr, line.baud


def main():
    print("bootloader fallback identity")

    # A probe commissioned at address 22 / 38400 whose bootloader could not
    # read the record and came up at 3 / 9600. This is the regression.
    found, addr, baud = sweep([Device(3, 9600)], 22, 38400)
    check("a probe that fell back to the default identity is found", found)
    check("and the bus is left where it answered",
          (addr, baud) == (3, 9600), "got (%s, %s)" % (addr, baud))

    # The same probe, but the operator was already asking at address 3. There
    # is nothing to sweep and nothing to say.
    found, addr, baud = sweep([Device(3, 9600)], 3, 9600)
    check("no sweep is needed when the asked identity answers", found)
    check("and nothing was moved", (addr, baud) == (3, 9600))

    # A STRANGER at address 3: it answers every frame, with numbers that are
    # not ours. Adopting it would push firmware into somebody else's
    # instrument.
    found, addr, baud = sweep([Device(3, 9600, update_block=False)], 22, 38400)
    check("a device with a different register map is NOT adopted", not found)
    check("and the line is left where the operator put it",
          (addr, baud) == (22, 38400), "got (%s, %s)" % (addr, baud))

    # A stranger whose 0x0050 happens to answer, but with a state and error
    # this tool has no names for. In range is the whole test.
    bad = Device(3, 9600, status=0x7F7F, loader_ver=999)
    found, addr, baud = sweep([bad], 22, 38400)
    check("an out-of-range update block is NOT adopted", not found)

    # Nothing on the cable at all.
    found, addr, baud = sweep([], 22, 38400)
    check("an empty cable stays a failure", not found)
    check("and the line is restored", (addr, baud) == (22, 38400))

    # The fallback address at a rate other than 9600 - possible because the
    # loader's baud fallback and its address fallback are separate branches,
    # and a record can be readable enough for one and not the other.
    found, addr, baud = sweep([Device(3, 19200)], 22, 38400)
    check("the fallback address is swept at every rate, not just 9600", found)
    check("and lands on the rate that answered", (addr, baud) == (3, 19200))

    # A bootloader at the RIGHT address and the wrong rate. resync() asks the
    # config block, which a bootloader refuses at every rate, so this case is
    # invisible to the ordinary rate hunt and needs its own sweep.
    found, addr, baud = sweep([Device(22, 19200)], 22, 38400)
    check("a bootloader at the configured address is found at another rate",
          found)
    check("and the address is not changed to the fallback",
          (addr, baud) == (22, 19200), "got (%s, %s)" % (addr, baud))

    # The application, not the bootloader, at the fallback identity: it
    # answers the config block too, so find_probe's ordinary rate hunt finds
    # it first and the fallback sweep is never reached. Still has to work.
    found, addr, baud = sweep(
        [Device(3, 9600, status=0, config_block=True)], 22, 38400)
    check("an application at the fallback identity is found too", found)

    print("all passed" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
