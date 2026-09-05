#!/usr/bin/env python3
"""Long-running wrapper around o2p_capture.py --once, safe across a rebuild.

`o2p_capture.py --count N` resolves the regmap address ONCE and holds the
snapshot layout (SNAPSHOT_LEN, REGMAP_LEN) in its process image for the whole
run. That is fine for an hour on a quiet bench and wrong for twelve hours on a
shared one: if anybody rebuilds the firmware mid-run, the running process keeps
decoding the new struct with the old layout and cannot know it.

Measured 2026-09-05, and the reason this file exists. A capture started at
09:06 against a 52-byte o2p_snapshot_t was still running at 09:36 when a peer
session appended `t_die` (52 -> 56 bytes), moved `g_rm` to 0x20000100 and
reflashed. The VREF plausibility check caught the first bad sample and MISSED
the next one, which went into the CSV as:

    2026-09-05T09:36:31,ok,215547903,2470,0,236.41,0.00,0xffff

Status `ok`, uptime 215547903 s, every fault bit set. A row like that is worse
than a gap, because a gap cannot be plotted.

So this samples by SPAWNING o2p_capture.py --once per sample. A fresh process
re-imports the module and re-reads the ELF every time, so an edit to either the
firmware or the tool is picked up on the next sample rather than never:

  * a rebuild that moves `g_rm` -> the new address, from the new ELF;
  * a rebuild that changes the struct -> the new layout constants;
  * a rebuild the board has not been flashed with yet -> an explicit `failed`
    row from the tool's own `live index` check, which is the honest answer;
  * a change to the COLUMN SET -> a new output file, see below. Appending rows
    of a different shape under an existing header yields a file that still
    parses and is silently wrong from the join onward.

The cost is one process spawn per sample. At a 30 s interval that is noise.

    python3 tools/o2p_capture_loop.py out.csv --count 540 --interval 30
    python3 tools/o2p_capture_loop.py out.csv --count 540 -- --adapter-backend hid

Everything after a bare `--` is passed through to o2p_capture.py untouched.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE = os.path.join(HERE, "o2p_capture.py")

# Generous: o2p_capture's own OpenOCD timeout is 60 s, and a sample that is
# merely slow must not be recorded as a failure.
SAMPLE_TIMEOUT_S = 120


def current_columns():
    """The tool's COLUMNS *as it exists on disk right now*, or None.

    Imported in a subprocess on purpose. Importing it here would cache the
    module for the life of this process and reintroduce exactly the staleness
    this file exists to avoid.
    """
    try:
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); "
             "import o2p_capture; print(','.join(o2p_capture.COLUMNS))" % HERE],
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    line = out.stdout.strip()
    return line or None


def one_sample(passthrough):
    """(row, error). row is a CSV line; error is set when we made it up."""
    cmd = [sys.executable, CAPTURE, "--once"] + passthrough
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=SAMPLE_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return None, f"capture did not return within {SAMPLE_TIMEOUT_S}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not run capture: {exc}"
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    if not lines:
        tail = (out.stderr or "").strip().splitlines()
        why = tail[-1] if tail else f"exit {out.returncode}, no output"
        return None, f"capture produced no row ({why})"
    return lines[-1], None


def failed_row(ncols, why):
    """A row of the right shape saying, explicitly, that we have nothing."""
    cells = [""] * ncols
    cells[0] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if ncols > 1:
        cells[1] = f"failed: {why}"
    return ",".join(cells)


def roll_path(path, n):
    base, ext = os.path.splitext(path)
    return f"{base}.{n}{ext or '.csv'}"


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv", help="output CSV; appends if it exists")
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("passthrough", nargs="*",
                    help="args for o2p_capture.py, after a bare --")
    args = ap.parse_args()

    path = args.csv
    header = None
    if os.path.exists(path):
        with open(path) as fh:
            header = fh.readline().strip() or None

    # Absolute schedule, so a slow sample does not push every later one late.
    t0 = time.monotonic()
    for i in range(args.count):
        cols = current_columns()
        if cols is None:
            # We could not even ask what shape a row is. Do not guess one.
            print("warning: could not read COLUMNS from the tool; skipping",
                  file=sys.stderr)
        else:
            if header is None:
                header = cols
                with open(path, "a", buffering=1) as fh:
                    fh.write(header + "\n")
            elif cols != header:
                # The column set changed under us. Never append the new shape
                # under the old header - start a new file and say so loudly.
                n = 2
                while os.path.exists(roll_path(path, n)):
                    n += 1
                new = roll_path(path, n)
                print(f"COLUMN SET CHANGED - rolling to {new}\n"
                      f"  was: {header}\n  now: {cols}", file=sys.stderr)
                path, header = new, cols
                with open(path, "a", buffering=1) as fh:
                    fh.write(header + "\n")

            row, err = one_sample(args.passthrough)
            if row is None:
                row = failed_row(len(header.split(",")), err)
            elif len(row.split(",")) != len(header.split(",")):
                # The tool answered in a shape that is not this file's. Record
                # the mismatch rather than the row.
                row = failed_row(len(header.split(",")),
                                 f"row has {len(row.split(','))} fields, "
                                 f"header has {len(header.split(','))}")
            with open(path, "a", buffering=1) as fh:
                fh.write(row + "\n")
            print(row, flush=True)

        if i + 1 < args.count:
            nxt = t0 + (i + 1) * args.interval
            time.sleep(max(0.0, nxt - time.monotonic()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
