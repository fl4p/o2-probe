#!/usr/bin/env bash
# seal_check.sh — assert a sliced plate carries the settings that seal a wall.
#
#   tools/seal_check.sh <plate_1.gcode>
#
# WHY THIS EXISTS, on top of zoe's slice-check.sh
#
# slice-check.sh asserts the plate and the material — the two things that cost a
# whole print when wrong. This asserts the things that cost a whole PROBE when
# wrong, because a part sliced at 2 walls and 0.42 mm lines looks perfect and
# leaks: `~/dev/ee/p1p/doc/gastight-and-watertight.md` measured 0.2 mm layers at
# ~31x the leakage of 0.1, and 0.40 mm lines never sealing at all. For a sensor
# whose whole output is a gas concentration, what the wall passes is AIR.
#
# It is not hypothetical here. The first slice of this part came out
# `wall_loops = 2`, `outer_wall_line_width = 0`, `brim_width = 0` — every
# numeric override in the process profile had been passed as a JSON number where
# OrcaSlicer wants a string, and it discarded them ALL without one word of
# warning. The header still named the sealing preset. That is the failure this
# file exists to catch, and it caught it.
#
# FAIL-CLOSED. Every field that cannot be read is a FAILURE, never a pass. An
# absent setting is not evidence of a correct one.

set -euo pipefail

g=""; part=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --part) part="${2:-}"; shift 2 ;;
        *)      g="$1"; shift ;;
    esac
done
fail() { echo "SEAL-CHECK FAIL: $*" >&2; exit 1; }
[[ -n "$g" ]] || fail "no G-code file given"
# FAIL-CLOSED on identity too. The brim rules are opposite for a tall tower and
# for a part whose z=0 is a seal face, and nothing in the G-code says which this
# is. An unknown part is unevaluable, and unevaluable is a failure, not a pass.
case "$part" in
    # fastener-coupon is NOT a sealing part -- it is a test block for the M2
    # insert and thread-forming bosses. It is checked here anyway, and against
    # the same wall and layer settings, because the whole point of the coupon is
    # to find out how a boss behaves IN THE PROCESS THE PART IS PRINTED IN. A
    # coupon sliced at other settings answers a question nobody asked.
    # fit-coupon is not a sealing part either, and it is the one plate here that
    # carries several objects on purpose -- see print.sh. It is checked against the
    # same walls and layers for the same reason as fastener-coupon: it measures
    # how a slot comes out IN THE PROCESS THE TUBE IS PRINTED IN, and a coupon
    # sliced at other settings answers a question nobody asked.
    # cap-fit is the cap, cut to one measured tube. Same geometry class, same
    # bridges, same brim rules -- so it is checked exactly as `cap` is, and it
    # is named separately only so the PART is traceable, never to soften a rule.
    monobody|cap|cap-fit|dam|carrier|retainer|fastener-coupon|fit-coupon) ;;
    "") fail "no --part given; the brim rules are part-specific and cannot be inferred from the G-code" ;;
    *)  fail "unknown --part '$part'" ;;
esac
[[ -f "$g" ]] || fail "no such file: $g"
[[ -s "$g" ]] || fail "empty file: $g -- the slice produced nothing"

# A '; key = value' field, CRLF stripped. Empty means ABSENT, which is a failure.
field() {
    local v
    v=$(grep -aoE "^; $1 = .*" "$g" | head -1 | sed 's/^; [^=]*= *//' | tr -d '\r' || true)
    [[ -n "$v" ]] || fail "$1 absent from $g -- cannot verify it"
    printf '%s' "$v"
}

