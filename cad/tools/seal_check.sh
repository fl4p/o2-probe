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

g="${1:-}"
fail() { echo "SEAL-CHECK FAIL: $*" >&2; exit 1; }
[[ -n "$g" ]] || fail "no G-code file given"
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
num brim_width 3 99 "a 147 mm ASA tube is a warp candidate"
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

echo "seal-check OK"
