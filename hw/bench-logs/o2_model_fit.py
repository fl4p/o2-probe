#!/usr/bin/env python3
"""Test the published oxygen model against a known truth: the probe is in AIR.

    ssh root@100.64.0.3 'curl -sg "http://127.0.0.1:8428/api/v1/export?\
        match[]={__name__=~\"gas_.*\",probe=\"3\"}&start=-5d"' > gas.ndjson
    python3 o2_model_fit.py --export gas.ndjson --plot o2-model-fit.png

WHY THIS IS A TEST AND NOT ANOTHER FIT. Every bench run since 2026-09-06 was
made in ambient air - room, oven vessel, freezer - so the DRY-basis oxygen
fraction was 20.946 %vol the whole time, at every temperature and every
humidity. Water vapour, which is the whole point of the dry basis, cannot
change it: the dry basis is defined water-free. So any spread in the published
number across the sweep is model error with a known sign and size, and no
reference instrument is needed to see it.

TWO THINGS ARE MEASURED, and they are independent.

  1. WHAT THE PROBE IS ACTUALLY RUNNING. The published `gas_pct_vol` is an
     exact function of the published `gas_cell_ua`, `gas_t_chamber_c` and
     `gas_rh_chamber_pct` through o2.c, so K, DIL_ALPHA and TEMPCO_PPM_K can
     be recovered from telemetry alone, without a Modbus read. The recovery is
     only believable when it closes: this prints the residual, and a residual
     above --recover-tol (0.02 %vol) means the config is NOT what came out and
     the numbers must not be quoted.

  2. HOW FAR THE MODEL IS FROM 20.946. Reported as SPREAD (max-min over the
     window) rather than as mean error, because the mean is dominated by the
     air point's own scale error - a recalibration, not a model property -
     while the spread is exactly what a wrong alpha or a missing tempco does.

WHAT IT REFUSES. Rows with settle_s > 0, with faults intersecting
O2P_FAULTS_INVALIDATE_O2 (0x6866), or taken while VREF was outside 2450-2550 mV
are dropped: the 2026-09-10 VREF collapses put the AFE somewhere else entirely.
Transients are dropped too (|dT/dt| over a +/-5 min window above --max-drift),
because the cell body lags the gas by ~18 min and a ramp is not a measurement
of anything here. A window that keeps fewer than --min-n rows, or spans less
than --min-span-k, is reported UNEVALUABLE and never given a number.
"""
import argparse, json, math, sys, datetime

INVALIDATE_O2 = 0x6866        # faults.h O2P_FAULTS_INVALIDATE_O2
C_AIR   = 0.20946             # o2.h O2P_C_AIR - the truth, dry basis
P_HPA   = 930.0               # o2.h O2P_P_HPA_DEFAULT, Rev A has no barometer
T_REF_C = 25.0                # arbitrary reference for the fitted gain
# d ln S / d ln C of the cell law at the air point; converts a log-domain
# regression slope into the CONCENTRATION-domain alpha the firmware consumes.
LOG_GAIN = C_AIR / ((1.0 - C_AIR) * math.log(1.0 / (1.0 - C_AIR)))

NEEDED = ("gas_cell_ua", "gas_t_chamber_c", "gas_rh_chamber_pct",
          "gas_faults", "gas_settle_s", "gas_vref_mv", "gas_pct_vol")


def p_sat_hpa(t_c):           # psychro.c, Magnus/Sonntag over water
    return 6.112 * math.exp(17.62 * t_c / (243.12 + t_c))


def load(path):
    """One probe's series. A mixed export is REFUSED, not merged.

    Keying on __name__ alone would let a second probe's samples overwrite the
    first's at matching timestamps and produce a confident number out of two
    instruments."""
    series = {}
    idents = set()
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            o = json.loads(line)
            m = dict(o["metric"])
            name = m.pop("__name__")
            idents.add(tuple(sorted(m.items())))
            d = series.setdefault(name, {})
            for t, v in zip(o["timestamps"], o["values"]):
                d[t] = v
    if len(idents) > 1:
        sys.exit("unevaluable: export holds %d distinct label sets (%s); "
                 "re-export one probe" %
                 (len(idents), " | ".join(str(dict(i)) for i in sorted(idents))))
    missing = [n for n in NEEDED if n not in series]
    if missing:
        sys.exit("unevaluable: export is missing " + ", ".join(missing))
    rows = []
    for t in sorted(series["gas_faults"]):
        r = {n[4:]: series[n].get(t) for n in series}
        r["t"] = t / 1000.0
        rows.append(r)
    return rows


