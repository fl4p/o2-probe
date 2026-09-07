# o2-probe battery budget. All currents from datasheets fetched 2026-09-07.
WH = 12.0*10.0          # 120 Wh gross
BUCK_ETA = 0.85         # AP63205 ~88% @5mA (DS41326); 0.85 at our few-mA load
BUCK_IQ_A = 22e-6       # AP63205 quiescent, non-switching, no load
V3 = 3.3

# (name, uA @3V3, uA in a duty-cycled/gated design)
ITEMS = [
 ("STM32G071 run 16MHz flash R1",  1800.0, 4.0),    # DS12232 T24; Stop1 flash-off RTC-on 25C
 ("THVD1410 Rx enabled, no load",   700.0, 1.0),    # Rx-en ICC 700 typ / 960 max
 ("ADS1119 AVDD conv, int ref",     250.0, 0.1),    # power-down 0.1 uA
 ("ADS1119 DVDD conv",               65.0, 0.3),
 ("TMP117 500ms cycle, 8-avg",       32.0, 0.15),   # 2x the 1Hz 8-avg 16 uA; shutdown 150 nA
 ("LMP91000 MODECN=0x03",            10.0, 10.0),   # 3-lead amperometric: MUST stay on
 ("SHT45",                            0.4, 0.08),
 ("TPS7A2033 x2 IGND",               13.0, 13.0),   # 6.5 uA typ each
]

def batt_mw(u3):
    p5 = u3*1e-6*V3 / 1.0            # LDO: same current, drawn from 5 V
    p5 = u3*1e-6*5.0
    return (p5/BUCK_ETA + BUCK_IQ_A*12.0)*1000.0

for label, idx in (("AS BUILT (Rev A, nothing gated)",1), ("DUTY-CYCLED (Stop1 + gated)",2)):
    tot = sum(r[idx] for r in ITEMS)
    mw = batt_mw(tot)
    print(f"\n-- {label} --")
    for r in ITEMS: print(f"   {r[0]:<34} {r[idx]:8.2f} uA")
    print(f"   {'TOTAL @3V3':<34} {tot:8.2f} uA   -> {mw:.2f} mW at 12 V ({mw/12:.3f} mA)")
    for chem, frac in (("LiFePO4 80% usable",0.80), ("SLA 50% usable",0.50)):
        print(f"      {chem:<22} {WH*frac/(mw/1000)/24:7.0f} days")

print("\n-- HEATER (140 ohm, 1.029 W at 12 V = 85.7 mA) --")
base = batt_mw(sum(r[1] for r in ITEMS))
for duty in (1.0, 0.12, 0.04, 0.0):
    mw = base + duty*1029.0
    print(f"   duty {duty*100:5.1f}%  {mw:8.1f} mW  ->  LiFePO4 {WH*0.8/(mw/1000)/24:6.1f} d   SLA {WH*0.5/(mw/1000)/24:6.1f} d")
