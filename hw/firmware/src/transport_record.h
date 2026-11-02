/* Where this probe is on the bus - the one fact the bootloader may never lose.
 *
 * THE FAILURE THIS EXISTS TO PREVENT. The loader reads the address, baud and
 * parity out of the application's configuration record, and it is the one
 * image that is never rewritten in the field (loader_main.c). So the loader
 * on a potted probe was compiled against whatever CONFIG_LAYOUT_VERSION was
 * current the day it was flashed, while the application's record marches on:
 * version 8 landed on 2026-09-08. read_serial() accepted only an exact
 * version match, so the moment the application's layout moved past the
 * loader's, the loader stopped being able to read the record at all and fell
 * back to address 3 / 9600 / even parity - silently, and precisely on the
 * probe whose application was already broken enough to need the loader.
 * A probe an operator had moved off the default transport was then
 * unreachable through the only door it had left. Found by review 2026-09-08.
 *
 * THE FIX IS A SECOND RECORD, not a cleverer parse of the first one. The
 * configuration record cannot be parsed by an older loader for a reason that
 * no amount of care removes: its CRC sits immediately after the configuration
 * struct, so its OFFSET moves every time the struct grows, and a loader that
 * does not know the new size cannot find the checksum that would tell it
 * whether the bytes are trustworthy. Reading fields out of a record you
 * cannot verify is worse than defaulting.
 *
 * So the three transport fields are written a second time, into their own
 * 16-byte record with its own magic, its own version and its own CRC at a
 * FIXED offset in the same page. The loader reads that and never needs to
 * know what the configuration looks like.
 *
 * THIS LAYOUT IS FROZEN. Not "stable", not "append-only" - frozen. Every byte
 * of it is addressed by images that will still be running years after this
 * file changes, and there is no mechanism by which they can be told. If a
 * future firmware needs to hand the loader something else, it puts a SECOND
 * block at a different fixed offset in the page (there are ~2 KiB spare) and
 * leaves this one exactly as it is. Do not grow it, do not reorder it, do not
 * move the CRC, and do not extend the CRC's coverage.
 *
 * WHAT IS DELIBERATELY NOT HERE: any judgement about what the codes MEAN. The
 * record carries three bytes; whether baud code 4 is a baud rate this build
 * knows is the caller's business, and keeping it so is what lets a new baud
 * code be added without touching a frozen file.
 */
#ifndef O2P_TRANSPORT_RECORD_H
#define O2P_TRANSPORT_RECORD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "modbus_pdu.h"   /* o2p_mb_crc16 */

#define O2P_TRANSPORT_MAGIC   0x4F325054u   /* "O2PT" */
#define O2P_TRANSPORT_VERSION 1u

/* Offset within a config page, and size. Immediately after the 64-byte
 * configuration record, double-word aligned because programming on this
 * family is 64-bit. Pinned against CONFIG_RECORD_SIZE and the page size by
 * static asserts in config_flash.h - this header deliberately does not
 * include the flash map, so that the loader can take it without taking the
 * application's world with it. */
#define O2P_TRANSPORT_OFFSET  64u
#define O2P_TRANSPORT_BYTES   16u

typedef struct {
    uint32_t magic;         /* 0  O2P_TRANSPORT_MAGIC */
    /* The sequence of the configuration record written beside it, in the same
     * erase. It is here so a loader can tell a fresh transport record from a
     * stale one - see o2p_transport_best(). */
    uint32_t sequence;      /* 4  */
    uint8_t  version;       /* 8  O2P_TRANSPORT_VERSION */
    uint8_t  slave_addr;    /* 9  */
    uint8_t  baud_code;     /* 10 */
    uint8_t  parity_code;   /* 11 */
    uint16_t crc;           /* 12 CRC-16/MODBUS over bytes 0..11 */
    uint8_t  reserved[2];   /* 14 written zero; NOT covered by the CRC */
} o2p_transport_record_t;

_Static_assert(sizeof(o2p_transport_record_t) == O2P_TRANSPORT_BYTES,
               "the transport record is frozen at 16 bytes");
_Static_assert(offsetof(o2p_transport_record_t, magic) == 0u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, sequence) == 4u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, version) == 8u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, slave_addr) == 9u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, baud_code) == 10u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, parity_code) == 11u, "frozen layout");
_Static_assert(offsetof(o2p_transport_record_t, crc) == 12u, "frozen layout");
_Static_assert(O2P_TRANSPORT_BYTES % 8u == 0u,
               "must be a whole number of double words for 64-bit flash "
               "programming");

