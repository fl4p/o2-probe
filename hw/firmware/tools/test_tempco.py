#!/usr/bin/env python3
"""o2p_tempco recovers a planted slope, and refuses when it cannot.

Synthetic runs only; no hardware. The known-bad cases are the point (guard
checklist item 7): a flat run, a run with too few rows, and a cell-mode run
where one heat source moved both temperatures must each come back
UNEVALUABLE, not as a number.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_tempco as T  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("  %s  %s %s" % ("ok  " if cond else "FAIL", name, detail))
    if not cond:
        FAILS.append(name)


def run(n, i0, afe_ppm, cell_ppm, t_afe_fn, t_cham_fn, tau=600.0, noise=0.03,
        dt_s=5.0, seed=1):
    rnd = random.Random(seed)
    rows, t_cell = [], None
    for k in range(n):
        t = 1.7e9 + k * dt_s
        ta, tc = t_afe_fn(k * dt_s), t_cham_fn(k * dt_s)
        t_cell = tc if t_cell is None else t_cell + (1 - math.exp(-dt_s / tau)) * (tc - t_cell)
        i = i0 * (1 + afe_ppm * 1e-6 * (ta - 25.0) + cell_ppm * 1e-6 * (t_cell - 25.0))
        rows.append({"t": t, "i_ua": i + rnd.gauss(0, noise), "t_afe": ta,
                     "t_tip": tc, "t_cham": tc, "faults": 0x8000, "settle": 0.0})
    return rows


print("faults.h agreement")
check("mask matches faults.h", T.check_against_source() == [],
      str(T.check_against_source()))

print("dummy mode")
rows = run(600, 100.0, 650.0, 0.0, lambda s: 25 + 25 * s / 3000.0,
           lambda s: 25.0)
r = T.analyse(rows, "dummy")
check("verdict ok", r["verdict"] == "ok", r["reasons"])
check("recovers +650 ppm/K", abs(r.get("afe_ppm_k", 0) - 650) < 3 * r.get("afe_ppm_k_se", 1e9) + 5,
      "%+.1f +/- %.1f" % (r.get("afe_ppm_k", 0), r.get("afe_ppm_k_se", 0)))

flat = run(600, 100.0, 650.0, 0.0, lambda s: 25.0 + 0.2 * math.sin(s / 300), lambda s: 25.0)
r = T.analyse(flat, "dummy")
check("flat run is unevaluable", r["verdict"] == "unevaluable" and "afe_ppm_k" not in r,
      r["reasons"])

r = T.analyse(rows[:10], "dummy")
check("too few rows is unevaluable", r["verdict"] == "unevaluable", r["reasons"])

print("select()")
sel, dropped = T.select([dict(x, settle=30.0) for x in rows[:5]]
                        + [dict(x, faults=0x0800) for x in rows[5:10]]
                        + [dict(x, t_afe=None) for x in rows[10:15]]
                        + rows[15:])
check("settling rows dropped", dropped["settling"] == 5)
check("ADC_RANGE rows dropped", dropped["faulted"] == 5)
check("rows without T_AFE dropped", dropped["missing"] == 5)
check("CAL_DEFAULT alone is kept", len(sel) == len(rows) - 15)

print("cell mode")
# One heat source: tip and AFE rise together -> collinear -> split refused.
co = run(720, 100.0, 650.0, 2000.0, lambda s: 25 + 12 * min(s, 1800) / 1800.0,
         lambda s: 25 + 30 * min(s, 1800) / 1800.0)
r = T.analyse(co, "cell")
check("collinear run refuses the split",
      r["verdict"] == "split-unevaluable" and "afe_ppm_k" not in r,
      "r=%.3f" % r.get("corr_afe_cell", 0))
check("but reports the combined slopes", "combined_on_afe_ppm_k" in r)

# Two excursions in sequence: AFE end warmed first with the tip cold, then
# the tip warmed with the AFE back at ambient. Decorrelated -> separable.
def afe_fn(s):
    return 25 + (15 * s / 1800.0 if s < 1800 else 15 * max(0, 1 - (s - 1800) / 600.0))


def cham_fn(s):
    return 25 + (0 if s < 2400 else 20 * min(s - 2400, 1800) / 1800.0)


de = run(1200, 100.0, 650.0, 2000.0, afe_fn, cham_fn, tau=600.0)
r = T.analyse(de, "cell")
check("decorrelated run splits", r["verdict"] == "ok", r["reasons"])
check("AFE share recovered",
      abs(r.get("afe_ppm_k", 0) - 650) < 3 * r.get("afe_ppm_k_se", 1e9) + 20,
      "%+.0f +/- %.0f" % (r.get("afe_ppm_k", 0), r.get("afe_ppm_k_se", 0)))
check("cell share recovered",
      abs(r.get("cell_apparent_ppm_k", 0) - 2000) < 3 * r.get("cell_apparent_ppm_k_se", 1e9) + 60,
      "%+.0f +/- %.0f tau=%s" % (r.get("cell_apparent_ppm_k", 0),
                                 r.get("cell_apparent_ppm_k_se", 0), r.get("tau_s")))
check("lag recovered near 600 s", 300 <= r.get("tau_s", -1) <= 900, str(r.get("tau_s")))

# Fixing the AFE share from a dummy run makes even the collinear run yield c.
r = T.analyse(co, "cell", afe_ppm_k=650.0)
check("fixed AFE share solves the cell share on the collinear run",
      r["verdict"] == "ok" and abs(r.get("cell_apparent_ppm_k", 0) - 2000) < 100,
      "%+.0f" % r.get("cell_apparent_ppm_k", 0))

print("loaders agree")
import csv, json, tempfile  # noqa: E401,E402
with tempfile.TemporaryDirectory() as d:
    p_csv = os.path.join(d, "a.csv")
    with open(p_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["utc", "o2_raw_ua", "t_afe_c", "t_tip_c",
                                           "t_chamber_c", "faults", "settle_s"])
        w.writeheader()
        for x in rows[:50]:
            w.writerow({"utc": T.dt.datetime.fromtimestamp(x["t"], T.dt.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "o2_raw_ua": "%.2f" % x["i_ua"], "t_afe_c": x["t_afe"],
                        "t_tip_c": x["t_tip"], "t_chamber_c": x["t_cham"],
                        "faults": x["faults"], "settle_s": 0})
    p_vm = os.path.join(d, "a.jsonl")
    with open(p_vm, "w") as fh:
        for name, key in (("gas_cell_ua", "i_ua"), ("gas_t_afe_c", "t_afe"),
                          ("gas_t_tip_c", "t_tip"), ("gas_t_chamber_c", "t_cham"),
                          ("gas_faults", "faults"), ("gas_settle_s", "settle")):
            fh.write(json.dumps({"metric": {"__name__": name},
                                 "values": [x[key] for x in rows[:50]],
                                 "timestamps": [int(x["t"] * 1000) for x in rows[:50]]})
                     + "\n")
    a, b = T.load_csv(p_csv), T.load_vm_export(p_vm)
    check("same row count", len(a) == len(b) == 50)
    check("same T_AFE", all(abs(x["t_afe"] - y["t_afe"]) < 1e-9 for x, y in zip(a, b)))
    check("same current to 0.01 uA", all(abs(x["i_ua"] - y["i_ua"]) < 0.006 for x, y in zip(a, b)))

if FAILS:
    print("FAILED: %s" % ", ".join(FAILS))
    sys.exit(1)
print("all ok")
