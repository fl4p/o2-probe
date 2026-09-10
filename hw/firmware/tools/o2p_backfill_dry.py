#!/usr/bin/env python3
"""Backfill a dry-basis oxygen series into VictoriaMetrics from the recorded raw.

    ssh -L 8428:127.0.0.1:8428 root@compostlab.fabi.me &
    python3 o2p_backfill_dry.py --dry-run
    python3 o2p_backfill_dry.py --write

WHY THIS IS ADDITIVE AND NOT AN OVERWRITE. `gas_pct_vol` is what the probe
actually published; it is evidence, and a corrected value written over it
would be unauditable and - because VictoriaMetrics appends rather than
replaces - would leave two samples at one timestamp. This writes a NEW series
and touches nothing that exists.

WHY IT IS COMPUTED FROM `gas_cell_ua` AND NOT FROM `gas_pct_vol`. The model is
then era-independent: it does not care which firmware produced the sample, so
one script covers history and everything after the reflash.

WHAT IT DOES NOT FIX, stated because the number looks authoritative and is not:

  * SCALE, unless you pass --k. The DEFAULT K (425557 nA, constant to 0.015 %
    over 3573 bench samples spanning RH 33.6-65.1) came from an air point
    taken under the pre-2026-09-06 assumption that the calibration air was
    DRY, so it is 2-3 % high. That was never arithmetic to fix - it needed a
    recalibration (O2-HUMIDITY-CORRECTION 3b) - and a later config migration
    zeroed the air point deliberately, which is why the probe now publishes
    CAL_DEFAULT and no %vol at all. After a fresh air point, pass the new K:
    it is NOT a register, the firmware derives it per conversion as
    (CAL_AIR_NA - CAL_ZERO_NA) / ln(1/(1 - CAL_AIR_FRAC)), o2.c:264.
  * DRIFT, which --k cannot fix either. A K measured today, applied to
    current recorded weeks ago, assumes the cell's sensitivity did not move
    in between. Nothing here tests that, and a two-point check separated in
    time is the only thing that would.
  * STRENGTH. --response (aka --alpha) is the fraction of the modelled
    dilution the cell actually shows. Default 1.0 = what the firmware did
    before DIL_ALPHA existed. Section 12's near-isothermal step suggested
    ~0.60; the fuller 2026-09-07 sweep gives alpha = 0.402 +/- 0.046 and that
    is what register 0x0045 now carries. Prefer the probe's own DIL_ALPHA so
    the backfill and the firmware agree; none of the three is validated.
  * TEMPERATURE. tempco is 0 in firmware by design, and section 11 could not
    identify one. Nothing here supplies it.
"""
import argparse, json, math, sys, urllib.request

# Defaults describe the PRE-RECALIBRATION era and are kept only so an old
# invocation reproduces its old numbers. Both are now overridable, because
# after a fresh air point neither is the probe's constant any more: K is
# derived per conversion from CAL_AIR_NA, CAL_ZERO_NA and CAL_AIR_FRAC
# (o2.c:264), so a hardcoded copy goes stale the moment anyone calibrates.
# tools/../../bench cal_air.py prints the K to pass here.
P_HPA_DEFAULT = 930.0      # ASSUMED_P_HPA; Rev A has no barometer
K_NA_DEFAULT  = 425557.0   # recovered from the pre-2026-09-06 published pairs
SRC   = ("gas_cell_ua", "gas_rh_chamber_pct", "gas_t_chamber_c")
# Fetched to EXCLUDE, not to compute with. See --drop-settling.
GATE  = ("gas_settle_s", "gas_faults")
O2P_F_SETTLING = 0x0001

def es(t):             # Magnus/Sonntag, hPa
    return 6.112 * math.exp(17.62 * t / (243.12 + t))

