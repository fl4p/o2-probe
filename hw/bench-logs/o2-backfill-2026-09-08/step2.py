import json, math, datetime, statistics as st
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
def norm(t):
    if t not in T or t not in RH: return None
    tc=T[t]; rh=RH[t]
    s=I[t]/(1.0+TEMPCO*(tc-CAL_TEMP))
    pw=rh/100.0*es(tc); f=(P-pw)/P
    return s/(1.0-ALPHA*(1.0-f))
def U(y,mo,d,h,mi): return datetime.datetime(y,mo,d,h,mi,tzinfo=datetime.UTC).timestamp()*1000
def med(a,b,label):
    ts=[t for t in sorted(I) if a<=t<b]
    v=[norm(t) for t in ts]; v=[x for x in v if x]
    tt=[T[t] for t in ts if t in T]
    m=st.median(v)
    print(f"  {label:22} {m:8.3f} uA  n={len(v):4d}  T {min(tt):.2f}-{max(tt):.2f} (drift {max(tt)-min(tt):.2f} K)")
    return m
print("isothermal windows either side of 23:01:52 CEST:")
pre  = med(U(2026,9,7,20,10), U(2026,9,7,20,50), "22:10-22:50 (pre)")
post = med(U(2026,9,7,21,10), U(2026,9,7,22,10), "23:10-00:10 (post)")
# background drift measured on a genuinely quiet stretch
q1 = med(U(2026,9,6,23,0), U(2026,9,7,1,0),  "01:00-03:00 quiet")
q2 = med(U(2026,9,7,5,0),  U(2026,9,7,7,0),  "07:00-09:00 quiet")
drift_h=(q2-q1)/6.0
print(f"\nbackground drift on quiet data: {drift_h:+.4f} uA/h")
gap_h=(U(2026,9,7,21,10)-U(2026,9,7,20,50))/3600e3
ratio=(pre + drift_h*gap_h)/post
print(f"gap between windows: {gap_h:.2f} h -> drift correction {drift_h*gap_h:+.4f} uA")
print(f"\nSTEP RATIO pre/post = {ratio:.5f}  ({100*(ratio-1):+.3f} %)")
print(f"pre-step O2 scale factor = {1/ratio:.5f}  ({100*(1/ratio-1):+.3f} %)")
print(f"at 21.0 %vol that is {21.0*(1/ratio-1):+.3f} %vol")
json.dump({'step_ms':U(2026,9,7,21,1)+52000,'scale':1/ratio}, open('step.json','w'))
