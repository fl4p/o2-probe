#!/usr/bin/env python3
"""Plot o2p_capture.py CSVs (and the older ad-hoc .log traces) to a PNG.

Railed samples are drawn as open markers at the clip level, never as a value:
during the 2026-09-04 polarisation the TIA output sat against its rail at every
gain, so the recorded "236 uA" was only ever a lower bound.

    python3 plot_capture.py out.webp
"""
import csv
import datetime as dt
import glob
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402
import matplotlib.dates as mdates                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = dt.date(2026, 9, 4)

# Stored air point (2026-09-04) and the firmware's own constants, so the
# derived curve is the same arithmetic the probe does, not an approximation:
#   K = cal_air_na / O2P_LN_AIR ;  C = 1 - exp(-S/K)      (o2.c:47-61)
# tempco_ppm_per_k defaults to 0 - SGX publishes no curve for this part.
CAL_AIR_NA = 100026.0
LN_AIR = 0.23503902


def derived_pct(cell_ua):
    if cell_ua is None:
        return None
    k = CAL_AIR_NA / LN_AIR
    return 100.0 * (1.0 - math.exp(-(cell_ua * 1000.0) / k))

LOG_RE = re.compile(
    r"^(\d\d:\d\d:\d\d)\s+up\s*(\d+)s.*?AFE\s*(\d+) mV\s+cell\s*(-?[\d.]+) uA.*?F (0x[0-9a-f]+)")


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "*.csv"))):
        with open(path) as fh:
            for r in csv.DictReader(fh):
                if r.get("status") != "ok":
                    continue
                t = r.get("iso_time")
                if not t:
                    continue
                rows.append(dict(
                    t=dt.datetime.fromisoformat(t),
                    cell=f(r.get("cell_ua")), comp=f(r.get("o2_comp_pct")),
                    tip=f(r.get("t_tip_c")), cham=f(r.get("t_chamber_c")),
                    rh=f(r.get("rh_pct")), dew=f(r.get("dew_margin_c")),
                    die=f(r.get("t_die_c")),
                    afe=f(r.get("afe_mv")),
                    deriv=derived_pct(f(r.get("cell_ua"))),
                    railed=(r.get("afe_rail") == "1"),
                    src="csv"))
    for path in sorted(glob.glob(os.path.join(HERE, "**", "*.log"),
                                 recursive=True)):
        if os.path.basename(path) in ("codex.log", "chrome.log"):
            continue
        with open(path, errors="replace") as fh:
            for line in fh:
                m = LOG_RE.match(line.strip())
                if not m:
                    continue
                hh, mm, ss = (int(x) for x in m.group(1).split(":"))
                afe = float(m.group(3))
                rows.append(dict(
                    t=dt.datetime.combine(DAY, dt.time(hh, mm, ss)),
                    cell=float(m.group(4)), comp=None, tip=None, cham=None,
                    rh=None, dew=None, die=None, afe=afe, deriv=None,
                    railed=(afe <= 50 or afe >= 3250), src="log"))
    rows.sort(key=lambda r: r["t"])
    return rows


GAP = dt.timedelta(minutes=3)


def series(rows, key, railed=None):
    """Points for `key`, with NaN inserted across sampling gaps.

    The bench was unpowered, reworked, or simply not logging for long stretches
    of this session. Joining across those gaps draws a line through time when
    nothing was measured - so break it instead.
    """
    out = [(r["t"], r[key]) for r in rows
           if r[key] is not None and (railed is None or r["railed"] == railed)]
    xs, ys = [], []
    for i, (t, v) in enumerate(out):
        if i and t - out[i - 1][0] > GAP:
            xs.append(out[i - 1][0] + GAP / 2)
            ys.append(float("nan"))
        xs.append(t)
        ys.append(v)
    return xs, ys


