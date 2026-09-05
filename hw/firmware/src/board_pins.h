/* o2-probe Rev A - GPIO bindings for the STM32G071CBT7 (LQFP-48).
 *
 * hw_contract.h is generated from ../gen_sch.py and says which NET is on which
 * package pin. This file says which PORT/PIN/ALTERNATE-FUNCTION that package
 * pin actually is, and then asserts the two agree. Move a net in the schematic
 * and the build stops here rather than reading the wrong pin at runtime.
 *
 * FAB-READINESS.md:82 - "Firmware must use this final pin map."
 */
#ifndef O2P_BOARD_PINS_H
#define O2P_BOARD_PINS_H

#include "hw_contract.h"

/* --- LQFP-48 package pin -> port, for every pin this firmware binds -------
 * From ST DS12232 Table "Pin definitions", LQFP48 column. Kept as macros so
 * the static assertions below can compare against the generated contract.
 */
#define O2P_LQFP48_PA2   13
#define O2P_LQFP48_PA3   14
#define O2P_LQFP48_PA6   17
#define O2P_LQFP48_PA7   18
#define O2P_LQFP48_PB0   19
#define O2P_LQFP48_PB1   20
#define O2P_LQFP48_PB2   21
#define O2P_LQFP48_PA8   28
#define O2P_LQFP48_PA9   29
#define O2P_LQFP48_PC6   30
#define O2P_LQFP48_PA10  32
#define O2P_LQFP48_PB6   45
#define O2P_LQFP48_PB7   46

/* --- Bindings ------------------------------------------------------------ */

/* RS-485, USART1. PA9/PA10 are USART1 TX/RX on AF1. */
#define O2P_RS485_TX_PORT     GPIOA
#define O2P_RS485_TX_PIN      9u
#define O2P_RS485_TX_AF       1u
#define O2P_RS485_RX_PORT     GPIOA
#define O2P_RS485_RX_PIN      10u
#define O2P_RS485_RX_AF       1u

/* Direction control. PC6 carries NO USART1_DE alternate function on this part
 * - it has only TIM2_CH3 (AF2) and TIM3_CH1 (AF1). USART1's hardware DE exists
 * only on PA12 and PB3, neither of which reaches the THVD1410. So DE is a
 * plain output driven in software; see modbus_rtu.c for the TC-interrupt
 * release. PLAN.md:261 says "USART+DE"; that is not achievable on this board.
 *
 * R7 (47k) pulls DE down, so the transceiver is a receiver through MCU reset.
 */
#define O2P_RS485_DE_PORT     GPIOC
#define O2P_RS485_DE_PIN      6u

/* The expansion/recovery UART, USART2. PA2/PA3 are USART2 TX/RX on AF1.
 *
 * NOTHING ON A SHIPPING PROBE USES THIS. Since 2026-09-05 these two pins land
 * on J105/J106, a pair of solder-wire lands, and stop there: the expansion
 * connector J2 and the R12-R16 series pack were deleted in the BOM pass
 * (BOM-REDUCTION.md 3), but R15/R16 were NOT deletable, because this comment
 * and bridge_main.c were already using their pads as the bench-bridge tap. The
 * lands replace them and are a better version of the same thing - a wire land
 * rather than half of an unfitted resistor. The LQFP's 0.5 mm pitch is still
 * not a tap point.
 *
 * There is no direction pin here and there must not be one: this side is a
 * point-to-point TTL link to one lead, not a bus.
 */
#define O2P_EXP_UART_TX_PORT  GPIOA
#define O2P_EXP_UART_TX_PIN   2u
#define O2P_EXP_UART_TX_AF    1u
#define O2P_EXP_UART_RX_PORT  GPIOA
#define O2P_EXP_UART_RX_PIN   3u
#define O2P_EXP_UART_RX_AF    1u

/* I2C1 on PB6/PB7, AF6. Bus is capped at 100 kHz because the LMP91000 is
 * standard-mode only (PLAN.md:234). 4.7k pull-ups are fitted (R10/R11). */
#define O2P_I2C_SCL_PORT      GPIOB
#define O2P_I2C_SCL_PIN       6u
#define O2P_I2C_SCL_AF        6u
#define O2P_I2C_SDA_PORT      GPIOB
#define O2P_I2C_SDA_PIN       7u
#define O2P_I2C_SDA_AF        6u