num() {  # num <key> <min> <max> <why>
    local v; v=$(field "$1")
    [[ "$v" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || fail "$1 = '$v' is not a number"
    awk -v v="$v" -v lo="$2" -v hi="$3" 'BEGIN{exit !(v+0 >= lo+0 && v+0 <= hi+0)}' \
        || fail "$1 = $v, wanted $2..$3 -- $4"
    echo "  $1 = $v"
}

eq() {   # eq <key> <want> <why>
    local v; v=$(field "$1")
    [[ "$v" == "$2" ]] || fail "$1 = '$v', wanted '$2' -- $3"
    echo "  $1 = $v"
}

pct() {  # pct <key> <min> <why> -- a '15%' field, compared as a number
    local v n; v=$(field "$1")
    [[ "$v" =~ ^[0-9]+(\.[0-9]+)?%$ ]] || fail "$1 = '$v' is not a percentage -- cannot verify it"
    n="${v%\%}"
    awk -v v="$n" -v lo="$2" 'BEGIN{exit !(v+0 >= lo+0)}' \
        || fail "$1 = $v, wanted >= $2% -- $3"
    echo "  $1 = $v"
}

echo "seal-check $g"
num layer_height 0.10 0.15 "0.2 mm cost ~31x leakage and +/-90% scatter"
num wall_loops 4 8 "the 2.4 mm wall is exactly 4 x 0.60; fewer loops leaves it unsealed"
num outer_wall_line_width 0.60 0.70 ">=0.64 sealed in test, 0.40 never did"
num inner_wall_line_width 0.60 0.70 ">=0.64 sealed in test, 0.40 never did"
num top_shell_layers 5 99 "closures leak, walls do not"
num bottom_shell_layers 5 99 "closures leak, walls do not"
num filament_flow_ratio 1.00 1.02 "0.95 is deliberate under-extrusion; 85-90% always leaked"

# INFILL, and it is TWO checks because the setting and the plate are different
# claims. Added 2026-09-30 after a retainer DEFORMED IN SERVICE, locally at each
# of its eight screws, on a plate that satisfied every other line of this file.
#
# The recipe row in ~/dev/ee/p1p/doc/gastight-and-watertight.md is >=25%, and the
# shared profile has been shipping 15% -- under its own floor -- on every part
# this script has ever passed, because sparse_infill_density is in the SHARED
# process profile and no per-part override ever mentioned it. Nothing here read
# it, so nothing caught it.
#
# A CLAMPED PART WANTS 100%, NOT 25%. The >=25%/<=50% band in that doc is about
# leakage through a WALL. A bolted part is loaded through its MIDDLE, where top
# and bottom shells say nothing: the measured failure was five consecutive
# layers, 0.6 mm, whose only structure between the screw-head bearing face and
# the sealing land was 15% crosshatch. wall_loops does not help -- walls stiffen
# a part in its own plane, and a screw head presses across them.
# NOT CHECKED, deliberately: skin_infill_density and skeleton_infill_density.
# Those two belong to Orca's LOCKED infill patterns (locked zigzag / crosszag)
# and are inert while sparse_infill_pattern is crosshatch, as it is here. They
# read 15% on every plate in the archive and mean nothing there, so asserting
# them would fail a correct plate for a value that never reached the plastic --
# and a guard that cries on an irrelevant field gets waived, taking the real
# check with it. If the pattern is ever changed to a locked one they become
# live and belong in this block.
case "$part" in
    # EVERY part here is either bolted through, clamped against a cord, or
    # carries the bosses the clamp is torqued into:
    #   retainer/carrier  the two halves of the membrane clamp, eight screws
    #   monobody          the head those eight screws thread into. NEARLY FREE:
    #                     its tube wall is walls-only (4 x 0.60 = 2.40), so the
    #                     r5 plate had sparse infill in 53 layers of 1113, all
    #                     at the head. 100% there is minutes, and it does NOT
    #                     add the shrinkage load the <=50% ceiling bounds.
    #   cap/cap-fit       prints gland-face-DOWN, so its sparse band (z 0.80 to
    #                     2.48 on cap-r1) sits behind the SEALING END.
    monobody|cap|cap-fit|carrier|retainer)
        eq sparse_infill_density 100% "a clamped or bolted part is loaded through its middle, and a crosshatch middle crushes under the screw heads -- measured 2026-09-30"
        # SOURCE OF TRUTH: the setting is intent, the feature list is the plate.
        # A modifier region, a per-object override or a future profile edit can
        # leave the header saying 100% while the part still contains crosshatch,
        # so assert the ABSENCE of the feature too. Independent of the key above
        # and the one that actually describes the defect.
        if grep -qa '^; FEATURE: Sparse infill' "$g"; then
            zs=$(awk '/^; Z_HEIGHT: /{z=$3} /^; FEATURE: Sparse infill/{print z}' "$g" \
                 | sort -n | uniq | tr '\n' ' ')
            fail "this plate contains sparse infill at z: $zs -- on a clamped part every one of those layers is a crush plane, whatever the density key says"
        fi
        echo "  no 'Sparse infill' feature on the plate"
        ;;
    # The coupons are not clamped and not sealing walls, so they keep the doc
    # band rather than 100%. They are still floored, because a coupon sliced
    # softer than the part answers a question nobody asked -- the same argument
    # this file already makes for their walls and layers.
    *)
        pct sparse_infill_density 25 "the doc floor for a non-clamped part"
        ;;
