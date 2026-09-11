#!/usr/bin/env python3
"""o2-probe interactive Modbus debugger CLI.

Communicates with the o2-probe over RS-485 Modbus RTU, providing:
  * Symbolic register read/write with engineering unit conversions.
  * Atomic multi-word heater-test override writes.
  * Memory peek with ELF symbol resolution and BUILD_ID safety checks: up to
    120 bytes per trigger through the wide block at 0x0100 (FW_VERSION 0x000D),
    one consistent snapshot, split across reads to fit --max-adu; the 4-word
    mailbox at 0x0065 on older or nodebug firmware.
  * Typed sensor diagnostic mailbox access (LMP91000, ADS1119, TMP117, SHT45).
  * Crash context decoding via arm-none-eabi-addr2line.
  * Arbitrary code execution mailbox (0x0150) for small Thumb-2 payloads in SRAM.

Usage:
    python3 tools/o2p_cli.py --port /dev/tty.usbserial-X read O2_COMP T_TIP HEATER_BLOCK
    python3 tools/o2p_cli.py --port ... write RH_SETPOINT 8000
    python3 tools/o2p_cli.py --port ... htest --arm --duty 20.0 --sp 45.0
    python3 tools/o2p_cli.py --port ... peek g_rm
    python3 tools/o2p_cli.py --port ... diag lmp-read 0x10
    python3 tools/o2p_cli.py --port ... diag gpio PB1          # or ADC_DRDY
    python3 tools/o2p_cli.py --port ... diag gpio --port B     # every bonded pin
    python3 tools/o2p_cli.py --port ... crash [--clear]
    python3 tools/o2p_cli.py --port ... exec "202a 4770"       # returns 42
    python3 tools/o2p_cli.py --port ... exec "3005 4770" --param 37 --timeout-ms 100
    python3 tools/o2p_cli.py --port ... exec payload.bin --param 0x1234
    python3 tools/o2p_cli.py --port ... exec --abort
"""

import argparse
import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2p_update import (Bus, ModbusException, NoReply, SerialLink, crc16)  # noqa: E402
# Only auto_max_adu() uses this, and only to NAME the link in its output - the
# limit is the probe's 255 either way. o2p_update.py is edited independently, so
# a copy without it must still import rather than take every command down.
try:
    from o2p_update import is_usb_serial_jtag  # noqa: E402
except ImportError:
    is_usb_serial_jtag = None

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.abspath(os.path.join(HERE, os.pardir))
DEFAULT_ELF = os.path.join(FW_DIR, ".pio", "build", "o2probe", "firmware.elf")
REGMAP_H = os.path.join(FW_DIR, "src", "regmap.h")

# Register definitions parsed from regmap.h
REGISTERS = {
    # Primary block (0x0000)
    "O2_COMP": 0x0000, "O2_RAW": 0x0001, "T_TIP": 0x0002, "T_CHAMBER": 0x0003,
    "RH_CHAMBER": 0x0004, "HEATER_DUTY": 0x0005, "FAULTS": 0x0006, "SETTLE_S": 0x0007,

    # Diagnostic block (0x0010)
    "VREF_MON_MV": 0x0010, "VA_MON_MV": 0x0011, "VIN_MON_MV": 0x0012,
    "AFE_VOUT_MV": 0x0013, "DEW_MARGIN": 0x0014, "PRESSURE_HPA": 0x0015,
    "UPTIME_HI": 0x0016, "UPTIME_LO": 0x0017, "FW_VERSION": 0x0018,
    "HW_REV": 0x0019, "RESET_CAUSE": 0x001A, "LMP_READBACK": 0x001B,
    "MB_CRC_ERRS": 0x001C, "MB_FRAME_ERRS": 0x001D, "I2C_ERRS": 0x001E,
    "EXP_DATA": 0x001F, "T_EXT": 0x001F, "SETTLE_RESTARTS": 0x0020, "SAMPLE_SEQ": 0x0021,
    "T_DIE": 0x0022, "FAULTS_EVER": 0x0023, "ADS_FAIL_COUNT": 0x0024,
    "WE_BUF_MV": 0x0025, "RE_BUF_MV": 0x0026, "CELL_BIAS_MV": 0x0027,
    "BUILD_ID_HI": 0x0028, "BUILD_ID_LO": 0x0029, "CMD_RESULT": 0x002A,
    "CAL_STATE": 0x002B, "T_AFE": 0x002C, "CE_MV": 0x002D,
    "HEATER_BLOCK": 0x002E, "SAMPLER_TIMING_MS": 0x002F,

    # Config block (0x0030)
    "SLAVE_ADDR": 0x0030, "BAUD_CODE": 0x0031, "PARITY_CODE": 0x0032,
    "RH_SETPOINT": 0x0033, "DT_MAX_K": 0x0034, "HEATER_MAX_DUTY": 0x0035,
    "HEATER_PWM_HZ": 0x0036, "CAL_AIR_NA_HI": 0x0037, "CAL_AIR_NA_LO": 0x0038,
    "CAL_TEMP_C100": 0x0039, "TEMPCO_PPM_K": 0x003A, "SHT_PULSE_H": 0x003B,
    "SHT_PULSE_TRIG": 0x003C, "CAL_TRIGGER": 0x003D, "COMMIT": 0x003E,
    "CONFIG_CRC": 0x003F, "HEATER_KP": 0x0040, "HEATER_KI": 0x0041,
    "ASSUMED_P_HPA": 0x0042, "CAL_AIR_FRAC": 0x0043, "CAL_P_HPA": 0x0044,
    "DIL_ALPHA": 0x0045, "CAL_ZERO_NA_HI": 0x0046, "CAL_ZERO_NA_LO": 0x0047,
    "HEATER_RH_CONSENT": 0x0048, "TIP_SETPOINT": 0x0049, "HEATER_TIP_CONSENT": 0x004A,

    # Heater test block (0x0060)
    "HEATER_TEST_ARM": 0x0060, "HEATER_TEST_DUTY": 0x0061,
    "HEATER_TEST_TIP_SP": 0x0062, "HEATER_TEST_KP": 0x0063, "HEATER_TEST_KI": 0x0064,

    # Memory peek block (0x0065)
    "PEEK_ADDR_HI": 0x0065, "PEEK_ADDR_LO": 0x0066, "PEEK_STATUS": 0x0067,
    "PEEK_W0_HI": 0x0068, "PEEK_W0_LO": 0x0069, "PEEK_W1_HI": 0x006A,
    "PEEK_W1_LO": 0x006B, "PEEK_W2_HI": 0x006C, "PEEK_W2_LO": 0x006D,
    "PEEK_W3_HI": 0x006E, "PEEK_W3_LO": 0x006F,

    # Wide peek block (0x0100), FW_VERSION 0x000D+, debug builds only
    "PEEKW_ADDR_HI": 0x0100, "PEEKW_ADDR_LO": 0x0101, "PEEKW_WORDS": 0x0102,
    "PEEKW_STATUS": 0x0103, "PEEKW_SEQ": 0x0104, "PEEKW_DATA": 0x0105,

    # Sensor diagnostic mailbox (0x0070)
    "DIAG_CMD": 0x0070, "DIAG_PARAM": 0x0071, "DIAG_STATUS": 0x0072,
    "DIAG_RDATA0": 0x0073, "DIAG_RDATA1": 0x0074, "DIAG_RDATA2": 0x0075,
    "DIAG_CRC_STATUS": 0x0076,

    # Crash context (0x0077)
    "CRASH_REASON": 0x0077, "CRASH_PC_HI": 0x0078, "CRASH_PC_LO": 0x0079,
    "CRASH_LR_HI": 0x007A, "CRASH_LR_LO": 0x007B, "CRASH_DETAIL_HI": 0x007C,
    "CRASH_DETAIL_LO": 0x007D, "CRASH_BUILD_ID_HI": 0x007E, "CRASH_BUILD_ID_LO": 0x007F,

    # Arbitrary code execution mailbox (0x0150), debug builds only
    "EXEC_CMD": 0x0150, "EXEC_LEN": 0x0151, "EXEC_PARAM_HI": 0x0152,
    "EXEC_PARAM_LO": 0x0153, "EXEC_TIMEOUT_MS": 0x0154, "EXEC_STATUS": 0x0155,
    "EXEC_RESULT_HI": 0x0156, "EXEC_RESULT_LO": 0x0157, "EXEC_CODE_START": 0x0158,
}

# 4 is FW_VERSION 0x000F+, and only on a part whose RAM_PARITY_CHECK option
# bit is enabled: SRAM outside .data/.bss, refused unread (src/regmap.h).
PEEK_STATUS_NAMES = {0: "NONE", 1: "OK", 2: "ERR_RANGE", 3: "ERR_ALIGN", 4: "ERR_PARITY"}
DIAG_STATUS_NAMES = {
    0: "NONE", 1: "PENDING", 2: "OK", 3: "ERR_OPCODE",
    4: "ERR_NACK", 5: "ERR_TIMEOUT", 6: "ERR_BUSY",
    # OP_READ_GPIO only, FW_VERSION 0x000E+ (src/regmap.h)
    7: "GPIO_NOT_SAMPLED", 8: "ERR_GPIO_UNCLOCKED", 9: "ERR_GPIO_NO_PIN",
}
CRASH_REASONS = {0: "NONE", 1: "HARDFAULT", 2: "ASSERT", 3: "IWDG"}

