/* LMP91000 configurable potentiostat AFE, I2C 0x48 (fixed).
 *
 * Register encodings verified against TI SNAS506I (Dec 2014) section 7.6 -
 * Table 2 register map and the TIACN / REFCN / MODECN field tables.
 *
 * The bias is the whole reason this part is here. The SGX-OX-ROHS-Mini is a
 * BIASED three-electrode cell needing -600 +/- 10 mV between working and
 * reference electrodes (DS-0637). With an external reference the LMP91000
 * expresses bias as a percentage of VREF (SNAS506I 7.6.4), and 24 % is the
 * TOP step it offers - so 0.24 * 2.500 V = 600.0 mV exactly, and the +/-10 mV
 * window means VREF must be trimmed to 2.500 V within about +/-42 mV. That is
 * a manual bench adjustment of RV1; firmware can only verify it.
 *
 * Two failure modes this driver exists to catch:
 *
 *  - The part powers up in DEEP SLEEP with VOLATILE configuration. A 3V3A
 *    brownout with the MCU still running drops the cell bias without any
 *    reset the MCU would notice (PLAN.md:273-280). Hence readback
 *    supervision on every cycle, not just at boot.
 *  - Losing bias costs up to FIFTEEN MINUTES of settling before the cell
 *    reads correctly again (DS-0637 Note 1). So a detected mismatch is not
 *    just "rewrite it": it must restart the settling timer and invalidate the
 *    oxygen channel until it expires.
 */
#ifndef O2P_LMP91000_H
#define O2P_LMP91000_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    O2P_LMP_REG_STATUS = 0x00u,  /* bit0: 1 = ready */
    O2P_LMP_REG_LOCK   = 0x01u,  /* bit0: 0 = TIACN/REFCN writable, 1 = locked */
    O2P_LMP_REG_TIACN  = 0x10u,
    O2P_LMP_REG_REFCN  = 0x11u,
    O2P_LMP_REG_MODECN = 0x12u,
};

/* TIACN = TIA_GAIN[4:2] | RLOAD[1:0].
 *   TIA_GAIN 011 = 7 kOhm. PLAN.md:254 sizes the chain for >=150 uA: the cell
 *   reaches ~152 uA at 30 % O2, which across 7 kOhm is a 1.06 V excursion from
 *   the 1.675 V internal zero - inside the 0-3.3 V output range. 14 kOhm would
 *   clip; 3.5 kOhm would waste half the ADC.
 *   RLOAD 00 = 10 Ohm, the smallest offered, because the load resistor sits in
 *   series with the working electrode and only adds error here.
 */
#define O2P_LMP_TIACN_INTENDED  ((uint8_t)((3u << 2) | 0u))   /* 0x0C */

/* REFCN = REF_SOURCE[7] | INT_Z[6:5] | BIAS_SIGN[4] | BIAS[3:0].
 *   REF_SOURCE 1 = external: the trimmed 2.500 V on VREF_TRIM, shared with the
 *   ADS1119's REFP so the measurement is ratiometric.
 *   INT_Z 10 = 67 %. The cell current is unipolar, so putting the zero high
 *   gives the whole downward swing to signal.
 *   BIAS_SIGN 0 = negative, i.e. (VWE - VRE) < 0, which is what the SGX cell
 *   specifies. NOTE: SCHEMATIC-REVIEW.md M4 leaves the SGX SIGN CONVENTION as
 *   an open release gate - this encodes the datasheet reading, and the bench
 *   air-versus-nitrogen pair is what confirms it.
 *   BIAS 1101 = 24 %, the maximum step.
 */
#define O2P_LMP_REFCN_INTENDED  ((uint8_t)(0x80u | (2u << 5) | (0u << 4) | 0x0Du)) /* 0xCD */

/* MODECN = FET_SHORT[7] | OP_MODE[2:0]. 011 = 3-lead amperometric cell.
 * FET_SHORT stays 0: shorting the cell is for storage, and doing it here
 * would trigger the 15-minute settling penalty every time. */
#define O2P_LMP_MODECN_INTENDED ((uint8_t)0x03u)

