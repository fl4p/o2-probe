/* Host oracle for tools/test_o2p_cli_gpio.py: the REAL register map, the REAL
 * Modbus PDU layer and the REAL OP_READ_GPIO logic, answering ADUs over a pipe,
 * with the counting GPIO/RCC fake from src/gpio_hal_host.c behind them.
 *
 * Why not a Python fake: the CLI decides what to PRINT from what the firmware
 * decided to SEND - above all, whether a pin has a level at all. A fake written
 * from the same reading of gpio_diag.h would share any misreading of it, and
 * pass. Same argument, same shape, as tools/peek_oracle.c.
 *
 * Protocol, one line each way:
 *   in   hex of a request ADU (CRC included)
 *   out  hex of the reply ADU, or an empty line when the probe stays silent
 * and, on lines starting with '#', control of the fake - test data, not a wire
 * protocol:
 *   #reset                          part reset values, clocks A/B/C, counters 0
 *   #gpio P MODER OTYPER PUPDR IDR ODR AFRL AFRH    (hex) set port index P
 *   #iopenr X                       (hex) set RCC_IOPENR
 *   #counts                         -> "gpio_loads rcc_loads unmasked_loads"
 * Every control line is answered with one line ("ok", or the counts). A nodebug
 * build has no fake and answers "nodebug".
 *
 * Deliberately NOT under test/: PlatformIO would treat a folder there as a
 * suite. Built by the Python test with the host C compiler. */
#include <stdio.h>
#include <string.h>

#include "modbus_pdu.h"
#include "regmap.h"
#if O2P_DEBUG_ENABLE
#include "gpio_hal.h"
#endif

static int nibble(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static o2p_regmap_t *s_rm;

static void control(const char *line)
{
#if O2P_DEBUG_ENABLE
    unsigned long v[8];
    if (strncmp(line, "#reset", 6) == 0) {
        o2p_host_gpio_reset();
    } else if (strncmp(line, "#counts", 7) == 0) {
        printf("%u %u %u\n", o2p_host_gpio_reads, o2p_host_rcc_reads,
               o2p_host_gpio_unmasked_reads + o2p_host_rcc_unmasked_reads);
        return;
    } else if (sscanf(line, "#gpio %lx %lx %lx %lx %lx %lx %lx %lx",
                      &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7]) == 8 &&
               v[0] < O2P_GPIO_PORT_SLOTS) {
        o2p_host_gpio_regs_t *g = &o2p_host_gpio[v[0]];
        g->MODER = (uint32_t)v[1];
        g->OTYPER = (uint32_t)v[2];
        g->PUPDR = (uint32_t)v[3];
        g->IDR = (uint32_t)v[4];
        g->ODR = (uint32_t)v[5];
        g->AFR[0] = (uint32_t)v[6];
        g->AFR[1] = (uint32_t)v[7];
    } else if (sscanf(line, "#iopenr %lx", &v[0]) == 1) {
        o2p_host_iopenr = (uint32_t)v[0];
    } else if (sscanf(line, "#diagdone %lx %lx %lx %lx %lx",
                      &v[0], &v[1], &v[2], &v[3], &v[4]) == 5 && s_rm != NULL) {
        /* What main.c's execute_diag_command() leaves behind when a queued
         * I2C opcode has run: its status and data, and the mailbox free.
         * main.c is not linked here, so the queue is emptied by hand. */
        s_rm->diag_status = (uint16_t)v[0];
        s_rm->diag_rdata0 = (uint16_t)v[1];
        s_rm->diag_rdata1 = (uint16_t)v[2];
        s_rm->diag_rdata2 = (uint16_t)v[3];
        s_rm->diag_crc_status = (uint16_t)v[4];
        s_rm->diag_pending = false;
    } else {
        printf("?\n");
        return;
    }
    printf("ok\n");
#else
    (void)line;
    printf("nodebug\n");
#endif
}

int main(void)
{
    static o2p_regmap_t rm;
    o2p_regmap_init(&rm);
    s_rm = &rm;
#if O2P_DEBUG_ENABLE
    o2p_host_gpio_reset();
#endif
    o2p_mb_handlers_t h = { o2p_regmap_read, o2p_regmap_write, &rm };

    char line[2048];
    while (fgets(line, sizeof line, stdin) != NULL) {
        if (line[0] == '#') {
            control(line);
            fflush(stdout);
            continue;
        }
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
