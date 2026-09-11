#!/usr/bin/env python3
"""tools/o2p_cli.py diag gpio, against the firmware's own OP_READ_GPIO.

Host-side only: nothing here opens a serial port or touches a probe. The probe
end is tools/gpio_oracle.c - src/regmap.c, src/modbus_pdu.c and src/gpio_diag.c
compiled for the host, with src/gpio_hal_host.c's counting register fake behind
them - so the CLI is checked against the decisions the firmware makes. A Python
fake written from the same reading of gpio_diag.h as the CLI would share any
misreading of it, and pass. The harness (OracleLink, the source list) is
test_o2p_cli_peek.py's, reused rather than copied.

The CLI is driven through main(), i.e. through the real argument parser, with
SerialLink swapped for the oracle.

Exit 0: every check passed. 1: a check failed. 2: something could not be
evaluated (no host C compiler) - which is not a pass.
"""
import contextlib
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
SRC = os.path.join(FW, "src")
sys.path.insert(0, HERE)

import o2p_cli as cli  # noqa: E402
import test_o2p_cli_peek as peek  # noqa: E402
from o2p_update import Bus, ModbusException  # noqa: E402

FAILS, SKIPS, COUNT = [], [], [0]
PORT = cli.GPIO_PORTS
SWD_PORT_A = (0xEBFFFFFF, 0x24000000)   # the fake's reset MODER/PUPDR for port A


def check(cond, what):
    COUNT[0] += 1
    print("  %s %s" % ("ok  " if cond else "FAIL", what))
    if not cond:
        FAILS.append(what)


def skip(what):
    print("  SKIP %s" % what)
    SKIPS.append(what)


def build_oracle(tmp, debug):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if cc is None:
        return None
    exe = os.path.join(tmp, "gpio_oracle_debug%d" % debug)
    cmd = ([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-DO2P_HOST_TEST=1", "-DO2P_BOARD_REV_A=1", "-DO2P_HEATER_ENABLE=0",
            "-DO2P_DEBUG_ENABLE=%d" % debug, "-I", SRC, "-o", exe,
            os.path.join(HERE, "gpio_oracle.c")] +
           [os.path.join(SRC, s) for s in peek.ORACLE_SOURCES] + ["-lm"])
    subprocess.run(cmd, check=True)
    return exe


def ctl(link, text):
    link.p.stdin.write(text + "\n")
    link.p.stdin.flush()
    return link.p.stdout.readline().strip()


def set_port(link, port, moder, otyper=0, pupdr=0, idr=0, odr=0, afrl=0, afrh=0):
    assert ctl(link, "#gpio %x %x %x %x %x %x %x %x" % (
        port, moder, otyper, pupdr, idr, odr, afrl, afrh)) == "ok"


def counts(link):
    return tuple(int(x) for x in ctl(link, "#counts").split())


def field(value, width, index, v):
    mask = ((1 << width) - 1) << (width * index)
    return (value & ~mask) | ((v << (width * index)) & mask)


class Harness:
    """Runs `o2p_cli.py --port X ARGS` through main(), with the oracle as the
    serial link. `setup` runs against the fresh oracle before the CLI does."""

    def __init__(self, exe):
        self.exe = exe
        self.link = None

    def run(self, argv, setup=None, before=None):
        def factory(port, baud, parity, timeout=1.0):
            link = peek.OracleLink(self.exe)
            if setup is not None:
                setup(link)
            link.before = before
            self.link = link
            return link

        saved_link, saved_close = cli.SerialLink, peek.OracleLink.close
        cli.SerialLink = factory
        # main() closes the link in `finally`; keep the process alive long
        # enough to read its counters afterwards, and close it here instead.
        peek.OracleLink.close = lambda self_: None
        out, code = io.StringIO(), 0
        saved_argv = sys.argv
        sys.argv = ["o2p_cli.py", "--port", "/dev/oracle"] + argv
        try:
            with contextlib.redirect_stdout(out):
                try:
                    cli.main()
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            sys.argv = saved_argv
            cli.SerialLink = saved_link
            peek.OracleLink.close = saved_close
        return code, out.getvalue()

    def finish(self):
        if self.link is not None:
            c = counts(self.link)
            self.link.close()
            self.link = None
            return c
        return None


