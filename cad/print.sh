#!/usr/bin/env bash
# Slice the O2 probe body for the P1P in ASA.
#
#   ./print.sh slice <part>   monobody | cap | dam | carrier | retainer
#                             fastener-coupon | fit-coupon
#                             (ONE part per plate, always)
#   ./print.sh upload <part>  send the plate (verified by size, material cross-checked)
#   ./print.sh start  <part>  start it -- blocks until lift-off
#   ./print.sh status
#
# ONE PART PER PLATE is not a preference. PRINTING-BODY-TUBE.md: identical parts
# measured 0 mTorr singly and 18 mTorr nine-up. This script therefore REFUSES a
# multi-part plate rather than arranging one.
#
# The machine ops (upload/start/status) are delegated to ~/dev/ee/p1p/bin, and
# the offline plate check to ~/dev/ee/zoe/enclosure/slice-check.sh. Neither is
# reimplemented here; if one is missing, that is an error, not a fallback.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

ORCA="${ORCA:-/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer}"
BBL="${BBL:-/Applications/OrcaSlicer.app/Contents/Resources/profiles/BBL}"
# NOT the stock BBL machine file. The CLI does not walk `inherits` for machines
# any more than for filaments, so the stock leaf slices against a 200x200x100
# bed -- Orca's built-in defaults -- and REFUSES any object over 100 mm tall with
# a wordless "run found error, exit". The 146.6 mm monobody is such an object.
# profiles/machine_p1p.json is that leaf plus the resolved geometry.
MACHINE="${MACHINE:-profiles/machine_p1p.json}"
PROCESS="${PROCESS:-profiles/process_asa_seal.json}"

