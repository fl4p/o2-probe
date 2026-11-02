/* The sampler's pure decisions, lifted out of main.c so they can be tested.
 *
 * main.c reaches CMSIS through every driver it calls and cannot compile on the
 * host, so none of this had coverage - including the arithmetic that turns an
 * ADC code into the cell current every published oxygen reading is derived
 * from. Two of the three fatal bugs found in this firmware's review cycle
 * lived in files with exactly this property.
 *
 * Nothing here touches hardware or global state: values in, decision out.
 */
#ifndef O2P_SAMPLER_LOGIC_H
#define O2P_SAMPLER_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

#include "ads1119.h"
#include "faults.h"
#include "hw_caps.h"
#include "o2.h"
#include "regmap.h"

/* LMP91000 transimpedance and internal zero. The zero is 67 % of VREF for the
 * 3-lead bias configuration this board uses. */
#define O2P_LMP_TIA_OHM   7000
#define O2P_LMP_INT_Z_NUM 67
#define O2P_LMP_INT_Z_DEN 100

/* Cell current in nanoamps, from an AIN0 code.
 *
 *   V(AIN0) = internal_zero -/+ I * R_TIA          (R_TIA = 7 kOhm)
 *
 * so the current is the DEPARTURE from the internal zero. Both the zero and
 * the ADC reference come from VREF_TRIM, so this is ratiometric and
 * first-order immune to VREF drift.
 *
 * The sign is deliberately preserved: SCHEMATIC-REVIEW.md M4 leaves the SGX
 * sign convention open and the air-versus-nitrogen bench pair is what settles
 * it. Taking an absolute value here would hide the answer. */
static inline int32_t o2p_cell_na_from_code(int32_t code, uint32_t vref_mv)
{
    int32_t uv = o2p_ads1119_code_to_uv(code, vref_mv);
    int32_t zero_uv = (int32_t)(((int64_t)vref_mv * 1000 * O2P_LMP_INT_Z_NUM) /
                                O2P_LMP_INT_Z_DEN);
    int32_t delta_uv = zero_uv - uv;
    return (int32_t)(((int64_t)delta_uv * 1000) / O2P_LMP_TIA_OHM);
}

/* The same current from an AIN0 reading already in absolute microvolts - one
 * taken against the ADS1119's INTERNAL 2.048 V reference (debug opcode 9). The
 * LMP91000's internal zero is still 0.67 x the analog reference it is fed, so
 * that term keeps the measured VREF: this is NOT ratiometric, and a VREF error
 * now lands in the current instead of cancelling. Equal to
 * o2p_cell_na_from_code(code, vref) when uv = o2p_ads1119_code_to_uv(code, vref). */
static inline int32_t o2p_cell_na_from_uv(int32_t uv, uint32_t zero_ref_mv)
{
    int32_t zero_uv = (int32_t)(((int64_t)zero_ref_mv * 1000 * O2P_LMP_INT_Z_NUM) /
                                O2P_LMP_INT_Z_DEN);
    int32_t delta_uv = zero_uv - uv;
    return (int32_t)(((int64_t)delta_uv * 1000) / O2P_LMP_TIA_OHM);
}

/* The gas temperature the conversion should use: the CHAMBER sensor if it
 * read, else the tip, else nothing.
 *
 * The order matters and is not arbitrary. The chamber sensor sits in the gas
 * being measured; the tip is heated on purpose and reads the ring, so using it
 * as a gas temperature biases the tempco correction by whatever the heater is
 * doing. It is a fallback because a biased temperature beats no reading at
 * all for a correction that degrades gracefully - but never for a CALIBRATION
 * reference, which is why finish_o2() additionally refuses to take an air
 * point on a fallback temperature. */
static inline int16_t o2p_gas_temperature(bool chamber_ok, int16_t t_chamber,
                                          bool tip_ok, int16_t t_tip)
{
    if (chamber_ok) {
        return t_chamber;
    }
    if (tip_ok) {
        return t_tip;
    }
    return O2P_I16_INVALID;
}

/* The last cell-side (T_EXT) reading that was both ACCEPTED by the ext glitch
 * filter and FRESH (ext Data_Ready seen recently, phase_temps), bridged for a
 * bounded age. One rule for both consumers - the dew-margin heater law
 * (FW 0x0013) and the oxygen temperature law (FW 0x001E) - so the two cannot
 * drift apart. The age runs from the last fresh accepted reading, not from the
 * last I2C answer: a frozen conversion engine still answers, and refreshing on
 * every read held a constant temperature forever (Codex review of 4fe6b36,
 * finding 1). */
typedef struct {
    int16_t  c100;
    uint32_t taken_s;
    bool     have;
} o2p_cell_bridge_t;

static inline void o2p_cell_bridge_note(o2p_cell_bridge_t *b, bool ext_ok,
                                        bool ext_fresh, int16_t t_ext_c100,
                                        uint32_t now_s)
{
    if (ext_ok && ext_fresh && t_ext_c100 != O2P_I16_INVALID) {
        b->c100 = t_ext_c100;
        b->taken_s = now_s;
        b->have = true;
    }
}

