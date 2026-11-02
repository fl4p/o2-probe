#!/usr/bin/env python3
"""Fail if tools/o2p_update.py drifts from the firmware it drives.

Two headers, for the same reason.

The field tool carries the addresses and command magics as literals on purpose:
it has to run from a laptop with no checkout, over a serial adapter, next to a
probe in a field. That is exactly why they need checking here - a tool that
writes BEGIN to the wrong register gets an exception 02 from a probe that is
otherwise fine, and the person holding the laptop has no way to tell which of
the two is wrong.

The same applies to `--bridge`, which is the one thing in the tool whose whole
purpose is to be trusted when nothing else answers: a `--bridge` that asked the
wrong address would report "no bridge" on a working bridge, and send someone
looking for a fault in the probe.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)

# tool constant -> header name
REGS = {
    "R_STATUS": "O2P_REG_UPD_STATUS",
    "R_BLOCK_MAX": "O2P_REG_UPD_BLOCK_MAX",
    "R_SLOT_HI": "O2P_REG_UPD_SLOT_HI",
    "R_CMD": "O2P_REG_UPD_CMD",
    "R_LEN_HI": "O2P_REG_UPD_LEN_HI",
    "R_CRC_HI": "O2P_REG_UPD_CRC_HI",
    "R_RECV_HI": "O2P_REG_UPD_RECV_HI",
    "R_NEXT_SEQ": "O2P_REG_UPD_NEXT_SEQ",
    "R_LOADER_VER": "O2P_REG_UPD_LOADER_VER",
    "R_IMAGE_VER": "O2P_REG_UPD_IMAGE_VER",
    "R_INSTALLS": "O2P_REG_UPD_INSTALLS",
    "R_DATA": "O2P_REG_UPD_DATA",
}
CMDS = {
    "CMD_BEGIN": "O2P_UPD_CMD_BEGIN",
    "CMD_COMMIT": "O2P_UPD_CMD_COMMIT",
    "CMD_BOOT": "O2P_UPD_CMD_BOOT",
    "CMD_ABORT": "O2P_UPD_CMD_ABORT",
    "CMD_STAY": "O2P_UPD_CMD_STAY",
}
# The tool decodes STATUS into these names; they are positional, so a state
# inserted in the middle of the C enum would silently rename every state after
# it in every message the tool prints.
STATES = ["IDLE", "ERASING", "READY", "RECEIVING", "VERIFYING", "STAGED",
          "ERROR"]
ERRORS = ["NONE", "STATE", "LENGTH", "SEQUENCE", "ALIGN", "FLASH", "CRC",
          "IMAGE", "NOIMAGE"]


def header_values(text):
    out = {}
    for m in re.finditer(r"(O2P_REG_UPD_\w+)\s*=\s*(0x[0-9A-Fa-f]+)u", text):
        out[m.group(1)] = int(m.group(2), 0)
    for m in re.finditer(r"#define\s+(O2P_UPD_CMD_\w+)\s+(0x[0-9A-Fa-f]+)u",
                         text):
        out[m.group(1)] = int(m.group(2), 0)
    return out


def header_enum(text, prefix):
    """Ordinals of O2P_UPD_<prefix><NAME> as written in the header's enum."""
    got = {}
    for m in re.finditer(r"O2P_UPD_%s(\w+)\s*=\s*(\d+)u" % prefix, text):
        got[m.group(1)] = int(m.group(2))
    return got


def tool_values(text):
    out = {}
    for m in re.finditer(r"^(\w+)(?:,\s*(\w+))?(?:,\s*(\w+))?\s*=\s*(.+)$",
                         text, re.M):
        names = [n for n in m.groups()[:3] if n]
        values = [v.strip() for v in m.group(4).split(",")]
        if len(names) != len(values):
            continue
        for n, v in zip(names, values):
            v = v.strip("()")
            if re.fullmatch(r"0x[0-9A-Fa-f]+", v):
                out[n] = int(v, 0)
    return out


