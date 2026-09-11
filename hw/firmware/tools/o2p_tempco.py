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
                 CELL's temperature. By default the chamber SHT45 stands in
                 for it; that sensor sees the gas, and the cell body lags it by
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

                 --cell-temp ext replaces lag(T_CHAMBER, tau) with T_EXT,
                 the external TMP117 (register 0x001F; CSV t_ext_c, VM
                 gas_t_ext_c) on the side of the cell enclosure, far from the
                 pins, since 2026-09-11. It is measured, so tau is NOT scanned (0 unless
                 --tau is given) - the scan is what broke the 2026-09-11 split.
                 It reads the can wall, not the electrolyte, so c still
                 carries that coupling. Rows without T_EXT are dropped and
                 counted as missing.

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
startup), when any regressor is missing or non-finite, when the timestamp is
unparseable, and when settle_s or faults was recorded but is not a number -
each counted in its own bucket. A direct analyse() call refuses missing,
non-finite or duplicate timestamps (rows are sorted by time). Cell mode also
refuses when its cell regressor - the source AND, for every tau tried, the
lagged series actually fitted - moved less than --min-span-k, with or without
--afe-ppm-k; no result is "ok" while any number in it is non-finite; and the
thresholds themselves must be finite and in range. "Unevaluable" exits 2,
never 0.

INPUTS. --csv takes the schema o2p_poll.py, o2p_thermal.py and their
--poll-csv write (utc, o2_raw_ua, t_afe_c, t_tip_c, t_chamber_c, t_ext_c,
faults, settle_s). --vm-export takes VictoriaMetrics /api/v1/export lines for the
gas_* metrics of one probe, e.g.

    ssh root@100.64.0.3 'curl -sg "http://127.0.0.1:8428/api/v1/export?\\
        match[]={__name__=~\\"gas_.*\\",probe=\\"3\\"}&start=2026-09-10T00:00:00Z"' \\
        > gas.jsonl

(curl needs -g, or it eats the brackets). The export is preferred over a
range query because those are the points as written, not step-aligned
re-evaluations. Rows from the two sources are the same shape once loaded.

PURE PYTHON, no numpy: this runs on the bench laptop next to the other
tools. The least squares is three parameters at most and is solved exactly, on
centred and scaled slope columns so a regressor's wobble is not lost to
cancellation.
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

# Cell-mode regressors: row key, CSV column, report label.
CELL_TEMPS = {
    "chamber-lag": ("t_cham", "t_chamber_c", "lagged T_CHAMBER"),
    "ext":         ("t_ext", "t_ext_c", "T_EXT"),
}


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
#   t (float, unix s), i_ua, t_afe, t_tip, t_cham, t_ext, faults (int|None),
#   settle (float|None)

def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _f(v):
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):  # NaN or +/-inf is unavailable, never a reading
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
        except (ValueError, OverflowError):
            return None


# A faults value that was recorded but is not an integer. select() drops it.
FAULTS_INVALID = -1


def _meta_f(v):
    """Row metadata (settle_s): None when not recorded, the float when it is -
    inf/nan kept, and NaN for text - so select() can refuse what was supplied
    but unusable instead of reading it as absent (codex review 2026-09-11)."""
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _meta_int(v):
    if v in (None, ""):
        return None
    x = _int(v)
    return FAULTS_INVALID if x is None or x < 0 else x


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
            try:
                t = parse_utc(ts) if ts else None
            except ValueError:
                t = None          # kept, so select() counts it as bad time
            rows.append({
                "t": t,
                "i_ua": _f(r.get("o2_raw_ua", r.get("cell_ua"))),
                "t_afe": _f(r.get("t_afe_c")),
                "t_tip": _f(r.get("t_tip_c")),
                "t_cham": _f(r.get("t_chamber_c")),
                "t_ext": _f(r.get("t_ext_c")),
                "faults": _meta_int(r.get("faults")),
                "settle": _meta_f(r.get("settle_s")),
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
            "t_ext": _f(g("gas_t_ext_c")),
            "faults": _meta_int(g("gas_faults")),
            "settle": _meta_f(g("gas_settle_s")),
        })
    return rows


