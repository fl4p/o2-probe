#!/usr/bin/env python3
"""Measure the probe's thermal resistance and capacitance from a heater step.

This is the executable form of ../../PILE-THERMAL-TEST.md. One number, theta =
dT/P in K/W, sizes the battery and the panel for every node; that document
argues why, and this tool is how you actually get it - on the bench, or in a
pile, over nothing but the Modbus cable.

    python3 tools/o2p_thermal.py --port /dev/cu.usbserial-0001 --preflight
    python3 tools/o2p_thermal.py --port ... run.csv --duty 20 --half 300
    python3 tools/o2p_thermal.py --analyze run.csv --plot run.png

WHAT IT DOES. Duty is not commandable directly - the firmware's loop regulates
chamber RH, not duty. So the tool saturates that loop (RH_SETPOINT to its legal
floor, 50.00 %RH) and then pins the output with HEATER_MAX_DUTY, alternating it
between D and 0 for N cycles. A square wave rather than a single step because
an active pile drifts degrees over an hour and a linear drift cancels between
adjacent half-cycles; on a quiet bench one cycle would do, and three costs
nothing but time.

WHAT IT REFUSES TO DO. The interlocks in heater_ctl.h force duty to zero for
about a dozen distinct reasons, and the mask that says WHICH is not published
in the register map (see the note on HEATER_BLOCK below). A run that silently
returns zeros is therefore indistinguishable from a probe with no heater
fitted, so every precondition this tool CAN test, it tests before writing
anything - and it reports duty read back from 0x0005, never the duty it asked
for. `--preflight` runs exactly those checks and stops.

WHAT IT ALWAYS UNDOES. HEATER_MAX_DUTY goes back to 0 and RH_SETPOINT to
whatever it was, on every exit path including Ctrl-C, an abort, and an
unhandled exception. The commit magic (0x003E) is NEVER written: this
configuration is a measurement fixture and must not survive a power cycle. If
the restore itself fails the tool says so loudly and exits non-zero, because a
probe left with a live HEATER_MAX_DUTY is a probe that keeps heating.

THE TRAPS, all of them paid for on the bench on 2026-09-04 and written up in
PILE-THERMAL-TEST.md section 6:

  * Do NOT use T_TIP - T_CHAMBER as dT. U10 and U12 are 6.6 mm apart on the
    same copper and are one thermal node; the difference is structurally ~0 at
    any duty. dT here is always the CHANGE in T_TIP across a step.
  * Do NOT take theta from the initial slope. The bench slope method gave
    0.57 K/% against a true 1.01 K/%, out by nearly 2x. This fits the
    asymptote, and warns when a half-cycle was too short for the asymptote to
    mean anything.
  * Let it settle. Five time constants, verified flat, or the number is low.
"""

import argparse
import csv
import math
import os
import re
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from o2p_update import Bus, ModbusException, SerialLink  # noqa: E402  # type: ignore[import-not-found]
# The decoders are IMPORTED, not copied. o2p_poll.py already transcribes the
# register map and already checks itself against src/regmap.h at startup; a
# second transcription here would be a second thing to keep in step, and the
# one that rotted would be the one nobody was watching.
from o2p_poll import (  # noqa: E402  # type: ignore[import-not-found]
    CSV_COLUMNS as POLL_COLUMNS,
    check_against_source as poll_check_against_source,
    decode_diag, decode_primary,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.pardir, "src")

U16_INVALID = 0xFFFF
I16_INVALID = 0x8000

PRIMARY_BASE, PRIMARY_COUNT = 0x0000, 8
DIAG_BASE, DIAG_COUNT = 0x0010, 21

REG_RH_SETPOINT = 0x0033
REG_HEATER_MAX_DUTY = 0x0035
REG_HEATER_PWM_HZ = 0x0036

# regmap.c o2p_config_valid(). The floor is the reason a dry bench cannot run
# this test over Modbus alone: the loop only saturates while measured RH is
# ABOVE the setpoint, and the lowest legal setpoint is 50 %RH.
RH_SETPOINT_MIN_X100 = 5000
RH_SETPOINT_MAX_X100 = 9000

# main.c O2P_VIN_LOW_MV. Below this, O2P_F_VIN_LOW clears supply_ok and the
# O2P_HB_SUPPLY interlock pins duty at zero - the heater will not run at all.
VIN_LOW_MV = 9000

# hw_contract.h O2P_HW_HEATER_OHM: RH1||RH2 on the main board. A ring PCB
# PARALLELS these through J5, so this is the floor of the load, not the whole
# of it - pass --ohm if a ring is fitted or the network was respun.
HEATER_OHM = 140.0

FAULT_BITS = [
    "SETTLING", "I2C_FAIL_LMP", "I2C_FAIL_ADS", "I2C_FAIL_TMP",
    "I2C_FAIL_SHT", "AFE_CONFIG_MISMATCH", "VA_LOW", "VIN_LOW",
    "HEATER_RUNAWAY", "TEMP_OVER", "DEW_SUSPECT", "ADC_RANGE",
    "CAL_DEFAULT", "ADS_DRDY_STUCK", "ADS_CONFIG_LOST", "HEATER_DISABLED",
]

CSV_COLUMNS = [
    "utc", "t_s", "cycle", "phase", "cmd_duty_pct", "status", "detail",
    "heater_duty_pct", "t_tip_c", "t_chamber_c", "t_die_c", "rh_pct",
    "vin_mv", "va_mv", "faults", "faults_named",
    "o2_comp_pct", "o2_raw_ua", "uptime_s", "sample_seq",
]


# --------------------------------------------------------------------------
# Agreement with the firmware. Every constant above is a copy of a header, and
# a copy rots. Fail at startup rather than at the reading.

def _read(name):
    with open(os.path.join(SRC, name), "r") as fh:
        return fh.read()


def _strip_c_comments(text):
    """Remove /* */ and // comments.

    The regexes below are unanchored, so a STALE COMMENTED-OUT definition
    sitting above a changed live one would satisfy the check and report
    agreement that does not exist. Stripping first makes that particular
    fail-open impossible. String literals are left alone - none of the
    constants read here live inside one."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def check_against_source():
    """Verify this file's constants still match src/. Returns problems."""
    bad = []
    try:
        regmap_h = _read("regmap.h")
        regmap_c = _read("regmap.c")
        faults_h = _read("faults.h")
        main_c = _read("main.c")
        contract = _read("hw_contract.h")
    except OSError as exc:
        return ["cannot read src/: %s" % exc]
    regmap_h, regmap_c, faults_h, main_c, contract = (
        _strip_c_comments(t) for t in
        (regmap_h, regmap_c, faults_h, main_c, contract))

    def define(text, name, cast=lambda s: int(s.rstrip("uU"), 0)):
        m = re.search(r"#define\s+%s\s+([-\w.]+)" % re.escape(name), text)
        return cast(m.group(1)) if m else None

    def enum(text, name):
        m = re.search(r"%s\s*=\s*(0x[0-9A-Fa-f]+)u?" % re.escape(name), text)
        return int(m.group(1), 16) if m else None

    for name, want in (("O2P_REG_RH_SETPOINT", REG_RH_SETPOINT),
                       ("O2P_REG_HEATER_MAX_DUTY", REG_HEATER_MAX_DUTY),
                       ("O2P_REG_HEATER_PWM_HZ", REG_HEATER_PWM_HZ)):
        got = enum(regmap_h, name)
        if got is None:
            bad.append("%s not found in regmap.h" % name)
        elif got != want:
            bad.append("%s is 0x%04X in regmap.h, this tool assumes 0x%04X"
                       % (name, got, want))

    for name, want in (("O2P_REG_PRIMARY_BASE", PRIMARY_BASE),
                       ("O2P_REG_PRIMARY_COUNT", PRIMARY_COUNT),
                       ("O2P_REG_DIAG_BASE", DIAG_BASE),
                       ("O2P_REG_DIAG_COUNT", DIAG_COUNT)):
        got = define(regmap_h, name)
        if got is None:
            bad.append("%s not found in regmap.h" % name)
        elif got != want:
            bad.append("%s is %d in regmap.h, this tool assumes %d"
                       % (name, got, want))

    got = define(main_c, "O2P_VIN_LOW_MV")
    if got is None:
        bad.append("O2P_VIN_LOW_MV not found in main.c")
    elif got != VIN_LOW_MV:
        bad.append("O2P_VIN_LOW_MV is %d in main.c, this tool assumes %d"
                   % (got, VIN_LOW_MV))

    got = define(contract, "O2P_HW_HEATER_OHM")
    if got is None:
        bad.append("O2P_HW_HEATER_OHM not found in hw_contract.h")
    elif float(got) != HEATER_OHM:
        bad.append("O2P_HW_HEATER_OHM is %d in hw_contract.h, this tool "
                   "assumes %g - pass --ohm if the network was respun"
                   % (got, HEATER_OHM))

    # The setpoint window is the precondition the whole test turns on, so read
    # it out of the validator rather than trusting the comment above it.
    m = re.search(r"rh_setpoint_x100\s*>\s*(\d+)u?\s*\|\|\s*"
                  r"cfg->rh_setpoint_x100\s*<\s*(\d+)u?", regmap_c)
    if not m:
        bad.append("could not find the RH_SETPOINT window in "
                   "o2p_config_valid(); check regmap.c by hand")
    else:
        hi, lo = int(m.group(1)), int(m.group(2))
        if (lo, hi) != (RH_SETPOINT_MIN_X100, RH_SETPOINT_MAX_X100):
            bad.append("regmap.c accepts RH_SETPOINT in [%d, %d], this tool "
                       "assumes [%d, %d]"
                       % (lo, hi, RH_SETPOINT_MIN_X100, RH_SETPOINT_MAX_X100))

    for bit, name in enumerate(FAULT_BITS):
        m = re.search(r"O2P_F_%s\s*=\s*1u?\s*<<\s*(\d+)" % re.escape(name),
                      faults_h)
        if not m:
            bad.append("fault O2P_F_%s not found in faults.h" % name)
        elif int(m.group(1)) != bit:
            bad.append("fault %s is bit %s in faults.h, this tool assumes %d"
                       % (name, m.group(1), bit))
    return bad


