#!/usr/bin/env python3
"""Poll the o2-probe over Modbus RTU - what the Dragino reads, on a laptop.

The node on the farm cable is an RS485-LS whose reads are literal
pre-programmed FC03 frames. This is the same thing from a serial port: a
USB-RS485 dongle, or a spare board flashed `-e bridge` with a USB-TTL lead on
its USART2 pads. The bridge is transparent, so nothing here knows or cares
which one is in the path - address the PROBE (default 3), not the bridge.

    python3 tools/o2p_poll.py --port /dev/cu.usbserial-0001
    python3 tools/o2p_poll.py --port ... --diag          # + the diagnostic block
    python3 tools/o2p_poll.py --port ... out.csv --count 240 --interval 30

This is the Modbus twin of tools/o2p_capture.py, which reads the same register
map over SWD. Use that one when the board is on a debugger; use this one when
it is on a cable - and only this one proves the cable.

It refuses to print a number it cannot justify:

  * The register map is transcribed from src/regmap.h and CHECKED against it at
    startup (--no-check to skip). A firmware that moved a register decodes to
    plausible garbage otherwise, which is the failure this file exists to avoid.
  * Sentinels are the firmware saying "do not trust me": 0xFFFF for the
    unsigned channels, 0x8000 for the signed ones. They become an explicit
    `invalid`, never a value, and an empty cell in CSV - so a plot shows a hole
    rather than 65535.
  * O2 is reported as untrustworthy whenever FAULTS says so, using the same
    masks the firmware uses (faults.h), not a hand-copied bit list. A reading
    that is numerically fine but arrives with SETTLING set is not a reading.
  * A failed poll writes an explicit `status=failed` row carrying the reason.
    Never a silent gap, never a stale value carried forward.

Exit status is 1 if any poll failed, so a wrapper can tell.
"""

import argparse
import csv
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2p_update import Bus, ModbusException, SerialLink  # noqa: E402  # type: ignore[import-not-found]

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.pardir, "src")

U16_INVALID = 0xFFFF
I16_INVALID = 0x8000

PRIMARY_BASE, PRIMARY_COUNT = 0x0000, 8
DIAG_BASE, DIAG_COUNT = 0x0010, 32

# Bit -> name. Checked against src/faults.h at startup.
FAULT_BITS = [
    "SETTLING", "I2C_FAIL_LMP", "I2C_FAIL_ADS", "I2C_FAIL_TMP",
    "I2C_FAIL_SHT", "AFE_CONFIG_MISMATCH", "VA_LOW", "VIN_LOW",
    "HEATER_RUNAWAY", "TEMP_OVER", "DEW_SUSPECT", "ADC_RANGE",
    "CAL_DEFAULT", "ADS_DRDY_STUCK", "ADS_CONFIG_LOST", "HEATER_DISABLED",
]

# The two masks the firmware itself tests. Never test a single bit: splitting
# DRDY out of I2C_FAIL_ADS once broke every site that did (faults.h).
# SETTLING is deliberately NOT here: it says the cell has not reached
# equilibrium, which invalidates the %vol derived from the current, not the
# current itself. Moved out of the raw mask in a2b39eb; the startup check
# below compares both lists against faults.h and will fail if they drift again.
INVALIDATE_O2 = ["I2C_FAIL_LMP", "I2C_FAIL_ADS",
                 "AFE_CONFIG_MISMATCH", "VA_LOW", "ADS_DRDY_STUCK",
                 "ADS_CONFIG_LOST", "ADC_RANGE"]
