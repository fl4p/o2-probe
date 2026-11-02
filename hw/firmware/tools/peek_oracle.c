/* Host oracle for tools/test_o2p_cli_peek.py: the REAL register map and the
 * REAL Modbus PDU layer, answering ADUs over stdin/stdout.
 *
 * Why not a Python fake: a fake written from the same reading of regmap.h as
 * o2p_cli.py would reproduce any misreading of it faithfully, and pass. This
 * links src/regmap.c and src/modbus_pdu.c as built for `pio test -e native`,
 * so the CLI is tested against the firmware's own decisions.
 *
 * Protocol, one line each way:
 *   in   hex of a request ADU (CRC included), e.g. "031000...."
 *   out  hex of the reply ADU, or an empty line when the probe stays silent
 *
 * Memory behind the peeks is a pattern of the address, which the test
 * recomputes: (a ^ 0x5A5A5A5A) & 0x7FFFFFFF. It is test data, not semantics.
 *
 * Deliberately NOT under test/: PlatformIO would try to treat a folder there
 * as a suite. Built by the Python test with the host C compiler. */
#include <stdio.h>
#include <string.h>

#include "modbus_pdu.h"
#include "regmap.h"

static uint32_t pattern(uint32_t a)
{
    return (a ^ 0x5A5A5A5Au) & 0x7FFFFFFFu;
}

static int nibble(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int main(void)
{
    static o2p_regmap_t rm;
    o2p_regmap_init(&rm);
#if O2P_DEBUG_ENABLE
    o2p_peek_host_read = pattern;
#else
    (void)pattern;
#endif
    o2p_mb_handlers_t h = { o2p_regmap_read, o2p_regmap_write, &rm };

    char line[2048];
    while (fgets(line, sizeof line, stdin) != NULL) {
        uint8_t req[O2P_MB_MAX_ADU + 1u];
        uint8_t rsp[O2P_MB_MAX_ADU];
        size_t n = 0u;
        int ok = 1;
        for (size_t i = 0; line[i] != '\0' && line[i] != '\n'; i += 2u) {
            int hi = nibble(line[i]);
            int lo = (line[i + 1u] != '\0') ? nibble(line[i + 1u]) : -1;
            if (hi < 0 || lo < 0 || n > O2P_MB_MAX_ADU) {
                ok = 0;
                break;
            }
            req[n++] = (uint8_t)((hi << 4) | lo);
        }
        size_t len = 0u;
        if (ok && n <= O2P_MB_MAX_ADU &&
            o2p_mb_classify(req, n, rm.cfg.slave_addr) == O2P_MB_EXECUTE) {
            len = o2p_mb_dispatch(req, n, rm.cfg.slave_addr, &h, rsp);
        }
        for (size_t i = 0; i < len; i++) {
            printf("%02x", rsp[i]);
        }
        printf("\n");
        fflush(stdout);
    }
    return 0;
}