def bridge_problems(tool):
    """The tool's --bridge constants against src/bridge_main.c."""
    src = open(os.path.join(FW, "src", "bridge_main.c"), encoding="utf-8").read()
    out = []

    def one(pattern, what):
        m = re.search(pattern, src)
        if not m:
            out.append("src/bridge_main.c no longer defines %s in a form this "
                       "check can read" % what)
            return None
        return int(m.group(1), 0)

    want = {
        "BRIDGE_ADDR": one(r"#define O2P_BRIDGE_ADDR\s+(\d+)u", "O2P_BRIDGE_ADDR"),
        "BRIDGE_IDENT": one(r"#define BR_IDENT\s+(0x[0-9A-Fa-f]+)u", "BR_IDENT"),
        # The version at which the bus rate became writable. If the firmware
        # ever raised BR_VERSION for an unrelated reason and this stayed put,
        # the tool would try to re-rate a bridge that cannot, and strand the
        # probe behind it; if the firmware LOWERED it, the tool would refuse a
        # bridge that can. Both are silent, and only this check sees them.
        "BRIDGE_VERSION_RERATEABLE":
            one(r"#define BR_VERSION_RERATEABLE\s+(\d+)u",
                "BR_VERSION_RERATEABLE"),
        # Which register carries it. The tool writes this number; the firmware
        # decides what it means.
        "BRIDGE_REG_BUS_BAUD":
            one(r"BR_REG_BUS_BAUD\s*=\s*(\d+)u", "BR_REG_BUS_BAUD"),
    }
    for name, value in want.items():
        if value is None:
            continue
        m = re.search(r"^%s = (0x[0-9A-Fa-f]+|\d+)$" % name, tool, re.M)
        if not m:
            out.append("tools/o2p_update.py no longer defines %s" % name)
        elif int(m.group(1), 0) != value:
            out.append("tools/o2p_update.py %s = %d, src/bridge_main.c says %d"
                       % (name, int(m.group(1), 0), value))

    ver = one(r"#define BR_VERSION\s+(\d+)u", "BR_VERSION")
    rer = want.get("BRIDGE_VERSION_RERATEABLE")
    if ver is not None and rer is not None and ver < rer:
        out.append("src/bridge_main.c reports BR_VERSION %d but says the bus "
                   "rate is writable from %d - no bridge would ever be "
                   "re-rated" % (ver, rer))

    # The rates the bridge accepts, against the probe's own enum. A bridge that
    # would take a rate the probe cannot reach is a way to move the cable
    # somewhere the probe is not, and the tool picks its target from the PROBE
    # table -- so the check is that the firmware's two lists agree.
    rep = open(os.path.join(FW, "src", "bridge_reply.h"), encoding="utf-8").read()
    accepts = set(int(m, 0) for m in
                  re.findall(r"#define O2P_BRIDGE_BAUD_\d+\s+(\d+)u", rep))
    tbl = re.search(r"^BAUD_CODES = \{(.*)\}$", tool, re.M)
    codes = set(int(v) for v in re.findall(r":\s*(\d+)", tbl.group(1))) \
        if tbl else set()
    # UNEVALUABLE INPUT IS NOT A PASS. Written as `if accepts and codes and
    # accepts != codes` this failed open: a renamed macro or a reformatted
    # Python table empties one side, the comparison is skipped, and the check
    # reports agreement it never established. Both sides are regex-scraped from
    # source, so "I could not read it" is a likely outcome and has to be loud.
    if not accepts:
        out.append("src/bridge_reply.h no longer declares its accepted bus "
                   "rates in a form this check can read (O2P_BRIDGE_BAUD_n)")
    if not codes:
        out.append("tools/o2p_update.py no longer declares BAUD_CODES in a "
                   "form this check can read")
    if accepts and codes and accepts != codes:
        out.append("src/bridge_reply.h accepts bus rates %s, the tool's "
                   "BAUD_CODES has %s - one of them can name a rate the other "
                   "cannot reach"
                   % (sorted(accepts), sorted(codes)))

    # AND THE DECLARATIONS AGAINST THE BRANCH THAT ACTUALLY ACCEPTS THEM. Every
    # check above this line reads #defines. That is why none of them said
    # anything when 5e163a1 declared O2P_BRIDGE_BAUD_5, static-asserted it in
    # bridge_main.c and listed it for the updater, while write_regs() went on
    # testing _1.._4 and answered exception 03 to a write of 57600: the
    # declared set and the tool agreed perfectly, and the accepting branch -
    # the only thing a master meets - was never in the comparison.
    # write_regs() now iterates O2P_BRIDGE_BAUD_LIST, so checking that the LIST
    # names every declared macro is what makes the scrape above mean what it
    # has always claimed to mean.
    m_list = re.search(r"#define O2P_BRIDGE_BAUD_LIST((?:.*\\\n)*.*)", rep)
    if not m_list:
        out.append("src/bridge_reply.h no longer defines O2P_BRIDGE_BAUD_LIST "
                   "- that macro is what write_regs() iterates, and without it "
                   "the rates the bridge declares and the rates it accepts can "
                   "drift apart again with every check here still passing")
    else:
        declared_n = set(re.findall(r"#define O2P_BRIDGE_BAUD_(\d+)\s+\d+u", rep))
        listed_n = set(re.findall(r"O2P_BRIDGE_BAUD_(\d+)", m_list.group(1)))
        missing = declared_n - listed_n
        if missing:
            out.append("src/bridge_reply.h declares %s but O2P_BRIDGE_BAUD_LIST "
                       "omits it - the bridge would advertise a rate its own "
                       "write path answers with exception 03"
                       % ", ".join(sorted("O2P_BRIDGE_BAUD_%s" % i
                                          for i in missing)))

    # The SWD mailbox: a literal address and a literal layout at both ends,
    # with a debugger in between that will happily read whatever is at the
    # address it is given and report success.
    mbx = open(os.path.join(FW, "src", "bridge_mailbox.h"),
               encoding="utf-8").read()
    for tool_name, hdr_name in (("MBX_BASE", "O2P_MBX_BASE"),
                                ("MBX_MAGIC", "O2P_MBX_MAGIC")):
        h = re.search(r"#define %s\s+(0x[0-9A-Fa-f]+)u" % hdr_name, mbx)
        t = re.search(r"^%s = (0x[0-9A-Fa-f]+)$" % tool_name, tool, re.M)
        if not h:
            out.append("src/bridge_mailbox.h no longer defines %s" % hdr_name)
        elif not t:
            out.append("tools/o2p_update.py no longer defines %s" % tool_name)
        elif int(h.group(1), 0) != int(t.group(1), 0):
            out.append("tools/o2p_update.py %s = 0x%08X, src/bridge_mailbox.h "
                       "%s = 0x%08X" % (tool_name, int(t.group(1), 0), hdr_name,
                                        int(h.group(1), 0)))

    # Field offsets, from the header's O2P_MBX_OFF_* constants - which
    # src/bridge_mailbox.h pins to the real struct with offsetof, so the
    # compiler rejects a layout that disagrees with them. Reading the offsets
    # out of the declarations' COMMENTS, as this check first did, was broken
    # by an adversarial review in one move: swapping two declarations and
    # leaving their comments alone passed everything.
    for field, tool_name in (("HOST_SEQ", "MBX_OFF_HOST_SEQ"),
                             ("TARGET_SEQ", "MBX_OFF_TARGET_SEQ"),
                             ("TX_LEN", "MBX_OFF_TX_LEN"),
                             ("RX_LEN", "MBX_OFF_RX_LEN"),
                             ("STATUS", "MBX_OFF_STATUS"),
                             ("TX", "MBX_OFF_TX"),
                             ("RX", "MBX_OFF_RX")):
        h = re.search(r"#define O2P_MBX_OFF_%s\s+(0x[0-9A-Fa-f]+)u" % field, mbx)
        t = re.search(r"^%s = (0x[0-9A-Fa-f]+)$" % tool_name, tool, re.M)
        if not h:
            out.append("src/bridge_mailbox.h no longer defines "
                       "O2P_MBX_OFF_%s" % field)
        elif not t:
            out.append("tools/o2p_update.py no longer defines %s" % tool_name)
        elif int(h.group(1), 0) != int(t.group(1), 0):
            out.append("mailbox field %s is at +0x%02X in the header and "
                       "+0x%02X in the tool" % (field, int(h.group(1), 0),
                                                int(t.group(1), 0)))

    # And the header's constants must actually be pinned to the struct. A
    # header that defines the offsets but drops the offsetof assertions is
    # back to being a comment.
    for field in ("magic", "version", "host_seq", "target_seq", "tx_len",
                  "rx_len", "status", "reply_ms", "tx", "rx"):
        if not re.search(r"O2P_MBX_ASSERT_AT\(%s,\s" % field, mbx):
            out.append("src/bridge_mailbox.h no longer pins %s's offset to "
                       "the struct with offsetof" % field)

    m = re.search(r"BR_REG_COUNT\s*=\s*(\d+)u", src)
    n = len(re.findall(r'"', re.search(r"BRIDGE_FIELDS = \[(.*?)\]", tool,
                                       re.S).group(1))) // 2
    if m and int(m.group(1)) != n:
        out.append("tools/o2p_update.py names %d bridge registers, "
                   "src/bridge_main.c has %s" % (n, m.group(1)))
    return out