/* OP_MODE 111 - temperature measurement with the TIA STILL ON.
 *
 * 110 offers the same reading with the TIA off and must never be used here:
 * dropping the TIA unbiases the cell, and DS-0637 Note 1 then costs up to
 * FIFTEEN MINUTES of settling. 111 leaves the potentiostat running and merely
 * re-routes what VOUT carries (SNAS506I 7.6.5): the temperature appears on
 * VOUT while the TIA output moves to pin C2.
 *
 * On this board C2 is only the external filter connector - it goes to no
 * converter - so for as long as this mode is set THERE IS NO OXYGEN READING.
 * The window must be short and no cell conversion may be attributed to it. */
#define O2P_LMP_MODECN_TEMP     ((uint8_t)0x07u)

/* SNAS506I 6.5: the sensor needs 1.9 ms after the mode is entered. */
#define O2P_LMP_TEMP_SETTLE_MS  3u

/* VOUT window the sensor is specified over, from the Table 1 endpoints:
 * 1875 mV at -40 C down to 861 mV at +85 C. Outside it the reading is not a
 * temperature.
 *
 * THIS IS NOT A SUBSTITUTE FOR THE MODE READBACK, and must never be used as
 * one. The oxygen channel swings roughly 930-970 mV on this cell, which sits
 * INSIDE this window and decodes as a perfectly plausible 72-77 C. So a mode
 * switch that silently failed would be caught by nothing here. Only the
 * MODECN readback separates the two, which is why both entering and leaving
 * the mode verify it and why a failure invalidates rather than estimates. */
#define O2P_LMP_TEMP_MV_MAX     1875u   /* -40 C */
#define O2P_LMP_TEMP_MV_MIN      861u   /* +85 C */

/* How far V(WE)-V(RE) may sit from the commanded -24 % of VREF before the
 * potentiostat is not doing its job. See the argument at the call site in
 * main.c: wide on purpose, because every term it has to clear - follower
 * offsets, the VREF trim band, TcVOS_RW at +/-1750 uV - is an order of
 * magnitude smaller, and a check that fires on a healthy probe is worse than
 * no check. A quarter of the commanded value. */
#define O2P_CELL_BIAS_TOLERANCE_MV 150

/* V(WE) - V(RE) in mV that REFCN_INTENDED actually commands, at this VREF.
 *
 * DERIVED from the constant, not restated. The bias guard and its test both
 * need this number, and two hand-copied "24 %, negative" would agree today and
 * go stale together the day the step changes - the guard checklist's
 * source-of-truth failure, in the one place it costs a probe its oxygen
 * channel. Review 2026-09-08.
 *
 * SNAS506I 7.6.4: BIAS[3:0] is a percentage of the reference in a table whose
 * first two steps are 0 % and 1 % and which then advances 2 % per code, so
 * code n>=1 is 2*(n-1) %... except that the table's own values are
 * 0,1,2,4,6,8,10,12,14,16,18,20,22,24, i.e. code 1 is 1 % and code n>=2 is
 * 2*(n-1) %. BIAS_SIGN (bit 4) 0 = negative, (VWE-VRE)<0. */
static inline int32_t o2p_lmp_bias_percent(uint8_t refcn)
{
    uint8_t code = (uint8_t)(refcn & 0x0Fu);
    if (code == 0u) { return 0; }
    if (code == 1u) { return 1; }
    return (int32_t)(2u * (code - 1u));
}

static inline int32_t o2p_lmp_commanded_bias_mv(int32_t vref_mv)
{
    int32_t pct = o2p_lmp_bias_percent(O2P_LMP_REFCN_INTENDED);
    int32_t mag = (vref_mv * pct) / 100;
    /* BIAS_SIGN 0 = negative = (VWE - VRE) < 0, and cell_bias_mv is measured
     * as WE - RE, so the two conventions line up with no extra inversion. */
    return ((O2P_LMP_REFCN_INTENDED & 0x10u) != 0u) ? mag : -mag;
}

typedef enum {
    O2P_LMP_OK = 0,
    O2P_LMP_IO,
    O2P_LMP_MISMATCH,   /* readback differs from intent - bias may be gone */
} o2p_lmp_status_t;

/* Drive MENB low (it is already pulled low by R17) and write the full
 * configuration. Safe to call repeatedly; it unlocks, writes, re-reads. */
