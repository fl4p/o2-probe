# The wipe temperature is pinned at 270 C

`profiles/machine_p1p.json` -> `machine_start_gcode`, inside the
`;===== wipe nozzle =` block (that block is `gcode_claim_action : 14`, the stage
a residue abort dies in):

```
M109 S270 ; WIPE TEMP: pinned, NOT the stock initial_layer-20
G1 X100 F18000 ; first wipe mouth
```

Stock Bambu ties the mouth wipe to the material:
`M109 S{nozzle_temperature_initial_layer[initial_extruder]-20}`. With our ASA at a
270 C initial layer that resolved to **250**. It is now a literal **270**, so the
wipe no longer moves when a filament profile's initial-layer temperature changes.

## Why decouple instead of raising the initial layer

Raising the initial layer is the cheap lever the p1p notes recommend
(`~/dev/ee/p1p/doc/levelling-faults.md`), but it is exhausted here: 270 is already
Bambu's own ASA initial-layer number, and buying a 270 wipe through the `-20`
coupling would need a **290** initial layer -- above `nozzle_temperature_range_high`
(280) for this filament, and it would print the whole first layer there. Pinning the
wipe raises only the wipe.

270 is inside what the machine's own start G-code permits at that point: four lines
later it runs `G28 Z P0 T300 ; home z with low precision, permit 300deg temperature`.

## What this does and does not fix

It reduces how much residue the wipe **leaves behind**. It does not remove a stub
that was already on the tip -- that survives any wipe temperature and then hardens
at the hard-coded `M109 S140` probe, where the nozzle *is* the bed-levelling probe.
**Hand-clean the tip after any material swap.** That is still a required step.

Cost: the nozzle is held 20 C hotter through the mouth-wipe and steel-edge sequence,
so expect slightly more ooze during it, and a short reheat from the 250 C shrink
step that precedes it.

## Not changed

The `M109 S{...-20} ; drop nozzle temp, make filament shink a bit` earlier in the
start G-code is left on the formula. Its purpose is to *drop* the temperature so the
filament shrinks before the shake; it is not the mouth wipe.

## Guard

`print.sh` reads the wipe temperature back out of the emitted `plate_1.gcode` and
refuses the slice if it is not `WIPE_TEMP` (270). Read from the emitted stream, not
from this profile -- the profile is the thing being checked.
