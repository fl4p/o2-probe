#!/usr/bin/env python3
"""Fail if tools/o2p_update.py's register addresses drift from src/update.h.

The field tool carries the addresses and command magics as literals on purpose:
it has to run from a laptop with no checkout, over a serial adapter, next to a
probe in a field. That is exactly why they need checking here - a tool that
writes BEGIN to the wrong register gets an exception 02 from a probe that is
otherwise fine, and the person holding the laptop has no way to tell which of
the two is wrong.
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

    if problems:
        print("!! the field update tool disagrees with src/update.h:")
        for p in problems:
            print("   -", p)
        return 1
    print("field update tool agrees with src/update.h (%d registers, "
          "%d commands, %d states, %d errors)"
          % (len(REGS), len(CMDS), len(STATES), len(ERRORS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
