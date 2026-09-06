/* Reading a configuration record written by an OLDER layout version.
 *
 * WHY THIS EXISTS, and it is not tidiness. Until 2026-09-06 a record whose
 * layout_version did not match exactly was discarded whole, and the probe came
 * up on defaults - which include slave address 3, 9600 baud and even parity.
 * A probe on the default transport survives that. A probe that an operator
 * moved to another address, baud or parity STOPS ANSWERING ITS MASTER the
 * moment it takes a firmware update, and there is no way back into it over the
 * bus. On a potted probe buried in a compost pile, "retrieve it and reflash
 * over SWD" is not a recovery procedure; it is the end of that probe.
 *
 * The argument that justified discarding the record was about the CALIBRATION,
 * and it is still correct: a version-2 cal_air_na was taken under the old
 * assumption that the air point sat in dry air, at a humidity nobody recorded,
 * so no honest cal_air_frac can be invented for it. But that argument reaches
 * exactly two fields. It never reached the slave address.
 *
 * So a migration carries forward everything that still means what it meant,
 * and discards ONLY what changed meaning:
 *
 *   carried   slave_addr, baud_code, parity_code      (reachability)
 *             rh_setpoint, dt_max_k, heater_max_duty,
 *             heater_pwm_hz, heater_kp, heater_ki     (heater tuning)
 *             sht_pulse_interval_h, tempco, cal_temp
 *   discarded cal_air_na -> 0, cal_air_frac -> 0, cal_p_hpa -> 0
 *
 * Zeroing the air point is what forces CAL_DEFAULT and keeps O2_COMP on its
 * sentinel until a fresh air point is taken. RECALIBRATION IS STILL REQUIRED
 * after the update; what is no longer required is a visit to the pile.
 *
 * Every layout is decoded through an EXPLICIT versioned struct, never by
 * casting the stored bytes to the current one. The layouts differ in size and
 * in field order - v2 is 28 bytes with slave_addr at 22, v3 is 32 with it at
 * 26, v4 is 32 with it at 28 - so a cast would read the baud code out of the
 * middle of a pressure.
 */
#ifndef O2P_CONFIG_MIGRATE_H
#define O2P_CONFIG_MIGRATE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "regmap.h"

/* Decode a stored 64-byte config record of a superseded layout version.
 *
 *   record    the raw bytes as they sit in flash
 *   len       how many of them there are; must be the whole record
 *   out       receives the migrated configuration, defaults-filled first
 *   out_seq   receives the record's sequence number, so the caller's
 *             higher-sequence-wins choice keeps working across the migration
 *
 * Returns false - and writes nothing - unless the record carries the config
 * magic, a layout version this function knows, an intact CRC for THAT layout,
 * and produces something o2p_config_valid() accepts. A migration that lands on
 * an invalid configuration is a failed migration, not a configuration.
 */
bool o2p_config_migrate(const void *record, size_t len,
                        o2p_config_t *out, uint32_t *out_seq);

#endif /* O2P_CONFIG_MIGRATE_H */
