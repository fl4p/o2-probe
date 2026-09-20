/* Membrane-heater control law and interlocks - portable, host-testable half.
 *
 * Everything here is arithmetic and decisions: no registers, no CMSIS, no
 * timer. heater.c owns the hardware. The split exists because this is the ONLY
 * part of the heater that can be validated before the probe ever meets
 * silicon, so it is the part that has to be testable.
 *
 * WHAT IS CONTROLLED, and why it is not a temperature.
 *
 * PLAN.md:294-297, verbatim: "primary loop regulates measured chamber RH
 * (SHT45, hold ~85-90 % - the actual controlled quantity: condensation margin
 * + the cell's 90 % continuous-RH spec)."
 *
 * Regulating relative humidity rather than a fixed temperature rise is the
 * whole design. PLAN.md:300-302: "+2 K gives only ~90-91 % RH on saturated
 * gas; 85 % needs ~3.1-3.7 K at 40-65 C - design the thermal path for a
 * 0-4 K dT range, not a fixed 2 K." A fixed offset that is right at 40 C is
 * wrong at 65 C, and the pile spans both.
 *
 * Heating the chamber lowers its relative humidity at constant absolute
 * humidity, so the loop is positive-acting: measured RH above setpoint asks
 * for more duty. That sign is what the monotonicity test pins down.
 *
 * THE PLANT GAIN IS UNKNOWN. THERMAL-BARRIER.md:5-9 gives 98 K/W (interval
 * 91-102, engineering bound 90-110 K/W) for the bare-PCB transverse path, and
 * :18 says plainly that this "is for PCB conduction only. It is not the
 * ring-to-ambient" path - which is the one that actually sets how many kelvin
 * a watt buys in wet pore gas. So the gains below are conservative starting
 * points, NOT design values, and they are exposed as holding registers
 * precisely because they cannot be known until the loop runs on hardware.
 */
#ifndef O2P_HEATER_CTL_H
#define O2P_HEATER_CTL_H

#include <stdbool.h>
#include <stdint.h>

/* Interlock bits. Any one of them set means duty is zero this cycle.
 *
 * They are a bitmask rather than a first-match reason code so that a buried
 * probe reporting "not heating" says everything that is wrong at once. Chasing
 * a refusal one cause at a time, five minutes per uplink, is not a diagnostic
 * procedure. Published in the diagnostic block as HEATER_BLOCK. */
enum {
    O2P_HB_NOT_COMPILED  = 1u << 0,  /* built with O2P_HEATER_ENABLE = 0 */
    O2P_HB_CONFIG_OFF    = 1u << 1,  /* HEATER_MAX_DUTY is zero */
    O2P_HB_SAFETY        = 1u << 2,  /* TMP117 therm-mode alert not armed.
                                      * An ANNOTATION, not a refusal, when it
                                      * is the ONLY bit and the attended tip
                                      * loop is armed with a valid tip - see
                                      * o2p_heater_ctl_step() (2026-09-11,
                                      * Fab's order). A hard refusal in every
                                      * other configuration, including all
                                      * autonomous loops. */
    O2P_HB_NO_RH         = 1u << 3,  /* no fresh, unmasked SHT45 humidity */
    O2P_HB_NO_TIP        = 1u << 4,  /* no fresh TMP117 reading */
    O2P_HB_NO_CHAMBER    = 1u << 5,  /* no chamber temperature for the dT clamp */
    O2P_HB_TIP_LIMIT     = 1u << 6,  /* tip at/above the firmware absolute limit */
    /* INERT on Rev A hardware: tip-minus-chamber is structurally ~0 because
     * U10 and U12 are one thermal node. Retained because the bit numbering is
     * published and because a revision with a thermally separated sensor - the
     * ring PCB's dropped temperature sensor - would make it live again. Do not
     * count it as protection; see FAB-READINESS.md. */
    O2P_HB_DT_LIMIT      = 1u << 7,  /* tip-minus-chamber at/above DT_MAX_K */
    O2P_HB_RUNAWAY       = 1u << 8,  /* latched: heat with no command */
    O2P_HB_SUPPLY        = 1u << 9,  /* rail fault - do not add 86 mA of load */
    O2P_HB_PIN_INTEGRITY = 1u << 10, /* TIM1 CH1N / PA7 assertion failed */
    O2P_HB_STALE         = 1u << 11, /* no decision recently; see heater.c */
    /* No consent to AUTONOMOUS heating: the RH loop wanted to drive and
     * HEATER_RH_CONSENT (0x0048) does not hold the magic. Never raised while
     * the bench override is armed - that path carries its own authorisation
     * and an operator. */
    O2P_HB_NO_CONSENT    = 1u << 12,
    /* NOT a refusal: the ring IS being driven, open-loop at the blind
     * fallback duty, despite the other bits set alongside it. See
     * O2P_HEATER_BLIND_DUTY_X100. */
    O2P_HB_BLIND         = 1u << 13,
    /* NOT refusals either - annotations, added 2026-09-10 (audit F5) for the
     * states an operator cannot otherwise tell from a fault. With the RH
     * loop in command - the default since fresh configs ship consent - a
     * cold, dry probe computes duty 0 with block 0, indistinguishable on
     * the bus from "would drive if needed" and from "tip mode disarmed at
     * the sentinel". These two make HEATER_BLOCK's contract ("explains why
     * HEATER_DUTY is zero") true for idleness too. They are the last two
     * free bits in the u16: the numbering is published append-only, so
     * there is no room for a third - a future "why" needs a mode field in
     * a spare diag register instead. */
    O2P_HB_IDLE          = 1u << 14, /* a loop is in command and simply has no demand */
    O2P_HB_TIP_DISARMED  = 1u << 15, /* stored tip setpoint at the 0x8000 sentinel: the RH loop is the configured law */
};

/* THE BLIND FALLBACK, added 2026-09-10 at Fab's instruction: "fix the firmware
 * so the heater can run at 10% duty, no mater the i2c".
 *
 * Twice that day the I2C bus died with the board wet - after an 80 C bath and
 * after an 80 C heater run - and the sensor-derived interlocks (NO_TIP,
 * NO_CHAMBER, SAFETY) then held the heater at zero, which is the one situation
 * where heat is the remedy. The runaway latch did the same, a false positive on
 * the cool-down that only a reset cleared.
 *
 * So when the only reasons to refuse are ones a wet or sensorless board
 * produces, the ring runs OPEN LOOP at this duty instead of zero.
 *
 * WHAT BOUNDS IT WITHOUT A TIP READING: the duty alone. Still air on this
 * board is about 1.0 K per % at the tip (PILE-THERMAL-TEST.md). Shipped at
 * 10 % (~80 mW at the bench's 10.7 V, ~+10 K); raised to 50 % the same day at
 * Fab's instruction: ~0.4 W, roughly +50 K above ambient at the asymptote in
 * still air - about 76 C on a 26 C bench, with the 82 C clamp blind because
 * the tip is. It is not a bound on absolute temperature: in a warm pile it
 * adds tens of kelvin to ambient. HEATER_MAX_DUTY still caps it, and an armed
 * open-loop override caps it at the operator's duty.
 *
 * STILL REFUSES: NOT_COMPILED and CONFIG_OFF (the off switches), NO_CONSENT,
 * PIN_INTEGRITY (reads MCU registers, not pin levels, so water cannot trip it;
 * heater.c refuses on it independently), TIP_LIMIT and DT_LIMIT (raised only
 * from VALID readings - a measured overtemperature is never overridden), and a
 * die reading that is missing or at/above O2P_HEATER_BLIND_DIE_MAX_C100: the
 * MCU's own sensor, off the I2C bus, and the one thermal witness left.
 * And, since FW 0x001C (Fab's "A", 2026-09-13): a RUNAWAY latch while the tip
 * AND the cell both read - blind is for a board whose sensors are gone, not
 * for a working loop whose runaway detector fired.
 *
 * OVERRIDES, LAW-AWARE (Fab's rulings 2026-09-11 - "fix that control loop
 * bullshit", "unattended loop: annotate and regulate (keep <=80 C)", and the
 * per-law blind rule: blind must require the in-command loop's own control
 * sensor to be invalid): a sensor-unavailability bit may blind ONLY the law
 * whose control quantity it is. When the law in command's own sensor is
 * valid, the other sensor bits are annotations and the loop REGULATES,
 * bounded by whatever limits remain evaluable. So:
 *   - NO_TIP blinds only a tip law (the volatile override's setpoint or the
 *     stored one) - for the RH loop it annotates, because the tip only feeds
 *     TIP_LIMIT there (its latch semantics unchanged: unevaluable never
 *     exonerates);
 *   - NO_RH blinds only the RH law, whose own control sensor it is;
 *   - NO_CHAMBER never blinds anything: the chamber is no law's control
 *     quantity, it only feeds DT_LIMIT, whose evidence-based latch needs
 *     both sensors and stays fully live as a hard refusal;
 *   - SAFETY annotates the tip laws (the setpoint laws Fab named) and keeps
 *     its founding blind membership for the open-loop override and the RH
 *     law - the rulings did not touch those;
 *   - SUPPLY annotates everywhere (de-vetoed 2026-09-11) and RUNAWAY, not a
 *     sensor bit, keeps its membership: a latched stuck-FET verdict still
 *     blinds every law.
 * The old premise that a setpoint law with a dead chamber must "refuse
 * rather than heat open-loop on temperature" is overruled: the controlled
 * quantity is the TIP, the chamber only feeds DT_LIMIT, and DT_LIMIT remains
 * the bound.
 *
 * THE DIE GATE IS THE STAND-DOWN (Fab's order 2026-09-11: "nope, no
 * stand-down. 50 is safe if MCU die is < 40 C"): nothing schedules the
 * heater down - blind heat rides through sensor loss bounded by the duty,
 * and stands down exactly when the die gate closes. During the SHT45's
 * scheduled de-creep the RH AND the chamber reading both go invalid (the
 * same sensor's mask, main.c), so the RH law's control sensor is down: NO_RH
 * blinds it and the ring rides at this duty until the window ends or the
 * die crosses 40 C, whichever comes first. The old claim that "NO_RH on its
 * own does not trigger it" was wrong twice: NO_RH now blinds the RH law by
 * rule, and it never did arrive alone - the mask takes the chamber with it. */
