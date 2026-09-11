/* OP_READ_GPIO: what one MCU pin is really doing, read over Modbus.
 *
 * WHY. On 2026-09-04 an ADS1119 was desoldered and replaced because every
 * channel read as the one before it. The part was healthy: PB1, its DRDY input,
 * had never been configured and sat in ANALOG mode, where the input buffer is
 * off and IDR reads 0 whatever the pin does - so the conversion wait fell
 * straight through (PIN-IDENTITY-POSTMORTEM.md, and the comment in ads1119.c).
 * One read of PB1's MODER would have said so. On a potted probe nothing else
 * can.
 *
 * STRICTLY READ-ONLY. The opcode loads GPIOx MODER, OTYPER, PUPDR, IDR, ODR and
 * AFR, and RCC_IOPENR, and writes nothing anywhere - see gpio_hal.h, which has
 * no write verb to call. It never enables a clock: a port whose clock is off is
 * reported as such, not woken up to be looked at.
 *
 * ---- Wire encoding (DIAG_CMD 0x5A08) ----
 *
 * DIAG_PARAM = port << 8 | pin
 *     port  0 = A, 1 = B, 2 = C, 3 = D, 5 = F. 4 is where E would be; the
 *           STM32G071 has no port E, and 4 is refused like any other absent pin.
 *     pin   0..15
 *
 * DIAG_STATUS
 *     OK (2)                    level sampled, every field below is real
 *     GPIO_NOT_SAMPLED (7)      the pin is in ANALOG mode, so there IS no level:
 *                               RDATA0's configuration and the port words are
 *                               real, LEVEL and LEVEL_VALID are 0. Not a LOW.
 *     ERR_GPIO_UNCLOCKED (8)    the port's RCC_IOPENR bit is clear. Nothing of
 *                               the port was loaded; all data reads 0.
 *     ERR_GPIO_NO_PIN (9)       no such bonded pin on the LQFP48 - absent port,
 *                               pin above 15, or a pad not brought out. Nothing
 *                               at all was loaded, RCC included; all data 0.
 *
 * RDATA0, the pin
 *     bits  1..0   MODE        MODER field: 0 input, 1 output, 2 AF, 3 analog
 *     bits  3..2   PULL        PUPDR field: 0 none, 1 up, 2 down, 3 reserved
 *     bit   4      OPEN_DRAIN  OTYPER bit: 0 push-pull, 1 open-drain
 *     bit   5      ODR         the output latch - what firmware ASKED for
 *     bit   6      LEVEL       the IDR bit - what the pin IS; 0 unless LEVEL_VALID
 *     bit   7      reserved, 0
 *     bits 11..8   AF          AFR field, 0..15, whatever the mode
 *     bits 13..12  reserved, 0
 *     bit  14      LEVEL_VALID set only with status OK
 *     bit  15      CONFIG_VALID set when the registers were loaded (OK or
 *                               GPIO_NOT_SAMPLED)
 * RDATA1       the whole port's IDR, bits 15..0
 * RDATA2       the whole port's ODR, bits 15..0
 * CRC_STATUS   the port's ANALOG mask: bit n set = pin n is in analog mode, so
 *              bit n of RDATA1 is 0 by construction and is not a sample. There
 *              is no CRC for this opcode; the register is reused rather than
 *              leaving a port IDR on the wire that silently contains unsampled
 *              zeros.
 *
 * The two VALID bits exist so that RDATA0 on its own, read by something that
 * ignored DIAG_STATUS, still cannot be mistaken for a LOW pin. That is also why
 * every refusal leaves RDATA0 at zero rather than 0xFFFF: 0xFFFF would carry
 * both VALID bits.
 */
#ifndef O2P_GPIO_DIAG_H
#define O2P_GPIO_DIAG_H

#include <stdbool.h>
#include <stdint.h>

#include "gpio_hal.h"
#include "regmap.h"

#define O2P_GPIO_PARAM(port, pin) ((uint16_t)(((unsigned)(port) << 8) | (unsigned)(pin)))
#define O2P_GPIO_PARAM_PORT(p)    ((uint8_t)((uint16_t)(p) >> 8))
#define O2P_GPIO_PARAM_PIN(p)     ((uint8_t)((uint16_t)(p) & 0xFFu))

