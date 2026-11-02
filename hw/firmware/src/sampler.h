/* The analog channels of the oxygen signal chain, named by what they MEASURE
 * rather than by where they happen to be converted.
 *
 * WHY THIS EXISTS. Rev A converts these on an ADS1119 over I2C; Rev B deleted
 * that part and converts them on the STM32G071's own SAR. Before this header,
 * main.c's phase machine named its channels `O2P_ADS_MUX_AIN0_AGND` and so on
 * - so the state machine that decides what the probe measures was written in
 * the register encoding of one specific converter, on one specific revision.
 * Porting it meant editing every phase, and a wrong edit produces a build that
 * runs and reads the wrong pin.
 *
 * The names below are the durable facts. `O2P_CH_AFE` is the oxygen signal
 * whether it arrives on the ADS1119's AIN0 or the MCU's ADC_IN9; which pin
 * that is, is a property of the board and belongs in the table in sampler.c
 * next to the other per-revision hardware facts.
 *
 * WHAT IS DELIBERATELY *NOT* HIDDEN. The two converters are not
 * interchangeable and this header does not pretend otherwise:
 *
 *   - Their code domains differ. The ADS1119 is signed 16-bit with full scale
 *     +/-VREF; the MCU's SAR is unsigned 12-bit with full scale VREF+. So each
 *     revision keeps its OWN code-to-microvolts conversion, and a code from
 *     one is meaningless to the other. There is no common "raw" integer here,
 *     because inventing one would silently rescale oxygen.
 *   - Rev A has channels Rev B does not, and the reverse. O2P_CH_VREF is the
 *     47k/47k sense tap on ADS AIN1, which Rev B deleted along with R34/R35 -
 *     Rev B's ADC reference IS the REF3425, so there is nothing to measure it
 *     against on-chip except VREFINT, which is 8x worse. O2P_CH_OFFSET is the
 *     ADS1119's shorted-input self-check and has no MCU equivalent at all.
 *     Those are marked unavailable per revision rather than faked, because a
 *     fabricated reference reading is exactly the failure that cost five hours
 *     on 2026-09-11.
 */
#ifndef O2P_SAMPLER_H
#define O2P_SAMPLER_H

#include <stdbool.h>
#include <stdint.h>

#include "hw_caps.h"

typedef enum {
    O2P_CH_VREF = 0,   /* the 2.500 V reference, via its sense tap (Rev A) */
    O2P_CH_AFE,        /* AFE_VOUT - the oxygen signal itself */
    O2P_CH_WE,         /* WE_BUF - working-electrode bias telemetry */
    O2P_CH_RE,         /* RE_BUF - reference-electrode bias telemetry */
    O2P_CH_OFFSET,     /* converter self-check, shorted input (Rev A) */
    O2P_CH_COUNT
} o2p_channel_t;

/* False where this revision's hardware cannot produce the channel at all.
 *
 * Callers must branch on this rather than converting and hoping: an
 * unavailable channel has no reading, not a zero reading. */
bool o2p_sampler_channel_available(o2p_channel_t ch);

/* Human-readable channel name, for diagnostics and for the fault log. Stable
 * across revisions - that is the point of it. */
const char *o2p_sampler_channel_name(o2p_channel_t ch);

#endif /* O2P_SAMPLER_H */
