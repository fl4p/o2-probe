/* Host tests for the poke blocks: the WRITE counterpart of the memory peek
 * (regmap.h, FW_VERSION 0x0012, Fab 2026-09-11: "the equivalent write
 * command of the peek").
 *
 * Its own suite, so it runs against regmap.c without test_logic. The
 * discipline follows the peek suites' guard-review shape: every refusal is
 * checked by its status code AND by a store count that proves nothing was
 * written, the accepted trigger shapes are enumerated exactly, and the
 * span policy (poke admits what the peek can read back, nothing more) is
 * pinned at every boundary - SHARED, the stack, the .data/.bss gap, the
 * span tail, and the regions a READ may touch but a WRITE may not: the
 * run slot, the UID, the flash-size word, and SCB AIRCR, the register a
 * poke must never be able to reach.
 *
 *   pio test -e native -f test_peek_write
 */
#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "regmap.h"

#if !O2P_DEBUG_ENABLE
/* The poke blocks are compiled out of a nodebug build (env:native_nodebug,
 * env:o2probe_nodebug), so this suite has nothing to exercise there. It
 * runs zero cases and passes; the compile-out itself is proven by the
 * nodebug BUILD of regmap.c, and test_main.c gates its own peek tests the
 * same way. */
void setUp(void) {}
void tearDown(void) {}
int main(void) { return 0; }
#else

/* ---- the fake the hooks back ----
 *
 * One 36 KiB SRAM image at 0x20000000, shared by the read hook and the
 * store hook, so a poke followed by a peek on the same address proves the
 * poke landed where the peek looks - which is the symmetry the poke's span
 * policy exists for. The store hook counts every store, which is how a
 * test proves a REFUSED poke wrote nothing rather than inferring it from
 * a status code. */

#define SRAM_FIRST 0x20000000u
#define SRAM_LAST  0x20008FFCu

static uint32_t fake_sram[(SRAM_LAST - SRAM_FIRST) / 4u + 1u];
static unsigned store_count;

static o2p_regmap_t rm;

static uint32_t fake_read(uint32_t a)
{
    TEST_ASSERT_TRUE_MESSAGE(a >= SRAM_FIRST && a <= SRAM_LAST && (a & 3u) == 0u,
                             "the peek path dereferenced outside SRAM");
    return fake_sram[(a - SRAM_FIRST) >> 2];
}

/* For the overlap tests: the poke-space address the payload buffer should
 * be treated as living at, or 0 for "no overlap possible". When set, a
 * store that lands in the payload's mapped range also writes the REAL
 * payload buffer, because in poke-space that range IS the payload - which
 * is the only way the host can reproduce the target's hazard of a store
 * clobbering a payload word that has not been read yet (N1's write side). */
static uint32_t payload_map_addr;
static void fake_store(uint32_t a, uint32_t v)
{
    TEST_ASSERT_TRUE_MESSAGE(a >= SRAM_FIRST && a <= SRAM_LAST && (a & 3u) == 0u,
                             "the poke path stored outside SRAM");
    fake_sram[(a - SRAM_FIRST) >> 2] = v;
    store_count++;
    if (payload_map_addr != 0u &&
        a >= payload_map_addr &&
        a < payload_map_addr + 4u * O2P_PEEKW_WORDS_MAX) {
        rm.pokew_words[(a - payload_map_addr) >> 2] = v;
    }
}

static uint32_t payload_src_addr(const uint32_t *src)
{
    /* Only the wide block's payload is mapped; anything else (the mailbox
     * buffer) reports no overlap, as the default would. */
    if (src == rm.pokew_words) {
        return payload_map_addr;
    }
    return 0u;
}

/* Spans: the linker's .data/.bss bounds as the parity gate reads them.
 * Default is abutting sections (the union path); the gap tests move .bss. */
