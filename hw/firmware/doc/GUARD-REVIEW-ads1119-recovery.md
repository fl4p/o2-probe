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

Two of the three fail closed; the third has a stated gap, below. The DRDY
drain returns `O2P_ADS_IO` when the *transfer* fails and `O2P_ADS_DRDY` when
the transfer succeeds but the line still will not rise — the distinction
matters, because reporting a bus NACK as a pin fault is the same misdirection
with the sign flipped. The config check returns `O2P_ADS_IO` if the readback
transfer fails and `O2P_ADS_CONFIG` if the pattern differs; there is no path
where an unreadable register is treated as a match. The new fault bits are set
from the status, so an unevaluable conversion still raises one.

**The stated gap:** the config readback runs only on a channel/reference
change, so the twelve same-config conversions per cycle write WREG without
verifying it. A device that stops storing configuration during the final
eight-sample O2 phase has its readings averaged and PUBLISHED before the next
cycle's change detects it. That is not failing closed, and titling this
section "all three fail closed" — as an earlier version did — is the kind of
summary that survives review precisely because it sounds complete.

## 2. Monotonicity

Worse input cannot flip the verdict back to PASS. **This claim was false in
three successive versions of this document,** and is worth reading with
suspicion. Each time, an intermittent DRDY line that read low at the wrong
moment produced `O2P_ADS_OK` carrying the previous channel's conversion — a
worse input flipping the verdict to PASS, which is precisely what the sentence
denies. It is recorded here because a checklist item that keeps being answered
wrongly is more useful as a warning than as a reassurance. The drain is attempted
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
`convert_once()` therefore re-confirms DRDY is high immediately *after* START.

**That single sample did not close the hole, and saying it did was wrong.** A
floating line can read high at that sample and spuriously low on the very next
loop evaluation — microseconds later, long before an 11.1 ms or 50 ms
conversion could have finished — whereupon RDATA hands back "the most recent
conversion result" (SBAS925A 8.5.3.5), the previous channel, and the driver
accepts it as current. The failure survived two rounds of repair at
progressively longer odds without ever being eliminated.

The wait loop gates on `conversion_min_ms()`, so a low arriving before the
datasheet says a conversion can possibly have completed is rejected as noise.

**But the clock alone cannot close this, and claiming it did was the third
wrong answer to the same question.** "Earliest possible" rejects impossibly
early lows; it cannot authenticate WHICH conversion a plausible-looking low
refers to. With fCLK spec'd -2%/+2% (SBAS925A 6.5), a 20 SPS conversion can
still be running about 2 ms after the 49 ms gate opens, and a floating line
sampled low inside that interval passed every check and returned the previous
channel as OK. The window kept shrinking; it never closed. "Low odds" is not a
guard — it is the same defect with a longer mean time to failure.

What closes it is asking the device instead of the pin. Once the pin reads low
and the clock gate has opened, `convert_once()` reads the STATUS register and
proceeds only if the converter itself reports a result ready (SBAS925A
8.5.3.6, bit 7). **The status register is the authority; the pin is a rumour**
— and a rumour that agrees with the clock is still a rumour.

That also gives the timeout path real evidence: on timeout the driver reads
STATUS and reports a pin fault only when the device says a result IS ready and
the pin never said so. Otherwise the device did not convert, which is not a
pin fault and is no longer labelled as one.

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
visible in the published fault word. Recovery was originally justified as **not** silent, on the grounds that the
failure which stranded the result already raised a fault bit in the cycle where
it happened. **That justification does not survive the reporting cadence.**
`cycle_begin()` clears `g_cyc.faults` every second, while the deployed uplink
is every five minutes, and the cumulative `I2C_ERRS` counter sits in the
diagnostic block outside the polled primary registers (`regmap.h:58`). A
transient that strands a result and then heals will normally never reach
ChirpStack or Home Assistant: roughly 299 cycles in 300 overwrite it.

So the channel still cannot say "I recovered from something" — only "I am fine
now", which is the same shape of silence this document is about. Closing it
needs a **cumulative** count of drained stale results in the diagnostic block
beside `I2C_ERRS`. That register is not added here: `regmap.h`/`regmap.c` and
`O2P_REG_DIAG_COUNT` are being edited by the Rev B work in the same tree, and
adding a register from two directions at once is how register maps come apart.
Recorded as owed.

