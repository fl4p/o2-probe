#!/usr/bin/env python3
"""Tempco + water-vapour dilution fit, probe 3 outdoors, 2026-09-12 18:40 UTC -> now.

Truth assumption (Fab, 2026-09-13): the probe was outside the whole time, so the
dry-basis O2 fraction is 20.946 %vol throughout. Cell current model:

    I = K * g(T) * L(C0 * (1 - alpha * p_w/P)) / L(C0),   L(c) = -ln(1 - c)

g(T): exp(beta*(T - 20)) on a chosen temperature regressor (optionally
first-order lagged), or the capillary law (T_K/293.15)^0.75 with no free term.
p_w = RH_chamber * psat(T_chamber) (SHT45, same die), P = Open-Meteo surface
pressure for 48.04N 8.03E interpolated - a SYNOPTIC PROXY, not a site reading.

    python3 fit.py            (reads gas.pkl + openmeteo.json next to it)
"""
import json, sys
import numpy as np, pandas as pd
from scipy.optimize import least_squares

HERE = sys.path[0]
C0 = 0.20946
INVALIDATE = 0x6866
START = '2026-09-12T18:40Z'


def psat_hpa(t):  # Buck 1996, over water
    return 6.1121 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def L(c):
    return -np.log1p(-c)


def lag(series, t_s, tau):
    if tau <= 0:
        return series.copy()
    out = np.empty_like(series)
    out[0] = series[0]
    for i in range(1, len(series)):
        dt = t_s[i] - t_s[i - 1]
        if dt > 900:  # gap: restart the filter rather than integrate across it
            out[i] = series[i]
            continue
        a = 1 - np.exp(-dt / tau)
        out[i] = out[i - 1] + a * (series[i] - out[i - 1])
    return out


def load():
    df = pd.read_pickle(f'{HERE}/gas.pkl')[START:]
    om = json.load(open(f'{HERE}/openmeteo.json'))['hourly']
    p = pd.Series(om['surface_pressure'], index=pd.to_datetime(om['time'], utc=True))
    t_s = df.index.astype('int64') / 1e9
    df['P'] = np.interp(t_s, p.index.astype('int64') / 1e9, p.values)
    df['t_s'] = t_s - t_s[0]
    # lags need the unfiltered series (rows are dropped after)
    raw = df.dropna(subset=['t_ext_c'])
    ok = (df.settle_s == 0) & ((df.faults.fillna(0xFFFF).astype(int) & INVALIDATE) == 0) \
        & df.cell_ua.between(50, 150)
    for c in ['cell_ua', 't_ext_c', 't_chamber_c', 't_afe_c', 'rh_chamber_pct']:
        ok &= np.isfinite(df[c])
    df['x'] = df.rh_chamber_pct / 100 * psat_hpa(df.t_chamber_c) / df.P
    print(f'rows {len(df)}, usable {ok.sum()}, dropped {len(df) - ok.sum()}')
    return df, ok


def model(params, d, spec):
    lnK, alpha = params[0], params[1]
    k = 2
    ln_g = 0.0
    if spec['law'] == 'lin':
        ln_g = params[k] * (d['T'] - 20); k += 1
    elif spec['law'] == 'cap':
        ln_g = 0.75 * np.log((d['T'] + 273.15) / 293.15)
    if spec.get('afe'):
        ln_g = ln_g + params[k] * (d['t_afe_c'] - 20); k += 1
    return lnK + ln_g + np.log(L(C0 * (1 - alpha * d['x'])) / L(C0))


def fit(d, spec, alpha_fixed=None):
    n = 2 + (spec['law'] == 'lin') + bool(spec.get('afe'))
    y = np.log(d['cell_ua'].values)
    dd = {c: d[c].values for c in ['T', 'x', 't_afe_c']}

    def res(p):
        if alpha_fixed is not None:
            p = np.r_[p[0], alpha_fixed, p[1:]]
        return model(p, dd, spec) - y
    p0 = np.r_[np.log(100), 0.5, np.zeros(n - 2)]
    if alpha_fixed is not None:
        p0 = np.delete(p0, 1)
    r = least_squares(res, p0)
    p = r.x if alpha_fixed is None else np.r_[r.x[0], alpha_fixed, r.x[1:]]
    return p, np.sqrt(np.mean(r.fun ** 2)) * 100, r.fun


def with_T(df, src, tau):
    d = df.copy()
    base = df[src].interpolate(limit_area='inside').values
    d['T'] = lag(base, df.t_s.values, tau)
    return d


def block_boot(d, ok, spec, n=400, block='30min', seed=1):
    dd = d[ok]
    groups = [g for _, g in dd.groupby(pd.Grouper(freq=block)) if len(g)]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        s = pd.concat([groups[i] for i in pick])
        out.append(fit(s, spec)[0])
    return np.array(out)


def describe(p, spec):
    s = f'alpha {p[1]:+.3f}'
    k = 2
    if spec['law'] == 'lin':
        s += f'  beta {p[k] * 1e6:+6.0f} ppm/K'; k += 1
    if spec.get('afe'):
        s += f'  afe {p[k] * 1e6:+6.0f} ppm/K'
    return s