esac
# BRIM. Adhesion area is the product of brim width AND the brim actually being
# attached. Bambu ships brim_object_gap = 0.1 so brims snap off by hand, which on
# 2026-09-05 left a 146.6 mm tower standing on its own 219 mm2 end face with
# 581 mm2 of brim parked beside it, and it came off the plate at layer 928/1221.
# Checking the width alone passed that plate.
#
# But the correct value is OPPOSITE for different parts on this same profile,
# which is why --part is mandatory:
#
#   monobody  h/d 4.58, so it needs a fused brim -- but its bore at z=0 is the
#             SEAL BORE and nothing may be printed in it. This rule used to read
#             "its bore at z=0 mates with nothing (the cap skirt goes OVER the
#             tube). Fuse the brim, and put one in the bore." That was true of a
#             plain O27.2 cable end and became false at 56407da, when the cable
#             end became the O25.5 collar the cap's spigot enters on an O-ring.
#             The rule did not move with the part, so THIS CHECK REQUIRED THE
#             DEFECT: brim_width 12 in a O25.5 bore is wider than its 12.75 mm
#             radius, so the inner brim filled the bore with a welded 0.2 mm
#             disc and the cap would not go on (measured 2026-09-06, 1601 points
#             on layer 1 of print/monobody/plate_1.gcode). Outer only now.
#   carrier   prints WET FACE DOWN, so z=0 IS the membrane sealing land. A fused
#             brim cannot be removed without scarring the surface the seal is
#             made on, and an inner brim lands on the O16 aperture rim and the
#             six O2.8 bolt holes. Stay outside, and keep the gap.
#   retainer  prints groove-up so z=0 is non-sealing, but an inner brim still
#             narrows the six bolt clearance holes.
case "$part" in
    monobody)
        num brim_width 6 99 "h/d 4.58 in ASA is a warp and tip candidate"
        eq  brim_object_gap 0 "a brim with a gap is not holding the part down"
        # THE BRIM RULE IS NOW A CHOICE BETWEEN TWO REAL COSTS, and the evidence
        # decided it. outer_only is still correct about the bore: an inner brim
        # at this width does not ring the O27.55 mouth, it fills it, and the cap
        # cannot enter a plugged bore. But the SCORE on four-hour prints is:
        #
        #   with an inner brim     monobody-r2, 2026-09-06  -- PRINTED
        #   without                monobody-r3, 2026-09-09  -- fell overnight
        #   without                monobody-r4, 2026-09-09  -- tilted out of its
        #                          own brim at layer 880, stopped at 887, on a
        #                          freshly cleaned plate with the machine newly
        #                          calibrated for its room. PHOTOGRAPHED: brim
        #                          flat on the plate, tube leaning out of it.
        #
        # A plugged bore is work with a knife and the reamer the bore needs
        # anyway. A fallen tower is four hours and 34 cm3. So the inner brim is
        # allowed HERE, by name, with the reason attached -- and the rule is not
        # deleted, because it is still the thing that will tell the next person
        # why their cap will not go on.
        if [ "${MONOBODY_INNER_BRIM_WAIVER:-0}" = 1 ]; then
            echo "  WAIVED brim_type: inner brim allowed on the monobody -- 0 for 2"
            echo "         on towers without one (r3, r4). The z=0 bore WILL be"
            echo "         plugged by a one-layer disc: cut it out and ream to H7"
            echo "         BEFORE fitting a cap, or the cap will not go on."
        else
            eq  brim_type outer_only "the bore at z=0 is the O-ring seal bore -- an inner brim FILLS it and the cap will not go on. Set MONOBODY_INNER_BRIM_WAIVER=1 to allow it deliberately; see the note above for what that costs"
        fi
        ;;
    carrier|retainer)
        num brim_width 3 99 "some brim, but it must stay removable"
        eq  brim_object_gap 0.1 "a fused brim on the seal land cannot be removed without scarring it"
        eq  brim_type outer_only "an inner brim lands in the aperture and the bolt holes"
        ;;
    fit-coupon)
        # z=0 is a plain ring face and its label flange; nothing there mates.
        num brim_width 3 99 "a 16 mm-tall O32 ring in ASA lifts without one"
        eq  brim_type outer_only "an inner brim prints inside the bore, under the rails being measured"
        ;;
    fastener-coupon)
        # z=0 is a plain flat face that mates with nothing and carries no hole:
        # every hole enters from the TOP, the same way up as the head prints.
        # So the only brim requirement is that it holds a small ASA block down.
        num brim_width 3 99 "a 36 x 12 ASA block lifts a corner without one"
        ;;
    *)
        num brim_width 3 99 "warp resistance"
        ;;