# process_asa_seal.json is the SHARED base and must stay safe for every part on
# it. Anything that is only right for one part goes here instead, because the
# parts disagree: the monobody is a 146.6 mm tower that needs all the adhesion
# it can get, while the carrier prints wet-face-DOWN, so its z=0 IS the membrane
# sealing land and ANY fused brim -- inner or outer -- scars the surface the
# seal is made on. A single shared value cannot serve both, and on 2026-09-05 a
# tall-tower brim setting was briefly pushed into the shared profile and would
# have done exactly that damage to the carrier.
#
# Orca does not resolve `inherits`, and `-s key=value` drops numerics, so the
# override is applied by generating a merged profile per part. Values must be
# JSON STRINGS -- a number is silently discarded (doc/slicer-presets.md).
part_process_overrides() {
    case "$1" in
        # A free bore at z=0 that mates with nothing: fuse the brim and put one
        # inside the bore too. 223 mm2 of part -> 2455 mm2 bonded.
        #
        # WIDTH 12, not 8, on Fab's ask 2026-09-05 -- and 12 rather than more,
        # because THE INNER BRIM SATURATES. It closes the O27.2 bore at 13.6 mm,
        # so past ~10 every extra millimetre is outer-only, and the outer edge is
        # where a partial lift starts:
        #     8 mm  outer 1005 + inner 483 = 1711 mm2   (O48)
        #    12 mm  outer 1659 + inner 573 = 2455 mm2   (O56)  +44%
        #    16 mm  outer 2413 + inner 581 = 3217 mm2   (O64)  +88%
        # 16 is not worth it at brim_object_gap 0: the brim is WELDED to the part,
        # and a fused O64 skirt on a O32 tube is chisel work.
        #
        # THIS IS BELT-AND-BRACES, NOT THE FIX. The 2026-09-05 failure at layer
        # 928 was a directional thermal gradient (the printer stood in direct
        # sun, since moved into a closed room), and its contributing cause --
        # Bambu's default brim_object_gap 0.1, which parked 581 mm2 of brim
        # BESIDE the part instead of attaching it -- is the "0" above. The tower
        # also lost 12.2 mm of height (146.6 -> 134.4) when the head's neck went.
        monobody) echo '{"brim_object_gap":"0","brim_type":"outer_and_inner","brim_width":"12"}' ;;
        # The carrier prints wet-face-DOWN, so its z=0 IS the membrane sealing
        # land: any fused brim scars the surface the seal is made on. Stay
        # outside and keep the gap.
        carrier)  echo '{"brim_object_gap":"0.1","brim_type":"outer_only"}' ;;
        # FIT COUPON. z=0 is a plain ring face plus its label flange and mates
        # with nothing, so a fused outer brim is free. An INNER brim is not: it
        # would print inside the bore, against the underside of the very rails
        # being measured, and come off badly if at all.
        fit-coupon) echo '{"brim_object_gap":"0","brim_type":"outer_only","brim_width":"4"}' ;;
        # RETAINER, GROOVE-UP -- Fab's decision 2026-09-06 after four plates
        # (GLAND-ON-THE-BED.md). Printed groove-up, z=0 is the flat BACK of the
        # part -- a full annulus r 7.60-18.78, 11.18 mm wide -- not the seal
        # face, and NOTHING BRIDGES. Groove-down with the old membrane seat, z=0
        # was a bare 6 mm ring (r 13.25-19.4) with nothing inside r13 and the
        # part spaghettified out of that empty middle; dropping the seat fixed
        # that and produced a clean print, but the groove roof still was not
        # good enough to seal on.
        #
        # An inner brim was the obvious answer and it is WRONG. Both seal-check
        # guards refused it and both reasons hold: fused (gap 0) the snap-off
        # scar lands on the datum ring, and inner brim of any kind prints INSIDE
        # the six M2.5 clearance holes that pass through that ring. At the 0.1
        # gap the guard requires it would not have bonded either, so it bought
        # nothing and cost six blocked holes. Left as outer_only on purpose.
        #
        # The actual first-layer fix here is not a slicer setting: residue on
        # the nozzle tip mis-levels z, because the tip IS the levelling probe.
        #
        # BRIDGE SPEED 25, not the shared 50, on Fab's ask 2026-09-06. This is
        # the one untried lever on the groove-down flip. Layer 17 (z 2.00-2.12)
        # is the groove ROOF: 549 Bridge extrusions, 735 mm of bridged path,
        # worst chord 2*sqrt(12.05^2 - 8.8^2) = 16.47 mm across a groove only
        # 3.25 mm wide radially (GLAND-ON-THE-BED.md). Halving the speed doubles
        # the time each unsupported strand has to freeze before the next one
        # pulls on it. It is PER-PART because nothing else here bridges over a
        # seal surface -- the monobody's bridges are structural, and slowing
        # them would add hours to a 1119-layer tower for no gain.
        #
        # bridge_flow stays 1. Two changes at once and a good print tells you
        # nothing about which one did it; flow is the second lever, not this
        # one. THE VERDICT COMES FROM A DEPTH GAUGE, NOT FROM LOOKING AT IT --
        # the whole squeeze window is 0.245 mm, and a roof that sags 0.1 mm
        # still looks perfect.
        #
        # INERT AS OF 2026-09-06: the retainer prints GROOVE-UP now and the
        # sliced gcode contains ZERO Bridge features, so this key changes
        # nothing on this plate. Kept, not deleted, because it is correct the
        # moment anyone slices groove-down again (which the CAD now gates behind
        # -D face_groove_down_waiver=true), and because the measurement below is
        # the reason not to re-run that experiment.
        #
        # OUTCOME 2026-09-06: 25 DID NOT FIX IT. The part held together where
        # bridge 50 had spaghettied, and the groove roof still came out full of
        # voids -- the failure moved rather than went away, which says strand
        # dwell time was not the binding constraint. The 16.47 mm worst chord
        # over a 3.25 mm groove is. Kept at 25 because it is strictly better
        # than 50 here, NOT because it works. If the flip is abandoned for a
        # top-surface sealing face there is no bridge at all and this is moot.
        retainer) echo '{"brim_object_gap":"0.1","brim_type":"outer_only","bridge_speed":["25","25"]}' ;;
        # THE GLAND'S SEAL NOTCH IS A BRIDGE, and it was missed. The cap prints
        # gland face DOWN, so that notch is a void from the bed up to
        # gland_notch_depth and its roof bridges 1.8 mm of air -- the SAME
        # feature the retainer above already carries an override for, on the
        # same reasoning. Sliced 2026-09-06 with no overrides at all and the
        # notch came out dirty; the lesson was already in this file one line up
        # and simply was not carried across.
        #
        # internal_bridge_speed as well as bridge_speed: this is a roof over a
        # POCKET, not an open span, and Orca drives the two from separate keys.
        cap)      echo '{"bridge_speed":["25","25"],"internal_bridge_speed":"25"}' ;;
        *)        echo '{}' ;;
    esac
}
# PER-PART FILAMENT OVERRIDES, added 2026-09-06. Cooling is a FILAMENT setting in
# Orca, not a process one, so the machinery above cannot reach it -- and there is
# exactly one filament profile shared by every part. Without this, raising the
# bridge fan for the retainer would also raise it for the 146.6 mm monobody
# tower, which is the last part on this machine that wants more cooling.
#
# SAFE BECAUSE THE MATERIAL GUARDS DO NOT READ THIS FILE. seal_check.sh gates
# filament_flow_ratio (1.00-1.02, gas-tightness) and filament_type, slice-check
# gates filament_type, and the vendor/id assertions below read filament_vendor
# and filament_ids -- ALL of them out of the EMITTED gcode, so a per-part
# divergence still has to survive them. tools/profile_check.py reads only
# process_asa_seal.json, so nothing here can blind it either.
#
# The identity keys are forbidden anyway (see FORBIDDEN in the merge): a part
# that needs a different MATERIAL needs a different spool and a conversation,
# not a per-part override.
part_filament_overrides() {
    case "$1" in
        # THE BRIDGE FAN AT 100 IS KNOWN-BAD. DO NOT PUT IT BACK.
        #
        # Tried 2026-09-06 as the second lever after bridge_speed 25 failed:
        # overhang_fan_speed 35 -> 100 for the retainer only, verified in the
        # toolpaths as M106 S255 inside the Bridge feature against S25 on the
        # rest of each layer, so the cooling really was scoped to overhang and
        # bridge paths. It still DETACHED THE PART -- at 12:42:25, around layer
        # 12, BEFORE the groove roof at layer 17. The printer then ran to FINISH,
        # 100%, 33/33, print_error 0, extruding into air for twenty minutes.
        #
        # 100% local cooling costs ASA its adhesion, and a 4.04 mm disc has no
        # mass above the first layers to hold it down while the outer wall
        # contracts. The plate never reached the bridge, so it says nothing about
        # the roof -- it only closes the lever. GLAND-ON-THE-BED.md, attempt 3.
        #
        # This case is left EMPTY on purpose. A known-bad value sitting in a
        # config is a trap for whoever slices next, and the retainer inherits the
        # shared ASA cap of 35 exactly like every other part.
        *)        echo '{}' ;;
    esac
}
FILAMENT="${FILAMENT:-profiles/filament_asa.json}"
CHECK="${CHECK:-$HOME/dev/ee/zoe/enclosure/slice-check.sh}"
P1P="${P1P:-$HOME/dev/ee/p1p/bin}"