#define O2P_HEATER_BLIND_DUTY_X100    5000u
/* 40.00 C, lowered from 70.00 at Fab's instruction when the blind duty went to
 * 50 %: "make sure the blind 50% are only available if MCU die is below 40°C".
 * THE BLIND DISCRIMINATOR AND STAND-DOWN GATE (Fab's order 2026-09-11, see
 * O2P_HEATER_BLIND_DUTY_X100 above): the one bound that decides whether the
 * blind fallback may drive at all, evaluated deliberately in every blind
 * cell. The die sat at 32 C while the tip reached 76 C at 70 % duty
 * (2026-09-10), so this is a bound on the MCU end of the board and on how
 * warm the environment already is, not a tip limit. No hysteresis: at the
 * threshold the fallback toggles at the 1 Hz decision rate, a slow bang-bang
 * on a thermal plant with a time constant of tens of seconds, and the die's
 * 0.29 K/LSB dither sets how often it flips there. */
#define O2P_HEATER_BLIND_DIE_MAX_C100 4000

/* Firmware's own absolute tip limit, independent of the TMP117's alert.
 *
 * DELIBERATELY BELOW the 85 C therm-mode threshold main.c programs into the
 * TMP117 (O2P_TIP_LIMIT_C100). Firmware backs off first; the hardware clamp is
 * the backstop for the case where firmware is the thing that failed. Two
 * mechanisms at the same threshold would be one mechanism.
 *
 * Hysteresis stops the clamp chattering at 1 Hz against a thermal plant whose
 * time constant is seconds. */
/* 82.00 C, raised from 80.00 on 2026-09-08.
 *
 * The clamp has to sit ABOVE the highest setpoint anyone is meant to command,
 * or it becomes the control mechanism instead of the backstop. The stated
 * experiment is to hold the tip at 80.00 C and compare against an external
 * 80.00 C bath, and with the clamp at 80.00 the loop could only be given
 * 79.00 - so the internal run topped out a kelvin below the external one and
 * the independent variable was not matched. Found by review 2026-09-08.
 *
 * Still separated from the TMP117's 85 C therm-mode threshold by 3 K, so
 * firmware continues to back off first and the hardware cutoff remains the
 * backstop for the case where firmware is the thing that failed. Two
 * mechanisms at the same threshold would be one mechanism. */
/* The tip limit programmed into the TMP117's therm-mode alert, in 0.01 C.
 *
 * IT LIVES HERE, NOT IN main.c, since 2026-09-19. main.c is the only
 * translation unit that programs it, but it is not the only one that has to
 * REASON about it: the ladder assertions compare it against the two constants
 * below, and the host tests - which cannot include main.c - had copied the
 * number as a bare `8500` in two places. When the ladder moved +10 K those
 * copies silently became assertions about a threshold that no longer existed,
 * and both tests failed for the right reason by luck rather than design.
 * A protection threshold with two definitions is a protection threshold that
 * can disagree with itself. */
#define O2P_TIP_LIMIT_C100 9500

/* 92.00 C / 87.00 C release, raised from 82.00/77.00 on 2026-09-19 (Fab:
 * "pump up the heater so the tip gets to 90 C", then "raise and push"). Same
 * +2 K over the highest commandable setpoint and the same 5 K hysteresis as
 * before; the TMP117 cutoff moved with it and is still 3 K above. The ladder
 * is asserted in main.c and this shift keeps every rung of it. */
#define O2P_HEATER_TIP_LIMIT_C100  9200
/* ONE hysteresis for every tip clamp. heater_ctl.c derives each clamp's
 * release as (limit in force - this), so the annotated 80.00 C clamp gets its
 * own correctly ordered release instead of borrowing the normal clamp's - see
 * the note at the release site. O2P_HEATER_TIP_RELEASE_C100 remains as the
 * normal clamp's release for the ladder assertions and the tests that pin it,
 * and is DERIVED so the two can no longer drift apart. */
#define O2P_HEATER_TIP_HYST_K100   500
#define O2P_HEATER_TIP_RELEASE_C100 \
    (O2P_HEATER_TIP_LIMIT_C100 - O2P_HEATER_TIP_HYST_K100)
/* 80.00 C: the tip clamp while SAFETY is in the annotated state - a tip law
 * in command, its sensor valid, and the hardware therm backstop known down.
 * Fab's order 2026-09-11: "unattended loop: annotate and regulate (keep
 * <=80 C)". Tighter than the 82.00 C limit on purpose: when the TMP117's
 * therm-mode alert cannot be credited, firmware backs off 2 K earlier. NOT
 * a permanent change - the normal O2P_HEATER_TIP_LIMIT_C100 resumes the
 * moment safety_armed does, or when no tip law is in command. */
#define O2P_HEATER_TIP_LIMIT_ANNOTATED_C100 8000

/* The dT clamp releases half a kelvin below DT_MAX_K, same reasoning. */
#define O2P_HEATER_DT_HYST_K100 50

/* Runaway: the tip is hot while we are commanding nothing.
 *
 * Cannot false-positive on a cold start, because at power-on the tip and the
 * chamber are the same temperature and dT is ~0 - the detector needs dT to
 * EXCEED the configured maximum by a further margin, sustained, with duty
 * commanded at zero throughout. The window rejects transients such as a probe
 * carried in a warm hand into cold air.
 *
 * The margin is above DT_MAX_K rather than above zero because a small standing
 * dT is expected: the TMP117 reads PCB copper on the heated island while the
 * SHT45 reads chamber gas, and PLAN.md:304-307 warns those two disagree by
 * design ("U10 measures PCB copper, but the 5 g ABS cell couples via three
 * pins and gas"). Only a difference larger than the loop is ever allowed to
 * command is evidence of uncommanded heat. */
#define O2P_HEATER_RUNAWAY_WINDOW_S 60u
/* The longest gap between two calls that may still be treated as continuous
 * observation. This is the CALLER'S CADENCE CONTRACT, not a tuning knob:
 * o2p_heater_ctl_step() runs once per 1 s cycle, so anything beyond a few
 * seconds means the detector was not watching and the evidence it holds
 * describes a different situation. Both failure modes are real - too small and
 * evidence never accumulates at the true cadence, too large and a sparse
 * glimpse across a blind interval is credited as a sustained event - and
 * neither can be fixed inside the detector, because it cannot tell sparse
 * sampling of a real event from isolated glimpses without knowing the rate. */
#define O2P_HEATER_RUNAWAY_MAX_GAP_S 5u
/* Commanded duty at or below this still counts as "we are not asking for
 * heat", in 0.01 %. Exactly-zero was too strict: a FET stuck fully on while
 * the loop happens to be asking for a few percent produced heat nobody
 * commanded, and every call reset the evidence because the duty was nonzero.
 * Saturated compost holds the humidity error positive indefinitely, so the
 * loop need never return to exactly zero.
 *
 * The genuinely dangerous case was already covered from the other side: heat
 * that pushes the tip past dt_max trips interlocks(), which zeroes the duty
 * and then arms this detector. What this threshold adds is the case where the
 * thermal outcome stays inside the safe envelope but the FET is stuck anyway -
 * broken humidity control and wasted power rather than a hazard. Found by
 * review 2026-09-08. */
#define O2P_HEATER_RUNAWAY_IDLE_DUTY_X100 500u
#define O2P_HEATER_RUNAWAY_MARGIN_K100 200

/* Runaway threshold on tip-minus-DIE.
 *
 * The chamber-referenced test above cannot see the failure it was written for.
 * A stuck-on FET heats the whole tip assembly, and the SHT45 sits 6.6 mm from
 * the TMP117 on the same copper, so both rise together: measured 2026-09-04
 * across a 30 K excursion, |tip - chamber| never exceeded 0.17 K at ANY duty
 * from 0 to 100 %. Against a 4 K limit it can never latch.
 *
 * The die is across the transverse thermal barrier and does not track the tip.
 * Measured the same evening: tip - die swings from about -2.2 K at rest to
 * +2.1 K at only 4 % duty, and the tip reached 56 C while the die stayed near
 * 28 C. A stuck-on FET is therefore a tens-of-kelvin signal on this channel.
 *
 * 10.00 K is PROVISIONAL and chosen on bench evidence: the widest legitimate
 * zero-duty excursion observed was +3.0 K (thermal history plus the die's
 * 0.29 K/LSB dither), so this is about 3.4x that, and it catches any stuck
 * duty above roughly 12 % in still air. In a pile the coupling is far tighter
 * and the same fault produces a smaller rise - PILE-THERMAL-TEST.md is the
 * measurement that should replace this number. Until then it is a detector
 * that can see the failure, which is strictly better than one that cannot. */
