#!/usr/bin/env python3
"""Host mirror of the firmware's psychrometry and the wet->dry O2 conversion.

One implementation, imported by every tool that needs it. It exists because
the alternative was a copy of the Magnus coefficients in a plotting script,
and a copy of a physical constant is a copy that will one day disagree with
the firmware it is supposed to describe - which is the failure this repo's
tools already guard against for the register map (o2p_poll.check_against_source)
and the flash map (check_flash_map.py).

The conversion:

    p_w   = RH/100 * p_sat(T_chamber)
    C_dry = C_wet * P / (P - p_w)

is the measurement-time half of O2-HUMIDITY-CORRECTION.md. It does NOT undo
the calibration-time half (that document's section 3b): the air point was
taken in moist air and attributed to dry air's 20.946 %, and the humidity at
which it was taken was never recorded - which is the register fe27d20 adds.
So a value corrected here still carries that constant bias, and on this bench
it is visible as roughly +1.4 %.

Every function is tri-state. An input that cannot be evaluated returns None
with a reason, never a plausible number.
"""

import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.pardir, "src")

# src/psychro.h O2P_MAGNUS_A / _B, Sonntag over water. Checked at import by
# check_against_source(); the constants are duplicated here only because
# Python cannot include a C header.
MAGNUS_A = 17.62
MAGNUS_B = 243.12
# Sonntag prefactor. MUST match O2P_MAGNUS_ES0_HPA in src/psychro.h - this
# module had 6.1094 hardcoded in p_sat_hpa() while the firmware used 6.112,
# and check_against_source() did not compare it, so the mismatch survived a
# passing check (Codex review 2026-09-07, finding 8).
MAGNUS_ES0_HPA = 6.112
# src/o2.h O2P_C_AIR - oxygen volume fraction of DRY air.
C_AIR_PCT = 20.946

# Above this fraction of total pressure the vapour term stops being a
# correction and starts being the measurement, and the Magnus fit is far
# outside its stated range. The firmware refuses here; so do we.
PW_FRACTION_MAX = 0.5


def p_sat_hpa(t_c):
    """Saturation vapour pressure over water, hPa. None if unevaluable."""
    if t_c is None or not math.isfinite(t_c) or t_c <= -MAGNUS_B:
        return None
    return MAGNUS_ES0_HPA * math.exp(MAGNUS_A * t_c / (MAGNUS_B + t_c))


def p_water_hpa(t_c, rh_pct):
    """Partial pressure of water vapour, hPa. None if unevaluable."""
    if rh_pct is None or not math.isfinite(rh_pct) or not 0.0 <= rh_pct <= 100.0:
        return None
    ps = p_sat_hpa(t_c)
    return None if ps is None else rh_pct / 100.0 * ps


def dry_from_wet(o2_wet_pct, t_c, rh_pct, p_total_hpa):
    """Wet-basis %vol -> dry-basis %vol. Returns (value, reason).

    value is None whenever the correction cannot be evaluated, and `reason`
    then says which input failed. A caller must render that as a gap, never as
    the uncorrected number and never as zero.
    """
    if o2_wet_pct is None or not math.isfinite(o2_wet_pct):
        return None, "no O2 reading"
    if p_total_hpa is None or not math.isfinite(p_total_hpa) or p_total_hpa <= 0:
        return None, "no total pressure"
    p_w = p_water_hpa(t_c, rh_pct)
    if p_w is None:
        return None, "no humidity or chamber temperature"
    if p_w >= PW_FRACTION_MAX * p_total_hpa:
        return None, ("vapour is %.0f %% of total pressure - past the "
                      "correction's validity" % (100.0 * p_w / p_total_hpa))
    return o2_wet_pct * p_total_hpa / (p_total_hpa - p_w), ""


def check_against_source():
    """Verify the constants here still match src/. Returns a list of problems."""
    bad = []

    def define(text, name):
        m = re.search(r"#define\s+%s\s+([-\w.]+)f?\b" % re.escape(name), text)
        return m.group(1).rstrip("fuU") if m else None

    for fname, checks in (("psychro.h", (("O2P_MAGNUS_A", MAGNUS_A),
                                         ("O2P_MAGNUS_B", MAGNUS_B),
                                         ("O2P_MAGNUS_ES0_HPA", MAGNUS_ES0_HPA))),
                          ("o2.h", (("O2P_C_AIR", C_AIR_PCT / 100.0),))):
        try:
            with open(os.path.join(SRC, fname)) as fh:
                text = fh.read()
        except OSError as exc:
            bad.append("cannot read src/%s: %s" % (fname, exc))
            continue
        for name, want in checks:
            got = define(text, name)
            if got is None:
                bad.append("%s not found in src/%s" % (name, fname))
            elif abs(float(got) - want) > 1e-9:
                bad.append("%s is %s in src/%s, this module assumes %g"
                           % (name, got, fname, want))
    return bad


if __name__ == "__main__":
    import sys
    problems = check_against_source()
    if problems:
        sys.exit("!! disagrees with src/:\n   " + "\n   ".join(problems))
    print("agrees with src/: Magnus %g/%g, dry air %g %%vol"
          % (MAGNUS_A, MAGNUS_B, C_AIR_PCT))
    for t, rh in ((23.4, 42.3), (25.0, 68.9), (60.0, 100.0), (75.0, 100.0)):
        v, why = dry_from_wet(20.946 * (1013.25 - p_water_hpa(t, rh)) / 1013.25,
                              t, rh, 1013.25)
        print("  %5.1f C %5.1f %%RH -> %s"
              % (t, rh, ("%.3f %%vol" % v) if v else "refused: " + why))
