/* Common MCU includes and the millisecond tick.
 *
 * Direct CMSIS register access rather than HAL or LL. This firmware touches
 * five peripherals, two of them (USART1 framing, I2C1 error recovery) in ways
 * the HAL state machines actively get in the way of, and it has to share
 * 128 KiB of flash with an RS-485 bootloader that does not exist yet. Register
 * code is also what an adversarial reviewer can actually check against RM0444.
 */
#ifndef O2P_MCU_H
#define O2P_MCU_H

#include "stm32g0xx.h"

#include <stdbool.h>
#include <stdint.h>

/* SYSCLK. HSI16 with HSIDIV = /1, no PLL.
 *
 * Nothing here needs speed - the sample loop is 1 Hz and the bus is 9600 baud
 * - and the board's whole purpose is a sub-microamp front end sitting beside
 * an ADS1119 whose modulator runs at 256 kHz. Every megahertz of core clock is
 * digital noise looking for a way into that. 16 MHz also divides to 9600 baud
 * with 0.02 % error (BRR = 1667).
 */
#define O2P_SYSCLK_HZ 16000000u

/* RESET_CAUSE is (RCC_CSR >> 24) & 0xFF, and it is a BITFIELD, not an
 * enumeration - two causes can be set at once. On STM32G0 the flags sit at
 * CSR bits 25..31, so after the shift:
 *
 *   bit 0  -            (never set)
 *   bit 1  0x02  OBL    option-byte loader
 *   bit 2  0x04  PIN    NRST pin
 *   bit 3  0x08  PWR    BOR / power-on
 *   bit 4  0x10  SFT    software
 *   bit 5  0x20  IWDG   independent watchdog
 *   bit 6  0x40  WWDG   window watchdog
 *   bit 7  0x80  LPWR   low-power
 *
 * 0xFFFF is the sentinel for "could not be recovered": an application under a
 * bootloader that clears RCC_CSR without parking it. No real combination can
 * reach it, since the real domain is one byte. */
#define O2P_RESET_CAUSE_UNKNOWN 0xFFFFu

void o2p_clock_init(void);

/* Free-running millisecond counter from SysTick. Wraps after 49 days; every
 * comparison below is written as a subtraction so the wrap is harmless. */
uint32_t o2p_millis(void);
static inline bool o2p_elapsed(uint32_t since_ms, uint32_t span_ms)
{
    return (uint32_t)(o2p_millis() - since_ms) >= span_ms;
}
void o2p_delay_ms(uint32_t ms);

/* Independent watchdog, ~4 s. Deliberately long: it must catch a hung probe,
 * not a slow flash erase. See o2p_wdt_feed's comment on what it must NOT mask. */
void o2p_wdt_init(void);
void o2p_wdt_feed(void);

/* Reset cause latched at boot and published in the diagnostic block, then
 * cleared - otherwise the flags accumulate and every later reset looks like a
 * watchdog reset. The byte is RCC_CSR bits 31:24, so bit 1 is OBLRSTF, 2
 * PINRSTF, 3 PWRRSTF, 4 SFTRSTF, 5 IWDGRSTF, 6 WWDGRSTF, 7 LPWRRSTF. */
uint16_t o2p_reset_cause(void);

/* True if this reset could have interrupted the analog rails, and therefore
 * the cell bias. Computed from the named RCC_CSR masks at latch time rather
 * than from bit arithmetic on the published byte.
 *
 * On STM32G0 there is no separate brown-out flag: PWRRSTF is documented as the
 * "BOR or POR/PDR" flag, so it covers both. A pin reset is included because
 * NRST is exposed on J3 and nothing tells us what else the person holding it
 * was doing to the board. */
bool o2p_reset_was_power_cycle(void);

#ifndef O2P_DEBUG_ENABLE
#define O2P_DEBUG_ENABLE 1
#endif

#if O2P_DEBUG_ENABLE
extern volatile bool g_exec_active;
extern volatile uint32_t g_exec_start_ms;
extern volatile uint32_t g_exec_timeout_ms;
void o2p_exec_timeout_trampoline(void);
void o2p_exec_fault_trampoline(void);
#endif

#if O2P_DEBUG_ENABLE
uint32_t o2p_crash_read_reg(uint8_t index);
void o2p_crash_clear(void);
void o2p_crash_set_breadcrumb(uint32_t val);
#else
static inline uint32_t o2p_crash_read_reg(uint8_t index) { (void)index; return 0u; }
static inline void o2p_crash_clear(void) {}
static inline void o2p_crash_set_breadcrumb(uint32_t val) { (void)val; }
#endif

#endif /* O2P_MCU_H */