# --------------------------------------------------------------------------
# Sampling. One transaction per block, decoded by o2p_poll's decoders so the
# thermal log and the Modbus log cannot disagree about what a register means.

def fault_names(word):
    return [n for i, n in enumerate(FAULT_BITS) if word & (1 << i)]


def sample(bus):
    row = decode_primary(bus.read(PRIMARY_BASE, PRIMARY_COUNT))
    row.update(decode_diag(bus.read(DIAG_BASE, DIAG_COUNT)))
    row["status"] = "ok"
    row["detail"] = ""
    return row


def sample_retry(bus, retries):
    last = None
    for attempt in range(retries + 1):
        try:
            return sample(bus)
        except ModbusException as exc:
            last = "modbus exception %d (%s)" % (exc.code, exc)
        except (IOError, OSError) as exc:
            last = "%s: %s" % (type(exc).__name__, exc)
        if attempt < retries:
            time.sleep(0.2)
    return {"status": "failed", "detail": last}


# --------------------------------------------------------------------------
# Preconditions.
#
# Guard discipline: an input this cannot evaluate is a REFUSAL, never an
# assumed pass. Every message names the remedy, because the interlock mask
# that would otherwise explain the zero duty is not published.

def rh_after_heating(rh_pct, t_c, dt_k):
    """Chamber RH after a dT rise at constant absolute humidity.

    d(ln RH)/dT = -L / (Rv * T^2), the same Clausius-Clapeyron relation
    PILE-THERMAL-TEST.md section 2 inverts to get its 3 K design point - this
    is that arithmetic run forwards. About -6 % per kelvin near room
    temperature, which is why a 20 K excursion does not just overheat the cell,
    it collapses the very measurement the loop is regulating.
    """
    L, RV = 2.45e6, 461.5          # J/kg, J/(kg K)
    t_k = t_c + 273.15
    return rh_pct * math.exp(-(L / (RV * t_k * t_k)) * dt_k)


def predict_step(duty_pct, vin_mv, ohm, theta):
    """(power W, expected dT K) for a duty step. theta is a GUESS, see below."""
    v = vin_mv / 1000.0
    power = (duty_pct / 100.0) * v * v / ohm
    return power, power * theta


class Refusal(Exception):
    """A precondition that makes the measurement meaningless. Never proceed."""


class Abort(Exception):
    """A running measurement that must stop NOW - too hot, rail gone, or an
    interlock refusing. Distinct from Refusal because the samples taken up to
    this point are real data and still get fitted; only the rest is lost."""