#define O2P_HEATER_RUNAWAY_DIE_K100 1000

/* Release hysteresis below BOTH runaway thresholds, in 0.01 K.
 *
 * Sized against the noise it has to reject, not against any event: one scaled
 * die count is 100 K over the 347-count calibration span, 0.288 K (mcu_adc.c,
 * die_temp.h), so 1.00 K is 3.47 counts - comfortably above adjacent-count
 * dither. THAT IS AN ARGUMENT FROM THE LSB, NOT A MEASUREMENT: the die is
 * converted each cycle without temporal averaging, against a separately
 * sampled VDDA, and its 1 Hz noise amplitude has never been recorded. Whether
 * a reference sitting on its threshold can chatter the release is therefore
 * conditional on that amplitude, and the full-window dwell is what actually
 * stands between dither and a release. It must also leave the release point
 * ABOVE the widest legitimate zero-duty excursion (+3.0 K, see
 * O2P_HEATER_RUNAWAY_DIE_K100), or a probe back at rest could never release;
 * 9.00 K is. Pinned by test_die_runaway_threshold_brackets_the_measured_evidence.
 *
 * Why a release exists at all is in update_runaway() (heater_ctl.c): on
 * 2026-09-10 an 80 C bath produced the die-referenced signature with no sign
 * of the FET conducting, and latched-until-reset disabled the heater. */
#define O2P_HEATER_RUNAWAY_RELEASE_HYST_K100 100

/* THE DECAY DISCRIMINATOR, FW 0x0017 (Fab 2026-09-13, watching the latch trip
 * on a probe that had just been driven hard: "this is not a runaway
 * situation", "fix the runaway latch now").
 *
 * THE DEFECT IT FIXES, which was structural rather than a bad threshold. The
 * tests above are on a LEVEL - tip minus die over 10.00 K - and the evidence
 * window is O2P_HEATER_RUNAWAY_WINDOW_S, 60 s. The plant's measured time
 * constant is tau = 150 s (docs/2026-09-12-thermal-relaxation-...). A tip
 * that the firmware itself drove to 22 K over the die therefore needs many
 * hundreds of seconds to fall back under 10 K, and the detector starts
 * counting the moment commanded duty drops under the idle threshold. So ANY
 * commanded excursion past the threshold latched on the way DOWN - reliably,
 * within 60 s, on a probe doing exactly what it was told. Measured 2026-09-13:
 * the dew law ran the tip 17.5 -> 40.7 C at 100 % duty, demand collapsed, and
 * the latch set during the cool-down with the FET plainly innocent.
 *
 * A longer window is NOT the fix. It would trade one wrong answer for
 * another: a stuck FET would heat unwatched for as long as the window, and a
 * cool-down that merely lingers near the threshold would still latch. The
 * window length cannot separate these because it is not what distinguishes
 * them.
 *
 * WHAT DOES DISTINGUISH THEM is the DIRECTION of the excess. Heat the
 * firmware commanded and then stopped commanding decays: the excess falls
 * monotonically from its peak, by tau's arithmetic several kelvin per window.
 * A FET stuck on keeps delivering power, so the excess climbs to its
 * asymptote and STAYS there. So: evidence accumulates only while the excess
 * has not fallen materially below the peak it reached in this window.
 *
 * WHY PEAK-REFERENCED rather than a per-sample derivative: the die is
 * converted without temporal averaging at 0.288 K per count (die_temp.h), so
 * a one-second difference is dominated by dither - a decay near the threshold
 * is only ~0.07 K/s. Against the PEAK over a 60 s window the same decay is
 * several kelvin, which is far outside that dither.
 *
 * 1.00 K, the same size as the release hysteresis and for the same reason:
 * comfortably above the die's adjacent-count dither (3.47 counts) and far
 * below the ~3-7 K a genuine cool-down sheds in one window.
 *
 * WHAT IS GIVEN UP, stated plainly (guard checklist 1 and 2): a FET that
 * sticks on DURING a cool-down is not seen until the decay stops, because
 * until then the excess is still falling. That is bounded - the excess stops
 * falling as soon as the stuck power balances the loss - and it is the right
 * trade against a detector that cannot be used at all because it fires on
 * every legitimate excursion. The detector remains MONOTONIC in the fault:
 * the more power a stuck FET delivers, the higher and flatter the excess, and
 * the sooner it latches. */
#define O2P_HEATER_RUNAWAY_DECAY_K100 100

/* Conservative default gains. Error is in 0.01 %RH, output in 0.01 % duty.
 *
 * kp = 2.00 means a 10 %RH error asks for 20 % duty; ki = 0.10 means the same
 * error integrates about 1 % of duty per second, reaching full scale in a
 * couple of minutes. Slow on purpose: a loop that cannot be tuned before it is
 * potted should err towards sluggish rather than towards overshooting into a
 * cell rated to 60 C.
 *
 * UNVERIFIED. These are not derived from a measured plant - see the header
 * comment on why no such plant model exists yet. */
#define O2P_HEATER_KP_X100_DEFAULT 200u
#define O2P_HEATER_KI_X100_DEFAULT 10u

/* Tip-loop defaults. Error is in 0.01 K, output in 0.01 % duty, so kp = 50
 * means a 2 K shortfall asks for full duty and ki = 0.5 means a 1 K standing
 * error integrates about 0.5 % of duty per second.
 *
 * Chosen to saturate early and integrate slowly, which suits a plant that is
 * ~1 W into a thermal mass with a time constant of seconds to tens of
 * seconds: overshoot costs little because the absolute clamp is a kelvin
 * above any legal setpoint, while a sluggish approach costs only bench time.
 * PROVISIONAL, like every other number about this plant - and unlike the RH
 * gains these are volatile registers, so they can be moved without a reflash. */
#define O2P_HEATER_TEST_KP_X100_DEFAULT 5000u
#define O2P_HEATER_TEST_KI_X100_DEFAULT 50u

/* THE DEW-MARGIN LAW, FW 0x0013 (Fab's order 2026-09-11, probe in a steam
 * bath: "fix it so it keeps a reasonable dew-margin"; his answers: reference
 * surface = the cell-side TMP117, margin = 4 K, "margin, up to the 80 C tip
 * cap").
 *
 * WHY THE RH LAW WAS NOT ENOUGH. It regulates RH measured by the SHT45 on
 * the heated island, i.e. at a PCB temperature, not at the cell. Published
 * DEW_MARGIN is tip minus dew point and has the same blindness
 * (DEW-MARGIN-IS-BLIND.md): every reference sat on the self-heated copper.
 * Measured 2026-09-11 15:18 UTC in the bath: tip 77.7 C, cell side 74.9 C,
 * gas dew point ~76.2 C - the cell was condensing with the tip reporting
 * +1.5 K of margin.
 *
 * WHAT IT REGULATES. margin = T_cell - Td(T_chamber, RH). The dew point is a
 * property of the gas, and absolute humidity survives the island's
 * self-heating, so the SHT45's RH at its own temperature still gives the
 * gas dew point; only the SURFACE it is compared against changes, from the
 * tip to the cell side. Positive error (margin short of 4 K) asks for duty.
 * CONDITION (Codex review of 4fe6b36, finding 4): only while the SHT45 is
 * responsive to the gas. Liquid water on its surface makes it unresponsive
 * to air RH (Sensirion SHT4x datasheet v7.3), and nothing here can detect
 * that - a successful read and a Magnus-valid input are not evidence of it.
 *
 * WHAT BOUNDS IT, and "margin wins, up to the 80 C cap" read literally. The
 * error is min(margin shortfall, tip ceiling room), so the loop holds the tip
 * at O2P_HEATER_DEW_TIP_CEIL_C100 when the margin cannot be met - which a
 * saturated gas near 76 C guarantees, because the cell side gains only ~0.4 K
 * per K of tip. The ceiling is a kelvin below the 80.00 C clamp so the clamp
 * stays a backstop rather than becoming the control mechanism (the argument
 * at O2P_HEATER_TIP_LIMIT_C100). The clamp itself is 80.00 C under this law
 * whatever SAFETY says. Above the cell's 60 C rating the margin still wins,
 * per the same answer.
 *
 * WHEN IT IS IN COMMAND. The autonomous humidity-side slot - no override, no
 * stored tip setpoint, RH consent (0x0048) - and a valid cell reading. With
 * the cell invalid the RH law runs exactly as before; the mode tag restarts
 * the integrator on every hand-over.
 *
 * Its sensors, per the per-law blind rule, REVISED FW 0x001B: only NO_TIP
 * blinds it. The tip is the bound, and an unevaluable cap is not a cap. NO_RH
 * and NO_CHAMBER - humidity lost, as in every SHT45 de-creep - now ANNOTATE:
 * the dew point is unavailable, so the law withholds its own demand, and the
 * gradient floor, which needs only the tip and the cell, keeps regulating
 * under dew_ceiling_c100(). Before, they blinded it into the 50 % fallback,
 * which ignores the gradient ceiling: the review modelled a de-creep with the
 * die under 40 C taking the tip 36.6 K over the cell. HEATER_LAW reports the
 * state as O2P_HEATER_LAWF_DEW_NO_DEWPOINT. SAFETY annotates, as before.
 *
 * The Magnus fit is stated to ~60 C; a bath or pile at 75 C is extrapolation
 * (psychro.h). All four numbers are compile-time: PROVISIONAL gains for an
 * unmeasured plant. Error in 0.01 K, output in 0.01 % duty: kp = 5 asks 20 %
 * for a 4 K shortfall, ki = 0.05 integrates 0.2 %/s at that error (Ti 100 s,
 * slow on purpose - the cell side lags the tip).
 *
 * THE GRADIENT CEILING, FW 0x001A (Fab 2026-09-13, "fix it, flash it", on the
 * proposal "never let the tip run more than a few K above the cell"). The
 * ceiling above is now min(79.00 C, T_cell + DT_MAX_K), everywhere the law
 * means "the ceiling" (dew_ceiling_c100() in heater_ctl.c).
 *
 * WHAT IT FIXES, measured on probe 3 that morning under FW 0x0017: with the
 * tip setpoint disarmed the dew law took command in a wet enclosure and ran
 * the tip 22 -> 69 C at 100 % duty with the cell fitted, while the cell sat
 * at 24 C and the gas dew point climbed to 28 C with the heat. Nothing about
 * the law was bounded in kelvin except the 79 C ceiling, and how far 1.2 W
 * gets toward it depends on theta - 68 K/W in still bench air, unknown and
 * probably far lower buried. A duty cap is the wrong bound for the same
 * reason (Fab: "no more 10% caps"). A GRADIENT is bounded whatever the
 * plant: the heater cannot hold the tip more than DT_MAX_K ahead of the cell
 * for more power than that gradient conducts.
 *
 * WHY DT_MAX_K and not a new constant. It is already the stored 0-4 K design
 * envelope (PLAN.md: "design the thermal path for a 0-4 K dT range"), but on
 * Rev A it is enforced against the chamber, which shares the tip's copper, so
 * the DT_LIMIT interlock can never raise. The cell-side TMP117 is the sensor
 * that envelope was written for. Using the register keeps the bound tunable
 * without a reflash, and adds nothing to the flash record - no layout bump,
 * no migration, the air point survives the install.
 *
 * WHAT IS GIVEN UP, stated. Authority. Where the cell gains k K per K of tip,
 * a 4 K gradient buys at most ~4k/(1-k) K of cell warming, so a margin that
 * needs a steeper gradient is now UNREACHABLE by construction - the law holds
 * the tip at T_cell + DT_MAX_K, and after O2P_HEATER_DEW_UNREACH_DWELL_S at
 * that ceiling the detector withholds its demand and the floor holds the
 * 2 K gradient. Raising DT_MAX_K buys authority back, one register write, at
 * the cost of the excursion this bounds. A DT_MAX_K under the floor's 2 K
 * clamps the floor too: the envelope is the envelope. */
