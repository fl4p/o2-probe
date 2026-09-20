#!/usr/bin/env python3
"""Apply the fitted cell model to an in-pile capture and show corrected %vol.

    python3 tools/o2p_pile_correct.py --export pile.jsonl \
        --pressure p.json --anchor 10:40-11:01 --from 11:47 --to 15:44 \
        --alpha 0.715 --plot pile.png --csv pile.csv

WHY THIS IS NOT o2p_soak_fit.py. In the oven the probe sat in air, the dry
oxygen fraction was known to be 20.946 %vol, and every wiggle was instrument -
so n and alpha could be FITTED. In the pile the oxygen fraction is the
unknown being measured. Nothing here can be fitted; the model is carried in
from the soak and only APPLIED. A tool that fits on pile data would be fitting
the biology into the instrument.

WHERE THE MODEL COMES FROM. The temperature law is read out of src/o2.h at
run time rather than copied, so this figure cannot drift away from the
firmware it is meant to describe. o2p_cell_t_lnf() is mirrored exactly: the
0.75 capillary law up to the knee, a straight line in ln T to the 41.37 C
anchor, a second to the 75.81 C anchor, and HELD - not extrapolated - above.

WHAT THE ABSOLUTE SCALE RESTS ON. One anchor window in ambient air taken
minutes before insertion, assumed to be 20.946 %vol dry. The cell constant K
follows from it. This run cannot measure K, and a number that looks absolute
but is not is exactly what o2p_backfill_dry.py warns about - so the anchor
window is printed, gated, and its scatter reported.

GATING. settle_s = 0, COMP_OK set, faults in {0, 512} (512 = TEMP_OVER,
expected above 60 C), RH in (0, 100], finite positive current, and a valid
t_ext - because o2p_cell_temperature() prefers t_ext and falls back to the
chamber, so a row without it was compensated against a DIFFERENT sensor and
is not comparable. Unevaluable rows are dropped and counted, never defaulted.
"""

import argparse
import datetime
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_psychro  # noqa: E402

O2_AIR_DRY_PCT = 20.946
FAULT_OK = {0, 512}
NEED = ("gas_cell_ua", "gas_t_chamber_c", "gas_rh_chamber_pct",
        "gas_faults", "gas_settle_s")
OPTIONAL = ("gas_comp_ok", "gas_pct_vol", "gas_heater_duty_pct", "gas_t_ext_c",
            "gas_t_tip_c")

O2_H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "o2.h")


def load_law(path):
    """Read the knee-law constants out of o2.h. Refuses on a missing one."""
    want = {"O2P_CELL_T_EXPONENT": float, "O2P_CELL_T_KNEE_C100": int,
            "O2P_CELL_T_MID_C100": int, "O2P_CELL_T_TOP_C100": int,
            "O2P_CELL_T_MID_LNF": float, "O2P_CELL_T_TOP_LNF": float,
            "O2P_CELL_T_REF_C100": int}
    src = open(path).read()
    out = {}
    for name, cast in want.items():
        # The literal must be the WHOLE value: anchored to a comment or the
        # end of line. A pattern that stopped at the first literal read 3600
        # out of "#define O2P_CELL_T_KNEE_C100 3600 + 100" while the firmware
        # compiled 3700 - a silent disagreement with the thing this tool
        # exists to track. Anything that is not a plain literal now refuses.
        m = re.search(r"^#define[ \t]+%s[ \t]+"
                      r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)[fFuU]*"
                      r"[ \t]*(?:/\*|//|$)" % name, src, re.M)
        if not m:
            if re.search(r"^#define[ \t]+%s\b" % name, src, re.M):
                sys.exit("o2.h defines %s as something other than a plain "
                         "numeric literal. Refusing to guess it: this tool's "
                         "whole claim is that its constants ARE the "
                         "firmware's." % name)
            sys.exit("o2.h has no %s - this tool describes the KNEE model; "
                     "the firmware in this tree does not have it yet." % name)
        out[name] = cast(m.group(1))
    return out