static void set_spans(uint32_t sdata, uint32_t edata, uint32_t sbss, uint32_t ebss)
{
    o2p_peek_host_sdata = sdata;
    o2p_peek_host_edata = edata;
    o2p_peek_host_sbss = sbss;
    o2p_peek_host_ebss = ebss;
}

void setUp(void)
{
    memset(&rm, 0, sizeof rm);
    o2p_regmap_init(&rm);
    memset(fake_sram, 0, sizeof fake_sram);
    store_count = 0u;
    payload_map_addr = 0u;
    o2p_peek_host_read = fake_read;
    o2p_peek_host_store = fake_store;
    o2p_peek_host_src_addr = payload_src_addr;
    o2p_peek_host_dst_addr = NULL;
    /* Factory option byte: parity check disabled, so the READ side is not
     * span-gated and the poke/peek symmetry tests exercise the poke's own
     * policy rather than the parity gate's. */
    o2p_peek_host_optr = 0xFFFFFFFFu;
    set_spans(0x20000010u, 0x20000100u, 0x20000100u, 0x20001000u);
}

void tearDown(void) {}

/* Trigger helpers: one FC16 at the block base, payload assembled as
 * hi/lo register pairs. */
static uint8_t poke_mb(uint32_t target, uint16_t words, const uint32_t *payload)
{
    uint16_t in[3u + 2u * 4u];
    in[0] = (uint16_t)(target >> 16);
    in[1] = (uint16_t)target;
    in[2] = words;
    for (unsigned w = 0; w < words; w++) {
        in[3u + 2u * w] = (uint16_t)(payload[w] >> 16);
        in[4u + 2u * w] = (uint16_t)payload[w];
    }
    return o2p_regmap_write(&rm, O2P_REG_POKE_BASE,
                            (uint16_t)(3u + 2u * words), in);
}

static uint16_t rd(uint16_t reg)
{
    uint16_t out = 0;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_read(&rm, reg, 1u, &out));
    return out;
}

static uint32_t rd_poke_word(unsigned i)
{
    return ((uint32_t)rd((uint16_t)(O2P_REG_POKE_W0_HI + 2u * i)) << 16) |
           (uint32_t)rd((uint16_t)(O2P_REG_POKE_W0_LO + 2u * i));
}

/* ------------------------------------------------------------------ */

void test_a_four_word_poke_lands_in_memory_and_holds(void)
{
    const uint32_t payload[4] = {0x11223344u, 0xDEADBEEFu, 0u, 0x0000FFFFu};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000100u, 4u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(4u, store_count);
    for (unsigned i = 0; i < 4u; i++) {
        TEST_ASSERT_EQUAL_UINT32(payload[i], fake_sram[(0x20000100u - SRAM_FIRST) / 4u + i]);
    }
    /* The held state echoes the request: address, words, payload, status.
     * 0x20000100's register halves are 0x2000 and 0x0100. */
    TEST_ASSERT_EQUAL_UINT16(0x2000, rd(O2P_REG_POKE_ADDR_HI));
    TEST_ASSERT_EQUAL_UINT16(0x0100, rd(O2P_REG_POKE_ADDR_LO));
    TEST_ASSERT_EQUAL_UINT16(4u, rd(O2P_REG_POKE_WORDS));
    for (unsigned i = 0; i < 4u; i++) {
        TEST_ASSERT_EQUAL_UINT32(payload[i], rd_poke_word(i));
    }
}

void test_every_accepted_mailbox_count_5_7_9_11(void)
{
    const uint32_t payload[4] = {0xA0A00000u, 0xA1A10001u, 0xA2A20002u, 0xA3A30003u};
    for (uint16_t words = 1u; words <= 4u; words++) {
        store_count = 0u;
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, poke_mb(0x20000100u, words, payload),
                                        "accepted count refused");
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(O2P_POKE_OK, rm.poke_status,
                                         "accepted count not OK");
        TEST_ASSERT_EQUAL_UINT_MESSAGE(words, store_count,
                                       "stored word count disagrees with the trigger");
    }
}