#define O2P_HEATER_DEW_MARGIN_K100    400
#define O2P_HEATER_DEW_TIP_CEIL_C100  7900
#define O2P_HEATER_DEW_KP_X100        500u
#define O2P_HEATER_DEW_KI_X100        5u

/* THE GRADIENT FLOOR, high-selected against the dew-margin law (FW 0x0016;
 * Fab 2026-09-13, "should we combine +2k and the 4k dew margin?" then "lets
 * do it then").
 *
 * WHAT IT IS. A second regulator running ALONGSIDE the dew law in the same
 * autonomous slot, on error = (T_cell + delta) - T_tip, whose duty is
 * high-selected against the dew law's:
 *
 *     duty = max(dew_duty, floor_duty)
 *
 * A high-select, not a mode switch and not a precedence rule. Both are LOWER
 * bounds on how hard the ring must drive, so the binding one wins and the
 * other is simply not binding. Neither can turn the other down.
 *
 * WHY A SECOND LAW AT ALL - THE FAILURE MODE IT COVERS. The dew law's own
 * header states its blind spot: "Liquid water on its surface makes [the
 * SHT45] unresponsive to air RH ... and nothing here can detect that - a
 * successful read and a Magnus-valid input are not evidence of it." The
 * dangerous direction is a wetted-then-drying element reading LOW RH: the
 * computed dew point drops, the margin looks generous, and the dew law asks
 * for NO DUTY while the membrane condenses. No interlock fires, because
 * every reading is valid; the law is simply being lied to. A buried probe in
 * saturated pore gas is exactly the environment that produces that.
 *
 * The floor's whole value is that its sensor chain is DISJOINT from the one
 * that can lie: two TMP117s, no humidity, no Magnus form, no wettable
 * sensing surface. It cannot chase a real dew point - it has no humidity
 * input - and it cannot be fooled by a wrong one either.
 *
 * WHY IT IS A GRADIENT AND NOT "+2 K OVER AMBIENT". Fab asked for a constant
 * +2 K over ambient, and THIS BOARD HAS NO AMBIENT SENSOR. T_EXT, the
 * cell-side TMP117, is simultaneously the closest thing to ambient and the
 * dew law's reference SURFACE, so "cell minus ambient" taken from it is
 * identically zero. What two sensors can state is a GRADIENT: hold the tip
 * delta above the cell side, i.e. always be pumping heat outward past the
 * membrane. Measured 2026-09-12/13
 * (docs/2026-09-12-thermal-relaxation-theta-and-ambient.md): the cell is
 * ~11 % coupled to the tip in still bench air, so a 2 K gradient lifts the
 * cell only ~0.22 K over true ambient there; the same night's bath data has
 * the cell gaining ~0.4 K per K of tip. So READ THIS AS "the heat never
 * stops flowing outward", NOT as a 2 K dew margin. It is a floor under the
 * dew law, not a substitute for it.
 *
 * WHAT IT COSTS, stated rather than discovered later. In a pile hotter than
 * the probe the cell is heated from OUTSIDE, the tip lags, and the floor
 * demands duty to get back ahead of it - so this runs continuously in a
 * self-heating windrow rather than only when the gas is wet. It is bounded
 * by the same 79.00 C ceiling and by HEATER_MAX_DUTY, and in saturated pore
 * gas the dew law was going to be the binding one anyway; but a power budget
 * for a buried probe cannot be taken from the dew law alone.
 *
 * MONOTONICITY, restated honestly (guard checklist 2). The dew law alone is
 * monotonic in margin. THE COMBINED LAW IS NOT monotonic in cell
 * temperature, and that is structural rather than an oversight: a cell ABOVE
 * the tip is the floor's own worst case (no outward heat flow) and the dew
 * law's best case (margin to spare). Each law stays monotonic in ITS OWN
 * error, and max() is monotonic in each argument - that is the guarantee
 * which survives the combination, and the one the tests pin down.
 *
 * COMPILE-TIME ON PURPOSE. delta and the gains are constants, not holding
 * registers, so this change does not touch the flash record's layout. A
 * CONFIG_LAYOUT_VERSION bump is what runs a record through config_migrate.c,
 * and that is the only path on which an air point has ever been lost. Fab,
 * 2026-09-13: "we can't loose our calibration every re-flash." Keeping the
 * law out of the record keeps that promise.
 *
 * GAINS. The error is in 0.01 K like the dew law's, but THE PLANT IS NOT THE
 * SAME - this one controls the tip directly, the fast node, where the dew
 * law controls the cell across a lag. So it takes the tip loop's gains
 * (O2P_HEATER_TEST_*_DEFAULT, bench-verified holding +/-0.04 K on
 * 2026-09-12) rather than the dew law's deliberately slow pair. PROVISIONAL,
 * like every other number about this plant. */
#define O2P_HEATER_FLOOR_DELTA_K100   200
#define O2P_HEATER_FLOOR_KP_X100      5000u
#define O2P_HEATER_FLOOR_KI_X100      50u