def select(rows, start=None, end=None, require=()):
    """Window, then drop the rows the firmware itself would not trust, and
    the rows missing any regressor named in `require` (e.g. "t_ext").

    Metadata that was recorded but is not a number (settle_s inf/nan/text,
    faults unparseable) is dropped as invalid, never read as absent: absent
    means not recorded, invalid means it cannot be trusted."""
    out = []
    dropped = {"window": 0, "settling": 0, "faulted": 0, "missing": 0,
               "bad_time": 0, "invalid_metadata": 0}
    for r in rows:
        if not _finite(r.get("t")):
            dropped["bad_time"] += 1
            continue
        if (start is not None and r["t"] < start) or \
           (end is not None and r["t"] > end):
            dropped["window"] += 1
            continue
        settle, faults = r.get("settle"), r.get("faults")
        if (settle is not None and not _finite(settle)) or \
           (faults is not None and faults < 0):
            dropped["invalid_metadata"] += 1
            continue
        if settle is not None and settle > 0:
            dropped["settling"] += 1
            continue
        if faults is not None and (faults & INVALIDATE_MASK):
            dropped["faulted"] += 1
            continue
        if r["i_ua"] is None or r["t_afe"] is None or \
           any(r.get(k) is None for k in require):
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


def _solve(a, b, tol=1e-12):
    """Gauss-Jordan on a square system; returns (x, inverse) or raises when a
    pivot falls below tol."""
    n = len(a)
    m = [list(map(float, a[i])) + [1.0 if i == j else 0.0 for j in range(n)]
         + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < tol:
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
    """X: rows with a leading 1.0 intercept column, y: list. Returns dict with
    beta, se, r2, rss, rms, n, p, fit.

    The slope columns are centred and scaled before solving. Raw normal
    equations on a regressor sitting at ~25 C lose a small wobble to float
    cancellation - which is how a frozen or near-frozen regressor used to pass
    the singularity check and come back with zero uncertainty. A column that
    does not move, or columns collinear to ~1e-10, raise ZeroDivisionError."""
    n, p = len(X), len(X[0])
    if any(row[0] != 1.0 for row in X):
        raise ValueError("ols needs a leading intercept column of 1.0")
    if n <= p:
        raise ZeroDivisionError("fewer rows than parameters")
    k = p - 1
    ybar = sum(y) / n
    means = [sum(row[j + 1] for row in X) / n for j in range(k)]
    sds = [math.sqrt(sum((row[j + 1] - means[j]) ** 2 for row in X) / n)
           for j in range(k)]
    if any(not (sd > 0) or not math.isfinite(sd) for sd in sds):
        raise ZeroDivisionError("a regressor does not move")
    Z = [[(row[j + 1] - means[j]) / sds[j] for j in range(k)] for row in X]
    beta_z, inv_z = [], []
    if k:
        ztz = [[sum(z[i] * z[j] for z in Z) for j in range(k)] for i in range(k)]
        zty = [sum(z[i] * (yy - ybar) for z, yy in zip(Z, y)) for i in range(k)]
        beta_z, inv_z = _solve(ztz, zty, tol=1e-10 * n)
    slopes = [bz / sd for bz, sd in zip(beta_z, sds)]
    b0 = ybar - sum(sl * m for sl, m in zip(slopes, means))
    beta = [b0] + slopes
    fit = [b0 + sum(sl * row[j + 1] for j, sl in enumerate(slopes)) for row in X]
    rss = sum((yy - ff) ** 2 for yy, ff in zip(y, fit))
    tss = sum((yy - ybar) ** 2 for yy in y)
    s2 = rss / (n - p)
    cov = [[s2 * inv_z[i][j] / (sds[i] * sds[j]) for j in range(k)] for i in range(k)]
    var_b0 = s2 / n + sum(means[i] * means[j] * cov[i][j]
                          for i in range(k) for j in range(k))
    se = [math.sqrt(max(var_b0, 0.0))] + [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)]
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

def _settle_ok(res):
    """Mark a finished fit ok - unless any number in it is non-finite, which
    is a failed fit however clean the arithmetic path looked."""
    bad = sorted(k for k, v in res.items()
                 if isinstance(v, float) and not math.isfinite(v))
    if bad:
        res["reasons"].append("non-finite result (%s)" % ", ".join(bad))
        res["verdict"] = "unevaluable"
    else:
        res["verdict"] = "ok"

def _check_options(tau, tau_grid, afe_ppm_k, min_span_k, min_n, max_corr):
    """Refuse nonsense thresholds. A NaN min_span_k compares False against every
    span, which silently resurrected the frozen-regressor acceptance (codex
    review 2026-09-11)."""
    if not (_finite(min_span_k) and min_span_k > 0):
        raise ValueError("min_span_k must be a finite number > 0, got %r" % (min_span_k,))
    if not (isinstance(min_n, int) and not isinstance(min_n, bool) and min_n >= 4):
        raise ValueError("min_n must be an integer >= 4, got %r" % (min_n,))
    if not (_finite(max_corr) and 0 < max_corr <= 1):
        raise ValueError("max_corr must be in (0, 1], got %r" % (max_corr,))
    if tau is not None and not (_finite(tau) and tau >= 0):
        raise ValueError("tau must be a finite number >= 0, got %r" % (tau,))
    if tau_grid is not None and (not tau_grid or not all(_finite(t) and t >= 0 for t in tau_grid)):
        raise ValueError("tau_grid must be non-empty finite values >= 0")
    if afe_ppm_k is not None and not _finite(afe_ppm_k):
        raise ValueError("afe_ppm_k must be finite, got %r" % (afe_ppm_k,))


