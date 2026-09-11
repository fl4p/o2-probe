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
                     "t_tip": tc, "t_cham": tc, "t_ext": t_cell,
                     "faults": 0x8000, "settle": 0.0})
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

print("cell mode on the cell-side sensor (--cell-temp ext)")
# run() plants t_ext as the true cell temperature, so no lag is needed.
r = T.analyse(de, "cell", cell_temp="ext")
check("ext regressor splits", r["verdict"] == "ok", r["reasons"])
check("and does not scan tau", r.get("tau_s") == 0, str(r.get("tau_s")))
check("AFE share recovered on T_EXT",
      abs(r.get("afe_ppm_k", 0) - 650) < 3 * r.get("afe_ppm_k_se", 1e9) + 20,
      "%+.0f +/- %.0f" % (r.get("afe_ppm_k", 0), r.get("afe_ppm_k_se", 0)))
check("cell share recovered on T_EXT",
      abs(r.get("cell_apparent_ppm_k", 0) - 2000) < 3 * r.get("cell_apparent_ppm_k_se", 1e9) + 60,
      "%+.0f +/- %.0f" % (r.get("cell_apparent_ppm_k", 0), r.get("cell_apparent_ppm_k_se", 0)))
holed = [dict(x, t_ext=None) if k == 7 else x for k, x in enumerate(de)]
r = T.analyse(holed, "cell", cell_temp="ext")
check("a row without T_EXT is refused, not fitted",
      r["verdict"] == "unevaluable" and "afe_ppm_k" not in r, r["reasons"])
sel, dropped = T.select(holed, require=("t_ext",))
check("select(require=t_ext) drops and counts it",
      dropped["missing"] == 1 and len(sel) == len(de) - 1)
try:
    T.analyse(de, "cell", cell_temp="tip")
    check("an unknown cell_temp raises", False)
except ValueError:
    check("an unknown cell_temp raises", True)