/* THE DRY-AIR IDLE GATE on the gradient floor (FW 0x0027; Fab 2026-09-19,
 * "is there an energy saving mode, when probe is not inside the pile and RH is
 * <90%, so heater stays off most of the time?" then "do it").
 *
 * WHAT IT DOES. While the gas is DRY the floor withholds its demand, so a
 * probe out of the pile in ordinary air draws nothing for heat. The dew law
 * was already free in that regime - at RH under 90 % the cell-side margin is
 * far past O2P_HEATER_DEW_MARGIN_K100 and its error is negative, so pi_core()
 * clamps it to zero - and the floor, which has no humidity input by design,
 * was the one paying: it demands T_cell + 2.00 K whatever the gas is doing.
 * POWER-BUDGET.md, 2026-09-07: the heater is 90-98 % of the battery budget at
 * any duty over a few percent (233 d at 0 %, 28 d at 12 %), so this gate is
 * the whole difference between a bench/transport probe lasting a season and
 * lasting a month.
 *
 * WHAT IT COSTS, stated rather than discovered later. The floor exists
 * BECAUSE the SHT45 can be valid and wrong: a wetted-then-drying element
 * reads LOW RH, the dew law asks for nothing, and the membrane condenses with
 * no bit raised. Gating the floor on that same reading re-opens exactly that
 * hole - it is the one objection to this change and it is not closed here,
 * only BOUNDED. Fab's call, having been told.
 *
 * TWO CONDITIONS, NOT ONE, AND THE SECOND IS THE LOAD-BEARING ONE. Fab named
 * RH under 90 %, and RH ALONE CANNOT BE THE TEST: heating the chamber lowers
 * its relative humidity at constant absolute humidity - that is the whole
 * design (heater_ctl.h:20) - so a floor gated on RH switches itself off by
 * its own success. Simulated against the test suite's wet-enclosure plant
 * (the 2026-09-13 bench regime, Td riding the tip at 0.92): an RH-only gate
 * read "dry" as soon as the ring had warmed the chamber a little, and the
 * outward gradient fell to a 0.40 K peak - 0.05 K mean over the last 1200 s -
 * where this form holds ~2 K. So the gate ALSO requires
 * O2P_HEATER_DRY_MARGIN_K100 of cell-side dew margin, the same quantity the
 * dew law regulates.
 *
 * WHY THAT HELPS, STATED NARROWLY (codex review of 0a5587a, finding 3). It is
 * NOT that warming gas always raises its dew point: at fixed vapour pressure
 * Td does not move, and dTd/dTtip = 0.92 describes that wet enclosure, not a
 * law. What the margin condition buys is that in an assembly with a finite
 * wet source - a pile, a damp chamber, a probe that came out of the ground -
 * the evaporating water tracks the heat, so RH falls while the margin does
 * not, and the margin is the one of the two that notices. It buys nothing
 * against a WRONG humidity: both conditions are computed from the same SHT45,
 * so they are not independent evidence, and a wetted element reading 60 %
 * where the gas is at 84 % gates the floor with the membrane 1 K under its
 * dew point (the review's constructed case, reproduced against this
 * controller). That is the hole the re-assert debt below bounds and does not
 * close. Both conditions must hold; either one failing runs the floor.
 *
 * WHY THE MARGIN THRESHOLD SITS ABOVE THE DEW LAW'S TARGET. At
 * O2P_HEATER_DEW_MARGIN_K100 the dew law is still asking for duty, so gating
 * the floor there would save nothing and would take the floor away at the one
 * moment the two laws disagree. 2 K of headroom means the gate can only act
 * where the dew law is comfortably satisfied, and it keeps the combination
 * monotonic in the direction that matters: as the gas gets wetter the gate
 * opens, and duty can only rise.
 *
 * HOW IT IS BOUNDED, AS A DEBT. The gate is not a latch. Each idle period
 * ends after O2P_HEATER_DRY_IDLE_MAX_S, and the next one may not begin until
 * the floor has driven for O2P_HEATER_DRY_ASSERT_S OBSERVED seconds. It is a
 * debt rather than a window because a window can be cancelled: the first form
 * cleared an in-flight window whenever the gas stopped reading dry, and one
 * invalid humidity sample every 1799 s then bought four driven seconds in two
 * hours (codex review of 0a5587a, finding 1). Seconds the floor runs for ANY
 * reason pay the debt, so a wet excursion now settles it instead of erasing
 * it, and out of reset the debt is unpaid - a probe drives its gradient for
 * 120 s before it is ever allowed to idle.
 *
 * WHAT THAT PREMIUM ACTUALLY BUYS, measured on the repo's own plant model
 * (theta 68 K/W, tau 150 s) rather than asserted: the floor's proportional
 * term asks for 100 % at the start of the window, so the 2 K gradient is back
 * within ~30 s and holds for the rest of it - NOT a ramp, despite the
 * integrator being zeroed. It then decays to ~0.27 K about 300 s into the
 * next idle period and to nothing well before the window after that. So the
 * probe spends 6.25 % of its time driving and ~14 % of the continuous
 * floor's ENERGY (the reheat is not free), and the membrane sees a gradient
 * that is real but intermittent. This is exposure bounding, NOT detection -
 * nothing here can tell a dry probe from a lied-to one, and no clearance of
 * existing condensate is claimed.
 *
 * FAIL-SAFE DIRECTION (guard checklist 1). Only a POSITIVE, evaluable "this
 * gas is dry" engages the gate: rh and chamber valid AND a Magnus-evaluable
 * dew point AND RH under the threshold. Every unevaluable case - NO_RH, a
 * de-creeping SHT45, an out-of-range humidity - leaves the floor running, the
 * same direction O2P_HEATER_LAWF_DEW_NO_DEWPOINT takes. So does a RUNAWAY
 * latch: under one the floor is the only thing regulating (FW 0x001F) and
 * this gate never touches that path.
 *
 * THE TWO CLOCKS ARE ASYMMETRIC ON PURPOSE. The idle clock is elapsed time,
 * so seconds nobody observed still count TOWARD re-asserting the floor; the
 * assert window counts only observed intervals, by the unreachable detector's
 * rules, so seconds nobody observed do NOT count toward ending it early.
 * Each choice errs toward heat.
 *
 * HYSTERESIS on both conditions, so a probe sitting at either threshold does
 * not chatter the floor's integrator on and off. Fab named 90 %RH; the
 * release is 5 %RH above it, and the margin releases 1 K below its entry.
 *
 * WHAT THIS IS WORTH, in the regime it was asked for. A bench or transport
 * probe in 22 C air needs about 6 K of margin, which is roughly 65 %RH or
 * drier - the ordinary lab case, and the case Fab described. In a pile, in a
 * wet enclosure, or in a box that has been breathed on, the margin is small
 * or negative and NOTHING here changes: the floor runs and the dew law runs.
 * The gate can never turn the dew law's demand down either - duty =
 * max(dew, floor), and only the floor's argument is gated.
 *
 * KNOWN INTERACTION, NOT FIXED HERE (codex review of 0a5587a, finding 5).
 * Zero duty is also what the RUNAWAY detector's 5 % idle threshold wants to
 * see before it calls environmental heat uncommanded, so on a plant where the
 * ungated floor would have sat just above that threshold, gating can latch
 * RUNAWAY where the parent did not. The consequence is a loss of the SAVING,
 * not of heat: under a latch this gate never runs and the floor regulates as
 * before (FW 0x001F). Left for Fab's call, because the fix is in the runaway
 * detector and that detector has been rebuilt twice already.
 *
 * THE GATE FEEDS BACK INTO ITS OWN RH INPUT, measured on probe 3 the evening
 * it first ran (2026-09-20, probe in bench air, VictoriaMetrics). The SHT45
 * sits in the chamber, and on Rev A the chamber shares the tip's copper - so
 * for five hours before the gate existed T_chamber - T_cell held 1.89..2.10 K,
 * which is the floor's own 2.00 K setpoint read back through that copper. The
 * moment the gate engaged it collapsed to 0.08 K and then -0.03 K, and the
 * chamber RH, flat at 43.7 % all afternoon, rose 43.67 -> 48.03 % as the
 * copper cooled: about +1.6 points of RH per kelvin at this humidity.
 *
 * So gating RAISES the humidity the gate reads, by roughly 3 points for the
 * ~2 K the chamber loses. That is the SAFE direction - it pushes toward the
 * exit threshold, i.e. toward heating - but two consequences follow and
 * neither was designed:
 *
 *   1. The exit band must be WIDER than the self-induced rise or the gate
 *      limit-cycles: engage, cool, read wetter, release, warm, read drier,
 *      engage. 9000 -> 9500 is 5 points against a measured ~3, so it holds -
 *      by 2 points, and by luck rather than by calculation. Anyone narrowing
 *      this band must re-measure that slope first.
 *   2. The energy saving SHRINKS exactly where the ambient is damp, because a
 *      probe sitting near 88 % RH gates, cools, reads past 95 % and puts the
 *      floor back. That is the right behaviour and it is not a free lunch.
 *
 * It also moves the published oxygen a little: the O2 conversion's temperature
 * term is the cell law on T_EXT (FW 0x001E), the cell is coupled to the tip at
 * the measured 3..11 %, and the tip now idles. Small against the knee's own
 * corrections, but it is a step at the moment of gating, not a drift.
 *
 * All four numbers PROVISIONAL, like every other number about this plant. */
#define O2P_HEATER_DRY_RH_X100          9000u
#define O2P_HEATER_DRY_RH_EXIT_X100     9500u
#define O2P_HEATER_DRY_MARGIN_K100      600
#define O2P_HEATER_DRY_MARGIN_EXIT_K100 500
#define O2P_HEATER_DRY_IDLE_MAX_S       1800u
#define O2P_HEATER_DRY_ASSERT_S         120u

/* The most one interval may credit to the re-assert debt. The floor's drive
 * does not outlive the actuator's staleness cut - heater.c stops driving
 * O2P_HEATER_STALE_MS (2 s) after the apply() that commanded it - so an
 * interval longer than that heated for 2 s whatever the clock says. Kept as
 * its own constant rather than including heater.h, which is the hardware
 * half: this file is the portable, host-tested one. Track O2P_HEATER_STALE_MS
 * if it moves. */
#define O2P_HEATER_DRY_CREDIT_MAX_S     2u