def main():
    args = [a for a in sys.argv[1:]]
    since = None
    if "--since" in args:
        i = args.index("--since")
        hh, mm = (int(x) for x in args[i + 1].split(":"))
        since = dt.datetime.combine(DAY, dt.time(hh, mm))
        del args[i:i + 2]
    out = args[0] if args else os.path.join(HERE, "capture.webp")

    rows = load()
    dropped = 0
    if since is not None:
        before = len(rows)
        rows = [r for r in rows if r["t"] >= since]
        dropped = before - len(rows)
    if not rows:
        print("no data", file=sys.stderr)
        return 1

    fig, ax = plt.subplots(3, 1, figsize=(12, 9), sharex=True,
                           gridspec_kw=dict(hspace=0.12))
    fig.suptitle("o2-probe Rev A first article — 2026-09-04, after U7 replacement", y=0.965,
                 fontsize=13, fontweight="bold")

    # --- cell current -----------------------------------------------------
    a = ax[0]
    tx, ty = series(rows, "cell", railed=False)
    a.plot(tx, ty, "-o", ms=3.5, lw=1.4, color="#2E6F9E", label="cell current")
    rx, ry = series(rows, "cell", railed=True)
    if rx:
        a.plot(rx, ry, "o", ms=6, mfc="none", mec="#B4462F", mew=1.4,
               label="TIA railed — value is a LOWER BOUND only")
    a.axhspan(70, 130, color="#4C9A6B", alpha=0.13, zorder=0)
    a.text(0.004, 0.90, "70–130 µA  datasheet spec in air", color="#2F6B4C",
           fontsize=8.5, transform=a.transAxes)
    a.set_ylabel("cell current  (µA)")
    a.grid(alpha=0.25)

    # Only raise a second axis if there is something to put on it - an empty
    # twin axis renders a 0..1 scale that reads like real data.
    cx, cy = series(rows, "comp")
    dx, dy = series(rows, "deriv")
    have_comp = any(v == v for v in cy)
    if have_comp or any(v == v for v in dy):
        b = a.twinx()
        if any(v == v for v in dy):
            b.plot(dx, dy, "--", lw=1.3, color="#B08CC7",
                   label=("O₂ from stored cal"
                          + ("" if have_comp else " — firmware withholding")))
        if have_comp:
            b.plot(cx, cy, "-s", ms=3.5, lw=1.4, color="#7A4FA3",
                   label="O₂ published by firmware")
        b.axhline(20.95, color="#7A4FA3", lw=0.9, ls=":", alpha=0.7)
        b.set_ylabel("O₂  (%vol)", color="#7A4FA3")
        b.tick_params(axis="y", colors="#7A4FA3")
        b.set_ylim(19.5, 22.5)
        # One legend for both axes, parked in the empty lower-left corner:
        # two separate boxes on a twinned axis land on top of the traces.
        h1, l1 = a.get_legend_handles_labels()
        h2, l2 = b.get_legend_handles_labels()
        b.legend(h1 + h2, l1 + l2, loc="lower left", fontsize=8.5,
                 framealpha=0.92, borderpad=0.6)
    else:
        a.legend(loc="lower left", fontsize=8.5, framealpha=0.92)

    # --- temperature ------------------------------------------------------
    a = ax[1]
    for key, col, lab in (("die", "#8A8F98", "MCU die (STM32 internal)"),
                          ("tip", "#C2703D", "tip (TMP117)"),
                          ("cham", "#3D8AC2", "chamber (SHT45)")):
        x, y = series(rows, key)
        if any(v == v for v in y):
            a.plot(x, y, "-o", ms=3, lw=1.3, color=col, label=lab)
    a.set_ylabel("temperature  (°C)")
    a.legend(loc="upper left", fontsize=8.5)
    a.grid(alpha=0.25)

    # --- humidity ---------------------------------------------------------
    a = ax[2]
    x, y = series(rows, "rh")
    if x:
        a.plot(x, y, "-o", ms=3, lw=1.3, color="#3D8AC2", label="RH (SHT45)")
    a.set_ylabel("relative humidity  (%)")
    a.legend(loc="upper left", fontsize=8.5)
    a.grid(alpha=0.25)

    d = a.twinx()
    x, y = series(rows, "dew")
    if x:
        d.plot(x, y, "-", lw=1.5, color="#4C9A6B", label="dew margin")
        d.axhline(0, color="#B4462F", lw=1, ls=":")
        d.set_ylabel("dew margin  (K)", color="#2F6B4C")
        d.tick_params(axis="y", colors="#2F6B4C")
        d.legend(loc="lower right", fontsize=8.5)

    ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax[2].set_xlabel("time (local)")
    for a in ax:
        a.spines["top"].set_visible(False)

    n_rail = sum(1 for r in rows if r["railed"])
    note = f"{len(rows)} samples, {n_rail} railed"
    if dropped:
        note += f"   ·   {dropped} earlier samples excluded (pre-U7-replacement)"
    note += "   ·   air point stored 100026 nA @ 28.84 °C"
    fig.text(0.5, 0.012, note, ha="center", fontsize=8.5, color="#555")

    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
