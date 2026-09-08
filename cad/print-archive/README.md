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
