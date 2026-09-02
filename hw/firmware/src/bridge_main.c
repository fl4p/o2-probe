/* BENCH TOOL. The o2-probe as its own RS-485 adapter.
 *
 * A potted probe can only be reflashed over RS-485 (DESIGN.md:60), and doing
 * that needs a Modbus master on the farm cable. This image turns a spare,
 * UNPOTTED probe into one - or rather, into the wire to one: it carries frames
 * between a laptop's 3.3 V USB-TTL lead and the board's own THVD1410, so
 * tools/o2p_update.py and any other Modbus master run against a real bus
 * without a USB-RS485 dongle.
 *
 * TWO HOST TRANSPORTS, one bus half. The lead described below is one of them;
 * the other is a block of SRAM a debugger reads and writes over the SWD that
 * is already attached to this board - see src/bridge_mailbox.h. They share
 * everything from the frame downwards, they are chosen by which one the host
 * actually uses, and neither knows about the other.
 *
 * The host lead does NOT go to J2. R15/R16 are DNP (gen_sch.py:511-512), so
 * UART2_TX/UART2_RX stop at those 0603 pads:
 *
 *     laptop TTL RX  <-  R15 pad, MCU side   (UART2_TX, PA2, LQFP48 pin 13)
 *     laptop TTL TX  ->  R16 pad, MCU side   (UART2_RX, PA3, LQFP48 pin 14)
 *     laptop TTL GND <-> board GND
 *
 * 3.3 V logic only. A 5 V lead on PA3 is outside the part's absolute maximum;
 * PA2/PA3 are not five-volt tolerant on this device.
 *
 * WHAT THIS IS NOT: it is not a Modbus master, it does not know the update
 * protocol, and it does not retry anything. Every decision stays with the host
 * tool, which is the point - a bridge that interpreted the traffic would be a
 * second thing to debug when a transfer fails.
 *
 * NEVER POT A PROBE RUNNING THIS. It has no sampler, no watchdog and no
 * register map; it publishes no oxygen number at all.
 *
 * -------------------------------------------------------------------------
 * The one thing it does answer for itself
 *
 * A bridge that only forwards is untestable: a silent bus tells you nothing
 * about whether the fault is your adapter, your baud rate, your parity, your
 * wiring, or the probe. So the bridge answers FC03/FC04 at ONE address of its
 * own with a handful of counters. Reading them proves the host half of the
 * chain end to end before any probe is blamed.
 *
 * That interception is the one way this image can eat a frame meant for
 * something else, so the address is constrained at compile time to the
 * reserved range the specification keeps for exactly this (248..255,
 * modbus_pdu.h:40), minus 253, which this firmware already uses as the
 * read-only discovery alias. O2P_BRIDGE_ADDR=0 disables interception outright
 * and makes the bridge a pure wire.
 */
#include "board_pins.h"
#include "bridge_mailbox.h"
#include "bridge_reply.h"
#include "bridge_uart.h"
#include "mcu.h"
#include "modbus_pdu.h"
#include "regmap.h"

#include <string.h>

/* The farm bus. The Dragino masters it at 9600 8E1 (regmap.h:123), and a
 * bridge that framed it differently would be transparent to nothing. */
#ifndef O2P_BRIDGE_BUS_BAUD
#define O2P_BRIDGE_BUS_BAUD 9600u
#endif
#ifndef O2P_BRIDGE_BUS_PARITY
#define O2P_BRIDGE_BUS_PARITY O2P_PARITY_EVEN
#endif

/* The host lead. Defaults to the bus settings so that the plain case needs no
 * flags, but the two sides are independent: this is store-and-forward, not a
 * level shifter, so the laptop may run faster than the cable. It must not run
 * SLOWER - see the note on overrun at the bottom of loop(). */
#ifndef O2P_BRIDGE_HOST_BAUD
#define O2P_BRIDGE_HOST_BAUD O2P_BRIDGE_BUS_BAUD
#endif
#ifndef O2P_BRIDGE_HOST_PARITY
#define O2P_BRIDGE_HOST_PARITY O2P_BRIDGE_BUS_PARITY
#endif

#ifndef O2P_BRIDGE_ADDR
#define O2P_BRIDGE_ADDR 250u
#endif

_Static_assert(O2P_BRIDGE_ADDR == O2P_MB_ADDR_BROADCAST ||
               (O2P_BRIDGE_ADDR > O2P_MB_ADDR_MAX &&
                O2P_BRIDGE_ADDR != O2P_MB_ADDR_DISCOVERY &&
                O2P_BRIDGE_ADDR <= 255u),
               "O2P_BRIDGE_ADDR must be 0 (no interception) or a reserved "
               "address 248..255 other than 253 - anything in 1..247 would "
               "make the bridge swallow frames addressed to a real slave");

