#!/usr/bin/env python3
"""Plot a CSV written by firmware/tools/o2p_poll.py.

    python3 bench-logs/plot_poll.py modbus-poll-2026-09-06.csv -o poll.png

The CSV's discipline is preserved here rather than papered over:

  * An empty cell is the firmware's sentinel - "I could not measure this". It
    becomes a GAP in the line, never an interpolated segment and never a zero.
  * Rows with status=failed are drawn as red vertical marks on every panel, so
    a comms outage is visible as an outage instead of as a straight line
    between the samples either side of it.
  * Samples where the firmware says O2 is not trustworthy (o2_trusted=False)
    are shaded, because a plotted number that FAULTS invalidated is exactly the
    reading that must not be believed by eye.
"""

import argparse
import csv
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates       # noqa: E402
import matplotlib.pyplot as plt         # noqa: E402


def num(row, key):
    """A cell -> float, or None for the sentinel/empty case. Never 0."""
    v = row.get(key, "")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def series(rows, key):
    """x,y with None preserved so matplotlib breaks the line at a gap."""
    return [r["_t"] for r in rows], [num(r, key) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv")
    ap.add_argument("-o", "--out", default="poll.png")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    with open(args.csv) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("!! %s has no rows" % args.csv)
    for r in rows:
        r["_t"] = dt.datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ")

    failed = [r["_t"] for r in rows if r["status"] != "ok"]
    untrusted = [r["_t"] for r in rows
                 if r["status"] == "ok" and r.get("o2_trusted") == "False"]
    ok = [r for r in rows if r["status"] == "ok"]

    panels = [
        ("O$_2$ (%vol)", [("o2_comp_pct", "compensated", "tab:blue")]),
        ("cell current (uA)", [("o2_raw_ua", "raw", "tab:purple")]),
        ("temperature (C)", [("t_tip_c", "tip (TMP117)", "tab:red"),
                             ("t_chamber_c", "chamber (SHT45)", "tab:orange"),
                             ("t_die_c", "MCU die", "tab:gray")]),
        ("humidity (%RH)", [("rh_pct", "chamber", "tab:green")]),
        ("VIN (mV)", [("vin_mv", "input rail", "tab:brown")]),
    ]
    panels = [p for p in panels
              if any(num(r, k) is not None for r in ok for k, _, _ in p[1])]

    fig, axes = plt.subplots(len(panels), 1, sharex=True,
                             figsize=(11, 2.0 * len(panels)))
    if len(panels) == 1:
        axes = [axes]

    span = rows[-1]["_t"] - rows[0]["_t"]
    fig.suptitle(args.title or "o2-probe over Modbus - %s  (%d samples, %s)"
                 % (args.csv.split("/")[-1], len(rows), span), y=0.995)

    vin_ax = None
    for ax, (label, keys) in zip(axes, panels):
        if label.startswith("VIN"):
            vin_ax = ax
        for key, name, colour in keys:
            x, y = series(ok, key)
            if any(v is not None for v in y):
                ax.plot(x, y, ".-", ms=3, lw=1, color=colour, label=name)
        for t in failed:
            ax.axvline(t, color="red", lw=1.2, alpha=0.8)
        for t in untrusted:
            ax.axvspan(t, t, color="red", alpha=0.10)
        ax.set_ylabel(label, fontsize=9)
        ax.grid(alpha=0.3)
        if len(keys) > 1:
            ax.legend(fontsize=7, loc="best")

    # Bind the threshold to the VIN axis itself. Reading it off the loop
    # variable drew it on whatever panel happened to be last, which is only
    # the right one while VIN is present AND last.
    if vin_ax is not None:
        vin_ax.axhline(9000, color="red", ls="--", lw=1, alpha=0.7)
        vin_ax.text(rows[0]["_t"], 9000, " VIN_LOW threshold (main.c:59)",
                    fontsize=7, color="red", va="bottom")

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    axes[-1].set_xlabel("UTC")

    note = "%d failed poll(s)" % len(failed) if failed else "no failed polls"
    if untrusted:
        note += ", %d sample(s) with O2 invalidated by FAULTS" % len(untrusted)
    fig.text(0.01, 0.005, note, fontsize=7, color="dimgray")

    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.98))
    fig.savefig(args.out, dpi=140)
    print("wrote %s  (%d rows, %s)" % (args.out, len(rows), note))


if __name__ == "__main__":
    main()
