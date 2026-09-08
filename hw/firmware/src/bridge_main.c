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
 * There is no J2 any more - the expansion connector and the R12-R16 series
 * pack went in the 2026-09-05 BOM pass. UART2_TX/UART2_RX now stop at two
 * solder-wire lands provided for exactly this lead:
 *
 *     laptop TTL RX  <-  J105  "BRIDGE TX"   (UART2_TX, PA2, LQFP48 pin 13)
 *     laptop TTL TX  ->  J106  "BRIDGE RX"   (UART2_RX, PA3, LQFP48 pin 14)
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
/* The HOST lead is not the farm bus and does not have to run at its baud. The
 * bus is 9600 because the Dragino masters it there; this link is private -
 * two solder lands to whatever is driving them, with nothing else listening -
 * and at 9600 a 249-byte ADU spends 285 ms on it, which is half the cost of
 * relaying one firmware block.
 *
 * Raising it is safe on its own terms: the frame delimiter is the USART's
 * hardware receiver timeout, counted in BIT times (bridge_uart.c:54), so 3.5
 * character times stays 3.5 character times at any baud; and the two USARTs
 * are configured independently, so the bus half is untouched. It is also
 * recoverable: whatever drives this lead can always reach the bridge, because
 * this baud is the one it chose.
 *
 * BOTH ENDS MUST AGREE. The node sets -DO2P_UART_BAUD in its platformio.ini;
 * changing one without the other makes the link garbage, not slow. */
#ifndef O2P_BRIDGE_HOST_BAUD
#define O2P_BRIDGE_HOST_BAUD 115200u
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
/* The bus rate is no longer only the build-time constant -- a master may move
 * it (see g_bus_baud) -- so the floor has to hold for the SLOWEST rate the
 * bridge will accept, not merely for the one it booted at. Checking only the
 * macro would pass a build whose first re-rate truncates every long frame. */
_Static_assert(O2P_BRIDGE_BAUD_1 * O2P_BUART_TX_TIMEOUT_MS >= 2816000u &&
               O2P_BRIDGE_BAUD_2 * O2P_BUART_TX_TIMEOUT_MS >= 2816000u &&
               O2P_BRIDGE_BAUD_3 * O2P_BUART_TX_TIMEOUT_MS >= 2816000u,
               "a selectable bus rate is below the transmit-timeout floor");

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
/* 2: BR_REG_BUS_BAUD became writable (FC16, one register). The host reads this
 * before it moves the probe's own BAUD_CODE -- a v1 bridge answers reads
 * identically and would forward the probe's frames at a rate it cannot change,
 * leaving the probe unreachable until its probation timer or a reset saved it.
 * So the version is the discriminator, not a trial write. */
#define BR_VERSION 2u
#define BR_VERSION_RERATEABLE 2u

static o2p_buart_t g_bus;
static o2p_buart_t g_host;

/* The bus rate the bridge is USING, which is the build-time constant only
 * until a master moves it. BR_REG_BUS_BAUD reports this and not the macro:
 * the register exists to answer "what rate is this cable running at", and
 * after a re-rate the macro is the wrong answer to that question.
 *
 * Why the bridge can be moved at all: the probe's own BAUD_CODE is already
 * negotiable and already protected by an auto-revert (serial_probation.h) --
 * it goes back to the old rate unless a unicast frame proves the master
 * followed it within 10 s. What was missing was the other half. A firmware
 * push is ~141 blocks of 240 bytes and the RS-485 hop is 0.302 s of each at
 * 9600, so this is where a push's time actually goes.
 *
 * The bridge deliberately has NO auto-revert of its own, and the honest
 * version of why is narrower than "it does not need one".
 *
 * WHAT IS TRUE: the bridge cannot strand ITSELF. It is reachable over the host
 * lead whatever the cable is doing, so a bridge left at a rate nothing on the
 * cable answers at is one FC16 write away from correct (FC16, not FC06 -- this
 * file accepts only the former, see bridge_reply.c).
 *
 * WHAT IS NOT TRUE: that the PAIR always recovers by itself. The probe's timer
 * reverts the probe and nothing reverts the bridge, so a master that dies in
 * the ten seconds between the two writes leaves the probe back at 9600 and the
 * bridge at 38400, with nothing able to cross. That state is recoverable and
 * not silent -- the next run re-rates the bridge and sweeps the cable's rates
 * to find the probe -- but it is recovered by a TOOL, not by a timer, and any
 * claim that a crash is automatically safe is wrong about this half.
 *
 * Giving the bridge its own timer would not fix it either: the two timers
 * would have to agree on a deadline across a link that is by definition not
 * working, and a bridge that reverted underneath a probe that had just been
 * confirmed at the new rate would break a transfer that was going fine.
 */