def analyse(rows, mode="dummy", tau=None, tau_grid=None, afe_ppm_k=None,
            min_span_k=8.0, min_n=20, max_corr=0.95, cell_temp="chamber-lag"):
    """Return a result dict. result["verdict"] is "ok" or "unevaluable";
    result["reasons"] says why. Numbers are only present when they mean
    something. cell_temp picks the cell-mode regressor: "chamber-lag" or
    "ext" (the cell-side TMP117)."""
    if cell_temp not in CELL_TEMPS:
        raise ValueError("cell_temp must be one of %s" % ", ".join(CELL_TEMPS))
    _check_options(tau, tau_grid, afe_ppm_k, min_span_k, min_n, max_corr)
    res = {"mode": mode, "n": len(rows), "verdict": "unevaluable",
           "reasons": []}
    if not rows:
        res["reasons"].append("no usable rows")
        return res
    # Time is an input too - lag() integrates over it. One NaN timestamp
    # poisoned every tau > 0 and let tau = 0 win with finite, wrong numbers
    # (codex review 2026-09-11); duplicates freeze the lag. Refuse both, and
    # sort the rest rather than trust the caller's order.
    if any(not _finite(r.get("t")) for r in rows):
        res["reasons"].append("missing or non-finite timestamp in the rows")
        return res
    rows = sorted(rows, key=lambda r: r["t"])
    if any(b["t"] <= a["t"] for a, b in zip(rows, rows[1:])):
        res["reasons"].append("duplicate timestamps - every row must be a distinct sample")
        return res
    ts = [r["t"] for r in rows]
    i_ua = [r["i_ua"] for r in rows]
    t_afe = [r["t_afe"] for r in rows]
    if any(v is None or not math.isfinite(v) for v in i_ua + t_afe):
        res["reasons"].append("missing or non-finite current or T_AFE in the "
                              "rows - select() drops these; a direct call "
                              "must too")
        return res
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
        _settle_ok(res)
        return res

    if mode != "cell":
        raise ValueError("mode must be dummy or cell")

    key, col, label = CELL_TEMPS[cell_temp]
    res["cell_temp"], res["cell_label"] = cell_temp, label
    t_src = [r[key] for r in rows]
    if any(v is None or not math.isfinite(v) for v in t_src):
        res["reasons"].append("cell mode needs a finite %s on every row" % col)
        return res
    # A frozen cell regressor must refuse, not fit: 1,000 identical T_EXT rows
    # once came back verdict=ok at +101,021 ppm/K, float cancellation having
    # slipped past the singularity check (codex review 2026-09-11). Checked
    # before any fit, so --afe-ppm-k cannot bypass it.
    res["t_cell_src_span_k"] = span(t_src)
    if res["t_cell_src_span_k"] < min_span_k:
        res["reasons"].append("%s moved %.2f K, need %.1f K - no cell "
                              "excursion to fit on"
                              % (label, res["t_cell_src_span_k"], min_span_k))
        return res

    # Scan tau for the best fit unless one was given - but never for a
    # MEASURED cell temperature: picking tau on the same data is what moved
    # the 2026-09-11 AFE share from 124 to 457 ppm/K at unchanged residual.
    if tau is not None:
        grid = [tau]
    elif cell_temp == "ext":
        grid = [0]
    else:
        grid = tau_grid or [0] + list(range(60, 1801, 60))
    best = None
    unexcited = 0
    for tau_try in grid:
        tc = lag(ts, t_src, tau_try)
        # The gate above saw the SOURCE; the fit sees the lagged series, which a
        # long tau flattens to a constant (codex review 2026-09-11: +38,093
        # ppm/K at zero uncertainty). Gate what is actually fitted.
        if span(tc) < min_span_k:
            unexcited += 1
            continue
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
        if unexcited == len(grid):
            res["reasons"].append("%s moves less than %.1f K after the lag at every "
                                  "tau tried - nothing to fit on" % (label, min_span_k))
        else:
            res["reasons"].append("normal equations singular at every tau "
                                  "(%d more tau left %s unexcited)" % (unexcited, label))
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
        _settle_ok(res)
        return res

    if abs(res["corr_afe_cell"]) > max_corr:
        res["reasons"].append(
            "T_AFE and %s are collinear (r = %.3f, limit %.2f): "
            "one heat source moved both, so the AFE's share cannot be "
            "separated from the cell's. Only the combined slopes are reported. "
            "Do the dummy-load run, or an excursion that warms or cools one end "
            "only (the AFE end or the cell)." % (label, res["corr_afe_cell"], max_corr))
        res["verdict"] = "split-unevaluable"
        return res

    res["afe_ppm_k"] = f["beta"][1] / imean * 1e6
    res["afe_ppm_k_se"] = f["se"][1] / imean * 1e6
    res["cell_apparent_ppm_k"] = f["beta"][2] / imean * 1e6
    res["cell_apparent_ppm_k_se"] = f["se"][2] / imean * 1e6
    _settle_ok(res)
    return res