void test_wrong_shapes_are_exception_03_and_change_nothing(void)
{
    const uint32_t payload[4] = {1u, 2u, 3u, 4u};
    /* A good poke first, so "changes nothing" is observable. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000100u, 4u, payload));
    uint16_t held[O2P_REG_POKE_COUNT];
    for (unsigned i = 0; i < O2P_REG_POKE_COUNT; i++) {
        held[i] = rd((uint16_t)(O2P_REG_POKE_BASE + i));
    }

    static const uint16_t bad_counts[] = {2u, 3u, 4u, 6u, 8u, 10u, 12u};
    for (unsigned c = 0; c < sizeof bad_counts / sizeof bad_counts[0]; c++) {
        uint16_t in[13] = {0x0200, 0x0100, 4u, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
        char msg[48];
        snprintf(msg, sizeof msg, "in-block count %u accepted", bad_counts[c]);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(
            O2P_MB_EX_ILLEGAL_VALUE,
            o2p_regmap_write(&rm, O2P_REG_POKE_BASE, bad_counts[c], in), msg);
    }
    /* A count that runs OFF the block's end (13 registers from 0x0198)
     * leaves the register map entirely, so the dispatch answers exception
     * 02 - illegal ADDRESS - before any block sees it. That is the map's
     * semantics for every off-end frame, not a poke decision, and nothing
     * is written either way. */
    {
        uint16_t in[13] = {0x0200, 0x0100, 4u, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
        TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_ADDRESS,
                                o2p_regmap_write(&rm, O2P_REG_POKE_BASE, 13u, in));
    }
    /* A frame starting one register into the block. */
    {
        uint16_t in[5] = {0x0100, 4u, 1u, 2u, 3u};
        TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                                o2p_regmap_write(&rm, O2P_REG_POKE_BASE + 1u, 5u, in));
    }
    /* A words/count disagreement: words 4 with a 4-word frame's count. */
    {
        uint16_t in[5] = {0x0200, 0x0100, 4u, 0, 0};
        TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                                o2p_regmap_write(&rm, O2P_REG_POKE_BASE, 5u, in));
    }
    /* Nothing changed: same held registers, same status, no stores. */
    for (unsigned i = 0; i < O2P_REG_POKE_COUNT; i++) {
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(held[i], rd((uint16_t)(O2P_REG_POKE_BASE + i)),
                                         "a refused shape changed held state");
    }
    TEST_ASSERT_EQUAL_UINT(4u, store_count);
}

void test_an_unaligned_target_is_refused_without_storing(void)
{
    const uint32_t payload[2] = {0x55555555u, 0x66666666u};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000102u, 2u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_ALIGN, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
    /* The refused request is still HELD, per the block contract: the
     * readback shows what was attempted while the status says it never
     * landed. */
    TEST_ASSERT_EQUAL_UINT16(2u, rd(O2P_REG_POKE_WORDS));
    TEST_ASSERT_EQUAL_UINT32(0x55555555u, rd_poke_word(0));
}

void test_flash_is_refused_even_though_the_peek_reads_it(void)
{
    /* The run slot is inside the peek's readable regions; the poke must
     * still refuse it - a runtime flash write tears pages (bad ECC, NMI,
     * a hung probe), which is the peek's own N4 reasoning. */
    const uint32_t payload[1] = {0x0BAD0BADu};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x08004000u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
}

void test_peripherals_are_refused_including_the_reset_register(void)
{
    /* SCB AIRCR is the one peripheral register a poke would be most
     * "useful" at: SYSRESETREQ is an instant MCU reset, the thing the
     * 2026-09-11 bench session wanted. It is refused on purpose - a
     * reset path the firmware does not own, competing with the ones it
     * does, is not an accident this block gets to have. */
    const uint32_t payload[2] = {0x05FA0004u, 0x05FA0004u};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0xE000ED0Cu, 2u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x40000000u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
}

