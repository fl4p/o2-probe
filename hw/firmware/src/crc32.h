/* CRC-32, the zlib/PNG parameterisation: reflected, polynomial 0x04C11DB7,
 * initial value 0xFFFFFFFF, final inversion.
 *
 * The parameterisation is not arbitrary. The value this computes is the one
 * Python's `zlib.crc32` and `binascii.crc32` produce, so the number a field
 * technician sends to the probe can be computed from firmware.bin with a
 * one-line command and no dependency on any tool written here. An update
 * protocol whose checksum can only be computed by its own tooling is one
 * hand-typed number away from being unverifiable.
 *
 * Not to be confused with the CRC-16/MODBUS in modbus_pdu.c, which protects
 * one frame on the wire. This protects a whole image across a transfer, a
 * flash erase, a copy and a reset.
 */
#ifndef O2P_CRC32_H
#define O2P_CRC32_H

#include <stddef.h>
#include <stdint.h>

/* Running form: start with O2P_CRC32_INIT, feed chunks, finish. The image is
 * checked in kilobyte slices between Modbus polls, so the running form is the
 * one that actually gets used; o2p_crc32() is the convenience wrapper. */
#define O2P_CRC32_INIT 0xFFFFFFFFu

uint32_t o2p_crc32_update(uint32_t crc, const void *data, size_t len);

static inline uint32_t o2p_crc32_final(uint32_t crc) { return ~crc; }

uint32_t o2p_crc32(const void *data, size_t len);

#endif /* O2P_CRC32_H */