static inline uint16_t o2p_transport_crc(const o2p_transport_record_t *r)
{
    return o2p_mb_crc16((const uint8_t *)r,
                        offsetof(o2p_transport_record_t, crc));
}

/* Fill in magic, version and CRC around three transport bytes. */
static inline void o2p_transport_build(o2p_transport_record_t *r,
                                       uint32_t sequence, uint8_t slave_addr,
                                       uint8_t baud_code, uint8_t parity_code)
{
    memset(r, 0, sizeof(*r));
    r->magic = O2P_TRANSPORT_MAGIC;
    r->sequence = sequence;
    r->version = (uint8_t)O2P_TRANSPORT_VERSION;
    r->slave_addr = slave_addr;
    r->baud_code = baud_code;
    r->parity_code = parity_code;
    r->crc = o2p_transport_crc(r);
}

/* Structurally sound? Says nothing about whether the three codes are ones
 * this build knows - see the header note. */
static inline bool o2p_transport_record_ok(const o2p_transport_record_t *r)
{
    if (r->magic != O2P_TRANSPORT_MAGIC) {
        return false;
    }
    /* An UNKNOWN version is refused, and that is the frozen layout doing its
     * job rather than the bug this file exists to fix repeating itself. A
     * version word that is not 1 means the bytes behind it are not the ones
     * described here, so reading slave_addr out of them would be a guess.
     * The rule above - a future need gets a second block, never a version
     * bump of this one - is what keeps this branch unreachable. */
    if (r->version != (uint8_t)O2P_TRANSPORT_VERSION) {
        return false;
    }
    o2p_transport_record_t t = *r;
    const uint16_t want = t.crc;
    t.crc = 0u;
    return o2p_transport_crc(&t) == want;
}

/* Pick the newer of the two pages' transport records. Returns false when
 * neither is sound, in which case `out` is untouched.
 *
 * Sequence, not page order, decides - the pages are written alternately, so
 * which one is current is not a property of its address. The comparison is
 * signed on the difference so it survives the sequence counter wrapping,
 * which is the same rule config_select.h applies to the configuration
 * records themselves. */
static inline bool o2p_transport_best(const o2p_transport_record_t *a,
                                      const o2p_transport_record_t *b,
                                      o2p_transport_record_t *out)
{
    const bool ok_a = o2p_transport_record_ok(a);
    const bool ok_b = o2p_transport_record_ok(b);
    if (!ok_a && !ok_b) {
        return false;
    }
    if (ok_a && ok_b) {
        *out = ((int32_t)(a->sequence - b->sequence) >= 0) ? *a : *b;
    } else {
        *out = ok_a ? *a : *b;
    }
    return true;
}

/* The three bytes, once a source has been chosen. */
typedef struct {
    uint8_t slave_addr;
    uint8_t baud_code;
    uint8_t parity_code;
} o2p_transport_t;

/* THE DECISION the bootloader makes at every reset, kept here as a pure
 * function so the host tests exercise the shipped rule rather than a
 * restatement of it - the same reason config_select.h exists.
 *
 * `cfg_ok`/`cfg_seq`/`cfg_tr` describe the newest CONFIGURATION record the
 * caller was able to verify, which for an older loader facing a newer layout
 * is none at all. Returns false when there is no trustworthy source and the
 * caller must fall back to the default identity.
 *
 * The rule: the frozen block wins, UNLESS a readable configuration record is
 * strictly newer than it. That exception is not symmetry for its own sake -
 * it covers a downgrade, where an application built before the frozen block
 * existed commits a configuration and leaves a valid but stale block behind
 * on the other page. Without it, an operator who moved the address on the old
 * firmware would find the loader still answering at the old one.
 */
static inline bool o2p_transport_select(const o2p_transport_record_t *a,
                                        const o2p_transport_record_t *b,
                                        bool cfg_ok, uint32_t cfg_seq,
                                        const o2p_transport_t *cfg_tr,
                                        o2p_transport_t *out)
{
    o2p_transport_record_t best;
    const bool have = o2p_transport_best(a, b, &best);
    if (have && !(cfg_ok && (int32_t)(cfg_seq - best.sequence) > 0)) {
        out->slave_addr = best.slave_addr;
        out->baud_code = best.baud_code;
        out->parity_code = best.parity_code;
        return true;
    }
    if (cfg_ok) {
        *out = *cfg_tr;
        return true;
    }
    return false;
}

#endif /* O2P_TRANSPORT_RECORD_H */
