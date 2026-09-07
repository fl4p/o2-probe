# RH step test 2026-09-07 - run conditions

Recorded during the run, before analysis, so the assumptions are on the record.

| item | value | source |
|---|---|---|
| barometric pressure | **965 hPa** | Fab's phone, 2026-09-07 ~07:00Z |
| pressure basis | taken as **station** (what the cell sees) | assumed; implies ~400 m, self-consistent for a phone barometer. If the reading was sea-level-reduced the true station value is lower. |
| dilution reference | **-0.1052 %/hPa** | -100/(965 - p_w), p_w ~14.3 hPa |
| firmware `ASSUMED_P_HPA` (0x0042) | 930 hPa | **wrong by +3.6 % for this bench** - never set for this location |
| vessel A | glass tankard, whole body fits, granular desiccant | **vented** - loose ceramic lid, confirmed by photo |
| vessel N | saturated NaCl slurry | not yet used |
| article | assembled, in the unibody | not potted, not tubed |
| logger | `o2p_poll.py` @ 5 s -> `modbus-poll-2026-09-07.csv` | with the 48d3d8b reopen fix |

## Vessel A as built (photo, 2026-09-07)

![Probe in vessel A](rh-step-2026-09-07-vessel-A.png)

A glass tankard, granular desiccant filling the base, the probe standing
upright in it, and a heavy two-tone ceramic lid **resting** on the rim.

What the photo settles, and what it raises:

* **VENTING: confirmed adequate.** The lid is a domed ceramic cap sitting loose
  on a glass rim, not a screw closure and not a gasket. It cannot hold a
  pressure difference, which is what section 4b of `RH-STEP-TEST.md` requires -
  a rigid *sealed* vessel changes total pressure instead of partial pressure
  and would predict "no dilution" from a healthy cell. This one is effectively
  vented while still restricting exchange with the room. The open item is
  closed.
* **The probe stands directly IN the desiccant.** Harmless for the dry leg, and
  it maximises coupling to the drying medium, which is why the jar dried as
  fast as it did. **It must NOT be repeated for vessel N.** The board is
  unpotted; over a saturated slurry the probe has to be suspended clear of the
  liquid with something inert underneath, per section 5.
* **Thermal mass and shading are large.** Glass plus a ceramic lid plus a bed of
  desiccant is a substantial thermal buffer, which is part of why the step held
  to 0.12 K. It also means the vessel's own equilibration is slow, and slow
  vessel equilibration is a candidate for the "slow" component in any
  two-exponential fit - see the lag question in
  `rh-step-2026-09-07-live-notes.md`.
* The desiccant is a granular medium of unrecorded type and unknown prior
  loading, so the endpoint RH it holds is whatever it holds. The SHT45 reading
  is the humidity of record; no fixed-point value is claimed for A.

## Open items that affect interpretation

* ~~Venting of the glass jar is unconfirmed.~~ **CLOSED** by the photo above:
  a loose ceramic lid on a glass rim cannot hold a pressure difference.
* **Vessel N is not yet built and must differ from A**: the probe stands in the
  medium in A, which is not acceptable over a slurry.
* **The scheduled SHT45 de-creep pulse fired inside step 1**, 07:16:59Z. The
  window 07:16:56Z to ~07:23:00Z is contaminated - the published RH runs up to
  1.63 %RH low and takes ~325 s to return to the undisturbed curve. Exclude it
  from any fit. See `SHT-DECREEP-MASK-IS-TOO-SHORT.md`.
* **Cell/SHT45 cavity: SAME OPEN CAVITY** (Fab, 2026-09-07, during the run).
  The two sensors share one gas volume, so the SHT45's `p_w` *is* the cell's
  `p_w`. This retires the "the cell and the RH sensor are not sampling the same
  gas" hypothesis of `O2-HUMIDITY-CORRECTION.md` - which had been retracted,
  reopened by section 10, and attacked again in review - on a fact about the
  assembly rather than another regression. It does not say the two sensors
  respond at the same *speed*: the SHT45 is fast and the cell sits behind a
  diffusion membrane, so a lag between them is still possible and has to be
  excluded on the shape of the response, not on this.
