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

echo "seal-check $g"
num layer_height 0.10 0.15 "0.2 mm cost ~31x leakage and +/-90% scatter"
num wall_loops 4 8 "the 2.4 mm wall is exactly 4 x 0.60; fewer loops leaves it unsealed"
num outer_wall_line_width 0.60 0.70 ">=0.64 sealed in test, 0.40 never did"
num inner_wall_line_width 0.60 0.70 ">=0.64 sealed in test, 0.40 never did"
num top_shell_layers 5 99 "closures leak, walls do not"
num bottom_shell_layers 5 99 "closures leak, walls do not"
num filament_flow_ratio 1.00 1.02 "0.95 is deliberate under-extrusion; 85-90% always leaked"
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
        eq  brim_type outer_only "the bore at z=0 is the O-ring seal bore -- an inner brim FILLS it and the cap will not go on"
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
python3 "$(dirname "$0")/bore_clear.py" "$g" --part "$part" \
    || fail "something is printed inside the cable-end seal bore (see above)"

echo "seal-check OK"
