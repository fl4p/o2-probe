#!/usr/bin/env bash
# Slice the O2 probe body for the P1P in ASA.
#
#   ./print.sh slice <part>   monobody | cap | dam      (ONE part per plate)
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
FILAMENT="${FILAMENT:-profiles/filament_asa.json}"
CHECK="${CHECK:-$HOME/dev/ee/zoe/enclosure/slice-check.sh}"
P1P="${P1P:-$HOME/dev/ee/p1p/bin}"

# The plate physically fitted. The P1P cannot detect it, so it is declared here
# and then asserted against what the slicer actually emitted.
BED_PLATE="${BED_PLATE:-Textured PEI Plate}"

die() { echo "error: $*" >&2; exit 1; }

part_stl() {
    case "$1" in
        monobody) echo exports/body-monobody.stl ;;
        cap)      echo exports/body-cap-print.stl ;;   # gland face DOWN; body-cap.stl would bridge its own roof
        dam)      echo exports/body-dam.stl ;;
        *)        die "unknown part '$1' (monobody | cap | dam)" ;;
    esac
}

cmd_slice() {
    [[ $# -eq 1 ]] || die "slice takes exactly one part: identical parts measured 0 mTorr singly and 18 mTorr nine-up"
    local part="$1" stl plate g
    stl=$(part_stl "$part")
    [[ -f $stl ]] || die "missing $stl -- run 'make monobody' first"
    [[ -x "$ORCA" ]] || die "OrcaSlicer not at $ORCA"
    [[ -x "$CHECK" ]] || die "no slice-check at $CHECK"
    plate="o2probe-$part.gcode.3mf"

    rm -rf "print/$part"; mkdir -p "print/$part"
    "$ORCA" --load-settings "$PWD/$MACHINE;$PWD/$PROCESS" \
            --load-filaments "$PWD/$FILAMENT" \
            --arrange 1 --slice 0 --outputdir "$PWD/print/$part" \
            --export-3mf "$plate" "$PWD/$stl" >"print/$part/orca.log" 2>&1 \
        || { tail -20 "print/$part/orca.log"; die "slice failed"; }

    g="print/$part/plate_1.gcode"
    [[ -f $g ]] || { tail -20 "print/$part/orca.log"; die "slice produced no gcode"; }

    "$CHECK" "$g" --plate "$BED_PLATE"
    ./tools/seal_check.sh "$g"
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
