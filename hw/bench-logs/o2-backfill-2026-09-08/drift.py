import json, math, datetime
def load(n):
    out={}
    for line in open(f'exp_{n}.jsonl'):
        line=line.strip()
        if not line: continue
        d=json.loads(line)
        for t,v in zip(d['timestamps'],d['values']): out[t]=v
    return out
I=load('gas_cell_ua'); T=load('gas_t_chamber_c'); RH=load('gas_rh_chamber_pct')
TEMPCO=2840e-6; CAL_TEMP=27.29; ALPHA=0.402; P=963.0
def es(t): return 6.112*math.exp(17.62*t/(243.12+t))
# Normalise each raw sample to 27.29 C and to dry basis. This removes T and RH
# entirely, so what is left is the CELL: drift, steps, anything non-thermal.
rows=[]
for t in sorted(I):
    if t not in T or t not in RH: continue
    tc=T[t]; rh=RH[t]
    s=I[t]/(1.0+TEMPCO*(tc-CAL_TEMP))          # -> current as if at 27.29 C
    pw=rh/100.0*es(tc); f=(P-pw)/P
    s/= (1.0-ALPHA*(1.0-f))                     # -> as if dry
    rows.append((t,s,tc,rh))
# hourly medians
from collections import defaultdict
b=defaultdict(list)
for t,s,tc,rh in rows:
    lt=datetime.datetime.fromtimestamp(t/1000,datetime.UTC)+datetime.timedelta(hours=2)
    b[f"{lt:%m-%d %H}"].append((s,tc))
print("normalised cell current (uA @ 27.29 C, dry basis) - T and RH removed")
print(f"{'hour':10} {'n':>4} {'median uA':>10} {'T range':>14}")
prev=None
for k in sorted(b):
    v=sorted(x[0] for x in b[k]); m=v[len(v)//2]
    ts=[x[1] for x in b[k]]
    d=f"{m-prev:+.3f}" if prev else "     "
    print(f"{k:10} {len(v):4d} {m:10.3f}  {min(ts):5.1f}-{max(ts):5.1f}   {d}")
    prev=m
