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

The case this reasoning originally missed is the one in between: an
**intermittent** line (floating pin, open R19) can read low, drain, then read
high by chance, which halves the detection probability rather than eliminating
it. A deterministic dead line was always caught; a noisy one was not.
`convert_once()` therefore re-confirms DRDY is high immediately *after* START,
where the fastest data rate in use (1000 SPS, 1 ms) guarantees it must be.
Monotonicity means little if the far tail is the only tail tested.

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

**This was not true when first written.** Only the change path invalidated;
the steady-state return carried 12 of the 15 conversions per cycle and passed
failures through with the cache intact. It happened to be safe because
`main.c` uses three mutually distinct configs and `accumulate()` abandons the
phase on failure, so a failure was always followed by a change — the driver
was correct only because of what today's caller does. The fast path now
invalidates too.

## 6. Provenance

This is the defect being fixed: the previous code produced a distinct
`O2P_ADS_DRDY` status and then destroyed it at `main.c:318`, reporting an
*I2C* fault for a *pin* failure. Two further instances were found by review
after the first attempt: the drain returned "not recovered" for a failed
*transfer*, publishing a bus fault as a pin fault — the same misreport with
the sign flipped — and `O2P_ADS_CONFIG`, which fix 2 had just made reachable,
had no bit of its own and landed on `I2C_FAIL_ADS`. Both now report
themselves. **Making a check reachable without giving it a name is only half
a guard**, and the published fault map is only as good as the decoders that
read it: `tech/chirpstack/rs485-ls-decoder.js` holds a positional copy of this
enum, and "no firmware writes bit 13" did not mean "nothing reads bit 13". After this change the two are separately
visible in the published fault word. Recovery is deliberately **not** silent
in the sense that matters: the I2C or timeout failure that stranded the result
already raised its own fault bit in the cycle where it happened, so draining
the leftover on a later cycle hides nothing that was not already reported.

## 7. Known-bad calibration

The target failure is constructible and has been observed on this board.
Putting PB1 back into analog mode (`MODER |= 3u << 2`) reproduces the exact
original defect; the guard must then fail every conversion rather than
returning the previous channel. This is not a hypothetical: it is the failure
that got a healthy ADS1119 replaced.

**But that known-bad was observed against the code this guard replaces, not
against the guard as landed.** `ads1119.c` is in no test build — the suite is
host-native logic only — so "98 tests pass" is silent about the drain, the
post-START confirmation and the config readback. Calibration against the real
known-bad is therefore still OWED: put PB1 back into analog mode on the bench
and confirm the fault word reports `ADS_DRDY_STUCK`, with no oxygen reading
published.

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
- **Config verification: ~165 us per channel/reference change, ~500 us per
  1 s cycle** (three changes: VREF, VIN, O2). RREG is a four-byte two-frame
  transaction (SBAS925A 8.5.3.6) at roughly 95 us, and the change path also
  issues a second `write_cfg()` of about 70 us on top of the one
  `convert_once()` already performs. An earlier version of this section said
  "150 us" and omitted the duplicate write entirely — understated by ~3x.
  The duplicate WREG is harmless in single-shot with no conversion in flight,
  but it is real traffic and it is counted here.
- **Failure state:** one additional 1-byte-write + 2-byte-read per conversion
  while DRDY is stuck. Bounded, and only in a state that is already faulted.

## What this does NOT fix

The 12 same-config conversions per cycle still write the config without
reading it back. A device that stops storing configuration mid-cycle is
caught at the next channel change — within one cycle — rather than at the next
conversion. That is a deliberate trade of bus time against detection latency.

**Say the consequence out loud, because "within one cycle" sounds harmless:**
the O2 phase is last, so a device that loses its configuration during the
eight O2 conversions is detected at the *next* cycle's VREF change — after
`finish_o2()` has already averaged and published those eight conversions,
taken on an unverified configuration, with no fault set. One plausible number
goes out before the guard speaks. Closing that costs a readback per
conversion; it has not been paid, and this is why a future reader might
decide to pay it.
