/* Revert-on-silence for the three settings that decide whether this probe can
 * be reached at all.
 *
 * SLAVE_ADDR, BAUD_CODE and PARITY_CODE are the "reachability" triplet
 * (config_migrate.h uses the same word for the same three). Every other
 * register in the config block is wrong-answer-shaped when it is set wrong: a
 * bad RH setpoint makes a bad heater, and you can see it and fix it. These
 * three are different in kind. Set one of them to something the master cannot
 * follow and THE MASTER CANNOT FOLLOW - there is no channel left to notice the
 * mistake through, let alone undo it. A probe potted into a compost pile on a
 * lead with no way to cut its supply is then off the bus until something else
 * resets it.
 *
 * So a change to any of the three is applied ON PROBATION. The new settings go
 * live immediately - they have to, that is what was asked for - but the old
 * ones are kept, and if no valid frame arrives at the new settings within
 * O2P_SERIAL_PROBATION_MS the transport is put back the way it was.
 *
 * What counts as proof is deliberately narrow: one well-formed frame addressed
 * to this probe's OWN unicast address, at the new settings. Not a broadcast,
 * which every device on the cable hears and which therefore proves nothing
 * about this one; and not the 253 discovery alias, which is answered at any
 * address and so would confirm a SLAVE_ADDR change that nobody can actually
 * reach. The master proving it can still talk to us is the entire signal.
 *
 * WHY A TIMER AND NOT A COMMIT. It would be simpler to say "a serial change is
 * provisional until COMMIT persists it". It would also be wrong in the one
 * direction that matters: the commit would have to arrive over the link whose
 * viability is exactly what is in question, so a master that CANNOT reach the
 * probe at the new settings can never retract them either. The timer is the
 * only mechanism here that does not depend on the link working.
 *
 * Nothing in this file touches hardware or a global - values and one register
 * map in, decision out - so main.c's serial handling is testable on the host,
 * which is where this file's tests live (test/test_logic/test_main.c). What
 * remains untestable there is the two lines main.c keeps: arming before the
 * transport switch, and calling o2p_modbus_reconfigure() when apply() says
 * to.
 */
#ifndef O2P_SERIAL_PROBATION_H
#define O2P_SERIAL_PROBATION_H

#include <stdbool.h>
#include <stdint.h>

#include "regmap.h"

/* How long a new setting has to prove itself.
 *
 * The floor is a master's round trip: tools/o2p_update.py retimes its line and
 * reads BAUD_CODE back inside about half a second, and a person driving it by
 * hand from a second terminal needs a few. The ceiling is how long a probe may
 * sit unreachable after a mistake, which on a buried probe is the whole cost
 * being defended against. Ten seconds is far above the first and far below
 * anything that would matter for the second.
 *
 * It is NOT derived from the Modbus response deadline: that bounds one
 * exchange, this bounds an operator noticing and a tool re-timing. */
#define O2P_SERIAL_PROBATION_MS 10000u

typedef struct {
    bool armed;
    uint32_t armed_ms;
    /* The frame counter as it stood when the new settings went live. Compared
     * for INEQUALITY, not "greater than": the counter is free to wrap, and a
     * wrap must not read as "no frames since". */
    uint32_t frames_at_arm;
    /* The settings to go back to. Captured from the config as it was BEFORE
     * the write, not from the config as it is now. */
    uint8_t prev_slave_addr;
    uint8_t prev_baud_code;
    uint8_t prev_parity_code;
} o2p_serial_probation_t;

typedef enum {
    O2P_SP_WAIT = 0,     /* nothing to decide, or still deciding */
    O2P_SP_CONFIRMED,    /* the master reached us at the new settings */
    O2P_SP_REVERT,       /* it did not: put prev_* back */
} o2p_sp_outcome_t;

/* Start (or extend) a probation.
 *
 * A SECOND change while one is already on probation does NOT overwrite prev_*.
 * That is the whole point of this branch: the settings recorded first are the
 * last ones known to have carried a frame, and the intermediate ones are by
 * definition unproven. Reverting to an unproven setting is not a fallback, it
 * is a second guess - and two bad writes in a row is exactly the sequence a
 * confused operator produces. The deadline and the frame mark DO move, because
 * the thing now being judged is the newest setting.
 */
