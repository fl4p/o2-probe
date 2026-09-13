#!/usr/bin/env python3
"""DS-0637 Issue 2 digitised mean (dsdig, overlay-review-required, NOT human-verified)
against the outdoor-run fits: slopes over the run's span, and the datasheet curve used
directly as g(T) with only K (and optionally alpha) fitted."""
import glob, sys
sys.path.insert(0, sys.path[0])
import numpy as np, pandas as pd
from scipy.optimize import least_squares
import fit as F
HERE = sys.path[0]
pts = pd.read_csv(glob.glob(f'{HERE}/ds0637/issue2/*.points.csv')[0])
def curve(series):
    s = pts[pts.series == series].groupby('temperature_c').output_pct.median().sort_index()
    return s.index.values, s.values
cur = {k: curve(k) for k in ('mean', 'upper', 'lower')}
def g_ds(t, k='mean'):
    x, y = cur[k]; return np.interp(t, x, y) / 100
print('== datasheet slopes, ppm/K of the 20 C output (local derivative via 5 K secant)')
for k in cur:
    row = [f'{(g_ds(t+2.5,k)-g_ds(t-2.5,k))/5/g_ds(t,k)*1e6:+5.0f}@{t}' for t in (0, 13, 20, 25, 30, 36, 45, 55)]
    print(f'  {k:5s}', ' '.join(row))
lo, hi = 12.86, 35.97
for k in cur:
    r = g_ds(hi, k) / g_ds(lo, k)
    print(f'  {k:5s} I({hi})/I({lo}) = {r:.4f}  -> mean slope {np.log(r)/(hi-lo)*1e6:+.0f} ppm/K')
cap = 0.75*np.log((hi+273.15)/(lo+273.15))
print(f'  T^0.75 law         ratio {np.exp(cap):.4f}  -> {cap/(hi-lo)*1e6:+.0f} ppm/K')

df, ok = F.load()
d = F.with_T(df, 't_ext_c', 0)
_, _, r = F.fit(d[ok], {'law': 'lin'}); keep = ok.copy(); keep[d[ok].index[abs(r) > 0.01]] = False
N = keep & (df.index < '2026-09-13T07:00Z'); D = keep & (df.index >= '2026-09-13T07:00Z')
for m, nm in [(keep, 'all'), (N, 'night'), (D, 'day')]:
    s = d[m]; print(f'  run {nm:5s}: T_EXT {s.t_ext_c.min():.2f}..{s.t_ext_c.max():.2f}')

def fit_ds(m, alpha=None, k='mean'):
    s = d[m]; y = np.log(s.cell_ua.values); lg = np.log(g_ds(s['T'].values, k)); x = s.x.values
    def res(p):
        a = alpha if alpha is not None else p[1]
        return p[0] + lg + np.log(F.L(F.C0*(1-a*x))/F.L(F.C0)) - y
    q = least_squares(res, [np.log(100)] + ([] if alpha is not None else [0.5]))
    a = alpha if alpha is not None else q.x[1]
    return q.x[0], a, np.sqrt(np.mean(q.fun**2))*100
def pred(lnK, a, m, k='mean'):
    s = d[m]
    e = lnK + np.log(g_ds(s['T'].values, k)) + np.log(F.L(F.C0*(1-a*s.x.values))/F.L(F.C0)) - np.log(s.cell_ua.values)
    return np.sqrt(np.mean(e**2))*100, np.median(e)*100

print('\n== datasheet curve as g(T) on T_EXT (zero temperature parameters)')
for k in ('mean', 'upper', 'lower'):
    for a in (None, 1.0, 0.8, 0.5):
        lnK, aa, rin = fit_ds(keep, a, k)
        lnKn, _, _ = fit_ds(N, a if a is not None else None, k); _, an, _ = fit_ds(N, a, k)
        lnKd, ad, _ = fit_ds(D, a, k)
        e_nd, o_nd = pred(lnKn, an, D, k); e_dn, o_dn = pred(lnKd, ad, N, k)
        lab = 'free' if a is None else f'{a:.1f}'
        print(f'  {k:5s} alpha {lab:4s}: all rms {rin:.3f}% alpha {aa:+.3f} | N->D {e_nd:.3f}% off {o_nd:+.3f} | D->N {e_dn:.3f}% off {o_dn:+.3f}'
              + ('' if a is not None else f' | alpha night {an:+.3f} day {ad:+.3f}'))
