#!/usr/bin/env python3
"""Capture the o2-probe live snapshot over SWD to CSV, for plotting.

Bring-up needs a time series the bench can plot - cell polarisation takes tens
of minutes, and the interesting failures are shapes, not single readings. The
2026-09-04 session lost that twice: once by logging into a per-session scratch
directory that vanished, and once by reading a saturated converter for six
minutes and calling it "steady" when the value was simply above full scale.

So this writes to a real file, and it refuses to write a number it cannot
justify:

  * The regmap address is resolved from the ELF symbol `g_rm`, not hardcoded.
    A rebuild moves it, and a stale address decodes to plausible garbage.
  * Every sample is sanity-checked before it is written. A failed probe emits
    an explicit `status=failed` row - never a silent gap, and never a stale
    value carried forward.
  * Sentinel readings (the firmware's 0xFFFF / 0x8000 "do not trust me")
    become empty CSV cells, so a plot shows a hole rather than 65535.
  * `afe_rail` flags a converter within 50 mV of either supply rail, because a
    saturated TIA reports the same value however the current moves.

    python3 tools/o2p_capture.py out.csv --count 240 --interval 30
    python3 tools/o2p_capture.py --once            # one row to stdout

Defaults are 120 samples at 30 s, i.e. one hour. Each sample spawns its own
OpenOCD, so a long capture is a detached process, not a foreground one - an
agent harness will cut a foreground call off at ten minutes and the run dies
with it. The CSV is line-buffered and appended per sample, so an interrupted
run keeps everything up to the interruption.

Pick the probe when more than one is attached, with EITHER of two selectors:

  * `--adapter-serial` / `O2P_ADAPTER_SERIAL` - matches the USB iSerial, so it
    can only name a probe that has one. `adapter usb location` is not an
    alternative: the xPack cmsis-dap driver accepts and silently ignores it
    (a deliberately bogus `9-9` still connects).
  * `--adapter-backend` / `O2P_ADAPTER_BACKEND` - the XIAO Debug Mate is
    HID-only and publishes no iSerial at all, so `--adapter-serial` cannot
    name it, but `--adapter-backend hid` selects it whenever the other probe
    speaks usb_bulk. `auto` fails on it outright with "unable to open
    CMSIS-DAP device 0xd28:0x204", which reads like no probe is attached when
    one is attached and working.

The backend only discriminates when the probes differ in one. If they do not,
unplugging is still the answer.

Two ways the address goes wrong, with different remedies:

  * `regmap reads all zero` - the dump succeeded but there is no g_rm there.
    Usually OpenOCD attached to the wrong board; see --adapter-serial above.
  * `live index N not 0/1` - the ELF is NEWER than the image on the board. The
    symbol resolves correctly, against a build the board is not running, and
    the decode is garbage. Either flash the board, or pass `--addr` with the
    running build's g_rm (0x200000F0 for the 2026-09-04 image; `git stash` the
    firmware tree and rebuild if you need to recover an older one).

Layout mirrors `o2p_snapshot_t` in src/regmap.h. If that struct changes, the
offsets below must change with it; the sanity check will usually catch it.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.dirname(HERE)

DEFAULT_ELF = os.path.join(FIRMWARE, ".pio", "build", "o2probe", "firmware.elf")
FALLBACK_ADDR = 0x200000F0        # 2026-09-04 build; only used if no ELF
# o2p_snapshot_t aligns to 4 (uptime_s is a uint32_t), so sizeof is 56 for 54
# bytes of fields - the padding is easy to forget and produces a decode that is
# wrong from `live` onward. Then buf[2], the 1-byte live index padded up to
# o2p_config_t's alignment, the config, four flags, a pointer.
#
# DO NOT hand-compute these when the struct changes. This file already caused
# one false emergency by decoding a healthy dump with a stale layout after
# t_die was appended: uptime appeared to count backwards, VREF read 32769 and
# the rail looked like it was collapsing.
#
# And DO NOT take the numbers from a host compile of regmap.h either. That was
# tried on 2026-09-05 and gave REGMAP_LEN 160 where the ARM build says 152:
# o2p_regmap_t holds a pointer, 8 bytes on the x86-64 host and 4 on the
# target. SNAPSHOT_LEN happens to agree at 56 because the snapshot is all
# fixed-width integers - which makes the host compile look trustworthy right
# up until it is not. Read the TARGET ELF:
#
#     arm-none-eabi-gdb -batch -ex 'p sizeof(o2p_snapshot_t)' firmware.elf
#
# The g_rm symbol size is checked against REGMAP_LEN at startup, which caught
# exactly the host-vs-target mistake above on its first run.
#
# The `live not in (0, 1)` and VREF plausibility checks below are a backstop,
# NOT a guarantee. A peer session's 12 h capture proved it on 2026-09-05: with
# a stale 52-byte layout the VREF check rejected one sample and passed the
# next, which reached the CSV as status=ok carrying uptime 215547903 and
# faults 0xffff. A wrong layout can land a plausible value in the very field
# being checked.
SNAPSHOT_LEN = 56
LIVE_OFF = 2 * SNAPSHOT_LEN
# 0x98 -> 0xa0 on 2026-09-07 with dil_alpha_x1000: o2p_config_t went 32 -> 36
# bytes and g_rm rounded up with it. Taken from the ARM ELF, as the note above
# insists - `arm-none-eabi-nm -S firmware.elf | grep g_rm` says 000000a0 - and
# NOT from the +4 the source diff suggests, which would have been 0x9c and
# wrong. SNAPSHOT_LEN is untouched: o2p_snapshot_t did not change.
REGMAP_LEN = 0xa0

U16_INVALID = 0xFFFF
I16_INVALID = -0x8000

# Defaults match O2P_LMP_INT_Z_NUM/DEN and O2P_LMP_TIA_OHM in the firmware.
INT_Z_FRACTION = 67.0 / 100.0
TIA_OHM = 7000.0

COLUMNS = [
    "iso_time", "status", "uptime_s", "seq", "vref_mv", "va_mv", "vin_mv",
    "afe_mv", "afe_rail", "cell_ua", "o2_raw_ua", "o2_comp_pct",
    "t_tip_c", "t_chamber_c", "t_die_c", "rh_pct", "dew_margin_c",
    "heater_duty_pct", "pressure_hpa", "faults", "faults_ever", "ads_fails",
    "settle_s", "i2c_errs", "lmp_readback",
]


def elf_symbol(path, name):
    """(address, size) of `name` in a little-endian 32-bit ELF, or (None, None).

    Reads the symbol table directly so the tool does not depend on an ARM
    toolchain being installed just to look up one address.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, None
    if data[:4] != b"\x7fELF" or data[4] != 1:            # 32-bit only
        return None, None
    e_shoff, = struct.unpack_from("<I", data, 0x20)
    e_shentsize, e_shnum, _ = struct.unpack_from("<HHH", data, 0x2E)
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        s_type, = struct.unpack_from("<I", data, off + 4)
        s_off, s_size, s_link = struct.unpack_from("<III", data, off + 0x10)
        s_entsize, = struct.unpack_from("<I", data, off + 0x24)
        sections.append((s_type, s_off, s_size, s_link, s_entsize))
    for s_type, s_off, s_size, s_link, s_entsize in sections:
        if s_type != 2 or not s_entsize:                  # SHT_SYMTAB
            continue
        str_off = sections[s_link][1]
        for j in range(s_size // s_entsize):
            off = s_off + j * s_entsize
            n_off, value, size = struct.unpack_from("<III", data, off)
            end = data.index(b"\0", str_off + n_off)
            if data[str_off + n_off:end].decode("ascii", "replace") == name:
                return value, size
    return None, None


def read_regmap(addr, openocd, scripts, interface, target,
                adapter_serial=None, backend=None):
    """Halt the target, dump the regmap, resume. Returns bytes or None."""
    tmp = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
    tmp.close()
    cmd = [
        openocd, "-s", scripts,
        "-f", interface,
    ]
    # With more than one CMSIS-DAP probe attached, OpenOCD binds to whichever
    # it enumerates first - so an unqualified capture can silently read a
    # DIFFERENT board and report its memory as this probe's regmap. The serial
    # must follow the interface file, which is what selects the adapter
    # driver. On 2026-09-05 the bench had two probes on the bus (CMSIS_DAP and
    # DAPLINK-S3-2) and one of them was running a bridge image, not this one.
    if backend:
        # The two probes on this bench are not interchangeable at the USB
        # level: the bench DAPLink speaks usb_bulk, the Debug Mate speaks HID
        # only. `auto` picks usb_bulk first and fails outright on the Debug
        # Mate with "unable to open CMSIS-DAP device 0xd28:0x204", so the
        # backend is both a fix and, incidentally, a probe selector.
        cmd += ["-c", "cmsis-dap backend %s" % backend]
    if adapter_serial:
        cmd += ["-c", "adapter serial %s" % adapter_serial]
    cmd += [
        "-f", target,
        "-c", "transport select swd; init; halt; "
              f"dump_image {tmp.name} 0x{addr:08x} 0x{REGMAP_LEN:x}; "
              "resume; exit",
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60, check=False)
        with open(tmp.name, "rb") as fh:
            blob = fh.read()
    except (OSError, subprocess.SubprocessError):
        blob = b""
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return blob if len(blob) >= REGMAP_LEN else None


def decode(blob, int_z, tia_ohm, va_rail_mv):
    """Decode one snapshot. Returns (row_dict, error_or_None).

    A decode that cannot be justified returns an error rather than a row: a
    wrong regmap address produces numbers that look like data, and the whole
    point of this tool is that a bad probe never masquerades as a measurement.
    """
    live = blob[LIVE_OFF]
    if live not in (0, 1):
        return None, f"live index {live} not 0/1 - wrong address?"
    b = blob[live * SNAPSHOT_LEN:(live + 1) * SNAPSHOT_LEN]

    o2_comp, o2_raw, t_tip, t_cham, rh, heater = struct.unpack_from("<HhhhHH", b, 0)
    faults, settle = struct.unpack_from("<HH", b, 12)
    vref, va, vin, afe = struct.unpack_from("<HHHH", b, 16)
    dew, pressure = struct.unpack_from("<hH", b, 24)
    uptime, = struct.unpack_from("<I", b, 28)
    lmp_rb, = struct.unpack_from("<H", b, 34)
    i2c_errs, = struct.unpack_from("<H", b, 40)
    seq, = struct.unpack_from("<H", b, 46)
    t_die, = struct.unpack_from("<h", b, 48)
    faults_ever, ads_fails = struct.unpack_from("<HH", b, 50)

    # Two very different things used to land here together.
    #
    # 0xFFFF is the firmware's SENTINEL: it is telling us it could not measure
    # the reference this cycle, which is an honest answer, and the fault word
    # in the same snapshot says why. Refusing the whole row then throws away
    # `faults`, `faults_ever` and `ads_fails` - exactly the registers that
    # explain the failure - and reports only "dead AFE", which is a guess.
    # Observed 2026-09-05 while deliberately breaking DRDY: the tool could say
    # nothing about a fault the firmware had diagnosed precisely.
    #
    # Any OTHER implausible value is not a sentinel and not a measurement; it
    # is a decode that has gone wrong - a stale struct layout or a bad address
    # - and there the whole row really is worthless.
    if vref != U16_INVALID and not 1500 <= vref <= 3300:
        return None, f"VREF {vref} mV implausible - wrong address or stale layout"

    if vref == U16_INVALID:
        cell = None                    # no reference, so no current to derive
    else:
        zero = vref * int_z
        cell = ((zero - afe) / (tia_ohm / 1000.0)
                if afe != U16_INVALID else None)

    def mv(x):
        return "" if x == U16_INVALID else x

    def c100(x):
        return "" if x == I16_INVALID else f"{x / 100.0:.2f}"

    # A converter can be pinned without going anywhere near a SUPPLY rail.
    # The ADS1119 converts AFE_VOUT against the external reference, so its
    # full scale is VREF - measured at 2492 mV, a full 800 mV below VA. The
    # original test only looked at 0 V and VA, and on 2026-09-05 a GAIN=4
    # fault injection pinned the channel at +32767 (afe_mv 2491) while this
    # column dutifully reported afe_rail=0 and printed a cell current of
    # -117.34 uA. That is the same class of mistake as reading a saturated
    # TIA as a steady 607 uA, which is the incident this tool exists to
    # prevent - so the converter's own full scale counts as a rail here.
    rail = ""
    clipped = False
    if afe != U16_INVALID:
        clipped = (afe <= 50 or afe >= va_rail_mv - 50)
        if vref != U16_INVALID and afe >= float(vref) - 5:
            clipped = True
        rail = "1" if clipped else "0"

    # A pinned conversion cannot say what the current was, so do not publish a
    # number derived from it. The firmware already withholds o2_raw_ua via
    # O2P_F_ADC_RANGE; cell_ua is this tool's own derivation and was still
    # being printed.
    if clipped:
        cell = None

    return {
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "ok",
        "uptime_s": uptime,
        "seq": seq,
        "vref_mv": mv(vref),   # blank on the sentinel, never 65535
        "va_mv": mv(va),
        "vin_mv": mv(vin),
        "afe_mv": mv(afe),
        "afe_rail": rail,
        "cell_ua": "" if cell is None else f"{cell:.2f}",
        "o2_raw_ua": "" if o2_raw == I16_INVALID else f"{o2_raw / 100.0:.2f}",
        "o2_comp_pct": "" if o2_comp == U16_INVALID else f"{o2_comp / 100.0:.2f}",
        "t_tip_c": c100(t_tip),
        "t_chamber_c": c100(t_cham),
        "t_die_c": c100(t_die),
        "rh_pct": "" if rh == U16_INVALID else f"{rh / 100.0:.2f}",
        "dew_margin_c": c100(dew),
        "heater_duty_pct": "" if heater == U16_INVALID else f"{heater / 100.0:.2f}",
        "pressure_hpa": "" if pressure == U16_INVALID else pressure,
        "faults": f"0x{faults:04x}",
        "faults_ever": f"0x{faults_ever:04x}",
        "ads_fails": ads_fails,
        "settle_s": settle,
        "i2c_errs": i2c_errs,
        "lmp_readback": f"0x{lmp_rb:04x}",
    }, None


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv", nargs="?", help="output CSV; appends if it exists")
    ap.add_argument("--once", action="store_true", help="one sample to stdout")
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--elf", default=DEFAULT_ELF)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=None,
                    help="regmap address; overrides the ELF symbol")
    ap.add_argument("--tia-ohm", type=float, default=TIA_OHM)
    ap.add_argument("--int-z", type=float, default=INT_Z_FRACTION)
    ap.add_argument("--va-rail-mv", type=float, default=3300.0)
    ap.add_argument("--openocd",
                    default=os.path.expanduser(
                        "~/.platformio/packages/tool-openocd/bin/openocd"))
    ap.add_argument("--scripts",
                    default=os.path.expanduser(
                        "~/.platformio/packages/tool-openocd/openocd/scripts"))
    ap.add_argument("--interface", default="interface/cmsis-dap.cfg")
    ap.add_argument("--adapter-backend",
                    default=os.environ.get("O2P_ADAPTER_BACKEND"),
                    choices=[None, "hid", "usb_bulk", "tcp", "auto"],
                    help="CMSIS-DAP backend (env O2P_ADAPTER_BACKEND). The "
                         "Debug Mate needs 'hid'; auto fails on it.")
    ap.add_argument("--adapter-serial",
                    default=os.environ.get("O2P_ADAPTER_SERIAL"),
                    help="CMSIS-DAP serial to bind to (env "
                         "O2P_ADAPTER_SERIAL). Required in spirit whenever "
                         "more than one probe is attached; without it "
                         "OpenOCD takes the first it finds.")
    ap.add_argument("--target", default="target/stm32g0x.cfg")
    args = ap.parse_args()

    if not args.once and not args.csv:
        ap.error("give a CSV path, or --once")

    addr = args.addr
    source = "--addr"
    sym_size = None
    if addr is None:
        addr, sym_size = elf_symbol(args.elf, "g_rm")
        source = f"ELF symbol g_rm in {os.path.relpath(args.elf, FIRMWARE)}"

    # The offsets below are hardcoded, so this file has a layout ASSUMPTION
    # about a struct that lives in another repository file and changes without
    # it. The ELF settles the question: sizeof(g_rm) is recorded in the symbol
    # table, so a mismatch means this tool is stale, full stop - no heuristic
    # needed and no judgement call.
    #
    # This exists because the heuristics were demonstrably not enough. On
    # 2026-09-05 a long-running capture whose process image predated a rebuild
    # kept decoding a 56-byte struct as 52 bytes; the VREF plausibility check
    # rejected one sample and PASSED the next, which reached the CSV as
    # status=ok with uptime 215547903 and faults 0xffff. A wrong layout can
    # put a plausible number in the one field being sanity-checked. Refuse the
    # run rather than write rows that parse.
    if sym_size and sym_size != REGMAP_LEN:
        sys.exit(f"o2p_capture.py is stale: g_rm is {sym_size} bytes in "
                 f"{os.path.relpath(args.elf, FIRMWARE)} but this tool assumes "
                 f"{REGMAP_LEN}. The snapshot layout changed. Update "
                 f"SNAPSHOT_LEN, REGMAP_LEN and the offsets in decode() - get "
                 f"them from the compiler, not by counting bytes.")

    if addr is None:
        addr = FALLBACK_ADDR
        source = "FALLBACK (no ELF found - rebuild may have moved it)"
        print(f"warning: {source}", file=sys.stderr)
    print(f"regmap at 0x{addr:08x}  ({source})", file=sys.stderr)

    fh = None
    if args.csv:
        fresh = not os.path.exists(args.csv)
        if not fresh:
            # Appending rows of a different shape under an existing header
            # yields a file that still parses and is silently wrong from the
            # join onward. Refuse instead, and say what to do about it.
            with open(args.csv) as old:
                header = old.readline().strip()
            if header and header != ",".join(COLUMNS):
                print(f"error: {args.csv} has a different column set.\n"
                      f"  file: {header}\n"
                      f"  tool: {','.join(COLUMNS)}\n"
                      "Rename the old file and start a new one.",
                      file=sys.stderr)
                return 2
        fh = open(args.csv, "a", buffering=1)
        if fresh:
            fh.write(",".join(COLUMNS) + "\n")

    n = 1 if args.once else args.count
    for i in range(n):
        blob = read_regmap(addr, args.openocd, args.scripts,
                           args.interface, args.target,
                           args.adapter_serial, args.adapter_backend)
        if blob is None:
            row, err = None, "SWD read failed"
        elif not any(blob):
            # A regmap of all zeros is not a reading, and it is not a dead
            # link either - the dump succeeded. It means the address holds no
            # g_rm: OpenOCD attached to a board running a different image.
            # With two CMSIS-DAP probes on the bus that is the likeliest
            # cause. Select with --adapter-serial where the probe has a USB
            # iSerial, or --adapter-backend where it does not.
            row, err = None, ("regmap reads all zero: wrong board "
                              "(is --adapter-serial or --adapter-backend "
                              "set?) or a stale --addr")
        else:
            row, err = decode(blob, args.int_z, args.tia_ohm, args.va_rail_mv)
        if row is None:
            row = {c: "" for c in COLUMNS}
            row["iso_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            row["status"] = f"failed: {err}"
        line = ",".join(str(row[c]) for c in COLUMNS)
        if fh:
            fh.write(line + "\n")
        print(line)
        if i + 1 < n:
            time.sleep(args.interval)

    if fh:
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
