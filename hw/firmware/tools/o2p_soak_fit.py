#!/usr/bin/env python3
"""Fit (tempco exponent n, dilution response alpha) on an oven-soak export.

    python3 tools/o2p_soak_fit.py --export soak.jsonl --pressure p.json \
        --plot o2.png --since 3h

WHAT IS FITTED. The probe sits in air, so the dry-basis oxygen fraction is a
constant 20.946 %vol and every wiggle in the cell current is instrument. The
model is the firmware's own two terms and nothing else:

    I(t) = I0 * (T_cell/T_ref)^n * (1 - alpha * p_w/P)

with n the capillary-law exponent (o2.h O2P_CELL_T_EXPONENT = 0.75) and alpha
the fraction of the modelled dilution the cell actually shows (DIL_ALPHA,
register 0x0045). Both are fitted in logs by least squares.

WHY THE UNCERTAINTY IS A BLOCK JACKKNIFE AND NOT THE COVARIANCE. Consecutive
uplinks are a minute apart and the cell's time constant is tens of minutes, so
the samples are autocorrelated and the naive standard error is roughly ten
times too small. O2-HUMIDITY-CORRECTION.md section 14 found exactly this: an
effective n of about 26 against a nominal 6505. A delete-one-block jackknife
over contiguous blocks is reported instead, and it is the number to quote.

WHY IT CAN REFUSE. n and alpha are separable only if temperature and humidity
moved DIFFERENTLY during the run. On a plain ramp they do not: both rise
together, the design matrix is collinear, and the fit will still return two
confident-looking numbers that are a ridge, not a minimum. The correlation of
the two regressors is computed and printed, and above --max-corr the split is
declared UNEVALUABLE - o2p_tempco.py refuses on the same grounds.

GATING. A sample is used only if the probe said it was usable: settle_s = 0,
COMP_OK set, faults in {0, 512} (512 = TEMP_OVER, expected above 60 C), RH in
(0, 100], a finite positive current. Unevaluable is dropped, never defaulted.
"""

import argparse
import datetime
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_psychro  # noqa: E402

O2_AIR_DRY_PCT = 20.946          # o2.h O2P_AIR_FRACTION
FAULT_OK = {0, 512}
NEED = ("gas_cell_ua", "gas_t_ext_c", "gas_t_chamber_c", "gas_rh_chamber_pct",
        "gas_faults", "gas_settle_s")
OPTIONAL = ("gas_comp_ok", "gas_pct_vol", "gas_t_afe_c", "gas_heater_duty_pct")


def load_export(path):
    series = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            d = json.loads(line)
            series.setdefault(d["metric"]["__name__"], []).extend(
                zip(d["timestamps"], d["values"]))
    for name in series:
        series[name].sort()
    return series


def pressure_lookup(path):
    """Hourly station pressure -> a linear interpolator on epoch ms.

    Rev A has no barometer and the firmware assumes 930 hPa, so this comes
    from outside. It is a MODEL value, not a station reading; the run log
    says so where the result is quoted.
    """
    if path is None:
        return None
    d = json.load(open(path))["hourly"]
    xs, ys = [], []
    for t, p in zip(d["time"], d["surface_pressure"]):
        if p is None:
            continue
        xs.append(datetime.datetime.fromisoformat(t).timestamp() * 1000.0)
        ys.append(float(p))
    xs, ys = np.array(xs), np.array(ys)
    return lambda t_ms: float(np.interp(t_ms, xs, ys))