def lines_for(text, pin_name):
    return [ln for ln in text.splitlines() if re.search(r"\b%s\b" % pin_name, ln)]


LEVEL_WORD = re.compile(r"\b(HIGH|LOW)\b")


def gpio_writes(link):
    """Params of every OP_READ_GPIO the CLI put on the wire, in order."""
    out = []
    for req, _rsp in link.log:
        if req[1] == 16 and struct.unpack(">H", req[2:4])[0] == 0x0070:
            cmd, param = struct.unpack(">HH", req[7:11])
            if cmd == 0x5A08:
                out.append(param)
    return out


# ------------------------------------------------------------------ pure parts

def test_sources_of_truth():
    print("names, masks and codes come from the firmware's headers")
    names = cli.load_signal_names()
    bonded = cli.load_bonded()
    check(names.get("ADC_DRDY") == (PORT["B"], 1) and names.get("RS485_DE") == (PORT["C"], 6),
          "board_pins.h names resolve to their ports and pins")
    check(all(bonded[p] >> n & 1 for p, n in names.values()),
          "every pin board_pins.h binds is bonded per gpio_diag.h")
    check(sum(bin(m).count("1") for m in bonded.values()) == 44 and bonded[PORT["E"]] == 0,
          "44 bonded I/O and no port E")

    regmap = open(os.path.join(SRC, "regmap.h"), encoding="utf-8").read()
    codes = {int(v): k for k, v in re.findall(r"O2P_DMBOX_STATUS_(\w+)\s*=\s*(\d+)u", regmap)}
    check(codes == cli.DIAG_STATUS_NAMES, "the CLI's DIAG_STATUS names are regmap.h's enum")
    m = re.search(r"O2P_OP_READ_GPIO\s*=\s*(0x[0-9A-Fa-f]+)u", regmap)
    check(m is not None and int(m.group(1), 16) == cli.OP_READ_GPIO, "opcode 0x08 is regmap.h's")
    m = re.search(r"#define O2P_FW_VERSION (0x[0-9A-Fa-f]+)u", regmap)
    check(m is not None and int(m.group(1), 16) == cli.FW_LATEST,
          "the CLI knows the probe's current wire contract (FW_VERSION %s)"
          % (m.group(1) if m else "?"))
    check(re.search(r"0x%04X adds OP_READ_GPIO" % cli.FW_READ_GPIO, regmap) is not None,
          "FW_READ_GPIO is the version regmap.h's changelog says introduced the opcode")
    check(re.search(r"0x%04X changes two refusals" % cli.FW_BUSY_IS_EXCEPTION, regmap)
          is not None and "O2P_MB_EX_DEVICE_BUSY      = 0x06u" in
          open(os.path.join(SRC, "modbus_pdu.h"), encoding="utf-8").read() and
          cli.MB_EX_BUSY == 6,
          "the busy refusal is exception 06 from the version the changelog names")
    diag_h = open(os.path.join(SRC, "gpio_diag.h"), encoding="utf-8").read()
    ok = True
    for macro, value in (("CONFIG_VALID", cli.R0_CONFIG_VALID), ("LEVEL_VALID", cli.R0_LEVEL_VALID),
                         ("LEVEL", cli.R0_LEVEL), ("ODR", cli.R0_ODR),
                         ("OPEN_DRAIN", cli.R0_OPEN_DRAIN), ("AF_MASK", cli.R0_AF_MASK),
                         ("PULL_MASK", cli.R0_PULL_MASK), ("MODE_MASK", cli.R0_MODE_MASK)):
        mm = re.search(r"#define\s+O2P_GPIO_R0_%s\s+(0x[0-9A-Fa-f]+)u" % macro, diag_h)
        ok = ok and mm is not None and int(mm.group(1), 16) == value
    check(ok, "RDATA0 bit positions are gpio_diag.h's")

    print("resolving a pin")
    check(cli.resolve_gpio("PB3", names) == (1, 3) and cli.resolve_gpio("pb3", names) == (1, 3),
          "PB3, any case")
    check(cli.resolve_gpio("ADC_DRDY", names) == (1, 1) and
          cli.resolve_gpio("o2p_adc_drdy", names) == (1, 1), "a board_pins.h name, with or without O2P_")
    check(cli.resolve_gpio("PE3", names) == (4, 3) and cli.resolve_gpio("PB16", names) == (1, 16),
          "PE3 and PB16 are SENT, so the firmware's refusal is what the user sees")
    for bad in ("PG1", "PB256", "NOPE", "B3"):
        try:
            cli.resolve_gpio(bad, names)
            check(False, "%s is refused before anything is sent" % bad)
        except ValueError:
            check(True, "%s is refused before anything is sent" % bad)

    print("a level only with OK, LEVEL_VALID and a digital mode")
    leaked = []
    for status in range(0, 12):
        for r0 in (0x0000, 0xFFFF, 0xC040, 0x8040, 0x4040, 0xC043, 0xC041, 0x8043, 0x0040):
            d = cli.decode_gpio(1, 1, status, r0, 0xFFFF, 0xFFFF, 0)
            has_level = d["level"] is not None
            may = status == 2 and r0 & 0xC000 == 0xC000 and r0 & 3 != 3
            printed = any(LEVEL_WORD.search(ln) for ln in cli.format_gpio(d, {}))
            printed = printed or bool(LEVEL_WORD.search(cli.format_gpio_row(d, {})))
            if has_level != may or printed != may:
                leaked.append((status, hex(r0)))
    check(not leaked, "no status/RDATA0 combination prints a level it was not given (%s)" % leaked[:4])


