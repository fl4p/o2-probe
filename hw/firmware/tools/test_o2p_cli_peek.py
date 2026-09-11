#!/usr/bin/env python3
"""tools/o2p_cli.py peek, against the firmware's own register map.

Host-side only: nothing here opens a serial port or touches a probe. The probe
end is tools/peek_oracle.c - src/regmap.c and src/modbus_pdu.c compiled for the
host and answering ADUs over a pipe - so the CLI is checked against the
decisions the firmware actually makes. A Python fake written from the same
reading of regmap.h as the CLI would share any misreading of it, and pass.

Exit 0: every check passed. 1: a check failed. 2: something could not be
evaluated (no host C compiler, no built ELF) - which is not a pass.
"""
import argparse
import contextlib
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

# What regmap.c needs to link on a host - the same files `pio test -e native`
# builds it with, minus the ones only the other suites use.
ORACLE_SOURCES = ["regmap.c", "modbus_pdu.c", "o2.c", "psychro.c", "faults.c",
                  "heater_ctl.c", "update.c", "crc32.c", "boot_desc.c",
                  # regmap.c serves OP_READ_GPIO (FW_VERSION 0x000E) through these
                  "gpio_diag.c", "gpio_hal_host.c"]

FAILS, SKIPS, COUNT = [], [], [0]


def check(cond, what):
    COUNT[0] += 1
    print("  %s %s" % ("ok  " if cond else "FAIL", what))
    if not cond:
        FAILS.append(what)


def skip(what):
    print("  SKIP %s" % what)
    SKIPS.append(what)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    return None


def pattern(a):
    """peek_oracle.c's memory. Test data, not firmware semantics."""
    return (a ^ 0x5A5A5A5A) & 0x7FFFFFFF


def memory(addr, n):
    start = addr & ~3
    count = (addr + n - start + 3) // 4
    raw = b"".join(struct.pack("<I", pattern(start + 4 * i)) for i in range(count))
    return raw[addr - start:addr - start + n]


def build_oracle(tmp, debug):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if cc is None:
        return None
    exe = os.path.join(tmp, "peek_oracle_debug%d" % debug)
    cmd = ([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-DO2P_HOST_TEST=1", "-DO2P_BOARD_REV_A=1", "-DO2P_HEATER_ENABLE=0",
            "-DO2P_DEBUG_ENABLE=%d" % debug, "-I", SRC, "-o", exe,
            os.path.join(HERE, "peek_oracle.c")] +
           [os.path.join(SRC, s) for s in ORACLE_SOURCES] + ["-lm"])
    subprocess.run(cmd, check=True)
    return exe


class OracleLink:
    """The link o2p_update.Bus expects, with the firmware on the other end."""

    def __init__(self, exe):
        self.p = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
        self.log = []
        self.before = None

    def raw(self, adu):
        self.p.stdin.write(adu.hex() + "\n")
        self.p.stdin.flush()
        return bytes.fromhex(self.p.stdout.readline().strip())

    def exchange(self, adu, expect_len):
        if self.before is not None:
            self.before(self, adu)
        rsp = self.raw(adu)
        self.log.append((adu, rsp))
        return rsp

    def close(self):
        self.p.stdin.close()
        self.p.wait()


class Refuse01xx:
    """In front of the real oracle: exception 02 at 0x0100 and above, which is
    what a 0x000C probe answers there. Everything else is the firmware's."""

    def __init__(self, inner):
        self.inner = inner

    def exchange(self, adu, expect_len):
        if adu[1] in (3, 16) and struct.unpack(">H", adu[2:4])[0] >= 0x0100:
            rsp = frame(bytes([adu[1] | 0x80, 2]))
            self.inner.log.append((adu, rsp))
            return rsp
        return self.inner.exchange(adu, expect_len)


def frame(pdu, addr=3):
    a = bytes([addr]) + pdu
    return a + struct.pack("<H", crc16(a))


def peer_trigger(link, target, words):
    """Another master's wide peek, put straight onto the bus."""
    rsp = link.raw(frame(struct.pack(">BHHBHHH", 16, cli.PEEKW_BASE, 3, 6,
                                     target >> 16, target & 0xFFFF, words)))
    assert rsp[1] == 16, rsp.hex()