EXEC_MAGIC = 0x5A00
EXEC_OP_RUN = 0x0001
EXEC_OP_ABORT = 0x0000

EXEC_STATUS_NONE = 0
EXEC_STATUS_PENDING = 1
EXEC_STATUS_OK = 2
EXEC_STATUS_ERR_OPCODE = 3
EXEC_STATUS_ERR_LEN = 4
EXEC_STATUS_FAULT = 5
EXEC_STATUS_TIMEOUT = 6

EXEC_STATUS_NAMES = {
    0: "NONE", 1: "PENDING", 2: "OK", 3: "ERR_OPCODE",
    4: "ERR_LEN", 5: "FAULT_INTERCEPTED", 6: "TIMEOUT_EXPIRED",
}

# HEATER_BLOCK (0x002E) decode, bits in heater_ctl.h order. Bits 14/15 are
# ANNOTATIONS, not refusals, since FW_VERSION 0x0010: a loop in command with
# no demand (IDLE), and the stored tip setpoint at the 0x8000 sentinel
# (TIP_DISARMED). Before 0x0010 they read as zeros.
HB_BITS = [
    "NOT_COMPILED", "CONFIG_OFF", "SAFETY", "NO_RH",
    "NO_TIP", "NO_CHAMBER", "TIP_LIMIT", "DT_LIMIT",
    "RUNAWAY", "SUPPLY", "PIN_INTEGRITY", "STALE", "NO_CONSENT",
    "BLIND", "IDLE*", "TIP_DISARMED*",
]

# FAULTS (0x0006) / FAULTS_EVER (0x0023) decode, faults.h order. FAULTS_EVER
# ORs every bit seen since power-up (main.c), so it reads as history, not
# state; e.g. 0x8301 after a bake-and-reboot is SETTLING|HEATER_RUNAWAY|
# TEMP_OVER|HEATER_DISABLED, every one expected.
FAULT_BITS = [
    "SETTLING", "I2C_FAIL_LMP", "I2C_FAIL_ADS", "I2C_FAIL_TMP",
    "I2C_FAIL_SHT", "AFE_CONFIG_MISMATCH", "VA_LOW", "VIN_LOW",
    "HEATER_RUNAWAY", "TEMP_OVER", "DEW_SUSPECT", "ADC_RANGE",
    "CAL_DEFAULT", "ADS_DRDY_STUCK", "ADS_CONFIG_LOST", "HEATER_DISABLED",
]

# RESET_CAUSE (0x001A) is (RCC_CSR >> 24) & 0xFF, a BITFIELD (mcu.h:27-43):
# two causes can be set at once, e.g. 0x14 = PIN|SFT for a software reset
# with the NRST pulse riding along. 0xFFFF is "could not be recovered".
RESET_CAUSE_BITS = {
    1: "OBL", 2: "PIN", 3: "PWR", 4: "SFT",
    5: "IWDG", 6: "WWDG", 7: "LPWR",
}

# Write to arm the heater test block; 0 disarms. Reads back 1/0 by design
# (regmap.h:452), never the magic. Canonical home: O2P_HEATER_TEST_MAGIC,
# regmap.h:721.
HEATER_TEST_MAGIC = 0x8EA7


def resolve_reg(name_or_addr):
    s = name_or_addr.strip().upper()
    if s in REGISTERS:
        return REGISTERS[s], s
    if s.startswith("0X"):
        addr = int(s, 16)
    elif s.isdigit():
        addr = int(s, 10)
    else:
        raise ValueError("Unknown register name or address: %s" % name_or_addr)
    # Reverse lookup name
    name = next((k for k, v in REGISTERS.items() if v == addr), "0x%04X" % addr)
    return addr, name


def format_reg(name, val):
    if name in ("RESET_CAUSE",):
        # NOT the u16 invalid sentinel: 0xFFFF here is its own meaning
        # ("CSR not parked", mcu.h) and must be decoded as such.
        if val == 0xFFFF:
            return "0xFFFF (unknown: CSR not parked)"
        active = [nm for bit, nm in sorted(RESET_CAUSE_BITS.items())
                  if val & (1 << bit)]
        return "0x%04X (%s)" % (val, "|".join(active) if active else "none")
    if val == 0xFFFF:
        return "0xFFFF (invalid)"
    if name in ("O2_COMP",):
        return "%.2f %%vol" % (val / 100.0)
    if name in ("O2_RAW",):
        signed = val if val < 32768 else val - 65536
        return "%d nA" % (signed * 10)
    if name in ("T_TIP", "T_CHAMBER", "T_DIE", "T_AFE"):
        signed = val if val < 32768 else val - 65536
        if signed == -32768:
            return "invalid"
        return "%.2f C" % (signed / 100.0)
    if name in ("RH_CHAMBER",):
        return "%.2f %%RH" % (val / 100.0)
    if name in ("HEATER_DUTY",):
        return "%.2f %%" % (val / 100.0)
    if name in ("HEATER_BLOCK",):
        active = [HB_BITS[i] for i in range(len(HB_BITS)) if val & (1 << i)]
        return "0x%04X (%s)" % (val, "|".join(active) if active else "none")
    if name in ("FAULTS", "FAULTS_EVER"):
        active = [FAULT_BITS[i] for i in range(len(FAULT_BITS))
                  if val & (1 << i)]
        return "0x%04X (%s)" % (val, "|".join(active) if active else "none")
    if name in ("SAMPLER_TIMING_MS",):
        return "%d ms" % val
    if name in ("BUILD_ID_HI", "BUILD_ID_LO"):
        return "0x%04X" % val
    return "0x%04X (%d)" % (val, val)


class AmbiguousSymbol(LookupError):
    """One name, several objects in the ELF: nothing says which was meant."""


def get_elf_symbols(elf_path):
    """{name: [(address, size), ...]} from the ELF, via arm-none-eabi-nm or nm.

    The size is nm -S's, i.e. the symbol table's st_size, so a struct's size
    comes from the compiler rather than from anyone's arithmetic; 0 where the
    symbol has none (labels, some assembler symbols). pyelftools would give
    the same number, and is not a dependency this tree has.

    A LIST PER NAME, because a name is not unique: file-local statics in two
    translation units share it. The 2026-09-10 env:o2probe ELF has two
    `finish`, two `s_sequence` and two `s_live_page`. A dict of one entry kept
    whichever nm printed last, and a peek of the wrong object reads as a
    plausible answer. resolve_peek_target() refuses a name with more than one.
    """
    nm_bins = ["arm-none-eabi-nm", "nm"]
    for nm in nm_bins:
        try:
            p = subprocess.run([nm, "-C", "-S", elf_path],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True)
            symbols = {}
            for line in p.stdout.splitlines():
                parts = line.strip().split()
                # "addr size type name" when the symbol has a size,
                # "addr type name" when it does not.
                if len(parts) == 4:
                    name, entry = parts[3], (int(parts[0], 16), int(parts[1], 16))
                elif len(parts) == 3:
                    name, entry = parts[2], (int(parts[0], 16), 0)
                else:
                    continue
                entries = symbols.setdefault(name, [])
                if entry not in entries:
                    entries.append(entry)
            return symbols
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    raise RuntimeError("Neither arm-none-eabi-nm nor nm available for symbol lookup")


def get_probe_build_id(bus):
    regs = bus.read(REGISTERS["BUILD_ID_HI"], 2)
    b_id = (regs[0] << 16) | regs[1]
    dirty = bool(b_id & 0x80000000)
    debug = bool(b_id & 0x40000000)
    sha = "%07x" % (b_id & 0x0FFFFFFF)
    return b_id, sha, dirty, debug


def get_elf_build_id(elf_path):
    for nm_cmd in ["arm-none-eabi-nm", "nm"]:
        try:
            out = subprocess.check_output([nm_cmd, elf_path], stderr=subprocess.DEVNULL).decode()
            addr = None
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[2] == "g_o2p_build_id":
                    addr = int(parts[0], 16)
                    break
            if addr is None:
                continue
            for objdump_cmd in ["arm-none-eabi-objdump", "objdump"]:
                try:
                    d_out = subprocess.check_output(
                        [objdump_cmd, "-s", "-j", ".data", elf_path],
                        stderr=subprocess.DEVNULL).decode()
                    data_bytes = bytearray()
                    base_addr = None
                    for line in d_out.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and len(parts[0]) == 8 and all(c in "0123456789abcdefABCDEF" for c in parts[0]):
                            cur_addr = int(parts[0], 16)
                            if base_addr is None:
                                base_addr = cur_addr
                            for hex_chunk in parts[1:]:
                                if len(hex_chunk) == 8 and all(c in "0123456789abcdefABCDEF" for c in hex_chunk):
                                    data_bytes.extend(bytes.fromhex(hex_chunk))
                    if base_addr is not None:
                        offset = addr - base_addr
                        if 0 <= offset <= len(data_bytes) - 4:
                            return struct.unpack("<I", data_bytes[offset:offset+4])[0]
                except Exception:
                    pass
        except Exception:
            pass
    return None