def make_lnf(L):
    """Mirror of o2p_cell_t_lnf() in src/o2.c, in degrees C."""
    n = L["O2P_CELL_T_EXPONENT"]
    t_ref = L["O2P_CELL_T_REF_C100"] / 100.0
    t_knee = L["O2P_CELL_T_KNEE_C100"] / 100.0
    t_mid = L["O2P_CELL_T_MID_C100"] / 100.0
    t_top = L["O2P_CELL_T_TOP_C100"] / 100.0
    lnf_mid = L["O2P_CELL_T_MID_LNF"]
    lnf_top = L["O2P_CELL_T_TOP_LNF"]

    def x(c):
        return math.log((c + 273.15) / (t_ref + 273.15))

    x_knee, x_mid, x_top = x(t_knee), x(t_mid), x(t_top)
    lnf_knee = n * x_knee

    def lnf(c):
        xx = x(c)
        if c <= t_knee:
            return n * xx
        if c <= t_mid:
            return lnf_knee + (xx - x_knee) * (lnf_mid - lnf_knee) / (x_mid - x_knee)
        if c >= t_top:
            return lnf_top
        return lnf_mid + (xx - x_mid) * (lnf_top - lnf_mid) / (x_top - x_mid)

    return lnf, dict(knee=t_knee, mid=t_mid, top=t_top, ref=t_ref, n=n)


def load_export(path):
    series = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            series[d["metric"]["__name__"]] = dict(zip(d["timestamps"], d["values"]))
    return series


def build_rows(series, p_at, t_source):
    missing = [k for k in NEED if k not in series]
    if missing:
        sys.exit("export lacks %s" % ", ".join(missing))
    stamps = sorted(series["gas_cell_ua"])
    rows, drop = [], {}
    for t in stamps:
        def g(k):
            return series.get(k, {}).get(t)
        vals = {k: g(k) for k in NEED + OPTIONAL}
        why = None
        if any(vals[k] is None for k in NEED):
            why = "incomplete uplink"
        elif t_source == "ext" and vals["gas_t_ext_c"] is None:
            why = "no t_ext and --t-source ext"
        elif vals["gas_settle_s"] != 0:
            why = "settling"
        elif vals["gas_comp_ok"] is not None and vals["gas_comp_ok"] < 1:
            why = "COMP_OK clear"
        elif int(vals["gas_faults"]) not in FAULT_OK:
            why = "faults 0x%04X" % int(vals["gas_faults"])
        elif not (0.0 < vals["gas_rh_chamber_pct"] <= 100.0):
            why = "RH out of range"
        elif not (vals["gas_cell_ua"] > 0) or \
                not math.isfinite(vals["gas_cell_ua"]):
            why = "non-positive or non-finite current"
        elif not all(math.isfinite(vals[k]) for k in NEED):
            why = "non-finite field"
        if why:
            drop[why] = drop.get(why, 0) + 1
            continue
        t_ch = vals["gas_t_chamber_c"]
        # o2p_cell_temperature(): t_ext when valid, else chamber-else-tip.
        # Mirrored so the figure compensates off the SAME sensor the probe did.
        if t_source == "chamber" or vals["gas_t_ext_c"] is None:
            t_cell, t_src = t_ch, "chamber"
        else:
            t_cell, t_src = vals["gas_t_ext_c"], "ext"
        p_w = o2p_psychro.p_sat_hpa(t_ch) * vals["gas_rh_chamber_pct"] / 100.0
        rows.append(dict(t=t, I=vals["gas_cell_ua"], t_ext=t_cell, t_src=t_src,
                         t_ch=t_ch, rh=vals["gas_rh_chamber_pct"], p_w=p_w,
                         P=p_at(t), pct_vol=vals["gas_pct_vol"],
                         duty=vals["gas_heater_duty_pct"]))
    return rows, drop


def stamp(t):
    return datetime.datetime.fromtimestamp(t / 1000)