def requests(link, fc, reg=None):
    out = []
    for req, rsp in link.log:
        if req[1] != fc:
            continue
        r, n = struct.unpack(">HH", req[2:6])
        if reg is None or r == reg:
            out.append((r, n, req, rsp))
    return out


def trigger_words(req):
    return struct.unpack(">H", req[11:13])[0]


def trigger_addr(req):
    hi, lo = struct.unpack(">HH", req[7:11])
    return (hi << 16) | lo


# ------------------------------------------------------------------ pure parts

def test_plan():
    print("planning reads under a reply ceiling")
    fit = cover = whole = mono = True
    for words in range(1, cli.PEEKW_WORDS_MAX + 1):
        prev = None
        for max_adu in range(19, 301):
            reads = cli.plan_wide_reads(words, max_adu)
            regs = []
            for base, count in reads:
                if 5 + 2 * count > min(max_adu, 255):
                    fit = False
                regs.extend(range(base, base + count))
            if regs != list(range(0x0100, 0x0105 + 2 * words)):
                cover = False
            if (reads[0][1] - 5) % 2 or any((b - 0x0105) % 2 or n % 2
                                            for b, n in reads[1:]):
                whole = False
            if prev is not None and len(reads) > prev:
                mono = False
            prev = len(reads)
    check(fit, "no planned read's reply exceeds --max-adu or the probe's 255 bytes")
    check(cover, "the reads cover the header and every data register once, in order")
    check(whole, "no word is split across two reads")
    check(mono, "a larger ceiling never needs more reads")
    dr4, dr3, dr0 = (cli.MAX_ADU_PRESETS[k] for k in ("lorawan-dr4", "lorawan-dr3", "lorawan-dr0"))
    check((dr4, dr3, dr0) == (242 - 15, 115 - 15, 51 - 15),
          "the LoRaWAN presets are RadioLib's EU868 payloadLenMax less a full 15-byte FOpts")
    check(len(cli.plan_wide_reads(30, 255)) == 1 and len(cli.plan_wide_reads(30, dr4)) == 1,
          "the full 30-word block is one read on the wired paths and at DR4/DR5, FOpts full")
    check(cli.plan_wide_reads(30, dr3)[0] == (0x0100, 47),
          "at DR3 the first read is the header and 21 words")
    check(cli.plan_wide_reads(30, dr0)[0] == (0x0100, 15),
          "at DR0-DR2 the first read is the header and 5 words")
    check(cli.plan_wide_reads(30, 46)[0] == (0x0100, 19),
          "at the A8's 46 bytes the first read is the header and 7 words")
    check(raises(lambda: cli.plan_wide_reads(1, 18), ValueError) is not None,
          "refuses a ceiling too small for the header and one word")
    check(raises(lambda: cli.plan_wide_reads(0, 255), ValueError) is not None,
          "refuses 0 words")
    check(raises(lambda: cli.plan_wide_reads(31, 255), ValueError) is not None,
          "refuses 31 words")

    print("--max-adu")
    check(cli.parse_max_adu("auto") is None, "auto defers to the link")
    check(cli.parse_max_adu("a8") == 46 and cli.parse_max_adu("lorawan-dr3") == 100,
          "named paths map to their reply ceilings")
    check(cli.parse_max_adu("0x40") == 64, "a number is a number")
    check(raises(lambda: cli.parse_max_adu("18"), argparse.ArgumentTypeError) is not None,
          "a ceiling that cannot carry one word is refused at the command line")
    check(raises(lambda: cli.parse_max_adu("wifi"), argparse.ArgumentTypeError) is not None,
          "an unknown name is refused")


