"""Monte-Carlo of the o2 cell correction-model calibration.

Model fitted:  I = I0 + K*(1 + a*(T-T0)) * ln(1/(1 - C*p/pref))
Estimated: sigma(I0), sigma(K), sigma(a), and the resulting %O2 error in the field.
"""
import numpy as np
from scipy.optimize import least_squares

rng = np.random.default_rng(20260907)
RTIA, VREF, ADCN, NAVG = 7000.0, 2.5, 62.5e-6, 8
PREF, T0 = 101.325, 20.0
CAIR_DRY = 0.20946
LAIR = np.log(1/(1-CAIR_DRY))

Iair0 = 100e-6            # DS-0637 Issue 2 (28-May-2026): 0.1 +/- 0.03 mA in air
K_TRUE = Iair0/LAIR
A_TRUE = 0.0020          # DS-0637 Issue 2 "%20C Output vs Temperature" curve, read as
                         # ~84 % at -40 C to ~105 % at +60 C => ~+0.2 %/K. NOT digitised.
I0_TRUE = 0.5*K_TRUE*np.log(1/(1-0.004))   # half the datasheet zero limit

def L(C, p=PREF): return np.log(1.0/(1.0 - np.clip(C*p/PREF, 0, 0.999)))
def model(th, C, T, p=PREF):
    I0, K, a = th
    return I0 + K*(1 + a*(T-T0))*L(C, p)

# --- plateau noise: ADC + short-term cell/gas stability -------------------
NPLAT = 20                       # 10 min at 30 s cadence
SIG_ADC = ADCN/np.sqrt(NAVG*NPLAT)/RTIA
def sig_I(I, rel=1e-3):          # 0.1 % of reading short-term cell/gas stability
    return np.hypot(SIG_ADC, rel*abs(I))

# --- reference-gas grades (1 sigma, relative unless noted) ---------------
GRADE = {
    "air_wet_corrected": 0.00005/0.2095,  # +-0.005 %O2 ABS from RH/p logging (a fraction
                                          # of 0.00005, not 0.0005 - the 10x typo the
                                          # 2026-09-07 Codex review caught)
    "N2_zero":           0.0,             # <5 ppm residual O2
    "mfc_mix":           0.010,           # 1 % rel, two-MFC blend
    "cyl_certified":     0.02,            # 2 % rel certification
}
SIG_T_MEAS = 0.1     # TMP117 accuracy, K
SIG_T_GRAD = 0.5     # cell-electrolyte vs TMP117 gradient in an isothermal bath, K

DESIGNS = {
 "A air-only @20C (today)":        dict(C=[0.20946], T=[20.0], g=["air_wet_corrected"], free="K"),
 "B N2+air @20C":                  dict(C=[0.0,0.20946], T=[20.0], g=["N2_zero","air_wet_corrected"], free="I0K"),
 "C N2+air x 5 T":                 dict(C=[0.0,0.20946], T=[10,25,40,50,60], g=["N2_zero","air_wet_corrected"], free="I0Ka"),
 "D 6 dilutions (MFC) x 5 T":      dict(C=[0.0,0.02,0.05,0.10,0.15,0.20946], T=[10,25,40,50,60],
                                        g=["N2_zero","mfc_mix","mfc_mix","mfc_mix","mfc_mix","air_wet_corrected"], free="I0Ka"),
 "E 6 dilutions (cyl) x 5 T":      dict(C=[0.0,0.02,0.05,0.10,0.15,0.20946], T=[10,25,40,50,60],
                                        g=["N2_zero","cyl_certified","cyl_certified","cyl_certified","cyl_certified","air_wet_corrected"], free="I0Ka"),
 "F 4 dilutions x 3 T (lean)":     dict(C=[0.0,0.05,0.10,0.20946], T=[15,35,55],
                                        g=["N2_zero","mfc_mix","mfc_mix","air_wet_corrected"], free="I0Ka"),
}

FIELD = [(0.21,25),(0.21,55),(0.10,45),(0.05,55),(0.05,65),(0.02,60)]

WEIGHTED = True