/* THE PILE LOCKOUT, FW 0x002A - the one gate input humidity cannot fake.
 *
 * MEASURED, probe 3 buried 24.2 h in the windrow, 2026-09-17/18 (VM, 26 h
 * window from 12:00): chamber RH ran 38.96..91.26 % and was UNDER 90 % for 238
 * of 270 samples. The SHT45 is on the tip's copper, the pile holds the probe at
 * 50..77 C, and heating collapses RELATIVE humidity while the gas stays
 * saturated - so a buried probe reads "dry" 88 % of the time and
 * O2P_HEATER_DRY_RH_X100 blocks nothing underground. The whole of the gate's
 * protection there rested on the margin.
 *
 * AND THE TWO ARE NOT INDEPENDENT EVIDENCE. The margin is T_EXT minus the GAS
 * dew point, and that dew point is Magnus on the SAME chamber RH: depressed RH
 * puts the dew point too low, which puts the margin too HIGH. They fail
 * together and for one reason. At 12:01:00 on 09-17, probe already in the pile
 * at T_EXT 51.15 C, the probe read RH 58.90 % and margin 8.56 K - BOTH gate
 * conditions satisfied, on the one sample of 76 where the margin cleared 6.00 K.
 * The gate would have withheld the floor inside the windrow. (This is the codex
 * review's finding 2, which the burial data turns from a hypothetical into an
 * observation.)
 *
 * So gate additionally on ABSOLUTE CELL TEMPERATURE, which no humidity error
 * can move: a pile is 50..77 C and a bench or a transit box is ~20 C. This is
 * also the honest encoding of what was actually asked for - "when probe is not
 * inside the pile" (Fab 2026-09-19) - rather than inferring location from a
 * sensor the heater warms.
 *
 * T_EXT and not the chamber: the chamber shares the tip's copper on Rev A and
 * so carries the heater's own rise, while the cell is coupled at the measured
 * 3..11 %. It costs nothing to require, because the margin already needs a
 * valid cell reading. An INVALID cell reading refuses the gate, like every
 * other unevaluable input here.
 *
 * 35.00 C with release at 37.00: far above any bench (probe 3 sat at 20.6..21.6
 * C through the 2026-09-20 acceptance run) and far below any pile, including
 * the 48.61 C the probe read on its way in. Hysteresis in the same direction as
 * the other two - once gated it takes the EXIT number to put the floor back. */
#define O2P_HEATER_DRY_MAX_CELL_C100      3500
#define O2P_HEATER_DRY_MAX_CELL_EXIT_C100 3700

/* THE UNREACHABLE-MARGIN DETECTOR - CEILING-DWELL FORM, FW 0x0019 (Fab
 * 2026-09-13: "build the unreachable-margin detector", then option A after the
 * codex xhigh review of the 0x0018 form).
 *
 * THE REGIME, measured on probe 3 that morning. With liquid water inside the
 * enclosure the gas dew point rose with the tip: tip 24.40 -> 40.66 C
 * (+16.26 K) while Td went 17.85 -> 32.83 C (+14.98 K), dTd/dTtip = 0.92, and
 * the cell gained 0.59 K for 23 K of tip. The law cannot close that error,
 * and by its own design it holds the tip at the ceiling indefinitely.
 *
 * WHY NOT A CLIMB TEST - the 0x0018 form, withdrawn before it was flashed.
 * "5 K of tip must buy 0.5 K of margin" needs >= 10 % cell coupling, and this
 * plant measures 3-11 %, so it gave up on margins that were reachable in dry
 * gas (review model at 9 %: gave up after 43 s and left the cell under its dew
 * point for 6 h, where the plain law reached 4 K at a 73.7 C tip). It also
 * credited heat from outside as its own climb, never fired when the tip could
 * not climb 5 K, and could clear itself on its own retreat. Every one of those
 * is an attribution question these inputs cannot answer.
 *
 * WHAT IS TESTED NOW asks no attribution question: the cell-side margin is
 * short AND the tip is within O2P_HEATER_DEW_UNREACH_BAND_K100 of the ceiling,
 * continuously for O2P_HEATER_DEW_UNREACH_DWELL_S observed seconds. At the
 * ceiling the law cannot add heat whatever put the tip there, so giving up
 * costs no authority - and if the pile put it there, backing off is right
 * anyway. Seconds are counted like the runaway detector's evidence: only
 * intervals actually observed between two pinned cycles, discarded across a
 * gap over O2P_HEATER_RUNAWAY_MAX_GAP_S and across any refused cycle.
 *
 * WHAT IT DOES NOT BOUND, stated rather than discovered. The climb to the
 * ceiling happens first: this bounds the TIME there, not the peak. And a plant
 * that cannot reach the ceiling at full duty - a well-coupled buried probe -
 * never trips it and keeps driving; that costs power, not the cell.
 *
 * THE RESPONSE is a fallback, never a shutdown: the dew law's demand is
 * withheld and the high-selected gradient floor holds the tip.
 *
 * RECOVERY: the margin at least O2P_HEATER_DEW_UNREACH_CLEAR_HYST_K100 over its
 * target for O2P_HEATER_DEW_UNREACH_CLEAR_HOLD_S observed seconds, or the
 * retry. The hysteresis is the point. Backing off cools the enclosure, it
 * re-absorbs water, Td falls and the margin rises; a bare "target met" exit let
 * that retreat clear the verdict and re-climb every ~80 min in the review's
 * model. The retry is long because each one costs a climb and a dwell.
 *
 * PAUSES, NOT RESETS (FW 0x001B, Fab 2026-09-13 "yes" to the codex review of
 * 9eb3a34/496dd2e). 0x0019 discarded the evidence on every refused cycle, and
 * the review showed the opposite failure that bought: one NO_TIP glitch every
 * 500 s kept a 75 C probe at >= 78 C for 21 562 s of 6 h with no verdict. Now
 * a refused cycle - and a cycle with no dew point, see below - only PAUSES
 * the evidence: those seconds are never credited, and nothing already counted
 * is lost. A pause longer than O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S, or another
 * law taking command, discards it. The 0x0018 hazard pausing could revive -
 * blind heat credited as the law's own climb - is closed by the same change,
 * because losing only humidity no longer drives the blind fallback at all.
 * The verdict survives a pause; a different law in command drops it.
 *
 * All PROVISIONAL. 1 K of band because the law parks at 79.00 C through its
 * min(); 600 s is four tau, long enough for the margin to have answered; the
 * clear hold matches it. */
#define O2P_HEATER_DEW_UNREACH_BAND_K100       100
#define O2P_HEATER_DEW_UNREACH_DWELL_S         600u
#define O2P_HEATER_DEW_UNREACH_CLEAR_HYST_K100 100
#define O2P_HEATER_DEW_UNREACH_CLEAR_HOLD_S    600u
#define O2P_HEATER_DEW_UNREACH_RETRY_S         21600u   /* 6 h */
/* A PAUSE in the detector's evidence longer than this is treated as a
 * different situation and the evidence is discarded; shorter ones only stop
 * the clock (FW 0x001B, codex review of 9eb3a34/496dd2e finding 2). Equal to
 * the dwell on purpose: a pause as long as a whole dwell has had time to
 * change the plant, one shorter than it has not. */
#define O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S     600u

/* How long main.c bridges the last accepted cell-side reading. Its glitch
 * filter withholds up to five 1 Hz readings after a >3 K jump; without a
 * bridge each of those would hand the loop to the RH law and back, restarting
 * the integrator twice. 10 s covers that and no more: the cell side moves
 * slowly, and past it the RH law takes over. */
#define O2P_HEATER_CELL_MAX_AGE_S     10u
/* A SHORT CELL DROPOUT IS NOT A DEAD CELL (FW 0x0020, Fab 2026-09-13 "fix it";
 * codex reviews of 455972d/c7baa57/a75c1f4, finding 1). Once a valid cell
 * reading has been seen, the reading going missing for less than this many
 * seconds - past O2P_HEATER_CELL_MAX_AGE_S's bridge, a stalled conversion's
 * grace, a run of rejected glitches - neither reaches the blind fallback nor
 * hands the dew law over. Before, every dropout did both: the review's flicker
 * schedule (13 s valid, 11 s missing) alternated refusal with blind 50 % and
 * took the tip 17 K over the cell, and one missing cycle every 500 s kept a hot
 * probe at the ceiling for hours by resetting the unreachable dwell.
 * A cell missing for LONGER than this is treated as gone, and the wet-board
 * blind fallback applies as before - die-gated, for a board whose sensors died.
 * A probe that never produced a cell reading (no T_EXT fitted) is unaffected.
 * PROVISIONAL: 60 s is several bridge windows and far under tau. */
#define O2P_HEATER_CELL_LOSS_BLIND_S  60u