# O2_COMP is DRY BASIS, so it also needs the calibration constant. It needs the
# SHT45 too, but I2C_FAIL_SHT is deliberately NOT here: the bit used to be
# raised for the SHT45's own scheduled de-creep pulse as well, and the firmware
# bridges a short gap from the last measured chamber reading (45 s,
# O2P_RH_MAX_AGE_S in o2.h) rather than blanking the channel. The 350 s de-creep
# mask is LONGER than that bound on purpose, so O2_COMP does take its sentinel
# for most of each mask; O2_RAW is unaffected. Since 2026-09-09 the mask raises no fault either, so a
# chamber reading missing WITHOUT this bit is a scheduled de-creep window and
# with it is a sensor that did not answer. When the data really is too old the
# firmware publishes the SENTINEL, which this tool already decodes to None.
# Kept in step with O2P_FAULTS_INVALIDATE_O2_COMP in faults.h, and now checked
# against it - see check_against_source().
# SETTLING is here and NOT in INVALIDATE_O2, which looks like an oversight and
# is the point: faults.h moved it off the raw channel on 2026-09-08 because the
# cell current during warmup is the only record of the cell recovering, while
# no %vol derived from an unsettled cell can be trusted. This tool kept the old
# pairing and check_against_source() therefore refused to start it at all -
# found 2026-09-09 while verifying an unrelated change, which is the check
# doing its job a day late because nothing runs it but the tool itself.
INVALIDATE_O2_COMP = INVALIDATE_O2 + ["SETTLING", "CAL_DEFAULT"]

CSV_COLUMNS = [
    "utc", "status", "detail", "sample_seq", "settle_s",
    "o2_comp_pct", "o2_raw_ua", "t_tip_c", "t_chamber_c", "rh_pct",
    "heater_duty_pct", "faults", "faults_named", "o2_trusted",
    "vref_mv", "va_mv", "vin_mv", "afe_mv", "dew_margin_k", "t_die_c",
    # t_afe_c was decoded from 0x002C since e2fd562 but never written: it
    # was missing from this list, and DictWriter(extrasaction="ignore")
    # dropped it without a word. Found 2026-09-09 when the first AFE tempco
    # run was about to be logged through this tool.
    "t_afe_c",
    "uptime_s", "fw", "hw", "reset_cause", "lmp_readback",
    "mb_crc_errs", "mb_frame_errs", "i2c_errs", "settle_restarts",
    "faults_ever", "faults_ever_named", "ads_fail_count", "exp_data",
    "t_ext_c",
    # HEATER_LAW (0x0008, FW 0x0018+): the law that produced heater_duty_pct,
    # and whether the dew law has handed the tip to the gradient floor. Kept
    # in THIS list on purpose - DictWriter(extrasaction="ignore") drops any
    # key missing here without a word, which is how t_afe_c was lost once.
    "heater_law",
]


# --------------------------------------------------------------------------
# Agreement with the firmware. A decode table is a copy of a header, and a copy
# rots; this makes it fail loudly at startup instead of quietly at the reading.

def _read(name):
    with open(os.path.join(SRC, name), "r") as fh:
        return fh.read()


