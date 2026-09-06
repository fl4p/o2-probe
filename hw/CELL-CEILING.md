# The 60 °C cell ceiling, the derated deployment ceiling, and what the firmware actually does

**Status:** finding, 2026-09-06. Arithmetic and code citations verified in this
document; the deployment decision it raises is Fab's, not mine.

**Scope note.** Unlike `DEW-MARGIN-IS-BLIND.md`, nothing here depends on the
bare, unpotted bench article. This is datasheet limits, the Magnus curve, the
design record, and the shipped source. It transfers.

## 1. The question

The Codex xhigh review of 2026-09-06 (finding 11) claimed that at 60 °C
saturated pile gas, the heater-only operating envelope is *empty*: reaching the
cell's 90 %RH continuous limit by heating alone needs ~62.3 °C, above the cell's
own 60 °C temperature limit. This document checks that, finds where the envelope
actually closes, and then asks what the firmware does about it.

## 2. The envelope closes at 57.8 °C, not 60 °C

Heating gas without adding or removing water conserves vapour pressure, so
`RH' = e_s(T_pile) / e_s(T_local)`. Using the firmware's own Magnus constants
(`psychro.h:19-27`, A=17.62, B=243.12, es0=6.112 hPa):

| pile T (sat.) | e_s | local T for 90 %RH | heater ΔT | verdict |
|---|---|---|---|---|
| 40 °C |  73.67 hPa | 41.99 °C | +1.99 K | ok |
| 45 °C |  95.80 hPa | 47.06 °C | +2.06 K | ok |
| 50 °C | 123.45 hPa | 52.13 °C | +2.13 K | ok |
| 55 °C | 157.74 hPa | 57.20 °C | +2.20 K | ok |
| 58 °C | 182.02 hPa | 60.25 °C | +2.25 K | **needs 60.2 °C — over the cell's rating** |
| 60 °C | 199.93 hPa | 62.28 °C | +2.28 K | **needs 62.3 °C** |
| 65 °C | 251.47 hPa | 67.35 °C | +2.35 K | **pile alone is over the rating** |
| 75 °C | 389.30 hPa | 77.51 °C | +2.51 K | **pile alone is over the rating** |

The review's 62.3 °C at the 60 °C point reproduces exactly. But the boundary is
not at 60 °C:

> **The envelope closes at a saturated pile temperature of 57.76 °C**, where the
> required local temperature reaches exactly 60.00 °C. Above that, no heater
> duty satisfies both DS-0637 limits simultaneously.

## 3. The heater is not the problem — the cell's temperature ceiling is

Note the fourth column. Across the entire 40–75 °C range, going from saturated
to 90 %RH costs a strikingly constant **2.0–2.5 K**. That is a trivial thermal
ask: at the bench-measured θ ≈ 117 K/W it is roughly 17–21 mW, a couple of
percent duty.

So the humidity job is easy and the main-board heater can plainly do it. What
fails is the *temperature* job, and heating makes temperature worse. The two
requirements only fight each other inside the last ~2.2 K of headroom below
60 °C. Above 60 °C pile gas the humidity question is moot — the cell is out of
its temperature rating regardless of what any heater does.

**This means the ring-heater question is not what these limits decide.** A ring
heater delivers the same 2 K more evenly; it does not create temperature
headroom that does not exist. The open decision here is the *cell*, or the
thermal architecture that keeps the cell below pile temperature — not the
heater topology.

## 4. The design record already knew this, and reached the same number

`PLAN.md` (in `ha/farming` history at `da22fd5^:o2-probe/PLAN.md`, lines
207–211 — the file did **not** come across in the repo split and is absent from
this repository), from an earlier Codex review:

> **Deployment ceiling corrected:** with the heater riding up to ~4 K above pile
> gas, the cell's +60 °C limit caps supported pile-gas temperature at
> **~56–58 °C**, not 60 (Codex). TEMP_OVER flag fires at the derated ceiling;
> > 60 °C cell temperature invalidates data per
> `compostlab/research/COMPOST-O2.md` §6.

That earlier ceiling came from a completely different mechanism — the heater's
own ~4 K rise above gas. The humidity-envelope closure above comes from the
Magnus curve and the 90 %RH limit. **Two independent routes, 56–58 °C and
57.76 °C.** They agree, which is worth more than either alone.

## 5. Neither half of that decision is in the firmware

**5a. The derated ceiling was never implemented.** `main.c:52` sets
`O2P_TEMP_OVER_C100 6000` — 60.00 °C, the raw datasheet number, not the
56–58 °C derated ceiling PLAN.md specified. `TEMP_OVER` therefore fires ~2–4 K
too late.