def test_resolve():
    print("what a symbol means")
    syms = {"g_rm": [(0x20000130, 412)], "label": [(0x08004000, 0)],
            # Two file-local statics of one name, as in the real ELF (review F4).
            "finish": [(0x08007EAC, 56), (0x08009C00, 22)]}

    def ns(target, nbytes=None, count=None):
        return types.SimpleNamespace(target=target, elf="unused.elf",
                                     bytes=nbytes, count=count)

    def get(elf):
        return syms

    check(cli.resolve_peek_target(ns("g_rm"), get)[:2] == (0x20000130, 412),
          "a symbol reads its ELF size by default")
    check(cli.resolve_peek_target(ns("g_rm", count=3), get)[1] == 12, "--count is words")
    check(cli.resolve_peek_target(ns("g_rm", nbytes=7), get)[1] == 7, "--bytes is bytes")
    check(cli.resolve_peek_target(ns("label"), get)[1] == 4,
          "a sizeless symbol reads one word, and says so")
    check(cli.resolve_peek_target(ns("0x1FFF75E0"), get)[:2] == (0x1FFF75E0, 4),
          "a literal address reads one word")
    check(raises(lambda: cli.resolve_peek_target(ns("nope"), get), KeyError) is not None,
          "an unknown symbol is an error, not address 0")
    check(raises(lambda: cli.resolve_peek_target(ns("g_rm", nbytes=0), get), ValueError)
          is not None, "zero bytes is refused")
    e = raises(lambda: cli.resolve_peek_target(ns("finish"), get), cli.AmbiguousSymbol)
    check(e is not None and "0x08007EAC" in str(e) and "0x08009C00" in str(e) and
          "peek 0x08007EAC" in str(e),
          "a name two objects share is refused, listing both addresses and a hex example")
    check(raises(lambda: cli.resolve_peek_target(ns("finish", count=1), get),
                 cli.AmbiguousSymbol) is not None,
          "and still refused when the size is given: the size was never the ambiguity")


# ---------------------------------------------------------- against firmware