def config_problems(tool):
    """The tool's baud-negotiation constants against src/regmap.h.

    The updater raises the probe's baud for the duration of a transfer, which
    means it writes a CONFIG register - the one block outside src/update.h it
    touches at all. A drifted address there is worse than a drifted update
    register: 0x0031 is BAUD_CODE, and the registers either side of it are the
    slave address and the parity, so an off-by-one would silently re-address
    the probe or take it to 8N1 instead of speeding it up. Either one leaves a
    potted probe unreachable at the settings the tool then falls back to.
    """
    src = open(os.path.join(FW, "src", "regmap.h"), encoding="utf-8").read()
    out = []

    for tool_name, hdr_name in (("R_SLAVE_ADDR", "O2P_REG_SLAVE_ADDR"),
                                ("R_BAUD_CODE", "O2P_REG_BAUD_CODE"),
                                ("R_PARITY_CODE", "O2P_REG_PARITY_CODE"),
                                # The two-way probation proof (FW 0x001D). A
                                # drifted ACK address would make every retime
                                # revert after 10 s - safe, but silently slow.
                                ("R_PROBATION_NONCE", "O2P_REG_PROBATION_NONCE"),
                                ("R_PROBATION_ACK", "O2P_REG_PROBATION_ACK")):
        h = re.search(r"%s\s*=\s*(0x[0-9A-Fa-f]+)u" % hdr_name, src)
        t = re.search(r"^%s = (0x[0-9A-Fa-f]+)$" % tool_name, tool, re.M)
        if not h:
            out.append("src/regmap.h no longer defines %s" % hdr_name)
        elif not t:
            out.append("tools/o2p_update.py no longer defines %s" % tool_name)
        elif int(h.group(1), 0) != int(t.group(1), 0):
            out.append("tools/o2p_update.py %s = 0x%04X, src/regmap.h %s = "
                       "0x%04X" % (tool_name, int(t.group(1), 0), hdr_name,
                                   int(h.group(1), 0)))

    # code -> rate, both sides. The tool picks the highest-RATE code as "the
    # fastest", so a code the header has and the tool does not is not cosmetic
    # - it is a speed-up the tool silently declines to take. A code the TOOL
    # has and the header does not is the dangerous direction: it would ask a
    # probe for a rate that firmware rejects, and fall back on every push.
    hdr_rates = {int(m.group(2)): int(m.group(1))
                 for m in re.finditer(r"O2P_BAUD_(\d+)\s*=\s*(\d+)u", src)}
    m = re.search(r"^BAUD_CODES = \{(.*?)\}$", tool, re.M | re.S)
    if not m:
        out.append("tools/o2p_update.py no longer defines BAUD_CODES in a "
                   "form this check can read")
    elif not hdr_rates:
        out.append("src/regmap.h no longer declares the O2P_BAUD_* rates in a "
                   "form this check can read")
    else:
        tool_rates = {int(k): int(v) for k, v in
                      re.findall(r"(\d+)\s*:\s*(\d+)", m.group(1))}
        if tool_rates != hdr_rates:
            out.append("tools/o2p_update.py BAUD_CODES = %r, src/regmap.h "
                       "declares %r" % (tool_rates, hdr_rates))

    # The enum is the SPELLING; O2P_BAUD_MAX_CODE is what o2p_config_valid()
    # actually enforces, and they are two separate lines that can drift apart.
    # A MAX_CODE tightened below a code the tool still offers does not break
    # the comparison above at all - both sides keep listing 38400 - it just
    # makes every push get exception 03 and silently fall back to 9600 for
    # ever. Checked against the tool's table AND against the enum, because a
    # MAX_CODE above the enum is a firmware that accepts a code it has no rate
    # for.
    mx = re.search(r"O2P_BAUD_MAX_CODE\s*=\s*(\d+)u", src)
    if not mx:
        out.append("src/regmap.h no longer defines O2P_BAUD_MAX_CODE in a "
                   "form this check can read")
    elif hdr_rates:
        limit = int(mx.group(1))
        if limit != max(hdr_rates):
            out.append("src/regmap.h O2P_BAUD_MAX_CODE = %d but the O2P_BAUD_* "
                       "enum goes up to %d" % (limit, max(hdr_rates)))
        if m and tool_rates and max(tool_rates) > limit:
            out.append("tools/o2p_update.py offers baud code %d, which "
                       "o2p_config_valid() refuses: O2P_BAUD_MAX_CODE = %d"
                       % (max(tool_rates), limit))

    # THE TWO COPIES THAT FAIL OPEN. The enum declares the codes; these two
    # switches are what actually set a divisor, and both end in
    # `default: 9600`. A code added to the enum and to MAX_CODE but not to
    # these is accepted by o2p_config_valid(), reported back by the register
    # map, agreed on by this tool - and runs the USART at 9600 while every
    # other copy says otherwise. Nothing about that is visible on the bus; the
    # probe simply stops answering and no counter moves.
    #
    # Pinning the DECLARATION and not the code that consumes it is guard-review
    # item 4, and this check had exactly that hole.
    for path, what in (("modbus_rtu.c", "the application's baud_from_code()"),
                       ("loader_main.c", "the bootloader's read_serial()")):
        text = open(os.path.join(FW, "src", path), encoding="utf-8").read()
        rates = {int(mm.group(1)): int(mm.group(2)) for mm in
                 re.finditer(r"case O2P_BAUD_(\d+):\s*(?:\*baud =\s*)?"
                             r"(?:return\s*)?(\d+)u", text)}
        if not rates:
            out.append("src/%s no longer maps baud codes in a form this "
                       "check can read" % path)
            continue
        # The switch cases name the codes by RATE (`case O2P_BAUD_19200:`),
        # so what is checked is that each one assigns the rate its own name
        # claims. The default arm supplies 9600, so that code is legitimately
        # absent; every OTHER code must be present and must agree with itself.
        want = {r: r for r in hdr_rates.values() if r != 9600}
        if rates != want:
            out.append("%s maps %r, src/regmap.h's enum declares %r "
                       "(9600 comes from the default arm)"
                       % (what, rates, want))
    return out