/* LMP91000 MENB, active low, gates the AFE's I2C interface only. R17 (100k)
 * pulls it LOW, so the AFE is addressable through MCU reset - deliberate, so
 * I2C availability is deterministic (PLAN.md:234-236). */
#define O2P_AFE_MENB_PORT     GPIOB
#define O2P_AFE_MENB_PIN      0u

/* ADS1119 DRDY, open-drain, R19 (10k) pull-up. Falls when a conversion is
 * ready. There is no GPIO on the ADS1119 RESET pin - R18 holds it released and
 * recovery must go through the I2C RESET command. */
#define O2P_ADC_DRDY_PORT     GPIOB
#define O2P_ADC_DRDY_PIN      1u

/* Membrane-ring heater. PA8 is TIM1_CH1 on AF2.
 *
 * DANGER: PA7 is TIM1_CH1N, the complement of this very channel, and PA7 is
 * the analog rail monitor. TIM1 CH1N must never be enabled. See heater.c. */
#define O2P_HEATER_PWM_PORT   GPIOA
#define O2P_HEATER_PWM_PIN    8u
#define O2P_HEATER_PWM_AF     2u

/* 3V3A rail monitor, ADC1_IN7. The independent witness for a 3V3A brownout:
 * the ADS1119's own AVDD is 3V3A, so it cannot report its own supply failing.
 * Referenced to VREF+ = 3V3D, so absolute volts need the VREFINT calibration. */
#define O2P_VA_MON_PORT       GPIOA
#define O2P_VA_MON_PIN        7u
#define O2P_VA_MON_ADC_CH     7u

/* +12V_SW input-rail monitor, ADC1_IN6, through R26/R27.
 *
 * THIS PIN WAS NEVER READ until 2026-09-05. The rail monitors moved from the
 * ADS1119 to the MCU's own ADC in an earlier revision; VA_MON's half of that
 * migration landed and VIN_MON's did not. main.c went on sampling ADS1119 AIN3
 * and scaling it by the VIN divider, but AIN3 is ADC_RE_BUF - the buffered
 * reference electrode - so vin_mv was never the input rail, and because
 * O2P_F_VIN_LOW feeds supply_ok, the undervoltage half of the heater interlock
 * could not fire. Found by an adversarial review of the BOM pass. */
#define O2P_VIN_MON_PORT      GPIOA
#define O2P_VIN_MON_PIN       6u
#define O2P_VIN_MON_ADC_CH    6u

/* --- The contract ---------------------------------------------------------
 * Each assertion pairs "which net the schematic put on this package pin" with
 * "which package pin this port bit is". Both halves must move together.
 */
#define O2P_ASSERT_NET(net, lqfp) \
    _Static_assert(O2P_HW_NET_##net##_PIN == (lqfp), \
                   "gen_sch.py moved " #net " off LQFP48 pin " #lqfp \
                   " - update board_pins.h and re-check every user of it")

O2P_ASSERT_NET(RS485_TX,   O2P_LQFP48_PA9);
O2P_ASSERT_NET(RS485_RX,   O2P_LQFP48_PA10);
O2P_ASSERT_NET(RS485_DE,   O2P_LQFP48_PC6);
O2P_ASSERT_NET(I2C_SCL,    O2P_LQFP48_PB6);
O2P_ASSERT_NET(I2C_SDA,    O2P_LQFP48_PB7);
O2P_ASSERT_NET(AFE_MENB,   O2P_LQFP48_PB0);
O2P_ASSERT_NET(ADC_DRDY,   O2P_LQFP48_PB1);
O2P_ASSERT_NET(HEATER_PWM, O2P_LQFP48_PA8);
O2P_ASSERT_NET(VA_MON,     O2P_LQFP48_PA7);
O2P_ASSERT_NET(VIN_MON,    O2P_LQFP48_PA6);
O2P_ASSERT_NET(UART2_TX,   O2P_LQFP48_PA2);
O2P_ASSERT_NET(UART2_RX,   O2P_LQFP48_PA3);

/* PA7 doubles as TIM1_CH1N for the PA8 heater channel. If a future schematic
 * moves the heater off TIM1, this pairing stops being a hazard and heater.c's
 * guard can be revisited - so pin it here too. */
_Static_assert(O2P_HW_NET_VA_MON_PIN == 18 && O2P_HW_NET_HEATER_PWM_PIN == 28,
               "VA_MON/HEATER_PWM moved: recheck the TIM1_CH1/CH1N conflict");

#endif /* O2P_BOARD_PINS_H */
