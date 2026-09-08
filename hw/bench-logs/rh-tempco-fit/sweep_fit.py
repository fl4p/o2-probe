# Two-stage fit on the 2026-09-07 sweep, merged series (device=farm-node-01).
#
# Stage 1  tempco from the ISOBARIC heating leg 15:26-16:20Z: T swings 7.3 K while
#          p_w stays inside 0.9 hPa, so the dilution term cannot move and the slope
#          of ln(I) on T is the temperature coefficient alone.  The jar is COVERED,
#          NOT SEALED (Fab, 2026-09-07), so total pressure stays ambient and pO2 is
#          constant: none of this slope is the ideal-gas law.
# Stage 2  alpha from the ISOTHERMAL dry-down 13:17-15:15Z: p_w falls 18.2 hPa while
#          T moves 1.0 K, with the stage-1 tempco held fixed.
# The two legs are disjoint, so neither coefficient is fitted through the other's
# variation -- this is what every earlier section could not do.
import json,math,datetime,sys,gzip,os
P=963.0;T0=25.0
def es(t): return 6.112*math.exp(17.62*t/(243.12+t))
def U(d,hh,mm): return datetime.datetime(2026,9,d,hh,mm,tzinfo=datetime.timezone.utc).timestamp()
S={}
SRC="sweep.ndjson.gz" if os.path.exists("sweep.ndjson.gz") else "sweep.ndjson"
for l in (gzip.open(SRC,"rt") if SRC.endswith(".gz") else open(SRC)):
    d=json.loads(l);S[d["metric"]["__name__"]]=dict(zip(d["timestamps"],d["values"]))
ts=sorted(set.intersection(*[set(v) for v in S.values()]))
rows=[]
for t in ts:
    I=S["gas_cell_ua"][t];h=S["gas_rh_chamber_pct"][t];T=S["gas_t_chamber_c"][t];c=S["gas_pct_vol"][t]
    if I<=0 or not(0<h<=100) or c<=0: continue
    if t/1000.0 < U(7,8,30): continue
    rows.append((t/1000.0,I,T,h/100*es(T),c))
rows.sort()
def slope(Q,xi,yi):
    n=len(Q);mx=sum(r[xi] for r in Q)/n;my=sum(r[yi] for r in Q)/n
    return sum((r[xi]-mx)*(r[yi]-my) for r in Q)/sum((r[xi]-mx)**2 for r in Q)
