#!/usr/bin/env python3
"""Plot the heater step response and fit the thermal model.

The whole power-sizing argument rests on one number, theta = dT/P, and that
number comes from the asymptote of this step - not from its initial slope,
which underestimates it by about 2x. So the fit is drawn on top of the data
rather than quoted beside it: if the tail is not flat, the number is wrong and
the picture says so.
"""
import csv, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

SRC = sys.argv[1] if len(sys.argv) > 1 else "heater-2026-09-04.csv"
R_HEATER = 140.0          # RH1||RH2, O2P_HW_HEATER_OHM

rows = [r for r in csv.DictReader(open(SRC)) if r["status"] == "ok"]
t0 = datetime.fromisoformat(rows[0]["iso_time"])
def f(r, k):
    v = r[k]
    return float(v) if v not in ("", None) else np.nan

t    = np.array([(datetime.fromisoformat(r["iso_time"]) - t0).total_seconds() for r in rows])
o2   = np.array([f(r, "o2_comp_pct") for r in rows])
# o2_raw_ua, NOT cell_ua. cell_ua is this tool re-deriving current from
# afe_vout_mv, a diagnostic register published as INTEGER millivolts: 1 mV
# across the 7 kohm TIA is 0.143 uA, and that quantisation is an artefact of
# the readout path, not of the measurement. o2_raw_ua is the firmware's own
# value, computed from the raw 16-bit code (1 LSB = 76.3 uV = 10.9 nA).
cell = np.array([f(r, "o2_raw_ua") for r in rows])
cellq = np.array([f(r, "cell_ua") for r in rows])
die  = np.array([f(r, "t_die_c") for r in rows])
tip  = np.array([f(r, "t_tip_c") for r in rows])
cham = np.array([f(r, "t_chamber_c") for r in rows])
duty = np.array([f(r, "heater_duty_pct") for r in rows])
rh   = np.array([f(r, "rh_pct") for r in rows])
vin  = np.array([f(r, "vin_mv") for r in rows]) / 1000.0

GAP_S = 40.0
gap = np.where(np.diff(t) > GAP_S)[0]
def brk(y):
    """Insert NaN after each gap so no line is drawn across missing samples."""
    return np.insert(y.astype(float), gap + 1, np.nan)
tb = brk(t)
gap_spans = [(t[i], t[i + 1]) for i in gap]

# The contiguous heated segment.
on = duty > 0.1
idx = np.where(on)[0]
seg = np.arange(idx[0], idx[-1] + 1)
ts, Ts = t[seg] - t[seg][0], tip[seg]
T_pre = np.nanmean(tip[max(0, idx[0] - 3):idx[0]])

# T(t) = A + B*exp(-t/tau). Grid tau, solve A,B linearly - no scipy needed.
best = None
for tau in np.arange(5, 400, 0.5):
    X = np.column_stack([np.ones_like(ts), np.exp(-ts / tau)])
    coef, *_ = np.linalg.lstsq(X, Ts, rcond=None)
    resid = np.sum((X @ coef - Ts) ** 2)
    if best is None or resid < best[0]:
        best = (resid, tau, coef)
_, tau, (A, B) = best
dT = A - T_pre
P  = np.nanmean(duty[seg]) / 100.0 * np.nanmean(vin[seg]) ** 2 / R_HEATER
theta, C = dT / P, tau / (dT / P)

fig, (ax1, axo, ax3) = plt.subplots(3, 1, figsize=(11, 10.5), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1.3, 1]})
fig.suptitle("o2-probe heater step response — first article, no ring, still air\n"
             f"2026-09-04  ·  {SRC}", fontsize=12, y=0.98)

ax1.plot(tb, brk(tip), ".-", ms=3, lw=1, color="#c0392b", label="tip (TMP117)")
ax1.plot(tb, brk(cham), ".-", ms=3, lw=1, color="#e67e22", alpha=.7, label="chamber (SHT45)")
# The die sits across the transverse thermal barrier and does NOT track the
# tip: it is the only sensor on this board that shows a real gradient.
ax1.plot(tb, brk(die), ".-", ms=3, lw=1, color="#2980b9", alpha=.85,
         label="MCU die (STM32 ADC, 0.29 K/LSB)")
tf = np.linspace(0, ts[-1], 400)
ax1.plot(t[seg][0] + tf, A + B * np.exp(-tf / tau), "--", lw=1.8, color="#2c3e50",
         label=f"fit: $T_\\infty$={A:.2f} °C, $\\tau$={tau:.0f} s")
ax1.axhline(T_pre, color="#7f8c8d", ls=":", lw=1)
ax1.axhline(A, color="#2c3e50", ls=":", lw=1)
ax1.annotate("", xy=(t[seg][-1] + 40, A), xytext=(t[seg][-1] + 40, T_pre),
             arrowprops=dict(arrowstyle="<->", color="#2c3e50"))