static uint32_t g_bus_baud = O2P_BRIDGE_BUS_BAUD;

static void snapshot(uint16_t *r)
{
    r[BR_REG_IDENT]     = BR_IDENT;
    r[BR_REG_VERSION]   = BR_VERSION;
    r[BR_REG_HOST_RX]   = g_host.frames;
    r[BR_REG_BUS_RX]    = g_bus.frames;
    r[BR_REG_HOST_DROP] = g_host.drops;
    r[BR_REG_BUS_DROP]  = g_bus.drops;
    r[BR_REG_BUS_BAUD]  = (uint16_t)(g_bus_baud / 100u);
    r[BR_REG_PARITY]    = (uint16_t)((O2P_BRIDGE_BUS_PARITY << 8) |
                                     O2P_BRIDGE_HOST_PARITY);
}

/* Carry out a write o2p_bridge_reply accepted. Called only AFTER the reply has
 * been sent, because the reply has to leave at the rate the master is still
 * listening at -- and only on the host lead, which this never touches.
 *
 * The bus port is idle here GIVEN ONE MASTER, which is what this cable has and
 * what the whole Modbus RTU scheme assumes. The bridge is half duplex and
 * single threaded; this frame was answered locally so nothing was put on the
 * cable for it; and a previous bus send has already waited for TC and released
 * DE before returning (bridge_uart.c), so nothing of ours is still shifting.
 *
 * The residual case is a frame arriving from somewhere else at this instant --
 * a late slave reply, or a SECOND master, which this bus is not supposed to
 * have. o2p_buart_set_baud discards the partial receive rather than splicing
 * bytes from two line rates into one frame. What it cannot do is un-truncate
 * somebody else's frame: a second master transmitting through a re-rate loses
 * that frame and must retry it. That is a real limit of this design, and it is
 * bounded by the single-master assumption rather than by anything here. */
static void apply(const o2p_bridge_action_t *act)
{
    if (!act->set_bus_baud || act->bus_baud == g_bus_baud) {
        return;
    }
    g_bus_baud = act->bus_baud;
    o2p_buart_set_baud(&g_bus, g_bus_baud, O2P_BRIDGE_BUS_PARITY);
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
    o2p_bridge_action_t act;
    snapshot(regs);

    const size_t len = o2p_bridge_reply((uint8_t)O2P_BRIDGE_ADDR, regs,
                                        BR_REG_COUNT, f, n, rsp, &act);
    o2p_buart_send(&g_host, &g_bus, rsp, len);   /* len 0 sends nothing */
    apply(&act);
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
        o2p_bridge_action_t act;
        snapshot(regs);
        const size_t n = o2p_bridge_reply((uint8_t)O2P_BRIDGE_ADDR, regs,
                                          BR_REG_COUNT, frame, len, rsp, &act);
        for (size_t i = 0; i < n; i++) {
            m->rx[i] = rsp[i];
        }
        m->rx_len = (uint32_t)n;
        m->status = O2P_MBX_LOCAL;
        /* Over SWD there is no reply to get out first -- the debugger reads
         * rx[] after the fact -- but the ordering costs nothing and keeps one
         * rule for both transports. */
        apply(&act);
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