static inline void o2p_sp_arm(o2p_serial_probation_t *p, uint32_t now_ms,
                              uint32_t frames, uint8_t prev_addr,
                              uint8_t prev_baud, uint8_t prev_parity)
{
    if (!p->armed) {
        p->prev_slave_addr = prev_addr;
        p->prev_baud_code = prev_baud;
        p->prev_parity_code = prev_parity;
    }
    p->armed = true;
    p->armed_ms = now_ms;
    p->frames_at_arm = frames;
}

/* Disarm without reverting. For the caller that has decided the question by
 * other means - a config reload from flash, say - and must not leave a stale
 * deadline pointing at settings that no longer exist. */
static inline void o2p_sp_disarm(o2p_serial_probation_t *p)
{
    p->armed = false;
}

/* Poll. Call every main-loop pass; `frames` is the count of valid unicast
 * frames served since boot.
 *
 * Returns CONFIRMED or REVERT exactly ONCE per probation - both disarm - so a
 * caller may act on the outcome without tracking edges itself. */
static inline o2p_sp_outcome_t o2p_sp_service(o2p_serial_probation_t *p,
                                              uint32_t now_ms, uint32_t frames)
{
    if (!p->armed) {
        return O2P_SP_WAIT;
    }
    if (frames != p->frames_at_arm) {
        p->armed = false;
        return O2P_SP_CONFIRMED;
    }
    /* Unsigned difference, so the millisecond counter may wrap under a
     * probation without the deadline becoming unreachable. */
    if ((uint32_t)(now_ms - p->armed_ms) >= O2P_SERIAL_PROBATION_MS) {
        p->armed = false;
        return O2P_SP_REVERT;
    }
    return O2P_SP_WAIT;
}

/* Apply an outcome to the register map. Returns true if the caller must
 * reconfigure the transport, i.e. if the live serial settings just changed.
 *
 * Here rather than in main.c so that it has tests. main.c cannot be built on
 * the host - it reaches CMSIS through every driver it calls - and this is the
 * part of the mechanism most worth testing: which fields go back, which
 * commits die with them, and the fact that the fallback is the caller's
 * stored triplet and not anything read out of the config being replaced.
 */
static inline bool o2p_sp_apply(const o2p_serial_probation_t *p,
                                o2p_sp_outcome_t out, o2p_regmap_t *rm)
{
    if (out == O2P_SP_WAIT) {
        return false;
    }

    rm->serial_probation = false;

    if (out == O2P_SP_CONFIRMED) {
        if (rm->commit_after_serial) {
            rm->commit_after_serial = false;
            rm->commit_pending = true;
        }
        return false;
    }

    /* Only the three reachability fields go back. Anything else the same
     * frame set is a measurement or a control parameter, and it was accepted
     * on its own terms - the master's inability to reach the new ADDRESS says
     * nothing about whether it meant the new RH setpoint. Reverting those too
     * would make one mistyped baud code silently discard a batch of
     * deliberate settings. */
    rm->cfg.slave_addr = p->prev_slave_addr;
    rm->cfg.baud_code = p->prev_baud_code;
    rm->cfg.parity_code = p->prev_parity_code;

    /* EVERY outstanding commit fails, whichever queue it is sitting in. The
     * master asked for settings it then could not reach to be made permanent,
     * and that request is refused however it was phrased.
     *
     * commit_after_cal has to be named explicitly. A frame that asked for a
     * calibration AND a serial change AND a commit puts the commit in that
     * queue, and finish_o2() can run long after the probation resolved: by
     * then serial_probation is false, the gate lets the commit straight
     * through, and the master is told OK for a configuration whose serial
     * change was silently undone. The same event through the non-cal path
     * says FAILED. Two answers to one question is worse than the wrong one.
     *
     * The calibration itself is untouched and stays in RAM; a master that
     * wants it persisted can COMMIT again, at settings that now work.
     *
     * NOTE: this is the same O2P_CMD_FAILED a worn flash page produces. The
     * fault word has no spare bit and a new diagnostic register would move
     * the block the ChirpStack decoder parses, so the two are not
     * distinguishable on the bus today - see FIRMWARE.md. What separates them
     * in practice is that this one is read at the OLD settings. */
    if (rm->commit_after_serial || rm->commit_after_cal) {
        rm->commit_after_serial = false;
        rm->commit_after_cal = false;
        o2p_regmap_set_commit_result(rm, O2P_CMD_FAILED);
    }
    return true;
}

#endif /* O2P_SERIAL_PROBATION_H */
