#!/usr/bin/env python3
"""THE o2-probe plot. One layout, defined once, used by every tool.

There is exactly one figure for this board and it always has the same five
panels in the same order:

    1. O2            compensated %vol, with raw cell current on the right axis
    2. temperature   tip (TMP117), chamber (SHT45), MCU die
    3. humidity      chamber %RH, with the 50 % RH_SETPOINT floor marked
    4. heater duty   applied (0x0005) and, when known, commanded
    5. VIN           input rail, with the 9000 mV interlock marked

A panel with no data is still DRAWN, labelled "no data". That is the whole
point: a figure whose panels come and go with the dataset cannot be compared
with the one from an hour ago, and comparing them is what a bench log is for.

Every tool that plots this board imports this module. o2p_thermal.py adds its
exponential fit on top of panel 2; it does not get its own layout.

Conventions that are part of the figure, not decoration:

  * A sentinel is a GAP. The firmware's 0xFFFF/0x8000 mean "do not trust me",
    so the line breaks. It is never interpolated and never drawn as zero.
  * A failed poll is a red vertical rule on every panel. An outage looks like
    an outage, not like a straight line between the samples either side.
  * Samples where FAULTS invalidated O2 are shaded on the O2 panel only,
    because that is an O2 statement and not a statement about temperature.
"""

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates       # noqa: E402
import matplotlib.pyplot as plt         # noqa: E402

RH_SETPOINT_FLOOR = 50.0        # regmap.c o2p_config_valid()
VIN_LOW_MV = 9000               # main.c O2P_VIN_LOW_MV

# label, [(column, legend, colour)], optional right-axis (column, label, colour)
PANELS = [
    ("O$_2$ (%vol)",
     [("o2_comp_pct", "as published (wet basis)", "tab:blue"),
      # Drawn only when the column exists. The firmware publishes wet basis
      # until fe27d20 is on the board; plot_poll.py --dry-basis computes the
      # corrected column offline so the size of the artefact is visible on the
      # same axes as the number it corrupts.
      ("o2_dry_pct", "dry basis (corrected)", "tab:cyan")],
     ("o2_raw_ua", "cell current (uA)", "tab:purple")),
    ("temperature (C)",
     [("t_tip_c", "tip (TMP117)", "tab:red"),
      ("t_chamber_c", "chamber (SHT45)", "tab:orange"),
      ("t_die_c", "MCU die", "tab:gray"),
      ("t_afe_c", "AFE die (LMP91000)", "tab:brown")],
     None),
    ("humidity (%RH)",
     [("rh_pct", "chamber", "tab:green")],
     None),
    ("heater duty (%)",
     [("heater_duty_pct", "applied (0x0005; 60 s mean on FW 0x0025+)", "tab:blue"),
      ("cmd_duty_pct", "commanded", "tab:orange")],
     None),
    ("VIN (mV)",
     [("vin_mv", "input rail", "tab:brown")],
     None),
]