void test_the_uid_and_flash_size_words_are_refused(void)
{
    const uint32_t payload[3] = {1u, 2u, 3u};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x1FFF7590u, 3u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x1FFF75E0u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
}

void test_shared_the_boot_handoff_is_excluded(void)
{
    /* 0x20000000..0x2000000F is SHARED, below _sdata (0x20000010 in the
     * default spans): the boot hand-off that must survive a warm reset. */
    const uint32_t payload[4] = {0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000000u, 4u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
}

void test_the_stack_and_never_written_sram_are_excluded(void)
{
    const uint32_t payload[1] = {0x1u};
    /* Above _ebss (0x20001000 in the default spans): the stack and the
     * never-written SRAM above it. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20001000u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
    /* The last word the span admits is fine - a tail-boundary check. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000FFCu, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(1u, store_count);
}

void test_a_gap_between_data_and_bss_refuses_bursts_that_cross_it(void)
{
    /* .data 0x20000010..0x20000100, then a gap, then .bss at 0x20000300. */
    set_spans(0x20000010u, 0x20000100u, 0x20000300u, 0x20001000u);
    const uint32_t payload[4] = {0xAu, 0xBu, 0xCu, 0xDu};
    /* Wholly inside .data: fine. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x200000F0u, 4u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.poke_status);
    /* Wholly inside .bss: fine (0x20000300..0x2000030F, inside the
     * 0x20000300 span start). */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000300u, 4u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.poke_status);
    /* Crossing the gap (last .data word into the gap): refused. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x200000FCu, 2u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    /* Inside the gap itself: refused. */
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000200u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(8u, store_count);
}

void test_an_empty_span_refuses_everything_in_sram(void)
{
    /* The degenerate map: nothing was written, so nothing may be poked -
     * the span gate fails closed, like the read-side parity gate does. */
    set_spans(0x20000010u, 0x20000010u, 0x20000010u, 0x20000010u);
    const uint32_t payload[1] = {1u};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000010u, 1u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.poke_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
}

/* ---- the wide block ---- */

static uint8_t poke_wide(uint32_t target, uint16_t words, uint32_t filler)
{
    uint16_t in[3u + 2u * O2P_PEEKW_WORDS_MAX];
    in[0] = (uint16_t)(target >> 16);
    in[1] = (uint16_t)target;
    in[2] = words;
    for (unsigned w = 0; w < words; w++) {
        uint32_t v = filler + w;
        in[3u + 2u * w] = (uint16_t)(v >> 16);
        in[4u + 2u * w] = (uint16_t)v;
    }
    return o2p_regmap_write(&rm, O2P_REG_POKEW_BASE,
                            (uint16_t)(3u + 2u * words), in);
}

static uint32_t rd_pokew_word(unsigned i)
{
    return ((uint32_t)rd((uint16_t)(O2P_REG_POKEW_DATA + 2u * i)) << 16) |
           (uint32_t)rd((uint16_t)(O2P_REG_POKEW_DATA + 2u * i + 1u));
}

void test_the_wide_poke_takes_thirty_words_in_one_trigger(void)
{
    TEST_ASSERT_EQUAL_UINT8(0, poke_wide(0x20000100u, O2P_PEEKW_WORDS_MAX, 0x1000u));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.pokew_status);
    TEST_ASSERT_EQUAL_UINT(O2P_PEEKW_WORDS_MAX, store_count);
    for (unsigned i = 0; i < O2P_PEEKW_WORDS_MAX; i++) {
        TEST_ASSERT_EQUAL_UINT32(0x1000u + i,
                                 fake_sram[(0x20000100u - SRAM_FIRST) / 4u + i]);
        TEST_ASSERT_EQUAL_UINT32(0x1000u + i, rd_pokew_word(i));
    }
    /* SEQ: 0 was "never triggered", the first trigger made it 1. */
    TEST_ASSERT_EQUAL_UINT16(1u, rd(O2P_REG_POKEW_SEQ));
    TEST_ASSERT_EQUAL_UINT8(0, poke_wide(0x20000100u, 1u, 0x9999u));
    TEST_ASSERT_EQUAL_UINT16(2u, rd(O2P_REG_POKEW_SEQ));
}

