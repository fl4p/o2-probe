import numpy as np
rng = np.random.default_rng(7)

# ---------------- chain constants (datasheet-sourced) ----------------
RTIA   = 7000.0          # LMP91000 TIA_GAIN=011, 7 kOhm (SNAS506I)
VREF   = 2.5             # V, trimmed
ADC_N  = 62.5e-6         # ADS1119 input-referred noise, gain 1, 20 SPS (SBAS925A Table 1)
NAVG   = 8               # O2P_N_O2 conversions averaged per reported sample
LSB    = 2*VREF/65536    # ADS1119 16-bit bipolar, ext ref 2.5 V
CAIR   = 0.20946
LAIR   = np.log(1/(1-CAIR))

def L(C, p_kpa=101.325, pref=101.325):
    return np.log(1.0/(1.0 - C*p_kpa/pref))

Iair = 100e-6            # DS-0637 Issue 2 (28-May-2026) nominal output in air
K    = Iair/LAIR         # A per ln-unit

print("== chain resolution ==")
print(f"LSB           {LSB*1e6:8.2f} uV = {LSB/RTIA*1e9:7.2f} nA")
print(f"ADC noise/sample (N=8) {ADC_N/np.sqrt(NAVG)*1e6:6.2f} uVrms = {ADC_N/np.sqrt(NAVG)/RTIA*1e9:6.2f} nArms")
# dC/dI at fraction C:  C = 1-exp(-I/K) -> dC/dI = (1-C)/K
for C in (0.20946, 0.05, 0.01):
    dCdI = (1-C)/K
    print(f"  at {C*100:5.2f} %O2: 1 LSB = {LSB/RTIA*dCdI*100:8.4f} %O2 ; "
          f"1 sample sigma = {ADC_N/np.sqrt(NAVG)/RTIA*dCdI*100:8.4f} %O2 ; "
          f"20-sample plateau = {ADC_N/np.sqrt(NAVG*20)/RTIA*dCdI*100:8.4f} %O2")

print("\n== static electronic offsets (do NOT cancel in a 1-point air cal) ==")
# LMP91000 internal-zero accuracy +-0.04 %  (of VREF, worst reading)
for label, dv in (("int-zero 0.04% of VREF", 0.0004*VREF),
                  ("int-zero 0.04% of 0.67*VREF", 0.0004*0.67*VREF),
                  ("ADS1119 INL 15 ppm FSR", 15e-6*2*VREF)):
    b = dv/RTIA
    # air-point cal absorbs it partly: C_est = 1-exp(-LAIR*(I+b)/(Iair+b))
    Cz = 1-np.exp(-LAIR*b/(Iair+b))
    print(f"{label:32s}: {dv*1e6:7.1f} uV = {b*1e9:7.1f} nA -> apparent O2 in pure N2 {Cz*100:6.3f} %")

print("\n== the terms that actually dominate ==")
zero_cell = 0.004      # DS-0637 'Zero Signal (20 C) < 0.4 %vol O2'
b_cell = K*L(zero_cell)
print(f"cell zero current (<0.4 %vol O2)      : {b_cell*1e9:7.1f} nA equivalent")
print(f"cell air output tolerance +-0.03 mA   : {0.03/0.10*100:5.1f} % of reading (cancels in ratio, sets K)")
print(f"TIA gain accuracy 5%, ADC gain 0.01%  : cancels in S/K to first order")
