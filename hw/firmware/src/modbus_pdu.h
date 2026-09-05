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

#endif /* O2P_MODBUS_PDU_H */