def resolve_spec(spec, dates):
    """Turn one window bound into an absolute local datetime, or refuse.

    The first version of this compared STRING SLICES of "%Y-%m-%dT%H:%M".
    Full bounds worked; every shorter form failed silently and differently -
    "09-17T10:40" was compared against "2026-09-17T" and selected nothing,
    a bare "23:59..00:01" selected nothing, a two-character spec compared
    MINUTES, and a bare "HH:MM" still matched every day in the export, which
    is the exact bug the date-awareness was added to kill. It survived only
    because the anchor-scatter guard happened to reject the contaminated
    window - luck, not protection.

    So: parse, resolve against the dates actually present, and REFUSE what is
    ambiguous or unrecognised rather than quietly selecting the wrong rows.
    """
    spec = spec.strip()
    try:
        return datetime.datetime.strptime(spec, "%Y-%m-%dT%H:%M:%S"), 1
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(spec, fmt), 60
        except ValueError:
            pass
    for fmt in ("%m-%dT%H:%M", "%m-%d %H:%M"):
        try:
            partial = datetime.datetime.strptime(spec, fmt)
        except ValueError:
            continue
        years = {d.year for d in dates if (d.month, d.day) ==
                 (partial.month, partial.day)}
        if len(years) != 1:
            sys.exit("'%s' matches %d years in this export - give the full "
                     "YYYY-MM-DDTHH:MM." % (spec, len(years)))
        return partial.replace(year=years.pop()), 60
    try:
        partial = datetime.datetime.strptime(spec, "%H:%M")
    except ValueError:
        sys.exit("cannot read '%s' as a time. Use YYYY-MM-DDTHH:MM (or a "
                 "bare HH:MM only when the export covers one day)." % spec)
    days = {d.date() for d in dates}
    if len(days) != 1:
        sys.exit("'%s' is a bare time and this export covers %d days (%s). "
                 "It would match one instant PER DAY. Give the full "
                 "YYYY-MM-DDTHH:MM." % (spec, len(days),
                                        ", ".join(str(d) for d in sorted(days))))
    return datetime.datetime.combine(days.pop(), partial.time()), 60


def make_window(spec, dates):
    """(lo, hi) absolute bounds for a START..END spec, or (None, None)."""
    if not spec:
        return None, None
    if ".." not in spec:
        sys.exit("window '%s' needs START..END" % spec)
    lo_s, hi_s = spec.split("..", 1)
    lo = resolve_spec(lo_s, dates)[0] if lo_s.strip() else None
    hi = upper_bound(hi_s, dates) if hi_s.strip() else None
    if lo and hi and hi < lo:
        sys.exit("window '%s' ends before it starts. A window that crosses "
                 "midnight must be written with both dates." % spec)
    return lo, hi


def upper_bound(spec, dates):
    """An END bound covers its own RESOLUTION, not just its first instant.

    "--to 11:01" reads as "through 11:01", so a sample at 11:01:24 is inside
    it. Comparing against 11:01:00 silently dropped the last minute of every
    window - it moved the committed 24 h pile result by one sample the first
    time this was tightened. Seconds-resolution specs bound to the second."""
    when, res = resolve_spec(spec, dates)
    return when + datetime.timedelta(seconds=res - 1, microseconds=999999)