def num(row, key):
    """A cell -> float, or None for the sentinel/empty/absent case. Never 0."""
    v = row.get(key, "")
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _xaxis(rows):
    """(x values, formatter, label). Seconds when the log has them, else UTC."""
    import datetime as dt
    # Choose on the whole column, and only a COMPLETE one. Deciding from
    # rows[0] alone (the original) meant a blank first-row t_s hid valid t_s in
    # every later row. But accepting a partially populated column is worse than
    # it looks: one None in x survives the guard and then kills matplotlib
    # inside tight_layout with "float() argument must be ... not NoneType",
    # which is the same class of unreadable failure this guard exists to stop.
    if rows:
        t_s = [num(r, "t_s") for r in rows]
        if all(v is not None for v in t_s):
            return (t_s, None, "seconds")
    out = []
    for r in rows:
        stamp = r.get("utc") or r.get("iso_time") or ""
        try:
            out.append(dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            try:
                out.append(dt.datetime.fromisoformat(stamp.replace("Z", "")))
            except ValueError:
                out.append(None)
    return (out, mdates.DateFormatter("%H:%M:%S"), "UTC")


def plot(rows, out_path, title=None, overlay=None, source=None):
    """Draw THE figure. `overlay(ax_by_label)` may add to a panel afterwards."""
    if not rows:
        raise ValueError("nothing to plot")

    # A CSV that is not a poll log gets here with rows full of unrecognised
    # keys, every series comes out empty, the axes are degenerate, and
    # matplotlib dies inside FreeType with "raster overflow" -- an error that
    # names a glyph rasteriser and not the file you passed. Measured
    # 2026-09-07 by handing this the RH-step marker CSV by mistake. Say what
    # is actually wrong, while the filename is still in scope.
    series = [k for _, left, right in PANELS
              for k in [c[0] for c in left] + ([right[0]] if right else [])]
    if not any(num(r, k) is not None for r in rows for k in series):
        raise ValueError(
            "%sno plottable column found -- is this a poll log?\n"
            "   expected at least one of: %s\n"
            "   this file has:            %s"
            % ("%s: " % source if source else "",
               ", ".join(series[:6]) + ", ...",
               ", ".join(sorted(rows[0].keys())[:8]) or "(no columns)"))
    x_probe, _, _ = _xaxis(rows)
    missing = sum(1 for v in x_probe if v is None)
    if missing:
        raise ValueError(
            "%s%s of %d row(s) have no usable timestamp -- expected 't_s', "
            "'utc' or 'iso_time'.\n   this file has: %s"
            % ("%s: " % source if source else "", missing or "all", len(rows),
               ", ".join(sorted(rows[0].keys())[:8]) or "(none)"))

    ok = [r for r in rows if r.get("status", "ok") == "ok"]
    failed_idx = [i for i, r in enumerate(rows)
                  if r.get("status", "ok") not in ("ok", "")]
    x_all, fmt, xlabel = _xaxis(rows)
    x_ok, _, _ = _xaxis(ok)
    failed_x = [x_all[i] for i in failed_idx if x_all[i] is not None]
    untrusted_x = [x for x, r in zip(x_ok, ok)
                   if str(r.get("o2_trusted", "")) == "False"]

    fig, axes = plt.subplots(len(PANELS), 1, sharex=True,
                             figsize=(11, 1.9 * len(PANELS)))
    by_label = {}
    for ax, (label, series, twin) in zip(axes, PANELS):
        by_label[label] = ax
        drew = False
        for key, name, colour in series:
            y = [num(r, key) for r in ok]
            if any(v is not None for v in y):
                ax.plot(x_ok, y, ".-", ms=3, lw=1, color=colour, label=name)
                drew = True
        if twin:
            key, name, colour = twin
            y = [num(r, key) for r in ok]
            if any(v is not None for v in y):
                tw = ax.twinx()
                tw.plot(x_ok, y, ".-", ms=2, lw=0.8, color=colour, alpha=0.75,
                        label=name)
                tw.set_ylabel(name, fontsize=7, color=colour)
                tw.tick_params(axis="y", labelsize=7, colors=colour)
                drew = True
        # Thresholds that are part of the firmware, not of this plot's taste.
        if label.startswith("humidity"):
            ax.axhline(RH_SETPOINT_FLOOR, color="red", ls="--", lw=1, alpha=0.7)
            ax.text(x_ok[0] if x_ok else 0, RH_SETPOINT_FLOOR,
                    " RH_SETPOINT floor (regmap.c)", fontsize=7, color="red",
                    va="bottom")
        if label.startswith("VIN"):
            ax.axhline(VIN_LOW_MV, color="red", ls="--", lw=1, alpha=0.7)
            ax.text(x_ok[0] if x_ok else 0, VIN_LOW_MV,
                    " VIN_LOW interlock (main.c)", fontsize=7, color="red",
                    va="bottom")
            y and ax.set_ylim((min(y)-1,max(y)+1))
        if label.startswith("O$_2$"):
            for xv in untrusted_x:
                ax.axvspan(xv, xv, color="red", alpha=0.10)
        for xv in failed_x:
            ax.axvline(xv, color="red", lw=1.2, alpha=0.8)
        ax.set_ylabel(label, fontsize=9)
        ax.grid(alpha=0.3)
        if not drew:
            # Drawn anyway, and said out loud. A panel that disappears when a
            # channel is missing makes two runs uncomparable.
            ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center",
                    va="center", fontsize=8, color="dimgray")
        elif len([s for s in series if any(num(r, s[0]) is not None
                                           for r in ok)]) > 1:
            ax.legend(fontsize=7, loc="best")

    if overlay:
        overlay(by_label)

    if fmt:
        axes[-1].xaxis.set_major_formatter(fmt)
    axes[-1].set_xlabel(xlabel)

    span = ""
    if x_all and x_all[0] is not None and x_all[-1] is not None:
        try:
            span = "  (%d samples, %s)" % (len(rows), x_all[-1] - x_all[0])
        except TypeError:
            span = "  (%d samples)" % len(rows)
    fig.suptitle((title or "o2-probe") + span, y=0.995)

    note = ("%d failed poll(s)" % len(failed_x)) if failed_x else "no failed polls"
    if untrusted_x:
        note += ", %d sample(s) with O2 invalidated by FAULTS" % len(untrusted_x)
    fig.text(0.01, 0.005, note, fontsize=7, color="dimgray")

    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.98))
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return note