def preflight(bus, want_duty_pct, retries, ohm=HEATER_OHM,
              theta_guess=98.0, tip_max=55.0, quiet=False):
    """Return (snapshot, list of blocking problems, list of warnings)."""
    snap = sample_retry(bus, retries)
    if snap["status"] != "ok":
        raise Refusal("cannot read the probe: %s" % snap["detail"])

    try:
        cfg = bus.read(REG_RH_SETPOINT, 1)[0]
    except (ModbusException, IOError, OSError) as exc:
        raise Refusal("cannot read RH_SETPOINT (0x%04X): %s"
                      % (REG_RH_SETPOINT, exc))

    blocking, warn = [], []
    named = snap["faults_named"].split("|") if snap["faults_named"] else []

    # 1. The supply interlock. main.c gates supply_ok on VA_LOW|VIN_LOW and
    #    heater_ctl.h turns that into O2P_HB_SUPPLY, which forces duty to zero.
    if "VIN_LOW" in named or "VA_LOW" in named:
        blocking.append(
            "FAULTS carries %s, so supply_ok is false and the O2P_HB_SUPPLY "
            "interlock pins duty at 0. VIN reads %s mV against the %d mV "
            "O2P_VIN_LOW_MV threshold (main.c). Raise the input rail, or "
            "measure it with a meter first - P = duty*VIN^2/R, so a wrong VIN "
            "scales theta by its square."
            % ("|".join(n for n in named if n in ("VIN_LOW", "VA_LOW")),
               snap["vin_mv"], VIN_LOW_MV))
    elif snap["vin_mv"] < VIN_LOW_MV * 1.05:
        warn.append("VIN is %d mV, only %d mV above the %d mV interlock - a "
                    "sag under heater load will abort the run mid-cycle"
                    % (snap["vin_mv"], snap["vin_mv"] - VIN_LOW_MV, VIN_LOW_MV))

    # 2. The loop must SATURATE, or HEATER_MAX_DUTY pins nothing. It saturates
    #    only while measured RH exceeds the setpoint, and the setpoint cannot
    #    legally go below 50 %RH (regmap.c o2p_config_valid).
    rh = snap["rh_pct"]
    if rh is None:
        blocking.append(
            "RH_CHAMBER reads its invalid sentinel, so the loop has no fresh "
            "humidity and the O2P_HB_NO_RH interlock forces duty to 0. Check "
            "the SHT45 (I2C_FAIL_SHT in FAULTS).")
    elif rh * 100.0 <= RH_SETPOINT_MIN_X100:
        blocking.append(
            "chamber RH is %.2f %%, at or below the %.0f %% floor on "
            "RH_SETPOINT (regmap.c o2p_config_valid). The loop is positive-"
            "acting - it asks for duty only while measured RH is ABOVE the "
            "setpoint - so at this humidity NO legal setpoint saturates it and "
            "the heater cannot be commanded over Modbus at all. Remedies: put "
            "the tip in a closed box with a damp sponge (not touching) until "
            "RH > 60 %%, which is also closer to the medium the probe lives "
            "in; or drive the setpoint below the floor over SWD, which is what "
            "the 2026-09-04 bench run did." % (rh, RH_SETPOINT_MIN_X100 / 100.0))
    elif rh * 100.0 < RH_SETPOINT_MIN_X100 + 500:
        warn.append("chamber RH is %.2f %%, only %.2f %% above the setpoint "
                    "floor. The loop saturates now, but heating LOWERS RH - if "
                    "it falls through %.0f %% mid-cycle the loop comes out of "
                    "saturation and the duty you read back will not be the duty "
                    "you asked for. Watch heater_duty_pct in the log."
                    % (rh, rh - RH_SETPOINT_MIN_X100 / 100.0,
                       RH_SETPOINT_MIN_X100 / 100.0))

    # 3. Is the duty SANE for the coupling we expect?
    #
    # PILE-THERMAL-TEST.md section 4 says "start at 2000 (20.00 %)", and that
    # is right for a pile, where theta is expected near 10-20 K/W and 20 %
    # buys 2-4 K. On a still-air bench at ~98 K/W the SAME command is a 20 K
    # excursion: it takes the cell past its 60 C rating and, worse, drops
    # chamber RH by a third - straight through the setpoint, out of
    # saturation, and the applied duty stops being the duty you asked for.
    # The measurement destroys its own precondition. Predict it and say so.
    pred_line = None
    if snap["t_tip_c"] is not None and snap["vin_mv"]:
        power, dt = predict_step(want_duty_pct, snap["vin_mv"], ohm, theta_guess)
        tip_end = snap["t_tip_c"] + dt
        # What the chamber has to start at for this step to stay saturated,
        # with 5 %RH of margin left at the top of the step. Heating LOWERS RH,
        # so the constraint is on the END of the ON half, not the start.
        margin = RH_SETPOINT_MIN_X100 / 100.0 + 5.0
        t_ch = snap["t_chamber_c"] if snap["t_chamber_c"] is not None else 25.0
        need_rh = margin / (rh_after_heating(1.0, t_ch, dt) or 1.0)
        pred_line = ("  predicted     %.2f %% -> %.1f mW -> +%.1f K at the "
                     "assumed %.0f K/W (tip %.1f C); needs the chamber to "
                     "start at %.0f %%RH"
                     % (want_duty_pct, power * 1000.0, dt, theta_guess,
                        tip_end, need_rh))
        if dt < 1.5:
            warn.append("--duty %g is predicted to raise the tip only %.2f K. "
                        "That is measurable - the TMP117 resolves 0.0078 K - "
                        "but it is thin against ambient drift, and theta is "
                        "dT/P, so the fractional error in dT is the fractional "
                        "error in theta. Consider --duty %.1f."
                        % (want_duty_pct, dt,
                           _duty_for(3.0, snap["vin_mv"], ohm, theta_guess)))
        if tip_end >= tip_max:
            blocking.append(
                "--duty %g would put the tip at about %.1f C (%.1f K rise at "
                "the assumed %.0f K/W), at or past the --tip-max %.1f C. Use "
                "--duty %.1f for a 3 K rise, or --theta-guess if you already "
                "know this installation couples better."
                % (want_duty_pct, tip_end, dt, theta_guess, tip_max,
                   _duty_for(3.0, snap["vin_mv"], ohm, theta_guess)))
        elif rh is not None:
            rh_end = rh_after_heating(rh, snap["t_chamber_c"] or 25.0, dt)
            if rh_end <= RH_SETPOINT_MIN_X100 / 100.0:
                blocking.append(
                    "--duty %g is predicted to raise the tip %.1f K, which "
                    "takes chamber RH from %.1f %% to about %.1f %% - below "
                    "the %.0f %% setpoint. The loop would leave saturation "
                    "mid-step and stop applying the duty you asked for, so "
                    "the run would measure nothing. Use --duty %.1f (about "
                    "3 K), or raise the chamber humidity further."
                    % (want_duty_pct, dt, rh, rh_end,
                       RH_SETPOINT_MIN_X100 / 100.0,
                       _duty_for(3.0, snap["vin_mv"], ohm, theta_guess)))
            elif rh_end <= RH_SETPOINT_MIN_X100 / 100.0 + 3.0:
                warn.append("heating %.1f K is predicted to take RH from "
                            "%.1f %% to %.1f %%, only %.1f %% above the "
                            "setpoint. Watch heater_duty_pct for the loop "
                            "coming out of saturation."
                            % (dt, rh, rh_end,
                               rh_end - RH_SETPOINT_MIN_X100 / 100.0))

    # 4. Things that are merely suspicious.
    if "HEATER_RUNAWAY" in named:
        blocking.append(
            "FAULTS carries HEATER_RUNAWAY. That latch survives until reset "
            "and holds duty at 0. Power-cycle and find out why before adding "
            "more heat.")
    for f in ("I2C_FAIL_TMP",):
        if f in named:
            blocking.append(
                "FAULTS carries %s - T_TIP is the measurement, and without a "
                "TMP117 there is nothing to fit." % f)
    if snap["t_tip_c"] is None:
        blocking.append("T_TIP reads its invalid sentinel; there is nothing "
                        "to measure.")
    elif snap["t_tip_c"] >= tip_max:
        blocking.append(
            "T_TIP is already %.2f C, at or above the --tip-max %.2f C. The "
            "in-run abort only fires AFTER a duty has been written; refusing "
            "here is what stops a hot probe being commanded hotter."
            % (snap["t_tip_c"], tip_max))
    if snap["t_chamber_c"] is None:
        blocking.append(
            "T_CHAMBER reads its invalid sentinel. The firmware's "
            "O2P_HB_NO_CHAMBER interlock will hold duty at 0, so the run "
            "would command heat and measure none.")
    if cfg < RH_SETPOINT_MIN_X100 or cfg > RH_SETPOINT_MAX_X100:
        warn.append("RH_SETPOINT reads %d (%.2f %%), outside the window the "
                    "validator accepts - this probe was configured by "
                    "something other than Modbus" % (cfg, cfg / 100.0))
    if want_duty_pct <= 0.0 or want_duty_pct > 100.0:
        blocking.append("--duty %g is not a duty" % want_duty_pct)

    if not quiet:
        print("preflight")
        print("  T_TIP         %s C" % _f(snap["t_tip_c"]))
        print("  T_CHAMBER     %s C   (one thermal node with the tip - NOT a "
              "dT reference)" % _f(snap["t_chamber_c"]))
        print("  T_DIE         %s C   (across the barrier; the runaway "
              "reference)" % _f(snap["t_die_c"]))
        print("  RH            %s %%" % _f(snap["rh_pct"]))
        print("  VIN           %d mV  (interlock at %d mV)"
              % (snap["vin_mv"], VIN_LOW_MV))
        print("  VA            %d mV" % snap["va_mv"])
        print("  duty now      %.2f %%" % snap["heater_duty_pct"])
        print("  RH_SETPOINT   %d (%.2f %%)" % (cfg, cfg / 100.0))
        print("  FAULTS        0x%04X  %s"
              % (snap["faults"], snap["faults_named"] or "none"))
        if pred_line:
            print(pred_line)
    return snap, cfg, blocking, warn


def _duty_for(dt_k, vin_mv, ohm, theta):
    """The duty that would give a dT of dt_k at the assumed theta."""
    v = vin_mv / 1000.0
    return 100.0 * (dt_k / theta) * ohm / (v * v)


def _f(v, places=2):
    return "invalid" if v is None else ("%%.%df" % places) % v


# --------------------------------------------------------------------------
# The run.

