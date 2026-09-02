/* The bench bridge's second host transport: a fixed block of SRAM that a
 * debugger reads and writes over SWD while the target runs.
 *
 * Why this exists alongside the UART one: SWD is already attached to a bridge
 * board, because that is how the bridge got flashed. The UART side needs a
 * 3.3 V USB-TTL lead and two soldered pads that are DNP; this needs neither.
 * The recipe that already reads this board's sensor globals is the same one -
 * OpenOCD, cmsis-dap.cfg, target/stm32g0x.cfg - so nothing new has to work.
 *
 * TWO RULES, and both are about a debugger's freedom to stop the core.
 *
 * 1. READ AND WRITE THIS ON A RUNNING TARGET. `mdw`/`mww` and
 *    `read_memory`/`write_memory` go through the AHB-AP and do not need the
 *    core halted. Halting is what the sensor-readout recipe does, for a
 *    coherent snapshot, and it must NOT be done here: PC6 is a plain GPIO, so
 *    a core halted between de_assert() and de_release() leaves the THVD1410
 *    driving the cable - which mutes every other node on it, the two SMT100s
 *    included - until the debugger resumes.
 *
 * 2. THE ADDRESS IS PINNED, NOT LINKED. The host writes a literal address;
 *    a symbol the linker was free to move would silently point the host at
 *    whatever landed there in the next build. So this lives in its own
 *    NOLOAD section at the bottom of SRAM, the way the boot-request word does
 *    in the other two images, and tools/pio_image_check.py fails the build if
 *    it is not exactly where the host expects.
 *
 * The handshake is the usual pair of sequence numbers, and the ordering is
 * the whole of the protocol:
 *
 *   host    fills tx[], sets tx_len, THEN increments host_seq
 *   bridge  sees host_seq change, transmits, collects a reply into rx[],
 *           sets rx_len and status, THEN increments target_seq
 *   host    polls target_seq, and only then reads rx_len and rx[]
 *
 * Each side writes the sequence word last, so neither can ever observe a
 * buffer that is half written - there is no torn state to reason about, only
 * a transaction that has or has not been published.
 */
#ifndef O2P_BRIDGE_MAILBOX_H
#define O2P_BRIDGE_MAILBOX_H

#include "modbus_pdu.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifndef O2P_HOST_TEST
#include "mcu.h"
/* The publication ordering below is a claim about what the debug MEM-AP
 * observes, not merely about what the compiler emits. `volatile` gives the
 * second and not the first: it forbids the compiler from removing or
 * reordering these accesses relative to each other, and says nothing about
 * the memory system. A data barrier before each publishing store is what
 * makes the claim true rather than true-by-observation of one compiler's
 * output. It is one instruction. */
#define o2p_mbx_publish_barrier() __DMB()
#else
#define o2p_mbx_publish_barrier() ((void)0)
#endif

/* Bottom of SRAM. Also written into tools/o2p_update.py, and checked. */
#define O2P_MBX_BASE    0x20000000u
#define O2P_MBX_MAGIC   0x4F324D42u   /* "O2MB", little-endian in memory */
#define O2P_MBX_VERSION 1u

/* status, published with rx_len before target_seq advances. */
enum {
    O2P_MBX_IDLE     = 0u,
    O2P_MBX_REPLIED  = 1u,   /* a frame came back; rx_len says how much */
    O2P_MBX_SILENT   = 2u,   /* nothing answered inside the reply window */
    O2P_MBX_LOCAL    = 3u,   /* the bridge answered for itself; see rx[] */
    O2P_MBX_REJECTED = 4u,   /* tx_len was not a possible ADU; nothing sent */
};

typedef struct {
    volatile uint32_t magic;        /* +0x00 O2P_MBX_MAGIC once initialised */
    volatile uint32_t version;      /* +0x04 */
    volatile uint32_t host_seq;     /* +0x08 written LAST by the host */
    volatile uint32_t target_seq;   /* +0x0C written LAST by the bridge */
    volatile uint32_t tx_len;       /* +0x10 */
    volatile uint32_t rx_len;       /* +0x14 */
    volatile uint32_t status;       /* +0x18 */
    volatile uint32_t reply_ms;     /* +0x1C how long the bridge will wait */
    volatile uint8_t  tx[O2P_MB_MAX_ADU];   /* +0x20 */
    volatile uint8_t  rx[O2P_MB_MAX_ADU];   /* +0x120 */
} o2p_mailbox_t;