def usable(r, vref_lo, vref_hi):
    # settle_s is in the REQUIRED list: a missing one used to read as zero,
    # which turns "we do not know whether the cell was settling" into "it was
    # not", the exact substitution this file exists to refuse.
    for k in ("cell_ua", "t_chamber_c", "rh_chamber_pct", "faults", "vref_mv",
              "settle_s"):
        if r.get(k) is None:
            return False
    return (int(r["faults"]) & INVALIDATE_O2 == 0
            and r["settle_s"] == 0
            and vref_lo <= r["vref_mv"] <= vref_hi)


def mark_steady(rows, max_drift):
    """|dT/dt| over a centred +/-5 min window, K/min. Ramps are not data here."""
    ts = [r["t"] for r in rows]
    T = [r["t_chamber_c"] for r in rows]
    out = []
    for i in range(len(rows)):
        j = k = i
        while j > 0 and ts[i] - ts[j - 1] < 300:
            j -= 1
        while k < len(rows) - 1 and ts[k + 1] - ts[i] < 300:
            k += 1
        if k > j and ts[k] - ts[j] > 120:
            # RANGE over the window, not |T[k]-T[j]|. Endpoints alone pass a
            # symmetric excursion of any size - an 80 K spike whose ends match
            # scored zero drift and was called steady.
            span = max(T[j:k + 1]) - min(T[j:k + 1])
            out.append(span / ((ts[k] - ts[j]) / 60.0) <= max_drift)
        else:
            out.append(False)      # cannot judge -> not steady, never silently in
    return out


# FW 0x001E: the conversion applies (T_cell/T_cal)^0.75 before the linear
# TEMPCO residual, and both use the cell-side T_EXT (else chamber) instead of
# the chamber (o2.c o2p_cell_t_law_gain, sampler_logic.h o2p_cell_temperature).
CELL_LAW_FW = 0x001E
CELL_T_EXPONENT = 0.75


def cell_t_terms(r):
    """(law, T for the linear residual) for one row, as the image that produced
    it computed them - decided per row from the probe's own gas_fw_version, so a
    window spanning a flash is modelled as what actually ran.

    T_cal is not in telemetry. The law is referenced to T_REF_C instead, and
    the constant factor (T_REF/T_cal)^0.75 lands in the recovered K: K from a
    0x001E window is therefore K at T_REF_C, not at the air point. A row with
    no gas_fw_version is treated as pre-0x001E and SAYS nothing about which
    image ran; recovery residual is what exposes a wrong guess."""
    fw = r.get("fw_version")
    if fw is None or int(fw) < CELL_LAW_FW:
        return 1.0, r["t_chamber_c"]
    t = r.get("t_ext_c")
    if t is None:
        t = r["t_chamber_c"]       # the firmware's own fallback
    law = ((t + 273.15) / (T_REF_C + 273.15)) ** CELL_T_EXPONENT
    return law, t


def published(I_na, t_c, rh, K, alpha, tempco, law=1.0, t_res=None):
    """o2.c o2p_dry_fraction_from_current(), in percent. P_cal == P_meas on Rev A.
    law / t_res come from cell_t_terms(); the defaults are the pre-0x001E image."""
    f = (P_HPA - rh / 100.0 * p_sat_hpa(t_c)) / P_HPA
    f_eff = 1.0 - alpha * (1.0 - f)
    t_res = t_c if t_res is None else t_res
    s = I_na / law / (1.0 + tempco * (t_res - T_REF_C))
    return (1.0 - math.exp(-s / K)) / f_eff * 100.0