class Fixture:
    """Owns every register this tool writes, and puts them all back.

    Separate from the run loop on purpose: the restore has to happen on paths
    the run loop never reaches - an exception, a signal, an abort - and a probe
    left with a live HEATER_MAX_DUTY keeps heating with nobody watching. The
    firmware has no deadman on this; nothing takes the heat away on its own
    until the 80 C firmware clamp or the 85 C TMP117 alert, both far above the
    cell's 60 C rating.

    Three rules, each of which was a defect found by review before it was one:

      * `armed` is set BEFORE the first write, not after. A write whose reply
        was lost may still have been APPLIED, so "we never confirmed it" is
        not the same as "it did not happen" - and only the pessimistic reading
        is safe.
      * `restore()` blocks SIGINT and SIGTERM while it runs. A second Ctrl-C
        landing inside the restore used to kill the process mid-way, between
        zeroing the duty and putting the setpoint back - or before either.
      * `restore()` retries against a wall-clock deadline rather than the
        run's ordinary retry count. Giving up after 3 attempts is right for a
        reading and wrong for the write that takes the heat away.
    """

    RESTORE_DEADLINE_S = 30.0

    def __init__(self, bus, retries):
        self.bus = bus
        self.retries = retries
        self.orig_setpoint = None
        self.armed = False
        self.hot = False          # a nonzero duty has been commanded at least once

    def _write(self, addr, value, deadline=None):
        last = None
        attempt = 0
        while True:
            try:
                self.bus.write(addr, [value])
                return
            except (ModbusException, IOError, OSError) as exc:
                last = exc
            attempt += 1
            if deadline is None:
                if attempt > self.retries:
                    break
            elif time.monotonic() >= deadline:
                break
            time.sleep(0.2)
        raise IOError("write of 0x%04X = %d failed after %d attempts: %s"
                      % (addr, value, attempt, last))

    def arm(self, orig_setpoint):
        """Saturate the loop. Duty stays 0 until set_duty() is called."""
        self.orig_setpoint = orig_setpoint
        # Pessimistic BEFORE the first write. See the class docstring.
        self.armed = True
        self._write(REG_HEATER_MAX_DUTY, 0)
        self._write(REG_RH_SETPOINT, RH_SETPOINT_MIN_X100)
        back = self.bus.read(REG_RH_SETPOINT, 1)[0]
        if back != RH_SETPOINT_MIN_X100:
            raise Refusal("RH_SETPOINT read back as %d after writing %d - the "
                          "probe did not take the write"
                          % (back, RH_SETPOINT_MIN_X100))

    def set_duty(self, duty_pct):
        if duty_pct > 0.0:
            self.hot = True
        self._write(REG_HEATER_MAX_DUTY, int(round(duty_pct * 100.0)))

    def restore(self):
        """Always called. Returns a list of things that did NOT go back.

        Never raises: a restore that fails has to be REPORTED, and an
        exception here would replace whatever the caller was already handling.
        """
        if not self.armed:
            return []
        blocked = False
        try:
            signal.pthread_sigmask(signal.SIG_BLOCK,
                                   {signal.SIGINT, signal.SIGTERM})
            blocked = True
        except (AttributeError, OSError, ValueError):
            pass          # not fatal; the retries below still help
        failed = []
        try:
            deadline = time.monotonic() + self.RESTORE_DEADLINE_S
            # Duty first, always. If only one of the two writes gets through,
            # the one that matters is the one that stops the heat.
            for addr, value, what in (
                    (REG_HEATER_MAX_DUTY, 0, "HEATER_MAX_DUTY -> 0"),
                    (REG_RH_SETPOINT, self.orig_setpoint,
                     "RH_SETPOINT -> %s" % self.orig_setpoint)):
                if value is None:
                    continue
                try:
                    self._write(addr, value, deadline=deadline)
                except (IOError, OSError) as exc:
                    failed.append("%s: %s" % (what, exc))
                deadline = max(deadline, time.monotonic() + 5.0)
            # Prove it, do not assume it. The write returning is the bridge
            # saying the frame went out; the readback is the probe saying it
            # took effect.
            if not failed:
                try:
                    back = self.bus.read(REG_HEATER_MAX_DUTY, 1)[0]
                    if back != 0:
                        failed.append("HEATER_MAX_DUTY reads back %d after "
                                      "being set to 0" % back)
                except (ModbusException, IOError, OSError) as exc:
                    failed.append("could not read HEATER_MAX_DUTY back: %s"
                                  % exc)
            # The commit magic is deliberately never written: this
            # configuration is a fixture, and a fixture that survives a power
            # cycle is a bug.
            if not failed:
                self.armed = False
        finally:
            if blocked:
                try:
                    signal.pthread_sigmask(signal.SIG_UNBLOCK,
                                           {signal.SIGINT, signal.SIGTERM})
                except (OSError, ValueError):
                    pass
        return failed


def _report_restore(fixture, failed):
    if failed:
        print("\n!! THE PROBE WAS NOT RESTORED. IT MAY STILL BE HEATING.")
        for f in failed:
            print("   - %s" % f)
        print("   HEATER_MAX_DUTY may still be non-zero and RH_SETPOINT at "
              "%d. Power-cycle the probe, or re-run with --preflight to see "
              "what it is actually doing." % RH_SETPOINT_MIN_X100)
    elif fixture.armed is False and fixture.orig_setpoint is not None:
        print("\nrestored: HEATER_MAX_DUTY = 0 (read back), RH_SETPOINT = %d "
              "(not committed to flash)" % fixture.orig_setpoint)


def run(args, bus, writer, poll_writer=None):
    snap, orig_setpoint, blocking, warn = preflight(
        bus, args.duty, args.retries, args.ohm, args.theta_guess,
        args.tip_max)
    for w in warn:
        print("  ** %s" % w)
    if blocking:
        raise Refusal("the heater cannot run:\n   - "
                      + "\n   - ".join(blocking))
    if args.preflight:
        print("\npreflight only - nothing was written.")
        return 0

    print("\nsquare wave: %d cycles of %.0f s at %.2f %% / %.0f s at 0 %%, "
          "sampling every %.0f s" % (args.cycles, args.half, args.duty,
                                     args.half, args.interval))
    print("total %.0f s (%.1f min).  Ctrl-C restores the registers and stops."
          % (2 * args.cycles * args.half, 2 * args.cycles * args.half / 60.0))

    fixture = Fixture(bus, args.retries)
    rows = []
    t_start = time.time()
    aborted = None
    unexpected = None
    consec_fail = 0

    def on_signal(signum, frame):
        raise KeyboardInterrupt("signal %d" % signum)

    old_term = signal.signal(signal.SIGTERM, on_signal)
    try:
        fixture.arm(orig_setpoint)
        for cycle in range(1, args.cycles + 1):
            for phase, duty in (("on", args.duty), ("off", 0.0)):
                fixture.set_duty(duty)
                t_phase = time.time()
                # A phase that has already been commanded is sampled to its
                # end even if the very first read shows nothing happening; the
                # abort below is what stops a run that is going nowhere.
                while time.time() - t_phase < args.half:
                    row = sample_retry(bus, args.retries)
                    now = time.time()
                    row.update({
                        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime(now)),
                        "t_s": round(now - t_start, 1),
                        "cycle": cycle,
                        "phase": phase,
                        "cmd_duty_pct": duty,
                    })
                    # A single failed poll is a gap in the log. A RUN of them
                    # while the heater is on is a probe we can no longer see
                    # or command, and continuing would be commanding heat
                    # blind - so it aborts into the restore instead.
                    if row["status"] == "ok":
                        consec_fail = 0
                    else:
                        consec_fail += 1
                        if fixture.hot and consec_fail >= args.max_fail:
                            raise Abort(
                                "%d consecutive failed polls with the heater "
                                "commanded on - the probe is unreachable and "
                                "must not be left heating blind"
                                % consec_fail)
                    rows.append(row)
                    if writer:
                        writer.writerow({c: row.get(c, "") for c in CSV_COLUMNS})
                    if poll_writer:
                        # Same row, the ordinary Modbus-log schema. The 15 s
                        # logger has to give up the port for the run; without
                        # this the continuous record would have an hour-long
                        # hole exactly where the interesting thing happened.
                        poll_writer.writerow({c: row.get(c, "")
                                              for c in POLL_COLUMNS})
                    _show_row(row)
                    why = _check_abort(row, phase, duty, t_phase, args)
                    if why:
                        raise Abort(why)
                    left = args.interval - (time.time() - now)
                    if left > 0:
                        time.sleep(left)
    except Abort as exc:
        aborted = str(exc)
        print("\n!! ABORTED: %s" % aborted)
    except KeyboardInterrupt as exc:
        aborted = "interrupted (%s)" % exc
        print("\n!! %s" % aborted)
    except BaseException as exc:            # noqa: BLE001 - deliberate
        # Anything at all - a Refusal from arm(), a bug in this file, a
        # SystemExit - must still take the heat away before it propagates.
        # Re-raised below, after the restore has been done and reported.
        aborted = "unexpected %s: %s" % (type(exc).__name__, exc)
        unexpected = exc
    finally:
        # Restore FIRST, then hand the signal disposition back. Doing it the
        # other way round left a window in which a second SIGTERM killed the
        # process during the write that takes the heat away.
        restore_failed = fixture.restore()
        signal.signal(signal.SIGTERM, old_term)
        _report_restore(fixture, restore_failed)

    if unexpected is not None:
        raise unexpected
    if restore_failed:
        return 2

    analyse(rows, args)
    if aborted:
        # The fit above is of whatever was collected before the stop. It is
        # reported because partial data beats no data, but the exit status has
        # to say the run did not finish, or a wrapper will bank the number.
        print("\n!! this run did not complete: %s" % aborted)
        return 1
    return 0