def main():
    df, ok = load()
    night = ok & (df.index < '2026-09-13T07:00Z')
    day = ok & (df.index >= '2026-09-13T07:00Z')
    d0 = df[ok]
    print(f"span T_ext {d0.t_ext_c.min():.2f}..{d0.t_ext_c.max():.2f} C, "
          f"T_chamber {d0.t_chamber_c.min():.2f}..{d0.t_chamber_c.max():.2f}, "
          f"p_w/P {d0.x.min() * 100:.2f}..{d0.x.max() * 100:.2f} %, "
          f"I {d0.cell_ua.min():.2f}..{d0.cell_ua.max():.2f} uA, "
          f"P {d0.P.min():.1f}..{d0.P.max():.1f} hPa")
    for name, m in [('all', ok), ('night', night), ('day', day)]:
        s = df[m]
        print(f"  corr {name:5s} n={m.sum():3d}  r(T_ext,x)={np.corrcoef(s.t_ext_c, s.x)[0, 1]:+.3f}"
              f"  r(T_ext,T_afe)={np.corrcoef(s.t_ext_c, s.t_afe_c)[0, 1]:+.3f}"
              f"  r(T_ext,hours)={np.corrcoef(s.t_ext_c, s.t_s)[0, 1]:+.3f}")

    print('\n== tau scan, linear tempco on lagged T_ext, alpha free (all usable rows)')
    for tau in [0, 120, 300, 600, 900, 1200, 1800]:
        d = with_T(df, 't_ext_c', tau)
        p, rms, _ = fit(d[ok], {'law': 'lin'})
        print(f'  tau {tau:5d} s  rms {rms:.3f} %  {describe(p, {"law": "lin"})}')

    specs = [
        ('T_ext, lin', 't_ext_c', 0, {'law': 'lin'}),
        ('T_ext, T^0.75 (0 free)', 't_ext_c', 0, {'law': 'cap'}),
        ('T_chamber, lin', 't_chamber_c', 0, {'law': 'lin'}),
        ('T_ext + T_afe, lin', 't_ext_c', 0, {'law': 'lin', 'afe': True}),
    ]
    print('\n== models: in-sample, and cross-prediction (fit one half, predict the other)')
    print(f'  {"model":24s} {"all rms":>8s}  params(all)                       '
          f'{"N->D rms":>8s} {"D->N rms":>8s}   night params / day params')
    for label, src, tau, spec in specs:
        d = with_T(df, src, tau)
        p, rms, _ = fit(d[ok], spec)
        pn, _, _ = fit(d[night], spec)
        pd_, _, _ = fit(d[day], spec)
        yd = np.log(d[day].cell_ua.values); yn = np.log(d[night].cell_ua.values)
        dd_day = {c: d[day][c].values for c in ['T', 'x', 't_afe_c']}
        dd_ngt = {c: d[night][c].values for c in ['T', 'x', 't_afe_c']}
        # cross prediction keeps K from the fitting half: an offset error is the point
        e_nd = np.sqrt(np.mean((model(pn, dd_day, spec) - yd) ** 2)) * 100
        e_dn = np.sqrt(np.mean((model(pd_, dd_ngt, spec) - yn) ** 2)) * 100
        print(f'  {label:24s} {rms:7.3f}%  {describe(p, spec):34s} {e_nd:7.3f}% {e_dn:7.3f}%   '
              f'{describe(pn, spec)} / {describe(pd_, spec)}')

    print('\n== alpha profile, T_ext linear tempco refit (all rows)')
    d = with_T(df, 't_ext_c', 0)
    for a in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25]:
        p, rms, _ = fit(d[ok], {'law': 'lin'}, alpha_fixed=a)
        print(f'  alpha {a:4.2f}  rms {rms:.3f} %  beta {p[2] * 1e6:+6.0f} ppm/K')

    print('\n== 30-min block bootstrap, T_ext linear, 400 draws')
    b = block_boot(d, ok, {'law': 'lin'})
    for i, nm, sc in [(1, 'alpha', 1), (2, 'beta ppm/K', 1e6)]:
        lo, med, hi = np.percentile(b[:, i] * sc, [2.5, 50, 97.5])
        print(f'  {nm:11s} median {med:+8.3f}  95% {lo:+8.3f} .. {hi:+8.3f}')
    print(f'  corr(alpha, beta) across draws {np.corrcoef(b[:, 1], b[:, 2])[0, 1]:+.3f}')

    # what the probe would publish under the fitted pair, vs what it did
    p, rms, r = fit(d[ok], {'law': 'lin'})
    s = d[ok]
    g = np.exp(p[2] * (s['T'] - 20))
    frac_wet = 1 - np.exp(-(s.cell_ua / (np.exp(p[0]) * g)) * L(C0))
    dry = frac_wet / (1 - p[1] * s.x) * 100
    out = pd.DataFrame({'published': s.pct_vol, 'fitted_dry': dry, 'T_ext': s.t_ext_c,
                        'pw_pct': s.x * 100, 'I': s.cell_ua, 'duty': s.heater_duty_pct})
    out.to_csv(f'{HERE}/fitted.csv')
    print('\n== published vs fitted-model dry O2 (%vol), 1-h medians')
    print(out.resample('1h').median().round(3).to_string())
    print(f"published range {out.published.min():.2f}..{out.published.max():.2f}, "
          f"sd {out.published.std():.3f};  fitted range {dry.min():.2f}..{dry.max():.2f}, sd {dry.std():.3f}")


if __name__ == '__main__':
    main()
