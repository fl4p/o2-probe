/* Host oracle for tools/test_o2p_cli_exec.py: the REAL register map and
 * Modbus PDU layer, simulating main.c's deferred execution mailbox handler.
 */
#include <stdio.h>
#include <string.h>

#include "modbus_pdu.h"
#include "regmap.h"

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
    o2p_mb_handlers_t h = { o2p_regmap_read, o2p_regmap_write, &rm };

#if O2P_DEBUG_ENABLE
    int pending_polls = 0;
#endif

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

#if O2P_DEBUG_ENABLE
        /* Simulate main.c deferred execution:
         * When triggered, stay PENDING for 1 poll cycle before completing. */
        if (rm.exec_pending && rm.exec_cmd == (O2P_EXEC_MAGIC | O2P_EXEC_OP_RUN)) {
            if (pending_polls == 0) {
                /* First cycle after trigger: stay pending so the client or a peer
                 * can observe PENDING status and busy state. */
                pending_polls = 1;
            } else {
                /* Second cycle: execute payload and update status/result */
                uint16_t first_op = rm.exec_code[0];
                uint16_t second_op = (rm.exec_len >= 4u) ? rm.exec_code[1] : 0u;

                if (first_op == 0x202Au) {
                    /* movs r0, #42 */
                    if (second_op == 0x4770u) { /* bx lr */
                        rm.exec_result_hi = 0u;
                        rm.exec_result_lo = 42u;
                        rm.exec_status = O2P_EXEC_STATUS_OK;
                    } else {
                        /* Missing return instruction: falls through into BKPT trap */
                        rm.exec_status = O2P_EXEC_STATUS_FAULT;
                    }
                } else if (first_op == 0x3005u) {
                    /* adds r0, #5 */
                    if (second_op == 0x4770u) { /* bx lr */
                        uint32_t arg = ((uint32_t)rm.exec_param_hi << 16) | rm.exec_param_lo;
                        uint32_t res = arg + 5u;
                        rm.exec_result_hi = (uint16_t)(res >> 16);
                        rm.exec_result_lo = (uint16_t)(res & 0xFFFFu);
                        rm.exec_status = O2P_EXEC_STATUS_OK;
                    } else {
                        rm.exec_status = O2P_EXEC_STATUS_FAULT;
                    }
                } else if (first_op == 0xDE00u) {
                    /* Permanent trap / HardFault */
                    rm.exec_result_hi = 0u;
                    rm.exec_result_lo = 0u;
                    rm.exec_status = O2P_EXEC_STATUS_FAULT;
                } else if (first_op == 0xE7FEu) {
                    /* Infinite loop (b .) -> SysTick timeout */
                    rm.exec_result_hi = 0u;
                    rm.exec_result_lo = 0u;
                    rm.exec_status = O2P_EXEC_STATUS_TIMEOUT;
                } else {
                    rm.exec_result_hi = 0u;
                    rm.exec_result_lo = 0u;
                    rm.exec_status = O2P_EXEC_STATUS_ERR_OPCODE;
                }
                rm.exec_pending = false;
                rm.exec_cmd = 0u;
                pending_polls = 0;
            }
        } else {
            pending_polls = 0;
        }
#endif

        for (size_t i = 0; i < len; i++) {
            printf("%02x", rsp[i]);
        }
        printf("\n");
        fflush(stdout);
    }
    return 0;
}