esac
eq  filament_type ASA "the enclosure material is ASA (MEMBRANE.md)"
eq  enable_support 0 "no feature on this part overhangs; support inside a sealing bore is scrap"
# Arachne varies extrusion width to fill a wall, which is exactly what breaks the
# '2.4 = 4 x 0.60, no gap fill' property the model asserts.
eq  wall_generator classic "Arachne varies line width and defeats the 4 x 0.60 wall"

# THE BED THE SLICER THOUGHT IT HAD. OrcaSlicer's CLI does not resolve a machine
# preset's `inherits`, so the stock BBL leaf slices against Orca's built-in
# defaults -- a 200x200 bed 100 mm tall -- while the header still names the P1P.
# Measured: a plain dia-32 cylinder slices at 95 mm and fails at 110 with no
# message at all, and the 146.6 mm monobody could not be sliced until the machine
# profile carried its own resolved geometry. A 200x200 bed also silently shrinks
# the arrange area on a machine that has 256.
num printable_height 200 999 "the CLI defaults to 100 when the machine preset is unresolved"
area=$(field printable_area)
[[ "$area" == *"256x256"* ]] || fail "printable_area = '$area', wanted the P1P's 256x256 -- an unresolved machine preset defaults to 200x200"
echo "  printable_area = $area"

# ONE OBJECT PER PLATE. Identical parts measured 0 mTorr singly and 18 mTorr
# nine-up (gastight-and-watertight.md), so this is a leak setting, not tidiness.
objs=$(grep -aoE '^; printing object .* id:[0-9]+' "$g" | sed 's/.* id://' | sort -u | wc -l | tr -d ' ')
[[ "$objs" =~ ^[0-9]+$ && "$objs" -ge 1 ]] || fail "could not count objects on the plate"
[[ "$objs" -eq 1 ]] || fail "$objs objects on this plate; identical parts measured 0 mTorr singly and 18 mTorr nine-up"
echo "  objects on plate = 1"