def check_build_id(bus, elf_path, force=False):
    if not os.path.exists(elf_path):
        if force:
            return None, None, False, False
        raise RuntimeError("ELF file not found: %s" % elf_path)
    b_id, sha, dirty, debug = get_probe_build_id(bus)
    elf_b_id = get_elf_build_id(elf_path)
    if elf_b_id is None:
        # A check that could not run is not a check that passed. Silently
        # skipping here resolved symbols against an ELF nothing had matched to
        # the probe -- the exact failure --force-build-id exists to make
        # deliberate.
        msg = ("could not read g_o2p_build_id from %s "
               "(arm-none-eabi-nm / objdump missing, or symbol absent)" % elf_path)
        if force:
            print("!! WARNING: %s (proceeding UNVERIFIED due to --force-build-id)" % msg)
        else:
            raise RuntimeError("%s. Refusing symbol lookup; "
                               "pass --force-build-id to override." % msg)
    else:
        probe_commit = b_id & 0x0FFFFFFF
        elf_commit = elf_b_id & 0x0FFFFFFF
        if probe_commit != elf_commit:
            msg = "Build ID MISMATCH: probe is %07x, ELF is %07x" % (probe_commit, elf_commit)
            if force:
                print("!! WARNING: %s (ignoring due to --force-build-id)" % msg)
            else:
                raise RuntimeError("%s. Refusing symbol lookup!" % msg)
    if dirty:
        print("!! WARNING: Probe running DIRTY build (%s*); symbols may drift!" % sha)
    return b_id, sha, dirty, debug


# ---------------------------------------------------------------- Commands

def cmd_read(bus, args):
    for target in args.targets:
        addr, name = resolve_reg(target)
        vals = bus.read(addr, 1)
        print("  %-22s : %s" % (name, format_reg(name, vals[0])))


def cmd_write(bus, args):
    addr, name = resolve_reg(args.target)
    val_str = args.value.strip()
    val = int(val_str, 16) if val_str.upper().startswith("0X") else int(val_str)
    bus.write(addr, [val])
    print("  Wrote 0x%04X (%d) to %s (0x%04X)" % (val, val, name, addr))


def cmd_htest(bus, args):
    duty = int(args.duty * 100.0) if args.duty is not None else 0
    sp = int(args.sp * 100.0) if args.sp is not None else 0x8000
    kp = int(args.kp * 100.0) if args.kp is not None else 100
    ki = int(args.ki * 100.0) if args.ki is not None else 20
    arm_magic = HEATER_TEST_MAGIC if args.arm else 0x0000
    block = [arm_magic, duty, sp, kp, ki]
    bus.write(REGISTERS["HEATER_TEST_ARM"], block)
    print("  Heater test block written atomically:")
    print("    ARM=%s, DUTY=%.2f %%, SP=%s, KP=%.2f, KI=%.2f"
          % ("ARMED" if args.arm else "DISARMED", duty / 100.0,
             "none" if sp in (0x8000, -32768) else "%.2f C" % (sp / 100.0),
             kp / 100.0, ki / 100.0))


def cmd_config(bus, args):
    addr, name = resolve_reg(args.target)
    val_str = args.value.strip()
    val = int(val_str, 16) if val_str.upper().startswith("0X") else int(val_str)
    bus.write(addr, [val])
    print("  Config written to RAM: %s = 0x%04X (%d)" % (name, val, val))
    if args.commit:
        bus.write(REGISTERS["COMMIT"], [0x5AC1])
        time.sleep(0.05)
        res = bus.read(REGISTERS["CMD_RESULT"], 1)[0]
        c_status = res & 0xFF
        s_str = {0: "NONE", 1: "PENDING", 2: "OK", 3: "FAILED"}.get(c_status, "UNKNOWN")
        print("  Commit flash result: %s (CMD_RESULT=0x%04X)" % (s_str, res))
        if c_status != 2:
            sys.exit(1)


# ---------------------------------------------------------------- Peek
#
# Two blocks answer a peek (src/regmap.h). Both refuse the same targets with the
# same status codes, because the firmware checks one table for both:
#   0x0065  4-word mailbox, FW_VERSION 0x000C+ (0x000B: a fixed 4-word burst)
#   0x0100  wide block, 1..30 words per trigger, snapshotted, FW_VERSION 0x000D+
# Neither answers on a nodebug build (exception 02), whatever FW_VERSION says.

FW_PEEK_COUNT = 0x000C
FW_WIDE_PEEK = 0x000D
# 0x000F: a busy diagnostic mailbox refuses with exception 06 and writes
# nothing (up to 0x000E: exception 03 plus DIAG_STATUS 6 ERR_BUSY over the
# queued command's PENDING), and a peek may answer 4 ERR_PARITY.
# 0x0011: heater supply veto removed, arbitrary code execution mailbox (0x0150).
FW_BUSY_IS_EXCEPTION = 0x000F
FW_LATEST = 0x0011
MB_EX_BUSY = 6
PEEK_OK = 1
PEEKW_BASE = 0x0100
PEEKW_HEADER = 5
PEEKW_DATA = PEEKW_BASE + PEEKW_HEADER
PEEKW_WORDS_MAX = 30          # O2P_PEEKW_WORDS_MAX
MB_MAX_READ_REGS = 125        # O2P_MB_MAX_READ_REGS, src/modbus_pdu.c

# The largest REPLY ADU each path carries, read from the code 2026-09-10 and
# not measured on a cable (FIRMWARE.md, "Wide peek block"). Every path this CLI
# can open itself - a USB-RS485 dongle, or the node's USB console relay - is
# limited by the probe's own 125-register FC03, 255 bytes; the radio figures
# are here for a transport that reuses plan_wide_reads().
#
# THE RADIO FIGURES ASSUME A FULL FOpts. The node uplinks a relayed reply as
# the raw ADU (node-prototype main.cpp relay(): reply_push(rbuf, rlen,
# O2P_FPORT)), and RadioLib 7.7.1 refuses a payload longer than
# getMaxPayloadLen() = payloadLenMax[dr] - fOptsUpLen (LoRaWAN.cpp:3785-3805),
# with payloadLenMax 51/51/51/115/242/242 for EU868 DR0..DR5
# (LoRaWANBands.cpp:25). The node drops such a reply for good (main.cpp,
# PACKET_TOO_LONG). Pending MAC answers take up to
# RADIOLIB_LORAWAN_FHDR_FOPTS_MAX_LEN = 15 bytes (LoRaWAN.h:124) and nobody
# on this side can see how many are pending, so each preset is the EU868
# figure minus 15: a ceiling that holds whatever the MAC layer is doing.
LORAWAN_FOPTS_MAX = 15
MAX_ADU_PRESETS = {
    "dongle": 255,        # USB-RS485: probe O2P_MB_MAX_READ_REGS
    "swd": 255,           # bridge mailbox tx/rx[O2P_MB_MAX_ADU]
    "node": 255,          # node-prototype serbus.h SERBUS_MAX_ADU / MAX_FRAME
    "lorawan-dr4": 242 - LORAWAN_FOPTS_MAX,   # 227, reply uplinked at DR4/DR5
    "lorawan-dr3": 115 - LORAWAN_FOPTS_MAX,   # 100
    "lorawan-dr0": 51 - LORAWAN_FOPTS_MAX,    # 36, DR0..DR2
    "a8": 46,             # Dragino A8: manual's 46-byte uplink data, UNVERIFIED
}
PROBE_MAX_ADU = 255


class PeekTorn(IOError):
    """The pieces of a peek did not come from the trigger this tool issued."""


def parse_max_adu(text):
    s = text.strip().lower()
    if s == "auto":
        return None
    if s in MAX_ADU_PRESETS:
        return MAX_ADU_PRESETS[s]
    try:
        n = int(s, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--max-adu takes auto, %s, or a byte count"
            % ", ".join(sorted(MAX_ADU_PRESETS)))
    if n < 5 + 2 * (PEEKW_HEADER + 2):
        raise argparse.ArgumentTypeError(
            "--max-adu %d cannot carry the wide block's header and one word "
            "(needs %d)" % (n, 5 + 2 * (PEEKW_HEADER + 2)))
    return n


def auto_max_adu(port):
    """Every link this CLI opens is limited by the probe, not the path."""
    try:
        node = is_usb_serial_jtag is not None and is_usb_serial_jtag(port)
    except Exception:
        node = False
    return PROBE_MAX_ADU, ("node USB serial relay" if node else "serial line")


