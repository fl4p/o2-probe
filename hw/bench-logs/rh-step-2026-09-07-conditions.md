# RH step test 2026-09-07 - run conditions

Recorded during the run, before analysis, so the assumptions are on the record.

| item | value | source |
|---|---|---|
| barometric pressure | **965 hPa** | Fab's phone, 2026-09-07 ~07:00Z |
| pressure basis | taken as **station** (what the cell sees) | assumed; implies ~400 m, self-consistent for a phone barometer. If the reading was sea-level-reduced the true station value is lower. |
| dilution reference | **-0.1052 %/hPa** | -100/(965 - p_w), p_w ~14.3 hPa |
| firmware `ASSUMED_P_HPA` (0x0042) | 930 hPa | **wrong by +3.6 % for this bench** - never set for this location |
| vessel A | glass jar, whole body fits, desiccant | venting NOT confirmed - see below |
| vessel N | saturated NaCl slurry | not yet used |
| article | assembled, in the unibody | not potted, not tubed |
| logger | `o2p_poll.py` @ 5 s -> `modbus-poll-2026-09-07.csv` | with the 48d3d8b reopen fix |

## Open items that affect interpretation

* **Venting of the glass jar is unconfirmed.** Section 4b of `RH-STEP-TEST.md`:
  a rigid sealed vessel changes total pressure instead of partial pressure and
  can produce "no dilution" from a healthy cell. For the dry leg the sign is
  the same trap - the desiccant removes ~16 hPa of vapour, and if the jar is
  sealed the total pressure falls with it while pO2 barely moves. Fab was asked
  to rest the lid loose or shim it. Confirm before the result is quoted.
* **Cell/SHT45 cavity question unanswered.** Whether both sit in the same open
  cavity of the unibody decides whether "two gas volumes" can be excluded.
