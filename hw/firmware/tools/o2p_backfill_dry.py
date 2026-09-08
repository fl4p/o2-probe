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

  * SCALE. K here is the probe's own stored constant, recovered from the
    published pairs (425557 nA, constant to 0.015 % over 3573 bench samples
    spanning RH 33.6-65.1). That air point was taken under the pre-2026-09-06
    assumption that the calibration air was DRY, so it is 2-3 % high. Fixing
    that is a recalibration, not arithmetic - see O2-HUMIDITY-CORRECTION 3b.
  * STRENGTH. The near-isothermal step of 2026-09-07 puts this cell's response
    at ~0.60 of the modelled dilution (section 12), so the full correction
    OVERSHOOTS by about 1.75x. --response scales it; the default is 1.0,
    which is what the firmware does, so history and the post-flash future
    agree. 0.60 fits the one step that has been measured. Neither is validated.
  * TEMPERATURE. tempco is 0 in firmware by design, and section 11 could not
    identify one. Nothing here supplies it.
"""
import argparse, json, math, sys, urllib.request

P_HPA = 930.0          # ASSUMED_P_HPA; Rev A has no barometer
K_NA  = 425557.0       # stored cal constant, recovered from published pairs
SRC   = ("gas_cell_ua", "gas_rh_chamber_pct", "gas_t_chamber_c")

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
    a.add_argument("--write", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    o = a.parse_args()
    if not (o.write or o.dry_run):
        sys.exit("refusing to guess: pass --dry-run or --write")

    series = {}
    for name in SRC:
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
        out_t, out_v = [], []
        for t in ts:
            s, rh, tc = m[SRC[0]][t], m[SRC[1]][t], m[SRC[2]][t]
            if s <= 0 or not (0.0 < rh <= 100.0) or not (-40.0 < tc < 80.0):
                continue                       # unevaluable is skipped, never defaulted
            pw = rh / 100.0 * es(tc)
            if pw >= P_HPA * 0.5:
                continue
            f = (P_HPA - pw) / P_HPA
            f = 1.0 - (1.0 - f) * o.response
            c_wet = 1.0 - math.exp(-s * 1000.0 / K_NA)
            c_dry = c_wet / f * 100.0
            if not (0.0 <= c_dry <= 30.0):
                continue
            out_t.append(t); out_v.append(round(c_dry, 4))
        lbl = dict(key); lbl["__name__"] = o.metric
        line = json.dumps({"metric": lbl, "values": out_v, "timestamps": out_t})
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
