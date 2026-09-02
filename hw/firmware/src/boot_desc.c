#include "boot_desc.h"

#include "modbus_pdu.h"   /* o2p_mb_crc16 */

#include <string.h>

#ifndef O2P_HOST_TEST
#include "flash_hal.h"
#endif

uint16_t o2p_desc_crc(const o2p_desc_t *d)
{
    o2p_desc_t t = *d;
    t.crc16 = 0u;
    return o2p_mb_crc16((const uint8_t *)&t, sizeof(t));
}

bool o2p_desc_record_valid(const o2p_desc_t *d)
{
    if (d == NULL) {
        return false;
    }
    if (d->magic != O2P_DESC_MAGIC) {
        return false;
    }
    /* An unknown layout version is refused rather than read optimistically.
     * A future field added in front of `flags` would otherwise be read as
     * flags, and the flag that matters says "install this image". */
    if (d->layout_version != O2P_DESC_LAYOUT_VERSION) {
        return false;
    }
    if (d->crc16 != o2p_desc_crc(d)) {
        return false;
    }
    /* A record can be structurally perfect and still describe an image that
     * cannot exist. Refuse it here, once, rather than in each of the three
     * places that act on the lengths. */
    if (d->staged_len > O2P_STAGE_BYTES || d->installed_len > O2P_APP_BYTES) {
        return false;
    }
    if ((d->flags & O2P_DESC_F_STAGED) != 0u &&
        (d->staged_len < O2P_IMAGE_MIN_BYTES ||
         (d->staged_len % O2P_IMAGE_ALIGN) != 0u)) {
        return false;
    }
    return true;
}

int o2p_desc_pick(const o2p_desc_t *a, bool ok_a,
                  const o2p_desc_t *b, bool ok_b)
{
    if (!ok_a && !ok_b) {
        return -1;
    }
    if (ok_a && !ok_b) {
        return 0;
    }
    if (ok_b && !ok_a) {
        return 1;
    }
    /* Signed difference, so the choice stays correct across a 32-bit wrap.
     * Equal sequences mean two records claiming to be the same generation:
     * that is not a tie to be broken, it is a sign that one of them is a
     * ghost, so prefer B - the page that would have been written second by
     * o2p_desc_store's alternation - and let the next store overwrite A. */
    return ((int32_t)(a->sequence - b->sequence) > 0) ? 0 : 1;
}

void o2p_desc_init(o2p_desc_t *d)
{
    memset(d, 0, sizeof(*d));
    d->magic = O2P_DESC_MAGIC;
    d->layout_version = O2P_DESC_LAYOUT_VERSION;
    d->crc16 = o2p_desc_crc(d);
}

#ifndef O2P_HOST_TEST

/* Which page the live record was read from, so a store goes to the other one.
 * Initialised to B so the very first store lands on A. */
static uint8_t s_live_page = O2P_DESC_PAGE_B;
static uint32_t s_sequence;

static bool read_page(uint8_t page, o2p_desc_t *out)
{
    memcpy(out, (const void *)O2P_PAGE_ADDR(page), sizeof(*out));
    return o2p_desc_record_valid(out);
}

bool o2p_desc_load(o2p_desc_t *out)
{
    o2p_desc_t a, b;
    bool ok_a = read_page(O2P_DESC_PAGE_A, &a);
    bool ok_b = read_page(O2P_DESC_PAGE_B, &b);

    int which = o2p_desc_pick(&a, ok_a, &b, ok_b);
    if (which < 0) {
        o2p_desc_init(out);
        s_sequence = 0u;
        s_live_page = O2P_DESC_PAGE_B;
        return false;
    }
    *out = (which == 0) ? a : b;
    s_live_page = (which == 0) ? O2P_DESC_PAGE_A : O2P_DESC_PAGE_B;
    s_sequence = out->sequence;
    return true;
}

bool o2p_desc_store(const o2p_desc_t *d)
{
    const uint8_t target = (s_live_page == O2P_DESC_PAGE_A) ? O2P_DESC_PAGE_B
                                                            : O2P_DESC_PAGE_A;
    o2p_desc_t r = *d;
    r.magic = O2P_DESC_MAGIC;
    r.layout_version = O2P_DESC_LAYOUT_VERSION;
    r.sequence = s_sequence + 1u;
    r.crc16 = 0u;
    r.crc16 = o2p_desc_crc(&r);

    _Static_assert(sizeof(o2p_desc_t) == O2P_DESC_BYTES,
                   "descriptor size changed - it is programmed as whole "
                   "doublewords and stored in a fixed-size page");
    _Static_assert((O2P_DESC_BYTES % O2P_IMAGE_ALIGN) == 0u,
                   "descriptor must be a whole number of doublewords");

    if (!o2p_flash_erase_page(target)) {
        return false;
    }
    if (!o2p_flash_program(O2P_PAGE_ADDR(target), &r, sizeof(r))) {
        return false;
    }
    /* Verify through the LOAD path, not by comparing bytes: a record that was
     * written perfectly but that o2p_desc_record_valid would reject is a
     * failure now, while the other page still holds the previous record. */
    o2p_desc_t back;
    if (!read_page(target, &back) || back.sequence != r.sequence ||
        memcmp(&back, &r, sizeof(back)) != 0) {
        return false;
    }
    s_live_page = target;
    s_sequence = r.sequence;
    return true;
}

#endif /* O2P_HOST_TEST */