def assemble(series, p_of, p_const, since_ms, until_ms):
    """One row per timestamp that every needed metric shares, gated."""
    common = None
    for name in NEED:
        ts = set(t for t, _ in series.get(name, []))
        common = ts if common is None else (common & ts)
    rows, dropped = [], {"gate": 0, "range": 0}
    idx = {n: dict(series.get(n, [])) for n in NEED + OPTIONAL}
    for t in sorted(common or ()):
        if since_ms and t < since_ms:
            continue
        if until_ms and t > until_ms:
            continue
        g = {n: idx[n].get(t) for n in NEED + OPTIONAL}
        try:
            faults = int(float(g["gas_faults"]))
            settle = float(g["gas_settle_s"])
            comp_ok = g["gas_comp_ok"]
            I = float(g["gas_cell_ua"])
            te, tc, rh = (float(g["gas_t_ext_c"]), float(g["gas_t_chamber_c"]),
                          float(g["gas_rh_chamber_pct"]))
        except (TypeError, ValueError):
            dropped["range"] += 1
            continue
        if faults not in FAULT_OK or settle != 0 or (comp_ok is not None and float(comp_ok) != 1):
            dropped["gate"] += 1
            continue
        if not (I > 0 and 0.0 < rh <= 100.0 and -40.0 < te < 200.0 and -40.0 < tc < 200.0):
            dropped["range"] += 1
            continue
        P = p_of(t) if p_of else p_const
        p_w = o2p_psychro.p_water_hpa(tc, rh)
        if p_w >= 0.5 * P:
            dropped["range"] += 1
            continue
        rows.append(dict(t=t, I=I, t_ext=te, t_ch=tc, rh=rh, P=P, p_w=p_w,
                         pct_vol=(float(g["gas_pct_vol"]) if g["gas_pct_vol"] is not None else None),
                         duty=(float(g["gas_heater_duty_pct"])
                               if g["gas_heater_duty_pct"] is not None else None)))
    return rows, dropped


def fit(rows, t_ref_c, fix_n=None, fix_alpha=None):
    """fix_n / fix_alpha pin a term the window cannot constrain.

    With temperature flat, n has no leverage: the fit will still return a
    value, and it will be a large one that then extrapolates the O2 scale to
    nonsense at the far end. Pinning it is how a drying window measures alpha
    alone, and the pinned value must be quoted with the result.
    """
    y = np.log(np.array([r["I"] for r in rows]))
    tk = np.array([r["t_ext"] for r in rows]) + 273.15
    frac = np.array([r["p_w"] / r["P"] for r in rows])
    x_t = np.log(tk / (t_ref_c + 273.15))

    def unpack(p):
        it = iter(p)
        lnI0 = next(it)
        n = fix_n if fix_n is not None else next(it)
        alpha = fix_alpha if fix_alpha is not None else next(it)
        return lnI0, n, alpha

    def resid(p):
        lnI0, n, alpha = unpack(p)
        return lnI0 + n * x_t + np.log1p(-alpha * frac) - y

    p0 = [y.mean()] + ([] if fix_n is not None else [0.75]) + \
         ([] if fix_alpha is not None else [0.5])
    lo = [-np.inf] + ([] if fix_n is not None else [-5.0]) + \
         ([] if fix_alpha is not None else [0.0])
    hi = [np.inf] + ([] if fix_n is not None else [5.0]) + \
         ([] if fix_alpha is not None else [2.0])
    sol = least_squares(resid, p0, bounds=(lo, hi))
    lnI0, n, alpha = unpack(sol.x)
    # Collinearity of the two regressors AT the fitted alpha - the question is
    # whether the data can tell the terms apart, not whether they look alike.
    x_d = np.log1p(-alpha * frac)
    corr = float(np.corrcoef(x_t, x_d)[0, 1]) if np.std(x_t) > 0 and np.std(x_d) > 0 else float("nan")
    return sol, (lnI0, n, alpha), corr, resid


def jackknife(rows, t_ref_c, nblocks, fix_n=None, fix_alpha=None):
    """Delete-one-contiguous-block jackknife. Blocks, because the samples are
    autocorrelated and a leave-one-out on 1-minute uplinks measures nothing."""
    if len(rows) < 3 * nblocks:
        return None
    edges = np.linspace(0, len(rows), nblocks + 1).astype(int)
    ests = []
    for i in range(nblocks):
        keep = rows[:edges[i]] + rows[edges[i + 1]:]
        if len(keep) < 10:
            continue
        try:
            _, (_, n, a), _, _ = fit(keep, t_ref_c, fix_n, fix_alpha)
        except Exception:                                    # noqa: BLE001
            continue
        ests.append((n, a))
    if len(ests) < 3:
        return None
    arr = np.array(ests)
    m = arr.mean(axis=0)
    se = np.sqrt((len(ests) - 1) / len(ests) * ((arr - m) ** 2).sum(axis=0))
    return {"n_se": float(se[0]), "alpha_se": float(se[1]),
            "n_lo": float(arr[:, 0].min()), "n_hi": float(arr[:, 0].max()),
            "alpha_lo": float(arr[:, 1].min()), "alpha_hi": float(arr[:, 1].max()),
            "blocks": len(ests)}


