# R44 via/land repair

`adapter.py` is the frozen exact delta, applied to a private snapshot of the board after the three-net route. All source footprint/net/endpoint preconditions are checked before mutation. All changed and added copper is locked.

- R44 shifts 0.05 mm right, to (108.4,111.5), retaining B.Cu and 90° orientation.
- Its existing GND via moves from (108.5,110.7) to (107.7,110.875), with a short B.Cu return to R44.2.
- U7.7 returns directly inward to the exposed pad through two 0.15 mm F.Cu segments.
- The adjacent SDA via moves from (107.5,110.5) to (107.4,110.3); a short local F.Cu escape shifts right around the ground stitch. SDA topology is preserved.
- One additional 0.4/0.2 mm GND via at (107.5,111.8) bridges the otherwise isolated front ground region to the main back plane. Native refill without this stitch demonstrated one new GND open; with it, the source's ground-open count is preserved.

Validation: full native `--refill-zones --save-board --all-track-errors --severity-all`, `drc.json`: zero electrical/geometric errors, no R44 courtyard overlap, and four remaining opens (the same two power gaps and two GND islands as `source-drc.json`). Private-directory library-configuration errors and unrelated warnings are not claimed cleared. The root owns remaining global completion.

`overlap-only.json` checks every via against every SMD copper pad on both faces at zero margin: no touching/overlapping pairs. The optional 0.20 mm via-to-land placement target is not treated as a process rule. The final frozen adapter was executed again on its source and its complete copper geometry/locking and footprint positions compared equal to the native-tested candidate.