typedef struct {
    uint16_t setpoint_x100;    /* target chamber RH, 0.01 %RH */
    uint16_t dt_max_k100;      /* tip-above-chamber clamp, and (FW 0x001A) the
                                  dew law's tip-above-cell ceiling, 0.01 K */
    uint16_t max_duty_x100;    /* output clamp, 0.01 %; zero disables */
    uint16_t kp_x100;
    uint16_t ki_x100;          /* per second */
    /* BENCH OVERRIDE (register 0x0060). Drives `test_duty_x100` open-loop and
     * suppresses exactly three interlocks: NO_RH, NO_CHAMBER and DT_LIMIT.
     *
     * Those three and no others because they are the interlocks that protect
     * the CONTROLLED QUANTITY, not the hardware. The loop regulates chamber
     * RH, so without humidity it has no error signal and without a chamber
     * temperature it cannot honour the 0-4 K envelope - both are refusals to
     * control, and an open-loop duty is not controlling anything. dT is that
     * envelope itself, and the envelope exists to hold the cell near ambient
     * for a dew-point loop; a deliberate thermal characterisation is the one
     * case where exceeding it is the experiment.
     *
     * Every interlock that answers to the hardware stays live: SAFETY,
     * NO_TIP, TIP_LIMIT, SUPPLY, RUNAWAY, PIN_INTEGRITY, NOT_COMPILED, and
     * max_duty_x100 which still clamps the commanded value and still means
     * "off" at zero. */
    bool     test_override;
    uint16_t test_duty_x100;   /* 0.01 %, clamped to max_duty_x100 */
    /* HEATER_RH_CONSENT holds its magic. Gates the RH loop ONLY - and, since
     * FW 0x0013, the dew-margin law that takes the RH loop's slot whenever
     * the cell-side reading is valid (O2P_HEATER_DEW_MARGIN_K100). Same
     * autonomous slot, same authorisation; no new register.
     *
     * The heater used to be compiled out, so O2P_HB_NOT_COMPILED refused
     * every path whatever the stored configuration said. Once the ring is
     * compiled in, a nonzero heater_max_duty_x100 in flash is on its own
     * enough to start an unvalidated loop on a buried probe with nobody
     * present, and migrations carry that maximum forward by design. This is
     * the consent that replaces the compile flag's guarantee. */
    bool     rh_consent;
    /* Increments on every 0 -> 1 arm of the bench override. Only equality
     * between consecutive cycles is used, so wrapping is harmless. */
    uint8_t  session;
    /* TIP TEMPERATURE SETPOINT MODE. When test_tip_sp_valid is set, the
     * override closes a PI loop on tip temperature instead of commanding
     * test_duty_x100 open loop.
     *
     * This exists because the alternative is not temperature control at all.
     * Nothing in this firmware regulates a temperature: the only loop is on
     * chamber RH, and the 80.00/75.00 C pair is the absolute CLAMP with its
     * anti-chatter hysteresis. Driving open loop against that clamp yields a
     * mean near 77.5 C with +/-2.5 K of sawtooth, and reaches it by bouncing
     * a protection device off its limits once per thermal time constant.
     *
     * With a setpoint bounded below the clamp, the clamp goes back to being
     * a backstop: it firing at all means the loop failed. */
    bool     test_tip_sp_valid;
    int16_t  test_tip_sp_c100;
    /* Gains for the TIP loop only. The RH loop's kp/ki above are in %RH and
     * do not transfer - error here is in 0.01 K. */
    uint16_t test_kp_x100;
    uint16_t test_ki_x100;
    /* PERSISTENT TIP SETPOINT MODE (registers 0x0049 and 0x004A), the flash-backed
     * counterpart of the volatile block above.
     *
     * Precedence is override > persistent tip > RH, and it is not arbitrary:
     * an armed override means an operator is standing at the bench right now,
     * and their intent outranks anything a previous session committed to
     * flash.
     *
     * WHAT THIS MODE SUPPRESSES, and it is one interlock rather than the
     * override's three. NO_RH only: a temperature loop genuinely has no use
     * for humidity, and refusing to hold a commanded temperature because the
     * SHT45 is in its de-creep window would be a refusal with no reason
     * behind it.
     *
     * NO_CHAMBER and DT_LIMIT stay LIVE, unlike under the override. The
     * override suppresses them because exceeding the 0-4 K envelope IS the
     * experiment and an operator is present to own that. Here nobody is
     * present, so the envelope keeps its meaning. On Rev A this costs
     * nothing - the dT clamp is structurally inert, tip and chamber being one
     * thermal node - but on a revision with a thermally separated sensor it
     * is the difference between a loop that holds 80 C in a pile and one that
     * refuses to. Refusing is correct: holding a tip tens of kelvin above the
     * chamber with nobody watching is the exact thing the envelope exists to
     * prevent. */
    bool     tip_consent;
    bool     tip_sp_valid;
    int16_t  tip_sp_c100;
    /* No gains of its own: it uses test_kp_x100/test_ki_x100 above. The flash
     * record had six spare bytes and the setpoint plus its consent took four;
     * see O2P_REG_HEATER_TIP_CONSENT for why the target and the authorisation
     * are the two things that had to survive a reset. */
} o2p_heater_cfg_t;

typedef struct {
    bool     drive_possible;   /* heater hardware is under our control at all */
    bool     safety_armed;     /* o2p_tmp117_safety_armed() */
    bool     pin_integrity_ok; /* CC1NE clear and PA7 still analog */
    bool     rh_valid;
    uint16_t rh_x100;
    bool     tip_valid;
    int16_t  t_tip_c100;
    bool     chamber_valid;
    int16_t  t_chamber_c100;
    /* The chamber temperature was MEASURED this cycle rather than bridged from
     * the cache. chamber_valid alone admits a cached value (main.c), which is
     * right for the dT clamp and for latching and wrong for EXONERATING a
     * latched runaway: release requires both. A zero-initialised caller gets
     * "not fresh", which can only delay a release. */
    bool     chamber_fresh;
    /* MCU die, o2p_mcu_adc_read_die_c100(). The ONLY sensor on this board
     * thermally separated from the tip - U10 and U12 sit 6.6 mm apart on the
     * same copper and cannot disagree. Used for runaway detection only; it is
     * +/-5 C absolute, which is useless for a 4 K clamp but irrelevant against
     * the tens of kelvin a stuck-on FET produces. */
    bool     die_valid;
    int16_t  t_die_c100;
    bool     supply_ok;
    /* The cell-side TMP117 (T_EXT, on the cell enclosure's side far from the
     * pins), bridged by main.c for O2P_HEATER_CELL_MAX_AGE_S. The dew-margin
     * law's reference surface; while it is invalid the RH law is in command
     * instead. A zero-initialised caller gets "no cell", i.e. the RH law. */
    bool     cell_valid;
    int16_t  t_cell_c100;
} o2p_heater_in_t;

typedef struct {
    float    integ;            /* integrator, carried in duty units */
    /* The GRADIENT FLOOR's own integrator (O2P_HEATER_FLOOR_DELTA_K100).
     *
     * Separate from `integ` because the floor runs CONCURRENTLY with the dew
     * law rather than instead of it, so the mode tag - which exists to stop
     * one law inheriting another's wind-up - cannot arbitrate between them:
     * both are live in the same cycle. Zeroed whenever the floor is not in
     * command, which is every path except the dew law's, so re-entry is the
     * same bumpless proportional-only restart a mode change gives. */
    float    integ_floor;
    bool     runaway_latched;
    bool     zero_duty_timing;
    uint32_t zero_duty_since_s;
    /* Seconds of OBSERVED, valid, uncommanded-heat evidence. Not elapsed time
     * and not a timestamp difference: only intervals the detector actually
     * looked at are counted, so a gap in sampling cannot be credited as if
     * the condition had held through it. */
    uint16_t runaway_evidence_s;
    /* Seconds of observed evidence, while LATCHED, that the signature has
     * cleared: every reference valid, and each below its threshold by
     * O2P_HEATER_RUNAWAY_RELEASE_HYST_K100. Counted by the same rules as
     * runaway_evidence_s, and reset by any hot or hysteresis-band sample, any
     * gap longer than O2P_HEATER_RUNAWAY_MAX_GAP_S, and any lost reference. */
    uint16_t runaway_clear_s;
    /* The highest "how far over the latching threshold" this evidence window
     * has seen, in 0.01 K, or INT16_MIN when the window holds no sample yet.
     * Evidence stops accumulating once the excess falls
     * O2P_HEATER_RUNAWAY_DECAY_K100 below it, which is what tells commanded
     * heat decaying from a peak apart from a FET stuck at one. Re-based on
     * every reset so a long decay does not leave a stale high-water mark that
     * suppresses the detector forever. */
    int16_t  runaway_peak_k100;
    /* The unreachable-margin detector (O2P_HEATER_DEW_UNREACH_DWELL_S):
     * observed seconds pinned at the ceiling and observed seconds recovered,
     * whether the previous dew-law cycle was itself pinned / recovered (so the
     * second BEFORE the first pinned sample is never credited), the previous
     * dew-law cycle's clock - invalid across any refusal or other law, so a gap
     * is never credited - and the verdict with its retry deadline. */
    bool     dew_unreachable;
    bool     dew_prev_valid;
    bool     dew_pinned;
    bool     dew_recovered;
    uint16_t dew_dwell_s;
    uint16_t dew_clear_s;
    uint32_t dew_prev_s;
    uint32_t dew_retry_at_s;
    /* The evidence is paused (a refused or dew-point-less cycle) since
     * dew_pause_since_s; see O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S. */
    bool     dew_paused;
    uint32_t dew_pause_since_s;
    /* The cell reading's dropout clock (O2P_HEATER_CELL_LOSS_BLIND_S): a
     * valid reading has been seen at least once, it is currently missing, and
     * since when. */
    bool     cell_seen;
    bool     cell_lost;
    uint32_t cell_lost_since_s;
    /* The DRY-AIR IDLE GATE on the gradient floor
     * (O2P_HEATER_DRY_IDLE_MAX_S): whether the floor is currently gated off
     * and since when (ELAPSED, not observed), the DEBT - how many observed
     * seconds the floor has driven since the last idle period began, which
     * must reach O2P_HEATER_DRY_ASSERT_S before the gate may engage again -
     * and the previous cycle's clock for counting it. dry_prev_valid is true
     * only after a cycle whose floor actually ran: it is cleared at the top
     * of every step, so no refused or handed-over interval is ever credited. */
    bool     dry_idle;
    bool     dry_prev_valid;
    uint16_t dry_floor_run_s;
    uint32_t dry_idle_since_s;
    uint32_t dry_prev_s;
    bool     dt_clamped;       /* hysteresis latches */
    bool     tip_clamped;
    /* Which loop produced the current integrator, so that switching between
     * them cannot inherit a wound-up integral whose units and plant are both
     * different. See O2P_HEATER_MODE_*. */
    uint8_t  last_mode;
    /* Which override session the integrator belongs to. A disarm and re-arm
     * served between two 1 Hz decisions changes neither the mode nor any
     * input, so without this a new bench run inherits the last one's wind-up. */
    uint8_t  last_session;
} o2p_heater_state_t;