def test_end_to_end(exe):
    link = OracleLink(exe)
    bus = Bus(link, 3)
    try:
        fw = bus.read(0x0018, 1)[0]
        check(fw >= 0x000D, "the oracle's register map has the wide block (FW_VERSION 0x%04X)" % fw)

        print("wide block, wired ceiling")
        link.log.clear()
        res = cli.peek_bytes(bus, 0x20000130, 272, 255, fw)
        check(res["status"] == 1 and res["wide"], "272 bytes read OK through the wide block")
        check(res["bytes"] == memory(0x20000130, 272), "the bytes are the ones the firmware copied")
        trig = requests(link, 16, 0x0100)
        check([trigger_words(t[2]) for t in trig] == [30, 30, 8] and res["snapshots"] == 3,
              "three triggers, of 30, 30 and 8 words")
        check(all(len(t[3]) <= 255 for t in requests(link, 3)), "every reply is within 255 bytes")
        check(not requests(link, 16, 0x0065), "the 4-word mailbox is not touched")
        check(len(requests(link, 3)) == 3, "one read per trigger at 255 bytes")

        print("wide block, 51-byte ceiling")
        link.log.clear()
        res = cli.peek_bytes(bus, 0x20000130, 120, 51, fw)
        check(res["status"] == 1 and res["bytes"] == memory(0x20000130, 120),
              "120 bytes survive being split into 51-byte replies")
        check(max(len(t[3]) for t in requests(link, 3)) <= 51, "no reply exceeds 51 bytes")
        check(res["snapshots"] == 1, "and they are still one trigger, one snapshot")

        print("alignment and the firmware's own refusals")
        link.log.clear()
        res = cli.peek_bytes(bus, 0x08004003, 5, 255, fw)
        trig = requests(link, 16, 0x0100)
        check(res["bytes"] == memory(0x08004003, 5), "an unaligned 5-byte symbol comes back exactly")
        check(len(trig) == 1 and trigger_addr(trig[0][2]) == 0x08004000 and
              trigger_words(trig[0][2]) == 2, "by asking for the two whole words around it")
        # Spans that are NOT a multiple of four. Every case above happened to
        # be one, so rounding the word count IN instead of out passed them all
        # (found by fault injection, 2026-09-10).
        link.log.clear()
        res = cli.peek_bytes(bus, 0x20000200, 3, 255, fw)
        trig = requests(link, 16, 0x0100)
        check(res["status"] == 1 and res["bytes"] == memory(0x20000200, 3) and
              len(trig) == 1 and trigger_words(trig[0][2]) == 1,
              "a 3-byte symbol on a word boundary reads the one word holding it")
        link.log.clear()
        res = cli.peek_bytes(bus, 0x08004001, 6, 255, fw)
        trig = requests(link, 16, 0x0100)
        check(res["status"] == 1 and res["bytes"] == memory(0x08004001, 6) and
              len(trig) == 1 and trigger_words(trig[0][2]) == 2,
              "6 bytes starting one byte into a word read both words they touch")

        link.log.clear()
        res = cli.peek_bytes(bus, 0x20008FF8, 16, 255, fw)
        trig = requests(link, 16, 0x0100)
        check(res["status"] == 2 and res["at"] == 0x20008FF8 and "bytes" not in res,
              "a burst off the end of SRAM is ERR_RANGE, with no bytes")
        check(len(trig) == 1 and trigger_words(trig[0][2]) == 4,
              "the count went to the firmware unclamped")
        check(cli.peek_bytes(bus, 0x40000000, 4, 255, fw)["status"] == 2,
              "a peripheral address is refused by the firmware")
        res = cli.peek_bytes(bus, 0x1FFF7590, 12, 255, fw)
        check(res["status"] == 1 and len(res["bytes"]) == 12, "the 96-bit UID is exactly reachable")
        check(cli.peek_bytes(bus, 0x1FFF7590, 16, 255, fw)["status"] == 2,
              "and a fourth UID word is not")

        print("another master in the middle")
        state = {"armed": True}

        def between_pieces(same):
            def hook(l, adu):
                if (state["armed"] and adu[1] == 3 and
                        struct.unpack(">H", adu[2:4])[0] > cli.PEEKW_BASE):
                    state["armed"] = False
                    if same:
                        peer_trigger(l, 0x20000130, 30)
                    else:
                        peer_trigger(l, 0x08004000, 1)
            return hook

        for same, why in ((False, "a different peek"), (True, "an identical peek")):
            state["armed"] = True
            link.before = between_pieces(same)
            e = raises(lambda: cli.peek_wide(bus, 0x20000130, 30, 51), cli.PeekTorn)
            link.before = None
            check(e is not None and not state["armed"],
                  "%s between two pieces is refused (only SEQ can catch the identical one)" % why)

        def before_read(l, adu):
            if state["armed"] and adu[1] == 3:
                state["armed"] = False
                peer_trigger(l, 0x08004000, 30)

        state["armed"] = True
        link.before = before_read
        e = raises(lambda: cli.peek_wide(bus, 0x20000130, 30, 255), cli.PeekTorn)
        link.before = None
        check(e is not None, "another master's trigger between ours and the read is refused")

        print("fallback to the 4-word mailbox")
        notes = []
        link.log.clear()
        res = cli.peek_bytes(Bus(Refuse01xx(link), 3), 0x20000130, 20, 255, 0x000D,
                             log=notes.append)
        narrow = requests(link, 16, 0x0065)
        check(res["status"] == 1 and not res["wide"] and res["bytes"] == memory(0x20000130, 20),
              "a 0x000D probe that answers exception 02 at 0x0100 is read through 0x0065")
        check(any("exception 02" in n for n in notes), "and the tool says it fell back")
        check([n for _, n, _, _ in narrow] == [3, 3], "two 3-register mailbox triggers")

        link.log.clear()
        res = cli.peek_bytes(bus, 0x20000130, 8, 255, 0x000C)
        check(res["status"] == 1 and not res["wide"] and not requests(link, 3, 0x0100) and
              not requests(link, 16, 0x0100), "FW_VERSION 0x000C never touches 0x0100")

        link.log.clear()
        res = cli.peek_bytes(bus, 0x20000100, 4, 255, 0x000B)
        narrow = requests(link, 16, 0x0065)
        check(res["status"] == 1 and res["bytes"] == memory(0x20000100, 4) and
              [n for _, n, _, _ in narrow] == [2], "0x000B gets the 2-register trigger it knows")
        check(cli.peek_bytes(bus, 0x20008FFC, 4, 255, 0x000B)["status"] == 2,
              "and is refused where its fixed 4-word burst does not fit, as 0x000B was")

        print("N2: the narrow path respects --max-adu")
        check(cli.max_narrow_words(19) == 2 and cli.max_narrow_words(255) == 4 and
              cli.max_narrow_words(23) == 3, "the mailbox word cap follows 11 + 4*words")
        for fw, narrow, why in ((0x000C, False, "old firmware"), (0x000E, True, "--narrow")):
            link.log.clear()
            res = cli.peek_bytes(bus, 0x20000000, 16, 19, fw, narrow=narrow)
            replies = [len(rsp) for _, rsp in link.log if rsp and rsp[1] in (3, 0x83)]
            check(res["status"] == 1 and res["bytes"] == memory(0x20000000, 16) and
                  max(replies) <= 19,
                  "%s: 16 bytes under --max-adu 19 split into <=19-byte replies (was 27)" % why)
            triggers = [n for _, n, _, _ in requests(link, 16, 0x0065)]
            check(all(t == 3 for t in triggers) and len(triggers) >= 2,
                  "%s: two-word mailbox triggers, not one 4-word request" % why)
        check(raises(lambda: cli.peek_bytes(bus, 0x20000000, 4, 14, 0x000C), ValueError)
              is not None,
              "a ceiling too small for even a one-word mailbox reply is refused before any trigger")

        print("N3: the mailbox cannot tell padding from data under a shorter peer")
        state = {"armed": True}

        def shorter_peer(l, adu):
            # B triggers ONE word at the same address between A's trigger and read.
            if state["armed"] and adu[1] == 3:
                state["armed"] = False
                rsp = l.raw(frame(struct.pack(">BHHBHHH", 16, 0x0065, 3, 6,
                                              0x2000, 0x0000, 1)))
                assert rsp[1] == 16, rsp.hex()

        link.before = shorter_peer
        status, got = cli.peek_narrow(bus, 0x20000000, 4, 0x000C)
        link.before = None
        # The wire cannot distinguish it: status OK, address echo passes, and 3
        # of 4 words are 0xFFFFFFFF padding. This documents the hole N3 is about;
        # cmd_peek() carries the sole-ownership caveat that warns of it.
        check(status == cli.PEEK_OK and got[0] == pattern(0x20000000) and
              got[1:] == [0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF],
              "a shorter same-address peer makes padding read as data (address echo cannot catch it)")

        code, text = run_cmd_peek(bus, "0x20000000", narrow=True)
        check(code in (0, None) and "sole ownership" in text and "4-word mailbox" in text,
              "a --narrow peek prints the sole-ownership caveat")
        code, text = run_cmd_peek(bus, "0x20000000")
        check("sole ownership" not in text and "wide block" in text,
              "a wide-block peek carries no such caveat")
    finally:
        link.before = None
        link.close()