## 7. Known-bad calibration

The target failure is constructible and has been observed on this board.
Putting PB1 back into analog mode (`MODER |= 3u << 2`) reproduces the exact
original defect; the guard must then fail every conversion rather than
returning the previous channel. This is not a hypothetical: it is the failure
that got a healthy ADS1119 replaced.

`ads1119.c` is in no test build — the suite is host-native logic only — so
"98 tests pass" is silent about the drain, the status confirmation and the
config readback. The calibration was therefore owed against real hardware, and
**it has now been run (2026-09-05, first article, firmware 39b2d97).**

| | Baseline | PB1 forced to analog | PB1 restored |
|---|---|---|---|
| `FAULTS` | `0x8001` | **`0xa001`** | `0x8001` |
| `O2_RAW` | 100.81 uA | **`0x8000`** | 100.81 uA |
| `VREF_MON` | 2492 mV | **`0xffff`** | 2492 mV |
| `I2C_ERRS` | 0 | **0** | 0 |

`0xa001` is `HEATER_DISABLED | ADS_DRDY_STUCK | SETTLING`: bit 13 fires on the
exact defect that cost a week, both channels go to their invalid sentinels, and
no oxygen number is published.

**`I2C_ERRS` staying at 0 is the result worth keeping.** The failure was
attributed to the PIN and not to the bus — the discrimination whose absence
got a healthy ADS1119 desoldered. A guard that fired but blamed I2C would have
passed a naive version of this test and still sent the next technician after
the wrong component.

The restore column is the second half of the calibration and was nearly left
out. Removing the defect cleared the fault and the channel recovered to the
same 100.81 uA **without a reset** — uptime ran straight through — which
exercises the drain against a genuinely latched DRDY on real hardware. That
was the first review's finding: a permanent lockout that a potted probe could
not come back from. It is now demonstrated fixed rather than argued.

**The config readback was calibrated too, on the same day.** It needs a device
that stops storing configuration, which no GPIO write can produce, so the real
device was made to lose its configuration at the one instant that matters: a
hardware breakpoint at `0x08006bb4`, between `write_cfg()` and the readback,
then an ADS1119 RESET command driven onto the real bus by hand from the halted
MCU's own I2C1 peripheral, then resume.

| step | observed |
|---|---|
| break between write and readback | `HIT 0x08006bb4` |
| RESET delivered over the real bus | `ISR = 0x1` (transfer complete) |
| driver's mismatch path executed | `HIT 0x08006bec` -> `O2P_ADS_CONFIG` |
| fault word | **`g_cyc.faults = 0x4000`** |

`0x4000` is bit 14, `ADS_CONFIG_LOST`, **and only that bit**. That is the whole
point of separating it: the bus was demonstrably healthy — it had just carried
the RESET that caused the fault — and the device disagreed. A guard that
reported this as `I2C_FAIL_ADS` would have sent a technician after a bus that
was working.

Note the shape of this fixture. Nothing was patched to make the guard fire: the
real device really stopped storing its configuration, the real driver noticed
by reading it back, and the real fault word carried the result. A hand-set flag
would have tested the design that was intended rather than the one that was
built.

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
- **Config verification: ~630 us per channel/reference change, ~1.9 ms per
  1 s cycle** (three changes: VREF, VIN, O2). WREG plus RREG is at least
  27 + 36 SCL clocks, and **this bus runs at 100 kHz, not 400 kHz**
  (`i2c1.c:6`, `O2P_I2C_TIMINGR` taken from the RM0444 16 MHz example). Two
  earlier versions of this figure were wrong — first "150 us", then "165 us" —
  both because the arithmetic was done at a bus speed the driver does not use.
  The duplicate WREG on the change path is harmless in single-shot with no
  conversion in flight, but it is real traffic and it is counted here. Against
  a ~0.53 s ADC budget in a 1 s loop, none of this is close to binding.
- **Status confirmation: one 4-byte RREG per conversion**, 36 SCL clocks at
  100 kHz, about 360 us x 15 conversions = **~5.4 ms per cycle**. An
  independent review computed the full worst case at roughly 620 ms against the
  1 s deadline before this was added, so the authoritative read fits with a
  wide margin. Relative to what it buys this is the cheapest item in the
  document: it is the only check here that AUTHENTICATES a reading rather than
  bounding it.
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
