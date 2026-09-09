#!/usr/bin/env python3
"""o2-probe interactive Modbus debugger CLI.

Communicates with the o2-probe over RS-485 Modbus RTU, providing:
  * Symbolic register read/write with engineering unit conversions.
  * Atomic multi-word heater-test override writes.
  * Memory peek with ELF symbol resolution and BUILD_ID safety checks.
  * Typed sensor diagnostic mailbox access (LMP91000, ADS1119, TMP117, SHT45).
  * Crash context decoding via arm-none-eabi-addr2line.

Usage:
    python3 tools/o2p_cli.py --port /dev/tty.usbserial-X read O2_COMP T_TIP HEATER_BLOCK
    python3 tools/o2p_cli.py --port ... write RH_SETPOINT 8000
    python3 tools/o2p_cli.py --port ... htest --arm --duty 20.0 --sp 45.0
    python3 tools/o2p_cli.py --port ... peek g_rm
    python3 tools/o2p_cli.py --port ... diag lmp-read 0x10
    python3 tools/o2p_cli.py --port ... crash [--clear]
"""

import argparse
import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2p_update import Bus, ModbusException, NoReply, SerialLink, crc16  # noqa: E402

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
    "EXP_DATA": 0x001F, "SETTLE_RESTARTS": 0x0020, "SAMPLE_SEQ": 0x0021,
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

    # Sensor diagnostic mailbox (0x0070)
    "DIAG_CMD": 0x0070, "DIAG_PARAM": 0x0071, "DIAG_STATUS": 0x0072,
    "DIAG_RDATA0": 0x0073, "DIAG_RDATA1": 0x0074, "DIAG_RDATA2": 0x0075,
    "DIAG_CRC_STATUS": 0x0076,

    # Crash context (0x0077)
    "CRASH_REASON": 0x0077, "CRASH_PC_HI": 0x0078, "CRASH_PC_LO": 0x0079,
    "CRASH_LR_HI": 0x007A, "CRASH_LR_LO": 0x007B, "CRASH_DETAIL_HI": 0x007C,
    "CRASH_DETAIL_LO": 0x007D, "CRASH_BUILD_ID_HI": 0x007E, "CRASH_BUILD_ID_LO": 0x007F,
}

PEEK_STATUS_NAMES = {0: "NONE", 1: "OK", 2: "ERR_RANGE", 3: "ERR_ALIGN"}
DIAG_STATUS_NAMES = {
    0: "NONE", 1: "PENDING", 2: "OK", 3: "ERR_OPCODE",
    4: "ERR_NACK", 5: "ERR_TIMEOUT", 6: "ERR_BUSY"
}
CRASH_REASONS = {0: "NONE", 1: "HARDFAULT", 2: "ASSERT", 3: "IWDG"}

HB_BITS = [
    "NOT_COMPILED", "CONFIG_OFF", "SAFETY", "NO_RH",
    "NO_TIP", "NO_CHAMBER", "TIP_LIMIT", "DT_LIMIT",
    "RUNAWAY", "SUPPLY", "PIN_INTEGRITY", "STALE", "NO_CONSENT"
]


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
    if name in ("SAMPLER_TIMING_MS",):
        return "%d ms" % val
    if name in ("BUILD_ID_HI", "BUILD_ID_LO"):
        return "0x%04X" % val
    return "0x%04X (%d)" % (val, val)