# --------------------------------------------------------------------------
# Reporting.

def report(res, dropped, out=sys.stdout):
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("o2p_tempco  mode=%s  verdict=%s" % (res["mode"], res["verdict"]))
    p("  rows used %d   dropped: window %d, settling %d, faulted %d, missing %d, "
      "bad time %d, invalid metadata %d"
      % (res["n"], dropped["window"], dropped["settling"], dropped["faulted"],
         dropped["missing"], dropped.get("bad_time", 0),
         dropped.get("invalid_metadata", 0)))
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
        label = res["cell_label"]
        p("  cell lag   tau = %d s   r(T_AFE, %s) = %.3f"
          % (res["tau_s"], label, res["corr_afe_cell"]))
        p("  combined   on T_AFE alone %+.0f +/- %.0f ppm/K; on %s "
          "alone %+.0f +/- %.0f ppm/K"
          % (res["combined_on_afe_ppm_k"], res["combined_on_afe_ppm_k_se"],
             label, res["combined_on_cell_ppm_k"],
             res["combined_on_cell_ppm_k_se"]))
        if "afe_ppm_k" in res:
            if res.get("afe_ppm_k_fixed"):
                p("  AFE tempco %+.0f ppm/K   (FIXED from --afe-ppm-k)"
                  % res["afe_ppm_k"])
            else:
                p("  AFE tempco %+.0f +/- %.0f ppm/K"
                  % (res["afe_ppm_k"], res["afe_ppm_k_se"]))
            p("  cell, apparent, per K of %s: "
              "%+.0f +/- %.0f ppm/K   (R2 %.3f, residual %.3f uA rms)"
              % (label, res["cell_apparent_ppm_k"],
                 res["cell_apparent_ppm_k_se"], res["r2"], res["rms_ua"]))
            if res["cell_temp"] == "ext":
                p("  (T_EXT reads the can wall; its coupling to the "
                  "electrolyte is still included)")
            else:
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
    if all(r.get("t_ext") is not None for r in rows):
        ax[1].plot(tt, [r["t_ext"] for r in rows], color="tab:olive",
                   label="T_EXT (cell side)")
    ax[1].set_xlabel("minutes")
    ax[1].set_ylabel("C")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def _arg_number(check, what):
    def parse(text):
        try:
            v = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError("not a number: %r" % text)
        if not (math.isfinite(v) and check(v)):
            raise argparse.ArgumentTypeError("must be %s, got %r" % (what, text))
        return v
    return parse


def _arg_min_n(text):
    try:
        v = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not an integer: %r" % text)
    if v < 4:
        raise argparse.ArgumentTypeError("must be >= 4, got %r" % text)
    return v


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
    ap.add_argument("--tau", type=_arg_number(lambda v: v >= 0, "finite and >= 0"), default=None,
                    help="cell lag in s; default scans 0..1800")
    ap.add_argument("--cell-temp", choices=sorted(CELL_TEMPS),
                    default="chamber-lag",
                    help="cell mode regressor: lagged chamber, or the "
                         "cell-side TMP117 (t_ext_c / gas_t_ext_c)")
    ap.add_argument("--afe-ppm-k", type=_arg_number(lambda v: True, "finite"), default=None,
                    help="cell mode: fix the AFE tempco to this measured value")
    ap.add_argument("--min-span-k", type=_arg_number(lambda v: v > 0, "finite and > 0"), default=8.0)
    ap.add_argument("--min-n", type=_arg_min_n, default=20)
    ap.add_argument("--max-corr", type=_arg_number(lambda v: 0 < v <= 1, "in (0, 1]"), default=0.95)
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
    require = ((CELL_TEMPS[args.cell_temp][0],)
               if args.mode == "cell" and args.cell_temp == "ext" else ())
    used, dropped = select(rows, start, end, require=require)
    res = analyse(used, mode=args.mode, tau=args.tau, afe_ppm_k=args.afe_ppm_k,
                  min_span_k=args.min_span_k, min_n=args.min_n,
                  max_corr=args.max_corr, cell_temp=args.cell_temp)
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