o2p_lmp_status_t o2p_lmp91000_configure(void);

/* Read TIACN/REFCN/MODECN back and compare with intent. This is the bias
 * supervisor: call it every cycle. `out_readback` receives TIACN << 8 | REFCN
 * for the diagnostic register, so a mismatch can be diagnosed remotely from
 * a buried probe rather than guessed at. */
o2p_lmp_status_t o2p_lmp91000_verify(uint16_t *out_readback);

/* Route VOUT to the die temperature sensor, and back.
 *
 * Both READ MODECN BACK and report MISMATCH if the part did not take the
 * change - see O2P_LMP_TEMP_MV_MAX for why a value check cannot stand in for
 * this. A caller that gets anything but O2P_LMP_OK from _enter() must not
 * convert AIN0 as a temperature; one that gets anything but O2P_LMP_OK from
 * _exit() is left with VOUT possibly still on the sensor, so it must
 * invalidate the oxygen channel rather than publish the next conversion.
 *
 * _enter() also spends O2P_LMP_TEMP_SETTLE_MS, so the caller does not have
 * to know the part's power-on time. */
o2p_lmp_status_t o2p_lmp91000_temp_enter(uint8_t *out_modecn);

/* Does this MODECN readback describe a mode in which the cell STOPPED being
 * driven? That is the only question that decides whether a failed mode switch
 * owes the caller a settling restart, and it is answerable only from the
 * readback value - which set_mode() used to discard.
 *
 * In the header, and inline, so the host tests can drive it: lmp91000.c does
 * not build on the host, and a decision that only exists there is a decision
 * nothing checks. SNAS506I 7.6.5 OP_MODE: 011 three-lead amperometric and 111
 * temperature-with-TIA-on both keep the potentiostat running; 000 deep sleep,
 * 010 standby and 110 temperature-with-TIA-off do not. Anything else is not a
 * mode this driver knows, and an unrecognised readback is not evidence the
 * cell is fine, so it counts as disturbed. */
static inline bool o2p_lmp_mode_unbiases_the_cell(uint8_t modecn)
{
    uint8_t op = (uint8_t)(modecn & 0x07u);
    return !(op == 0x03u || op == 0x07u);
}
o2p_lmp_status_t o2p_lmp91000_temp_exit(void);

/* Table 1 (SNAS506I 7.3.1.5) is a 126-row lookup from -40 to +85 C. This is a
 * least-squares fit over its 0..85 C rows, the range this probe measures in:
 *
 *     V(mV) = 1563.42 - 8.2236 * T(C)
 *
 * whose slope is exactly the -8.2 mV/C the datasheet quotes as Sensitivity,
 * and which reproduces every row in that span to within 0.41 C.
 *
 * The fit is deliberately taken over 0..85 rather than the full table. This
 * register exists to measure the AFE while the ring heater is running, so
 * DIFFERENTIAL accuracy across 20..85 C is what it is for, and a fit over the
 * whole -40..85 span would trade that away to serve temperatures this probe
 * does not operate the heater at. The cost is at the cold end: extrapolating
 * below 0 C reaches 2.12 C of error at -40 - checked against every one of
 * Table 1's 126 rows, not asserted. That is still inside the sensor's own +/-3
 * C Temperature Error, so one line covers the specified window, but a caller
 * wanting absolute accuracy in the cold should not read this as 0.41 C.
 *
 * Returns false - and writes nothing - outside the specified VOUT window. */
static inline bool o2p_lmp_temp_c100_from_mv(uint16_t mv, int16_t *out_c100)
{
    if (out_c100 == NULL) {
        return false;
    }
    if (mv > O2P_LMP_TEMP_MV_MAX || mv < O2P_LMP_TEMP_MV_MIN) {
        return false;
    }
    /* c100 = (1563.42 - mv) * 100 / 8.2236, in integer arithmetic. */
    int64_t num = (int64_t)(156342 - (int32_t)mv * 100) * 10000;
    int32_t c100 = (int32_t)(num / 82236);
    if (c100 < -32767 || c100 > 32767) {
        return false;
    }
    *out_c100 = (int16_t)c100;
    return true;
}

void o2p_lmp91000_gpio_init(void);

#endif /* O2P_LMP91000_H */