def max_read_regs(max_adu):
    return min(MB_MAX_READ_REGS, (max_adu - 5) // 2)


def max_narrow_words(max_adu):
    """Words the 4-word mailbox may return under `max_adu`, never above 4.

    The mailbox reply is 3 header registers plus 2 per word, and an FC03 ADU is
    5 framing bytes plus 2 per register: 11 + 4*words bytes. N2 (review,
    2026-09-10): peek_bytes always asked for four words on the narrow path, a
    27-byte reply, even under `--max-adu 19` - a ceiling that link then drops.
    Unlike the wide block, the mailbox has no way to split a burst, so the only
    lever is how many words one trigger asks for.
    """
    return min(4, (max_adu - 11) // 4)


def plan_wide_reads(words, max_adu):
    """The FC03s that carry a `words`-word snapshot home under `max_adu`.

    [(first_register, count), ...]: the first covers the header and as many
    WHOLE words as fit, the rest whole words only. A word is never split across
    two reads, so a failure between them cannot leave half a word looking like
    data. More than one entry means the caller must re-read the header after
    the last one - that is what proves the pieces share a snapshot.
    """
    if not 1 <= words <= PEEKW_WORDS_MAX:
        raise ValueError("a wide peek is 1..%d words, not %d" % (PEEKW_WORDS_MAX, words))
    per = max_read_regs(max_adu)
    if per < PEEKW_HEADER + 2:
        raise ValueError("max ADU %d cannot carry the header and one word" % max_adu)
    data = 2 * words
    first = min(data, ((per - PEEKW_HEADER) // 2) * 2)
    reads = [(PEEKW_BASE, PEEKW_HEADER + first)]
    off = first
    step = (per // 2) * 2
    while off < data:
        n = min(step, data - off)
        reads.append((PEEKW_DATA + off, n))
        off += n
    return reads


def peek_wide(bus, addr, words, max_adu):
    """One trigger, as few reads as max_adu allows. Returns (status, seq, words).

    The firmware validates the address and the count; this only checks that
    what came back is the answer to THIS trigger. Raises PeekTorn when it is
    not - never returns data it cannot vouch for.

    The reads are PLANNED BEFORE THE TRIGGER IS SENT. A ceiling that cannot
    carry the header and one word is refused with nothing on the wire, rather
    than after a trigger has replaced whatever the block held - possibly
    another master's snapshot, half-read.
    """
    reads = plan_wide_reads(words, max_adu)
    bus.write(PEEKW_BASE, [(addr >> 16) & 0xFFFF, addr & 0xFFFF, words])
    # The first planned read always starts at the header (plan_wide_reads),
    # so the header is taken from it unconditionally: there is no path on
    # which it could be missing.
    first = bus.read(*reads[0])
    header, regs = first[:PEEKW_HEADER], list(first[PEEKW_HEADER:])
    for base, count in reads[1:]:
        regs.extend(bus.read(base, count))
    if len(reads) > 1:
        closing = bus.read(PEEKW_BASE, PEEKW_HEADER)
        if closing != header:
            raise PeekTorn(
                "the wide peek block changed between reads (SEQ %d -> %d): "
                "another master triggered a peek; nothing from this attempt "
                "is trustworthy" % (header[4], closing[4]))
    held = (header[0] << 16) | header[1]
    if held != addr or header[2] != words:
        raise PeekTorn(
            "the block holds %d words at 0x%08X, not the %d at 0x%08X this "
            "trigger asked for: another master triggered in between"
            % (header[2], held, words, addr))
    status, seq = header[3], header[4]
    if status != PEEK_OK:
        return status, seq, []
    return status, seq, [(regs[2 * i] << 16) | regs[2 * i + 1] for i in range(words)]


def peek_narrow(bus, addr, words, fw_version):
    """The 4-word mailbox at 0x0065. Returns (status, words).

    ASSUMES SOLE OWNERSHIP of the mailbox for the trigger/read pair. The header
    echoes the address but not the word count, so a shorter peer trigger at the
    same address in between returns 0xFFFFFFFF padding this cannot distinguish
    from data (N3). cmd_peek() prints that caveat; the wide block, which echoes
    WORDS and SEQ, is used instead whenever the firmware supports it.
    """
    if not 1 <= words <= 4:
        raise ValueError("the 4-word mailbox takes 1..4 words, not %d" % words)
    hi, lo = (addr >> 16) & 0xFFFF, addr & 0xFFFF
    if fw_version >= FW_PEEK_COUNT:
        # The count is SENT, so the firmware checks it against the region;
        # a fixed 4-word burst made a 1-word peek at a region's last word
        # look like a range error.
        bus.write(REGISTERS["PEEK_ADDR_HI"], [hi, lo, words])
    else:
        # 0x000B knows only the 2-register form: always 4 words, refused
        # wherever 4 do not fit.
        bus.write(REGISTERS["PEEK_ADDR_HI"], [hi, lo])
    regs = bus.read(REGISTERS["PEEK_ADDR_HI"], 3 + 2 * words)
    if ((regs[0] << 16) | regs[1]) != addr:
        raise PeekTorn("the mailbox holds a peek at 0x%08X, not 0x%08X: another "
                       "master triggered in between" % ((regs[0] << 16) | regs[1], addr))
    status = regs[2]
    if status != PEEK_OK:
        return status, []
    return status, [(regs[3 + 2 * i] << 16) | regs[4 + 2 * i] for i in range(words)]


def peek_bytes(bus, addr, nbytes, max_adu, fw_version, narrow=False, log=print):
    """Read `nbytes` from `addr`, word-aligned. Returns a dict describing it.

    The firmware refuses a misaligned target, and most symbols worth reading -
    a uint16_t, a char array - are not 4-byte aligned, so the request is
    rounded OUT to whole words and the caller slices the bytes it asked for.
    """
    start = addr & ~3
    total_words = (addr + nbytes - start + 3) // 4
    wide = (not narrow) and fw_version >= FW_WIDE_PEEK
    # The narrow burst cap under this ceiling, refused up front rather than
    # after a trigger has fired (N2). Computed even when starting wide, because
    # a wide block that answers exception 02 falls back to the mailbox below.
    narrow_cap = max_narrow_words(max_adu)
    if not wide and narrow_cap < 1:
        raise ValueError("max ADU %d cannot carry even a one-word mailbox reply "
                         "(needs 15)" % max_adu)
    words, snapshots, off = [], 0, 0
    while off < total_words:
        a = start + 4 * off
        if wide:
            n = min(PEEKW_WORDS_MAX, total_words - off)
            try:
                status, _seq, got = peek_wide(bus, a, n, max_adu)
            except ModbusException as e:
                if e.code != 2 or snapshots:
                    raise
                # NOT "using the mailbox": on a nodebug build - the likeliest
                # reason for this 02 - 0x0065 is compiled out too and refuses
                # the same way, and cmd_peek() then says so. The note must not
                # promise a read that cannot happen there.
                log("   note: 0x%04X answers exception 02 although FW_VERSION is "
                    "0x%04X - either the debug blocks are compiled out (a nodebug "
                    "build, which refuses 0x0065 too) or the image lacks the wide "
                    "block; trying the 4-word mailbox at 0x0065"
                    % (PEEKW_BASE, fw_version))
                wide = False
                if narrow_cap < 1:
                    raise ValueError(
                        "max ADU %d cannot carry a one-word mailbox reply, and "
                        "the wide block is unavailable (needs 15)" % max_adu)
                continue
        else:
            n = min(narrow_cap, total_words - off)
            status, got = peek_narrow(bus, a, n, fw_version)
        snapshots += 1
        if status != PEEK_OK:
            return {"status": status, "at": a, "words": words, "start": start,
                    "snapshots": snapshots, "wide": wide}
        words.extend(got)
        off += n
    raw = b"".join(struct.pack("<I", w) for w in words)   # the core is little-endian
    return {"status": PEEK_OK, "at": None, "words": words, "start": start,
            "snapshots": snapshots, "wide": wide,
            "bytes": raw[addr - start:addr - start + nbytes]}


def resolve_peek_target(args, symbols_fn=None):
    """(address, byte count, label) from a symbol or a literal address."""
    target = args.target.strip()
    size = None
    if target.upper().startswith("0X") or target.isdigit():
        addr = int(target, 0)
        label = "0x%08X" % addr
    else:
        symbols = (symbols_fn or get_elf_symbols)(args.elf)
        if target not in symbols:
            raise KeyError("Symbol '%s' not found in %s" % (target, args.elf))
        entries = symbols[target]
        if len(entries) != 1:
            raise AmbiguousSymbol(
                "symbol '%s' names %d objects in %s (file-local statics share "
                "a name across translation units): %s. Nothing here says which "
                "one you meant - peek the address, e.g. `peek 0x%08X --bytes %d`"
                % (target, len(entries), args.elf,
                   ", ".join("0x%08X (%d bytes)" % e for e in entries),
                   entries[0][0], entries[0][1] or 4))
        addr, size = entries[0]
        label = "%s (0x%08X)" % (target, addr)
    if args.bytes is not None:
        nbytes = args.bytes
    elif args.count is not None:
        nbytes = 4 * args.count
    elif size:
        nbytes = size
    else:
        nbytes = 4
        if size == 0:
            print("   note: %s has no size in the ELF; reading one word "
                  "(pass --bytes or --count)" % target)
    if nbytes < 1:
        raise ValueError("nothing to read: %d bytes" % nbytes)
    return addr, nbytes, label


def cmd_peek(bus, args):
    b_id, _sha, _dirty, debug = check_build_id(bus, args.elf, force=args.force_build_id)
    try:
        addr, nbytes, label = resolve_peek_target(args)
    except (KeyError, AmbiguousSymbol) as e:
        print("  !! %s" % (e.args[0] if e.args else e))
        sys.exit(1)
    if args.max_adu is None:
        max_adu, why = auto_max_adu(args.port)
    else:
        max_adu, why = args.max_adu, "--max-adu"
    fw = bus.read(REGISTERS["FW_VERSION"], 1)[0]

    try:
        res = peek_bytes(bus, addr, nbytes, max_adu, fw, narrow=args.narrow)
    except ModbusException as e:
        if e.code != 2:
            raise
        # Both peek blocks refused as undefined addresses. That is a nodebug
        # image, whatever FW_VERSION says - a nodebug build reports the same
        # version (src/regmap.h). BUILD_ID bit 30 is quoted only when it was
        # read; an image older than faf52d8 has it clear either way.
        print("  !! 0x%04X answers exception 02: debug blocks compiled out (an "
              "O2P_DEBUG_ENABLE=0 build%s). This image has no memory peek; "
              "nothing was read."
              % (REGISTERS["PEEK_ADDR_HI"],
                 "" if b_id is None else
                 ", BUILD_ID bit 30 reads %d" % (1 if debug else 0)))
        sys.exit(1)
    print("  Peek %s, %d bytes:" % (label, nbytes))
    print("    Path     : %s, FW_VERSION 0x%04X, max ADU %d (%s)"
          % ("wide block 0x0100" if res["wide"] else "4-word mailbox 0x0065",
             fw, max_adu, why))
    if not res["wide"]:
        # N3: the legacy mailbox echoes the address but not the word COUNT, so
        # a shorter peer trigger at the same address, serialized before this
        # read, returns unused-slot 0xFFFFFFFF padding that reads as memory
        # (and 0xFFFFFFFF is also erased flash, so value cannot tell). The wide
        # block has WORDS and SEQ and is preferred whenever FW_VERSION allows;
        # here it was not available. Re-reading the mailbox header cannot close
        # this - it carries no count either - so the tool states the assumption
        # rather than pretending to have checked it.
        print("    !! assumes sole ownership of the 0x0065 mailbox: it echoes "
              "no word count, so a shorter peer peek at this address between "
              "trigger and read would return padding as data undetectably. "
              "Use the wide block (FW_VERSION 0x000D+, no --narrow) for a "
              "shared bus.")
    if res["status"] != PEEK_OK:
        print("    Status   : %s at 0x%08X"
              % (PEEK_STATUS_NAMES.get(res["status"], "ERR_%d" % res["status"]),
                 res["at"]))
        sys.exit(1)
    print("    Status   : OK, %d trigger(s)" % res["snapshots"])
    if res["snapshots"] > 1:
        per = PEEKW_WORDS_MAX * 4 if res["wide"] else 16
        print("!! NOT ONE MOMENT: %d triggers, each consistent within its own "
              "%d bytes only; a struct spanning two may be torn"
              % (res["snapshots"], per))
    start = res["start"]
    # Offsets are from the symbol, so a word that starts before an unaligned
    # symbol prints as a small negative offset rather than silently as +0.
    for i, w in enumerate(res["words"]):
        rel = start + 4 * i - addr
        print("    [%s0x%03X] 0x%08X  (%d)" % ("-" if rel < 0 else "+", abs(rel), w, w))
    body = res["bytes"]
    for off in range(0, len(body), 16):
        chunk = body[off:off + 16]
        print("    %04x  %-47s  %s" % (off, " ".join("%02x" % b for b in chunk),
                                       "".join(chr(b) if 32 <= b < 127 else "."
                                               for b in chunk)))


def cmd_diag(bus, args):
    sub = args.diag_cmd.lower()
    op = 0
    param = 0
    if sub == "gpio":
        rc = cmd_diag_gpio(bus, args)
        if rc:
            sys.exit(rc)
        return
    if getattr(args, "gpio_port", None) is not None:
        raise ValueError("--port after 'diag' belongs to 'diag gpio' only")
    param_text = args.param if args.param is not None else "0"

    if sub == "lmp-read":
        op = 0x01
        param = int(param_text, 0)
    elif sub == "lmp-trim":
        op = 0x02
        param = int(param_text, 0)
    elif sub == "ads-status":
        op = 0x03
    elif sub == "ads-config":
        op = 0x04
    elif sub == "tmp-read":
        op = 0x05
        param = (getattr(args, "dev", 0) << 8) | int(param_text, 0)
    elif sub == "sht-serial":
        op = 0x06
    elif sub == "sht-sample":
        op = 0x07
    else:
        raise ValueError("Unknown diag command: %s" % sub)

    cmd_word = 0x5A00 | op
    try:
        bus.write(REGISTERS["DIAG_CMD"], [cmd_word, param])
    except ModbusException as e:
        if e.code != MB_EX_BUSY:
            raise
        print("  !! the probe answered exception 06 (busy): an earlier diagnostic "
              "command is still queued on it, and nothing of '%s' was queued. "
              "Retry once that one has run." % sub)
        sys.exit(1)

    # Poll until THIS command's status is final (max 1000 ms). Two rules, both
    # from review F2 (2026-09-10):
    #   * The command and parameter are read with every status and must be
    #     ours. Another master may queue its own once ours has run, and its
    #     status would otherwise be printed as this command's.
    #   * ERR_BUSY is not final. This command was ACCEPTED, so it never
    #     produces ERR_BUSY; on FW_VERSION <= 0x000E that value is another
    #     master's refused write overwriting our PENDING while ours is still
    #     queued, and the real result is yet to come. 0x000F+ never writes it.
    t0 = time.time()
    while time.time() - t0 < 1.0:
        regs = bus.read(REGISTERS["DIAG_CMD"], 7)
        if regs[0] != cmd_word or regs[1] != (param & 0xFFFF):
            raise DiagTorn("the mailbox holds command 0x%04X param 0x%04X, not "
                           "0x%04X 0x%04X: another master's command replaced "
                           "this one; its status is not reported as ours"
                           % (regs[0], regs[1], cmd_word, param & 0xFFFF))
        regs = regs[2:]
        st = regs[0]
        if st not in (DIAG_PENDING, DIAG_ERR_BUSY):
            st_str = DIAG_STATUS_NAMES.get(st, "STATUS_%d" % st)
            print("  Diag '%s' result: %s" % (sub, st_str))
            if st == 2:
                r0 = regs[1]
                r1 = regs[2]
                r2 = regs[3]
                crc_st = regs[4]
                print("    RDATA0: 0x%04X (%d)" % (r0, r0))
                if sub in ("sht-serial", "sht-sample"):
                    print("    RDATA1: 0x%04X (%d)" % (r1, r1))
                if sub == "sht-sample":
                    print("    RDATA2: 0x%04X, CRC_STATUS: 0x%04X" % (r2, crc_st))
            return
        time.sleep(0.05)
    print("  !! Diag command timed out waiting for execution")
    sys.exit(1)


# ---------------------------------------------------------------- GPIO
#
# OP_READ_GPIO (0x08), FW_VERSION 0x000E+, debug builds only. The encoding and
# the packing are src/gpio_diag.h's; the bonded-pin masks are READ from there
# and the signal names from src/board_pins.h, so neither can drift from the
# firmware here.
#
# The rule this section exists to keep: a level is printed ONLY when the
# firmware sent status OK with LEVEL_VALID. An analog-mode pin reads 0 in IDR
# whatever the pad is at, and printing that 0 as LOW is how PB1 (ADC_DRDY) hid
# for a whole bring-up and got a healthy ADS1119 replaced.

OP_READ_GPIO = 0x08
FW_READ_GPIO = 0x000E
GPIO_DIAG_H = os.path.join(FW_DIR, "src", "gpio_diag.h")
BOARD_PINS_H = os.path.join(FW_DIR, "src", "board_pins.h")

GPIO_PORTS = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
GPIO_LETTERS = {v: k for k, v in GPIO_PORTS.items()}
DIAG_OK, DIAG_PENDING, DIAG_ERR_BUSY = 2, 1, 6
GPIO_NOT_SAMPLED, GPIO_UNCLOCKED, GPIO_NO_PIN = 7, 8, 9

R0_MODE_MASK = 0x0003
R0_PULL_SHIFT, R0_PULL_MASK = 2, 0x000C
R0_OPEN_DRAIN = 0x0010
R0_ODR = 0x0020
R0_LEVEL = 0x0040
R0_AF_SHIFT, R0_AF_MASK = 8, 0x0F00
R0_LEVEL_VALID = 0x4000
R0_CONFIG_VALID = 0x8000

GPIO_MODES = {0: "input", 1: "output", 2: "alternate", 3: "analog"}
GPIO_PULLS = {0: "no pull", 1: "pull-up", 2: "pull-down", 3: "pull=11 (reserved)"}
MODE_OUTPUT, MODE_AF, MODE_ANALOG = 1, 2, 3

DRIVEN_NOT_REACHED = "driven level not reached - overloaded or shorted?"


class DiagTorn(IOError):
    """The diagnostic mailbox held somebody else's command when this tool read
    it back, so the status beside it is not this tool's to report."""


class GpioTorn(DiagTorn):
    """The mailbox held somebody else's command when this tool read it back."""


def load_bonded(path=GPIO_DIAG_H):
    """{port index: bonded-pin mask} from gpio_diag.h's O2P_GPIO_BONDED_*."""
    text = open(path, encoding="utf-8").read()
    masks = {GPIO_PORTS["E"]: 0}
    for letter in "ABCDF":
        m = re.search(r"#define\s+O2P_GPIO_BONDED_%s\s+(0x[0-9A-Fa-f]+)u" % letter, text)
        if not m:
            raise RuntimeError("%s has no O2P_GPIO_BONDED_%s" % (path, letter))
        masks[GPIO_PORTS[letter]] = int(m.group(1), 16)
    return masks


def load_signal_names(path=BOARD_PINS_H):
    """{NAME: (port, pin)} from board_pins.h's O2P_<NAME>_PORT/_PIN pairs."""
    text = open(path, encoding="utf-8").read()
    ports = dict(re.findall(r"#define\s+O2P_(\w+)_PORT\s+GPIO([A-F])\b", text))
    pins = dict(re.findall(r"#define\s+O2P_(\w+)_PIN\s+(\d+)u?\b", text))
    return {name: (GPIO_PORTS[ports[name]], int(pins[name]))
            for name in ports if name in pins}


def gpio_pin_name(port, pin):
    return "P%s%d" % (GPIO_LETTERS.get(port, "?%d" % port), pin)


def resolve_gpio(text, names):
    """(port, pin) from 'PB3' or a board_pins.h signal name.

    Deliberately does NOT check the package: PE3 or PB16 is sent as asked, so
    the refusal a probe gives is the firmware's, and is seen."""
    s = text.strip().upper()
    if s.startswith("O2P_"):
        s = s[4:]
    m = re.fullmatch(r"P([A-Z])(\d+)", s)
    if m:
        if m.group(1) not in GPIO_PORTS:
            raise ValueError("no GPIO port %s on an STM32G0: A, B, C, D, F"
                             % m.group(1))
        pin = int(m.group(2))
        if pin > 0xFF:
            raise ValueError("pin %d does not fit the opcode's pin byte" % pin)
        return GPIO_PORTS[m.group(1)], pin
    if s in names:
        return names[s]
    raise ValueError("unknown pin %r: give PB3-style, or one of %s"
                     % (text, ", ".join(sorted(names))))


def decode_gpio(port, pin, status, r0, r1, r2, aux):
    """What the firmware's reply entitles a reader to say. Never a level
    without status OK, LEVEL_VALID and a non-analog mode - all three."""
    d = {"port": port, "pin": pin, "status": status,
         "status_name": DIAG_STATUS_NAMES.get(status, "STATUS_%d" % status),
         "config": None, "level": None, "port_idr": None, "port_odr": None,
         "analog_mask": None, "reason": None, "warning": None}
    letter = GPIO_LETTERS.get(port, "?")
    if status in (DIAG_OK, GPIO_NOT_SAMPLED):
        if not r0 & R0_CONFIG_VALID:
            d["reason"] = ("status %s without CONFIG_VALID: an inconsistent reply, "
                           "nothing in it is trusted" % d["status_name"])
            return d
        mode = r0 & R0_MODE_MASK
        d["config"] = {"mode": mode,
                       "pull": (r0 & R0_PULL_MASK) >> R0_PULL_SHIFT,
                       "open_drain": bool(r0 & R0_OPEN_DRAIN),
                       "odr": 1 if r0 & R0_ODR else 0,
                       "af": (r0 & R0_AF_MASK) >> R0_AF_SHIFT}
        d["port_idr"], d["port_odr"], d["analog_mask"] = r1, r2, aux
        if status == GPIO_NOT_SAMPLED:
            d["reason"] = ("analog mode: the input buffer is off and IDR reads 0 "
                           "whatever the pin is at")
        elif not r0 & R0_LEVEL_VALID or mode == MODE_ANALOG:
            d["reason"] = "status OK without a valid level: an inconsistent reply"
        else:
            d["level"] = 1 if r0 & R0_LEVEL else 0
            cfg = d["config"]
            if mode == MODE_OUTPUT and d["level"] != cfg["odr"]:
                d["warning"] = DRIVEN_NOT_REACHED
                if cfg["open_drain"] and cfg["odr"] == 1:
                    d["warning"] += (" (open-drain, released: held low from "
                                     "outside, or no pull-up)")
    elif status == GPIO_UNCLOCKED:
        d["reason"] = ("port %s clock is off (RCC_IOPENR): the firmware never "
                       "enabled it, and nothing on the port was read" % letter)
    elif status == GPIO_NO_PIN:
        d["reason"] = ("no such pin on the STM32G071CBT7 LQFP48 - no port there, "
                       "pin above 15, or a pad not bonded out; nothing was read")
    elif status == DIAG_PENDING:
        d["reason"] = "PENDING, which this opcode never is: an older or foreign image?"
    else:
        d["reason"] = "the firmware answered %s" % d["status_name"]
    return d


def gpio_query(bus, port, pin):
    """One OP_READ_GPIO. Served inside the write, so one read-back suffices;
    the command and parameter are read with it to prove the result is ours."""
    cmd, param = 0x5A00 | OP_READ_GPIO, ((port << 8) | pin) & 0xFFFF
    bus.write(REGISTERS["DIAG_CMD"], [cmd, param])
    regs = bus.read(REGISTERS["DIAG_CMD"], 7)
    if regs[0] != cmd or regs[1] != param:
        raise GpioTorn("the mailbox holds command 0x%04X param 0x%04X, not "
                       "0x%04X 0x%04X: another master used it in between"
                       % (regs[0], regs[1], cmd, param))
    return decode_gpio(port, pin, regs[2], regs[3], regs[4], regs[5], regs[6])


def gpio_state(d):
    if d["level"] is not None:
        return "HIGH" if d["level"] else "LOW"
    if d["status"] == GPIO_NOT_SAMPLED and d["config"] is not None:
        return "NOT SAMPLED"
    if d["status"] in (GPIO_UNCLOCKED, GPIO_NO_PIN):
        return "REFUSED"
    return "NO LEVEL"


def gpio_label(d, by_pin):
    base = gpio_pin_name(d["port"], d["pin"])
    names = by_pin.get((d["port"], d["pin"]))
    return "%s (%s)" % (base, ", ".join(sorted(names))) if names else base


def format_gpio(d, by_pin):
    lines = ["  %s: %s" % (gpio_label(d, by_pin), gpio_state(d)),
             "    status : %s (%d)" % (d["status_name"], d["status"])]
    if d["reason"]:
        lines.append("    why    : %s" % d["reason"])
    c = d["config"]
    if c is not None:
        mode = GPIO_MODES[c["mode"]]
        lines.append("    mode   : %s" % mode)
        lines.append("    pull   : %s" % GPIO_PULLS[c["pull"]])
        lines.append("    type   : %s" % ("open-drain" if c["open_drain"] else "push-pull"))
        lines.append("    ODR    : %d%s" % (c["odr"], "" if c["mode"] == MODE_OUTPUT else
                                              " (latch only; not driving the pin in %s mode)" % mode))
        lines.append("    AF     : AF%d%s" % (c["af"], "" if c["mode"] == MODE_AF else
                                               " (not selected; mode is %s)" % mode))
        lines.append("    port %s : IDR 0x%04X  ODR 0x%04X  analog 0x%04X (analog pins' "
                     "IDR bits read 0 and are not samples)"
                     % (GPIO_LETTERS.get(d["port"], "?"), d["port_idr"], d["port_odr"],
                        d["analog_mask"]))
    if d["warning"]:
        lines.append("  !! %s" % d["warning"])
    return lines


def format_gpio_row(d, by_pin):
    base = gpio_pin_name(d["port"], d["pin"])
    names = ",".join(sorted(by_pin.get((d["port"], d["pin"]), []))) or "-"
    c = d["config"]
    if c is None:
        return "  %-5s %-12s %s: %s" % (base, names, gpio_state(d), d["reason"])
    return "  %-5s %-12s %-9s %-18s %-10s AF%-2d ODR %d  %s" % (
        base, names, GPIO_MODES[c["mode"]], GPIO_PULLS[c["pull"]],
        "open-drain" if c["open_drain"] else "push-pull", c["af"], c["odr"],
        gpio_state(d))


def cmd_diag_gpio(bus, args, out=print, names=None, bonded=None):
    """`diag gpio PIN` or `diag gpio --port X`. Returns the exit code:
    0 answered (a NOT SAMPLED pin is an answer), 1 refused, 2 inconsistent."""
    names = load_signal_names() if names is None else names
    bonded = load_bonded() if bonded is None else bonded
    by_pin = {}
    for name, key in names.items():
        by_pin.setdefault(key, []).append(name)
    port_arg = getattr(args, "gpio_port", None)
    try:
        if port_arg is not None:
            if args.param is not None:
                raise ValueError("give a pin or --port, not both")
            letter = port_arg.strip().upper()
            if letter not in GPIO_PORTS:
                raise ValueError("no GPIO port %s on an STM32G0: A, B, C, D, F" % port_arg)
            port = GPIO_PORTS[letter]
            pins = [n for n in range(16) if bonded.get(port, 0) >> n & 1]
            if not pins:
                out("  port %s: no bonded pins on the STM32G071CBT7 LQFP48 (it has "
                    "no port %s); nothing sent" % (letter, letter))
                return 1
            out("  Port %s: %d bonded pins (src/gpio_diag.h)" % (letter, len(pins)))
            rc = 0
            for n in pins:
                d = gpio_query(bus, port, n)
                if d["status"] == GPIO_UNCLOCKED:
                    out("  %s: %s" % (gpio_pin_name(port, n), d["reason"]))
                    return 1
                out(format_gpio_row(d, by_pin))
                if d["warning"]:
                    out("        !! %s" % d["warning"])
                if d["status"] not in (DIAG_OK, GPIO_NOT_SAMPLED):
                    rc = max(rc, 1)
                elif d["level"] is None and d["status"] == DIAG_OK:
                    rc = 2
            return rc
        if args.param is None:
            raise ValueError("diag gpio needs a pin (PB3, ADC_DRDY) or --port B")
        port, pin = resolve_gpio(args.param, names)
        d = gpio_query(bus, port, pin)
        for line in format_gpio(d, by_pin):
            out(line)
        if d["status"] == DIAG_OK:
            return 0 if d["level"] is not None else 2
        if d["status"] == GPIO_NOT_SAMPLED:
            return 0 if d["config"] is not None else 2
        return 1
    except ModbusException as e:
        if e.code == 2:
            out("  !! 0x0070 answers exception 02: this image has no diagnostic "
                "mailbox (a nodebug build)")
            return 1
        if e.code == MB_EX_BUSY:
            # FW_VERSION 0x000F+. Nothing was read and nothing was written: the
            # queued command's registers are still its own.
            out("  !! the probe answered exception 06 (busy): an I2C diagnostic "
                "command queued on it owns the mailbox until it has run. No pin "
                "was read; retry")
            return 1
        if e.code == 3:
            try:
                fw = "0x%04X" % bus.read(REGISTERS["FW_VERSION"], 1)[0]
            except (ModbusException, NoReply):
                fw = "unreadable"
            out("  !! the probe refused opcode 0x%02X with exception 03 (FW_VERSION %s; "
                "READ_GPIO needs 0x%04X or later - and up to 0x000E, 03 was also "
                "the answer while another diag command was still pending)"
                % (OP_READ_GPIO, fw, FW_READ_GPIO))
            return 1
        raise


def cmd_crash(bus, args):
    regs = bus.read(REGISTERS["CRASH_REASON"], 9)
    reason = regs[0]
    pc = (regs[1] << 16) | regs[2]
    lr = (regs[3] << 16) | regs[4]
    detail = (regs[5] << 16) | regs[6]
    b_id = (regs[7] << 16) | regs[8]

    reason_str = CRASH_REASONS.get(reason, "UNKNOWN_%d" % reason)
    b_sha = "%07x" % (b_id & 0x0FFFFFFF)
    dirty = bool(b_id & 0x80000000)

    print("  Crash Record:")
    print("    Reason   : %s (%d)" % (reason_str, reason))
    print("    PC       : 0x%08X" % pc)
    print("    LR       : 0x%08X" % lr)
    print("    Detail   : 0x%08X (%d)" % (detail, detail))
    print("    Build ID : %s%s" % (b_sha, "*" if dirty else ""))

    if reason != 0 and pc != 0 and os.path.exists(args.elf):
        elf_b_id = get_elf_build_id(args.elf)
        if elf_b_id is None:
            msg = ("could not read g_o2p_build_id from %s, so the ELF is "
                   "unverified against the crash record" % args.elf)
        elif (elf_b_id & 0x0FFFFFFF) != (b_id & 0x0FFFFFFF):
            msg = "Crash record BUILD_ID (%s) does not match ELF (%07x)" % (b_sha, elf_b_id & 0x0FFFFFFF)
        else:
            msg = None
        if msg is not None:
            if args.force_build_id:
                print("!! WARNING: %s (decoding anyway due to --force-build-id)" % msg)
            else:
                print("!! ERROR: %s. Use --force-build-id to decode anyway." % msg)
                return
        try:
            out = subprocess.check_output(
                ["arm-none-eabi-addr2line", "-e", args.elf, "-f", "-C", "0x%08x" % pc],
                text=True).strip()
            print("    PC decode: %s" % out.replace("\n", " at "))
        except Exception:
            pass

    if args.clear:
        bus.write(REGISTERS["CRASH_BUILD_ID_LO"], [0])
        print("  Crash record cleared.")


# ---------------------------------------------------------------- Exec (0x0150)

def parse_code_payload(code_arg):
    """Parse code argument from file path or hex string into (byte_len, words)."""
    if os.path.isfile(code_arg):
        with open(code_arg, "rb") as f:
            raw = f.read()
        if len(raw) % 2 != 0:
            raise ValueError("Binary payload length must be even (16-bit halfwords), got %d bytes" % len(raw))
        if len(raw) < 2 or len(raw) > 128:
            raise ValueError("Payload must be 2..128 bytes, got %d bytes" % len(raw))
        words = [w[0] for w in struct.iter_unpack("<H", raw)]
        return len(raw), words

    cleaned = code_arg.strip()
    tokens = [t for t in re.split(r'[\s,]+', cleaned) if t]
    words = []
    if len(tokens) == 1 and len(tokens[0]) > 4 and not tokens[0].lower().startswith("0x"):
        hex_str = tokens[0]
        if not re.fullmatch(r'[0-9a-fA-F]+', hex_str):
            raise ValueError("Continuous hex string contains non-hexadecimal characters: %r" % hex_str)
        if len(hex_str) % 4 != 0:
            raise ValueError("Hex string length must be a multiple of 4 characters (16-bit words), got %d chars" % len(hex_str))
        for i in range(0, len(hex_str), 4):
            chunk = hex_str[i:i+4]
            val = int(chunk, 16)
            if val < 0 or val > 0xFFFF:
                raise ValueError("Code word 0x%X out of range (must be 16-bit unsigned integer)" % val)
            words.append(val)
    else:
        for t in tokens:
            t_clean = t.lower()
            if t_clean.startswith("0x"):
                t_hex = t_clean[2:]
            else:
                t_hex = t_clean
            if not re.fullmatch(r'[0-9a-fA-F]+', t_hex):
                raise ValueError("Invalid hex token %r (must be positive hex halfword)" % t)
            val = int(t, 16)
            if val < 0 or val > 0xFFFF:
                raise ValueError("Code word 0x%X out of range (must be 16-bit unsigned integer)" % val)
            words.append(val)

    byte_len = len(words) * 2
    if byte_len < 2 or byte_len > 128:
        raise ValueError("Payload must be 2..128 bytes (1..64 halfwords), got %d bytes" % byte_len)
    return byte_len, words


def cmd_exec(bus, args):
    if args.abort:
        print("  Aborting arbitrary code execution...")
        try:
            bus.write(REGISTERS["EXEC_CMD"], [EXEC_MAGIC | EXEC_OP_ABORT])
        except ModbusException as e:
            if e.code == 2:
                print("  !! Exception 02: debug blocks compiled out (O2P_DEBUG_ENABLE=0).")
                sys.exit(1)
            raise
        st = bus.read(REGISTERS["EXEC_STATUS"], 1)[0]
        print("  Status: %s (%d)" % (EXEC_STATUS_NAMES.get(st, "UNKNOWN_%d" % st), st))
        return

    if not args.code:
        print("  !! Error: code payload required unless --abort is specified.")
        sys.exit(1)

    try:
        byte_len, words = parse_code_payload(args.code)
    except Exception as e:
        print("  !! Error parsing code payload: %s" % e)
        sys.exit(1)

    try:
        param = int(args.param, 0) if isinstance(args.param, str) else int(args.param)
    except (ValueError, TypeError) as e:
        print("  !! Invalid integer for --param: %s" % e)
        sys.exit(1)
    if param < -2147483648 or param > 0xFFFFFFFF:
        print("  !! --param %d out of range (must fit in 32-bit signed or unsigned integer: -2147483648..4294967295)" % param)
        sys.exit(1)
    param_u32 = param & 0xFFFFFFFF
    param_hi = (param_u32 >> 16) & 0xFFFF
    param_lo = param_u32 & 0xFFFF
    timeout_ms = args.timeout_ms
    if timeout_ms < 1 or timeout_ms > 1000:
        print("  !! Timeout must be 1..1000 ms, got %d" % timeout_ms)
        sys.exit(1)

    # 1. Upload code payload to EXEC_CODE_START (0x0158)
    try:
        bus.write(REGISTERS["EXEC_CODE_START"], words)
    except ModbusException as e:
        if e.code == 2:
            print("  !! 0x0150 answers exception 02: debug blocks compiled out (O2P_DEBUG_ENABLE=0). "
                  "This image does not support arbitrary code execution.")
            sys.exit(1)
        if e.code == MB_EX_BUSY:
            print("  !! The probe answered exception 06 (busy): execution is currently pending.")
            sys.exit(1)
        raise

    # 2. Trigger execution: write [CMD, LEN, PARAM_HI, PARAM_LO, TIMEOUT_MS] to 0x0150
    cmd_payload = [
        EXEC_MAGIC | EXEC_OP_RUN,
        byte_len,
        param_hi,
        param_lo,
        timeout_ms,
    ]
    try:
        bus.write(REGISTERS["EXEC_CMD"], cmd_payload)
    except ModbusException as e:
        if e.code == MB_EX_BUSY:
            print("  !! The probe answered exception 06 (busy): execution is currently pending.")
            sys.exit(1)
        raise

    # 3. Poll EXEC_STATUS until not PENDING (monotonic deadline)
    t0 = time.monotonic()
    max_wait = (timeout_ms / 1000.0) + 2.0
    deadline = t0 + max_wait
    st = EXEC_STATUS_PENDING
    regs = [EXEC_STATUS_PENDING, 0, 0]
    read_error = None

    while time.monotonic() < deadline:
        try:
            regs = bus.read(REGISTERS["EXEC_STATUS"], 3)
            read_error = None
            st = regs[0]
            if st != EXEC_STATUS_PENDING:
                break
        except (ModbusException, NoReply) as e:
            read_error = e
        time.sleep(0.02)

    elapsed_ms = (time.monotonic() - t0) * 1000.0

    if read_error is not None and st == EXEC_STATUS_PENDING:
        print("  !! Polling failed to read status before deadline: %s" % read_error)
        print("     Execution was triggered, but final outcome is unknown.")
        sys.exit(4)

    st_name = EXEC_STATUS_NAMES.get(st, "STATUS_%d" % st)

    print("  Exec result: %s (status code %d, elapsed ~%.1f ms)" % (st_name, st, elapsed_ms))
    if st == EXEC_STATUS_OK:
        res_hi = regs[1]
        res_lo = regs[2]
        res_u32 = (res_hi << 16) | res_lo
        res_s32 = struct.unpack(">i", struct.pack(">I", res_u32))[0]
        if res_s32 < 0:
            print("    Return value: 0x%08X (%d unsigned, %d signed)" % (res_u32, res_u32, res_s32))
        else:
            print("    Return value: 0x%08X (%d)" % (res_u32, res_u32))
    elif st == EXEC_STATUS_FAULT:
        print("    !! Execution triggered a HardFault; caught by interceptor trampoline.")
        sys.exit(2)
    elif st == EXEC_STATUS_TIMEOUT:
        print("    !! Execution timed out after %d ms; aborted by SysTick trampoline." % timeout_ms)
        sys.exit(3)
    elif st == EXEC_STATUS_PENDING:
        print("    !! Execution timed out waiting for status update (still PENDING after %.1f ms)." % elapsed_ms)
        sys.exit(4)
    else:
        print("    !! Execution failed with status %s (%d)" % (st_name, st))
        sys.exit(5)


# ---------------------------------------------------------------- Main

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/tty.usbserial-X)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    parser.add_argument("--parity", default="E", choices=["N", "E", "O"], help="Parity (default E)")
    parser.add_argument("--addr", type=int, default=3, help="Modbus slave address (default 3)")
    parser.add_argument("--elf", default=DEFAULT_ELF, help="Path to firmware.elf for symbol resolution")
    parser.add_argument("--force-build-id", action="store_true", help="Ignore build ID mismatch")
    parser.add_argument("--force-bus-master", action="store_true", help="Force bus master operation on multi-drop cables")
    # Was a hardcoded 1.0. The committed SerialLink.exchange() keeps reading for
    # max(2, 3 x timeout) s after a read that held no frame, so 1.0 already
    # waits ~4 s for a late reply (the independent review's reasoning, checked
    # against HEAD's o2p_update.py 2026-09-10). The flag exists anyway because
    # the node README's relayed example passes --timeout 3 to o2p_update.py,
    # and the same wrapped command line should work for both tools.
    parser.add_argument("--timeout", type=float, default=1.0,
                        help="per-read serial timeout in seconds (default 1.0; "
                             "3 through the node's USB console relay)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_read = subparsers.add_parser("read", help="Read register(s)")
    p_read.add_argument("targets", nargs="+", help="Register name(s) or address(es)")

    p_write = subparsers.add_parser("write", help="Write register")
    p_write.add_argument("target", help="Register name or address")
    p_write.add_argument("value", help="Value to write (dec or hex)")

    p_htest = subparsers.add_parser("htest", help="Atomic heater test control")
    p_htest.add_argument("--arm", action="store_true", help="Arm heater test override")
    p_htest.add_argument("--duty", type=float, default=0.0, help="Duty percentage (0-100)")
    p_htest.add_argument("--sp", type=float, help="Tip setpoint in C")
    p_htest.add_argument("--kp", type=float, default=1.0, help="Proportional gain")
    p_htest.add_argument("--ki", type=float, default=0.2, help="Integral gain")

    p_cfg = subparsers.add_parser("config", help="Write configuration register")
    p_cfg.add_argument("target", help="Config register name")
    p_cfg.add_argument("value", help="Value")
    p_cfg.add_argument("--commit", action="store_true", help="Persist to flash and verify CMD_RESULT")

    p_peek = subparsers.add_parser("peek", help="Memory peek")
    p_peek.add_argument("target", help="Symbol name or 32-bit address")
    size = p_peek.add_mutually_exclusive_group()
    size.add_argument("--count", type=int, default=None,
                      help="words to read (default: the ELF symbol's size, "
                           "or one word for a literal address)")
    size.add_argument("--bytes", type=int, default=None,
                      help="bytes to read; rounded out to whole words on the wire")
    p_peek.add_argument("--max-adu", type=parse_max_adu, default=None,
                        help="largest reply ADU the path carries: auto (default, "
                             "255 on every link this tool opens), %s, or a "
                             "byte count" % ", ".join(
                                 "%s=%d" % kv for kv in sorted(MAX_ADU_PRESETS.items())))
    p_peek.add_argument("--narrow", action="store_true",
                        help="use the 4-word mailbox at 0x0065 even when the "
                             "wide block is available")

    p_diag = subparsers.add_parser("diag", help="Sensor diagnostic mailbox")
    p_diag.add_argument("diag_cmd", help="Command (lmp-read, lmp-trim, ads-status, ads-config, tmp-read, sht-serial, sht-sample, gpio)")
    p_diag.add_argument("param", nargs="?", default=None,
                        help="Parameter (reg address or value); for gpio a pin: "
                             "PB3-style, or a src/board_pins.h name such as ADC_DRDY")
    p_diag.add_argument("--dev", type=int, default=0,
                        help="tmp-read only: device selector (0=tip at 0x49, 1=ext at 0x4A/0x4B)")
    # dest is NOT "port": that is the serial port given before the subcommand.
    p_diag.add_argument("--port", dest="gpio_port", default=None, metavar="LETTER",
                        help="gpio only: walk every bonded pin of this GPIO port (A, B, C, D, F)")

    p_crash = subparsers.add_parser("crash", help="Read retained crash context")
    p_crash.add_argument("--clear", action="store_true", help="Clear crash record")

    p_exec = subparsers.add_parser("exec", help="Arbitrary code execution mailbox (debug builds only)")
    p_exec.add_argument("code", nargs="?", default=None,
                        help="Code payload: hex halfwords (e.g. '202a 4770'), continuous hex, or path to .bin file")
    p_exec.add_argument("--param", default=0,
                        help="32-bit input argument passed in R0 (dec or hex, default 0)")
    p_exec.add_argument("--timeout-ms", type=int, default=50,
                        help="Execution timeout in milliseconds (1..1000, default 50)")
    p_exec.add_argument("--abort", action="store_true", help="Abort any pending execution")

    args = parser.parse_args()

    link = SerialLink(args.port, args.baud, args.parity, timeout=args.timeout)
    bus = Bus(link, args.addr)

    try:
        if args.command == "read":
            cmd_read(bus, args)
        elif args.command == "write":
            cmd_write(bus, args)
        elif args.command == "htest":
            cmd_htest(bus, args)
        elif args.command == "config":
            cmd_config(bus, args)
        elif args.command == "peek":
            cmd_peek(bus, args)
        elif args.command == "diag":
            cmd_diag(bus, args)
        elif args.command == "exec":
            cmd_exec(bus, args)
        elif args.command == "crash":
            cmd_crash(bus, args)
    finally:
        link.close()


if __name__ == "__main__":
    main()