/* The layout, as CONSTANTS the compiler checks - not as comments.
 *
 * tools/check_update_tool.py compares these against the literals in
 * tools/o2p_update.py, which is the only way the Python and the C can agree
 * on a layout neither can import. An earlier version of that check read the
 * offsets out of the struct's comments, and an adversarial review broke it in
 * one move: swapping two declarations while leaving their comments in place
 * passed the check, the build, and would have pointed the host at the wrong
 * word. offsetof cannot be fooled that way. */
#define O2P_MBX_OFF_MAGIC       0x00u
#define O2P_MBX_OFF_VERSION     0x04u
#define O2P_MBX_OFF_HOST_SEQ    0x08u
#define O2P_MBX_OFF_TARGET_SEQ  0x0Cu
#define O2P_MBX_OFF_TX_LEN      0x10u
#define O2P_MBX_OFF_RX_LEN      0x14u
#define O2P_MBX_OFF_STATUS      0x18u
#define O2P_MBX_OFF_REPLY_MS    0x1Cu
#define O2P_MBX_OFF_TX          0x20u
#define O2P_MBX_OFF_RX          0x120u
#define O2P_MBX_BYTES           0x220u

#define O2P_MBX_ASSERT_AT(field, off) \
    _Static_assert(offsetof(o2p_mailbox_t, field) == (off), \
                   "the mailbox field " #field " moved - the host writes a " \
                   "literal address and cannot find out")

O2P_MBX_ASSERT_AT(magic,      O2P_MBX_OFF_MAGIC);
O2P_MBX_ASSERT_AT(version,    O2P_MBX_OFF_VERSION);
O2P_MBX_ASSERT_AT(host_seq,   O2P_MBX_OFF_HOST_SEQ);
O2P_MBX_ASSERT_AT(target_seq, O2P_MBX_OFF_TARGET_SEQ);
O2P_MBX_ASSERT_AT(tx_len,     O2P_MBX_OFF_TX_LEN);
O2P_MBX_ASSERT_AT(rx_len,     O2P_MBX_OFF_RX_LEN);
O2P_MBX_ASSERT_AT(status,     O2P_MBX_OFF_STATUS);
O2P_MBX_ASSERT_AT(reply_ms,   O2P_MBX_OFF_REPLY_MS);
O2P_MBX_ASSERT_AT(tx,         O2P_MBX_OFF_TX);
O2P_MBX_ASSERT_AT(rx,         O2P_MBX_OFF_RX);
_Static_assert(sizeof(o2p_mailbox_t) == O2P_MBX_BYTES,
               "the mailbox changed size - ldscript/o2probe_bridge.ld's "
               "MAILBOX region must change with it");

extern o2p_mailbox_t g_o2p_mailbox;

/* Zero the block and stamp the magic. Called at every boot, BEFORE the bus is
 * touched: the section is NOLOAD, so without this the mailbox comes up
 * holding whatever the last session - or a power-on garbage pattern - left,
 * and a host_seq that happens to differ from zero would fire a transmission
 * built out of nothing. */
void o2p_mailbox_init(void);

/* Is tx_len something that could be a Modbus ADU at all? An address byte, a
 * function code and a CRC is four bytes; O2P_MB_MAX_ADU is the ceiling. Pure,
 * so the host tests can walk the boundary. */
bool o2p_mailbox_len_ok(uint32_t len);

/* How long the bridge waits for a reply, clamped. A host that leaves
 * reply_ms at 0 gets the default; one that asks for an hour does not get to
 * hold the loop for an hour. */
uint32_t o2p_mailbox_reply_window(uint32_t asked_ms);

#define O2P_MBX_REPLY_MS_DEFAULT 1000u
#define O2P_MBX_REPLY_MS_MAX     5000u

#endif /* O2P_BRIDGE_MAILBOX_H */