void test_a_refused_wide_poke_still_counts_and_holds(void)
{
    TEST_ASSERT_EQUAL_UINT8(0, poke_wide(0x20008000u, 2u, 0xAAu));
    /* 0x20008000 is above _ebss: refused, nothing stored. */
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_ERR_RANGE, rm.pokew_status);
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
    /* An executed-but-refused trigger still advanced SEQ and still holds
     * the request, exactly like the wide peek's refused triggers. */
    TEST_ASSERT_EQUAL_UINT16(1u, rd(O2P_REG_POKEW_SEQ));
    TEST_ASSERT_EQUAL_UINT32(0xAAu, rd_pokew_word(0));
    TEST_ASSERT_EQUAL_UINT32(0xABu, rd_pokew_word(1));
}

void test_wide_shapes_outside_3_plus_2_words_are_exception_03(void)
{
    /* words 0 / 31 / 32, and counts that disagree with the word count. */
    static const struct { uint16_t words; uint16_t count; uint8_t ex; } bad[] = {
        {0u, 3u, O2P_MB_EX_ILLEGAL_VALUE},
        {31u, 65u, O2P_MB_EX_ILLEGAL_VALUE},
        /* 67 registers from 0x01B0 runs off the block's end: exception 02,
         * the map's answer for any off-end frame (see the mailbox test). */
        {32u, 67u, O2P_MB_EX_ILLEGAL_ADDRESS},
        {4u, 9u, O2P_MB_EX_ILLEGAL_VALUE},
        {4u, 13u, O2P_MB_EX_ILLEGAL_VALUE},
        {2u, 5u, O2P_MB_EX_ILLEGAL_VALUE},
    };
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        uint16_t in[3u + 2u * O2P_PEEKW_WORDS_MAX] = {0};
        in[0] = 0x2000;
        in[1] = 0x0100;
        in[2] = bad[i].words;
        char msg[64];
        snprintf(msg, sizeof msg, "words %u count %u accepted",
                 bad[i].words, bad[i].count);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(
            bad[i].ex,
            o2p_regmap_write(&rm, O2P_REG_POKEW_BASE, bad[i].count, in), msg);
    }
    /* A frame starting at POKEW_DATA instead of the base. */
    {
        uint16_t in[5] = {0x2000, 0x0200, 1u, 0, 0};
        TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                                o2p_regmap_write(&rm, O2P_REG_POKEW_DATA, 5u, in));
    }
    TEST_ASSERT_EQUAL_UINT(0u, store_count);
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_NONE, rm.pokew_status);
}

void test_poke_then_peek_roundtrip_proves_the_symmetry(void)
{
    /* The span policy's whole point: whatever the poke may write, the
     * peek can read back. Poke three words, then trigger the read-side
     * wide peek at the same address and compare the snapshot. */
    const uint32_t payload[3] = {0x00C0FFEEu, 0x5AC15AC1u, 0x8EA70032u};
    TEST_ASSERT_EQUAL_UINT8(0, poke_mb(0x20000200u, 3u, payload));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.poke_status);

    uint16_t trig[3] = {0x2000, 0x0200, 3u};
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_write(&rm, O2P_REG_PEEKW_BASE, 3u, trig));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peekw_status);
    for (unsigned i = 0; i < 3u; i++) {
        uint16_t out[2];
        TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_read(
            &rm, (uint16_t)(O2P_REG_PEEKW_DATA + 2u * i), 2u, out));
        TEST_ASSERT_EQUAL_UINT32(payload[i],
                                 ((uint32_t)out[0] << 16) | out[1]);
    }
}

/* ---- overlap: the write side of N1 ---- */

