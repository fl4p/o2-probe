/* BENCH TOOL. The o2-probe as its own RS-485 adapter.
 *
 * A potted probe can only be reflashed over RS-485 (DESIGN.md:60), and doing
 * that needs a Modbus master on the farm cable. This image turns a spare,
 * UNPOTTED probe into one - or rather, into the wire to one: it carries frames
 * between a laptop's 3.3 V USB-TTL lead and the board's own THVD1410, so
 * tools/o2p_update.py and any other Modbus master run against a real bus
 * without a USB-RS485 dongle.
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

_Static_assert(O2P_BRIDGE_HOST_BAUD >= O2P_BRIDGE_BUS_BAUD,
               "the host link must not be slower than the bus: the bridge "
               "cannot drain a bus reply faster than it arrives, and the "
               "difference comes out as dropped frames");

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
    o2p_buart_send(&g_host, rsp, len);   /* len 0 sends nothing */
    return true;
}

int main(void)
{
    o2p_clock_init();
    o2p_buart_init_bus(&g_bus, O2P_BRIDGE_BUS_BAUD, O2P_BRIDGE_BUS_PARITY);
    o2p_buart_init_host(&g_host, O2P_BRIDGE_HOST_BAUD, O2P_BRIDGE_HOST_PARITY);

    static uint8_t frame[O2P_MB_MAX_ADU];

    for (;;) {
        /* Host -> cable. The frame is forwarded only once the host has been
         * silent for 3.5 character times, because that silence is the only
         * thing that says the frame is over, and DE cannot be asserted before
         * then. That latency - about 4 ms at 9600 - is inherent to bridging a
         * half-duplex bus, and is three orders below the host's timeout. */
        size_t n = o2p_buart_poll(&g_host, frame, sizeof(frame));
        if (n != 0u && !answered_locally(frame, n)) {
            o2p_buart_send(&g_bus, frame, n);
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
            o2p_buart_send(&g_host, frame, n);
        }
    }
}