def check_against_source():
    """Verify this file's map still matches src/. Returns a list of problems."""
    bad = []
    try:
        regmap, faults = _read("regmap.h"), _read("faults.h")
    except OSError as exc:
        return ["cannot read src/: %s" % exc]

    def const(text, name):
        m = re.search(r"#define\s+%s\s+(\w+)" % re.escape(name), text)
        return int(m.group(1).rstrip("uU"), 0) if m else None

    for name, want in (("O2P_REG_PRIMARY_BASE", PRIMARY_BASE),
                       ("O2P_REG_PRIMARY_COUNT", PRIMARY_COUNT),
                       ("O2P_REG_DIAG_BASE", DIAG_BASE),
                       ("O2P_REG_DIAG_COUNT", DIAG_COUNT)):
        got = const(regmap, name)
        if got is None:
            bad.append("%s not found in regmap.h" % name)
        elif got != want:
            bad.append("%s is 0x%X in regmap.h, this tool assumes 0x%X"
                       % (name, got, want))

    for bit, name in enumerate(FAULT_BITS):
        m = re.search(r"O2P_F_%s\s*=\s*1u?\s*<<\s*(\d+)" % re.escape(name), faults)
        if not m:
            bad.append("fault O2P_F_%s not found in faults.h" % name)
        elif int(m.group(1)) != bit:
            bad.append("fault %s is bit %s in faults.h, this tool assumes %d"
                       % (name, m.group(1), bit))

    # BOTH masks, not just the raw one. Checking only INVALIDATE_O2 was a hole
    # a reviewer found by deleting this tool's compensated list outright and
    # watching the check still pass: the copy that had actually changed in the
    # firmware was the one nothing compared.
    for macro, mine in (("O2P_FAULTS_INVALIDATE_O2", INVALIDATE_O2),
                        ("O2P_FAULTS_INVALIDATE_O2_COMP", INVALIDATE_O2_COMP)):
        m = re.search(r"#define\s+%s\s*\((.*?)\)" % re.escape(macro),
                      faults, re.S)
        if not m:
            bad.append("%s not found in faults.h" % macro)
            continue
        want = set(re.findall(r"O2P_F_(\w+)", m.group(1)))
        # The compensated macro is written in terms of the raw one, so expand
        # that reference the way the preprocessor would.
        if "O2P_FAULTS_INVALIDATE_O2" in m.group(1):
            raw = re.search(r"#define\s+O2P_FAULTS_INVALIDATE_O2\s*\((.*?)\)",
                            faults, re.S)
            if raw:
                want |= set(re.findall(r"O2P_F_(\w+)", raw.group(1)))
        if want != set(mine):
            bad.append("%s differs from faults.h: firmware has %s, this tool "
                       "has %s" % (macro, sorted(want), sorted(mine)))
    return bad


# --------------------------------------------------------------------------
# Decoding. Every conversion is one-way and explicit; a sentinel returns None.

def u16(v):
    return None if v == U16_INVALID else v


def i16(v):
    if v == I16_INVALID:
        return None
    return v - 0x10000 if v & 0x8000 else v


def scaled(v, div):
    return None if v is None else v / div


def fault_names(word):
    return [n for i, n in enumerate(FAULT_BITS) if word & (1 << i)]


def decode_primary(r):
    faults = r[6]
    named = fault_names(faults)
    o2_ok = not any(n in named for n in INVALIDATE_O2_COMP)
    return {
        "o2_comp_pct": scaled(u16(r[0]), 100.0),
        "o2_raw_ua": scaled(i16(r[1]), 100.0),
        "t_tip_c": scaled(i16(r[2]), 100.0),
        "t_chamber_c": scaled(i16(r[3]), 100.0),
        "rh_pct": scaled(u16(r[4]), 100.0),
        "heater_duty_pct": r[5] / 100.0,
        "faults": faults,
        "faults_named": "|".join(named),
        "settle_s": r[7],
        "o2_trusted": o2_ok,
    }


def build_id_str(v):
    """0 is "built without the stamp", not commit 0000000."""
    if v == 0:
        return "unstamped"
    return "%07x%s" % (v & 0x0FFFFFFF, "-dirty" if v & 0x80000000 else "")


