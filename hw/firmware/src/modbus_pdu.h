/* Modbus RTU frame handling, transport-independent so it can be tested on a
 * host. modbus_rtu.c owns the USART, the DE line and the timing; this file
 * owns everything that can be got wrong without hardware.
 *
 * The master on this bus is a Dragino RS485-LS LoRaWAN node, not a PC. It
 * emits literal, pre-programmed frames configured as
 *
 *     AT+COMMAND3=03 03 00 00 00 08,1
 *
 * i.e. a fixed FC03 read of a contiguous block (tech/RS485-LS-SMT100.md:290).
 * That is the ONLY function code that will ever arrive in normal operation,
 * and it is why every channel is exposed through holding registers.
 */
#ifndef O2P_MODBUS_PDU_H
#define O2P_MODBUS_PDU_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define O2P_MB_MAX_ADU 256u

/* Function codes we implement. Anything else gets exception 0x01. */
enum {
    O2P_MB_FC_READ_HOLDING   = 0x03u,
    O2P_MB_FC_READ_INPUT     = 0x04u,  /* mirrors 0x03, same address space */
    O2P_MB_FC_WRITE_SINGLE   = 0x06u,
    O2P_MB_FC_WRITE_MULTIPLE = 0x10u,
};

enum {
    O2P_MB_EX_ILLEGAL_FUNCTION = 0x01u,
    O2P_MB_EX_ILLEGAL_ADDRESS  = 0x02u,
    O2P_MB_EX_ILLEGAL_VALUE    = 0x03u,
    O2P_MB_EX_DEVICE_FAILURE   = 0x04u,
};

/* Valid unicast slave addresses are 1..247. 0 is broadcast.
 *
 * 248..255 are RESERVED by the Modbus specification, and 253 is used on this
 * bus as a discovery address: tech/RS485-LS-SMT100.md:247 documents that the
 * Truebner SMT100 answers 253 whatever its configured address, which is how a
 * probe with an unknown address is found ("the bench found probe 1 at address
 * 0"). We implement the same convention so one procedure works for every
 * probe on the bus - but it is only safe with a SINGLE device connected,
 * because two responders collide.
 *
 * OUR ALIAS IS READ-ONLY. The SMT100 procedure re-addresses through 253
 * (`AT+CFGDEV=FD 06 00 04 00 01,1`), and that is precisely the operation that
 * writes to EVERY device answering the alias if more than one is connected.
 * Reading a probe's own SLAVE_ADDR register through 253 recovers the address
 * just as well, after which the write goes to the real unicast address - same
 * capability, no way to reconfigure the wrong device. */
#define O2P_MB_ADDR_BROADCAST 0u
#define O2P_MB_ADDR_DISCOVERY 253u
#define O2P_MB_ADDR_MIN       1u
#define O2P_MB_ADDR_MAX       247u

uint16_t o2p_mb_crc16(const uint8_t *buf, size_t len);

/* How a received ADU should be treated. */
typedef enum {
    O2P_MB_DROP = 0,   /* not ours, or corrupt: stay silent */
    O2P_MB_EXECUTE,    /* ours: act and reply */
    O2P_MB_EXECUTE_NO_REPLY, /* broadcast: act, but never transmit */
} o2p_mb_disposition_t;

/* Classify a received ADU. `len` is the byte count the framer captured.
 *
 * Returns DROP for anything with a bad CRC, an impossible length, or another
 * device's address. Silence is the specified behaviour for a corrupt frame:
 * replying to one would put an unrequested transmission on a shared bus. */
o2p_mb_disposition_t o2p_mb_classify(const uint8_t *adu, size_t len,
                                     uint8_t own_addr);

/* Register access callbacks supplied by regmap.c. Both return a Modbus
 * exception code, or 0 on success. */
typedef uint8_t (*o2p_mb_read_fn)(void *ctx, uint16_t addr, uint16_t count,
                                  uint16_t *out);
typedef uint8_t (*o2p_mb_write_fn)(void *ctx, uint16_t addr, uint16_t count,
                                   const uint16_t *in);

typedef struct {
    o2p_mb_read_fn  read;
    o2p_mb_write_fn write;
    void           *ctx;
} o2p_mb_handlers_t;

/* Build the response ADU for a request already classified as EXECUTE.
 *
 * Returns the response length, or 0 if nothing should be transmitted (which
 * is what a broadcast produces). `rsp` must have room for O2P_MB_MAX_ADU.
 */
size_t o2p_mb_dispatch(const uint8_t *req, size_t req_len,
                       uint8_t own_addr,
                       const o2p_mb_handlers_t *h,
                       uint8_t *rsp);


/* Receiver timeout for one RTU frame boundary, in BIT TIMES (what the STM32
 * USART's RTOR register wants), for `baud` and `parity_code`.
 *
 * TWO RULES, AND THE SPEC SWITCHES BETWEEN THEM AT 19200. Modbus over Serial
 * Line v1.02 section 2.5.1.1: up to 19200 baud the inter-frame delay is 3.5
 * character times; ABOVE 19200 that formula is abandoned and a FIXED 1.750 ms
 * is mandated instead. The reason is the whole point of this function - a
 * character time shrinks with the baud rate, so 3.5 of them eventually falls
 * below the gap an ordinary master leaves between bytes, and a receiver using
 * the character rule starts declaring a frame boundary in the middle of one.
 *
 * WHAT THAT COST HERE. Every one of the three UARTs in this firmware computed
 * ceil(3.5 * bits) and ignored the baud entirely, so the absolute silence
 * collapsed as the bus sped up: 4010 us at 9600, 1003 us at 38400 - already
 * under the 1750 us floor - and 334 us at 115200, which a901947 had just made
 * selectable. The failure is silent and misleading: the receiver sees two
 * fragments, both fail CRC, both are dropped, and the master simply gets no
 * reply. That reads as "this cable cannot do 115200" and sends you to the
 * transceiver or the wiring, when it is this constant.
 *
 * Taking the larger of the two rules implements the switchover exactly,
 * because the fixed floor only overtakes 3.5 characters above 19200:
 *
 *     9600   max(39, 17)  = 39    unchanged
 *    19200   max(39, 34)  = 39    unchanged
 *    38400   max(39, 68)  = 68
 *   115200   max(39, 202) = 202
 *
 * So this is a no-op at every rate this firmware has ever shipped on, and only
 * bites where the spec says it must. */
static inline uint32_t o2p_mb_rtor_bit_times(uint32_t baud, uint8_t parity_none)
{
    const uint32_t bits     = parity_none ? 10u : 11u;
    const uint32_t chars35  = (bits * 7u + 1u) / 2u;      /* ceil(3.5 * bits) */
    /* ceil(0.001750 * baud), in integer arithmetic: (baud * 175 + 99999)/100000 */
    const uint32_t floor35  = (baud * 175u + 99999u) / 100000u;
    return chars35 > floor35 ? chars35 : floor35;
}

#endif /* O2P_MODBUS_PDU_H */