def jk(Q,fn,block):
    ks=sorted(set(int(r[0]//block) for r in Q));out=[]
    for k in ks:
        sub=[r for r in Q if int(r[0]//block)!=k]
        if len(sub)>6: out.append(fn(sub))
    n=len(out);m=sum(out)/n
    return math.sqrt((n-1)/n*sum((o-m)**2 for o in out)),n
L=[(r[0],r[1],r[2],r[3],math.log(r[1])) for r in rows]
PK=max((r for r in L if r[0]>=U(7,15,0)),key=lambda r:r[2])
H=[r for r in L if U(7,15,26)<=r[0]<=PK[0]]
C=[r for r in L if r[0]>PK[0]]
TC=slope(H,2,4); SE_TC,nb1=jk(H,lambda q:slope(q,2,4),600)
D=[r for r in L if U(7,13,17)<=r[0]<U(7,15,15)]
mw=sum(r[3] for r in D)/len(D); dil=-1.0/(P-mw)
# THE UNITS THE FIRMWARE CONSUMES, which are not the units this regression is
# natural in. Adversarial review 2026-09-07, confirmed numerically below.
#
# The regression gives d ln(I)/d p_w and divides by the ideal concentration
# slope -1/(P-p_w), so its alpha lives in the LOG-CURRENT domain. The firmware
# applies alpha to CONCENTRATION and then goes through the cell's log law,
# C = 1 - exp(-S/K). The two differ by the local gain of that law:
#
#     d ln S / d ln C = C / ((1-C) * L(C)),  L(C) = -ln(1-C)
#
# which at 20.946 %vol is 1.1273. So alpha_firmware = alpha_log / 1.1273.
# Reporting 0.453 and writing it into DIL_ALPHA overstates the correction by
# 12 %, worth about +0.17 pp on a 20.95 %vol reading at pile conditions.
AMP = O2P_C_AIR_L = None
def logamp(c):
    L=-math.log(1-c); return c/((1-c)*L)
AMP = logamp(0.20946)

def alpha_at(Q,tc):
    Q2=[(r[0],r[3],r[4]-tc*r[2]) for r in Q]
    return slope(Q2,1,2)/dil/AMP
A=alpha_at(D,TC); SE_A,nb2=jk(D,lambda q:alpha_at(q,TC),600)
SE_A=math.sqrt(SE_A**2+((alpha_at(D,TC-SE_TC)-alpha_at(D,TC+SE_TC))/2)**2)
print("stage 1  tempco = %+.3f +/- %.3f %%/K   (n=%d, dT=%.2f K, p_w range %.2f hPa, %d blocks)"
      %(TC*100,SE_TC*100,len(H),max(r[2] for r in H)-min(r[2] for r in H),max(r[3] for r in H)-min(r[3] for r in H),nb1))
print("stage 2  alpha  = %+.3f +/- %.3f       (n=%d, dp_w=%.1f hPa, dT=%.2f K, %d blocks)"
      %(A,SE_A,len(D),max(r[3] for r in D)-min(r[3] for r in D),max(r[2] for r in D)-min(r[2] for r in D),nb2))
print("         (log-current domain %+.3f, / %.4f for the cell law)"%(A*AMP,AMP))
def tempco_at(Q,alpha):
    # alpha comes back to the LOG-CURRENT domain here (x AMP), because this
    # regression is on ln(I): the tempco itself needs no conversion - the
    # firmware divides the CURRENT by (1 + tempco*dT), the same domain it is
    # fitted in - but the alpha term being removed from ln(I) does.
    n=len(Q);dl=-1.0/(P-sum(r[3] for r in Q)/n)
    Q2=[(r[0],r[2],r[4]-alpha*AMP*dl*r[3]) for r in Q]
    return slope(Q2,1,2)
TCC=SEC=None
if len(C)>=8:
    TCC=tempco_at(C,A); SEC,_=jk(C,lambda q:tempco_at(q,A),600)
    print("cooldown tempco = %+.3f +/- %.3f %%/K   (n=%d, dT=%.2f K, dp_w=%.2f hPa, alpha held)"
          %(TCC*100,SEC*100,len(C),max(r[2] for r in C)-min(r[2] for r in C),max(r[3] for r in C)-min(r[3] for r in C)))
json.dump(dict(alpha=A,se_alpha=SE_A,tempco=TC,se_tempco=SE_TC,tempco_cooldown=TCC,se_tempco_cooldown=SEC,P=P,n=len(rows)),open("sweep.json","w"),indent=1)

import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.dates as mdates
def series(a,tc):
    v=[(r[1]/(1.0+tc*(r[2]-T0)), 1-(1-(P-r[3])/P)*a) for r in rows]
    lo,hi=3e5,7e5
    for _ in range(80):
        K=(lo+hi)/2
        if sum((1-math.exp(-s*1000/K))/f for s,f in v)/len(v)*100>20.95: lo=K
        else: hi=K
    K=(lo+hi)/2
    return [(1-math.exp(-s*1000/K))/f*100 for s,f in v]
x=[datetime.datetime.fromtimestamp(r[0],datetime.UTC) for r in rows]
pub=[r[4] for r in rows]
full=series(1.0,0.0); pw=series(A,0.0); both=series(A,TC)
def sd(v):
    m=sum(v)/len(v);return math.sqrt(sum((z-m)**2 for z in v)/len(v))
fig,(ax,bx)=plt.subplots(2,1,figsize=(13.5,8.6),sharex=True,height_ratios=[2.6,1],gridspec_kw=dict(hspace=0.10))
ax.axhline(20.95,color="#333",lw=1,ls=(0,(6,4)),zorder=1)
ax.plot(x,full,lw=.9,color="#e8a2a2",label="dilution only, full (a=1.00)                    sd %.3f pp"%sd(full))
ax.plot(x,pub ,lw=1.2,color="#7f8c8d",label="published, uncorrected                         sd %.3f pp"%sd(pub))
ax.plot(x,pw  ,lw=1.1,color="#e67e22",label="dilution only, fitted (a=%.2f)                 sd %.3f pp"%(A,sd(pw)))
ax.plot(x,both,lw=1.7,color="#1f77b4",label="dilution a=%.2f + tempco %+.3f %%/K            sd %.3f pp"%(A,TC*100,sd(both)))
ax.set_ylabel("O$_2$  [%vol]")
ax.legend(loc="upper left",fontsize=9,framealpha=.95,prop={"family":"monospace","size":8.4})
ax.grid(alpha=.25)
ax.set_title("o2-probe 2026-09-07: the first sweep that separates the two coefficients\n"
             "tempco %+.3f +/- %.3f %%/K from the ISOBARIC heat (p_w flat to %.1f hPa over %.1f K)   |   "
             "a = %.3f +/- %.3f from the ISOTHERMAL dry-down (p_w -%.0f hPa)%s"
             %(TC*100,SE_TC*100,max(r[3] for r in H)-min(r[3] for r in H),
               max(r[2] for r in H)-min(r[2] for r in H),A,SE_A,max(r[3] for r in D)-min(r[3] for r in D),
               ("   |   cooldown gives %+.3f +/- %.3f %%/K"%(TCC*100,SEC*100)) if TCC is not None else ""),
             fontsize=10.5,loc="left")
marks=[(U(7,10,53),"bench logger stops (cp2102)","#8e44ad"),
       (U(7,11,11),"LoRa node resumes\n\nsame probe -> merged","#8e44ad"),
       (U(7,13,17),"\n\n\ndesiccant in\n-> isothermal dry-down","#16a085"),
       (U(7,15,20),"heat gun ~1 min\n(excluded)","#c0392b"),
       (U(7,15,26),"\n\n\n\n\nisobaric heat\n-> tempco leg","#c0392b"),
       (PK[0],"\n\npeak, then\ncooldown","#8e44ad")]
for t,lab,col in marks:
    d=datetime.datetime.fromtimestamp(t,datetime.UTC)
    for a_ in (ax,bx): a_.axvline(d,color=col,lw=1.0,ls=":")
    ax.annotate(lab,xy=(d,ax.get_ylim()[1]),xytext=(4,-6),textcoords="offset points",fontsize=7.6,color=col,va="top")
for a0,a1,col in [(U(7,13,17),U(7,15,15),"#16a085"),(U(7,15,26),PK[0],"#c0392b"),(PK[0],rows[-1][0],"#8e44ad")]:
    for a_ in (ax,bx):
        a_.axvspan(datetime.datetime.fromtimestamp(a0,datetime.UTC),
                   datetime.datetime.fromtimestamp(min(a1,rows[-1][0]),datetime.UTC),color=col,alpha=.07,zorder=0)
bx.plot(x,[r[3] for r in rows],lw=1.3,color="#2980b9")
bx.set_ylabel("$p_w$  [hPa]",color="#2980b9");bx.tick_params(axis="y",colors="#2980b9");bx.grid(alpha=.25)
cx=bx.twinx();cx.plot(x,[r[2] for r in rows],lw=1.3,color="#c0392b")
cx.set_ylabel("T chamber  [degC]",color="#c0392b");cx.tick_params(axis="y",colors="#c0392b")
bx.set_xlabel("UTC, 2026-09-07")
bx.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
bx.text(0.005,1.05,"green: p_w moves, T does not -> fits a.   red: T moves, p_w does not -> fits tempco.  "
        "Jar is covered, not sealed, so pO2 is constant through the heat and none of the red-leg slope is the gas law.",
        transform=bx.transAxes,fontsize=8.2,color="#555")
fig.savefig("../o2-sweep-2026-09-07.png",dpi=155,bbox_inches="tight")
print("wrote ../o2-sweep-2026-09-07.png")