def main():
    hdr = open(os.path.join(FW, "src", "update.h"), encoding="utf-8").read()
    tool = open(os.path.join(HERE, "o2p_update.py"), encoding="utf-8").read()

    hv = header_values(hdr)
    tv = tool_values(tool)
    problems = []

    for tool_name, hdr_name in list(REGS.items()) + list(CMDS.items()):
        if hdr_name not in hv:
            problems.append("src/update.h no longer defines %s" % hdr_name)
        elif tool_name not in tv:
            problems.append("tools/o2p_update.py no longer defines %s in a form "
                            "this check can read" % tool_name)
        elif tv[tool_name] != hv[hdr_name]:
            problems.append("tools/o2p_update.py %s = 0x%04X, src/update.h %s "
                            "= 0x%04X" % (tool_name, tv[tool_name], hdr_name,
                                          hv[hdr_name]))

    for prefix, names, what in (("", STATES, "state"), ("ERR_", ERRORS, "error")):
        got = header_enum(hdr, prefix)
        for i, n in enumerate(names):
            if n not in got:
                problems.append("src/update.h has no %s O2P_UPD_%s%s"
                                % (what, prefix, n))
            elif got[n] != i:
                problems.append("%s %s is %d in src/update.h but position %d in "
                                "tools/o2p_update.py's list"
                                % (what, n, got[n], i))

    problems += bridge_problems(tool)
    problems += config_problems(tool)

    if problems:
        print("!! the field update tool disagrees with the firmware:")
        for p in problems:
            print("   -", p)
        return 1
    print("field update tool agrees with src/update.h (%d registers, "
          "%d commands, %d states, %d errors), with src/bridge_main.c, and "
          "with src/regmap.h's config registers and baud codes"
          % (len(REGS), len(CMDS), len(STATES), len(ERRORS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
