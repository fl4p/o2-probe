/* I2C1 master on PB6/PB7.
 *
 * One bus, four devices: ADS1119 0x40, SHT45 0x44, LMP91000 0x48, TMP117 0x49
 * (DESIGN.md "Address map"). The bus is capped at 100 kHz because the
 * LMP91000 is standard-mode only (PLAN.md:234) - the fastest device does not
 * get to set the speed.
 *
 * Every call is bounded in time and returns a status. There is no "retry
 * forever" path: a wedged device must become a fault bit on the next uplink,
 * not a probe that stops answering the bus.
 */
#ifndef O2P_I2C1_H
#define O2P_I2C1_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    O2P_I2C_OK = 0,
    O2P_I2C_NACK,      /* device did not acknowledge - absent or unpowered */
    O2P_I2C_TIMEOUT,   /* transfer did not complete in time */
    O2P_I2C_BUSY,      /* bus held by something else; recovery attempted */
    O2P_I2C_ARG,
} o2p_i2c_status_t;

void o2p_i2c1_init(void);

/* Total errors seen since boot, published as a diagnostic register. A count
 * that climbs slowly is a marginal pull-up or a cable; one that jumps is a
 * device dying. Neither is visible from a single fault bit. */
uint16_t o2p_i2c1_error_count(void);

o2p_i2c_status_t o2p_i2c1_write(uint8_t addr7, const uint8_t *buf, size_t len);
o2p_i2c_status_t o2p_i2c1_read(uint8_t addr7, uint8_t *buf, size_t len);
/* Write then repeated-START read: the register-pointer idiom every device on
 * this bus uses. */
o2p_i2c_status_t o2p_i2c1_write_read(uint8_t addr7,
                                     const uint8_t *wbuf, size_t wlen,
                                     uint8_t *rbuf, size_t rlen);

/* Probe an address with a 0-byte transfer without bumping the bus error count
 * if the device is absent (NACK). Returns O2P_I2C_OK if ACKed, O2P_I2C_NACK if
 * not present. */
o2p_i2c_status_t o2p_i2c1_probe(uint8_t addr7);

/* Bit-bang nine clocks to free a slave that is holding SDA low - the classic
 * wedge after a reset in the middle of a read. Called automatically when a
 * transfer finds the bus busy; exposed for the bring-up self-test. */
void o2p_i2c1_bus_recover(void);

#endif /* O2P_I2C1_H */