def decode_diag(r):
    ever = fault_names(r[0x13])
    return {
        # The rail monitors carry the SAME 0xFFFF sentinel as every other
        # unsigned channel: regmap.c pre-fills the snapshot with
        # O2P_U16_INVALID and main.c leaves it there when the ADC read fails,
        # raising VA_LOW/VIN_LOW rather than publishing a number. Without u16()
        # here an unreadable rail was logged as 65535 mV - a 65 volt reading
        # that a plot draws as a spike and an average silently believes.
        "vref_mv": u16(r[0x00]), "va_mv": u16(r[0x01]),
        "vin_mv": u16(r[0x02]), "afe_mv": u16(r[0x03]),
        "dew_margin_k": scaled(i16(r[0x04]), 100.0),
        "uptime_s": (r[0x06] << 16) | r[0x07],
        "fw": "0x%04X" % r[0x08], "hw": "0x%04X" % r[0x09],
        "reset_cause": "0x%04X" % r[0x0A],
        "lmp_readback": "0x%04X" % r[0x0B],
        "mb_crc_errs": r[0x0C], "mb_frame_errs": r[0x0D], "i2c_errs": r[0x0E],
        "exp_data": None if r[0x0F] == U16_INVALID else r[0x0F],
        "t_ext_c": scaled(i16(r[0x0F]), 100.0) if r[0x0F] != U16_INVALID else None,
        "settle_restarts": r[0x10],
        "sample_seq": r[0x11],
        "t_die_c": scaled(i16(r[0x12]), 100.0),
        "faults_ever": r[0x13],
        "faults_ever_named": "|".join(ever),
        "ads_fail_count": r[0x14],
        "we_buf_mv": u16(r[0x15]), "re_buf_mv": u16(r[0x16]),
        "cell_bias_mv": i16(r[0x17]) if i16(r[0x17]) != -32768 else None,
        # Bit 31 is the dirty flag, bits 27..0 the commit prefix. Rendered as
        # the SHA a human can paste into `git show`, never as a bare number.
        "build_id": build_id_str((r[0x18] << 16) | r[0x19]),
        # 0x1A/0x1B are CMD_RESULT and CAL_STATE, decoded elsewhere.
        # T_AFE (0x002C): the LMP91000's OWN die temperature, and the only
        # channel that reports it. t_die is the MCU at the other end of the
        # board - on 2026-09-08 the heater held the tip at 78.00 C while the
        # MCU die sat at 49 C, and the AFE is at neither. It matters because
        # cell_ua is (0.67*VREF - VOUT)/R_TIA with R_TIA hardcoded at 7000 ohm
        # and SNAS506I publishing no tempco for it: R_TIA is the one
        # uncharacterised term in the oxygen measurement and it drifts with
        # THIS temperature, not the tip's.
        "t_afe_c": (i16(r[0x1C]) / 100.0) if i16(r[0x1C]) != -32768 else None,
        # CE_MV (0x002D): the potentiostat's CONTROL EFFORT, and the reason
        # this tool is the intended consumer - it is deliberately not on the
        # radio. A1 drives the counter electrode until RE reaches the commanded
        # bias, and the loop closes THROUGH THE CELL, so an absent or
        # high-impedance cell leaves CE against a rail while TIACN/REFCN/MODECN
        # still read back exactly as written. cell_bias_mv shows the symptom;
        # this shows the cause. Published, never judged: the 91k/91k divider is
        # 1 % a leg and this cell's healthy CE point has never been measured,
        # so a compliance window here would be a guard built on nothing.
        "ce_mv": u16(r[0x1D]),
        "heater_block": "0x%04X" % r[0x1E] if r[0x1E] != U16_INVALID else None,
        "sampler_timing_ms": r[0x1F] if r[0x1F] != U16_INVALID else None,
    }


def utc_stamp(when=None):
    """ISO-8601 UTC with milliseconds, e.g. 2026-09-11T12:00:00.250Z.

    Whole seconds gave every sample of a sub-second --interval the same
    timestamp, and o2p_tempco rightly refuses duplicate times - so the whole
    CSV was lost (codex review of 75dfc0a). o2p_tempco.parse_utc,
    o2p_thermal's reader and o2p_plot all accept the fractional form."""
    when = time.time() if when is None else when
    return (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(when))
            + ".%03dZ" % int((when % 1.0) * 1000))


HEATER_LAW_ADDR = 0x0008
HEATER_LAW_NAMES = {0: "RH", 1: "OPEN", 2: "TIP", 3: "TIP_AUTO", 4: "DEW",
                    5: "BLIND", 6: "REFUSED"}


def decode_heater_law(v):
    """HEATER_LAW as "DEW", "DEW+UNREACHABLE", ..., or None for 0xFFFF.

    0xFFFF is "the heater has not been stepped", not a law, so it is None
    rather than a name - the same rule as every other invalid sentinel here."""
    if v == U16_INVALID:
        return None
    name = HEATER_LAW_NAMES.get(v & 0xFF, "LAW%d" % (v & 0xFF))
    return name + ("+UNREACHABLE" if v & 0x0100 else "")


