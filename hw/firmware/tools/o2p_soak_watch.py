#!/usr/bin/env python3
"""Watch a running oven soak against OVEN-SOAK-TEST.md's hold and abort rules.

    python3 tools/o2p_soak_watch.py --once
    python3 tools/o2p_soak_watch.py --interval 120 \
        --jsonl docs/2026-09-19-oven-soak-evidence/watch.jsonl

WHY A SCRIPT AND NOT AN EYE ON A DASHBOARD. OVEN-SOAK-TEST.md section 6 lists
five abort criteria, and four of them are things that appear between glances:
a fault other than 512, settle_s restarting, the cell current leaving
80-120 uA, and link loss. The fifth, T_AFE above 85 C, is the one a human
would catch. This polls VictoriaMetrics and says which rule fired.

TRI-STATE, DELIBERATELY. The failure this guards against is a watcher that
reports OK because it could not read anything: no samples, a broken tunnel, a
metric that stopped being published all look identical to "nothing is wrong"
if the code only tests thresholds. So every verdict is one of

    ABORT        a section 6 criterion is met, on data recent enough to trust
    WARN         a departure from the plan's premises, not a section 6 abort
    UNEVALUABLE  the data cannot support a verdict (stale, missing, partial)
    OK           every rule checked, on fresh data, and none fired

and UNEVALUABLE is NOT OK. Staleness is checked before any threshold, because
a stale sample that happens to sit inside the band is the exact shape of a
silent failure: the probe stops publishing mid-abort and the watcher keeps
printing the last good number.

The dry-basis correction is o2p_psychro's, the firmware's own Sonntag
constants, never a local copy of Magnus.
"""

import argparse
import json
import re
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_psychro  # noqa: E402

# Section 6, plus the metrics section 7 asks to export.
METRICS = [
    "gas_cell_ua", "gas_t_ext_c", "gas_t_chamber_c", "gas_t_afe_c",
    "gas_rh_chamber_pct", "gas_faults", "gas_settle_s", "gas_heater_duty_pct",
]
FAULT_OK = {0, 512}          # 512 = TEMP_OVER, expected above 60 C
CELL_UA_MIN, CELL_UA_MAX = 80.0, 120.0
T_AFE_MAX_C = 85.0
LINK_LOSS_S = 300            # "link loss > 5 min"
# Section 4's settled-hold test.
HOLD_WINDOW_S = 600
HOLD_DRIFT_K_PER_MIN = 0.05
HOLD_SPREAD_K = 1.0
# Not in the plan: the chamber turned out to be wet (2026-09-19), so the
# descending leg can cross its own dew point ON the cell. Warn before it does.
DEW_MARGIN_WARN_K = 8.0


def fetch(host, window_s, timeout):
    """Return {metric: [(t_ms, value), ...]} from VictoriaMetrics over ssh.

    VM listens on the VPS loopback only, so the export runs there. A failed
    ssh raises; it must never look like an empty-but-healthy series.
    """
    script = (
        "end=$(date +%s); start=$((end-{w})); "
        'for m in {ms}; do curl -sf '
        '"http://127.0.0.1:8428/api/v1/export?match[]=$m&start=$start&end=$end"; '
        "echo; done"
    ).format(w=window_s, ms=" ".join(METRICS))
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError("ssh/curl failed rc=%d: %s" % (out.returncode, out.stderr.strip()[:200]))
    series = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        d = json.loads(line)
        name = d["metric"]["__name__"]
        series.setdefault(name, []).extend(zip(d["timestamps"], d["values"]))
    for name in series:
        series[name].sort()
    return series


def latest(series, name, max_age_ms, now_ms):
    if not series.get(name):
        return None
    t, v = series[name][-1]
    return (t, float(v)) if now_ms - t <= max_age_ms else None


