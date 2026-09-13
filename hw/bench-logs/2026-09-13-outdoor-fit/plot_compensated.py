#!/usr/bin/env python3
"""Published vs compensated O2 (T^0.75 on T_EXT, alpha=1, K fitted) for the outdoor run."""
import sys; sys.path.insert(0, sys.path[0])
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as mdates
import fit as F
df, ok = F.load()
d = F.with_T(df, 't_ext_c', 0)
_, _, r = F.fit(d[ok], {'law': 'lin'})
keep = ok.copy(); keep[d[ok].index[abs(r) > 0.01]] = False
spec = {'law': 'cap'}; ALPHA = 1.0
p, rms, _ = F.fit(d[keep], spec, alpha_fixed=ALPHA)
s = d[keep]
g = ((s['T'] + 273.15) / 293.15) ** 0.75
wet = 1 - np.exp(-(s.cell_ua / (np.exp(p[0]) * g)) * F.L(F.C0))
dry = wet / (1 - ALPHA * s.x) * 100
tz = 'Europe/Berlin'
# break lines across gaps (settle windows, reboots) instead of bridging them
gap = s.index.to_series().diff().dt.total_seconds() > 180
plot = pd.DataFrame({'pct_vol': s.pct_vol, 'dry': dry, 't_ext_c': s.t_ext_c})
nan_rows = plot[gap].copy(); nan_rows[:] = np.nan; nan_rows.index = nan_rows.index - pd.Timedelta(seconds=1)
plot = pd.concat([plot, nan_rows]).sort_index()
t = plot.index.tz_convert(tz)
INK, MUTED, GRID = '#1a1a19', '#6b6a63', '#e6e5df'; BLUE, ORANGE = '#2a78d6', '#eb6834'
fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, gridspec_kw={'height_ratios': [2.2, 1]})
for a in (a1, a2):
    a.grid(axis='y', color=GRID, lw=0.8); a.set_axisbelow(True)
    for sp in ('top', 'right'): a.spines[sp].set_visible(False)
    for sp in ('left', 'bottom'): a.spines[sp].set_color(GRID)
    a.tick_params(colors=MUTED, labelsize=9)
a1.axhline(20.946, color=MUTED, lw=1, ls=(0, (4, 3)))
a1.annotate('dry air\n20.946', xy=(1.0, 20.946), xycoords=('axes fraction', 'data'), xytext=(6, 0), textcoords='offset points', color=MUTED, fontsize=8.5, va='center')
a1.plot(t, plot.pct_vol, color=ORANGE, lw=1.6, label='published (TEMPCO 0, alpha 1)')
a1.plot(t, plot.dry, color=BLUE, lw=1.6, label='compensated: (T_ext)^0.75, alpha 1')
a1.text(s.index[-1].tz_convert(tz), s.pct_vol.iloc[-8:].median() + 0.05, '  published', color=INK, fontsize=9, va='bottom', ha='right')
a1.text(s.index[-1].tz_convert(tz), dry.iloc[-8:].median() - 0.08, '  compensated', color=INK, fontsize=9, va='top', ha='right')
a1.set_ylabel('O₂, %vol (dry)', color=INK, fontsize=10)
a1.legend(loc='upper left', frameon=False, fontsize=9, bbox_to_anchor=(0, 1.02), ncol=2)
a1.set_title(f'Probe 3 outdoors, 12–13 Sep 2026 — compensated sd {dry.std():.3f} %vol vs published {s.pct_vol.std():.3f}',
             loc='left', color=INK, fontsize=11.5, pad=18)
a2.plot(t, plot.t_ext_c, color=BLUE, lw=1.6)
a2.set_ylabel('T_ext, °C', color=INK, fontsize=10)
a2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=tz))
a2.set_xlabel('CEST', color=MUTED, fontsize=9)
fig.text(0.01, 0.005, f'K {np.exp(p[0])*1000:,.0f} nA fitted on {len(s)} clean 1-min rows; 9 single-sample spikes removed. '
         'Gaps = settle windows / probe reboots. Pressure: Open-Meteo regional proxy. Data to 13:23 CEST.', color=MUTED, fontsize=8)
fig.tight_layout(rect=(0, 0.02, 1, 1)); fig.savefig(f'{sys.path[0]}/o2-compensated.png', dpi=150)
pd.DataFrame({'published': s.pct_vol, 'compensated': dry, 't_ext_c': s.t_ext_c}).to_csv(f'{sys.path[0]}/o2-compensated.csv')
print('range pub', s.pct_vol.min(), s.pct_vol.max(), 'comp', dry.min().round(3), dry.max().round(3), 'rms fit', round(rms, 3))
