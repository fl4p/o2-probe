import math
A,B,ES0 = 17.62, 243.12, 6.112
def es(t): return ES0*math.exp(A*t/(B+t))
def t_for_es(p):
    y = math.log(p/ES0); return B*y/(A-y)

print("Cell limits (DS-0637 Issue 2): T <= 60 C, RH <= 90 % continuous non-condensing")
print()
print(" pile T   es(T)    to reach 90%RH   heater dT   verdict")
for T in (40,45,50,55,58,60,65,70,75):
    p = es(T)                      # saturated pile gas
    Tn = t_for_es(p/0.90)          # local T that dilutes 100->90 %RH
    dT = Tn - T
    if T > 60:   v = "IMPOSSIBLE - pile alone exceeds the 60 C cell rating"
    elif Tn > 60: v = "IMPOSSIBLE - needs %.1f C, above the 60 C cell rating" % Tn
    else:        v = "ok, %.2f K of heating" % dT
    print(f"  {T:3d} C  {p:7.2f} hPa   {Tn:6.2f} C      +{dT:5.2f} K   {v}")

print()
# where does it close?
lo,hi = 30.0,60.0
for _ in range(200):
    m=(lo+hi)/2
    if t_for_es(es(m)/0.90) > 60: hi=m
    else: lo=m
print(f"Envelope closes at pile T = {lo:.2f} C saturated (heating to exactly 60.00 C)")
print(f"  above that, no heater duty can satisfy both limits at once.")
print()
# how much RH can you actually reach at the 60 C ceiling from various pile T
print(" pile T  best RH achievable while staying <= 60 C")
for T in (50,52,55,57,58,59,60):
    best = 100*es(T)/es(60.0) if T<=60 else float('nan')
    print(f"  {T:3d} C   {best:6.2f} %")