# ---------------------------------------------------------- against firmware

def pin_setup(port, pin, mode, idr=0, odr=0, pull=0, od=0, af=0, iopenr=None):
    def setup(link):
        moder, pupdr = (SWD_PORT_A if port == PORT["A"] else (0xFFFFFFFF, 0))
        moder = field(moder, 2, pin, mode)
        pupdr = field(pupdr, 2, pin, pull)
        afr = [0, 0]
        afr[pin >> 3] = field(0, 4, pin & 7, af)
        set_port(link, port, moder, field(0, 1, pin, od), pupdr, idr, odr, afr[0], afr[1])
        if iopenr is not None:
            assert ctl(link, "#iopenr %x" % iopenr) == "ok"
    return setup


def test_end_to_end(exe):
    h = Harness(exe)
    fw_ok = None

    print("an analog pin is NOT SAMPLED, whatever its IDR bit says")
    for idr in (0x0002, 0x0000):
        code, text = h.run(["diag", "gpio", "ADC_DRDY"], setup=pin_setup(PORT["B"], 1, 3, idr=idr))
        reads = h.finish()
        pb1 = lines_for(text, "PB1")
        check(code == 0 and pb1 and "NOT SAMPLED" in pb1[0],
              "PB1 (ADC_DRDY) with IDR bit %d prints NOT SAMPLED" % (idr >> 1))
        check(not LEVEL_WORD.search(text), "and no HIGH or LOW anywhere in the output")
        check("analog" in text and reads[0] == 6, "the mode is still reported, from one snapshot")

    print("an input pin prints its real level, both ways")
    for idr, word in ((0x0002, "HIGH"), (0xFFFD, "LOW")):
        code, text = h.run(["diag", "gpio", "PB1"], setup=pin_setup(PORT["B"], 1, 0, idr=idr))
        h.finish()
        check(code == 0 and "PB1 (ADC_DRDY): %s" % word in text, "PB1 input, IDR %s -> %s" % (hex(idr), word))
        check(DRIVEN := cli.DRIVEN_NOT_REACHED not in text, "no drive warning on an input")
        del DRIVEN

    print("an output pin whose latch and level disagree is flagged")
    code, text = h.run(["diag", "gpio", "RS485_DE"],
                       setup=pin_setup(PORT["C"], 6, 1, odr=0x0040, idr=0x0000))
    h.finish()
    check("PC6 (RS485_DE): LOW" in text and "ODR    : 1" in text,
          "ODR 1 and IDR 0 are both printed as they are")
    check(cli.DRIVEN_NOT_REACHED in text, "and flagged: '%s'" % cli.DRIVEN_NOT_REACHED)
    code, text = h.run(["diag", "gpio", "PC6"], setup=pin_setup(PORT["C"], 6, 1, odr=0x0040, idr=0x0040))
    h.finish()
    check("HIGH" in text and cli.DRIVEN_NOT_REACHED not in text, "not flagged when they agree")
    code, text = h.run(["diag", "gpio", "PB6"],
                       setup=pin_setup(PORT["B"], 6, 1, od=1, odr=0x0040, idr=0x0000))
    h.finish()
    check(cli.DRIVEN_NOT_REACHED in text and "open-drain" in text,
          "an open-drain output released but held low says so")
    code, text = h.run(["diag", "gpio", "HEATER_PWM"],
                       setup=pin_setup(PORT["A"], 8, 2, af=2, odr=0x0000, idr=0x0100))
    h.finish()
    check(cli.DRIVEN_NOT_REACHED not in text and "AF2" in text,
          "an AF pin is not judged by its unused latch")

    print("an unclocked port is refused, and nothing on it is read")
    code, text = h.run(["diag", "gpio", "PD0"], setup=pin_setup(PORT["D"], 0, 0, idr=1))
    reads = h.finish()
    check(code == 1 and "REFUSED" in text and "clock is off" in text, "PD0: port D clock off")
    check(reads == (0, 1, 0), "zero GPIO loads, one RCC load, none unmasked (%r)" % (reads,))
    check(not LEVEL_WORD.search(text), "no level printed")

    print("an absent pin is refused, and nothing at all is read")
    for pin in ("PC0", "PE0", "PB16", "PF3"):
        code, text = h.run(["diag", "gpio", pin])
        reads = h.finish()
        check(code == 1 and "no such pin" in text and reads == (0, 0, 0) and
              not LEVEL_WORD.search(text), "%s: refused by the firmware, no loads" % pin)

    print("walking a port")
    def port_b(link):
        moder = 0xFFFFFFFF
        moder = field(moder, 2, 0, 1)      # PB0 AFE_MENB output
        moder = field(moder, 2, 6, 2)      # PB6/PB7 I2C AF6, open-drain
        moder = field(moder, 2, 7, 2)
        set_port(link, PORT["B"], moder, 0x00C0, 0, 0x00C2, 0x0000, 0x66000000, 0)
    code, text = h.run(["diag", "gpio", "--port", "B"], setup=port_b)
    link = h.link
    params = gpio_writes(link)
    h.finish()
    rows = [ln for ln in text.splitlines() if re.match(r"\s+PB\d+\s", ln)]
    check(params == [0x0100 + n for n in range(16)] and len(rows) == 16,
          "port B: one query per bonded pin, PB0..PB15, one row each")
    pb1 = lines_for(text, "PB1")
    check(pb1 and "NOT SAMPLED" in pb1[0] and not LEVEL_WORD.search(pb1[0]),
          "PB1's row is NOT SAMPLED, with no level")
    check(all(not LEVEL_WORD.search(r) for r in rows if "analog" in r),
          "no analog row carries a level")
    pb0 = lines_for(text, "PB0")
    check(pb0 and "output" in pb0[0] and "LOW" in pb0[0], "PB0 output row reads LOW")
    pb7 = lines_for(text, "PB7")
    check(pb7 and "AF6" in pb7[0] and "HIGH" in pb7[0] and "open-drain" in pb7[0],
          "PB7 (I2C_SDA) row: AF6, open-drain, HIGH")

    code, text = h.run(["diag", "gpio", "--port", "c"])
    params = gpio_writes(h.link)
    h.finish()
    check(params == [0x0206, 0x0207, 0x020D, 0x020E, 0x020F],
          "port C walks exactly PC6, PC7, PC13, PC14, PC15")

    code, text = h.run(["diag", "gpio", "--port", "D"])
    params = gpio_writes(h.link)
    reads = h.finish()
    check(code == 1 and params == [0x0300] and "clock is off" in text and reads[0] == 0,
          "port D stops at its first pin: clock off, nothing loaded")

    code, text = h.run(["diag", "gpio", "--port", "E"])
    params = gpio_writes(h.link) if h.link else []
    h.finish()
    check(code == 1 and params == [] and "no port E" in text, "port E: nothing to walk, nothing sent")

    print("another master in the mailbox")
    state = {"armed": True}

    def peer(link, adu):
        if state["armed"] and adu[1] == 3:
            state["armed"] = False
            rsp = link.raw(peek.frame(struct.pack(">BHHBHH", 16, 0x0070, 2, 4, 0x5A08, 0x0107)))
            assert rsp[1] == 16, rsp.hex()

    code, text = "", ""
    try:
        h.run(["diag", "gpio", "PB1"], setup=pin_setup(PORT["B"], 1, 0, idr=2), before=peer)
        check(False, "a peer's command between write and read-back is refused")
    except cli.GpioTorn:
        check(not state["armed"], "a peer's command between write and read-back is refused")
    h.finish()

    print("a queued I2C command, and a second master's pin query (review F2)")

    def queue_lmp(link):
        """Master 1's LMP91000 read, queued and not yet run: nothing links
        main.c into the oracle, so it stays PENDING until #diagdone."""
        rsp = link.raw(peek.frame(struct.pack(">BHHBHH", 16, 0x0070, 2, 4, 0x5A01, 0x0010)))
        assert rsp[1] == 16, rsp.hex()

    def mailbox(link):
        rsp = link.raw(peek.frame(struct.pack(">BHH", 3, 0x0070, 7)))
        return list(struct.unpack(">7H", rsp[3:17]))

    try:
        code, text = h.run(["diag", "gpio", "PB1"], setup=queue_lmp)
    except ModbusException as e:
        # The tool must report the refusal, not let it escape.
        code, text = "raised exception %d" % e.code, ""
    link = h.link
    after = mailbox(link)
    reads = h.finish()
    check(code == 1 and "exception 06" in text and "busy" in text.lower() and
          not LEVEL_WORD.search(text),
          "master 2's `diag gpio PB1` is refused as busy, exit 1, no level")
    check(after[:3] == [0x5A01, 0x0010, cli.DIAG_PENDING],
          "and master 1's command still reads 0x5A01 0x0010 PENDING (%s)"
          % ["0x%04X" % v for v in after[:3]])
    check(reads == (0, 0, 0), "no GPIO or RCC register was loaded (%r)" % (reads,))

    code, text = h.run(["diag", "gpio", "--port", "A"], setup=queue_lmp)
    params = gpio_writes(h.link)
    h.finish()
    check(code == 1 and params == [0x0000] and "exception 06" in text,
          "a port walk stops at its first refused pin rather than printing sixteen of them")

    # Master 1's side: its poll must neither end at a status its command did
    # not produce, nor report a result that belongs to someone else.
    state = {"n": 0}

    def peer_gpio_then_done(link, adu):
        if adu[1] != 3 or struct.unpack(">H", adu[2:4])[0] != 0x0070:
            return
        state["n"] += 1
        if state["n"] == 1:
            rsp = link.raw(peek.frame(struct.pack(">BHHBHH", 16, 0x0070, 2, 4, 0x5A08, 0x0101)))
            state["peer"] = (rsp[1], rsp[2] if len(rsp) > 2 else None)
        elif state["n"] == 2:
            assert ctl(link, "#diagdone 2 1234 0 0 0") == "ok"

    code, text = h.run(["diag", "lmp-read", "0x10"], before=peer_gpio_then_done)
    h.finish()
    check(state.get("peer") == (0x90, 6),
          "the peer's pin query between master 1's polls got exception 06 (%r)"
          % (state.get("peer"),))
    check(code in (0, None) and "result: OK" in text and "0x1234" in text and
          "ERR_BUSY" not in text,
          "master 1 kept polling through it and reports its own OK and RDATA0 0x1234")

    def peer_replaces_after_done(link, adu):
        if adu[1] != 3 or struct.unpack(">H", adu[2:4])[0] != 0x0070:
            return
        state["n"] += 1
        if state["n"] == 1:
            assert ctl(link, "#diagdone 2 1234 0 0 0") == "ok"
            rsp = link.raw(peek.frame(struct.pack(">BHHBHH", 16, 0x0070, 2, 4, 0x5A08, 0x0101)))
            assert rsp[1] == 16, rsp.hex()

    state["n"] = 0
    try:
        h.run(["diag", "lmp-read", "0x10"], setup=pin_setup(PORT["B"], 1, 0, idr=2),
              before=peer_replaces_after_done)
        check(False, "a result that is another master's command is refused, not printed")
    except cli.DiagTorn:
        check(True, "a result that is another master's command is refused, not printed")
    h.finish()

    # A 0x000E probe's clobber, replayed on the wire the old regmap.c produced
    # (9c05fef: DIAG_STATUS := ERR_BUSY while the command stays queued). The
    # current oracle cannot produce it any more, which is the point of F2.
    class Clobber0x000E:
        def __init__(self, inner):
            self.inner, self.p, self.log, self.polls = inner, inner.p, inner.log, 0

        def exchange(self, adu, expect_len):
            rsp = self.inner.exchange(adu, expect_len)
            if adu[1] == 3 and struct.unpack(">H", adu[2:4])[0] == 0x0070:
                self.polls += 1
                if self.polls == 1:
                    regs = list(struct.unpack(">7H", rsp[3:17]))
                    regs[2] = 6
                    return peek.frame(bytes([3, 14]) + struct.pack(">7H", *regs))
                if self.polls == 2:
                    assert ctl(self.inner, "#diagdone 2 beef 0 0 0") == "ok"
                    return self.inner.exchange(adu, expect_len)
            return rsp

        def close(self):
            pass

    link = peek.OracleLink(exe)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            cli.cmd_diag(Bus(Clobber0x000E(link), 3),
                         type("A", (), {"diag_cmd": "lmp-read", "param": "0x10",
                                        "gpio_port": None})())
            rc = 0
        except SystemExit as e:
            rc = e.code
    link.close()
    check(rc == 0 and "ERR_BUSY" not in out.getvalue() and "0xBEEF" in out.getvalue(),
          "on a 0x000E probe, ERR_BUSY over master 1's PENDING is not taken as its answer")

    print("a probe that does not know the opcode")
    class Refuse08:
        def __init__(self, inner):
            self.inner = inner
            self.p = inner.p
            self.log = inner.log

        def exchange(self, adu, expect_len):
            if adu[1] == 16 and adu[7:9] == b"\x5a\x08":
                return peek.frame(bytes([0x90, 3]))
            return self.inner.exchange(adu, expect_len)

        def close(self):
            pass

    link = peek.OracleLink(exe)
    out = []
    rc = cli.cmd_diag_gpio(Bus(Refuse08(link), 3),
                           type("A", (), {"param": "PB1", "gpio_port": None})(), out=out.append)
    link.close()
    probe_fw = "FW_VERSION 0x%04X" % cli.FW_LATEST
    check(rc == 1 and any(probe_fw in ln and "needs 0x%04X" % cli.FW_READ_GPIO in ln
                          for ln in out),
          "exception 03 is reported with the probe's FW_VERSION and the one needed")
    return fw_ok