/* A maximum ADU must fit inside the transmit timeout, or the timeout truncates
 * a frame the bridge was in the middle of sending. 256 characters of 11 bits
 * each at B baud is 2816000/B milliseconds; at the 500 ms ceiling that puts
 * the floor at 5632 baud. DE is still released on the timeout path, so this
 * is a truncation bug and not a cable jam - but it is silent, which is worse
 * to debug. */
_Static_assert(O2P_BRIDGE_BUS_BAUD * O2P_BUART_TX_TIMEOUT_MS >= 2816000u &&
               O2P_BRIDGE_HOST_BAUD * O2P_BUART_TX_TIMEOUT_MS >= 2816000u,
               "at this baud a full 256-byte ADU takes longer than "
               "O2P_BUART_TX_TIMEOUT_MS and would be truncated mid-frame");

/* There is deliberately NO assertion that the host link is at least as fast as
 * the bus. An earlier version had one, on the reasoning that a slower host
 * could not drain a bus reply as it arrived - which is wrong twice. The reply
 * is complete and buffered before the host transmission starts, so nothing is
 * drained in real time; and a baud ordering cannot establish the property
 * that actually matters, which is that nobody transmits at the bridge while
 * the bridge is transmitting. That is a traffic model, not a line rate, and
 * it is stated where it belongs, at the sends in loop(). */

/* The bridge's own register block, FC03/FC04, read-only, addresses 0..7. */
enum {
    BR_REG_IDENT    = 0u,   /* 0xB21D, constant: "a bridge answered" */
    BR_REG_VERSION  = 1u,
    BR_REG_HOST_RX  = 2u,   /* frames taken from the host lead */
    BR_REG_BUS_RX   = 3u,   /* frames taken from the cable */
    BR_REG_HOST_DROP = 4u,  /* host frames discarded: line error or overrun */
    BR_REG_BUS_DROP = 5u,   /* cable frames discarded, ditto */
    BR_REG_BUS_BAUD = 6u,   /* bus baud / 100 */
    BR_REG_PARITY   = 7u,   /* bus parity in the high byte, host in the low */
    BR_REG_COUNT    = 8u,
};
#define BR_IDENT   0xB21Du
#define BR_VERSION 1u

static o2p_buart_t g_bus;
static o2p_buart_t g_host;

static void snapshot(uint16_t *r)
{
    r[BR_REG_IDENT]     = BR_IDENT;
    r[BR_REG_VERSION]   = BR_VERSION;
    r[BR_REG_HOST_RX]   = g_host.frames;
    r[BR_REG_BUS_RX]    = g_bus.frames;
    r[BR_REG_HOST_DROP] = g_host.drops;
    r[BR_REG_BUS_DROP]  = g_bus.drops;
    r[BR_REG_BUS_BAUD]  = (uint16_t)(O2P_BRIDGE_BUS_BAUD / 100u);
    r[BR_REG_PARITY]    = (uint16_t)((O2P_BRIDGE_BUS_PARITY << 8) |
                                     O2P_BRIDGE_HOST_PARITY);
}

/* True if the frame was for the bridge itself and must NOT reach the cable. */
static bool answered_locally(const uint8_t *f, size_t n)
{
    if (O2P_BRIDGE_ADDR == O2P_MB_ADDR_BROADCAST || f[0] != O2P_BRIDGE_ADDR) {
        return false;
    }
    /* Addressed to us. From here the frame is consumed whatever happens to it:
     * putting a frame that carries our own address onto the cable would be
     * asking some other node to answer as us. */
    uint16_t regs[BR_REG_COUNT];
    uint8_t rsp[5u + 2u * BR_REG_COUNT];
    snapshot(regs);

    const size_t len = o2p_bridge_reply((uint8_t)O2P_BRIDGE_ADDR, regs,
                                        BR_REG_COUNT, f, n, rsp);
    o2p_buart_send(&g_host, &g_bus, rsp, len);   /* len 0 sends nothing */
    return true;
}

/* One SWD transaction, start to finish. Called with a frame the host has
 * published; returns having published a reply, or the reason there is none. */
