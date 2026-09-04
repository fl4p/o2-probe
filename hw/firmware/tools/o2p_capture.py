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
REGMAP_LEN = 0x88
SNAPSHOT_LEN = 48

U16_INVALID = 0xFFFF
I16_INVALID = -0x8000

# Defaults match O2P_LMP_INT_Z_NUM/DEN and O2P_LMP_TIA_OHM in the firmware.
INT_Z_FRACTION = 67.0 / 100.0
TIA_OHM = 7000.0

COLUMNS = [
    "iso_time", "status", "uptime_s", "seq", "vref_mv", "va_mv", "vin_mv",
    "afe_mv", "afe_rail", "cell_ua", "o2_raw_ua", "o2_comp_pct",
    "t_tip_c", "t_chamber_c", "rh_pct", "dew_margin_c", "heater_duty_pct",
    "pressure_hpa", "faults", "settle_s", "i2c_errs", "lmp_readback",
]


def elf_symbol(path, name):
    """Address of `name` in a little-endian 32-bit ELF, or None.

    Reads the symbol table directly so the tool does not depend on an ARM
    toolchain being installed just to look up one address.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if data[:4] != b"\x7fELF" or data[4] != 1:            # 32-bit only
        return None
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
            n_off, value = struct.unpack_from("<II", data, off)
            end = data.index(b"\0", str_off + n_off)
            if data[str_off + n_off:end].decode("ascii", "replace") == name:
                return value
    return None


def read_regmap(addr, openocd, scripts, interface, target):
    """Halt the target, dump the regmap, resume. Returns bytes or None."""
    tmp = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
    tmp.close()
    cmd = [
        openocd, "-s", scripts,
        "-f", interface, "-f", target,
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
    live = blob[96]
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

    if not 1500 <= vref <= 3300:
        return None, f"VREF {vref} mV implausible - wrong address or dead AFE"

    zero = vref * int_z
    cell = (zero - afe) / (tia_ohm / 1000.0) if afe != U16_INVALID else None

    def mv(x):
        return "" if x == U16_INVALID else x

    def c100(x):
        return "" if x == I16_INVALID else f"{x / 100.0:.2f}"

    rail = ""
    if afe != U16_INVALID:
        rail = "1" if (afe <= 50 or afe >= va_rail_mv - 50) else "0"

    return {
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "ok",
        "uptime_s": uptime,
        "seq": seq,
        "vref_mv": vref,
        "va_mv": mv(va),
        "vin_mv": mv(vin),
        "afe_mv": mv(afe),
        "afe_rail": rail,
        "cell_ua": "" if cell is None else f"{cell:.2f}",
        "o2_raw_ua": "" if o2_raw == I16_INVALID else f"{o2_raw / 100.0:.2f}",
        "o2_comp_pct": "" if o2_comp == U16_INVALID else f"{o2_comp / 100.0:.2f}",
        "t_tip_c": c100(t_tip),
        "t_chamber_c": c100(t_cham),
        "rh_pct": "" if rh == U16_INVALID else f"{rh / 100.0:.2f}",
        "dew_margin_c": c100(dew),
        "heater_duty_pct": "" if heater == U16_INVALID else f"{heater / 100.0:.2f}",
        "pressure_hpa": "" if pressure == U16_INVALID else pressure,
        "faults": f"0x{faults:04x}",
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
    ap.add_argument("--target", default="target/stm32g0x.cfg")
    args = ap.parse_args()

    if not args.once and not args.csv:
        ap.error("give a CSV path, or --once")

    addr = args.addr
    source = "--addr"
    if addr is None:
        addr = elf_symbol(args.elf, "g_rm")
        source = f"ELF symbol g_rm in {os.path.relpath(args.elf, FIRMWARE)}"
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
                           args.interface, args.target)
        if blob is None:
            row, err = None, "SWD read failed"
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