def fetch(base, match):
    q = urllib.parse.urlencode({"match[]": match, "start": "0"})
    with urllib.request.urlopen(base + "/api/v1/export?" + q, timeout=120) as r:
        return [json.loads(l) for l in r.read().splitlines() if l.strip()]

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--url", default="http://127.0.0.1:8428")
    a.add_argument("--metric", default="gas_o2_dry_pct")
    a.add_argument("--response", type=float, default=1.0,
                   help="fraction of the modelled dilution the cell shows (1.0 = firmware)")
    a.add_argument("--k", type=float, default=K_NA_DEFAULT,
                   help="cell constant K in nA, as o2.c:264 derives it: "
                        "(CAL_AIR_NA - CAL_ZERO_NA) / ln(1/(1 - CAL_AIR_FRAC)). "
                        "Read it off the probe after calibrating; the default "
                        "is the stale pre-2026-09-06 constant.")
    a.add_argument("--p-hpa", type=float, default=P_HPA_DEFAULT,
                   help="total pressure for the dilution term, hPa")
    a.add_argument("--tempco", type=float, default=0.0,
                   help="cell tempco in %%/K, applied as a DIFFERENTIAL "
                        "correction about --tempco-ref. 0 = none, which is "
                        "what the firmware does (O2P_TEMPCO_DEFAULT). The "
                        "jointly fitted value on this cell is +0.220 %%/K - "
                        "read the warning this tool prints before using it.")
    a.add_argument("--tempco-ref", type=float, default=None,
                   help="reference temperature in C for --tempco. Default: the "
                        "MEDIAN chamber temperature of the data, which removes "
                        "temperature-driven variation without moving the mean - "
                        "the absolute scale stays owned by K.")
    a.add_argument("--drop-settling", action="store_true",
                   help="omit every sample taken while the cell was settling: "
                        "SETTLE_S != 0 or the SETTLING fault bit set. The cell "
                        "needs up to 15 min after a bias interruption, and the "
                        "FIRMWARE ITSELF refuses O2_COMP for exactly this "
                        "reason (O2P_FAULTS_INVALIDATE_O2_COMP includes "
                        "O2P_F_SETTLING) - a current measured mid-warm-up is "
                        "not an equilibrium current.")
    a.add_argument("--alpha", type=float, default=None,
                   help="alias for --response, named as the probe names it "
                        "(DIL_ALPHA, register 0x0045)")
    a.add_argument("--write", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    o = a.parse_args()
    if not (o.write or o.dry_run):
        sys.exit("refusing to guess: pass --dry-run or --write")
    if o.alpha is not None:
        if o.response != 1.0 and o.response != o.alpha:
            sys.exit("--alpha and --response are the same knob and disagree; "
                     "pass one")
        o.response = o.alpha
    # FINITE, not merely positive. `inf` satisfies k > 0, and then
    # 1 - exp(-s/inf) is exactly 0.0, which passes the 0..30 %vol plausibility
    # check below and imports a series of confident 0.000 %vol - a manufactured
    # measurement, which is the one thing this tool must never produce. `nan`
    # fails every comparison instead, so it slips through as "not out of range"
    # and dies later on min([]) with an empty-series traceback. Found by
    # review 2026-09-10.
    if not (math.isfinite(o.k) and o.k > 0.0):
        sys.exit("K must be a finite positive number of nA; got %r" % o.k)
    if not (math.isfinite(o.response) and 0.0 <= o.response <= 2.0):
        sys.exit("--response/--alpha must be finite in 0..2 (DIL_ALPHA's own "
                 "range, O2P_DIL_ALPHA_MAX); got %r" % o.response)
    if not (math.isfinite(o.p_hpa) and 500.0 <= o.p_hpa <= 1200.0):
        sys.exit("--p-hpa %r is not a plausible total pressure" % o.p_hpa)
    if not (math.isfinite(o.tempco) and -5.0 <= o.tempco <= 5.0):
        sys.exit("--tempco %r is not a plausible %%/K" % o.tempco)
    print("K = %.1f nA   P = %.1f hPa   response/alpha = %.3f   tempco = "
          "%+.3f %%/K" % (o.k, o.p_hpa, o.response, o.tempco), file=sys.stderr)
    if o.tempco != 0.0 or o.response < 0.55:
        print(
"WARNING, and it is this repo's own reviewed conclusion, not a caveat I am\n"
"adding: O2-HUMIDITY-CORRECTION.md section 14 reviewed the joint\n"
"alpha=0.442 / tempco=+0.220 %/K model adversarially and returned DO NOT\n"
"FLASH, DO NOT BACKFILL. Two reasons, both reproduced by the author:\n"
"  * At pile conditions the break-even is alpha = 1/(1+f) = 0.546. The\n"
"    fitted 0.442 sits BELOW it, so a FULL dilution correction there is\n"
"    worse than none (+11.40 % against -7.50 %). Passing the fitted alpha\n"
"    is the right side of that - alpha=1.0 was the worst available choice -\n"
"    but the margin is not the point:\n"
"  * the effective sample size is about 26, not 6505. A delete-block\n"
"    jackknife gives +/-0.09 to 0.10 on alpha, ten times the published\n"
"    +/-0.010, and that interval STRADDLES 0.546. So the honest statement\n"
"    is not 'this is wrong' but 'this data cannot tell you whether it helps\n"
"    or hurts'.\n"
"  * +0.220 %/K rests on ONE warming ramp over 6.5 K and 17 hPa. A pile is\n"
"    30 K and 158 hPa beyond that, a deliberate isobaric sweep has never\n"
"    been run, and leg transfer is inconsistent: the model interpolates one\n"
"    day's trajectory and is NOT a demonstrated calibration.\n"
"Use it knowingly, keep it in its own metric, and do not read absolute\n"
"values off the result.\n", file=sys.stderr)

    series = {}
    for name in SRC + (GATE if o.drop_settling else ()):
        for d in fetch(o.url, '{__name__="%s"}' % name):
            lbl = {k: v for k, v in d["metric"].items() if k != "__name__"}
            key = tuple(sorted(lbl.items()))
            series.setdefault(key, {})[name] = dict(zip(d["timestamps"], d["values"]))

    total = 0
    for key, m in series.items():
        if not all(n in m for n in SRC):
            print("skip %s: missing %s" % (dict(key), set(SRC) - set(m)), file=sys.stderr)
            continue
        ts = sorted(set(m[SRC[0]]) & set(m[SRC[1]]) & set(m[SRC[2]]))

        # THE WARM-UP GATE. Dropped BEFORE the tempco reference is computed, so
        # a long settling stretch cannot drag the reference temperature either.
        dropped_settling = 0
        if o.drop_settling:
            keep = []
            for t in ts:
                st = m.get("gas_settle_s", {}).get(t)
                fl = m.get("gas_faults", {}).get(t)
                # UNEVALUABLE IS NOT OK: if we cannot see whether the cell was
                # settling at this timestamp, we do not get to assume it wasn't.
                if st is None or fl is None:
                    dropped_settling += 1
                    continue
                if st != 0 or (int(fl) & O2P_F_SETTLING):
                    dropped_settling += 1
                    continue
                keep.append(t)
            ts = keep

        # Differential tempco reference: the median T of what SURVIVED the gate.
        # A median, not a mean, so one warm excursion cannot move it, and the
        # correction is zero-mean by construction - the absolute scale stays
        # owned by K rather than being silently re-scaled by an unmeasured
        # coefficient.
        t_ref = o.tempco_ref
        if t_ref is None:
            temps = sorted(m[SRC[2]][t] for t in ts
                           if -40.0 < m[SRC[2]][t] < 80.0)
            t_ref = temps[len(temps) // 2] if temps else 0.0

        out_t, out_v = [], []
        for t in ts:
            s, rh, tc = m[SRC[0]][t], m[SRC[1]][t], m[SRC[2]][t]
            if s <= 0 or not (0.0 < rh <= 100.0) or not (-40.0 < tc < 80.0):
                continue                       # unevaluable is skipped, never defaulted
            pw = rh / 100.0 * es(tc)
            if pw >= o.p_hpa * 0.5:
                continue
            f = (o.p_hpa - pw) / o.p_hpa
            f = 1.0 - (1.0 - f) * o.response
            # TEMPCO on the CURRENT, before the cell law, because that is where
            # the coefficient was fitted - a %/K on the signal, not on the
            # derived fraction. Guarded so a bad pair cannot produce a negative
            # or infinite current.
            s_corr = s / (1.0 + o.tempco / 100.0 * (tc - t_ref))
            if not (math.isfinite(s_corr) and s_corr > 0.0):
                continue
            c_wet = 1.0 - math.exp(-s_corr * 1000.0 / o.k)
            c_dry = c_wet / f * 100.0
            if not (0.0 <= c_dry <= 30.0):
                continue
            out_t.append(t); out_v.append(round(c_dry, 4))
        if o.drop_settling:
            print("   dropped %d sample(s) taken while the cell was settling; "
                  "tempco reference %.2f C" % (dropped_settling, t_ref),
                  file=sys.stderr)
        lbl = dict(key); lbl["__name__"] = o.metric
        line = json.dumps({"metric": lbl, "values": out_v, "timestamps": out_t})
        if not out_v:
            # Every sample was unevaluable. Say so and write nothing for this
            # series - an empty import is not a failure, but it must not look
            # like a successful one, and it must not crash on min([]).
            print("%-16s      0 samples - every point was unevaluable "
                  "(no import for this series)" % lbl.get("device"),
                  file=sys.stderr)
            continue
        print("%-16s %6d samples  %.3f..%.3f %%vol"
              % (lbl.get("device"), len(out_v), min(out_v), max(out_v)))
        total += len(out_v)
        if o.write:
            req = urllib.request.Request(o.url + "/api/v1/import",
                                         data=line.encode(), method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
    print("%s %d samples as %s (response=%.2f)"
          % ("wrote" if o.write else "would write", total, o.metric, o.response))

if __name__ == "__main__":
    main()