static bool mailbox_run(uint8_t *frame, uint32_t serving)
{
    o2p_mailbox_t *m = &g_o2p_mailbox;
    const uint32_t len = m->tx_len;

    if (!o2p_mailbox_len_ok(len)) {
        m->rx_len = 0u;
        m->status = O2P_MBX_REJECTED;
        return true;
    }
    for (uint32_t i = 0; i < len; i++) {
        frame[i] = m->tx[i];
    }
    /* Nothing stops a debugger writing the mailbox while this copy runs - a
     * second host, or the same tool restarted after a timeout it believed was
     * fatal. The sequence word is the host's last write, so re-reading it
     * after the copy is what says whether the bytes just copied all belong to
     * one frame. If they do not, publish nothing: this sequence has not been
     * consumed, and the loop comes back for the newer one. */
    if (m->host_seq != serving) {
        return false;
    }

    /* A frame for the bridge itself is answered here too, so that --bridge
     * works over SWD and proves the mailbox without touching the cable. */
    uint16_t regs[BR_REG_COUNT];
    uint8_t rsp[5u + 2u * BR_REG_COUNT];
    if (O2P_BRIDGE_ADDR != O2P_MB_ADDR_BROADCAST && frame[0] == O2P_BRIDGE_ADDR) {
        snapshot(regs);
        const size_t n = o2p_bridge_reply((uint8_t)O2P_BRIDGE_ADDR, regs,
                                          BR_REG_COUNT, frame, len, rsp);
        for (size_t i = 0; i < n; i++) {
            m->rx[i] = rsp[i];
        }
        m->rx_len = (uint32_t)n;
        m->status = O2P_MBX_LOCAL;
        return true;
    }

    o2p_buart_send(&g_bus, &g_host, frame, len);

    const uint32_t window = o2p_mailbox_reply_window(m->reply_ms);
    const uint32_t t0 = o2p_millis();
    for (;;) {
        const size_t n = o2p_buart_poll(&g_bus, frame, O2P_MB_MAX_ADU);
        if (n != 0u) {
            for (size_t i = 0; i < n; i++) {
                m->rx[i] = frame[i];
            }
            m->rx_len = (uint32_t)n;
            m->status = O2P_MBX_REPLIED;
            return true;
        }
        if (o2p_elapsed(t0, window)) {
            /* Silence is a result, not an error. The host's own Modbus
             * timeout is what decides whether to retry; saying nothing here
             * would leave it unable to tell a lost reply from a wedged
             * bridge. */
            m->rx_len = 0u;
            m->status = O2P_MBX_SILENT;
            return true;
        }
    }
}

int main(void)
{
    o2p_clock_init();
    o2p_mailbox_init();
    o2p_buart_init_bus(&g_bus, O2P_BRIDGE_BUS_BAUD, O2P_BRIDGE_BUS_PARITY);
    o2p_buart_init_host(&g_host, O2P_BRIDGE_HOST_BAUD, O2P_BRIDGE_HOST_PARITY);

    static uint8_t frame[O2P_MB_MAX_ADU];
    uint32_t seen_seq = g_o2p_mailbox.host_seq;

    for (;;) {
        /* SWD host. The sequence word is the host's last write, so seeing it
         * change means the buffer behind it is complete. Our own sequence
         * word is written last for the same reason, and only after rx_len and
         * status are in place. */
        const uint32_t asked = g_o2p_mailbox.host_seq;
        if (asked != seen_seq && mailbox_run(frame, asked)) {
            /* rx_len and status are in place; the barrier makes that true for
             * the debugger reading them, not merely for the compiler, before
             * the sequence word says the transaction is finished. */
            o2p_mbx_publish_barrier();
            g_o2p_mailbox.target_seq = asked;
            seen_seq = asked;
        }

        /* Host -> cable. The frame is forwarded only once the host has been
         * silent for 3.5 character times, because that silence is the only
         * thing that says the frame is over, and DE cannot be asserted before
         * then. That latency - about 4 ms at 9600 - is inherent to bridging a
         * half-duplex bus, and is three orders below the host's timeout. */
        size_t n = o2p_buart_poll(&g_host, frame, sizeof(frame));
        if (n != 0u && !answered_locally(frame, n)) {
            o2p_buart_send(&g_bus, &g_host, frame, n);
        }

        /* Cable -> host, verbatim, CRC and all. The host checks the CRC; the
         * bridge deliberately does not, so a bus error reaches the person
         * debugging it instead of being converted into a silence here.
         *
         * Both sends block, and nothing services the opposite receiver while
         * one runs. That is safe in the traffic a Modbus master generates - it
         * is waiting for the reply it just asked for - and it is why the host
         * link may not be slower than the bus. If it ever is, the symptom is
         * BUS_DROP climbing in the bridge's own registers. */
        n = o2p_buart_poll(&g_bus, frame, sizeof(frame));
        if (n != 0u) {
            o2p_buart_send(&g_host, &g_bus, frame, n);
        }
    }
}
