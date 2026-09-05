#!/usr/bin/env python3
"""The bed's layer quantization must match the profile that actually slices it.

WHY THIS EXISTS. The clamped membrane bed quantizes its groove depth, its seat
and the retainer's total height to the build layer, because squeeze is
1 - gap/cord: a depth that is not an integer number of layers is a depth the
SLICER picks, and the slicer does not know it is a seal dimension.

The layer height therefore appears twice -- as `face_layer_h` in
membrane_cartridge_common.scad, and as `layer_height` in
profiles/process_asa_seal.json -- and on 2026-09-05 those two numbers were 0.2
and 0.12. The model asserted its own multiple happily; the assert was measuring
a layer height nothing used. The seat was 0.2 = 1.67 real layers.

The same applies to the wall line width: `face_wall_min` is stated in beads, and
a 0.4-nozzle assumption against a profile that prints 0.6-wide walls is the same
class of error one level down.

Anything unreadable is a hard failure, never a default: a check that silently
skips is worse than no check, because it reports success.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
SCAD = os.path.join(CAD, 'membrane_cartridge_common.scad')
PROFILE = os.path.join(CAD, 'profiles', 'process_asa_seal.json')

# scad constant -> profile key. Both directions are load-bearing, so both are
# compared exactly rather than with a tolerance: these are declared decimals,
# not measurements.
PAIRS = [
    ('face_layer_h',       'layer_height'),
    ('face_first_layer_h', 'initial_layer_print_height'),
    ('face_line_w',        'outer_wall_line_width'),
]


def scad_num(src, name):
    m = re.search(r'^%s\s*=\s*([0-9.]+)\s*;' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit(
            "profile_check: %s is not a plain number in %s.\n"
            "It has probably become an expression. Read it and decide -- do NOT "
            "let this check pass by default, which is exactly how the bed came "
            "to be quantized to a layer height nothing used."
            % (name, os.path.basename(SCAD)))
    return float(m.group(1))


def main():
    src = open(SCAD).read()
    prof = json.load(open(PROFILE))
    bad = []
    for scad_name, prof_key in PAIRS:
        if prof_key not in prof:
            raise SystemExit("profile_check: %s has no %r" % (PROFILE, prof_key))
        a, b = scad_num(src, scad_name), float(prof[prof_key])
        mark = 'ok' if a == b else 'MISMATCH'
        print("  %-20s %-28s %6.3f  %6.3f  %s"
              % (scad_name, prof_key, a, b, mark))
        if a != b:
            bad.append((scad_name, a, prof_key, b))
    if bad:
        print()
        for scad_name, a, prof_key, b in bad:
            print("profile_check: %s = %g but %s = %g in %s"
                  % (scad_name, a, prof_key, b, os.path.basename(PROFILE)))
        raise SystemExit(
            "\nThe bed is quantized to a build that is not the one being sliced. "
            "Move the SCAD constant to match the profile and RE-DERIVE the "
            "depths, or slice with a profile that matches.")
    print("profile_check: the bed's quantization matches %s"
          % os.path.basename(PROFILE))


if __name__ == '__main__':
    main()
