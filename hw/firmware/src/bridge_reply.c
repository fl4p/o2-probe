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

/* The bridge's only writable register: BR_REG_BUS_BAUD, in units of baud/100
 * so that 38400 fits a Modbus register. Named here rather than included from
 * bridge_main.c because that file is MCU-only and this one is tested on the
 * host; the two are tied together by test_bridge.c asserting they agree. */
#define BR_WRITABLE_REG 6u

static size_t write_regs(uint8_t addr, const uint8_t *req, size_t n,
                         uint8_t *rsp, o2p_bridge_action_t *act)
{
    const uint8_t fc = O2P_MB_FC_WRITE_MULTIPLE;
    /* FC16 and not FC06, although one register is all this accepts. FC16 is
     * the dialect everything else on this cable already speaks -- the probe's
     * whole config block is written with it, and o2p_update.py's Bus.write is
     * FC16 -- so a bridge that answered only FC06 would need its own verb on
     * the host side for one register. FC16 also echoes the address and count
     * it applied, which is the check that catches a write that landed
     * somewhere else.
     *
     * Address, count, byte count, one value, CRC: exactly eleven bytes. Same
     * reasoning as the read path's n != 8. */
    if (n != 11u) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (act == NULL) {
        /* This caller has no way to carry the write out. Refusing is the whole
         * point: echoing it would tell the master the cable moved when nothing
         * did, and the master would then talk into it at a rate nobody on it
         * is using, with no error anywhere to point at. */
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_FUNCTION);
    }

    const uint16_t reg = (uint16_t)((req[2] << 8) | req[3]);
    const uint16_t count = (uint16_t)((req[4] << 8) | req[5]);
    const uint8_t bytes = req[6];
    if (count != 1u || bytes != 2u) {
        /* A multi-register write cannot be partly applied here: register 6 is
         * the only writable one, so any block containing it also contains a
         * register that must not move. Refusing the whole frame is the only
         * answer that leaves no doubt about what happened. */
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (reg != BR_WRITABLE_REG) {
        /* Every other register is a counter or an identity. There is nothing
         * to write there, and a master that thinks otherwise has the wrong
         * map -- worth an exception rather than a silent no-op. */
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_ADDRESS);
    }

    const uint16_t val = (uint16_t)((req[7] << 8) | req[8]);
    const uint32_t baud = (uint32_t)val * 100u;
    if (baud != O2P_BRIDGE_BAUD_1 && baud != O2P_BRIDGE_BAUD_2 &&
        baud != O2P_BRIDGE_BAUD_3) {
        return exception(rsp, addr, fc, O2P_MB_EX_ILLEGAL_VALUE);
    }

    act->set_bus_baud = true;
    act->bus_baud = baud;
    /* FC16 answers with the address and count it applied. Built field by field
     * rather than memcpy'd so a caller may hand us overlapping buffers. */
    rsp[0] = addr;
    rsp[1] = fc;
    rsp[2] = req[2];
    rsp[3] = req[3];
    rsp[4] = req[4];
    rsp[5] = req[5];
    return finish(rsp, 6u);
}

size_t o2p_bridge_reply(uint8_t addr, const uint16_t *regs, unsigned nregs,
                        const uint8_t *req, size_t n, uint8_t *rsp,
                        o2p_bridge_action_t *act)
{
    if (act != NULL) {
        act->set_bus_baud = false;
        act->bus_baud = 0u;
    }
    if (n < 4u) {
        return 0u;
    }
    const uint16_t got = (uint16_t)(req[n - 2] | ((uint16_t)req[n - 1] << 8));
    if (o2p_mb_crc16(req, n - 2u) != got) {
        return 0u;
    }

    const uint8_t fc = req[1];
    if (fc == O2P_MB_FC_WRITE_MULTIPLE) {
        return write_regs(addr, req, n, rsp, act);
    }
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