/* ---- Bonded pins, STM32G071CBT7, LQFP48 ----
 *
 * Bit n set = pin n of that port reaches a pad. Taken from ST DS12232 Rev 5
 * (June 2025), Table 12 "Pin assignment and description", LQFP48/UFQFPN48
 * column, read 2026-09-10 - every row with a pin number there, and none with
 * "-". 44 I/Os. The local KiCad 10.0.5 library has no STM32G071CBTx symbol
 * (only the G081CBTx sibling, which lists the same 44), so it is not the
 * source. board_pins.h's O2P_LQFP48_* numbers agree with the same table.
 *
 * TWO PADS WITH A CAVEAT. Pins 33/34 are "PA11 [PA9]" and "PA12 [PA10]":
 * DS12232 Table 12 note 5 - PA9/PA10 can be remapped in place of PA11/PA12,
 * the default, through SYSCFG_CFGR1. This firmware never writes SYSCFG, so the
 * pads are PA11/PA12 and PA9/PA10 are pins 29/32. Were a remap ever added, the
 * PA11/PA12 GPIO bits would stop describing a pad, and this table would be the
 * place that has to learn about it.
 *
 * PF2 SHARES ITS PAD WITH NRST ("PF2-NRST" in DS12232 Table 12). Its GPIO
 * registers describe that pad only when the NRST_MODE option bits (FLASH_OPTR
 * 28:27) select 10,
 * GPIO: RM0444 Rev 6, 7.3.17 "Reset pin (PF2-NRST) in GPIO mode" (p. 237), and
 * 3.7.8 (p. 102). The factory value is 11, bidirectional reset (RM0444 Table
 * 17, p. 83), and nothing in src/ writes the option bytes - so on these probes
 * the pad is the reset pin, and a PF2 answer describes a GPIO cell that is not
 * connected to it. No runtime effect today either way: mcu.c never enables
 * GPIOF's clock, so PF0..PF2 answer ERR_GPIO_UNCLOCKED before any GPIOF
 * register is loaded. PF2 stays in the table because it IS bonded, and
 * refusing it as absent would be the wrong reason. */
#define O2P_GPIO_BONDED_A 0xFFFFu   /* PA0..PA15                         */
#define O2P_GPIO_BONDED_B 0xFFFFu   /* PB0..PB15                         */
#define O2P_GPIO_BONDED_C 0xE0C0u   /* PC6, PC7, PC13, PC14, PC15        */
#define O2P_GPIO_BONDED_D 0x000Fu   /* PD0..PD3                          */
#define O2P_GPIO_BONDED_F 0x0007u   /* PF0, PF1, PF2                     */

#define O2P_GPIO_R0_MODE_MASK    0x0003u
#define O2P_GPIO_R0_PULL_SHIFT   2u
#define O2P_GPIO_R0_PULL_MASK    0x000Cu
#define O2P_GPIO_R0_OPEN_DRAIN   0x0010u
#define O2P_GPIO_R0_ODR          0x0020u
#define O2P_GPIO_R0_LEVEL        0x0040u
#define O2P_GPIO_R0_AF_SHIFT     8u
#define O2P_GPIO_R0_AF_MASK      0x0F00u
#define O2P_GPIO_R0_LEVEL_VALID  0x4000u
#define O2P_GPIO_R0_CONFIG_VALID 0x8000u

enum {
    O2P_GPIO_MODE_INPUT  = 0u,
    O2P_GPIO_MODE_OUTPUT = 1u,
    O2P_GPIO_MODE_AF     = 2u,
    O2P_GPIO_MODE_ANALOG = 3u,
};

enum {
    O2P_GPIO_PULL_NONE     = 0u,
    O2P_GPIO_PULL_UP       = 1u,
    O2P_GPIO_PULL_DOWN     = 2u,
    O2P_GPIO_PULL_RESERVED = 3u,
};

typedef struct {
    uint16_t rdata[3];
    uint16_t analog_mask;   /* published in DIAG_CRC_STATUS */
} o2p_gpio_diag_result_t;

#if O2P_DEBUG_ENABLE
/* True if `pin` of `port` (encoded as above) reaches a pad on this package. */
bool o2p_gpio_pin_bonded(uint8_t port, uint8_t pin);

/* Validate `param`, take the snapshot, pack it. Returns the O2P_DMBOX_STATUS_*
 * the mailbox publishes; `out` is always fully written, zeros on a refusal. */
uint16_t o2p_gpio_diag_read(uint16_t param, o2p_gpio_diag_result_t *out);
#endif

#endif /* O2P_GPIO_DIAG_H */