# The header is the slicer's INTENT. What the plastic sees is the M104/M109
# target in force when the MODEL starts extruding -- and 270 is load-bearing
# beyond quality, because the wipe runs at initial_layer-20, so 260 puts it at
# 240, the bottom of ASA's range.
#
# ANCHOR ON THE FIRST LAYER CHANGE, not on the first extrusion. Everything above
# it is Bambu's start G-code, which purges at a deliberate `M109 S250 ;set nozzle
# to common flush temp` and restores 270 immediately before the model. Anchoring
# on the first positive-E move reads that 250 and condemns a correct slice --
# this check did exactly that on its first run.
eff=$(python3 - "$g" <<'NOZZLE'
import re, sys
target = None
started = False
cmd = re.compile(r'^\s*M1(?:04|09)(?=\s|$)(.*)$')
par = re.compile(r'\b([SR])\s*(-?\d+(?:\.\d+)?)')
# E values arrive as `E2`, `E.8` and `E.03329` -- a LEADING DOT is normal G-code
# and `\d+(\.\d+)?` does not match it. That cost a false failure on the dam,
# whose first model move is `G1 E.8 F1800` while the cap's happened to be `G0 E2`.
# `-.8` retractions must still not match, so keep the sign out of the group.
ext = re.compile(r'^\s*G[01](?=\s)(?=.*\bE\s*\+?(\d+\.?\d*|\.\d+))')
with open(sys.argv[1], errors='replace') as f:
    for line in f:
        line = line.rstrip('\r\n')
        if line.startswith('; CHANGE_LAYER'):
            started = True
        m = cmd.match(line)
        if m:
            vals = par.findall(m.group(1))
            if vals:
                target = float(vals[-1][1])
            continue
        if not started:
            continue
        e = ext.match(line)
        if e and float(e.group(1)) > 0:
            break
    else:
        sys.exit('no model extrusion found after a "; CHANGE_LAYER" marker')
print('' if target is None else repr(target))
NOZZLE
) || fail "could not find the model's first extrusion in $g -- refusing to guess the nozzle temperature"
[[ -n "$eff" ]] || fail "no M104/M109 target is in force when the model starts -- the nozzle is cold"
awk -v v="$eff" 'BEGIN{exit !(v+0 >= 265 && v+0 <= 280)}' \
    || fail "nozzle target at first extrusion is ${eff}C, wanted 265-280 (the wipe runs 20 below it)"
echo "  nozzle at first extrusion = ${eff}C"

# GEOMETRY, not settings. Everything above this line reads the header and trusts
# that the named settings produce the intended part. The 2026-09-06 monobody
# proves that is not enough: its header was correct by the rules in force, and
# the bore was still plugged. This asks where the extruder actually went.
# The same waiver reaches here, and it has to: bore_clear.py is the gate that
# actually catches an inner brim, so waiving brim_type alone would fail here
# instead and look like a different problem. What it measures stays TRUE -- the
# bore really is plugged -- so this does not pretend otherwise, it records that
# the plug is now deliberate and names the work that clears it.
#
# A REAL LIMIT OF THIS GATE, found in the 2026-09-09 Codex review and not fixed
# here: it samples straight G1 moves at their ENDPOINTS only, so a chord that
# crosses the bore with both ends outside it passes. It is sound against a brim
# (which fills the region with endpoints) and unsound against a travel-shaped
# path. Do not read a pass as proof of an empty bore.
if [ "${MONOBODY_INNER_BRIM_WAIVER:-0}" = 1 ] && [ "$part" = monobody ]; then
    python3 "$(dirname "$0")/bore_clear.py" "$g" --part "$part" || {
        echo "  WAIVED bore-clear: the O-ring bore IS obstructed, deliberately."
        echo "         POST-PROCESSING IS NOW MANDATORY, not optional:"
        echo "           1. cut out the one-layer brim disc across the bore;"
        echo "           2. deburr the 20 deg lead-in lip at the mouth (O27.55 --"
        echo "              a O25.7 reamer cannot reach residue stuck to it);"
        echo "           3. ream the parallel bore to O25.7 H7."
        echo "         Skip these and the cap spigot will not enter. This is the"
        echo "         trade accepted for a tower that stays standing."
    }
else
    python3 "$(dirname "$0")/bore_clear.py" "$g" --part "$part" \
        || fail "something is printed inside the cable-end seal bore (see above)"
fi

echo "seal-check OK"