# The plate physically fitted. The P1P cannot detect it, so it is declared here
# and then asserted against what the slicer actually emitted.
BED_PLATE="${BED_PLATE:-Textured PEI Plate}"

# THE SPOOL PHYSICALLY LOADED, declared for the same reason as the plate: the
# printer cannot tell us, and a declared consumable is not a reading. Added
# 2026-09-05 after two failed retainer prints were traced to a filament profile
# named "ASA sealing" that was a BAMBU ASA chain while the machine held Elegoo
# ASA. Every existing guard passed, because they all check things that were
# right: filament_type really did resolve to ASA, the plate really was Textured
# PEI, the layer height really was 0.12. Nothing asked WHICH ASA, so the flow
# ratio and the 18 vs 12 volumetric limit were tuned for a material that was not
# in the extruder.
#
# Set FILAMENT_VENDOR/FILAMENT_ID when the spool changes, or the slice is
# refused. That is the point: swapping filament without saying so should fail
# loudly rather than print badly.
#
# KNOW WHAT THIS GUARD CANNOT DO -- three holes, all found by review 2026-09-05:
#   1. Orca documents filament_vendor as "For show only" and filament_ids comes
#      from the preset's filament_id. Both are METADATA. A copied or hand-edited
#      profile can keep Elegoo identity while carrying transplanted temperatures
#      and cooling -- exactly the failure above, wearing the right name. Identity
#      is a cheap first gate, not an attestation. A guard that must hold has to
#      assert the behaviour-critical emitted values too, or hash the resolved
#      chain.
#   2. It cannot authenticate the physical spool. Leaving these defaults while
#      loading something else passes. The echo says "declared loaded" for that
#      reason -- it is a declaration, like BED_PLATE, not a reading.
#   3. It cannot see an ABSENT key. This profile carries no pressure advance at
#      all and the emitted gcode reads enable_pressure_advance = 0; a claim that
#      the rebuild "kept PA 0.04" was simply false, and nothing here noticed.
#   4. IT DOES NOT GUARD THE ARTIFACT THAT SHIPS. `slice` validates
#      print/<part>/plate_1.gcode and exits; `upload` is a separate invocation
#      that sends o2probe-*.gcode.3mf, and nothing re-runs or binds the checks to
#      it. They match today, but anything that replaces or staleness-drifts one
#      between the two commands walks past both guards. The right fix is to
#      verify the .3mf's embedded stream (or its hash against the validated
#      plate_1.gcode) inside cmd_upload. NOT DONE.
FILAMENT_VENDOR="${FILAMENT_VENDOR:-Elegoo}"
FILAMENT_ID="${FILAMENT_ID:-OEASAB00}"