/* True, and *out_c100 written, only while a fresh accepted reading is at most
 * max_age_s old. Nothing is written otherwise. */
static inline bool o2p_cell_bridge_get(const o2p_cell_bridge_t *b,
                                       uint32_t now_s, uint32_t max_age_s,
                                       int16_t *out_c100)
{
    if (!b->have || (uint32_t)(now_s - b->taken_s) > max_age_s) {
        return false;
    }
    *out_c100 = b->c100;
    return true;
}

/* How long the OXYGEN path bridges T_EXT. The glitch filter withholds up to
 * five 1 Hz readings after a >3 K jump; without a bridge each withheld cycle
 * would hand the conversion to the chamber sensor, which on the 2026-09-13
 * outdoor run sat up to ~4 K above T_EXT in sun - a ~1 % step in the
 * published number and back. 10 s covers the filter and no more. */
#define O2P_O2_CELL_MAX_AGE_S 10u

/* The temperature the OXYGEN conversion and the air point use (FW 0x001E):
 * the cell-side TMP117 (T_EXT, on the cell enclosure) when a bridged reading
 * exists, else o2p_gas_temperature() above.
 *
 * Why T_EXT and not the chamber: every other temperature is a BOARD node on
 * the ring heater's copper, and the cell is on flying leads. Measured on the
 * 2026-09-13 outdoor run (13-36 C, ~850 rows, heater cycling overnight): the
 * capillary law on T_EXT fits the cell current to 0.19 % rms of ln(current)
 * (percent of current, NOT %vol) and predicts the day from the night with no
 * offset. A fitted LINEAR tempco on the chamber - not the same law - did worse
 * than the same linear fit on T_EXT (0.70 against 0.60 % rms, before glitch
 * clipping) and landed on a negative dilution alpha.
 * docs/2026-09-13-outdoor-tempco-dilution-fit.md. The run is 13-36 C with
 * the heater near idle: it does NOT validate the 40-75 C heated pile case.
 *
 * The fallback is a board node and therefore biased whenever the heater runs;
 * it is kept because a biased temperature beats none for a correction that
 * degrades gracefully. finish_o2() refuses to take an AIR POINT on it when
 * the probe has a T_EXT sensor, so the stored reference and the running
 * measurement are always the same sensor. */
static inline int16_t o2p_cell_temperature(bool ext_ok, int16_t t_ext,
                                           bool chamber_ok, int16_t t_chamber,
                                           bool tip_ok, int16_t t_tip)
{
    if (ext_ok && t_ext != O2P_I16_INVALID) {
        return t_ext;
    }
    return o2p_gas_temperature(chamber_ok, t_chamber, tip_ok, t_tip);
}

/* Encode a cell current into the O2_RAW register's uA*100 units, or its
 * sentinel when it will not fit. 10 nA per count. */
static inline int16_t o2p_encode_raw_ua_x100(int32_t cell_na)
{
    int32_t raw_x100 = cell_na / 10;
    if (raw_x100 > 32767 || raw_x100 < -32767) {
        return O2P_I16_INVALID;
    }
    return (int16_t)raw_x100;
}

/* The settling restart. Returns the new deadline; bumps *restarts only when
 * the deadline was actually expired, so a fault that persists for minutes
 * cannot inflate the counter into meaninglessness - the counter's whole job
 * is to make a bias interruption that the once-a-second supervision MISSED
 * visible from a buried probe, and a counter that also climbs during a fault
 * you can already see is no longer that evidence. Saturates rather than
 * wrapping. */
static inline uint32_t o2p_settle_restart(uint32_t now_s, uint32_t deadline_s,
                                          uint32_t settle_s,
                                          uint16_t *restarts)
{
    if (deadline_s <= now_s && *restarts != 0xFFFFu) {
        (*restarts)++;
    }
    return now_s + settle_s;
}

/* Undo the Rev A ADS voltage dividers (VA: R24/R25, VIN: R26/R27).
 *
 * Lifted here so the formula and constants are shared with the host test suite
 * (test_main.c). The call site in main.c remains review-only because main.c
 * cannot link on the host (CMSIS). Clamps to 0xFFFE so a railed measurement
 * never emits the 0xFFFF invalid sentinel (O2P_U16_INVALID). */
static inline uint16_t o2p_scale_va_ads(uint16_t raw_mv)
{
    uint32_t va = ((uint32_t)raw_mv * O2P_HW_DIV_VA_ADS_DEN) / O2P_HW_DIV_VA_ADS_NUM;
    if (va > 0xFFFEu) {
        va = 0xFFFEu;
    }
    return (uint16_t)va;
}

/* VIN takes the board's stored ratio, VIN_DIV_X1000 (0x004B), when it holds
 * one a write would have accepted, and the netlist divider otherwise - pass
 * o2p_cfg_vin_div_x1000(&cfg). The stored branch cannot overflow: 65535 *
 * 20000 is inside u32. */
