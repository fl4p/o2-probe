#!/usr/bin/env python3
"""tools/o2p_cli.py exec tests against the firmware's real register map.

Tests payload parsing, code upload to 0x0158, trigger write to 0x0150,
parameter passing (including high words and signed input), return value decoding,
timeout/fault reporting, pending/busy handling, and abort.
"""
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
SRC = os.path.join(FW, "src")
sys.path.insert(0, HERE)

import o2p_cli as cli  # noqa: E402
from o2p_update import Bus, ModbusException, crc16  # noqa: E402

ORACLE_SOURCES = ["regmap.c", "modbus_pdu.c", "o2.c", "psychro.c", "faults.c",
                  "heater_ctl.c", "update.c", "crc32.c", "boot_desc.c",
                  "gpio_diag.c", "gpio_hal_host.c"]

FAILS, COUNT = [], [0]


def check(cond, what):
    COUNT[0] += 1
    print("  %s %s" % ("ok  " if cond else "FAIL", what))
    if not cond:
        FAILS.append(what)


def build_oracle(tmp, debug):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if cc is None:
        return None
    exe = os.path.join(tmp, "exec_oracle_debug%d" % debug)
    cmd = ([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-DO2P_HOST_TEST=1", "-DO2P_BOARD_REV_A=1", "-DO2P_HEATER_ENABLE=0",
            "-DO2P_DEBUG_ENABLE=%d" % debug, "-I", SRC, "-o", exe,
            os.path.join(HERE, "exec_oracle.c")] +
           [os.path.join(SRC, s) for s in ORACLE_SOURCES] + ["-lm"])
    subprocess.run(cmd, check=True)
    return exe