# The mouth-wipe temperature, pinned in profiles/machine_p1p.json rather than
# inherited from the stock {nozzle_temperature_initial_layer-20}. See
# profiles/WIPE-TEMP.md. Guarded because a re-flatten of the machine profile
# from Bambu's tree would silently put it back on the formula.
# Overridable so a different process can declare its own wipe -- but note that
# makes it a MUTE BUTTON: WIPE_TEMP=250 redefines the failure as success. Change
# the profile, not this, unless you mean it.
WIPE_TEMP="${WIPE_TEMP:-270}"

die() { echo "error: $*" >&2; exit 1; }

part_stl() {
    case "$1" in
        monobody) echo exports/body-monobody.stl ;;
        cap)      echo exports/body-cap-print.stl ;;   # gland face DOWN; body-cap.stl would bridge its own roof
        dam)      echo exports/body-dam.stl ;;
        # The head-end seal parts, printed ASA, clamped membrane bed. Both are
        # the *-print orientation and neither may share a plate: they carry the
        # seal, and that is exactly what the 0 vs 18 mTorr result above is about.
        carrier)  echo exports/asa-carrier-print.stl ;;   # wet face DOWN; forced by the flange step
        # Groove DOWN (face_groove_up = false): the sealing face is the bed face
        # and the groove roof bridges at z 2.00. The old comment here said
        # "groove UP", which was true of the flag's previous value and stopped
        # being true when it was reverted -- corrected 2026-09-06.
        retainer) echo exports/asa-retainer-print.stl ;;
        # Fastener test block: the M2 insert and thread-forming bosses, at full
        # depth, in the process the head is printed in. Holes UP, which is the
        # way up the head prints -- a coupon printed the other way round tests
        # thread-forming against a layer structure the part does not have.
        fastener-coupon) echo exports/fastener-coupon.stl ;;
        # Wire-end GRIP FIT ladder: one ring of the real tube section per rung, each
        # with the real guide rails and a 6 mm interference band, differing only
        # in grip_slack. PRINTING-BODY-TUBE.md, "Setting the wire-end grip".
        #
        # THIS ONE PART IS SEVERAL OBJECTS, and that is the exemption to the
        # one-part-per-plate rule above, not a violation of it. The 0 vs 18 mTorr
        # result is about SEALING, and nothing on this plate seals. What the
        # coupon measures is the difference between the rungs, so they have
        # to see the same plate: split one per plate, plate-to-plate
        # variation lands directly in the answer and there is no answer left.
        fit-coupon) echo exports/body-fit-coupon.stl ;;
        *)        die "unknown part '$1' (monobody | cap | dam | carrier | retainer | fastener-coupon | fit-coupon)" ;;
    esac
}

