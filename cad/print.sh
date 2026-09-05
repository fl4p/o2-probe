#!/usr/bin/env bash
# Slice the O2 probe body for the P1P in ASA.
#
#   ./print.sh slice <part>   monobody | cap | dam | carrier | retainer
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
        # h/d 4.58 with a free bore at z=0 that mates with nothing: fuse the
        # brim and put one inside the bore too. 219 -> ~1709 mm2 bonded.
        monobody) echo '{"brim_object_gap":"0","brim_type":"outer_and_inner","brim_width":"8"}' ;;
        # The carrier prints wet-face-DOWN, so its z=0 IS the membrane sealing
        # land: any fused brim scars the surface the seal is made on. Stay
        # outside and keep the gap.
        carrier)  echo '{"brim_object_gap":"0.1","brim_type":"outer_only"}' ;;
        # RETAINER, re-examined 2026-09-05 when the part was flipped to print
        # groove-DOWN. The old note said its z=0 "carries the six bolt clearance
        # holes"; that was the groove-UP orientation. Groove-down, z=0 is the
        # annulus that BOTTOMS ON THE CARRIER AND SETS THE GAP, and the seat and
        # groove are recesses -- so the first layer is a bare 6 mm ring
        # (r 13.25-19.4) with nothing inside r13. The part spaghettified out of
        # that empty middle on the first attempt.
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
        retainer) echo '{"brim_object_gap":"0.1","brim_type":"outer_only"}' ;;
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
# ratio, the 18 vs 12 volumetric limit and pressure advance were all tuned for
# a material that was not in the extruder.
#
# Set FILAMENT_VENDOR/FILAMENT_ID when the spool changes, or the slice is
# refused. That is the point: swapping filament without saying so should fail
# loudly rather than print badly.
FILAMENT_VENDOR="${FILAMENT_VENDOR:-Elegoo}"
FILAMENT_ID="${FILAMENT_ID:-OEASAB00}"

# The mouth-wipe temperature, pinned in profiles/machine_p1p.json rather than
# inherited from the stock {nozzle_temperature_initial_layer-20}. See
# profiles/WIPE-TEMP.md. Guarded because a re-flatten of the machine profile
# from Bambu's tree would silently put it back on the formula.
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
        retainer) echo exports/asa-retainer-print.stl ;;  # groove UP; flat-side-down bridges the bed floor
        # Fastener test block: the M2 insert and thread-forming bosses, at full
        # depth, in the process the head is printed in. Holes UP, which is the
        # way up the head prints -- a coupon printed the other way round tests
        # thread-forming against a layer structure the part does not have.
        fastener-coupon) echo exports/fastener-coupon.stl ;;
        *)        die "unknown part '$1' (monobody | cap | dam | carrier | retainer | fastener-coupon)" ;;
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

    "$ORCA" --load-settings "$PWD/$MACHINE;$PWD/$proc" \
            --load-filaments "$PWD/$FILAMENT" \
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