def within(t, lo, hi):
    d = stamp(t)
    return (lo is None or d >= lo) and (hi is None or d <= hi)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True)
    ap.add_argument("--pressure", help="open-meteo hourly json")
    ap.add_argument("--p-hpa", type=float, default=936.6)
    ap.add_argument("--anchor", required=True,
                    help="START..END in ambient air, sets the cell constant; "
                         "local, e.g. 2026-09-17T10:40..2026-09-17T11:01")
    ap.add_argument("--from", dest="t_from")
    ap.add_argument("--to", dest="t_to")
    ap.add_argument("--max-anchor-scatter", type=float, default=1.0,
                    help="refuse an anchor whose current scatter exceeds this "
                         "%%; the absolute scale rests entirely on it")
    ap.add_argument("--alpha", type=float, default=0.715,
                    help="dilution response, DIL_ALPHA/1000 (soak: 0.715)")
    ap.add_argument("--t-source", default="firmware",
                    choices=("firmware", "ext", "chamber"),
                    help="firmware = t_ext else chamber, what the probe itself "
                         "used; ext = refuse rows without the cell sensor")
    ap.add_argument("--o2-h", default=O2_H)
    ap.add_argument("--plot")
    ap.add_argument("--csv")
    a = ap.parse_args()

    L = load_law(a.o2_h)
    lnf, geom = make_lnf(L)
    print("law from %s" % os.path.normpath(a.o2_h))
    print("  n=%.2f to %.2f C, then ln-linear to %.2f C, then to %.2f C, "
          "HELD above" % (geom["n"], geom["knee"], geom["mid"], geom["top"]))

    p_hourly = None
    if a.pressure:
        d = json.load(open(a.pressure))
        if abs(d.get("elevation", -1) - 715) > 1.0:
            sys.exit("open-meteo did not honour elevation=715 (got %r) - refusing"
                     % d.get("elevation"))
        p_hourly = {datetime.datetime.fromisoformat(ts).timestamp(): p
                    for ts, p in zip(d["hourly"]["time"],
                                     d["hourly"]["surface_pressure"])}
        print("  pressure: open-meteo, elevation echoed %.1f m" % d["elevation"])

    def p_at(t):
        if not p_hourly:
            return a.p_hpa
        return min(p_hourly.items(), key=lambda kv: abs(kv[0] - t / 1000.0))[1]

    series = load_export(a.export)
    rows, drop = build_rows(series, p_at, a.t_source)
    for why, k in sorted(drop.items(), key=lambda kv: -kv[1]):
        print("  dropped %4d: %s" % (k, why))

    dates = [stamp(r["t"]) for r in rows]
    a_lo, a_hi = make_window(a.anchor, dates)
    anchor = [r for r in rows if within(r["t"], a_lo, a_hi)]
    if len(anchor) < 5:
        sys.exit("UNEVALUABLE: anchor window has %d usable samples, need 5"
                 % len(anchor))

    s_lo = resolve_spec(a.t_from, dates)[0] if a.t_from else None
    s_hi = upper_bound(a.t_to, dates) if a.t_to else None
    span = [r for r in rows if within(r["t"], s_lo, s_hi)]
    if not span:
        sys.exit("UNEVALUABLE: no usable samples in the requested span")

    def dry(r, mode):
        """Dry, temperature-normalised current under a given law."""
        if mode == "knee":
            law = math.exp(lnf(r["t_ext"]) - lnf(anchor_t))
        elif mode == "fw":
            law = ((r["t_ext"] + 273.15) / (anchor_t + 273.15)) ** geom["n"]
        else:
            law = 1.0
        dil = 1.0 - (a.alpha if mode != "raw" else 0.0) * r["p_w"] / r["P"]
        return r["I"] / law / dil

    anchor_t = float(np.mean([r["t_ext"] for r in anchor]))
    scat = float(np.std([r["I"] for r in anchor]) / np.mean([r["I"] for r in anchor]))
    print("  anchor: %d samples, %s .. %s, %.2f C, I %.3f uA, scatter %.2f %%"
          % (len(anchor), stamp(anchor[0]["t"]).strftime("%Y-%m-%dT%H:%M"),
             stamp(anchor[-1]["t"]).strftime("%Y-%m-%dT%H:%M"),
             anchor_t, float(np.mean([r["I"] for r in anchor])), 100 * scat))
    # NaN fails EVERY comparison, so "scatter > limit" silently passes an
    # anchor built from nonfinite currents. Unevaluable is not OK.
    if not math.isfinite(scat):
        sys.exit("UNEVALUABLE: anchor scatter is not finite - the window "
                 "contains data this tool cannot judge. Refusing to set an "
                 "absolute scale from it.")
    if 100 * scat > a.max_anchor_scatter:
        sys.exit("UNEVALUABLE: anchor scatter %.2f %% exceeds %.2f %%. The "
                 "absolute scale rests entirely on this window - a spread "
                 "this wide means it is not one settled air reading. Narrow "
                 "--anchor or raise --max-anchor-scatter deliberately."
                 % (100 * scat, a.max_anchor_scatter))

    out = {}
    for mode in ("raw", "fw", "knee"):
        base = float(np.mean([dry(r, mode) for r in anchor]))
        K = -base / math.log(1.0 - O2_AIR_DRY_PCT / 100.0)
        out[mode] = [(r["t"], 100.0 * (1.0 - math.exp(-dry(r, mode) / K)))
                     for r in span]

    pub = [(r["t"], r["pct_vol"]) for r in span if r["pct_vol"] is not None]
    names = {"raw": "uncorrected", "fw": "firmware n=0.75",
             "knee": "fitted knee model"}
    n_ch = sum(1 for r in span if r["t_src"] == "chamber")
    if n_ch:
        print("  !! %d of %d span rows have NO CELL-SIDE TEMPERATURE and are "
              "compensated off the chamber, exactly as the probe did"
              % (n_ch, len(span)))
    print("  span: %d samples, T_cell %.1f..%.1f C"
          % (len(span), min(r["t_ext"] for r in span),
             max(r["t_ext"] for r in span)))
    for mode in ("raw", "fw", "knee"):
        v = np.array([x for _, x in out[mode]])
        print("  %-18s %%vol  first %6.3f  last %6.3f  min %6.3f  max %6.3f"
              % (names[mode], v[0], v[-1], v.min(), v.max()))
    if pub:
        v = np.array([x for _, x in pub])
        print("  %-18s %%vol  first %6.3f  last %6.3f  min %6.3f  max %6.3f"
              % ("probe published", v[0], v[-1], v.min(), v.max()))

    if a.csv:
        pubd = dict(pub)
        with open(a.csv, "w") as fh:
            fh.write("time,t_ext_c,t_chamber_c,rh_pct,p_w_hpa,P_hpa,cell_ua,"
                     "o2_uncorrected,o2_firmware,o2_knee,o2_published\n")
            for r, (_, u), (_, f), (_, k) in zip(span, out["raw"], out["fw"],
                                                 out["knee"]):
                fh.write("%s,%.2f,%.2f,%.1f,%.2f,%.1f,%.3f,%.3f,%.3f,%.3f,%s\n"
                         % (datetime.datetime.fromtimestamp(r["t"] / 1000).isoformat(),
                            r["t_ext"], r["t_ch"], r["rh"], r["p_w"], r["P"],
                            r["I"], u, f, k,
                            ("%.3f" % pubd[r["t"]]) if r["t"] in pubd else ""))
        print("  csv -> %s" % a.csv)

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        def xs(ser):
            return [datetime.datetime.fromtimestamp(t / 1000) for t, _ in ser]

        fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                                      gridspec_kw={"height_ratios": [2, 1]})
        ax.plot(xs(out["raw"]), [v for _, v in out["raw"]], color="#c0c0c0",
                lw=1.0, label="uncorrected")
        if pub:
            ax.plot(xs(pub), [v for _, v in pub], color="#d1495b", lw=1.4,
                    label="probe published (as flashed)")
        ax.plot(xs(out["fw"]), [v for _, v in out["fw"]], color="#00798c",
                lw=1.4, label="firmware law (n=0.75, $\\alpha$=1)")
        ax.plot(xs(out["knee"]), [v for _, v in out["knee"]], color="#1b1b3a",
                lw=2.2, label="fitted knee model ($\\alpha$=%.3f)" % a.alpha)
        # Uplinks go sparse once the keeper is off, and a line drawn across a
        # 30 min hole looks like data. Mark where samples actually are.
        ax.plot(xs(out["knee"]), [v for _, v in out["knee"]], "o", ms=3.0,
                color="#1b1b3a", label="actual uplinks")
        ax.set_ylabel("O$_2$, %vol dry basis")
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(alpha=0.3)
        ax.set_title("o2-probe in the Strassenmiete, 2026-09-17 - "
                     "corrected with the soak-fitted cell model")
        ax2.plot(xs(out["knee"]), [r["t_ext"] for r in span], color="#e07a5f",
                 lw=1.4, label="cell T (t_ext)")
        ax2.axhline(geom["knee"], color="#888", ls=":", lw=1.2,
                    label="knee, %.0f C - the 0.75 law's last evidence" % geom["knee"])
        ax2.axhline(geom["mid"], color="#888", ls="--", lw=1.0,
                    label="soak anchor, %.1f C" % geom["mid"])
        ax2.set_ylabel("cell T, C")
        ax2.legend(loc="lower right", fontsize=8)
        ax2.grid(alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.tight_layout()
        fig.savefig(a.plot, dpi=130)
        print("  plot -> %s" % a.plot)


if __name__ == "__main__":
    main()