static inline uint16_t o2p_scale_vin_ads(uint16_t raw_mv, uint16_t div_x1000)
{
    uint32_t vin = o2p_vin_div_x1000_in_window(div_x1000)
        ? ((uint32_t)raw_mv * div_x1000) / 1000u
        : ((uint32_t)raw_mv * O2P_HW_DIV_VIN_ADS_DEN) / O2P_HW_DIV_VIN_ADS_NUM;
    if (vin > 0xFFFEu) {
        vin = 0xFFFEu;
    }
    return (uint16_t)vin;
}

/* --- the SHT45 de-creep gate ---------------------------------------------
 *
 * Two decisions, lifted here for the reason at the top of this file: they
 * lived inside phase_sht(), main.c does not compile on the host, and the
 * question they answer - "is a silent chamber a maintenance window or a dead
 * sensor" - is the one every consumer of the fault word depends on.
 *
 * They are a PAIR on purpose. Whether to read, and what to report, are the two
 * halves of one rule, and the bug they replace was exactly the two halves
 * disagreeing: the mask suppressed the reading AND raised I2C_FAIL_SHT, so a
 * working sensor was reported as failed three times a day while I2C_ERRS sat
 * at 0. Keeping them adjacent, and calling both from the one site, is what
 * stops the next edit from restoring one without the other.
 */

/* Is this cycle inside the recovery window of a de-creep pulse?
 *
 * Written as a subtraction so the 49-day o2p_millis() wrap is harmless, the
 * same way o2p_elapsed() is. main.c seeds the pulse timestamp at boot as
 * (now - O2P_SHT_RECOVERY_MS) so the first cycle is NOT masked; that relies on
 * the same wrap-safe subtraction, and is why this is `<` and not `<=`. */
static inline bool o2p_sht_masked(uint32_t now_ms, uint32_t pulse_ms)
{
    return (uint32_t)(now_ms - pulse_ms) < O2P_SHT_RECOVERY_MS;
}

/* What the SHT45 phase contributes to the cycle's fault word.
 *
 * A SCHEDULED MASK CONTRIBUTES NOTHING, and that is the whole content of this
 * function. The chamber channels still publish their sentinels - the snapshot
 * is reset to INVALID every cycle and a masked cycle writes nothing into it -
 * so a consumer sees "no chamber reading, no fault" for a mask and "no chamber
 * reading, I2C_FAIL_SHT" for a sensor that genuinely did not answer. The
 * absence of the bit is the only thing in this firmware that tells those two
 * apart; see faults.h.
 *
 * `pulse_failed` IS THE EXCEPTION, AND IT WAS MISSED ON THE FIRST PASS. The
 * mask is entered by main.c whether the heater command succeeded or not - a
 * pulse that did not complete leaves the element in an unknown thermal state,
 * so masking is right either way. But the transaction failing IS an observed
 * I2C failure, and while the mask reported I2C_FAIL_SHT unconditionally it was
 * reported by accident. Dropping the unconditional fault turned an already-seen
 * bus failure into 350 s of silence indistinguishable from healthy
 * maintenance - unevaluable input reading as OK, which is the first line of
 * this repo's guard checklist. Found by review of 2ac1712.
 *
 * `measure_ok` is meaningless while masked, because no measurement is
 * attempted then. It is ignored rather than asserted on: the caller's control
 * flow already cannot produce that combination, and a gate that traps on an
 * impossible input is one that fails on the day the control flow changes for
 * an unrelated reason. */
static inline uint16_t o2p_sht_phase_faults(bool masked, bool pulse_failed,
                                            bool measure_ok)
{
    if (masked) {
        return pulse_failed ? O2P_F_I2C_FAIL_SHT : 0u;
    }
    return measure_ok ? 0u : O2P_F_I2C_FAIL_SHT;
}

#endif /* O2P_SAMPLER_LOGIC_H */

/* P4a: the stuck-mux signature, as a pure predicate so it can be tested.
 *
 * A stuck mux returns the PREVIOUS channel's sample, so two DIFFERENT channels
 * yielding bit-identical averages is the direct evidence. Bit-identical is
 * deliberate: WE_BUF and RE_BUF sit within a few mV of each other whenever the
 * cell is unbiased, so any near-miss tolerance would fire on healthy hardware.
 * It reports evidence, never a verdict - nothing is suppressed on this bit. */
static inline bool o2p_mux_stuck_signature(bool prev_valid, uint8_t prev_mux,
                                           int32_t prev_code, uint8_t mux,
                                           int32_t code)
{
    return prev_valid && mux != prev_mux && code == prev_code;
}

/* P4b: the ADS1119's own offset, inputs shorted to AVDD/2 by MUX=111. */
static inline bool o2p_adc_offset_out_of_band(int32_t code, int32_t max_lsb)
{
    return code > max_lsb || code < -max_lsb;
}
