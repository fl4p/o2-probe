import numpy as np
def psat_kPa(T):                      # Sonntag/Magnus over water
    return 0.61094*np.exp(17.62*T/(243.12+T))
P_SITE = 101.325*(1-2.25577e-5*715)**5.2559     # Steingrubenhof 715 m

print(f"site pressure at 715 m: {P_SITE:.2f} kPa ({P_SITE/101.325-1:+.1%} vs sea level)\n")
print("water-vapour dilution of the pore gas (100 %RH):")
print(" T[C]  psat[kPa]  p_w/p    O2_wet if O2_dry=20.95   ... if O2_dry=5.00   d(O2_wet)/dT [%O2/K]")
for T in (20,30,40,50,55,60,65,70):
    f = psat_kPa(T)/P_SITE
    fp = psat_kPa(T+1)/P_SITE
    print(f" {T:4d} {psat_kPa(T):9.2f} {f:8.3f} {20.95*(1-f):19.2f} {5.0*(1-f):17.3f} "
          f"{20.95*(fp-f)*-1:14.3f}")

print("\nbarometric weather swing at the site (+-2 kPa) -> apparent O2 (uncorrected, air-cal in situ):")
for C in (0.2095,0.10,0.05):
    # cell sees pO2; C_apparent = 1-exp(-L(C*p/pref_cal)) with pref_cal the cal-day pressure
    for dp in (-2.0, 2.0):
        s = np.log(1/(1-C*(P_SITE+dp)/P_SITE))
        print(f"  O2={C*100:5.2f}% dp={dp:+.0f} kPa -> {(1-np.exp(-s))*100-C*100:+7.3f} %O2")

print("\nCO2 enhancement, 0.3 % of signal per 1 % CO2 (SGX DS-0143, 4-series; UNVERIFIED for the Mini):")
K=100e-6/np.log(1/(1-0.20946))
for C in (0.2095,0.15,0.10,0.05,0.02):
    co2 = max(20.9-C*100,0.0)
    I = K*np.log(1/(1-C))*(1+0.003*co2)
    print(f"  O2={C*100:5.2f}%  CO2~{co2:4.1f}%  signal x{1+0.003*co2:5.3f} -> reads {(1-np.exp(-I/K))*100:6.3f} % "
          f"({(1-np.exp(-I/K))*100-C*100:+6.3f} %O2)")

print("\ntempco leverage: error in %O2 for a 1 K error in cell temperature")
for a,lbl in ((0.0025,"capillary, +0.25 %/K"),(0.020,"membrane, +2 %/K")):
    for C in (0.2095,0.05):
        s=np.log(1/(1-C)); dC=(1-C)*s*a
        print(f"  alpha={lbl:22s} O2={C*100:5.2f}% -> {dC*100:+6.3f} %O2 per K")