static void overlap_case(uint32_t target, uint32_t payload_addr, uint16_t words)
{
    /* The payload is mapped at payload_addr (in poke-space); a store that
     * lands in its range writes the real buffer too, which is the hazard
     * the store order exists for. Fill the payload with distinct values
     * so any clobber is a wrong value, not a plausible one. */
    payload_map_addr = payload_addr;
    for (unsigned i = 0; i < words; i++) {
        rm.pokew_words[i] = 0x70000000u + i;
    }
    /* poke_wide() would overwrite the payload, so drive the write path
     * directly with the pre-filled buffer. */
    uint16_t in[3u + 2u * words];
    in[0] = (uint16_t)(target >> 16);
    in[1] = (uint16_t)target;
    in[2] = words;
    for (unsigned w = 0; w < words; w++) {
        in[3u + 2u * w] = (uint16_t)(rm.pokew_words[w] >> 16);
        in[4u + 2u * w] = (uint16_t)rm.pokew_words[w];
    }
    uint32_t before[O2P_PEEKW_WORDS_MAX];
    memcpy(before, rm.pokew_words, sizeof before);
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_write(&rm, O2P_REG_POKEW_BASE,
                                                (uint16_t)(3u + 2u * words), in));
    TEST_ASSERT_EQUAL_UINT16(O2P_POKE_OK, rm.pokew_status);
    /* Every word that landed must be one of the ORIGINAL payload values -
     * a mid-write clobber would have written a corrupted one here. */
    unsigned landings = 0;
    for (unsigned i = 0; i < words; i++) {
        uint32_t got = fake_sram[(target + 4u * i - SRAM_FIRST) / 4u];
        bool found = false;
        for (unsigned j = 0; j < words; j++) {
            if (got == before[j]) { found = true; break; }
        }
        TEST_ASSERT_TRUE_MESSAGE(found, "an overlapping poke wrote a clobbered value");
        landings++;
    }
    TEST_ASSERT_EQUAL_UINT(words, landings);
}

void test_an_overlapping_poke_below_the_target_writes_high_to_low(void)
{
    /* Payload BELOW the target (destination above source): memmove walks
     * high-to-low, or an early store clobbers a payload word a later load
     * still needs. */
    overlap_case(0x20000200u, 0x200001F8u, 4u);
}

void test_an_overlapping_poke_above_the_target_writes_low_to_high(void)
{
    /* Payload ABOVE the target (destination below source): memmove walks
     * low-to-high for the mirror reason. */
    overlap_case(0x20000200u, 0x20000204u, 4u);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_four_word_poke_lands_in_memory_and_holds);
    RUN_TEST(test_every_accepted_mailbox_count_5_7_9_11);
    RUN_TEST(test_wrong_shapes_are_exception_03_and_change_nothing);
    RUN_TEST(test_an_unaligned_target_is_refused_without_storing);
    RUN_TEST(test_flash_is_refused_even_though_the_peek_reads_it);
    RUN_TEST(test_peripherals_are_refused_including_the_reset_register);
    RUN_TEST(test_the_uid_and_flash_size_words_are_refused);
    RUN_TEST(test_shared_the_boot_handoff_is_excluded);
    RUN_TEST(test_the_stack_and_never_written_sram_are_excluded);
    RUN_TEST(test_a_gap_between_data_and_bss_refuses_bursts_that_cross_it);
    RUN_TEST(test_an_empty_span_refuses_everything_in_sram);
    RUN_TEST(test_the_wide_poke_takes_thirty_words_in_one_trigger);
    RUN_TEST(test_a_refused_wide_poke_still_counts_and_holds);
    RUN_TEST(test_wide_shapes_outside_3_plus_2_words_are_exception_03);
    RUN_TEST(test_poke_then_peek_roundtrip_proves_the_symmetry);
    RUN_TEST(test_an_overlapping_poke_below_the_target_writes_high_to_low);
    RUN_TEST(test_an_overlapping_poke_above_the_target_writes_low_to_high);
    return UNITY_END();
}

#endif /* O2P_DEBUG_ENABLE */