def _show_row(row):
    if row["status"] != "ok":
        print("  %6s  !! %s" % (row.get("t_s", "?"), row["detail"]))
        return
    print("  %6.0f s  %-3s cmd %5.2f %%  applied %5.2f %%  tip %s C  "
          "chamber %s C  die %s C  RH %s %%  VIN %d mV  %s"
          % (row["t_s"], row["phase"], row["cmd_duty_pct"],
             row["heater_duty_pct"], _f(row["t_tip_c"]),
             _f(row["t_chamber_c"]), _f(row["t_die_c"], 1),
             _f(row["rh_pct"], 1), row["vin_mv"],
             row["faults_named"] or "-"))


def _check_abort(row, phase, cmd_duty, t_phase, args):
    """Reasons to stop early. None means carry on."""
    if row["status"] != "ok":
        return None                      # a single failed poll is a gap, not an abort
    tip = row["t_tip_c"]
    if tip is not None and tip >= args.tip_max:
        return ("T_TIP reached %.2f C, at or above the --tip-max %.2f C limit"
                % (tip, args.tip_max))
    named = row["faults_named"].split("|") if row["faults_named"] else []
    if "HEATER_RUNAWAY" in named:
        return "FAULTS raised HEATER_RUNAWAY - the firmware saw uncommanded heat"
    if "VIN_LOW" in named or "VA_LOW" in named:
        return ("the rail fell out of tolerance under load (%s); every reading "
                "after this point is at an unknown power"
                % row["faults_named"])
    # The interlock that matters most, and the one the register map cannot
    # explain: commanded duty, nothing applied. Give the loop a few samples to
    # act before calling it.
    if (cmd_duty > 0.0 and row["heater_duty_pct"] == 0.0
            and time.time() - t_phase > max(3 * args.interval, 20.0)):
        return ("commanded %.2f %% for %.0f s and 0x0005 still reads 0.00 %% - "
                "an interlock is refusing. The mask that says which is NOT "
                "published (heater_ctl.h claims a HEATER_BLOCK register, "
                "main.c computes it, the register map has no such address). "
                "Most likely, in order: the build is O2P_HEATER_ENABLE=0 "
                "(HB_NOT_COMPILED - reflash -e o2probe_heater_enabled); the "
                "TMP117 alert is not armed (HB_SAFETY); or RH fell below the "
                "setpoint so the loop came out of saturation - check rh_pct in "
                "the log against %.2f %%."
                % (cmd_duty, time.time() - t_phase,
                   RH_SETPOINT_MIN_X100 / 100.0))
    return None


# --------------------------------------------------------------------------
# The fit.
#
# T(t) = T_inf + (T_0 - T_inf) * exp(-t/tau), fitted per half-cycle. tau enters
# nonlinearly and everything else linearly, so scan tau and solve the rest
# exactly at each step - no optimiser, no scipy, and no local minimum to land
# in. Deliberately not scipy: this has to run on a bench laptop.

def _fit_exp(t, y):
    """Return (T_inf, T_0, tau, rms) or None if the segment cannot support a fit."""
    n = len(t)
    if n < 5:
        return None
    span = t[-1] - t[0]
    if span <= 0:
        return None
    t = [x - t[0] for x in t]

    def sse_for(tau):
        # least squares on [1, exp(-t/tau)] -> T_inf and (T_0 - T_inf)
        b = [math.exp(-x / tau) for x in t]
        s11, s1b, sbb = float(n), sum(b), sum(v * v for v in b)
        s1y, sby = sum(y), sum(bi * yi for bi, yi in zip(b, y))
        det = s11 * sbb - s1b * s1b
        if abs(det) < 1e-12:
            return None
        inf = (s1y * sbb - s1b * sby) / det
        amp = (s11 * sby - s1b * s1y) / det
        resid = [yi - (inf + amp * bi) for bi, yi in zip(b, y)]
        return sum(r * r for r in resid), inf, amp

    def scan(lo, hi, steps):
        out = None
        for k in range(steps):
            tau = lo * (hi / lo) ** (k / (steps - 1.0))
            got = sse_for(tau)
            if got and (out is None or got[0] < out[0]):
                out = (got[0], got[1], got[2], tau)
        return out

    # Scan wide: a well-coupled probe settles fast, a still-air one slowly, and
    # the point of the measurement is that we do not know which.
    lo, hi = max(span / 200.0, 0.5), span * 5.0
    best = scan(lo, hi, 400)
    if best is None:
        return None
    # A minimum sitting ON a boundary is not a minimum, it is the edge of the
    # search. Push the boundary out and look again - and if it still will not
    # come inside, say so, because the fit is then unidentifiable: a segment
    # far shorter than tau cannot distinguish "slow exponential" from
    # "straight line", and a straight line fitted at the boundary returns a
    # confident asymptote that is simply wrong.
    for _ in range(5):
        if best[3] < hi * 0.99:
            break
        hi *= 4.0
        got = scan(lo, hi, 400)
        if got and got[0] < best[0]:
            best = got
    edge = best[3] >= hi * 0.99 or best[3] <= lo * 1.01
    # Refine around the winner.
    tau0 = best[3]
    got = scan(tau0 / 1.2, tau0 * 1.2, 200)
    if got and got[0] < best[0]:
        best = got
    sse, inf, amp, tau = best
    return inf, inf + amp, tau, math.sqrt(sse / n), edge


def _segments(rows):
    """Group ok-rows into consecutive (cycle, phase) runs."""
    out, cur, key = [], [], None
    for r in rows:
        if r.get("status") != "ok":
            continue
        k = (r["cycle"], r["phase"])
        if k != key:
            if cur:
                out.append((key, cur))
            cur, key = [], k
        cur.append(r)
    if cur:
        out.append((key, cur))
    return out


def _steady_part(seg):
    """The segment minus its command-latency head.

    The firmware's control loop runs at 1 Hz and this samples every few
    seconds, so the FIRST sample after a duty change routinely still reports
    the previous duty - the command has been accepted but not yet acted on.
    That is command latency, not a duty that varied, and counting it as
    variation flagged DUTY_VARIES on every single ON half of a live run,
    which would have excluded all of them and returned no theta at all.

    Only a leading run is skipped, and only while the duty disagrees with the
    rest of the segment. A duty that changes LATER - the loop falling out of
    saturation, which is the failure this check exists to catch - is still
    seen.
    """
    duties = [r.get("heater_duty_pct") for r in seg]
    known = [d for d in duties if d is not None]
    if len(known) < 3:
        return seg
    settled = known[-1]
    i = 0
    while i < len(seg) - 2 and duties[i] is not None \
            and abs(duties[i] - settled) > 1e-9:
        i += 1
        if i >= 2:            # more than a couple of samples is not latency
            return seg
    return seg[i:] if i else seg


