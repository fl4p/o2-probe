#!/usr/bin/env python3
"""Fit the published cell current against the AFE's OWN temperature.

    python3 tools/o2p_tempco.py --csv run.csv --mode dummy
    python3 tools/o2p_tempco.py --vm-export gas.jsonl --mode cell \\
        --start 2026-09-10T08:00Z --end 2026-09-10T12:00Z --plot fit.png

WHAT IT MEASURES. The firmware publishes

    I = (0.67 * VREF - VOUT) / R_TIA         (sampler_logic.h, R_TIA = 7000)

and SNAS506I gives R_TIA an accuracy (5 %) but no temperature coefficient.
Every other term in the chain is bounded and small (ADS1119 gain 2 ppm/K,
TcVOS_RW 8 uV/K, VREF cancels), so the AFE's contribution to the oxygen
reading's temperature dependence is essentially tc(R_TIA), and it drifts
with the LMP91000 die - register T_AFE (0x002C), CSV column t_afe_c - not
with the tip. This tool regresses the current on that column and reports
the slope in ppm/K of the mean current, with its standard error.

TWO MODES, because the cell is the confounder.

  --mode dummy   A fixed resistor sits in the cell socket (see
                 docs/2026-09-09-afe-tempco-plan.md for the values). Nothing
                 else on the board is temperature-sensitive at the ppm level,
                 so I ~ a + b*T_AFE and b/mean(I) IS the AFE tempco, less the
                 dummy resistor's own (25 ppm/K for an ordinary metal film,
                 which is why the plan asks for one). This is the clean
                 measurement and the one to do first.

  --mode cell    The real cell is fitted. The current then also follows the
                 CELL's temperature, which nothing measures directly: the
                 chamber SHT45 sees the gas, and the cell body lags it by
                 about ten minutes (2026-09-08 run). So the model is

                     I ~ a + b*T_AFE + c*lag(T_CHAMBER, tau)

                 with tau scanned for the best fit. b and c can only be
                 separated when the two regressors moved DIFFERENTLY during
                 the run. If they are collinear (|r| above --max-corr) the
                 split is UNEVALUABLE and this tool says so and refuses to
                 print two numbers; it prints the single combined slope
                 instead, which is all such a run supports. Heating the tip
                 with the ring heater alone gives collinear regressors by
                 construction - both temperatures follow one heat source -
                 which is why the plan calls for a second excursion that warms
                 the AFE end and not the tip, or for the dummy.

                 --afe-ppm-k fixes b to a value measured in dummy mode, and
                 then the fit solves for c alone: the cell's apparent
                 dependence on chamber temperature with the AFE's share
                 removed. That number still contains the cell's unmeasured
                 coupling to the gas temperature; it is not the cell's tempco.

WHAT IT REFUSES. A regression over a flat run returns a slope, and the slope
is noise divided by nothing. So it refuses to report when the T_AFE span is
below --min-span-k (8 K) or fewer than --min-n (20) usable samples remain,
and it always prints the span so the reader can judge the rest. Rows are
dropped when settle_s > 0, when faults intersect O2P_FAULTS_INVALIDATE_O2
(0x6866: I2C_FAIL_LMP, I2C_FAIL_ADS, AFE_CONFIG_MISMATCH, VA_LOW, ADC_RANGE,
ADS_DRDY_STUCK, ADS_CONFIG_LOST - a copy of faults.h, checked against it at
startup), or when any regressor is missing. "Unevaluable" exits 2, never 0.

INPUTS. --csv takes the schema o2p_poll.py, o2p_thermal.py and their
--poll-csv write (utc, o2_raw_ua, t_afe_c, t_tip_c, t_chamber_c, faults,
settle_s). --vm-export takes VictoriaMetrics /api/v1/export lines for the
gas_* metrics of one probe, e.g.

    ssh root@100.64.0.3 'curl -sg "http://127.0.0.1:8428/api/v1/export?\\
        match[]={__name__=~\\"gas_.*\\",probe=\\"3\\"}&start=2026-09-10T00:00:00Z"' \\
        > gas.jsonl

(curl needs -g, or it eats the brackets). The export is preferred over a
range query because those are the points as written, not step-aligned
re-evaluations. Rows from the two sources are the same shape once loaded.

PURE PYTHON, no numpy: this runs on the bench laptop next to the other
tools. The least squares is three parameters at most and is solved exactly.
"""

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys

DOC = __doc__ or ""
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.pardir, "src")

# Copy of O2P_FAULTS_INVALIDATE_O2 - the same copy oxygen.json's red band uses.
# A copy rots, so check_against_source() compares it with faults.h at startup.
INVALIDATE_MASK = 0x6866