def hold_state(series, now_ms):
    """Section 4's settled test over the trailing HOLD_WINDOW_S.

    Returns (settled: bool|None, detail). None means unevaluable - too few
    points, not "unsettled", because those are different findings.
    """
    win = [(t, float(v)) for t, v in series.get("gas_t_ext_c", [])
           if now_ms - t <= HOLD_WINDOW_S * 1000]
    if len(win) < 4 or (win[-1][0] - win[0][0]) < 0.5 * HOLD_WINDOW_S * 1000:
        return None, "fewer than 4 points spanning %d s" % (HOLD_WINDOW_S // 2)
    span_min = (win[-1][0] - win[0][0]) / 60000.0
    drift = abs(win[-1][1] - win[0][1]) / span_min
    temps = {}
    for name in ("gas_t_ext_c", "gas_t_chamber_c", "gas_t_afe_c"):
        got = latest(series, name, LINK_LOSS_S * 1000, now_ms)
        if got is None:
            return None, "%s missing or stale" % name
        temps[name] = got[1]
    spread = max(temps.values()) - min(temps.values())
    ok = drift < HOLD_DRIFT_K_PER_MIN and spread < HOLD_SPREAD_K
    return ok, "drift %.3f K/min over %.0f min, T spread %.2f K" % (drift, span_min, spread)


def evaluate(series, now_ms, p_total_hpa):
    findings, reading = [], {}
    fresh = {}
    for name in METRICS:
        got = latest(series, name, LINK_LOSS_S * 1000, now_ms)
        if got is None:
            newest = series.get(name) and series[name][-1][0]
            age = "no samples" if not newest else "%.0f s old" % ((now_ms - newest) / 1000.0)
            findings.append(("UNEVALUABLE", "%s: %s" % (name, age)))
        else:
            fresh[name] = got[1]
            reading[name] = got[1]

    # Staleness first: a threshold applied to a stale value is worse than no
    # verdict, because it reads as a pass.
    if "gas_cell_ua" not in fresh or "gas_t_ext_c" not in fresh:
        return "UNEVALUABLE", findings, reading

    faults = int(fresh.get("gas_faults", -1))
    if faults not in FAULT_OK:
        findings.append(("ABORT", "faults=%d, not 0 or 512 (section 6)" % faults))
    settle = fresh.get("gas_settle_s")
    if settle is not None and settle > 0:
        findings.append(("ABORT", "settle_s=%.0f, the conversion restarted" % settle))
    ua = fresh["gas_cell_ua"]
    if not (CELL_UA_MIN <= ua <= CELL_UA_MAX):
        findings.append(("ABORT", "cell %.2f uA outside %g-%g" % (ua, CELL_UA_MIN, CELL_UA_MAX)))
    t_afe = fresh.get("gas_t_afe_c")
    if t_afe is not None and t_afe > T_AFE_MAX_C:
        findings.append(("ABORT", "T_AFE %.1f C above %.0f" % (t_afe, T_AFE_MAX_C)))

    duty = fresh.get("gas_heater_duty_pct")
    if duty is not None and duty != 0.0:
        findings.append(("WARN", "heater duty %.2f %% is not 0; section 3 voids the hold" % duty))

    t_ch, rh = fresh.get("gas_t_chamber_c"), fresh.get("gas_rh_chamber_pct")
    dry = None
    if t_ch is not None and rh is not None:
        p_w = o2p_psychro.p_water_hpa(t_ch, rh)
        reading["p_w_hpa"] = p_w
        reading["p_w_frac_pct"] = 100.0 * p_w / p_total_hpa
        dry = ua / (1.0 - p_w / p_total_hpa)
        reading["cell_ua_dry"] = dry
        # Dew point of the chamber air, against the cell-side temperature.
        ratio = math.log(p_w / o2p_psychro.MAGNUS_ES0_HPA) if p_w > 0 else None
        if ratio is not None:
            t_dew = o2p_psychro.MAGNUS_B * ratio / (o2p_psychro.MAGNUS_A - ratio)
            margin = fresh["gas_t_ext_c"] - t_dew
            reading["t_dew_c"], reading["dew_margin_k"] = t_dew, margin
            if margin < DEW_MARGIN_WARN_K:
                findings.append(("WARN", "cell is %.1f K above the chamber dew point %.1f C"
                                 % (margin, t_dew)))

    settled, detail = hold_state(series, now_ms)
    reading["hold"] = {True: "settled", False: "moving", None: "unevaluable"}[settled]
    reading["hold_detail"] = detail

    for level in ("ABORT", "UNEVALUABLE", "WARN"):
        if any(f[0] == level for f in findings):
            return level, findings, reading
    return "OK", findings, reading


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="root@100.64.0.3", help="VPS holding VictoriaMetrics")
    ap.add_argument("--pressure-hpa", type=float, default=941.1,
                    help="measured station pressure; the firmware assumes 930")
    ap.add_argument("--interval", type=float, default=120.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--jsonl", help="append every poll here as evidence")
    ap.add_argument("--window", type=int, default=1800, help="export window, s")
    ap.add_argument("--events", action="store_true",
                    help="print only what changed: a new verdict, a new or "
                         "cleared finding, a dew-margin threshold crossed, the "
                         "hold state flipping - plus a heartbeat. For driving a "
                         "notification stream, where one line per poll is noise "
                         "and a missed ABORT is not.")
    ap.add_argument("--heartbeat", type=float, default=900.0,
                    help="seconds between heartbeat lines in --events mode")
    a = ap.parse_args()

    # --events state. Thresholds are crossed DOWNWARD only: the run descends
    # into condensation risk, and re-announcing 12 K every poll while it
    # hovers there would bury the 8 K crossing that matters.
    DEW_STEPS = (12.0, 8.0, 4.0)
    last_verdict, last_findings, last_hold = None, set(), None
    dew_announced = set()
    last_beat = 0.0

    while True:
        now_ms = int(time.time() * 1000)
        try:
            series = fetch(a.host, a.window, timeout=60)
            verdict, findings, reading = evaluate(series, now_ms, a.pressure_hpa)
        except Exception as exc:                     # noqa: BLE001 - any failure is UNEVALUABLE
            verdict, findings, reading = "UNEVALUABLE", [("UNEVALUABLE", str(exc)[:200])], {}
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = "%s %s" % (stamp, verdict)
        if reading:
            line += (" T_ext=%.2f T_ch=%.2f T_afe=%.2f RH=%.1f I=%.2f I_dry=%s dew_margin=%s %s"
                     % (reading.get("gas_t_ext_c", float("nan")),
                        reading.get("gas_t_chamber_c", float("nan")),
                        reading.get("gas_t_afe_c", float("nan")),
                        reading.get("gas_rh_chamber_pct", float("nan")),
                        reading.get("gas_cell_ua", float("nan")),
                        ("%.2f" % reading["cell_ua_dry"]) if "cell_ua_dry" in reading else "n/a",
                        ("%.1fK" % reading["dew_margin_k"]) if "dew_margin_k" in reading else "n/a",
                        reading.get("hold", "?")))
        emit, why = True, []
        if a.events:
            # Dedup on the finding with its NUMBERS removed. "gas_cell_ua: 582 s
            # old" and "... 703 s old" are one ongoing condition, not two
            # events; comparing the raw text re-announces every poll and the
            # flood gets the monitor stopped, which silently ends the watch.
            def key(text):
                return re.sub(r"[-+0-9.]+", "#", text)
            fset = set(key(t) for _, t in findings)
            if verdict != last_verdict:
                why.append("verdict %s -> %s" % (last_verdict, verdict))
            texts = {key(t): t for _, t in findings}
            for t in sorted(fset - last_findings):
                why.append("NEW: " + texts[t])
            for t in sorted(last_findings - fset):
                why.append("CLEARED: " + t)
            hold = reading.get("hold")
            # settled <-> moving is the event. Either of them <-> unevaluable is
            # the sample rate, not the run, and announcing it buries the rest.
            if hold != last_hold and "unevaluable" not in (hold, last_hold):
                why.append("hold %s -> %s" % (last_hold, hold))
            margin = reading.get("dew_margin_k")
            if margin is not None:
                for step in DEW_STEPS:
                    if margin < step and step not in dew_announced:
                        dew_announced.add(step)
                        why.append("DEW MARGIN below %.0f K (%.1f K)" % (step, margin))
            # A heartbeat so silence always means "watched and unchanged",
            # never "the watcher died".
            if time.time() - last_beat >= a.heartbeat:
                why.append("heartbeat")
                last_beat = time.time()
            last_verdict, last_findings, last_hold = verdict, fset, hold
            emit = bool(why)
        if emit:
            print(line + (("   [" + "; ".join(why) + "]") if why else ""), flush=True)
            if not a.events:
                for level, text in findings:
                    print("    %-11s %s" % (level, text), flush=True)
        if a.jsonl:
            with open(a.jsonl, "a") as fh:
                fh.write(json.dumps({"t": stamp, "verdict": verdict,
                                     "findings": findings, "reading": reading}) + "\n")
        if a.once:
            return 2 if verdict in ("ABORT", "UNEVALUABLE") else 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
