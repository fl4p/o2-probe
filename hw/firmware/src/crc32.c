#include "crc32.h"

/* Nibble-wise, with a 16-entry table.
 *
 * The byte-wise table is 1 KiB, which is 0.4 % of an image whose whole point
 * is fitting in a slot, and it lives in the bootloader too. The bitwise form
 * needs no table and is about four times slower. The nibble form costs 64
 * bytes and runs at roughly 1.3 MB/s at 16 MHz - fast enough that verifying
 * a 52 KiB slot is ~40 ms, which is why the verify can afford to be split
 * into kilobyte slices and still finish inside one Modbus poll interval.
 */
static const uint32_t k_nibble[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu,
    0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
    0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
    0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

uint32_t o2p_crc32_update(uint32_t crc, const void *data, size_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < len; i++) {
        crc ^= p[i];
        crc = (crc >> 4) ^ k_nibble[crc & 0x0Fu];
        crc = (crc >> 4) ^ k_nibble[crc & 0x0Fu];
    }
    return crc;
}

uint32_t o2p_crc32(const void *data, size_t len)
{
    return o2p_crc32_final(o2p_crc32_update(O2P_CRC32_INIT, data, len));
}