Worse, `main.c:321-323` tests **gas** temperature:

```c
/* The temperature that matters for the cell's rating is the gas it sees. */
int16_t t_gas = g_cyc.chamber_ok ? g_cyc.t_chamber : g_cyc.t_tip;
if ((g_cyc.chamber_ok || g_cyc.tip_ok) && t_gas > O2P_TEMP_OVER_C100) {
```

The comment's premise is exactly what PLAN.md corrected. The rating applies to
the *cell*, and with the heater on, the cell rides above the gas. Gas at
59.9 °C with the heater lifting 4 K puts the cell near 64 °C with no fault
raised. The derating exists precisely to close that gap and it is not there.

**5b. The invalidation rule was inverted, and the citation for the inversion
points at the wrong thing.** `faults.h:10-15`:

> `- TEMP_OVER does NOT invalidate. PLAN.md:211-228 (decision 2026-08-27)`
> `deliberately deploys the SGX cell above its 60 C rating [...]`
> `This overrides compostlab research/COMPOST-O2.md section 6.`

and `faults.c:9-12` locks it in:

```c
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_TEMP_OVER) == 0,
               "TEMP_OVER must not invalidate: ... (PLAN.md:211-228)");
```

Checking the cited range: **PLAN.md lines 211–228 are the I²C address map and
the expansion-connector specification.** They contain no decision about fault
masks. The one adjacent sentence that *is* about this topic — line 210 — says
the opposite: "> 60 °C cell temperature **invalidates** data".

So the policy is asserted, compile-time-locked, and attributed to a passage
that says the reverse, in a file no longer present in the repository. The
`_Static_assert` comment even warns off "someone who has not read
PLAN.md:211-228" — a reader who follows that pointer finds an I²C table.

**5c. The stated justification does not hold against the document it
overrides.** `faults.h` argues that discarding the reading "would throw away the
data the instrument was built for". But `COMPOST-O2.md` §6 does not discard
anything: `invalid` there is a state in the Home Assistant alarm logic, and the
section explicitly says *"Do not convert a missing or invalid value to zero"*.
Marking O₂ invalid above the cell rating suppresses the low-O₂ **alarm
thresholds**; the sample, the temperature, and the trend all still log. The
override answers an objection the source never made.

## 6. What is and is not settled

Settled:

- The envelope closes at **57.76 °C** saturated pile gas. Above that, DS-0637's
  60 °C and 90 %RH limits cannot both be met by heating.
- The humidity half of the problem costs only ~2.2 K and is well within the
  main-board heater. The temperature half has no heater solution at all.
- `TEMP_OVER` fires at 60 °C on **gas**, not at the derated ceiling on the
  **cell**, contrary to the design record.
- `faults.h:10` and `faults.c:11` cite PLAN.md for the opposite of what
  PLAN.md says, and PLAN.md is not in this repository.

Not settled, and needing Fab:

- **Whether operating the cell above its rating is acceptable at all.** The
  argument for it (the thermophilic phase is the phase worth observing) is
  real. But above 60 °C SGX makes no accuracy claim, and the degradation is
  cumulative, not merely an extrapolation error — the current framing treats it
  as arithmetic extrapolation only.
- **Whether 40–65 °C stays the spec.** `PLAN.md` set it. The top 7 K of it is
  outside the cell's rating by construction.
- If the ceiling stands, the honest options are a cell with a higher rating,
  drawing gas out to a cell held below pile temperature (with the tube heated
  against condensation), or narrowing the spec and flagging the thermophilic
  peak as unmeasured.

## 7. Recommended actions

1. **Restore `PLAN.md` to this repository.** Multiple load-bearing firmware
   comments cite it by line number and it is not here. Until then, every
   `PLAN.md:NNN` citation in `firmware/src/` is unverifiable in-tree.
2. **Fix the two citations in `faults.h` and `faults.c`** regardless of which
   way the policy goes. A compile-time lock with a false citation is the
   mechanism that stops the policy being revisited.
3. **Decide 5a on its own merits**: either implement the derated ceiling and
   test the cell rather than the gas, or record why 60 °C-on-gas supersedes the
   PLAN.md derating.
4. **Re-open the invalidation question** with §5c on the table, since the
   override's stated reason does not survive reading the overridden source.

There is **no bench experiment queued by this document**. It is a specification
and source-fidelity finding, and the answers are decisions, not measurements.