print("loaders agree")
import csv, json, tempfile  # noqa: E401,E402
with tempfile.TemporaryDirectory() as d:
    p_csv = os.path.join(d, "a.csv")
    with open(p_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["utc", "o2_raw_ua", "t_afe_c", "t_tip_c",
                                           "t_chamber_c", "t_ext_c", "faults", "settle_s"])
        w.writeheader()
        for x in rows[:50]:
            w.writerow({"utc": T.dt.datetime.fromtimestamp(x["t"], T.dt.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "o2_raw_ua": "%.2f" % x["i_ua"], "t_afe_c": x["t_afe"],
                        "t_tip_c": x["t_tip"], "t_chamber_c": x["t_cham"],
                        "t_ext_c": x["t_ext"],
                        "faults": x["faults"], "settle_s": 0})
    p_vm = os.path.join(d, "a.jsonl")
    with open(p_vm, "w") as fh:
        for name, key in (("gas_cell_ua", "i_ua"), ("gas_t_afe_c", "t_afe"),
                          ("gas_t_tip_c", "t_tip"), ("gas_t_chamber_c", "t_cham"),
                          ("gas_t_ext_c", "t_ext"),
                          ("gas_faults", "faults"), ("gas_settle_s", "settle")):
            fh.write(json.dumps({"metric": {"__name__": name},
                                 "values": [x[key] for x in rows[:50]],
                                 "timestamps": [int(x["t"] * 1000) for x in rows[:50]]})
                     + "\n")
    a, b = T.load_csv(p_csv), T.load_vm_export(p_vm)
    check("same row count", len(a) == len(b) == 50)
    check("same T_AFE", all(abs(x["t_afe"] - y["t_afe"]) < 1e-9 for x, y in zip(a, b)))
    check("same T_EXT", all(x["t_ext"] is not None and abs(x["t_ext"] - y["t_ext"]) < 1e-9
                            for x, y in zip(a, b)))
    check("same current to 0.01 uA", all(abs(x["i_ua"] - y["i_ua"]) < 0.006 for x, y in zip(a, b)))

print("refusals on bad regressors (codex review 2026-09-11)")
frozen = [dict(x, t_ext=22.01) for x in de]
r = T.analyse(frozen, "cell", cell_temp="ext")
check("a frozen T_EXT is refused, not fitted",
      r["verdict"] == "unevaluable" and "cell_apparent_ppm_k" not in r, r["reasons"])
r = T.analyse(frozen, "cell", cell_temp="ext", afe_ppm_k=650.0)
check("... even with the AFE share fixed",
      r["verdict"] == "unevaluable" and "cell_apparent_ppm_k" not in r, r["reasons"])
r = T.analyse([dict(x, t_ext=float("nan")) if k == 3 else x for k, x in enumerate(de)],
              "cell", cell_temp="ext")
check("a NaN T_EXT is refused on a direct call", r["verdict"] == "unevaluable", r["reasons"])
r = T.analyse([dict(x, t_afe=float("inf")) if k == 3 else x for k, x in enumerate(de)],
              "cell", cell_temp="ext")
check("a non-finite T_AFE is refused on a direct call", r["verdict"] == "unevaluable",
      r["reasons"])
check("the loader reads inf/nan as unavailable",
      T._f("inf") is None and T._f("-inf") is None and T._f("nan") is None)
with tempfile.TemporaryDirectory() as d:
    p_csv, p_json = os.path.join(d, "inf.csv"), os.path.join(d, "r.json")
    with open(p_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["utc", "o2_raw_ua", "t_afe_c", "t_tip_c",
                                           "t_chamber_c", "t_ext_c", "faults", "settle_s"])
        w.writeheader()
        for k, x in enumerate(de):
            w.writerow({"utc": T.dt.datetime.fromtimestamp(x["t"], T.dt.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "o2_raw_ua": x["i_ua"], "t_afe_c": x["t_afe"], "t_tip_c": x["t_tip"],
                        "t_chamber_c": x["t_cham"],
                        "t_ext_c": "inf" if k == 7 else x["t_ext"],
                        "faults": x["faults"], "settle_s": 0})
    rc = T.main(["--csv", p_csv, "--mode", "cell", "--cell-temp", "ext",
                 "--json", p_json, "--no-check"])
    with open(p_json) as fh:
        out = json.load(fh)
    nums = [v for v in out["result"].values() if isinstance(v, float)]
    check("CLI: an inf row is dropped as missing, and the fit stays finite",
          rc == 0 and out["dropped"]["missing"] == 1 and all(math.isfinite(v) for v in nums),
          "rc=%s dropped=%s" % (rc, out["dropped"]))
    frozen_csv = os.path.join(d, "frozen.csv")
    with open(p_csv) as src, open(frozen_csv, "w", newline="") as dst:
        rows_in = list(csv.DictReader(src))
        w = csv.DictWriter(dst, fieldnames=list(rows_in[0].keys()))
        w.writeheader()
        for row in rows_in:
            w.writerow(dict(row, t_ext_c="22.01"))
    rc = T.main(["--csv", frozen_csv, "--mode", "cell", "--cell-temp", "ext", "--no-check"])
    check("CLI: a frozen T_EXT exits 2, never 0", rc == 2, "rc=%s" % rc)

print("second review (2026-09-11): lagged span, timestamps, metadata, options, rank")
r = T.analyse(de, "cell", tau=1e12)
check("a tau that flattens the lagged regressor refuses",
      r["verdict"] == "unevaluable" and "cell_apparent_ppm_k" not in r, r["reasons"])
r = T.analyse(co, "cell", tau=1e12, afe_ppm_k=650.0)
check("... also with the AFE share fixed",
      r["verdict"] == "unevaluable" and "cell_apparent_ppm_k" not in r, r["reasons"])
r = T.analyse(de, "cell", tau_grid=[1e12, 600.0])
check("an unexcited tau is skipped, not chosen", r["verdict"] == "ok" and r.get("tau_s") == 600.0,
      "%s %s" % (r.get("tau_s"), r["reasons"]))

r = T.analyse([dict(x, t=1.7e9) for x in de], "cell")
check("duplicate timestamps refuse", r["verdict"] == "unevaluable" and "afe_ppm_k" not in r,
      r["reasons"])
r = T.analyse([dict(x, t=float("nan")) if k == 600 else x for k, x in enumerate(de)], "cell")
check("one NaN timestamp refuses, instead of moving tau", r["verdict"] == "unevaluable",
      r["reasons"])
r = T.analyse([dict(x, t=None) if k == 300 else x for k, x in enumerate(rows)], "dummy")
check("a missing timestamp refuses in dummy mode too", r["verdict"] == "unevaluable", r["reasons"])
shuffled = list(de)
random.Random(3).shuffle(shuffled)
r1, r2 = T.analyse(de, "cell", cell_temp="ext"), T.analyse(shuffled, "cell", cell_temp="ext")
check("row order does not change the fit",
      r2["verdict"] == "ok" and abs(r1["cell_apparent_ppm_k"] - r2["cell_apparent_ppm_k"]) < 1e-6,
      "%s vs %s" % (r1.get("cell_apparent_ppm_k"), r2.get("cell_apparent_ppm_k")))

for kw in ({"min_span_k": float("nan")}, {"min_span_k": 0.0}, {"max_corr": float("nan")},
           {"max_corr": 1.5}, {"tau": -5.0}, {"tau": float("inf")}, {"min_n": 2},
           {"afe_ppm_k": float("inf")}, {"tau_grid": [float("nan")]}):
    try:
        T.analyse(frozen, "cell", cell_temp="ext", **kw)
        check("option %s raises" % kw, False)
    except ValueError:
        check("option %s raises" % kw, True)

sel, dropped = T.select([dict(x, settle=float("inf")) for x in rows[:3]]
                        + [dict(x, settle=float("nan")) for x in rows[3:6]]
                        + [dict(x, faults=T.FAULTS_INVALID) for x in rows[6:8]]
                        + [dict(x, t=None) for x in rows[8:10]]
                        + [dict(x, t=float("nan")) for x in rows[10:11]]
                        + rows[11:])
check("recorded-but-invalid settle/faults are dropped as invalid, not accepted",
      dropped["invalid_metadata"] == 8 and dropped["settling"] == 0, str(dropped))
check("missing/non-finite time is dropped and counted", dropped["bad_time"] == 3, str(dropped))
check("everything else is kept", len(sel) == len(rows) - 11)
check("the metadata loader keeps inf, marks text NaN, and None stays None",
      T._meta_f("inf") == float("inf") and math.isnan(T._meta_f("x")) and T._meta_f("") is None)
check("unparseable faults become the invalid sentinel",
      T._meta_int("zz") == T.FAULTS_INVALID and T._meta_int("inf") == T.FAULTS_INVALID
      and T._meta_int("") is None and T._meta_int("0x8000") == 0x8000)

with tempfile.TemporaryDirectory() as d:
    p_csv, p_json = os.path.join(d, "settle.csv"), os.path.join(d, "r.json")
    with open(p_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["utc", "o2_raw_ua", "t_afe_c", "t_tip_c",
                                           "t_chamber_c", "faults", "settle_s"])
        w.writeheader()
        for k, x in enumerate(rows):
            w.writerow({"utc": "garbage" if k == 0 else
                        T.dt.datetime.fromtimestamp(x["t"], T.dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "o2_raw_ua": x["i_ua"], "t_afe_c": x["t_afe"], "t_tip_c": x["t_tip"],
                        "t_chamber_c": x["t_cham"], "faults": x["faults"],
                        "settle_s": "inf" if k % 2 else "nan"})
    rc = T.main(["--csv", p_csv, "--mode", "dummy", "--json", p_json, "--no-check"])
    with open(p_json) as fh:
        out = json.load(fh)
    check("CLI: every settle_s inf/nan refuses the run (exit 2), counted as invalid",
          rc == 2 and out["dropped"]["invalid_metadata"] == len(rows) - 1
          and out["dropped"]["bad_time"] == 1, "rc=%s %s" % (rc, out["dropped"]))
    for bad in (["--min-span-k", "nan"], ["--max-corr", "0"], ["--tau", "-1"], ["--min-n", "2"]):
        try:
            T.main(["--csv", p_csv, "--mode", "cell", "--no-check"] + bad)
            check("CLI rejects %s" % bad, False)
        except SystemExit as exc:
            check("CLI rejects %s" % bad, exc.code == 2, "code=%s" % exc.code)

try:
    T.ols([[1.0, float(x), x + 1e-13] for x in range(30)], [float(x) for x in range(30)])
    check("collinear columns raise in ols", False)
except ZeroDivisionError:
    check("collinear columns raise in ols", True)
try:
    T.ols([[1.0, 25.0 + 1e-15 * (x % 2)] for x in range(30)], [float(x) for x in range(30)])
    check("a column that does not move raises in ols", False)
except ZeroDivisionError:
    check("a column that does not move raises in ols", True)
f = T.ols([[1.0, 25.0 + 0.01 * x] for x in range(40)], [3.0 + 2.0 * (25.0 + 0.01 * x) for x in range(40)])
check("a small wobble on a large offset is still solved exactly",
      abs(f["beta"][1] - 2.0) < 1e-9 and abs(f["beta"][0] - 3.0) < 1e-7, str(f["beta"]))

if FAILS:
    print("FAILED: %s" % ", ".join(FAILS))
    sys.exit(1)
print("all ok")
