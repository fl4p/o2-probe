import json, math, datetime, statistics as st
def load(n):
    out={}; meta=None
    for line in open(f'r3_{n}.jsonl'):
        line=line.strip()
        if not line: continue
        d=json.loads(line); meta=d['metric']
        for t,v in zip(d['timestamps'],d['values']): out[t]=v
    return out, meta
S={}; META=None
for m in ['gas_cell_ua','gas_t_chamber_c','gas_t_tip_c','gas_rh_chamber_pct','gas_settle_s','gas_pct_vol']:
    S[m],mt=load(m)
    if m=='gas_pct_vol': META=mt

CAL_AIR_NA=(1<<16)+36116; CAL_FRAC=20867e-5; CAL_TEMP=27.29; CAL_P=963.0
TEMPCO=2840e-6; ALPHA=0.402; P=963.0
K=CAL_AIR_NA/math.log(1.0/(1.0-CAL_FRAC))
STEP_MS=datetime.datetime(2026,9,7,21,1,52,tzinfo=datetime.UTC).timestamp()*1000
def es(t): return 6.112*math.exp(17.62*t/(243.12+t))

def build(scale_pre):
    rows=[]
    for t in sorted(S['gas_cell_ua']):
        s_=S['gas_settle_s'].get(t)
        if s_ is not None and s_>0: continue
        tc=S['gas_t_chamber_c'].get(t, S['gas_t_tip_c'].get(t))
        rh=S['gas_rh_chamber_pct'].get(t); cell=S['gas_cell_ua'].get(t)
        if tc is None or rh is None or cell is None: continue
        cell_na=cell*1000.0
        if t<STEP_MS: cell_na*=scale_pre
        gain=1.0+TEMPCO*(tc-CAL_TEMP)
        if not (0.05<gain<20.0): continue
        s=cell_na/gain*(CAL_P/P)
        if s<=0: continue
        c_wet=1.0-math.exp(-s/K)
        pw=rh/100.0*es(tc); f=(P-pw)/P
        feff=1.0-ALPHA*(1.0-f)
        if not (0.0<feff<=1.0): continue
        c=c_wet/feff
        if not (0.0<c<1.0): continue
        rows.append((t, round(c*100.0,2)))
    return rows

plain = build(1.0)          # what the instrument reported, step intact
adj   = build(0.99492)      # conditional rescale, kept as a separate series

def dump(rows, meta, path):
    open(path,'w').write(json.dumps({'metric':meta,
        'values':[v for _,v in rows],'timestamps':[t for t,_ in rows]})+'\n')

dump(plain, META, 'import_revert.jsonl')
meta2=dict(META); meta2['__name__']='gas_pct_vol_stepadj'
dump(adj, meta2, 'import_stepadj.jsonl')

for name,rows in [('gas_pct_vol (reverted)',plain),('gas_pct_vol_stepadj',adj)]:
    pre=[v for t,v in rows if t<STEP_MS]; post=[v for t,v in rows if t>=STEP_MS]
    print(f"{name}: n={len(rows)}  pre-step median {st.median(pre):.2f}  post-step median {st.median(post):.2f}"
          f"  step {st.median(post)-st.median(pre):+.3f} %vol")
