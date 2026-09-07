import json,math,datetime
P=930.0;T0=25.0
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
def ols(X,y):
    k=len(X[0]);A=[[sum(r[i]*r[j] for r in X) for j in range(k)] for i in range(k)]
    b=[sum(X[n][i]*y[n] for n in range(len(y))) for i in range(k)]
    M=[A[i][:]+[b[i]]+[1.0 if i==j else 0.0 for j in range(k)] for i in range(k)]
    for i in range(k):
        p=max(range(i,k),key=lambda r:abs(M[r][i]));M[i],M[p]=M[p],M[i]
        for r in range(k):
            if r==i: continue
            f=M[r][i]/M[i][i]
            for c in range(i,2*k+1): M[r][c]-=f*M[i][c]
    beta=[M[i][k]/M[i][i] for i in range(k)]
    XtXi=[[M[i][k+1+j]/M[i][i] for j in range(k)] for i in range(k)]
    res=[y[n]-sum(beta[i]*X[n][i] for i in range(k)) for n in range(len(y))]
    L=max(1,int(4*(len(y)/100.0)**(2/9.)))
    Om=[[0.0]*k for _ in range(k)]
    for lag in range(L+1):
        w=1.0 if lag==0 else 1.0-lag/(L+1.0)
        mult=1 if lag==0 else 2
        for n in range(lag,len(y)):
            for i in range(k):
                xi=X[n][i]*res[n]
                for j in range(k): Om[i][j]+=w*mult*xi*X[n-lag][j]*res[n-lag]
    V=[[sum(XtXi[i][a]*Om[a][b2]*XtXi[b2][j] for a in range(k) for b2 in range(k)) for j in range(k)] for i in range(k)]
    return beta,[math.sqrt(max(V[i][i],0)) for i in range(k)]
y=[math.log(r[1]) for r in rows]
mw=sum(r[3] for r in rows)/len(rows); dil=-1.0/(P-mw)
X=[[1.0,r[3],r[2]] for r in rows]
beta,se=ols(X,y)
ALPHA=beta[1]/dil; SEA=se[1]/abs(dil); TC=beta[2]; SET=se[2]
print("JOINT FIT over the whole 12 h, n=%d  (HAC/Newey-West)"%len(rows))
print("  alpha  = %+.3f +/- %.3f   (fraction of the modelled dilution)"%(ALPHA,SEA))
print("  tempco = %+.3f +/- %.3f %%/K"%(TC*100,SET*100))
def series(a,tc):
    v=[]
    for r in rows:
        s=r[1]/(1.0+tc*(r[2]-T0))
        f=1-(1-(P-r[3])/P)*a
        v.append((s,f))
    lo,hi=3e5,7e5
    for _ in range(70):
        K=(lo+hi)/2
        m=sum((1-math.exp(-s*1000/K))/f for s,f in v)/len(v)*100
        if m>20.95: lo=K
        else: hi=K
    K=(lo+hi)/2
    return [(1-math.exp(-s*1000/K))/f*100 for s,f in v],K
def rep(v,lab):
    m=sum(v)/len(v);sd=math.sqrt(sum((x-m)**2 for x in v)/len(v))
    print("  %-46s sd %.4f pp   range %.3f pp"%(lab,sd,max(v)-min(v)))
print("\nflatness over the whole 12 h (true value constant: both vessels are air)")
rep([r[4] for r in rows],"published, uncorrected")
for a,tc,lab in ((1.0,0.0,"full dilution, no temperature"),
                 (ALPHA,0.0,"alpha=%.2f, no temperature"%ALPHA),
                 (ALPHA,TC,"alpha=%.2f + tempco %+.3f %%/K"%(ALPHA,TC*100))):
    v,K=series(a,tc); rep(v,lab)
json.dump({"alpha":ALPHA,"se_alpha":SEA,"tempco":TC,"se_tempco":SET},open("joint.json","w"))