I16_INVALID = -32768


# --------------------------------------------------------------------------
# Agreement with the firmware.

def check_against_source():
    """Return a list of problems, empty when the copied mask still matches."""
    try:
        with open(os.path.join(SRC, "faults.h")) as fh:
            text = fh.read()
    except OSError as exc:
        return ["cannot read src/faults.h: %s" % exc]
    # faults.h: `#define O2P_FAULTS_INVALIDATE_O2 ( O2P_F_A \\ | O2P_F_B ... )`
    # over several lines, each bit an enum member `O2P_F_A = 1u << n,`.
    m = re.search(r"#define\s+O2P_FAULTS_INVALIDATE_O2\s*\(([^)]*)\)", text)
    if not m:
        return ["O2P_FAULTS_INVALIDATE_O2 not found in faults.h"]
    names = re.findall(r"O2P_F_[A-Z0-9_]+", m.group(1))
    if not names:
        return ["O2P_FAULTS_INVALIDATE_O2 has no terms I can read"]
    mask = 0
    for n in names:
        d = re.search(r"\b%s\s*=\s*1[uU]?\s*<<\s*(\d+)" % re.escape(n), text)
        if not d:
            return ["cannot resolve %s in faults.h" % n]
        mask |= 1 << int(d.group(1))
    if mask != INVALIDATE_MASK:
        return ["INVALIDATE_MASK 0x%04X but faults.h says 0x%04X"
                % (INVALIDATE_MASK, mask)]
    return []


# --------------------------------------------------------------------------
# Loading. Both loaders yield dicts with the same keys:
#   t (float, unix s), i_ua, t_afe, t_tip, t_cham, faults (int|None),
#   settle (float|None)

def _f(v):
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return x


def _int(v):
    if v in (None, ""):
        return None
    try:
        return int(str(v), 0)
    except ValueError:
        try:
            return int(float(v))
        except ValueError:
            return None