def test_echoes(exe):
    """Each echo check the CLI makes, broken on purpose: a peer's frame goes
    onto the bus at the one moment that check exists for (review C5, C6, F6)."""
    link = OracleLink(exe)
    bus = Bus(link, 3)
    state = {"armed": True}
    try:
        print("the echoes that prove a result is this trigger's")

        def same_addr_other_words(l, adu):
            if state["armed"] and adu[1] == 3:
                state["armed"] = False
                peer_trigger(l, 0x20000130, 29)

        link.before = same_addr_other_words
        e = raises(lambda: cli.peek_wide(bus, 0x20000130, 30, 255), cli.PeekTorn)
        link.before = None
        check(e is not None and not state["armed"],
              "a peer's trigger at the SAME address for 29 words is caught by the WORDS echo")

        def narrow_elsewhere(l, adu):
            if state["armed"] and adu[1] == 3:
                state["armed"] = False
                rsp = l.raw(frame(struct.pack(">BHHBHHH", 16, 0x0065, 3, 6,
                                              0x0800, 0x4000, 4)))
                assert rsp[1] == 16, rsp.hex()

        state["armed"] = True
        link.before = narrow_elsewhere
        e = raises(lambda: cli.peek_narrow(bus, 0x20000130, 4, 0x000C), cli.PeekTorn)
        link.before = None
        check(e is not None and not state["armed"],
              "a peer's 4-word trigger at another address is caught by the mailbox's address echo")

        print("a ceiling too small is refused before anything is sent")
        link.log.clear()
        e = raises(lambda: cli.peek_wide(bus, 0x20000130, 1, 18), ValueError)
        check(e is not None and not link.log,
              "no trigger goes out when the reads cannot be planned")
    finally:
        link.before = None
        link.close()


