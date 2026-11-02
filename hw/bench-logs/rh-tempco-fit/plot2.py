import json,math,datetime
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.dates as mdates
P=930.0;T0=25.0
J=json.load(open("joint.json")); A=J["alpha"]; TC=J["tempco"]
def es(t): return 6.112*math.exp(17.62*t/(243.12+t))
S={}
for l in open("w12.ndjson"):
    d=json.loads(l);m=d["metric"]
    S.setdefault(m.get("device"),{})[m["__name__"]]=dict(zip(d["timestamps"],d["values"]))
rows=[]
for dev,mm in S.items():
    ts=sorted(set(mm["gas_cell_ua"])&set(mm["gas_rh_chamber_pct"])&set(mm["gas_t_chamber_c"])&set(mm["gas_pct_vol"]))
    for t in ts:
        s=mm["gas_cell_ua"][t];h=mm["gas_rh_chamber_pct"][t];T=mm["gas_t_chamber_c"][t];c=mm["gas_pct_vol"][t]
        if s<=0 or not(0<h<=100) or c<=0: continue
        rows.append((t/1000.0,s,T,h/100*es(T),c))
rows.sort()
def series(a,tc):
    v=[(r[1]/(1.0+tc*(r[2]-T0)), 1-(1-(P-r[3])/P)*a) for r in rows]
    lo,hi=3e5,7e5
    for _ in range(70):
        K=(lo+hi)/2
        if sum((1-math.exp(-s*1000/K))/f for s,f in v)/len(v)*100>20.95: lo=K
        else: hi=K
    K=(lo+hi)/2
    return [(1-math.exp(-s*1000/K))/f*100 for s,f in v]
x=[datetime.datetime.fromtimestamp(r[0],datetime.UTC) for r in rows]
pub=[r[4] for r in rows]
full=series(1.0,0.0); pw_only=series(A,0.0); both=series(A,TC)
def sd(v): 
    m=sum(v)/len(v); return math.sqrt(sum((z-m)**2 for z in v)/len(v))
fig,(ax,bx)=plt.subplots(2,1,figsize=(13.5,8.4),sharex=True,height_ratios=[2.6,1],
                         gridspec_kw=dict(hspace=0.10))
ax.axhline(20.95,color="#333",lw=1,ls=(0,(6,4)),zorder=1)
ax.plot(x,full,lw=.9,color="#e8a2a2",label="dilution only, full (α=1.00)                     sd %.3f pp"%sd(full))
ax.plot(x,pub, lw=1.2,color="#7f8c8d",label="published, uncorrected                          sd %.3f pp"%sd(pub))
ax.plot(x,pw_only,lw=1.1,color="#e67e22",label="dilution only, fitted (α=%.2f)                  sd %.3f pp"%(A,sd(pw_only)))
ax.plot(x,both,lw=1.7,color="#1f77b4",label="dilution α=%.2f  +  tempco %+.3f %%/K       sd %.4f pp"%(A,TC*100,sd(both)))
ax.text(x[4],20.958,"20.95 %vol — dry-basis O$_2$ in air; every line should sit flat on this",
        fontsize=8.5,color="#333",va="bottom")
ax.set_ylabel("O$_2$  [%vol]")
ax.legend(loc="upper left",fontsize=9,framealpha=.95,prop={"family":"monospace","size":8.6})
ax.grid(alpha=.25)
ax.set_title("o2-probe, 12 h in two vessels of air: the humidity term alone does not flatten it — temperature does\n"
             "α = %.3f ± %.3f of the modelled dilution, tempco = %+.3f ± %.3f %%/K   (n=%d, HAC)"
             %(A,J["se_alpha"],TC*100,J["se_tempco"]*100,len(rows)),fontsize=10.5,loc="left")
marks=[(1788764045,"→ vessel A\n(desiccant)"),(1788768707,"→ vessel N\n(sat. NaCl)"),(1788786871,"→ vessel A\n(desiccant)")]
for t,lab in marks:
    d=datetime.datetime.fromtimestamp(t,datetime.UTC)
    for a_ in (ax,bx): a_.axvline(d,color="#8e44ad",lw=1.0,ls=":")
    ax.annotate(lab,xy=(d,ax.get_ylim()[1]),xytext=(4,-30),textcoords="offset points",
                fontsize=8,color="#8e44ad",va="top")
bx.plot(x,[r[3] for r in rows],lw=1.3,color="#2980b9")
bx.set_ylabel("$p_w$  [hPa]",color="#2980b9"); bx.tick_params(axis="y",colors="#2980b9"); bx.grid(alpha=.25)
cx=bx.twinx(); cx.plot(x,[r[2] for r in rows],lw=1.3,color="#c0392b")
cx.set_ylabel("T chamber  [°C]",color="#c0392b"); cx.tick_params(axis="y",colors="#c0392b")
bx.set_xlabel("UTC, 2026-09-07")
bx.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
bx.text(0.005,1.045,"the 08:12→11:00 ramp is the room warming +3.4 K, not the vessel wetting — "
        "T and $p_w$ move together there (r=+0.91), which is why the humidity-only fits split on direction",
        transform=bx.transAxes,fontsize=8.4,color="#555")
fig.savefig("o2-12h-with-tempco.png",dpi=155,bbox_inches="tight")
print("ok")