cmd_slice() {
    [[ $# -eq 1 ]] || die "slice takes exactly one part: identical parts measured 0 mTorr singly and 18 mTorr nine-up"
    local part="$1" stl plate g
    stl=$(part_stl "$part")
    [[ -f $stl ]] || die "missing $stl -- run 'make monobody' (body parts) or 'make head-end-asa' (carrier, retainer) first"
    [[ -x "$ORCA" ]] || die "OrcaSlicer not at $ORCA"
    [[ -x "$CHECK" ]] || die "no slice-check at $CHECK"
    plate="o2probe-$part.gcode.3mf"

    rm -rf "print/$part"; mkdir -p "print/$part"

    # Merge the shared base with this part's overrides into the plate directory,
    # so what was sliced is recoverable next to the plate rather than inferred.
    local proc="print/$part/process.json"
    PART_OVERRIDES="$(part_process_overrides "$part")" python3 - "$PROCESS" "$proc" <<'MERGE'
import json, os, sys, collections
base = json.load(open(sys.argv[1]), object_pairs_hook=collections.OrderedDict)
over = json.loads(os.environ["PART_OVERRIDES"])
bad = [k for k, v in over.items() if not isinstance(v, (str, list))]
if bad:
    sys.exit("override(s) %s are not strings -- Orca discards JSON numbers silently" % bad)

# Keys the CAD quantizes against. membrane_cartridge_common.scad derives seal
# dimensions as integer multiples of the build layer, and tools/profile_check.py
# gates those constants against process_asa_seal.json -- the BASE file. The
# moment a part overrides one of them here, profile_check is validating a number
# that did not slice the plate, and it would still report green. Rather than
# teach that check about per-part generation, forbid the overlap: these belong
# to the shared profile, and a part that genuinely needs a different one needs a
# conversation, not a silent divergence.
QUANTIZED = ("layer_height", "initial_layer_print_height", "outer_wall_line_width")
clash = [k for k in over if k in QUANTIZED]
if clash:
    sys.exit("override(s) %s are quantized against by the CAD and gated by "
             "tools/profile_check.py against the BASE profile -- overriding them "
             "per part would make that check validate a value that did not slice "
             "this plate" % clash)
for k, v in over.items():
    if k not in base:
        sys.exit("override key %r is not in the base profile -- typo, or a key "
                 "Orca will ignore" % k)
    base[k] = v
json.dump(base, open(sys.argv[2], "w"), indent=4, ensure_ascii=False)
print("  process overrides: %s" % (over or "none"))
MERGE

    # Same again for the filament, and for the same reason: what was sliced ends
    # up next to the plate instead of having to be inferred from the shared file
    # plus a memory of which part it was.
    local filam="print/$part/filament.json"
    PART_OVERRIDES="$(part_filament_overrides "$part")" python3 - "$FILAMENT" "$filam" <<'MERGE'
import json, os, sys, collections
base = json.load(open(sys.argv[1]), object_pairs_hook=collections.OrderedDict)
over = json.loads(os.environ["PART_OVERRIDES"])
bad = [k for k, v in over.items() if not isinstance(v, (str, list))]
if bad:
    sys.exit("override(s) %s are not strings -- Orca discards JSON numbers silently" % bad)

# The material's IDENTITY and its gas-tightness are not per-part properties.
# Every one of these is asserted downstream out of the emitted gcode, so an
# override could not hide anyway -- it would just turn a guard into a failed
# slice at the end of a slow step. Refuse it here, where the message can say why.
FORBIDDEN = ("filament_type", "filament_vendor", "filament_ids",
             "filament_flow_ratio", "filament_settings_id")
clash = [k for k in over if k in FORBIDDEN]
if clash:
    sys.exit("override(s) %s name the MATERIAL, which is a property of the spool "
             "in the extruder and not of the part on the plate. seal_check.sh and "
             "slice-check assert these from the emitted gcode; a part that needs a "
             "different material needs a different spool" % clash)
for k, v in over.items():
    if k not in base:
        sys.exit("override key %r is not in the base filament profile -- typo, or "
                 "a key Orca will ignore" % k)
    base[k] = v
json.dump(base, open(sys.argv[2], "w"), indent=4, ensure_ascii=False)
print("  filament overrides: %s" % (over or "none"))
MERGE

    "$ORCA" --load-settings "$PWD/$MACHINE;$PWD/$proc" \
            --load-filaments "$PWD/$filam" \
            --arrange 1 --slice 0 --outputdir "$PWD/print/$part" \
            --export-3mf "$plate" "$PWD/$stl" >"print/$part/orca.log" 2>&1 \
        || { tail -20 "print/$part/orca.log"; die "slice failed"; }

    g="print/$part/plate_1.gcode"
    [[ -f $g ]] || { tail -20 "print/$part/orca.log"; die "slice produced no gcode"; }

    "$CHECK" "$g" --plate "$BED_PLATE"
    # Assert the slice used the spool that is actually loaded. Read from the
    # EMITTED gcode, never from the profile we passed in -- the profile is the
    # thing being checked, so trusting it would make this guard tautological.
    emitted_vendor=$(grep -aE '^; filament_vendor = ' "$g" | head -1 | sed 's/^; filament_vendor = //; s/"//g; s/;.*//')
    emitted_id=$(grep -aE '^; filament_ids = ' "$g" | head -1 | sed 's/^; filament_ids = //; s/"//g; s/;.*//')
    [[ -n $emitted_vendor ]] || die "no filament_vendor in the gcode: cannot verify the spool, refusing rather than assuming"
    [[ $emitted_vendor == "$FILAMENT_VENDOR" ]] \
        || die "filament vendor is '$emitted_vendor', loaded spool is '$FILAMENT_VENDOR' -- the profile is for the wrong material"
    [[ $emitted_id == "$FILAMENT_ID" ]] \
        || die "filament id is '$emitted_id', loaded spool is '$FILAMENT_ID' -- same vendor, different material"
    echo "  filament: $emitted_vendor $emitted_id (declared loaded)"

    # Wipe temperature, read out of the EXECUTABLE stream inside the machine's
    # own ";===== wipe nozzle =" block -- the "; machine_start_gcode = " header
    # comment is a mixed template and still carries unresolved formulae there.
    emitted_wipe=$(awk '/^;===== wipe nozzle =/{w=1} /^;===== wipe nozzle end/{w=0}
                        w && /^[[:space:]]*M109 S[0-9]+/{sub(/^[[:space:]]*M109 S/,""); sub(/[^0-9].*$/,""); print; exit}' "$g")
    [[ -n $emitted_wipe ]] || die "no numeric M109 in the wipe-nozzle block: the wipe temperature is unverifiable, refusing rather than assuming"
    [[ $emitted_wipe == "$WIPE_TEMP" ]] \
        || die "wipe temperature is ${emitted_wipe}C, expected ${WIPE_TEMP}C -- machine_start_gcode has fallen back to the stock initial_layer-20 (profiles/WIPE-TEMP.md)"
    echo "  wipe: ${emitted_wipe}C (probe still at 140C; hand-clean the tip after a material swap)"
    ./tools/seal_check.sh "$g" --part "$part"
    grep -aE '^; (model printing time|total filament used \[g\]|filament used \[cm3\])' "$g" | sed 's/^; /  /'
    echo "  plate: print/$part/$plate"
}

case "${1:-}" in
    slice)  shift; cmd_slice "$@" ;;
    upload) shift; [[ $# -eq 1 ]] || die "upload takes one part"
            "$P1P/p1p-upload" "print/$1/o2probe-$1.gcode.3mf" ;;
    start)  shift; [[ $# -eq 1 ]] || die "start takes one part"
            "$P1P/p1p-start" "o2probe-$1.gcode.3mf" ;;
    status) "$P1P/p1p-status" ;;
    *)      sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