def run_cmd_peek(bus, target, **kw):
    """cmd_peek() as main() calls it, stdout captured. No ELF: a literal
    address, with the build-ID check forced past."""
    args = types.SimpleNamespace(elf="/nonexistent/firmware.elf", force_build_id=True,
                                 target=target, bytes=None, count=None, max_adu=255,
                                 narrow=False, port="/dev/oracle")
    for k, v in kw.items():
        setattr(args, k, v)
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            cli.cmd_peek(bus, args)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        except (ModbusException, LookupError, IOError) as e:
            # Escaping the command IS the failure a caller checks for: return
            # it as an outcome, so a check names it instead of the script dying.
            code = "raised %s: %s" % (type(e).__name__, e)
    return code, out.getvalue()


def test_nodebug(exe):
    print("nodebug build")
    link = OracleLink(exe)
    bus = Bus(link, 3)
    try:
        notes = []
        e = raises(lambda: cli.peek_bytes(bus, 0x20000130, 4, 255, 0x000D, log=notes.append),
                   ModbusException)
        check(e is not None and e.code == 2,
              "both peeks answer exception 02, and the tool reports it rather than data")
        check(notes and not any("using the 4-word mailbox" in n for n in notes),
              "the fallback note does not promise a mailbox a nodebug build refuses too")
        code, text = run_cmd_peek(bus, "0x20000130")
        check(code == 1 and "debug blocks compiled out" in text and "Status   : OK" not in text,
              "`peek` on a nodebug build says the debug blocks are compiled out, exit 1")
    finally:
        link.close()


def test_elf():
    print("the real ELF")
    elf = cli.DEFAULT_ELF
    if not os.path.exists(elf):
        skip("no %s: build it with `pio run -e o2probe` to check nm -S parsing" % elf)
        return
    try:
        syms = cli.get_elf_symbols(elf)
    except RuntimeError as e:
        skip("no nm: %s" % e)
        return
    g_rm = syms.get("g_rm", [])
    check(len(g_rm) == 1 and g_rm[0][1] >= 272 + 4 * cli.PEEKW_WORDS_MAX and g_rm[0][1] % 4 == 0,
          "g_rm is one object with a size, and it includes the wide block's buffer (%r)" % (g_rm,))
    check(syms.get("g_o2p_build_id", [(0, 0)]) [0][1] == 4, "g_o2p_build_id is 4 bytes")
    shared = sorted(n for n, v in syms.items() if len(v) > 1)
    check(bool(shared), "the real ELF has names that several objects share (%s)" % shared[:4])
    if shared:
        args = types.SimpleNamespace(target=shared[0], elf=elf, bytes=None, count=None)
        check(raises(lambda: cli.resolve_peek_target(args), cli.AmbiguousSymbol) is not None,
              "and `peek %s` against it is refused, not resolved to one of them" % shared[0])


def main():
    test_plan()
    test_resolve()
    tmp = tempfile.mkdtemp(prefix="o2p-peek-oracle-")
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
            test_echoes(exe)
            test_nodebug(exe0)
        test_elf()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d checks, %d failure(s), %d skipped" % (COUNT[0], len(FAILS), len(SKIPS)))
    if FAILS:
        print("FAILED: " + "; ".join(FAILS))
        return 1
    return 2 if SKIPS else 0


if __name__ == "__main__":
    sys.exit(main())