def n_of_t(n_table, t_c, n_default):
    """Effective exponent at a cell temperature, from measured anchors.

    The 2026-09-19 soak found n_eff is NOT a constant - 0.573 at 41.4 C and
    0.10-0.35 at 75.8 C - so a single power law cannot describe both ends.
    This interpolates LINEARLY IN TEMPERATURE between the anchors and CLAMPS
    outside their range rather than extrapolating: two points constrain a line
    between them and say nothing beyond them, and an extrapolated exponent
    compounds into the exponent of a ratio.
    """
    if not n_table:
        return n_default
    ts = sorted(n_table)
    if t_c <= ts[0]:
        return n_table[ts[0]]
    if t_c >= ts[-1]:
        return n_table[ts[-1]]
    for a, b in zip(ts, ts[1:]):
        if a <= t_c <= b:
            f = (t_c - a) / (b - a)
            return n_table[a] + f * (n_table[b] - n_table[a])
    return n_default


def o2_pct(rows, n, alpha, t_ref_c, anchor, n_table=None):
    """Model-corrected dry-basis %vol, anchored so the anchor rows read air.

    The absolute scale stays owned by the anchor, not by a K carried over from
    another calibration era: this run cannot measure the cell constant, and a
    number that looks absolute but is not is the failure o2p_backfill_dry
    warns about.
    """
    tref_k = t_ref_c + 273.15
    def corrected(r):
        law = ((r["t_ext"] + 273.15) / tref_k) ** n_of_t(n_table, r["t_ext"], n)
        dil = 1.0 - alpha * r["p_w"] / r["P"]
        return r["I"] / law / dil
    base = np.mean([corrected(r) for r in anchor])
    # Firmware conversion shape, c_wet = 1 - exp(-I/K), with K set by the
    # anchor reading dry air. Linear only to first order; the excursions here
    # are several percent, so the exponential is kept.
    K_ua = -base / math.log(1.0 - O2_AIR_DRY_PCT / 100.0)
    return [(r["t"], 100.0 * (1.0 - math.exp(-corrected(r) / K_ua))) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="VictoriaMetrics /api/v1/export jsonl")
    ap.add_argument("--pressure", help="open-meteo hourly json; else --p-hpa")
    ap.add_argument("--p-hpa", type=float, default=941.1)
    ap.add_argument("--anchor", default=None,
                    help="HH:MM-HH:MM local window that is known-good air (the R1 baseline)")
    ap.add_argument("--from", dest="t_from", help="local HH:MM, first sample to use")
    ap.add_argument("--to", dest="t_to", help="local HH:MM, last sample to use")
    ap.add_argument("--n-table", default=None,
                    help="measured anchors as T:n pairs, e.g. "
                         "41.37:0.573,75.81:0.225 - adds a curve using an "
                         "exponent that VARIES with temperature, clamped "
                         "outside the anchors rather than extrapolated")
    ap.add_argument("--fix-n", type=float, default=None,
                    help="pin the exponent (0.75 = the firmware's) when the "
                         "window holds temperature flat and cannot constrain it")
    ap.add_argument("--fix-alpha", type=float, default=None,
                    help="pin the dilution response")
    ap.add_argument("--min-samples", type=int, default=20,
                    help="refuse below this many gated samples. Lower it "
                         "deliberately for a provisional look at a leg still "
                         "in progress, and label the result provisional - the "
                         "block jackknife needs blocks to be worth anything.")
    ap.add_argument("--max-corr", type=float, default=0.90)
    ap.add_argument("--blocks", type=int, default=10)
    ap.add_argument("--plot")
    ap.add_argument("--csv")
    a = ap.parse_args()

    series = load_export(a.export)
    def hhmm_ms(s):
        if not s:
            return None
        newest = max(t for v in series.values() for t, _ in v)
        day = datetime.datetime.fromtimestamp(newest / 1000).date()
        h, m = (int(x) for x in s.split(":"))
        return int(datetime.datetime.combine(day, datetime.time(h, m)).timestamp() * 1000)

    p_of = pressure_lookup(a.pressure)
    all_rows, _ = assemble(series, p_of, a.p_hpa, None, None)
    rows, dropped = assemble(series, p_of, a.p_hpa, hhmm_ms(a.t_from), hhmm_ms(a.t_to))
    if len(rows) < a.min_samples:
        sys.exit("UNEVALUABLE: %d usable samples after gating (%s)" % (len(rows), dropped))
    t0 = datetime.datetime.fromtimestamp(rows[0]["t"] / 1000)
    t1 = datetime.datetime.fromtimestamp(rows[-1]["t"] / 1000)
    print("%d samples %s..%s  (dropped: gate %d, range %d)"
          % (len(rows), t0.strftime("%H:%M"), t1.strftime("%H:%M"),
             dropped["gate"], dropped["range"]))

    if a.anchor:
        lo, hi = a.anchor.split("-")
        def inwin(r):
            hhmm = datetime.datetime.fromtimestamp(r["t"] / 1000).strftime("%H:%M")
            return lo <= hhmm <= hi
        anchor = [r for r in all_rows if inwin(r)]
    else:
        anchor = all_rows[:30]
    if len(anchor) < 5:
        sys.exit("UNEVALUABLE: anchor window has %d samples" % len(anchor))
    t_ref_c = float(np.median([r["t_ext"] for r in anchor]))

    sol, (lnI0, n, alpha), corr = fit(rows, t_ref_c, a.fix_n, a.fix_alpha)[:3]
    jk = jackknife(rows, t_ref_c, a.blocks, a.fix_n, a.fix_alpha)
    if a.fix_n is not None:
        print("  n PINNED at %+.3f - not measured here" % a.fix_n)
    if a.fix_alpha is not None:
        print("  alpha PINNED at %+.3f - not measured here" % a.fix_alpha)
    rms = float(np.sqrt(np.mean(sol.fun ** 2)) * 100)

    print("\nfit on T_ref = %.2f C (median of the anchor), P from %s"
          % (t_ref_c, "open-meteo hourly" if a.pressure else "%.1f hPa constant" % a.p_hpa))
    if jk:
        print("  n     = %+.3f  +/- %.3f (block jackknife, %d blocks, range %+.3f..%+.3f)"
              % (n, jk["n_se"], jk["blocks"], jk["n_lo"], jk["n_hi"]))
        print("  alpha = %+.3f  +/- %.3f                       (range %+.3f..%+.3f)"
              % (alpha, jk["alpha_se"], jk["alpha_lo"], jk["alpha_hi"]))
    else:
        print("  n = %+.3f, alpha = %+.3f  (jackknife UNEVALUABLE: too few blocks)" % (n, alpha))
    print("  residual rms %.2f %% of current" % rms)
    print("  regressor correlation r = %+.4f  ->  %s"
          % (corr, "SEPARABLE" if abs(corr) <= a.max_corr else
             "UNEVALUABLE: the split is a ridge, not a minimum"))
    if abs(corr) > a.max_corr:
        print("  the pair (n, alpha) above describes the data but neither value "
              "stands alone; quote the curve, not the coefficients.")

    # What the firmware does, for comparison: n = 0.75, alpha = 1.
    n_table = None
    if a.n_table:
        n_table = {}
        for pair in a.n_table.split(","):
            tk, nv = pair.split(":")
            n_table[float(tk)] = float(nv)
        print("  n table: " + ", ".join("%.2f C -> %+.3f" % (k, n_table[k])
                                        for k in sorted(n_table))
              + "  (linear in T, clamped outside)")
    fw = o2_pct(rows, 0.75, 1.0, t_ref_c, anchor)
    fit_o2 = o2_pct(rows, n, alpha, t_ref_c, anchor)
    raw = o2_pct(rows, 0.0, 0.0, t_ref_c, anchor)
    tab = o2_pct(rows, n, alpha, t_ref_c, anchor, n_table) if n_table else None
    series = [("uncorrected", raw), ("firmware n=0.75 a=1", fw), ("fitted", fit_o2)]
    if tab:
        series.append(("two-anchor n(T)", tab))
    for label, ser in series:
        v = np.array([x for _, x in ser])
        print("  %-20s %%vol  mean %6.3f  min %6.3f  max %6.3f  span %.3f"
              % (label, v.mean(), v.min(), v.max(), v.max() - v.min()))
    pub = [(r["t"], r["pct_vol"]) for r in rows if r["pct_vol"] is not None]
    if pub:
        v = np.array([x for _, x in pub])
        print("  %-20s %%vol  mean %6.3f  min %6.3f  max %6.3f  span %.3f"
              % ("probe published", v.mean(), v.min(), v.max(), v.max() - v.min()))

    if a.csv:
        with open(a.csv, "w") as fh:
            fh.write("time,t_ext_c,t_chamber_c,rh_pct,p_w_hpa,P_hpa,cell_ua,"
                     "o2_uncorrected,o2_firmware,o2_fitted,o2_ntable,o2_published\n")
            pubd = dict(pub)
            tabd = dict(tab) if tab else {}
            for r, (_, u), (_, f), (_, g) in zip(rows, raw, fw, fit_o2):
                fh.write("%s,%.2f,%.2f,%.1f,%.2f,%.1f,%.3f,%.3f,%.3f,%.3f,%s,%s\n"
                         % (datetime.datetime.fromtimestamp(r["t"] / 1000).isoformat(),
                            r["t_ext"], r["t_ch"], r["rh"], r["p_w"], r["P"], r["I"],
                            u, f, g,
                            ("%.3f" % tabd[r["t"]]) if r["t"] in tabd else "",
                            ("%.3f" % pubd[r["t"]]) if r["t"] in pubd else ""))
        print("  csv -> %s" % a.csv)

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        def xs(ser):
            return [datetime.datetime.fromtimestamp(t / 1000) for t, _ in ser]
        fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                      gridspec_kw={"height_ratios": [2, 1]})
        ax.axhline(O2_AIR_DRY_PCT, color="#444", lw=1.2, ls="--",
                   label="dry air, 20.946 %vol (truth)")
        ax.plot(xs(raw), [v for _, v in raw], color="#c0c0c0", lw=1.0,
                label="uncorrected")
        if pub:
            ax.plot(xs(pub), [v for _, v in pub], color="#d1495b", lw=1.4,
                    label="probe published")
        ax.plot(xs(fw), [v for _, v in fw], color="#00798c", lw=1.4,
                label="firmware model (n=0.75, $\\alpha$=1)")
        ax.plot(xs(fit_o2), [v for _, v in fit_o2], color="#7a9cc6", lw=1.5,
                label="single exponent (n=%.2f, $\\alpha$=%.2f)" % (n, alpha))
        if tab:
            ax.plot(xs(tab), [v for _, v in tab], color="#1b1b3a", lw=2.0,
                    label="measured n(T), $\\alpha$=%.2f" % alpha)
        ax.set_ylabel("O$_2$, %vol dry basis")
        ax.legend(loc="lower left", fontsize=8, ncol=2, frameon=False)
        ax.grid(alpha=0.25)
        ax.set_title("Oven soak 2026-09-19: the probe is in air, so every "
                     "excursion from the dashed line is instrument")
        ax2.plot(xs(raw), [r["t_ext"] for r in rows], color="#e07a5f", label="T_EXT")
        ax2.plot(xs(raw), [r["t_ch"] for r in rows], color="#f2cc8f", label="T chamber")
        ax2.set_ylabel("°C", color="#e07a5f")
        ax3 = ax2.twinx()
        ax3.plot(xs(raw), [100 * r["p_w"] / r["P"] for r in rows], color="#3d405b",
                 label="p$_w$/P")
        ax3.set_ylabel("p$_w$/P, %", color="#3d405b")
        ax2.grid(alpha=0.25)
        ax2.legend(loc="upper left", fontsize=8, frameon=False)
        ax3.legend(loc="upper right", fontsize=8, frameon=False)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.tight_layout()
        fig.savefig(a.plot, dpi=140)
        print("  plot -> %s" % a.plot)


if __name__ == "__main__":
    main()