def poll(bus, want_diag):
    row = decode_primary(bus.read(PRIMARY_BASE, PRIMARY_COUNT))
    if want_diag:
        row.update(decode_diag(bus.read(DIAG_BASE, DIAG_COUNT)))
        # HEATER_LAW exists from FW 0x0018. On older firmware the address is
        # ILLEGAL, so it is read only when the image says it has it, and on
        # its own: one refused read must not cost the whole row. A failed read
        # is recorded as EMPTY with the reason in `detail`, never as a law.
        row["heater_law"] = None
        try:
            fw = int(row.get("fw") or "0", 16)
        except ValueError:
            fw = 0
        if fw >= 0x0018:
            try:
                row["heater_law"] = decode_heater_law(
                    bus.read(HEATER_LAW_ADDR, 1)[0])
            except Exception as exc:        # noqa: BLE001 - any bus failure
                row["heater_law"] = None
                row["heater_law_error"] = str(exc)[:80]
    row["status"] = "ok"
    row["detail"] = ("heater_law read failed: %s" % row["heater_law_error"]
                     if row.get("heater_law_error") else "")
    return row


# --------------------------------------------------------------------------

def fmt(v, unit="", places=2):
    if v is None:
        return "invalid"
    if isinstance(v, float):
        return ("%%.%df%%s" % places) % (v, unit)
    return "%s%s" % (v, unit)