def fit(rows, target, free, p0, bounds):
    from scipy.optimize import least_squares
    import numpy as np
    I = np.array([r["cell_ua"] for r in rows]) * 1000.0
    T = np.array([r["t_chamber_c"] for r in rows])
    H = np.array([r["rh_chamber_pct"] for r in rows])
    y = np.array(target, dtype=float)
    # What the image that produced each row did with temperature (cell_t_terms).
    # The dilution term stays on the chamber in every era: p_w is the SHT45's.
    law, T_res = (np.array(v) for v in zip(*(cell_t_terms(r) for r in rows)))

    def model(p):
        K, alpha, tc = free(p)
        pw = H / 100.0 * 6.112 * np.exp(17.62 * T / (243.12 + T))
        f_eff = 1.0 - alpha * (1.0 - (P_HPA - pw) / P_HPA)
        s = I / law / (1.0 + tc * (T_res - T_REF_C))
        return (1.0 - np.exp(-s / K)) / f_eff * 100.0

    sol = least_squares(lambda p: model(p) - y, p0, bounds=bounds)
    # A parameter sitting on its bound is not a measurement; the caller must
    # be able to say so rather than print it like one.
    at_bound = [i for i, v in enumerate(sol.x)
                if (abs(v - bounds[0][i]) <= 1e-9 * max(1.0, abs(v))
                    or abs(v - bounds[1][i]) <= 1e-9 * max(1.0, abs(v)))]
    return sol.x, model(sol.x), y, at_bound


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--export", required=True)
    a.add_argument("--plot")
    a.add_argument("--max-drift", type=float, default=0.10, help="K/min")
    a.add_argument("--min-n", type=int, default=40)
    a.add_argument("--min-span-k", type=float, default=8.0)
    a.add_argument("--recover-tol", type=float, default=0.02, help="percent by volume")
    a.add_argument("--vref-lo", type=float, default=2450.0)
    a.add_argument("--vref-hi", type=float, default=2550.0)
    a.add_argument("--iso-span-k", type=float, default=0.5,
                   help="a segment is isothermal below this T span, K")
    a.add_argument("--iso-pw-span", type=float, default=0.005,
                   help="minimum p_w/P span for an alpha to be identified")
    a.add_argument("--iso-min-n", type=int, default=15)
    a.add_argument("--iso-show", type=int, default=3,
                   help="longest N windows to print per temperature cluster")
    a.add_argument("--drift-reject", type=float, default=2.0,
                   help="percent per hour above which a window is called out")
    a.add_argument("--gap-s", type=float, default=1200.0,
                   help="a gap this long starts a new window")
    o = a.parse_args()

    import numpy as np
    rows = [r for r in load(o.export) if usable(r, o.vref_lo, o.vref_hi)]
    if not rows:
        sys.exit("unevaluable: no usable rows")
    steady = mark_steady(rows, o.max_drift)

    # --- 1. what the probe is running, window by window --------------------
    print("RECOVERED CONFIG  (from published pct_vol; a residual above "
          f"{o.recover_tol} %vol means these numbers are not the probe's)")
    print(f"  {'window (UTC)':27s} {'n':>5s} {'T span':>13s} {'RH span':>9s} "
          f"{'K nA':>8s} {'alpha':>6s} {'ppm/K':>7s} {'resid':>7s}")
    have_pub = [r for r in rows if r.get("pct_vol") is not None]
    windows, cur = [], []
    for r in have_pub:
        if cur and r["t"] - cur[-1]["t"] > o.gap_s:
            windows.append(cur)
            cur = []
        cur.append(r)
    if cur:
        windows.append(cur)
    recovered = []
    plots = []
    for w in windows:
        if len(w) < o.min_n:
            continue
        T = [r["t_chamber_c"] for r in w]
        H = [r["rh_chamber_pct"] for r in w]
        p, m, y, ab = fit(w, [r["pct_vol"] for r in w], lambda p: (p[0], p[1], p[2]),
                      [4.2e5, 0.5, 0.001], ([3e5, 0.0, -0.005], [6e5, 2.0, 0.005]))
        rms = float(np.sqrt(((m - y) ** 2).mean()))
        s = datetime.datetime.fromtimestamp(w[0]["t"], datetime.UTC)
        e = datetime.datetime.fromtimestamp(w[-1]["t"], datetime.UTC)
        flat = (max(T) - min(T) < 3.0) or (max(H) - min(H) < 5.0)
        note = "  (flat: alpha/tempco unidentified)" if flat else ""
        if ab:
            note += "  (fit on a bound: %s - not a measurement)" % ",".join(
                ["K", "alpha", "tempco"][i] for i in ab)
        if rms > o.recover_tol:
            note = f"  UNEVALUABLE: residual {rms:.3f} %vol, config not recovered"
        print(f"  {s:%m-%d %H:%M}..{e:%H:%M}{'':11s} {len(w):5d} "
              f"{min(T):5.1f}..{max(T):5.1f} {min(H):3.0f}..{max(H):3.0f} "
              f"{p[0]:8.0f} {p[1]:6.3f} {p[2]*1e6:7.0f} {rms:7.4f}{note}")
        # rms and the bound flag are CARRIED, and section 2 consults them. A
        # window whose config could not be recovered must not reappear two
        # sections later under a confident "probe ran ..." line.
        recovered.append((s, e, p, rms, flat, bool(ab)))

    # --- 2. how far the model is from 20.946, on steady rows ---------------
    # PER CONFIG ERA. K moved 3.5 % across the 2026-09-08 rework, so pooling
    # the eras would charge a changed air point to the model.
    eras = []
    rejected = [(s_, e_, rms_) for s_, e_, p_, rms_, f_, b_ in recovered
                if rms_ > o.recover_tol]
    for s_, e_, rms_ in rejected:
        print(f"\nMODEL vs TRUTH {s_:%m-%d %H:%M}..{e_:%m-%d %H:%M}: SKIPPED, "
              f"config recovery failed (residual {rms_:.3f} %vol) - the probe's "
              "own constants are unknown here, so there is nothing to compare")
    for s_, e_, p_, rms_, flat_, bound_ in recovered:
        if rms_ > o.recover_tol:
            continue
        key = (round(p_[0] / 1000.0), round(p_[1], 2), round(p_[2] * 1e6))
        # Same config = same K (to 1 uA), same alpha (to 0.05) and same tempco
        # (to 100 ppm/K). All three, or a window that changed only alpha would
        # be silently pooled with the one before it and its spread charged to
        # the model.
        if (eras and abs(eras[-1][0][0] - key[0]) <= 1
                and abs(eras[-1][0][1] - key[1]) <= 0.05
                and abs(eras[-1][0][2] - key[2]) < 100):
            eras[-1][2] = e_
        else:
            eras.append([key, s_, e_])
    if not eras:
        eras = [[None, datetime.datetime.fromtimestamp(rows[0]["t"], datetime.UTC),
                 datetime.datetime.fromtimestamp(rows[-1]["t"], datetime.UTC)]]
    for key, s_, e_ in eras:
        lo, hi = s_.timestamp(), e_.timestamp()
        st = [r for r, k in zip(rows, steady) if k and lo <= r["t"] <= hi]
        if len(st) < o.min_n:
            print(f"\nMODEL vs TRUTH {s_:%m-%d %H:%M}..{e_:%m-%d %H:%M}: "
                  f"UNEVALUABLE, {len(st)} steady rows (need {o.min_n})")
            continue
        T = np.array([r["t_chamber_c"] for r in st])
        if T.max() - T.min() < o.min_span_k:
            print(f"\nMODEL vs TRUTH {s_:%m-%d %H:%M}..{e_:%m-%d %H:%M}: "
                  f"UNEVALUABLE, T span {T.max()-T.min():.1f} K "
                  f"(need {o.min_span_k})")
            continue
        cfg = ("K=%d nA alpha=%.3f tempco=%+d ppm/K" %
               (key[0] * 1000, key[1], key[2])) if key else "config unknown"
        print(f"\nMODEL vs TRUTH ({C_AIR*100:.3f} %vol dry, the probe is in air)"
              f"   {s_:%m-%d %H:%M}..{e_:%m-%d %H:%M} UTC   probe ran {cfg}")
        print(f"  steady n={len(st)}  T {T.min():.1f}..{T.max():.1f} C  "
              f"RH {min(r['rh_chamber_pct'] for r in st):.0f}.."
              f"{max(r['rh_chamber_pct'] for r in st):.0f} %")
        pub = np.array([r["pct_vol"] for r in st if r.get("pct_vol") is not None])
        if len(pub):
            print(f"  {'published gas_pct_vol':38s} {pub.min():6.2f}..{pub.max():6.2f}"
                  f" %vol   spread {100*(pub.max()-pub.min())/C_AIR/100:5.2f} %"
                  f"   (n={len(pub)} of {len(st)}: pct_vol is absent when the "
                  "probe refused the conversion)")
        variants = [("alpha=1    tempco=0   (defaults)", 1.0, 0.0),
                    ("alpha=0.40 tempco=0   (o2.h)", 0.402, 0.0),
                    ("alpha=0    tempco=0   (no vapour corr)", 0.0, 0.0)]
        curves = {}
        for tag, al, tc in variants:
            p_, m, _, _ab = fit(st, [C_AIR * 100] * len(st),
                                lambda p, al=al, tc=tc: (p[0], al, tc),
                                [4.2e5], ([3e5], [6e5]))
            curves[tag] = m
            print(f"  {tag:38s} {m.min():6.2f}..{m.max():6.2f} %vol   "
                  f"spread {100*(m.max()-m.min())/C_AIR/100:5.2f} %   "
                  f"rms {100*np.sqrt(((m-C_AIR*100)**2).mean())/C_AIR/100:5.2f} %   "
                  f"(K={p_[0]:.0f})")
        p_, m, _, ab_ = fit(st, [C_AIR * 100] * len(st),
                            lambda p: (p[0], p[1], p[2]), [4.2e5, 0.45, 0.0012],
                            ([3e5, 0.0, -0.005], [6e5, 2.0, 0.005]))
        curves["best fit"] = m
        print(f"  {'BEST FIT K, alpha, tempco':38s} {m.min():6.2f}..{m.max():6.2f} %vol   "
              f"spread {100*(m.max()-m.min())/C_AIR/100:5.2f} %   "
              f"rms {100*np.sqrt(((m-C_AIR*100)**2).mean())/C_AIR/100:5.2f} %")
        if ab_:
            print("      WARNING: " + ",".join(["K", "alpha", "tempco"][i]
                  for i in ab_) + " sits on a fit bound - read it as "
                  "unidentified, not as a value")
        print(f"      K={p_[0]:.0f} nA   alpha={p_[1]:.3f}   "
              f"tempco={p_[2]*1e6:+.0f} ppm/K   -- alpha and tempco are CORRELATED "
              "here; only an isothermal RH change identifies alpha alone")
        plots.append((s_, e_, st, curves))

    # --- 3. alpha from isothermal segments only ----------------------------
    # A segment with T pinned to < --iso-span-k cannot hide a temperature
    # term, so its slope of ln(I) against p_w/P IS the dilution response.
    #
    # EVERY maximal isothermal window is enumerated, not a greedy partition of
    # the export. A greedy scan consumes each window and restarts after it, so
    # its answer depends on where the export happens to begin: on this data,
    # starting at 06:30 instead of midnight moved alpha from 0.398 to 0.496,
    # and starting at 07:00 left no qualifying segment at all. The spread
    # across windows is reported as PROCEDURE SPREAD, because a regression's
    # own standard error describes one chosen window and not the choosing.
    print(f"\nALPHA FROM ISOTHERMAL SEGMENTS (T span < {o.iso_span_k} K, "
          f"p_w/P span > {o.iso_pw_span*100:.1f} %, n >= {o.iso_min_n})")
    ts_all = [r["t"] for r in rows]
    T_all = np.array([r["t_chamber_c"] for r in rows])
    H_all = np.array([r["rh_chamber_pct"] for r in rows])
    I_all = np.array([r["cell_ua"] for r in rows]) * 1000.0
    x_all = (H_all / 100.0 * 6.112
             * np.exp(17.62 * T_all / (243.12 + T_all)) / P_HPA)

    def reach(i):
        """Largest j with T range over [i..j] within the guard and no gap."""
        j = i
        lo = hi = T_all[i]
        while j + 1 < len(rows) and ts_all[j + 1] - ts_all[j] <= o.gap_s:
            nlo, nhi = min(lo, T_all[j + 1]), max(hi, T_all[j + 1])
            if nhi - nlo > o.iso_span_k:
                break
            lo, hi = nlo, nhi
            j += 1
        return j

    def slope(seg, drift):
        n = seg.stop - seg.start
        cols = [np.ones(n), x_all[seg]]
        if drift:
            cols.append((np.array(ts_all[seg]) - ts_all[seg.start]) / 3600.0)
        A = np.vstack(cols).T
        y = np.log(I_all[seg])
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        res = y - A @ beta
        cov = (res ** 2).sum() / (n - A.shape[1]) * np.linalg.inv(A.T @ A)
        return -beta[1] / LOG_GAIN, math.sqrt(cov[1][1]) / LOG_GAIN, \
            (beta[2] * 100 if drift else None)

    # one maximal window per right edge, the longest of them
    best = {}
    for i in range(len(rows)):
        j = reach(i)
        if j - i + 1 >= o.iso_min_n and j not in best:
            best[j] = i
    segs = []
    for j, i in sorted(best.items()):
        seg = slice(i, j + 1)
        if x_all[seg].max() - x_all[seg].min() < o.iso_pw_span:
            continue
        a_nd, se_nd, _ = slope(seg, False)
        a_d, se_d, dr = slope(seg, True)
        segs.append((T_all[seg].mean(), i, j, seg.stop - seg.start,
                     x_all[seg].min(), x_all[seg].max(), a_nd, se_nd, a_d, dr))
    if not segs:
        print("  none: no window held temperature still while humidity moved")
    else:
        clusters = {}
        for srow in segs:
            clusters.setdefault(round(srow[0] / 2.0) * 2, []).append(srow)
        for tk in sorted(clusters):
            cl = clusters[tk]
            longest = max(cl, key=lambda r: r[3])
            alphas = [r[6] for r in cl]
            print(f"  ~{tk:5.0f} C  {len(cl):3d} maximal window(s)  "
                  f"PROCEDURE SPREAD alpha {min(alphas):6.3f}..{max(alphas):6.3f}")
            for srow in sorted(cl, key=lambda r: -r[3])[:o.iso_show]:
                _, i, j, n, xlo, xhi, a_nd, se_nd, a_d, dr = srow
                print(f"      {datetime.datetime.fromtimestamp(ts_all[i], datetime.UTC):%m-%d %H:%M}"
                      f"..{datetime.datetime.fromtimestamp(ts_all[j], datetime.UTC):%H:%M}"
                      f"  n={n:5d}  p_w/P {xlo*100:5.2f}..{xhi*100:5.2f} %  "
                      f"alpha={a_nd:6.3f} +/- {se_nd:.3f}   "
                      f"with drift term {a_d:6.3f} ({dr:+6.2f} %/h)")
            if longest[9] is not None and abs(longest[9]) > o.drift_reject:
                print(f"      REJECTED at this temperature: the longest window "
                      f"carries {longest[9]:+.2f} %/h of drift, above "
                      f"--drift-reject {o.drift_reject} %/h - the drift is "
                      f"larger than the dilution signal")
    print("  NOTE: a standard error here is one window's regression. Read the "
          "procedure spread as the uncertainty of the MEASUREMENT, and neither "
          "as the uncertainty of alpha itself: nothing in this section "
          "controls cell-body temperature, heater duty or the RH sensor's own "
          "error, all of which move with humidity in a heated vessel.")

    if o.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        if not plots:
            print("no evaluable era to plot")
        else:
            fig, axes = plt.subplots(2, len(plots), squeeze=False,
                                     figsize=(5.6 * len(plots), 7.4))
            for col, (s_, e_, st, curves) in enumerate(plots):
                T = np.array([r["t_chamber_c"] for r in st])
                tp = np.array([r["t_chamber_c"] for r in st
                               if r.get("pct_vol") is not None])
                pub = np.array([r["pct_vol"] for r in st
                                if r.get("pct_vol") is not None])
                ax = axes[0][col]
                ax.axhline(C_AIR * 100, color="k", lw=1.2, ls="--",
                           label="truth 20.946 %vol (ambient air)")
                if len(pub):
                    ax.plot(tp, pub, ".", ms=3, alpha=.45,
                            label="published gas_pct_vol")
                for tag, c in (("alpha=1    tempco=0   (defaults)", "tab:orange"),
                               ("best fit", "tab:green")):
                    if tag in curves:
                        ax.plot(T, curves[tag], ".", ms=3, alpha=.45,
                                color=c, label=tag)
                ax.set_title(f"{s_:%m-%d %H:%M}..{e_:%m-%d %H:%M} UTC", fontsize=9)
                ax.set_ylabel("dry-basis oxygen, %vol")
                ax.legend(fontsize=7)
                ax.grid(alpha=.25)
                ax = axes[1][col]
                ax.axhline(0, color="k", lw=1.2, ls="--")
                ax.plot(T, curves["best fit"] - C_AIR * 100, ".", ms=3,
                        alpha=.45, color="tab:green")
                ax.set_xlabel("chamber temperature, C")
                ax.set_ylabel("best-fit residual, %vol")
                ax.grid(alpha=.25)
            fig.suptitle("o2-probe: the model against a known truth "
                         "(the probe was in air the whole time)", fontsize=11)
            fig.tight_layout()
            fig.savefig(o.plot, dpi=140)
            print(f"\nwrote {o.plot}")


if __name__ == "__main__":
    main()