ax1.text(t[seg][-1] + 60, (A + T_pre) / 2, f"ΔT = {dT:.2f} K", va="center", fontsize=11)
d_tc = np.nanmax(np.abs(tip - cham))
on_i, off_i = seg[len(seg)//2], 0
ax1.set_title(f"tip−chamber never exceeds {d_tc:.2f} K (one thermal node, 6.6 mm apart)  ·  "
              f"tip−die swings {np.nanmin(tip-die):+.1f} → {np.nanmax(tip-die):+.1f} K",
              fontsize=9, color="#444", pad=6)
ax1.set_ylabel("temperature (°C)")
ax1.legend(loc="upper left", fontsize=9)
ax1.grid(alpha=.3)

box = (f"duty {np.nanmean(duty[seg]):.2f} %   P = {P*1000:.1f} mW\n"
       f"ΔT = {dT:.2f} K   →   θ = {theta:.0f} K/W\n"
       f"τ = {tau:.0f} s   →   C = {C:.2f} J/K\n"
       f"gain = {dT/np.nanmean(duty[seg]):.2f} K per % duty\n"
       f"+2 K needs {2.0/(dT/np.nanmean(duty[seg])):.1f} % duty")
ax1.text(.985, .04, box, transform=ax1.transAxes, ha="right", va="bottom",
         fontsize=10, family="monospace",
         bbox=dict(fc="#fdf6e3", ec="#b58900", alpha=.95, boxstyle="round,pad=.5"))

# Oxygen - the measurement the probe exists for, and the one that has to
# survive everything above it.
axo.plot(tb, brk(o2), ".-", ms=3, lw=1.2, color="#16a085", label="O$_2$ compensated (%vol)")
axo.set_ylabel("O$_2$ (%vol)", color="#16a085"); axo.tick_params(axis="y", colors="#16a085")
fin = o2[np.isfinite(o2)]
if fin.size:
    axo.set_ylim(fin.min() - .12, fin.max() + .12)
    axo.axhline(fin.mean(), color="#16a085", ls=":", lw=1)
    axo.text(.985, .95, f"O$_2$ {fin.min():.2f}–{fin.max():.2f} %vol "
                        f"(span {fin.max()-fin.min():.2f} %vol) "
                        f"through a {np.nanmax(tip)-np.nanmin(tip):.1f} K excursion",
             transform=axo.transAxes, ha="right", va="top", fontsize=9,
             bbox=dict(fc="#eafaf1", ec="#16a085", alpha=.9, boxstyle="round,pad=.4"))
axc = axo.twinx()
axc.plot(tb, brk(cellq), lw=.9, color="#bdc3c7", label="cell via afe_vout_mv (0.14 µA/LSB)")
axc.plot(tb, brk(cell), lw=1.2, color="#8e44ad", alpha=.85, label="cell, O2_RAW (0.01 µA)")
axc.set_ylabel("cell (µA)", color="#8e44ad"); axc.tick_params(axis="y", colors="#8e44ad")
axc.legend(loc="lower left", fontsize=8)
axo.grid(alpha=.3)
axo.legend(loc="center left", fontsize=9)

ax2 = ax3.twinx()
ax3.plot(tb, brk(rh), lw=1.2, color="#2980b9", label="chamber RH")
ax3.set_ylabel("RH (%)", color="#2980b9"); ax3.tick_params(axis="y", colors="#2980b9")
ax2.step(tb, brk(duty), where="post", lw=1.4, color="#27ae60", label="heater duty")
ax2.set_ylabel("duty (%)", color="#27ae60"); ax2.tick_params(axis="y", colors="#27ae60")
ax2.set_ylim(-0.3, max(6, np.nanmax(duty) * 1.3))
ax3.set_xlabel("seconds since %s" % rows[0]["iso_time"])
ax3.grid(alpha=.3)

for ax in (ax1, axo, ax3):
    ax.axvspan(t[seg][0], t[seg][-1], color="#27ae60", alpha=.07)
    for a, b in gap_spans:
        ax.axvspan(a, b, color="#95a5a6", alpha=.18, hatch="//", ec="none")
ax1.text(sum(gap_spans[0]) / 2 if gap_spans else 0, np.nanmax(tip),
         "no data\n(core halted\nfor cutoff test)", ha="center", va="top",
         fontsize=8, color="#555") if gap_spans else None

fig.tight_layout(rect=[0, 0, 1, .95])
fig.savefig("heater-step.webp", dpi=150)
print("gaps broken:", [(f"{a:.0f}", f"{b:.0f}") for a, b in gap_spans])
print(f"duty={np.nanmean(duty[seg]):.2f}%  P={P*1000:.1f}mW  dT={dT:.3f}K  "
      f"theta={theta:.1f}K/W  tau={tau:.0f}s  C={C:.2f}J/K  "
      f"gain={dT/np.nanmean(duty[seg]):.3f}K/%")
print("wrote heater-step.webp")
