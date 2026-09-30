# Archived plates

One file per plate actually sent to the printer, named for the tag that
describes the tree it came from (`git show print/<name>`).

These are here because a `.3mf` is only reproducible under the same slicer
build. `cad/print/` stays ignored -- this directory is the deliberate exception,
and only finished runs belong in it.

An earlier version of this file went on to say *"the mesh and the profiles are
tracked normally and are recoverable from the tag; the sliced plate is not."*
**The second half is right and the first half is not always true** -- see the
monobody-r2 row. What actually makes a plate recoverable is the `.3mf` itself:
OrcaSlicer packs the mesh (`3D/Objects/<name>.stl_1.model`), the G-code and the
whole resolved config into it, so an archived plate is a complete, self-contained
record of a print whether or not `cad/exports/` was up to date that day.

| mark | plate | tag | printed |
|---|---|---|---|
| `T1` | `monobody-r1.gcode.3mf` | `print/monobody-r1` | 2026-09-05, ASA, first article |
| `R1` | `retainer-groove-up.gcode.3mf` | `print/retainer-groove-up` | 2026-09-06 14:42 uploaded; **print unconfirmed** |
| `C1 25.2` | `cap-r1.gcode.3mf` | `print/cap-r1` | 2026-09-06 15:11, ASA; P1P reported FINISH |
| `T2 25.5` | `monobody-r2.gcode.3mf` | `print/monobody-r2` | 2026-09-06 16:05, ASA; first collar tube, **brim fused in the seal bore** |
| (none) | `carrier-22x2-seat.gcode.3mf` | -- | 2026-09-05 18:44 uploaded, **outcome unrecorded**; cut for `onhand-22x2` and still carrying the Ø26.5 membrane seat |
| `M1 26.8` | `carrier-r1.gcode.3mf` | `print/carrier-r1` | 2026-09-08 17:52, ASA; P1P reported FINISH at 100% after 17 min. FIRST carrier for the sourced Ø24 x 1.5 |
| `R3 31.2` | `retainer-r3.gcode.3mf` | `print/retainer-r3` | 2026-09-08 22:31, ASA; P1P reported FINISH at 100%, 28/28 layers, 10 min. FIRST retainer with the 17 x 2.0 membrane bed (`6a0a7ba`), and the mate for `M1 26.8` |
| `T3 25.5` | `monobody-r3.gcode.3mf` | `print/monobody-r3` | 2026-09-09 uploaded, 1113 layers, 4h 06m est. FIRST monobody in the sourced-ring family (head OD 40, bolt circle Ø31.2) -- mates `M1 26.8` + `R3 31.2`. Cable end unchanged: Ø25.7 collar, 22 x 2. **FELL OVER.** The machine still reported FINISH/100%/1113 layers -- it kept extruding after the part detached. FAILURE HEIGHT: no telemetry, no camera (p1p-stream's ring buffer is 55 min of RAM and this was a 4 h print, so it had aged out). Fab observed it fell at the SAME height as r4, i.e. around layer 880 / z 106 mm. That observation is the only record there is |
| (none) | -- | -- | 2026-09-09 10:36, ASA; RE-RUN OF THE r3 PLATE, byte-identical, on a freshly cleaned bed with the machine newly calibrated for its new room. **TILTED OUT OF ITS OWN BRIM at layer 880**, stopped at 887. Photographed: brim flat on the plate, tube leaning out of it. Not archived separately -- same bytes as r3. This is the run that ruled out bed surface, vibration compensation and the room, and left the missing inner brim as the cause |
| `T5 25.5` | `monobody-r5.gcode.3mf` | -- | 2026-09-09 uploaded. **INNER BRIM RESTORED** (`outer_and_inner`, width 16): 1913 brim extrusion points inside the O27.55 mouth, reaching r 0.23, against NOTHING under r 16.23 on r3/r4. Both seal gates waived by name via `MONOBODY_INNER_BRIM_WAIVER=1`. **THE BORE IS PLUGGED ON PURPOSE** -- cut the disc out, deburr the 20 deg lip, ream to O25.7 H7 BEFORE fitting a cap. **PRINTED 2026-09-09 20:0x, ABORTED BY HAND at layer 949/1113 (z 113.96, 84%)** -- 69 layers further than r3/r4, so the inner brim did buy something. CAUSE, from Fab at the machine: **the enclosure front was not closed, so the chamber ran too cold for a 134 mm ASA tower.** That is consistent with the plate's own bridge/overhang report, which lists NOTHING between z 104.12 and z 128.24: there was no overhanging geometry at the failure height, so this was never a support problem. Warping load grows with height, which is why all three failures cluster near the same z and why more brim delayed rather than prevented it |
| `R4 30.2` | `print/retainer/o2probe-retainer.gcode.3mf` (not archived) | -- | 2026-09-09 ~21:45, ASA; P1P reported FINISH, 28/28 layers. `onhand-22x2` family (Ø37.4, bolt circle Ø30.2), 17 x 2.0 bed at 1.44. Exports built 20:57 with `RING=onhand-22x2`; packed mesh measured Ø37.400 / Z 3.44. Mate for `T2 25.5` (mono-r2, head OD 38) |
| `M2 25.8` | `print/carrier/o2probe-carrier.gcode.3mf` (not archived) | -- | 2026-09-09, ASA, after R4; `onhand-22x2` spigot Ø25.8, packed mesh Ø37.400 / Z 8.30. Mate for `T2 25.5` + `R4 30.2`. **Fab asked for BOTH to be reprinted on 2026-09-11** -- the next attempts are `R5 30.2` / `M3 25.8`, same geometry unless a change is recorded here |
| `R5 30.2` | same plate as `R4`, re-uploaded (not archived; overwritten by the `R6` slice) | -- | 2026-09-11 18:44 lift-off, FINISH 18:54, 28/28 layers. Geometry identical to `R4`: bed drawn 1.44 |
| `M3 25.8` | same plate as `M2`, re-uploaded (not archived) | -- | 2026-09-11. Two starts ABORTED in prep before it printed: 18:56 in stage 14 (tip cleaning) with `0300_0B00_0001_0004` + `0300_0D00_0001_000B`, print_error `0x03004000` Z homing failed; 19:05 got past the wipe and died 11 s into auto bed levelling with `0300_0B00_0001_0004`, print_error `0x03004002`, a white strand hanging off the toolhead on camera. Third start after Fab cleared it: lift-off 19:29, FINISH 19:46:57, 68/68 layers, no HMS. The 2026-09-11 20:01 re-export of the carrier is geometrically IDENTICAL to what printed (6552 triangles, volume 3677.444, area 3217.967, same z levels), so `M3` is current |
| `R6 30.2` | `retainer-r6.gcode.3mf` | -- | 2026-09-11 sliced + uploaded (279 872 B); lift-off 20:39, **FINISH 100% at 20:48**, 27 layers on the plate against `R5`'s 28 -- that layer-count difference is what proved by content that the new plate was the one loaded. **Bed drawn 1.32, one layer shallower**, on Fab's ask, with the measured 0.15 groove-up overcut now inside the model (`face_print_overcut()`): expected printed gap 1.47, 25.2 % nominal. Packed mesh measured Ø37.400, h 3.32, groove floor 2.00 above the outer face (web 2.0). Overhang report: `Internal Bridge` only, at z 1.52/1.64/2.84, the first top-shell layers over sparse infill five layers under the groove floor and the top face. None on a sealing surface. **Gauge the groove on this part**: it tests the 0.15 mm overcut. NOT done before it went into the 2026-09-12 leak test, which it passed (see the note under this table) -- so do it when the assembly comes apart. |

**`R6 30.2` + `M3 25.8` passed a 12 h under-water leak test on 2026-09-12** (Fab),
assembled to `T2 25.5` with 17 x 2.0 and 22 x 2.0 rings. The retainer is identified
as R6 -- the 1.32 groove, the last one printed -- by Fab's recall, hedged (*"i think
the last one you printed"*), NOT by reading the mark off the part. R5 and R6 are
indistinguishable in the hand except by that mark, so confirm it when the assembly
comes apart. See `PRINTING-HEAD-END.md`, 2026-09-12, for what the pass does and does
not establish.

**There is no `R2`, and the gap is deliberate.** A retainer was sliced for a
17 x 2.5 bed on 2026-09-08 and uploaded, but it never printed: six consecutive
starts aborted (Z-axis HMS, PLA under the levelling pad), and before the machine
was fixed the bed itself was superseded -- the 2.5 on hand turned out not to be
EPDM. The run number is spent, so the next retainer is R4, not R3-again. Run
numbers count ATTEMPTS ON THE MACHINE, not successes; reusing one would make two
different plates share a mark.

## The mark on the part

Parts are hand-marked as they come off the bed -- scribed or burned in, because
ink does not survive the IPA wipe before assembly, let alone the pile. There is
no embossed ID in the models yet, so this is the only identification a physical
part carries.

    <letter><run>  <fit diameter>          e.g.  T2 25.5      C1 25.2      M1 26.8

Letter for the part type (T tube, C cap, R retainer, **M membrane carrier**),
run number matching the tag in the table above, and the ONE diameter that
decides whether two parts mate: the tube's collar bore, the cap's spigot OD,
**the carrier's spigot OD**.

`M`, not `C`, because the cap already owns `C`. The carrier's mate is the head,
and `well_d = spigot_d + carrier_fit` with `carrier_fit = 0.5` at the head end,
so **a carrier and a head fit when their numbers differ by 0.5** -- `M1 26.8`
takes a head whose well reads 27.3. Mark the DRAWN diameter, as the tube does:
`T2 25.5` is drawn 25.5 and reamed to 25.7 afterwards.

Where it goes on a carrier: the **outer rim of the flange**, the 3 mm tall
cylindrical edge at Ø38.4. Not either face. The flange's underside is the
membrane sealing land -- the part prints wet-face-DOWN, so that surface IS the
seal -- the top face bears against the head under the six screws, and the spigot
carries the O-ring groove. The rim seals nothing, bears nothing, and stays
readable with the probe assembled.

Where it goes on a **retainer**: the flat OUTER face, in the 3.6 mm annulus
between the Ø31.2 bolt circle and the Ø38.4 rim. That is the face that was DOWN
on the plate -- the retainer prints groove-up -- so it is the smooth one, and it
is the face pointing out of the assembled probe. Not the groove face: the groove
IS the membrane bed now. The rim would do but it is only 3.44 mm tall.

And the diameter on a retainer is the BOLT CIRCLE, not a fit diameter, because
that is what decides whether it lands on a head. It moves with the radial ring
even though the retainer has nothing to do with that seal -- the ring sets the
head OD (38 -> 40) and the bolt circle follows (Ø30.2 -> Ø31.2). So a retainer
for the sourced ring measures Ø38.4 across and one for `onhand-22x2` measures
Ø37.4, and in the hand that is one millimetre. `R3` was confirmed as the
Ø38.4 part by measuring the mesh packed inside its own `.3mf` and rendering the
retainer both ways -- not by trusting the filename. Do that check, not that
assumption: `print.sh slice` names the file after the part, never after the ring.

**A tube and a cap fit when their numbers differ by 0.3**, because
`spigot_od = cable_bore_d - carrier_fit` and `carrier_fit` is 0.3. So `T2 25.5`
takes `C1 25.2`, and the next pair will be `T3 25.7` + `C2 25.4`.

The diameter is on the part rather than only in this table because successive
pairs are visually identical and differ by 0.2 mm on a reamed bore that cannot
be measured quickly once the collar is finished. A bare serial would need this
file every time; the diameter checks itself in your hand.

WRITE THE MARK BEFORE THE PART LEAVES THE PRINTER. An unmarked part is
indistinguishable from its successor within one revision, and no amount of
journal fixes that afterwards.

Where it goes: cap on the flat outer gland face, in the ring outside the SW 16
gland footprint; tube on the outer wall more than 20 mm from the cable end,
clear of the `cap_engage = 18.0` the skirt covers and of the lock pilot at z=17.

## Two things this directory exists to stop, both of which already happened

**`print.sh slice` overwrites `plate_1.gcode` in place, and `cad/print/` is
ignored.** So the only trace of what was printed is a file mtime, and the next
slice of the same part destroys it. On 2026-09-06 the monobody plate was
re-sliced at 20:34 while diagnosing why the cap would not fit -- the fix
overwrote the evidence for the defect it was fixing. It survived only because it
had been copied aside minutes earlier.

**A local file with the right name is not necessarily the one that was printed.**
`cad/print/cap/plate_1.gcode` is dated 16:23, but the cap on the bench was
uploaded at 15:11 and the local file is a later re-slice. The two happen to carry
identical geometry -- verified, not assumed -- but they are different bytes, and
reading provenance off the local filename would have dated the cap to the wrong
commit.

## The printer's SD card is the real log, and it is recoverable

Every upload stays on the machine with its upload timestamp. That listing is the
only complete record of what was sent, and each file is a full `.3mf`, so a plate
whose local copy has been overwritten can be pulled back:

```sh
cd ~/dev/ee/p1p/bin && set -a && . ./_common.sh; set +a
curl -s --insecure --ftp-ssl --disable-epsv \
     -u "$BAMBU_USER:$BAMBU_ACCESS_CODE" "ftps://$BAMBU_HOST:990/"          # list
curl -s --insecure --ftp-ssl --disable-epsv \
     -u "$BAMBU_USER:$BAMBU_ACCESS_CODE" \
     "ftps://$BAMBU_HOST:990/o2probe-<part>.gcode.3mf" -o <dest>            # fetch
```

`cap-r1`, `monobody-r2` and `retainer-groove-up` were all recovered this way on
2026-09-06. For monobody-r2 the recovered G-code is byte-identical to the copy
archived from disk, which is two independent witnesses to one print.

**Uploaded is not printed.** The SD card proves a file reached the machine, never
that the job ran or how it ended. Where the outcome is not evidenced, the table
says so rather than guessing.

## Still unrecorded

Sliced and uploaded before this journal was kept up, with no tag and no archived
plate. The local `plate_1.gcode` for each is still the original (not re-sliced),
so they can be tagged retrospectively if they matter:

| part | sliced | uploaded |
|---|---|---|
| `fastener-coupon` | 2026-09-05 20:43 | Sep 05 20:43 |
| `fit-coupon` | 2026-09-05 20:47 | Sep 05 21:42 |
| `dam` | 2026-09-05 11:21 | not on the SD card |

**`M1` is not the first carrier ever printed, only the first marked one.** Two
predecessors are on the bench, both unmarked, both superseded, and both easy to
mistake for it in the hand:

| printed | family | spigot OD | why it is not M1 |
|---|---|---|---|
| 2026-09-03 | Ø24 x 1.5, pre-`spigot_land` dims | 27.0 drawn, 26.83 measured | uncompensated print: root came out 24.800, squeeze 14.90%, under the 15% floor |
| 2026-09-05 | `onhand-22x2` | 25.8 | wrong ring, and still carries the Ø26.5 membrane seat `01a9fa8` deleted |

Numbering restarts at 1 with the first TAGGED run, which is why this note exists:
without it `M1` reads as "the first carrier" and the two on the bench become
ambiguous again -- the exact failure the marking rule above is for.

`carrier` came out of this table on 2026-09-08 and into the one above, archived
before `./print.sh slice carrier` overwrote it -- exactly the loss this directory
exists to stop. Its sources are `3f48e4e` (the last cad commit before the 18:42
slice); it is deliberately NOT tagged, because it is superseded twice over: by
`01a9fa8`, which deleted the membrane seat it still carries, and by the ring.
sha256 `1407f697...f0c48e9f` -- run `shasum -a 256` on the file, not on this line.

`GLAND-ON-THE-BED.md` also refers to four retainer trial plates that predate
`print/retainer-groove-up`; none of them were archived and none survive.

## Recording a run

Do this at upload time, not afterwards -- run 1's own tag notes it was written
mid-print because HEAD had already moved:

1. copy the `.3mf` here as `<name>.gcode.3mf`;
2. `git tag -a print/<name>` on the commit whose **sources** produce the printed
   geometry, which is not always the commit that was HEAD when it was sliced
   (`print/cap-r1` was sliced 37 minutes before its tree was committed);
3. in the tag body record the SHA-256 of the archived `.3mf` and of the tracked
   mesh, the slicer version and slice timestamp, and **verify the mesh against
   the plate by content** -- a diameter measured off the G-code against the same
   diameter in the model. That check is what dated `cap-r1` correctly and what
   caught `body-monobody.stl` being stale.