def get_elf_symbols(elf_path):
    """Parse symbol table from ELF using nm or arm-none-eabi-nm."""
    nm_bins = ["arm-none-eabi-nm", "nm"]
    for nm in nm_bins:
        try:
            p = subprocess.run([nm, "-C", "-S", elf_path],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True)
            symbols = {}
            for line in p.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    # addr [size] type name
                    addr = int(parts[0], 16)
                    name = parts[-1]
                    symbols[name] = addr
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
    if elf_b_id is not None:
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
    arm_magic = 0x8EA7 if args.arm else 0x0000
    block = [arm_magic, duty, sp, kp, ki]
    bus.write(REGISTERS["HEATER_TEST_ARM"], block)
    print("  Heater test block written atomically:")
    print("    ARM=%s, DUTY=%.2f %%, SP=%s, KP=%.2f, KI=%.2f"
          % ("ARMED" if args.arm else "DISARMED", duty / 100.0,
             "none" if sp == -32768 else "%.2f C" % (sp / 100.0),
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


def cmd_peek(bus, args):
    check_build_id(bus, args.elf, force=args.force_build_id)
    target_str = args.target.strip()
    if target_str.upper().startswith("0X") or target_str.isdigit():
        addr = int(target_str, 16) if target_str.upper().startswith("0X") else int(target_str)
        name = "0x%08X" % addr
    else:
        symbols = get_elf_symbols(args.elf)
        if target_str not in symbols:
            raise KeyError("Symbol '%s' not found in %s" % (target_str, args.elf))
        addr = symbols[target_str]
        name = "%s (0x%08X)" % (target_str, addr)

    # Atomic 2-register FC16 write to 0x0065..0x0066
    hi = (addr >> 16) & 0xFFFF
    lo = addr & 0xFFFF
    bus.write(REGISTERS["PEEK_ADDR_HI"], [hi, lo])

    # Read back 11 registers: ADDR_HI, ADDR_LO, STATUS, W0_HI/LO, W1_HI/LO, W2_HI/LO, W3_HI/LO
    regs = bus.read(REGISTERS["PEEK_ADDR_HI"], 11)
    status = regs[2]
    status_str = PEEK_STATUS_NAMES.get(status, "ERR_%d" % status)

    print("  Peek %s:" % name)
    print("    Status: %s" % status_str)
    if status == 1:
        count = min(max(args.count, 1), 4)
        for w in range(count):
            w_hi = regs[3 + w * 2]
            w_lo = regs[4 + w * 2]
            w_val = (w_hi << 16) | w_lo
            print("    [+0x%02X] 0x%08X  (%d)" % (w * 4, w_val, w_val))
    else:
        sys.exit(1)


def cmd_diag(bus, args):
    sub = args.diag_cmd.lower()
    op = 0
    param = 0

    if sub == "lmp-read":
        op = 0x01
        param = int(args.param, 0)
    elif sub == "lmp-trim":
        op = 0x02
        param = int(args.param, 0)
    elif sub == "ads-status":
        op = 0x03
    elif sub == "ads-config":
        op = 0x04
    elif sub == "tmp-read":
        op = 0x05
        param = int(args.param, 0)
    elif sub == "sht-serial":
        op = 0x06
    elif sub == "sht-sample":
        op = 0x07
    else:
        raise ValueError("Unknown diag command: %s" % sub)

    cmd_word = 0x5A00 | op
    bus.write(REGISTERS["DIAG_CMD"], [cmd_word, param])

    # Poll status until done (max 1000ms)
    t0 = time.time()
    while time.time() - t0 < 1.0:
        regs = bus.read(REGISTERS["DIAG_STATUS"], 5)
        st = regs[0]
        if st != 1:  # Not pending
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
        if elf_b_id is not None and (elf_b_id & 0x0FFFFFFF) != (b_id & 0x0FFFFFFF):
            msg = "Crash record BUILD_ID (%s) does not match ELF (%07x)" % (b_sha, elf_b_id & 0x0FFFFFFF)
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
    p_peek.add_argument("--count", type=int, default=1, choices=[1, 2, 3, 4], help="Word count (1-4)")

    p_diag = subparsers.add_parser("diag", help="Sensor diagnostic mailbox")
    p_diag.add_argument("diag_cmd", help="Command (lmp-read, lmp-trim, ads-status, ads-config, tmp-read, sht-serial, sht-sample)")
    p_diag.add_argument("param", nargs="?", default="0", help="Parameter (reg address or value)")

    p_crash = subparsers.add_parser("crash", help="Read retained crash context")
    p_crash.add_argument("--clear", action="store_true", help="Clear crash record")

    args = parser.parse_args()

    link = SerialLink(args.port, args.baud, args.parity, timeout=1.0)
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
        elif args.command == "crash":
            cmd_crash(bus, args)
    finally:
        link.close()


if __name__ == "__main__":
    main()
