# Guard review: ADS1119 stale-DRDY recovery, config re-verification, fault surfacing

Three defects found by adversarial review of the guards landed on 2026-09-04
(`AFE-BRING-UP-POSTMORTEM.md` section 5.1). This document answers the eight
guard-checklist questions for the fixes *before* they land, as required.

## What changes

1. **Stale-DRDY recovery.** The pre-START DRDY check in `convert_once()` now
   attempts to drain an unread result before condemning the part.
2. **Config re-verification at runtime.** `o2p_ads1119_convert()` verifies the
   config register on every channel/reference change, making `O2P_ADS_CONFIG`
   reachable outside `o2p_ads1119_init()`.
3. **A distinct fault bit.** `O2P_ADS_DRDY` no longer collapses into
   `O2P_F_I2C_FAIL_ADS`; it raises the renamed bit 13,
   `O2P_F_ADS_DRDY_STUCK`.

## 1. Unevaluable input must not read as OK

All three fail closed. The DRDY drain returns `O2P_ADS_DRDY` unless the line is
*observed* high afterwards — a failed drain transfer, or a line that never
rises, both keep the failing status. The config check returns `O2P_ADS_IO` if
the readback transfer fails and `O2P_ADS_CONFIG` if the pattern differs; there
is no path where an unreadable register is treated as a match. The new fault
bit is set from the status, so an unevaluable conversion still raises it.

## 2. Monotonicity

Worse input cannot flip the verdict back to PASS. The drain is attempted
**once** per conversion and only ever converts "stuck low" into either "still
stuck low" (fail) or "released, conversion proceeds". A permanently
misconfigured pin — the original bug, `MODER = 11`, `IDR` reads 0 forever —
drains, re-reads 0, and fails, every conversion, for as long as it lasts. The
far tail (line dead) and the near miss (one stale latch) both behave correctly,
and the far tail is the one that keeps failing.

## 3. Preconditions

`O2P_ADC_DRDY_PORT->MODER` is cleared to input mode in `o2p_ads1119_init()`,
which runs before any conversion. The drain uses `o2p_i2c1_write_read()`, the
same transport the conversion itself uses, so it cannot succeed where the real
read would fail. The config check runs only on the change path, which is
exactly where a new config has just been written — verifying a register we did
not just write would prove nothing.

## 4. Source of truth

The DRDY checks read `IDR` directly, the same register the wait loop reads —
no proxy. The config check reads the ADS1119's own configuration register back
over the bus rather than trusting `s_last_cfg`, which is a *host-side cache of
intent* and by construction cannot detect the device disagreeing with it.

## 5. Persistence

Nothing caches a verdict. `s_last_cfg` is set to `0xFFu` on every non-OK
status, so a failed conversion cannot leave the driver believing the device is
configured. A failed probe therefore never caches "verified clean" — it caches
"unknown", which forces the full change path (write, verify, throwaway) next
time.

## 6. Provenance

This is the defect being fixed: the previous code produced a distinct
`O2P_ADS_DRDY` status and then destroyed it at `main.c:318`, reporting an
*I2C* fault for a *pin* failure. After this change the two are separately
visible in the published fault word. Recovery is deliberately **not** silent
in the sense that matters: the I2C or timeout failure that stranded the result
already raised its own fault bit in the cycle where it happened, so draining
the leftover on a later cycle hides nothing that was not already reported.

## 7. Known-bad calibration

The target failure is constructible and has been observed on this board.
Putting PB1 back into analog mode (`MODER |= 3u << 2`) reproduces the exact
original defect; the guard must then fail every conversion rather than
returning the previous channel. This is not a hypothetical: it is the failure
that got a healthy ADS1119 replaced, so the guard is calibrated against a real
known-bad, not an imagined one.

## 8. Fix vs mute

Fix 1 changes the underlying quantity: an unread result is *drained* rather
than annotated, so the channel recovers instead of staying dead until
power-cycle. Fix 2 makes a check that did not exist actually run — the
comment it replaces asserted a per-conversion config verification that no code
performed, which is the purest form of a mute button. Fix 3 removes a mute by
letting a distinct failure reach the operator as a distinct bit.

## Runtime cost

- **Steady state: zero.** The drain executes only when DRDY is already low,
  which cannot happen on a healthy cycle. No extra bus traffic on the happy
  path.
- **Config verification: 3 two-byte reads per 1 s cycle** (one per
  channel/reference change: VREF, VIN, O2), roughly 150 us of bus time at
  400 kHz on a bus that is otherwise idle for most of the second.
- **Failure state:** one additional 1-byte-write + 2-byte-read per conversion
  while DRDY is stuck. Bounded, and only in a state that is already faulted.

## What this does NOT fix

The 12 same-config conversions per cycle still write the config without
reading it back. A device that stops storing configuration mid-cycle is
therefore caught at the next channel change — within one cycle — rather than
at the next conversion. That is a deliberate trade of ~50 us of bus time per
conversion against a one-cycle detection delay, and it is stated here rather
than left for a reader to discover.
