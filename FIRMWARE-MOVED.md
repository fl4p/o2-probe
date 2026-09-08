# The firmware is not in this repository

The o2-probe firmware lives in **`ee/hw/o2-probe/firmware`** in `flap/dev-root`,
which is what ships. The copy that used to sit here was a fork that shared no
git history with it, and on 2026-09-08 the two had diverged far enough to be
actively dangerous:

- The deployed probe (`farm-node-01`, build stamped in `BUILD_ID`) runs the
  dev-root tree. This copy was never deployed anywhere.
- The register maps disagreed. This copy served an 18-register diagnostic
  block; the deployed firmware serves 26, including `T_DIE`, `FAULTS_EVER`,
  `ADS_FAIL_COUNT`, the cell-buffer channels and `BUILD_ID` — all of which the
  ChirpStack decoder in `farming` has been parsing successfully for weeks.
- This copy carried at least one fatal bug the real firmware never had
  (`modbus_rtu.c` never assigning the response deadline, which would have made
  the probe silent on the bus), and lacked the bootloader, the RS-485 bridge,
  OTA update and config migration entirely.

A ten-round adversarial review was run against this copy before anyone noticed
it was not the shipping tree. The findings that turned out to apply to the real
firmware were verified against it individually and ported there; the ones that
were artefacts of this fork were not. See `O2-CORRECTION-MODEL-BUDGET.md` for
the analysis, which is about the cell and the parts rather than the code and so
remains valid.

**Do not re-add a firmware directory here.** `ee/hw/o2-probe/firmware/src/regmap.h`
is the source of truth for the register map, by the decoder's own statement.