enum {
    O2P_HEATER_MODE_RH   = 0u,  /* the shipped humidity loop */
    O2P_HEATER_MODE_OPEN = 1u,  /* override, open-loop duty */
    O2P_HEATER_MODE_TIP  = 2u,  /* override, tip-temperature loop */
    /* The PERSISTENT tip loop. A distinct tag from O2P_HEATER_MODE_TIP even
     * though the control law is identical, because pi_step() resets the
     * integrator on a mode change and these two modes have different gains
     * and different authorisation. Sliding between them with a wound-up
     * integral would carry a bench run's history into an unattended one. */
    O2P_HEATER_MODE_TIP_AUTO = 3u,
    /* The dew-margin law (FW 0x0013). Its own tag because its error is in
     * kelvin of margin while the RH law it replaces is in %RH: an integral
     * carried between them would be in the wrong units. */
    O2P_HEATER_MODE_DEW = 4u,
};

/* WHICH LAW PRODUCED THIS DUTY, published as HEATER_LAW (0x0008).
 *
 * HEATER_BLOCK cannot answer this and was never able to. Its bit 15
 * (TIP_DISARMED) says only "no stored tip setpoint", which is identical for
 * the RH law and the dew law; and the annotations are added only on the path
 * where a loop actually regulated, so on a refusing or blind cycle the bit is
 * ABSENT whatever the configuration holds. A bench tool read that absence as
 * "a tip setpoint is in command" twice on 2026-09-13 and reported the
 * opposite of the truth both times. heater_ctl.h:78-87 anticipated exactly
 * this - "a future 'why' needs a mode field in a spare diag register" - and
 * the u16's last two bits went to IDLE and TIP_DISARMED, so there was none.
 *
 * Low byte: the law. High byte: flags about it. */
enum {
    O2P_HEATER_LAW_RH       = 0u,  /* the shipped humidity loop */
    O2P_HEATER_LAW_OPEN     = 1u,  /* bench override, open-loop duty */
    O2P_HEATER_LAW_TIP      = 2u,  /* bench override, tip-temperature loop */
    O2P_HEATER_LAW_TIP_AUTO = 3u,  /* the stored absolute tip setpoint */
    O2P_HEATER_LAW_DEW      = 4u,  /* dew margin, high-selected with the floor */
    /* Not laws - the two ways there is no law in command. Distinct values
     * because "driving open-loop because everything refused" and "not driving
     * at all" are different situations and an operator must not have to infer
     * which from the duty. */
    O2P_HEATER_LAW_BLIND    = 5u,
    O2P_HEATER_LAW_REFUSED  = 6u,
};
/* The dew law has given up on its margin and the gradient floor is holding
 * the tip instead. See O2P_HEATER_DEW_UNREACH_DWELL_S. Set only alongside
 * O2P_HEATER_LAW_DEW. */
#define O2P_HEATER_LAWF_DEW_UNREACHABLE 0x0100u
/* The dew law is configured but has no dew point this cycle - humidity lost,
 * typically the SHT45 de-creep - so its own demand is withheld and only the
 * gradient floor is regulating (FW 0x001B). Set only alongside
 * O2P_HEATER_LAW_DEW. */
#define O2P_HEATER_LAWF_DEW_NO_DEWPOINT 0x0200u
/* A runaway latch is in force while the tip and cell still read, so the dew
 * law's demand is withheld and only the gradient floor runs (FW 0x001F). Set
 * only alongside O2P_HEATER_LAW_DEW, and only when RUNAWAY is the sole
 * refusal; HEATER_BLOCK still carries O2P_HB_RUNAWAY. */
#define O2P_HEATER_LAWF_DEW_RUNAWAY_FLOOR 0x0400u
/* The gas reads dry and the gradient floor's demand is gated off to save
 * power (FW 0x0027; O2P_HEATER_DRY_RH_X100). Set only alongside
 * O2P_HEATER_LAW_DEW, and only on a cycle the floor actually contributed
 * nothing - it is absent while the floor pays its periodic debt, which is how
 * an operator tells "idling" from "idling, but paying its periodic premium".
 * Duty zero with this bit set is the designed energy-saving state, not a
 * fault; HEATER_BLOCK carries the usual O2P_HB_IDLE beside it. */
#define O2P_HEATER_LAWF_DEW_DRY_IDLE 0x0800u

typedef struct {
    uint16_t duty_x100;
    uint16_t block;            /* O2P_HB_* ; zero means the loop is driving */
    uint16_t law;              /* O2P_HEATER_LAW_* | O2P_HEATER_LAWF_* */
} o2p_heater_out_t;

void o2p_heater_ctl_reset(o2p_heater_state_t *st);

/* One 1 Hz step. `now_s` is a monotonic seconds counter used only for the
 * runaway window; it may wrap.
 *
 * Guarantees the tests pin down: any interlock forces duty zero; an input that
 * cannot be evaluated is an interlock, never a mid-range duty; and the
 * integrator cannot accumulate while the output is clamped. */
void o2p_heater_ctl_step(o2p_heater_state_t *st,
                         const o2p_heater_cfg_t *cfg,
                         const o2p_heater_in_t *in,
                         uint32_t now_s,
                         o2p_heater_out_t *out);

/* THE PUBLISHED DUTY IS A 60 s TRAILING MEAN (FW 0x0025, Fab 2026-09-17).
 *
 * WHY. The loop decides once a second, and until 0x0025 HEATER_DUTY (0x0005)
 * carried only the last decision. Its readers sample it sparsely - the farm
 * node every 60 s for LoRaWAN, the web app every 5 s - so Grafana plotted a
 * 1-in-60 snapshot of a duty that moves every second and aliased (seen live:
 * 0 / 8.5 / 0 / 1.9 %). The instantaneous duty moved to HEATER_DUTY_NOW
 * (0x0009) for the readers that need it: the web app's heater badge, which
 * takes duty > 0 as the witness that the ring is driven, and tip-loop tuning.
 *
 * WHY TIME, NOT "SINCE THE LAST READ". Several masters share the register (the
 * node, the keeper, o2p_cli.py). A read-reset mean would make each one's value
 * depend on when the others last read. This window depends on the clock only.
 *
 * DEFINITION. main.c notes the duty the hardware layer holds -
 * o2p_heater_duty_x100(), after o2p_heater_service() has had its chance to
 * stale-cut it - once per elapsed second of uptime. The published value is
 * the arithmetic mean of the last O2P_DUTY_MEAN_WINDOW_S such samples, rounded
 * half up, in the same u16 0.01 % format.
 *  - It is the APPLIED duty, not the controller's request: a refused, stale-cut
 *    or pin-integrity-forced-off second counts as the zero the ring got.
 *  - A second in which no decision arrived (a slow cycle, a blocking SHT45
 *    pulse) is sampled as whatever the ring held through it. Time-weighted,
 *    not decision-weighted: a duty held for 3 s counts three times.
 *  - Fewer than 60 samples since boot: the mean of those that exist - the
 *    window is SHORTER, never padded with zeros the probe did not measure.
 *  - No sample at all (the first second of uptime): the instantaneous duty,
 *    because it is the only evidence there is. The window never produces a
 *    number it has not seen.
 *  - Samples above 10000 are clamped to 10000 on the way in, so the mean is
 *    always 0..10000.
 * The window restarts only at boot; nothing a master does resets it. */
#define O2P_DUTY_MEAN_WINDOW_S 60u

typedef struct {
    uint16_t ring[O2P_DUTY_MEAN_WINDOW_S];
    uint8_t  head;     /* index the next sample is written to */
    uint8_t  n;        /* samples held, 0..O2P_DUTY_MEAN_WINDOW_S */
} o2p_duty_mean_t;

void o2p_duty_mean_reset(o2p_duty_mean_t *m);

/* One call per elapsed second of uptime, with the duty applied at that second. */
void o2p_duty_mean_note(o2p_duty_mean_t *m, uint16_t applied_x100);

/* The trailing mean, 0..10000. `now_x100` is returned (clamped) only when the
 * window holds no sample yet. */
uint16_t o2p_duty_mean_x100(const o2p_duty_mean_t *m, uint16_t now_x100);

#endif /* O2P_HEATER_CTL_H */