def _quality(seg, fit, args):
    """Reasons this half-cycle's asymptote cannot be believed.

    A segment that fails here is EXCLUDED from theta rather than averaged into
    it. Measured the hard way on bench-logs/heater-2026-09-04.csv: its trailing
    "off" half runs straight through the board being powered down, and taking
    that fit at face value moves theta from 98 to 107 K/W - a 9 % error that
    looks exactly like a real result.
    """
    flags = []
    if args.vin_mv:
        # The logged rail has been overridden, so checking ITS stability proves
        # nothing - it is the channel we just declared untrustworthy. The
        # override is only ever right for a rail measured externally and known
        # to be steady; that judgement is the operator's and is recorded in the
        # header of the analysis output.
        vins = [float(args.vin_mv)]
    else:
        vins = [r["vin_mv"] for r in seg
                if r.get("vin_mv") is not None and math.isfinite(r["vin_mv"])]
    if not vins:
        # No rail reading at all. P is duty*VIN^2, so without VIN there is no
        # power and therefore no theta - and an unevaluable input must never
        # come out as a pass.
        flags.append("NO_VIN")
    else:
        spread = (max(vins) - min(vins)) / max(_mean(vins), 1.0)
        if spread > args.vin_tol:
            flags.append("UNSTABLE_VIN(%.0f%%)" % (100.0 * spread))
    if fit and not all(math.isfinite(fit[k])
                       for k in ("inf", "asym", "t0", "tau", "rms")):
        flags.append("NON_FINITE")
    if fit and fit["tau"] <= 0.0:
        flags.append("BAD_TAU")
    if fit and fit.get("edge"):
        # tau pinned to the edge of the search: the segment cannot distinguish
        # a slow exponential from a straight line, and the asymptote it
        # reports is an artefact of where the scan stopped.
        flags.append("TAU_UNIDENTIFIABLE")
    if fit and math.isfinite(fit.get("duty_spread", float("nan"))) \
            and fit["duty"] > 0.0 \
            and fit["duty_spread"] > max(0.05 * fit["duty"], 0.02):
        # A duty that MOVED is not a step. The loop coming out of saturation
        # looks exactly like this, and the fit would report it as one clean
        # fixed-power response.
        flags.append("DUTY_VARIES(%.2f%%)" % fit["duty_spread"])
    faulted = set()
    for r in seg:
        for n in (r.get("faults_named") or "").split("|"):
            if n in ("VIN_LOW", "VA_LOW", "HEATER_RUNAWAY", "I2C_FAIL_TMP"):
                faulted.add(n)
    if faulted:
        flags.append("FAULTED(%s)" % ",".join(sorted(faulted)))
    if fit and fit["rms"] > args.rms_max:
        flags.append("NOISY(rms %.2f K)" % fit["rms"])
    if fit and fit["tau"] > 0.0:
        ratio = fit["span"] / fit["tau"]
        # Extrapolating an asymptote is legitimate - it is the whole advantage
        # over the slope method, and the real 2026-09-04 step at 3.2 tau is
        # perfectly usable. But there is a floor. Below one time constant the
        # data is barely distinguishable from a straight line, the amplitude
        # and tau trade off almost freely, and the fit returns a confident
        # asymptote that is mostly an artefact: a synthetic 0.1-tau segment
        # with a true 98 K/W came back as 105 K/W with a 1 mK residual.
        if ratio < 1.0:
            flags.append("TOO_SHORT(%.2f tau)" % ratio)
        elif ratio < 5.0:
            flags.append("SHORT(%.1f tau)" % ratio)
    return flags


# Flags that make a segment unusable, as opposed to merely worth saying aloud.
# SHORT is not among them: the exponential fit EXTRAPOLATES the asymptote, so a
# short step is recoverable in a way the slope method never was - it just wants
# saying, loudly, because it is the trap the bench fell into.
FATAL_FLAGS = ("UNSTABLE_VIN", "FAULTED", "NOISY", "NO_VIN", "NON_FINITE",
               "BAD_TAU", "TAU_UNIDENTIFIABLE", "DUTY_VARIES", "TOO_SHORT")


def _seg_power_w(seg, ohm, vin_override_mv=None):
    """Mean electrical power over a segment, averaged the right way round.

    P is duty x VIN^2, and the mean of a product is not the product of the
    means. With a duty or a rail that moved, mean(duty)*mean(VIN)^2 is simply a
    different number - so average the per-sample power instead.
    """
    ps = []
    for r in seg:
        d = r.get("heater_duty_pct")
        v = vin_override_mv if vin_override_mv else r.get("vin_mv")
        if d is None or v is None:
            continue
        volts = v / 1000.0
        ps.append((d / 100.0) * volts * volts / ohm)
    return _mean(ps) if ps else float("nan")