def parse_utc(s):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).replace(
                tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError("unparseable UTC time %r" % s)


def load_csv(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            ts = r.get("utc") or r.get("iso_time")
            if not ts:
                continue
            try:
                t = parse_utc(ts)
            except ValueError:
                continue
            rows.append({
                "t": t,
                "i_ua": _f(r.get("o2_raw_ua", r.get("cell_ua"))),
                "t_afe": _f(r.get("t_afe_c")),
                "t_tip": _f(r.get("t_tip_c")),
                "t_cham": _f(r.get("t_chamber_c")),
                "faults": _int(r.get("faults")),
                "settle": _f(r.get("settle_s")),
            })
    return rows


def load_vm_export(path):
    series = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            name = d["metric"].get("__name__")
            series.setdefault(name, {}).update(
                zip(d["timestamps"], d["values"]))
    cur = series.get("gas_cell_ua", {})
    rows = []
    for ts in sorted(cur):
        def g(name):
            return series.get(name, {}).get(ts)
        rows.append({
            "t": ts / 1000.0,
            "i_ua": _f(cur[ts]),
            "t_afe": _f(g("gas_t_afe_c")),
            "t_tip": _f(g("gas_t_tip_c")),
            "t_cham": _f(g("gas_t_chamber_c")),
            "faults": _int(g("gas_faults")),
            "settle": _f(g("gas_settle_s")),
        })
    return rows


def select(rows, start=None, end=None):
    """Window, then drop the rows the firmware itself would not trust."""
    out = []
    dropped = {"window": 0, "settling": 0, "faulted": 0, "missing": 0}
    for r in rows:
        if (start is not None and r["t"] < start) or \
           (end is not None and r["t"] > end):
            dropped["window"] += 1
            continue
        if r["settle"] is not None and r["settle"] > 0:
            dropped["settling"] += 1
            continue
        if r["faults"] is not None and (r["faults"] & INVALIDATE_MASK):
            dropped["faulted"] += 1
            continue
        if r["i_ua"] is None or r["t_afe"] is None:
            dropped["missing"] += 1
            continue
        out.append(r)
    return out, dropped


# --------------------------------------------------------------------------
# Numerics. Exact least squares for p <= 3, plus a first-order lag.

def lag(ts, xs, tau):
    """First-order lag of xs sampled at ts (irregular), time constant tau s.
    tau <= 0 returns xs unchanged. Gaps in xs hold the state."""
    if tau <= 0:
        return list(xs)
    out, y, t_prev = [], None, None
    for t, x in zip(ts, xs):
        if x is None:
            out.append(None)
            continue
        if y is None:
            y = x
        else:
            a = 1.0 - math.exp(-(t - t_prev) / tau)
            y += a * (x - y)
        t_prev = t
        out.append(y)
    return out


def _solve(a, b):
    """Gauss-Jordan on a square system; returns (x, inverse) or raises."""
    n = len(a)
    m = [list(map(float, a[i])) + [1.0 if i == j else 0.0 for j in range(n)]
         + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ZeroDivisionError("singular normal equations")
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        m[col] = [v / p for v in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0.0:
                f = m[r][col]
                m[r] = [rv - f * cv for rv, cv in zip(m[r], m[col])]
    inv = [row[n:2 * n] for row in m]
    x = [row[2 * n] for row in m]
    return x, inv


def ols(X, y):
    """X: list of rows (with leading 1.0), y: list. Returns dict with beta,
    se, r2, rss, rms, n, p."""
    n, p = len(X), len(X[0])
    xtx = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(p)]
           for i in range(p)]
    xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(p)]
    beta, inv = _solve(xtx, xty)
    fit = [sum(b * x for b, x in zip(beta, row)) for row in X]
    rss = sum((yy - ff) ** 2 for yy, ff in zip(y, fit))
    ybar = sum(y) / n
    tss = sum((yy - ybar) ** 2 for yy in y)
    dof = max(n - p, 1)
    s2 = rss / dof
    se = [math.sqrt(max(s2 * inv[i][i], 0.0)) for i in range(p)]
    return {"beta": beta, "se": se, "r2": (1.0 - rss / tss) if tss > 0 else 0.0,
            "rss": rss, "rms": math.sqrt(rss / n), "n": n, "p": p, "fit": fit}


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def span(xs):
    xs = [x for x in xs if x is not None]
    return (max(xs) - min(xs)) if xs else 0.0


# --------------------------------------------------------------------------
# The analysis.

def analyse(rows, mode="dummy", tau=None, tau_grid=None, afe_ppm_k=None,
            min_span_k=8.0, min_n=20, max_corr=0.95):
    """Return a result dict. result["verdict"] is "ok" or "unevaluable";
    result["reasons"] says why. Numbers are only present when they mean
    something."""
    res = {"mode": mode, "n": len(rows), "verdict": "unevaluable",
           "reasons": []}
    if not rows:
        res["reasons"].append("no usable rows")
        return res
    ts = [r["t"] for r in rows]
    i_ua = [r["i_ua"] for r in rows]
    t_afe = [r["t_afe"] for r in rows]
    res["t_afe_span_k"] = span(t_afe)
    res["t_afe_min_c"], res["t_afe_max_c"] = min(t_afe), max(t_afe)
    res["i_mean_ua"] = sum(i_ua) / len(i_ua)
    res["duration_s"] = ts[-1] - ts[0]

    # gamma: how much of the tip's excursion the AFE saw. Reported whenever
    # the tip moved, in every mode - it is the coupling the hot-bath note
    # called unknowable.
    tip = [r["t_tip"] for r in rows]
    if all(v is not None for v in tip) and span(tip) >= 2.0:
        g = ols([[1.0, v] for v in tip], t_afe)
        res["gamma_afe_per_tip"] = g["beta"][1]
        res["gamma_se"] = g["se"][1]
        res["t_tip_span_k"] = span(tip)

    if len(rows) < min_n:
        res["reasons"].append("only %d usable rows, need %d"
                              % (len(rows), min_n))
    if res["t_afe_span_k"] < min_span_k:
        res["reasons"].append("T_AFE moved %.2f K, need %.1f K - no excursion "
                              "to fit on" % (res["t_afe_span_k"], min_span_k))
    if res["reasons"]:
        return res

    imean = res["i_mean_ua"]

    if mode == "dummy":
        f = ols([[1.0, v] for v in t_afe], i_ua)
        res.update({
            "afe_ppm_k": f["beta"][1] / imean * 1e6,
            "afe_ppm_k_se": f["se"][1] / imean * 1e6,
            "slope_ua_per_k": f["beta"][1],
            "r2": f["r2"], "rms_ua": f["rms"],
        })
        res["verdict"] = "ok"
        return res

    if mode != "cell":
        raise ValueError("mode must be dummy or cell")

    cham = [r["t_cham"] for r in rows]
    if any(v is None for v in cham):
        res["reasons"].append("cell mode needs t_chamber_c on every row")
        return res

    # Scan tau for the best fit unless one was given.
    grid = [tau] if tau is not None else (tau_grid or
                                           [0] + list(range(60, 1801, 60)))
    best = None
    for tau_try in grid:
        tc = lag(ts, cham, tau_try)
        if afe_ppm_k is None:
            X = [[1.0, a, c] for a, c in zip(t_afe, tc)]
            y = i_ua
        else:
            # b is fixed: subtract its contribution and fit the rest.
            b_fixed = afe_ppm_k * 1e-6 * imean
            X = [[1.0, c] for c in tc]
            y = [i - b_fixed * a for i, a in zip(i_ua, t_afe)]
        try:
            f = ols(X, y)
        except ZeroDivisionError:
            continue
        if best is None or f["rss"] < best[1]["rss"]:
            best = (tau_try, f, tc)
    if best is None:
        res["reasons"].append("normal equations singular at every tau")
        return res
    tau_best, f, tc = best
    res["tau_s"] = tau_best
    res["t_cell_lag_span_k"] = span(tc)
    res["corr_afe_cell"] = corr(t_afe, tc)
    res["r2"], res["rms_ua"] = f["r2"], f["rms"]

    # The combined single-regressor slopes are always reportable: they are
    # what a collinear run measures, and they bound the split.
    fa = ols([[1.0, a] for a in t_afe], i_ua)
    fc = ols([[1.0, c] for c in tc], i_ua)
    res["combined_on_afe_ppm_k"] = fa["beta"][1] / imean * 1e6
    res["combined_on_afe_ppm_k_se"] = fa["se"][1] / imean * 1e6
    res["combined_on_cell_ppm_k"] = fc["beta"][1] / imean * 1e6
    res["combined_on_cell_ppm_k_se"] = fc["se"][1] / imean * 1e6

    if afe_ppm_k is not None:
        res["afe_ppm_k"] = afe_ppm_k
        res["afe_ppm_k_fixed"] = True
        res["cell_apparent_ppm_k"] = f["beta"][1] / imean * 1e6
        res["cell_apparent_ppm_k_se"] = f["se"][1] / imean * 1e6
        res["verdict"] = "ok"
        return res

    if abs(res["corr_afe_cell"]) > max_corr:
        res["reasons"].append(
            "T_AFE and lagged T_CHAMBER are collinear (r = %.3f, limit %.2f): "
            "one heat source moved both, so the AFE's share cannot be "
            "separated from the cell's. Only the combined slopes are reported. "
            "Do the dummy-load run, or add an excursion that warms the AFE "
            "end and not the tip." % (res["corr_afe_cell"], max_corr))
        res["verdict"] = "split-unevaluable"
        return res

    res["afe_ppm_k"] = f["beta"][1] / imean * 1e6
    res["afe_ppm_k_se"] = f["se"][1] / imean * 1e6
    res["cell_apparent_ppm_k"] = f["beta"][2] / imean * 1e6
    res["cell_apparent_ppm_k_se"] = f["se"][2] / imean * 1e6
    res["verdict"] = "ok"
    return res


# --------------------------------------------------------------------------
# Reporting.

def report(res, dropped, out=sys.stdout):
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("o2p_tempco  mode=%s  verdict=%s" % (res["mode"], res["verdict"]))
    p("  rows used %d   dropped: window %d, settling %d, faulted %d, missing %d"
      % (res["n"], dropped["window"], dropped["settling"], dropped["faulted"],
         dropped["missing"]))
    if "duration_s" in res:
        p("  window     %.0f s   mean current %.2f uA"
          % (res["duration_s"], res["i_mean_ua"]))
        p("  T_AFE      %.2f .. %.2f C   span %.2f K"
          % (res["t_afe_min_c"], res["t_afe_max_c"], res["t_afe_span_k"]))
    if "gamma_afe_per_tip" in res:
        p("  gamma      dT_AFE/dT_TIP = %.3f +/- %.3f   (tip span %.1f K)"
          % (res["gamma_afe_per_tip"], res["gamma_se"], res["t_tip_span_k"]))
    for r in res["reasons"]:
        p("  ! " + r)
    if res["mode"] == "dummy" and "afe_ppm_k" in res:
        p("  AFE tempco %+.0f +/- %.0f ppm/K   (%.4f uA/K, R2 %.3f, "
          "residual %.3f uA rms)"
          % (res["afe_ppm_k"], res["afe_ppm_k_se"], res["slope_ua_per_k"],
             res["r2"], res["rms_ua"]))
        p("  (less the dummy resistor's own tempco; a 25 ppm/K film adds "
          "that much uncertainty)")
    if res["mode"] == "cell" and "tau_s" in res:
        p("  cell lag   tau = %d s   r(T_AFE, lagged T_CHAMBER) = %.3f"
          % (res["tau_s"], res["corr_afe_cell"]))
        p("  combined   on T_AFE alone %+.0f +/- %.0f ppm/K; on lagged "
          "T_CHAMBER alone %+.0f +/- %.0f ppm/K"
          % (res["combined_on_afe_ppm_k"], res["combined_on_afe_ppm_k_se"],
             res["combined_on_cell_ppm_k"], res["combined_on_cell_ppm_k_se"]))
        if "afe_ppm_k" in res:
            if res.get("afe_ppm_k_fixed"):
                p("  AFE tempco %+.0f ppm/K   (FIXED from --afe-ppm-k)"
                  % res["afe_ppm_k"])
            else:
                p("  AFE tempco %+.0f +/- %.0f ppm/K"
                  % (res["afe_ppm_k"], res["afe_ppm_k_se"]))
            p("  cell, apparent, per K of lagged chamber temperature: "
              "%+.0f +/- %.0f ppm/K   (R2 %.3f, residual %.3f uA rms)"
              % (res["cell_apparent_ppm_k"], res["cell_apparent_ppm_k_se"],
                 res["r2"], res["rms_ua"]))
            p("  (that is a_cell * beta, the cell's coupling to the gas "
              "temperature included; not the cell's tempco)")


def plot(rows, res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t0 = rows[0]["t"]
    tt = [(r["t"] - t0) / 60.0 for r in rows]
    fig, ax = plt.subplots(2, 1, figsize=(8, 7))
    ax[0].plot([r["t_afe"] for r in rows], [r["i_ua"] for r in rows],
               ".", ms=3, color="tab:purple", label="samples")
    if "slope_ua_per_k" in res:
        xs = [res["t_afe_min_c"], res["t_afe_max_c"]]
        im = res["i_mean_ua"]
        am = sum(r["t_afe"] for r in rows) / len(rows)
        ax[0].plot(xs, [im + res["slope_ua_per_k"] * (x - am) for x in xs],
                   "-", color="k",
                   label="%+.0f ppm/K" % res["afe_ppm_k"])
    ax[0].set_xlabel("T_AFE (C)")
    ax[0].set_ylabel("cell current (uA)")
    ax[0].legend()
    ax[0].set_title("o2p_tempco  mode=%s  %s" % (res["mode"], res["verdict"]))
    ax[1].plot(tt, [r["t_afe"] for r in rows], color="tab:brown", label="T_AFE")
    if all(r["t_tip"] is not None for r in rows):
        ax[1].plot(tt, [r["t_tip"] for r in rows], color="tab:red", label="T_TIP")
    if all(r["t_cham"] is not None for r in rows):
        ax[1].plot(tt, [r["t_cham"] for r in rows], color="tab:orange",
                   label="T_CHAMBER")
    ax[1].set_xlabel("minutes")
    ax[1].set_ylabel("C")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=DOC.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=DOC)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="o2p_poll / o2p_thermal CSV")
    src.add_argument("--vm-export", help="VictoriaMetrics /api/v1/export lines")
    ap.add_argument("--mode", choices=["dummy", "cell"], default="dummy")
    ap.add_argument("--start", help="UTC, e.g. 2026-09-10T08:00Z")
    ap.add_argument("--end", help="UTC")
    ap.add_argument("--tau", type=float, default=None,
                    help="cell lag in s; default scans 0..1800")
    ap.add_argument("--afe-ppm-k", type=float, default=None,
                    help="cell mode: fix the AFE tempco to this measured value")
    ap.add_argument("--min-span-k", type=float, default=8.0)
    ap.add_argument("--min-n", type=int, default=20)
    ap.add_argument("--max-corr", type=float, default=0.95)
    ap.add_argument("--json", metavar="PATH", help="also write the result dict")
    ap.add_argument("--plot", metavar="PNG")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the faults.h agreement check")
    args = ap.parse_args(argv)

    if not args.no_check:
        problems = check_against_source()
        if problems:
            for pr in problems:
                print("FAULT MASK OUT OF STEP: " + pr, file=sys.stderr)
            return 1

    rows = load_csv(args.csv) if args.csv else load_vm_export(args.vm_export)
    start = parse_utc(args.start) if args.start else None
    end = parse_utc(args.end) if args.end else None
    used, dropped = select(rows, start, end)
    res = analyse(used, mode=args.mode, tau=args.tau, afe_ppm_k=args.afe_ppm_k,
                  min_span_k=args.min_span_k, min_n=args.min_n,
                  max_corr=args.max_corr)
    report(res, dropped)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"result": res, "dropped": dropped}, fh, indent=2)
    if args.plot and used:
        plot(used, res, args.plot)
        print("  plot       %s" % args.plot)
    return 0 if res["verdict"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