def run(dsg, ntrial=1500):
    Cs, Ts, gs = np.array(dsg["C"]), np.array(dsg["T"]), dsg["g"]
    grid_C = np.repeat(Cs, len(Ts)); grid_T = np.tile(Ts, len(Cs))
    grid_g = np.repeat(gs, len(Ts))
    pars, fielderr = [], []
    for _ in range(ntrial):
        # true gas differs from the nominal by the reference-gas error (one draw per level)
        dref = {i: rng.normal(0, GRADE[gs[i]]*max(Cs[i],1e-9)) for i in range(len(Cs))}
        Ctrue = np.array([Cs[i]+dref[i] for i in range(len(Cs))])
        Ctrue = np.repeat(np.clip(Ctrue,0,None), len(Ts))
        # The electrolyte-vs-sensor gradient is a property of the SETUP at a
        # given bath temperature, not of each gas level, so it is drawn once
        # per temperature level and shared across that level's points.
        dgrad = {t: rng.normal(0, SIG_T_GRAD) for t in Ts}
        Ttrue = grid_T + np.array([dgrad[t] for t in grid_T])
        Tmeas = grid_T + rng.normal(0, SIG_T_MEAS, grid_T.shape)
        I = model((I0_TRUE, K_TRUE, A_TRUE), Ctrue, Ttrue)
        I = I + rng.normal(0, sig_I(I))
        # Weight each residual by its TOTAL uncertainty, current noise combined
        # with the reference gas propagated through dI/dC = K/(1-C). Without
        # this the fit believes a 2 %-relative cylinder as much as an air point
        # good to 0.005 %O2, which is what made added points look harmful.
        if WEIGHTED:
            sref = np.array([GRADE[gs[i]]*max(Cs[i],1e-9) for i in range(len(Cs))])
            sref = np.repeat(sref, len(Ts))
            w = np.hypot(sig_I(I), K_TRUE*sref/(1.0-grid_C))
        else:
            w = sig_I(I)
        free = dsg["free"]
        if free == "K":
            f = lambda x: (I - model((0.0, x[0], 0.0), grid_C, Tmeas))/w
            r = least_squares(f, [K_TRUE]); th = (0.0, r.x[0], 0.0)
        elif free == "I0K":
            f = lambda x: (I - model((x[0], x[1], 0.0), grid_C, Tmeas))/w
            r = least_squares(f, [0.0, K_TRUE]); th = (r.x[0], r.x[1], 0.0)
        else:
            f = lambda x: (I - model((x[0], x[1], x[2]), grid_C, Tmeas))/w
            r = least_squares(f, [0.0, K_TRUE, 0.0]); th = tuple(r.x)
        pars.append(th)
        # field: invert the fitted model on truth-generated current
        errs = []
        for Cf, Tf in FIELD:
            Itrue = model((I0_TRUE, K_TRUE, A_TRUE), Cf, Tf)
            I0h, Kh, ah = th
            s = (Itrue - I0h)/(Kh*(1+ah*(Tf-T0)))
            errs.append((1-np.exp(-s)) - Cf)
        fielderr.append(errs)
    return np.array(pars), np.array(fielderr)

print(f"truth: K={K_TRUE*1e6:.3f} uA/ln, I0={I0_TRUE*1e9:.0f} nA (=0.2 %vol equiv), alpha={A_TRUE:.4f}/K\n")
hdr = "design                          sK/K%   sI0[nA]   sa[1/K]   " + "  ".join(f"{int(c*100)}%@{t}C" for c,t in FIELD)
print(hdr)
for name, d in DESIGNS.items():
    p, fe = run(d)
    sK = p[:,1].std()/K_TRUE*100
    sI0 = p[:,0].std()*1e9
    sa = p[:,2].std()
    # report RMS field error in percentage points O2
    rms = np.sqrt((fe**2).mean(axis=0))*100
    print(f"{name:30s} {sK:6.3f} {sI0:9.1f} {sa:9.5f}   " + "  ".join(f"{v:7.3f}" for v in rms))
print("\n(field columns: RMS |error| in percentage points O2, calibration uncertainty only;"
      f" WEIGHTED={WEIGHTED})")