def _fit_segment(seg, args):
    t = [r["t_s"] for r in seg if r.get("t_tip_c") is not None]
    y = [r["t_tip_c"] for r in seg if r.get("t_tip_c") is not None]
    fit = _fit_exp(t, y)
    if fit is None:
        return None
    inf, t0, tau, rms, edge = fit
    span = t[-1] - t[0]
    refit = False
    # A segment far longer than tau carries history that is not part of THIS
    # step, and a single exponential cannot describe both. Re-fit the last few
    # time constants - the part that is actually this step's tail.
    if rms > args.rms_max and tau > 0 and span > 6.0 * tau:
        cut = t[-1] - 6.0 * tau
        tt = [x for x in t if x >= cut]
        yy = [v for x, v in zip(t, y) if x >= cut]
        again = _fit_exp(tt, yy) if len(tt) >= 8 else None
        if again and again[3] < rms:
            inf, t0, tau, rms, edge = again
            span, t, y, refit = tt[-1] - tt[0], tt, yy, True
    # Prefer a MEASURED asymptote to an extrapolated one - but only once the
    # measurement has earned it. The tail mean is biased LOW by construction:
    # it averages the last fifth of the segment, which at 5 tau is still
    # climbing through 98-99 % of the step, and on synthetic data with a known
    # answer that cost 2.5 K/W. At 8 tau the residual is under 0.1 % and the
    # tail is the more robust of the two, because it does not depend on the
    # three-parameter fit having placed the asymptote correctly.
    n_tail = max(3, len(y) // 5)
    asym, asym_from = inf, "fit"
    if span >= 8.0 * tau and len(y) >= n_tail:
        asym, asym_from = _mean(y[-n_tail:]), "tail"
    steady = _steady_part(seg)
    duties = [r["heater_duty_pct"] for r in steady
              if r.get("heater_duty_pct") is not None]
    return {"inf": inf, "asym": asym, "asym_from": asym_from, "t0": t0,
            "tau": tau, "rms": rms, "span": span, "n": len(y), "refit": refit,
            "edge": edge,
            "duty": _mean(duties),
            "duty_spread": (max(duties) - min(duties)) if duties else float("nan"),
            "power_w": _seg_power_w(steady, args.ohm, args.vin_mv),
            "vin": _mean([r["vin_mv"] for r in seg])}


def analyse(rows, args):
    segs = _segments(rows)
    if not segs:
        print("\nno usable samples - nothing to fit.")
        return

    print("\n--- per half-cycle fit  T(t) = T_inf + (T_0 - T_inf) exp(-t/tau) ---")
    print("  cycle phase   T_0     T_inf   asympt      tau     rms   applied"
          "   VIN    span/tau  quality")
    fits = {}
    for (cycle, phase), seg in segs:
        f = _fit_segment(seg, args)
        if f is None:
            print("  %5d %-5s  -- too few samples to fit (%d) --"
                  % (cycle, phase, len(seg)))
            continue
        f["flags"] = _quality(seg, f, args)
        f["usable"] = not any(x.startswith(k) for x in f["flags"]
                              for k in FATAL_FLAGS)
        print("  %5d %-5s %7.3f %7.3f %7.3f%-5s %6.1f %7.4f %6.2f %% %5.0f mV"
              "  %6.1f    %s"
              % (cycle, phase, f["t0"], f["inf"], f["asym"],
                 "" if f["asym_from"] == "fit" else "(tail)",
                 f["tau"], f["rms"], f["duty"], f["vin"],
                 f["span"] / f["tau"] if f["tau"] else 0.0,
                 " ".join(f["flags"]) + ("  EXCLUDED" if not f["usable"]
                                         else "") if f["flags"] else "ok"))
        if f["refit"]:
            print("        (re-fitted on the last 6 tau; the full segment "
                  "carried history this step did not cause)")
        fits[(cycle, phase)] = f

    short = [k for k, v in fits.items()
             if v["usable"] and any(x.startswith("SHORT") for x in v["flags"])]
    if short:
        print("\n  ** %d half-cycle(s) ran for less than 5 tau. The asymptote "
              "there is EXTRAPOLATED, not observed. It is still the right "
              "estimator - the slope method got 0.57 K/%% against a true "
              "1.01 K/%% - but re-run with --half >= %.0f before quoting the "
              "number." % (len(short), 5.0 * max(fits[k]["tau"] for k in short)))

    # Each ON asymptote against the mean of its neighbouring OFF asymptotes.
    # That pairing is what cancels a linear drift; a pile moves degrees in an
    # hour and a single step cannot tell drift from response.
    ohm = args.ohm
    results, skipped = [], []
    for cycle, phase in sorted(fits):
        if phase != "on":
            continue
        on = fits[(cycle, "on")]
        if not on["usable"]:
            skipped.append("cycle %d: the ON half is %s"
                           % (cycle, " ".join(on["flags"])))
            continue
        neigh = [fits[k]["asym"] for k in ((cycle - 1, "off"), (cycle, "off"))
                 if k in fits and fits[k]["usable"]]
        if not neigh:
            skipped.append(
                "cycle %d: no usable OFF half either side, so there is no "
                "baseline to subtract. dT is a CHANGE in T_TIP - it can never "
                "come from T_TIP - T_CHAMBER, which is structurally ~0 on this "
                "board." % cycle)
            continue
        dt = on["asym"] - _mean(neigh)
        power = on["power_w"]
        # Every one of these was a way for a nonsense number to reach the
        # headline. An unevaluable input is a refusal, not a result.
        if not math.isfinite(power) or power <= 0.0:
            skipped.append("cycle %d: applied power is %s - commanded duty is "
                           "not applied duty, and an interlock refused"
                           % (cycle, "unevaluable" if not math.isfinite(power)
                              else "%.1f mW" % (power * 1000.0)))
            continue
        if not math.isfinite(dt):
            skipped.append("cycle %d: dT is unevaluable" % cycle)
            continue
        if dt <= 0.0:
            skipped.append(
                "cycle %d: the tip ENDED %.3f K cooler than its baseline while "
                "%.2f %% duty was applied. That is not a heater step - suspect "
                "the phase labelling, or ambient falling faster than the "
                "heater raised it." % (cycle, -dt, on["duty"]))
            continue
        theta = dt / power
        if not math.isfinite(theta) or theta <= 0.0:
            skipped.append("cycle %d: theta is unevaluable" % cycle)
            continue
        results.append((cycle, dt, power, theta, on["tau"] / theta, on["tau"],
                        len(neigh)))

    for s in skipped:
        print("\n  ** %s" % s)
    if not results:
        print("\nno usable on/off pair - theta needs both asymptotes, and "
              "nothing here supplies a clean one.")
        # Draw it anyway. A run that produced no number is exactly the run
        # somebody needs to LOOK at, and having the plot live only on the
        # success path is the wrong way round.
        if args.plot:
            _plot(rows, fits, args)
        return

    if args.vin_mv:
        print("\n  !! VIN OVERRIDDEN to %d mV. The logged rail is NOT being "
              "used. Every power below is computed from the override, and the "
              "rail-stability exclusion is disabled because the logged channel "
              "has been declared untrustworthy." % args.vin_mv)
    print("\n--- theta = dT / P,  C = tau / theta,  P = duty * VIN^2 / %g ohm ---"
          % ohm)
    print("  cycle     dT         P        theta       C        tau    baseline")
    for cycle, dt, power, theta, cap, tau, nb in results:
        print("  %5d  %+6.3f K  %6.1f mW  %6.1f K/W  %5.2f J/K  %6.1f s  %s"
              % (cycle, dt, power * 1000.0, theta, cap, tau,
                 "both sides" if nb == 2 else "ONE side (drift uncancelled)"))

    # A one-sided cycle has no drift cancellation - the run starts with ON, so
    # cycle 1 always is one. Averaging it into the headline drags the answer
    # by the drift it was supposed to remove (2.5 K/W on the synthetic set), so
    # it is reported per-cycle but kept OUT of the mean whenever a two-sided
    # cycle exists.
    two_sided = [r for r in results if r[6] == 2]
    used = two_sided or results
    if two_sided and len(two_sided) != len(results):
        print("\n  (%d one-sided cycle(s) excluded from the mean below - no "
              "drift cancellation; they are listed above)"
              % (len(results) - len(two_sided)))
    thetas = [r[3] for r in used]
    caps = [r[4] for r in used]
    taus = [r[5] for r in used]
    print("\n  theta   %6.1f K/W" % _mean(thetas)
          + ("   (spread %.1f over %d cycles)"
             % (max(thetas) - min(thetas), len(thetas)) if len(thetas) > 1
             else "   (ONE cycle - no spread, and no drift cancellation)"))
    print("  C       %6.2f J/K" % _mean(caps))
    print("  tau     %6.1f s" % _mean(taus))
    print("\n  Report theta WITH the medium: moisture, potted or bare, tubed "
          "or not, depth, aeration. It is a property of the installation, not "
          "of the board. PILE-THERMAL-TEST.md section 7 says where it goes.")

    if args.plot:
        _plot(rows, fits, args)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")



def _plot(rows, fits, args):
    """THE figure, plus this tool's fit drawn on the temperature panel.

    The layout is not this tool's business - it lives in o2p_plot.py and is
    shared with every other tool that plots this board, so two runs an hour
    apart can actually be compared. All that is added here is the fit, drawn
    ON the data rather than quoted beside it: if the tail is not flat, the
    picture has to say so.
    """
    try:
        import o2p_plot
    except ImportError:
        print("\n  (matplotlib not available - no plot written)")
        return
    ok = [r for r in rows if r.get("status") == "ok"]

    def overlay(by_label):
        ax = None
        for label, axis in by_label.items():
            if label.startswith("temperature"):
                ax = axis
        if ax is None:
            return
        for (cycle, phase), seg in _segments(ok):
            f = fits.get((cycle, phase))
            if not f:
                continue
            t = [r["t_s"] for r in seg if r.get("t_tip_c") is not None]
            if not t or f["tau"] <= 0:
                continue
            xs = [t[0] + i * (t[-1] - t[0]) / 100.0 for i in range(101)]
            ys = [f["inf"] + (f["t0"] - f["inf"])
                  * math.exp(-(x - t[0]) / f["tau"]) for x in xs]
            bad = not f.get("usable", True)
            ax.plot(xs, ys, "-", lw=1.4,
                    color="tab:red" if bad else "black",
                    ls=":" if bad else "-", alpha=0.75)

    try:
        o2p_plot.plot(rows, args.plot,
                      title="o2-probe heater step - black is the fitted "
                            "asymptote (red dotted = excluded)",
                      overlay=overlay)
    except (ValueError, OSError) as exc:
        print("\n  !! could not write %s: %s" % (args.plot, exc))
        return
    print("\n  wrote %s" % args.plot)


def load_csv(path):
    """Read a run CSV.

    Tolerant on purpose. This tool's own output carries t_s/cycle/phase, but
    the useful older datasets do not - tools/o2p_capture.py (SWD) and
    tools/o2p_poll.py (Modbus) both log the same MEASUREMENTS under a
    timestamp, and a step buried in one of those is still a step. So a missing
    t_s is derived from the timestamp and a missing phase is derived from the
    applied duty itself, which is the honest source anyway: the phase of a
    half-cycle is what the heater DID, not what a script asked for.
    """
    import datetime as _dt

    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            for k in ("t_s", "cmd_duty_pct", "heater_duty_pct", "t_tip_c",
                      "t_chamber_c", "t_die_c", "rh_pct", "vin_mv", "va_mv"):
                v = r.get(k, "")
                try:
                    r[k] = float(v) if v not in ("", None) else None
                except ValueError:
                    r[k] = None
            if not r.get("status"):
                r["status"] = "ok"
            rows.append(r)
    if not rows:
        return rows

    if rows[0].get("t_s") is None:
        stamp = next((k for k in ("utc", "iso_time", "time", "timestamp")
                      if k in rows[0]), None)
        if stamp is None:
            raise SystemExit("!! %s has neither t_s nor a timestamp column"
                             % path)
        t0 = None
        for r in rows:
            try:
                when = _dt.datetime.fromisoformat(
                    r[stamp].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                r["t_s"] = None
                continue
            t0 = t0 if t0 is not None else when
            r["t_s"] = (when - t0).total_seconds()
        rows = [r for r in rows if r["t_s"] is not None]

    if not rows[0].get("phase"):
        # Segment on the APPLIED duty. A change of duty starts a new
        # half-cycle; an on->off->on pattern numbers the cycles. Rows with no
        # duty reading at all (a failed poll) inherit the current phase rather
        # than splitting the segment around a hole.
        cycle, phase, last = 0, None, None
        for r in rows:
            d = r.get("heater_duty_pct")
            if d is None:
                r["cycle"], r["phase"] = cycle, phase or "off"
                continue
            if last is None or abs(d - last) > 1e-9:
                new_phase = "on" if d > 0.0 else "off"
                # A cycle begins when the heater turns ON, not whenever the
                # duty VALUE changes. A ramp 1,2,...,20 % is one ON half whose
                # duty moved - which _quality flags as DUTY_VARIES - and not
                # twenty cycles, nineteen of which would have no OFF half.
                if new_phase == "on" and phase != "on":
                    cycle += 1
                elif cycle == 0:
                    cycle = 1     # a log that starts cold, before any step
                phase = new_phase
                last = d
            r["cycle"], r["phase"] = cycle, phase
            if r.get("cmd_duty_pct") is None:
                r["cmd_duty_pct"] = d
    else:
        for r in rows:
            r["cycle"] = int(r["cycle"]) if r.get("cycle") else 0
    return rows


# --------------------------------------------------------------------------

def _port_in_use(port):
    """True if another process holds the serial device.

    Only ever used to REFUSE. A false negative just means the run proceeds and
    fails on the port itself, which is the same outcome as not checking; a
    false positive would block a legitimate run, so an unusable lsof is
    treated as "not in use" rather than as evidence.
    """
    import subprocess
    try:
        out = subprocess.run(["lsof", "-t", port], capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    # lsof exits 1 with no output when nothing holds the file. Judge by the
    # OUTPUT, not the status - `lsof | head` returning 0 is how the last check
    # of this kind reported every port as busy.
    #
    # And exclude OURSELVES. This runs after SerialLink has already opened the
    # port, so the tool was reliably detecting its own handle and refusing to
    # start every single time - a guard that fires on the one process it is
    # supposed to permit is just a broken program.
    mine = os.getpid()
    others = [int(x) for x in out.stdout.split() if x.strip().isdigit()
              and int(x) != mine]
    return bool(others)


def main():
    ap = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See ../../PILE-THERMAL-TEST.md for what the number is for.")
    ap.add_argument("csv", nargs="?", help="output CSV; appended if it exists")
    ap.add_argument("--port", help="serial line to the bus (required to run)")
    ap.add_argument("--addr", type=int, default=3,
                    help="the PROBE's Modbus address (default 3)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="E", choices=["N", "E", "O"])
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--max-fail", type=int, default=5,
                    help="abort and restore after this many CONSECUTIVE failed "
                         "polls while the heater is on (default 5). A probe "
                         "that cannot be read must not be left heating.")
    ap.add_argument("--duty", type=float, default=4.0,
                    help="percent, applied during the ON half (default 4, "
                         "which is ~4 K in still air and is what the "
                         "2026-09-04 bench used). Pick it for a 2-5 K rise. A "
                         "PILE couples far better and wants several times "
                         "more - preflight predicts the rise and tells you "
                         "the duty that would give 3 K.")
    ap.add_argument("--half", type=float, default=300.0,
                    help="seconds per half-cycle (default 300). Must be at "
                         "least 5 tau or the asymptote is guesswork.")
    ap.add_argument("--cycles", type=int, default=3,
                    help="on/off pairs (default 3). One is enough on a quiet "
                         "bench; a drifting pile needs three.")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="seconds between samples (default 5)")
    ap.add_argument("--tip-max", type=float, default=55.0,
                    help="abort if T_TIP reaches this (default 55 C, below "
                         "the cell's 60 C rating and well below the firmware's "
                         "own 80 C clamp)")
    ap.add_argument("--ohm", type=float, default=HEATER_OHM,
                    help="heater resistance (default %g, RH1||RH2). MEASURE it "
                         "if a ring PCB is fitted - a ring parallels these."
                         % HEATER_OHM)
    ap.add_argument("--vin-mv", type=float, default=None,
                    help="use this rail voltage (mV) instead of the logged "
                         "VIN_MON. For when the rail is known from a meter and "
                         "the probe's own channel is not trusted - e.g. an "
                         "image predating e31d5ac, where vin_mv was ADS1119 "
                         "AIN3 (the buffered reference electrode) scaled by the "
                         "VIN divider and had nothing to do with the supply. "
                         "P scales with VIN^2, so this moves theta a lot.")
    ap.add_argument("--theta-guess", type=float, default=98.0,
                    help="K/W assumed ONLY to sanity-check --duty before the "
                         "run (default 98, the still-air bench figure in "
                         "PILE-THERMAL-TEST.md section 1). It never enters the "
                         "result - the whole point is to measure it. Lower it "
                         "for a pile, where coupling is far tighter.")
    ap.add_argument("--rms-max", type=float, default=0.30,
                    help="a half-cycle whose exponential fit misses by more "
                         "than this RMS (K) is excluded from theta (default "
                         "0.30). The bench fits land near 0.04 K.")
    ap.add_argument("--vin-tol", type=float, default=0.02,
                    help="a half-cycle whose VIN varies by more than this "
                         "fraction is excluded (default 0.02). P scales with "
                         "VIN^2, and a rail that moved was not one experiment.")
    ap.add_argument("--preflight", action="store_true",
                    help="check the preconditions and stop; writes nothing")
    ap.add_argument("--analyze", metavar="CSV",
                    help="fit an existing run and exit; touches no hardware")
    ap.add_argument("--plot", metavar="PNG", help="write a plot of the fit")
    ap.add_argument("--poll-csv", metavar="CSV",
                    help="ALSO append every sample to this file in "
                         "o2p_poll.py's schema. The run owns the serial port, "
                         "so point this at the file the 15 s logger was "
                         "writing and the continuous record carries straight "
                         "through the experiment instead of stopping for it.")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the startup check against src/")
    args = ap.parse_args()

    if not args.no_check:
        problems = check_against_source()
        if problems:
            sys.exit("!! this tool disagrees with src/:\n   "
                     + "\n   ".join(problems)
                     + "\n   Fix the tool, or --no-check if you know better.")

    if args.analyze:
        analyse(load_csv(args.analyze), args)
        return 0

    if not args.port:
        sys.exit("!! --port is required to run (or --analyze a saved CSV)")

    link = SerialLink(args.port, args.baud, args.parity, args.timeout)
    bus = Bus(link, args.addr)
    def _open(path, columns):
        exists = os.path.exists(path) and os.path.getsize(path) > 0
        handle = open(path, "a", buffering=1, newline="")
        w = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if not exists:
            w.writeheader()
        return handle, w

    writer = poll_writer = fh = poll_fh = None
    if not args.preflight:
        if args.csv:
            fh, writer = _open(args.csv, CSV_COLUMNS)
        if args.poll_csv:
            # Appending to a file another process is writing would interleave
            # half-lines. The logger has to be stopped first, and saying so is
            # cheaper than explaining a corrupted CSV later.
            if _port_in_use(args.port):
                sys.exit("!! something else already holds %s - stop the "
                         "logger before starting the run" % args.port)
            poll_fh, poll_writer = _open(args.poll_csv, POLL_COLUMNS)
    try:
        return run(args, bus, writer, poll_writer)
    except Refusal as exc:
        print("\n!! %s" % exc)
        return 1
    finally:
        link.close()
        for handle in (fh, poll_fh):
            if handle:
                handle.close()


if __name__ == "__main__":
    sys.exit(main())
