#include "modbus_pdu.h"

#include <string.h>

/* CRC-16/MODBUS: poly 0xA001 reflected, init 0xFFFF, no final xor.
 * Bitwise rather than table-driven: at 9600 baud the longest frame we will
 * ever see is a few hundred microseconds of CPU on a 16 MHz M0+, and a 512-byte
 * table is a poor trade against 128 KiB of flash shared with a bootloader. */
uint16_t o2p_mb_crc16(const uint8_t *buf, size_t len)
{
    uint16_t crc = 0xFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)buf[i];
        for (unsigned b = 0; b < 8u; b++) {
            crc = (crc & 1u) ? (uint16_t)((crc >> 1) ^ 0xA001u) : (uint16_t)(crc >> 1);
        }
    }
    return crc;
}

static bool crc_ok(const uint8_t *adu, size_t len)
{
    /* Modbus sends the CRC low byte first. */
    uint16_t want = (uint16_t)adu[len - 2] | ((uint16_t)adu[len - 1] << 8);
    return o2p_mb_crc16(adu, len - 2) == want;
}

o2p_mb_disposition_t o2p_mb_classify(const uint8_t *adu, size_t len,
                                     uint8_t own_addr)
{
    /* Shortest legal RTU ADU is address + function + CRC = 4 bytes. Anything
     * shorter is a fragment left by a collision or a truncated master. */
    if (adu == NULL || len < 4u || len > O2P_MB_MAX_ADU) {
        return O2P_MB_DROP;
    }
    if (!crc_ok(adu, len)) {
        return O2P_MB_DROP;
    }

    uint8_t addr = adu[0];
    if (addr == O2P_MB_ADDR_BROADCAST) {
        return O2P_MB_EXECUTE_NO_REPLY;
    }
    if (addr == own_addr || addr == O2P_MB_ADDR_DISCOVERY) {
        return O2P_MB_EXECUTE;
    }
    return O2P_MB_DROP;
}

static size_t exception(uint8_t *rsp, uint8_t addr, uint8_t fc, uint8_t code)
{
    rsp[0] = addr;
    rsp[1] = (uint8_t)(fc | 0x80u);
    rsp[2] = code;
    uint16_t crc = o2p_mb_crc16(rsp, 3u);
    rsp[3] = (uint8_t)(crc & 0xFFu);
    rsp[4] = (uint8_t)(crc >> 8);
    return 5u;
}

static size_t finish(uint8_t *rsp, size_t n)
{
    uint16_t crc = o2p_mb_crc16(rsp, n);
    rsp[n] = (uint8_t)(crc & 0xFFu);
    rsp[n + 1u] = (uint8_t)(crc >> 8);
    return n + 2u;
}

/* The response ADU for a read is 3 header bytes + 2 per register + 2 CRC.
 * With a 256-byte ADU limit that caps a read at 125 registers, which is also
 * the Modbus specification's limit. */
#define O2P_MB_MAX_READ_REGS 125u
#define O2P_MB_MAX_WRITE_REGS 123u

size_t o2p_mb_dispatch(const uint8_t *req, size_t req_len,
                       uint8_t own_addr,
                       const o2p_mb_handlers_t *h,
                       uint8_t *rsp)
{
    (void)own_addr;
    if (req == NULL || rsp == NULL || h == NULL || req_len < 4u) {
        return 0u;
    }

    /* Reply from the address the master used. A discovery read addressed to
     * 253 is answered as 253: that is what makes the reply recognisable to a
     * master that does not yet know our address. */
    const uint8_t addr = req[0];
    const uint8_t fc = req[1];
    const bool broadcast = (addr == O2P_MB_ADDR_BROADCAST);

    /* The discovery alias answers reads only - see the header. A write that
     * arrives on 253 is refused rather than ignored, so an operator who tries
     * the SMT100 re-addressing recipe gets told no instead of silently
     * reconfiguring whichever devices happened to be listening. */
    if (addr == O2P_MB_ADDR_DISCOVERY &&
        fc != O2P_MB_FC_READ_HOLDING && fc != O2P_MB_FC_READ_INPUT) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_FUNCTION);
    }

    uint16_t start = 0, count = 0;
    uint16_t regs[O2P_MB_MAX_READ_REGS];

    switch (fc) {
    case O2P_MB_FC_READ_HOLDING:
    case O2P_MB_FC_READ_INPUT: {
        if (req_len != 8u) {
            return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
        }
        start = (uint16_t)((uint16_t)req[2] << 8 | req[3]);
        count = (uint16_t)((uint16_t)req[4] << 8 | req[5]);
        if (count == 0u || count > O2P_MB_MAX_READ_REGS) {
            return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
        }
        uint8_t ex = h->read(h->ctx, start, count, regs);
        if (ex != 0u) {
            return broadcast ? 0u : exception(rsp, addr, fc, ex);
        }
        /* A read is pointless as a broadcast and the specification forbids a
         * reply, so execute nothing and stay silent. */
        if (broadcast) {
            return 0u;
        }
        rsp[0] = addr;
        rsp[1] = fc;
        rsp[2] = (uint8_t)(count * 2u);
        for (uint16_t i = 0; i < count; i++) {
            rsp[3u + i * 2u] = (uint8_t)(regs[i] >> 8);
            rsp[4u + i * 2u] = (uint8_t)(regs[i] & 0xFFu);
        }
        return finish(rsp, 3u + (size_t)count * 2u);
    }

    case O2P_MB_FC_WRITE_SINGLE: {
        if (req_len != 8u) {
            return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
        }
        start = (uint16_t)((uint16_t)req[2] << 8 | req[3]);
        uint16_t value = (uint16_t)((uint16_t)req[4] << 8 | req[5]);
        uint8_t ex = h->write(h->ctx, start, 1u, &value);
        if (broadcast) {
            return 0u;
        }
        if (ex != 0u) {
            return exception(rsp, addr, fc, ex);
        }
        /* The specified response echoes the request verbatim. */
        memcpy(rsp, req, 6u);
        return finish(rsp, 6u);
    }

    case O2P_MB_FC_WRITE_MULTIPLE: {
        if (req_len < 9u) {
            return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
        }
        start = (uint16_t)((uint16_t)req[2] << 8 | req[3]);
        count = (uint16_t)((uint16_t)req[4] << 8 | req[5]);
        uint8_t bytecount = req[6];
        /* Three independent length statements must agree: the register count,
         * the byte count, and the actual frame length. A master that
         * disagrees with itself is not one we execute for. */
        if (count == 0u || count > O2P_MB_MAX_WRITE_REGS ||
            bytecount != (uint8_t)(count * 2u) ||
            req_len != (size_t)9u + bytecount) {
            return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
        }
        uint16_t vals[O2P_MB_MAX_WRITE_REGS];
        for (uint16_t i = 0; i < count; i++) {
            vals[i] = (uint16_t)((uint16_t)req[7u + i * 2u] << 8 | req[8u + i * 2u]);
        }
        uint8_t ex = h->write(h->ctx, start, count, vals);
        if (broadcast) {
            return 0u;
        }
        if (ex != 0u) {
            return exception(rsp, addr, fc, ex);
        }
        rsp[0] = addr;
        rsp[1] = fc;
        rsp[2] = req[2];
        rsp[3] = req[3];
        rsp[4] = req[4];
        rsp[5] = req[5];
        return finish(rsp, 6u);
    }

    default:
        return broadcast ? 0u : exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_FUNCTION);
    }
}