class OracleLink:
    def __init__(self, exe):
        self.p = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
        self.log = []

    def raw(self, adu):
        self.p.stdin.write(adu.hex() + "\n")
        self.p.stdin.flush()
        return bytes.fromhex(self.p.stdout.readline().strip())

    def exchange(self, adu, expect_len):
        rsp = self.raw(adu)
        self.log.append((adu, rsp))
        return rsp

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def main():
    print("Testing parse_code_payload:")
    # 1. Parsing tests
    l, w = cli.parse_code_payload("202a 4770")
    check(l == 4 and w == [0x202A, 0x4770], "space-separated hex words")

    l, w = cli.parse_code_payload("0x202A, 0x4770")
    check(l == 4 and w == [0x202A, 0x4770], "comma-separated with 0x prefix")

    l, w = cli.parse_code_payload("202a4770")
    check(l == 4 and w == [0x202A, 0x4770], "continuous hex string")

    # Finding 4 checks: negative signs, non-hex characters in continuous/separated
    bad_neg = False
    try:
        cli.parse_code_payload("202a-001")
    except ValueError:
        bad_neg = True
    check(bad_neg, "negative token in continuous hex rejected (Finding 4)")

    bad_neg_sep = False
    try:
        cli.parse_code_payload("0x202a, -0x0001")
    except ValueError:
        bad_neg_sep = True
    check(bad_neg_sep, "negative token in separated hex rejected")

    bad_nonhex = False
    try:
        cli.parse_code_payload("202azzzz")
    except ValueError:
        bad_nonhex = True
    check(bad_nonhex, "non-hex token in continuous hex rejected")

    tmp = tempfile.mkdtemp(prefix="o2p_test_exec_")
    try:
        bin_path = os.path.join(tmp, "code.bin")
        with open(bin_path, "wb") as f:
            f.write(struct.pack("<HH", 0x202A, 0x4770))
        l, w = cli.parse_code_payload(bin_path)
        check(l == 4 and w == [0x202A, 0x4770], "binary file unpacking")

        bad_len = False
        try:
            cli.parse_code_payload("202a47")  # 3 bytes, odd
        except ValueError:
            bad_len = True
        check(bad_len, "odd hex string length rejected")

        bad_range = False
        try:
            cli.parse_code_payload("0x10000 0x2000")
        except ValueError:
            bad_range = True
        check(bad_range, "out of range word rejected")

        # 2. Oracle interaction tests
        print("\nTesting Modbus execution against debug=1 oracle:")
        exe = build_oracle(tmp, debug=1)
        if exe is None:
            print("  SKIP: no host compiler found")
            return 2

        link = OracleLink(exe)
        bus = Bus(link, 3)

        # Finding 5 checks: out of bounds param
        args_bad_param = types.SimpleNamespace(code="202a 4770", param=0x100000000, timeout_ms=50, abort=False)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        exited = False
        try:
            cli.cmd_exec(bus, args_bad_param)
        except SystemExit as e:
            exited = (e.code == 1)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "out of range" in out, "out of range --param 0x100000000 rejected (Finding 5)")

        args_bad_param_str = types.SimpleNamespace(code="202a 4770", param="not_a_num", timeout_ms=50, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        exited = False
        try:
            cli.cmd_exec(bus, args_bad_param_str)
        except SystemExit as e:
            exited = (e.code == 1)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "Invalid integer" in out, "non-numeric --param rejected cleanly (Finding 5)")

        # Simple run: 0x202A (movs r0, #42), 0x4770 (bx lr)
        args = types.SimpleNamespace(code="202a 4770", param=0, timeout_ms=50, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            cli.cmd_exec(bus, args)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check("Return value: 0x0000002A (42)" in out, "exec movs r0, #42; bx lr returns 42")

        # Incomplete upload (Finding 7 check): missing bx lr
        args_inc = types.SimpleNamespace(code="202a 0000", param=0, timeout_ms=50, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        exited = False
        try:
            cli.cmd_exec(bus, args_inc)
        except SystemExit as e:
            exited = (e.code == 2)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "HardFault" in out, "incomplete upload (missing bx lr) triggers fault (Finding 7)")

        # Param passing with high word & calculation: 0x3005 (adds r0, #5) with param=0x12340005
        args = types.SimpleNamespace(code="3005 4770", param=0x12340005, timeout_ms=100, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            cli.cmd_exec(bus, args)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check("Return value: 0x1234000A (305397770)" in out, "exec adds r0, #5 with 32-bit high word param returns 0x1234000A")

        # Fault test: 0xDE00 (trap)
        args_fault = types.SimpleNamespace(code="DE00 4770", param=0, timeout_ms=50, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        exited = False
        try:
            cli.cmd_exec(bus, args_fault)
        except SystemExit as e:
            exited = (e.code == 2)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "HardFault" in out, "fault payload returns FAULT_INTERCEPTED and exit code 2")

        # Timeout test: 0xE7FE (b .)
        args_to = types.SimpleNamespace(code="E7FE 4770", param=0, timeout_ms=50, abort=False)
        captured = io.StringIO()
        sys.stdout = captured
        exited = False
        try:
            cli.cmd_exec(bus, args_to)
        except SystemExit as e:
            exited = (e.code == 3)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "timed out" in out, "infinite loop payload returns TIMEOUT_EXPIRED and exit code 3")

        # Abort test: direct write of 0x5A00 resets status to NONE
        args = types.SimpleNamespace(code=None, param=0, timeout_ms=50, abort=True)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            cli.cmd_exec(bus, args)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check("Aborting arbitrary code execution..." in out and "Status: NONE (0)" in out, "abort command resets status to NONE")

        # Busy refusal test (Finding 7): Trigger execution then immediately send another write
        bus.write(cli.REGISTERS["EXEC_CODE_START"], [0x202A, 0x4770])
        bus.write(cli.REGISTERS["EXEC_CMD"], [cli.EXEC_MAGIC | cli.EXEC_OP_RUN, 4, 0, 0, 50])
        # Second write while pending
        busy_caught = False
        try:
            bus.write(cli.REGISTERS["EXEC_CMD"], [cli.EXEC_MAGIC | cli.EXEC_OP_RUN, 4, 0, 0, 50])
        except ModbusException as e:
            busy_caught = (e.code == cli.MB_EX_BUSY)
        check(busy_caught, "second write while pending returns exception 06 DEVICE_BUSY")

        link.close()

        # 3. Test debug=0 (nodebug) refusal
        print("\nTesting Modbus execution against debug=0 oracle:")
        exe_nodebug = build_oracle(tmp, debug=0)
        link_nodebug = OracleLink(exe_nodebug)
        bus_nodebug = Bus(link_nodebug, 3)

        args = types.SimpleNamespace(code="202a 4770", param=0, timeout_ms=50, abort=False)
        exited = False
        captured = io.StringIO()
        sys.stdout = captured
        try:
            cli.cmd_exec(bus_nodebug, args)
        except SystemExit as e:
            exited = (e.code == 1)
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        check(exited and "debug blocks compiled out" in out, "nodebug build refuses exec with clear message")

        link_nodebug.close()

    finally:
        shutil.rmtree(tmp)

    if FAILS:
        print("\nFAILED %d checks: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("\nAll %d checks passed." % COUNT[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