def test_nodebug(exe):
    print("nodebug build")
    link = peek.OracleLink(exe)
    out = []
    try:
        rc = cli.cmd_diag_gpio(Bus(link, 3), type("A", (), {"param": "PB1", "gpio_port": None})(),
                               out=out.append)
        check(rc == 1 and any("exception 02" in ln for ln in out) and
              not any(LEVEL_WORD.search(ln) for ln in out),
              "the mailbox answers exception 02, and the tool reports it rather than a pin")
    except ModbusException as e:
        check(False, "exception %d escaped the tool" % e.code)
    finally:
        link.close()


def main():
    test_sources_of_truth()
    tmp = tempfile.mkdtemp(prefix="o2p-gpio-oracle-")
    try:
        try:
            exe = build_oracle(tmp, 1)
            exe0 = build_oracle(tmp, 0)
        except subprocess.CalledProcessError as e:
            check(False, "the oracle builds from src/ (%s)" % e)
            exe = exe0 = None
        if exe is None or exe0 is None:
            if not FAILS:
                skip("no host C compiler: the CLI was NOT checked against the firmware")
        else:
            test_end_to_end(exe)
            test_nodebug(exe0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d checks, %d failure(s), %d skipped" % (COUNT[0], len(FAILS), len(SKIPS)))
    if FAILS:
        print("FAILED: " + "; ".join(FAILS))
        return 1
    return 2 if SKIPS else 0


if __name__ == "__main__":
    sys.exit(main())