def show(row):
    if row["status"] != "ok":
        print("  !! %s: %s" % (row["status"], row["detail"]))
        return
    trust = "" if row["o2_trusted"] else "   <- NOT TRUSTWORTHY, see faults"
    print("  O2 (dry)      %s%s" % (fmt(row["o2_comp_pct"], " %vol"), trust))
    print("  cell current  %s" % fmt(row["o2_raw_ua"], " uA"))
    print("  tip / chamber %s / %s"
          % (fmt(row["t_tip_c"], " C"), fmt(row["t_chamber_c"], " C")))
    print("  humidity      %s" % fmt(row["rh_pct"], " %RH"))
    print("  heater duty   %s" % fmt(row["heater_duty_pct"], " %"))
    print("  settling      %s" % ("settled" if row["settle_s"] == 0
                                  else "%d s remaining" % row["settle_s"]))
    print("  faults        0x%04X%s"
          % (row["faults"],
             "  " + row["faults_named"] if row["faults_named"] else "  none"))
    # Every row is pre-filled with empty strings for the CSV writer, so
    # presence of the key proves nothing - the VALUE is what says whether the
    # diagnostic block was actually read.
    if row.get("vref_mv", "") != "":
        print("  rails         VREF %s  VA %s  VIN %s  AFE %s"
              % tuple(fmt(row[k], " mV", 0) if row[k] is not None else "invalid"
                      for k in ("vref_mv", "va_mv", "vin_mv", "afe_mv")))
        print("  dew margin    %s" % fmt(row["dew_margin_k"], " K"))
        print("  die temp      %s" % fmt(row["t_die_c"], " C"))
        print("  AFE temp      %s" % fmt(row.get("t_afe_c"), " C"))
        if row.get("t_ext_c") is not None:
            print("  ext temp      %s" % fmt(row["t_ext_c"], " C"))
        print("  uptime        %d s   seq %d   fw %s hw %s"
              % (row["uptime_s"], row["sample_seq"], row["fw"], row["hw"]))
        print("  errors        crc %d  frame %d  i2c %d  ads_fail %d  "
              "settle_restarts %d"
              % (row["mb_crc_errs"], row["mb_frame_errs"], row["i2c_errs"],
                 row["ads_fail_count"], row["settle_restarts"]))
        print("  faults ever   0x%04X%s"
              % (row["faults_ever"],
                 "  " + row["faults_ever_named"] if row["faults_ever_named"]
                 else "  none"))


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv", nargs="?", help="output CSV; appends if it exists")
    ap.add_argument("--port", required=True,
                    help="serial line: a USB-RS485 dongle, or a USB-TTL lead "
                         "into a board flashed -e bridge")
    ap.add_argument("--addr", type=int, default=3,
                    help="the PROBE's Modbus address (default 3). The bridge "
                         "is transparent; do not address it here.")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="E", choices=["N", "E", "O"])
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--retries", type=int, default=2,
                    help="retries per poll before the row is marked failed")
    def nonneg(v):
        n = int(v)
        if n < 0:
            # The trigger is `consecutive % N == 0`, under which -12 behaves as
            # 12 and -1 reopens after every single failure. Accidental
            # semantics, not a feature.
            raise argparse.ArgumentTypeError(
                "--reopen-after must be >= 0 (0 disables); got %d" % n)
        return n
    ap.add_argument("--reopen-after", type=nonneg, default=12, metavar="N",
                    help="reopen the serial link after N consecutive failed "
                         "polls (0 disables). A handle can wedge while the "
                         "device is fine: on 2026-09-07 a session held for 14 h "
                         "read 0 bytes for 12 min while the probe kept "
                         "sampling and answered a fresh session instantly. "
                         "Reopening does NOT mark anything ok - failed rows "
                         "stay failed, and the reopen is recorded in `detail`.")
    ap.add_argument("--diag", action="store_true",
                    help="also read the diagnostic block at 0x0010")
    ap.add_argument("--count", type=int, default=1,
                    help="number of polls (0 = forever)")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the startup check against src/regmap.h")
    args = ap.parse_args()

    if not args.no_check:
        problems = check_against_source()
        if problems:
            sys.exit("!! this tool's register map disagrees with src/:\n   "
                     + "\n   ".join(problems)
                     + "\n   Fix the tool, or --no-check if you know better.")

    if args.diag:
        # 21 registers plus overhead is well inside a 256-byte ADU, but say so
        # rather than discovering it on a long cable.
        assert DIAG_COUNT * 2 + 5 < 256

    link = SerialLink(args.port, args.baud, args.parity, args.timeout)
    bus = Bus(link, args.addr)

    writer = fh = None
    if args.csv:
        exists = os.path.exists(args.csv) and os.path.getsize(args.csv) > 0
        fh = open(args.csv, "a", buffering=1, newline="")
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()

    failures = 0
    consecutive = 0
    n = 0
    try:
        while args.count == 0 or n < args.count:
            n += 1
            stamp = utc_stamp()
            row = {c: "" for c in CSV_COLUMNS}
            row["utc"] = stamp
            last = None
            for attempt in range(args.retries + 1):
                try:
                    row.update(poll(bus, args.diag))
                    last = None
                    break
                except ModbusException as exc:
                    last = "modbus exception %d (%s)" % (exc.code, exc)
                except (IOError, OSError) as exc:
                    last = "%s: %s" % (type(exc).__name__, exc)
                if attempt < args.retries:
                    time.sleep(0.2)
            if last is not None:
                failures += 1
                consecutive += 1
                row["status"], row["detail"] = "failed", last
                if args.reopen_after and consecutive % args.reopen_after == 0:
                    # The link, not the transaction. Never changes this row's
                    # verdict: a dead device keeps failing after a reopen, which
                    # is the point - this must not become a way to launder a
                    # real fault into silence.
                    try:
                        link.close()
                    except Exception:
                        pass
                    try:
                        link = SerialLink(args.port, args.baud, args.parity,
                                          args.timeout)
                        bus = Bus(link, args.addr)
                        note = "reopened link after %d consecutive failures" % consecutive
                    except Exception as exc:
                        note = "reopen FAILED after %d: %s" % (consecutive, exc)
                    row["detail"] = "%s; %s" % (last, note)
                    print("!! " + note)
            else:
                consecutive = 0
            print("%s  addr %d" % (stamp, args.addr))
            show(row)
            if writer:
                writer.writerow(row)
            if args.count == 0 or n < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        link.close()
        if fh:
            fh.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
