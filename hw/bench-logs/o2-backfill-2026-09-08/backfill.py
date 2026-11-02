import json, math, datetime, sys

def load(name):
    out = {}
    meta = None
    for line in open(f'exp_{name}.jsonl'):
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        meta = d['metric']
        for t, v in zip(d['timestamps'], d['values']):
            out[t] = v
    return out, meta

S = {}
for m in ['gas_pct_vol','gas_cell_ua','gas_t_chamber_c','gas_t_tip_c',
          'gas_rh_chamber_pct','gas_settle_s','gas_faults']:
    S[m], meta = load(m)
    if m == 'gas_pct_vol': PCT_META = meta

# committed config, read back from probe flash 2026-09-08 00:0x CEST
CAL_AIR_NA = (1 << 16) + 36116     # 0x0037/0x0038
CAL_FRAC   = 20867 * 1e-5          # 0x0043
CAL_TEMP   = 2729 * 0.01           # 0x0039
CAL_P      = 963.0                 # 0x0044
TEMPCO     = 2840 * 1e-6           # 0x003A
ALPHA      = 402 * 1e-3            # 0x0045
P          = 963.0                 # 0x0042
LN_AIR     = math.log(1.0 / (1.0 - CAL_FRAC))
K          = CAL_AIR_NA / LN_AIR

FRAC_MIN, FRAC_MAX = 0.15, 0.25
assert FRAC_MIN <= CAL_FRAC <= FRAC_MAX

def es(t): return 6.112 * math.exp(17.62 * t / (243.12 + t))

def compute(cell_ua, t, rh):
    """Mirror o2.c: tempco -> pressure -> log law -> dilution. None = UNEVALUABLE."""
    if t is None or rh is None or cell_ua is None: return None
    cell_na = cell_ua * 1000.0
    gain = 1.0 + TEMPCO * (t - CAL_TEMP)
    if not (0.05 < gain < 20.0): return None
    s = cell_na / gain
    s *= CAL_P / P
    if s <= 0: return None
    c_wet = 1.0 - math.exp(-s / K)
    pw = rh / 100.0 * es(t)
    f = (P - pw) / P
    f_eff = 1.0 - ALPHA * (1.0 - f)
    if not (0.0 < f_eff <= 1.0): return None
    c = c_wet / f_eff
    if not (0.0 < c < 1.0): return None
    return round(c * 100.0, 2)      # probe quantises to 0.01 %vol

ts_all = sorted(set(S['gas_cell_ua']))
rows, skipped_settle, skipped_input, unevaluable = [], 0, 0, 0
for t in ts_all:
    settle = S['gas_settle_s'].get(t)
    if settle is not None and settle > 0:
        skipped_settle += 1
        continue
    temp = S['gas_t_chamber_c'].get(t, S['gas_t_tip_c'].get(t))
    rh   = S['gas_rh_chamber_pct'].get(t)
    cell = S['gas_cell_ua'].get(t)
    if temp is None or rh is None or cell is None:
        skipped_input += 1
        continue
    v = compute(cell, temp, rh)
    if v is None:
        unevaluable += 1
        continue
    rows.append((t, v, S['gas_pct_vol'].get(t)))

old_ts = set(S['gas_pct_vol'])
new_ts = {r[0] for r in rows}
both = [(t, v, o) for t, v, o in rows if o is not None]
deltas = [v - o for _, v, o in both]
filled = len(new_ts - old_ts)
dropped = len(old_ts - new_ts)

print(f"K = {K:.0f} nA   cal_frac {CAL_FRAC:.5f}  cal_temp {CAL_TEMP} C  tempco {TEMPCO*1e6:.0f} ppm/K  alpha {ALPHA}")
print()
print(f"input timestamps (cell_ua)      {len(ts_all)}")
print(f"  skipped, probe still settling {skipped_settle}")
print(f"  skipped, missing T or RH      {skipped_input}")
print(f"  computed but unevaluable      {unevaluable}")
print(f"recomputed samples to write     {len(rows)}")
print()
print(f"existing gas_pct_vol samples    {len(old_ts)}")
print(f"  overlapping (will change)     {len(both)}")
print(f"  NEW timestamps (gap filled)   {filled}")
print(f"  existing ts with no new value {dropped}")
print()
if deltas:
    deltas.sort()
    n = len(deltas)
    print(f"delta new-old over {n} overlapping samples (%vol):")
    print(f"  min {deltas[0]:+.3f}  p05 {deltas[n//20]:+.3f}  median {deltas[n//2]:+.3f}"
          f"  p95 {deltas[19*n//20]:+.3f}  max {deltas[-1]:+.3f}")
    print(f"  mean {sum(deltas)/n:+.3f}")
print()
print("sample rows (local time, old -> new):")
for t, v, o in rows[::max(1, len(rows)//15)][:15]:
    lt = datetime.datetime.fromtimestamp(t/1000, datetime.UTC) + datetime.timedelta(hours=2)
    temp = S['gas_t_chamber_c'].get(t, float('nan'))
    print(f"  {lt:%m-%d %H:%M:%S}  T={temp:5.2f}  {('%.2f'%o) if o is not None else '  -- ':>6} -> {v:.2f}")

json.dump({'meta': PCT_META, 'rows': [[t, v] for t, v, _ in rows]}, open('recomputed.json','w'))
print(f"\nwrote recomputed.json ({len(rows)} samples)")
