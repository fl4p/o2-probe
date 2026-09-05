#include "bridge_reply.h"

#include "modbus_pdu.h"

static size_t finish(uint8_t *rsp, size_t len)
{
    const uint16_t crc = o2p_mb_crc16(rsp, len);
    rsp[len] = (uint8_t)(crc & 0xFFu);
    rsp[len + 1u] = (uint8_t)(crc >> 8);
    return len + 2u;
}

static size_t exception(uint8_t *rsp, uint8_t addr, uint8_t fc, uint8_t code)
{
    rsp[0] = addr;
    rsp[1] = (uint8_t)(fc | 0x80u);
    rsp[2] = code;
    return finish(rsp, 3u);
}

size_t o2p_bridge_reply(uint8_t addr, const uint16_t *regs, unsigned nregs,
                        const uint8_t *req, size_t n, uint8_t *rsp)
{
    if (n < 4u) {
        return 0u;
    }
    const uint16_t got = (uint16_t)(req[n - 2] | ((uint16_t)req[n - 1] << 8));
    if (o2p_mb_crc16(req, n - 2u) != got) {
        return 0u;
    }

    const uint8_t fc = req[1];
    if (fc != O2P_MB_FC_READ_HOLDING && fc != O2P_MB_FC_READ_INPUT) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_FUNCTION);
    }
    /* Address, count, CRC - a read request is exactly eight bytes. Anything
     * else that got this far passed a CRC by accident or came from a master
     * speaking a different dialect; neither is a thing to answer with data. */
    if (n != 8u) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
    }

    const uint16_t first = (uint16_t)((req[2] << 8) | req[3]);
    const uint16_t count = (uint16_t)((req[4] << 8) | req[5]);
    /* Written as a subtraction on the right-hand side so that first + count
     * cannot wrap: both are 16-bit and nregs is small. */
    if (count == 0u || count > nregs || first > (uint16_t)(nregs - count)) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_ADDRESS);
    }

    rsp[0] = addr;
    rsp[1] = fc;
    rsp[2] = (uint8_t)(2u * count);
    for (unsigned i = 0; i < count; i++) {
        const uint16_t v = regs[first + i];
        rsp[3u + 2u * i] = (uint8_t)(v >> 8);
        rsp[4u + 2u * i] = (uint8_t)(v & 0xFFu);
    }
    return finish(rsp, 3u + 2u * (size_t)count);
}
