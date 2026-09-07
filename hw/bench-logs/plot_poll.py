#!/usr/bin/env python3
"""Plot a CSV written by firmware/tools/o2p_poll.py.

    python3 bench-logs/plot_poll.py modbus-poll-2026-09-06.csv -o poll.webp

There is deliberately almost nothing here. The figure - which panels, in which
order, with which thresholds drawn on them - is defined once in
firmware/tools/o2p_plot.py and shared with every other tool that plots this
board, so a log from this morning and a heater run from this afternoon are the
same picture and can be read against each other. This file only chooses the
input and the title.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "firmware", "tools"))
import o2p_plot     # noqa: E402  # type: ignore[import-not-found]
import o2p_psychro  # noqa: E402  # type: ignore[import-not-found]


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv")
    ap.add_argument("-o", "--out", default="poll.webp")
    ap.add_argument("--title", default=None)
    ap.add_argument("--dry-basis", action="store_true",
                    help="also compute and plot O2 on a DRY basis. The probe "
                         "publishes wet basis until fe27d20 is flashed; this "
                         "applies the measurement-time half of that correction "
                         "offline, so the artefact can be seen against the "
                         "number it corrupts.")
    ap.add_argument("--pressure-hpa", type=float, default=1013.25,
                    help="total pressure assumed for --dry-basis (default "
                         "1013.25). The correction is weakly sensitive to it: "
                         "930 vs 1013 hPa moves it by about 0.3 %%.")
    args = ap.parse_args()

    with open(args.csv) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("!! %s has no rows" % args.csv)

    if args.dry_basis:
        # The arithmetic lives in firmware/tools/o2p_psychro.py, which checks
        # its Magnus coefficients and dry-air constant against src/ at call
        # time. A plotting script is the wrong place to keep a copy of a
        # physical constant the firmware also holds.
        problems = o2p_psychro.check_against_source()
        if problems:
            raise SystemExit("!! o2p_psychro disagrees with src/:\n   "
                             + "\n   ".join(problems))
        n, refused = 0, {}
        for r in rows:
            v, why = o2p_psychro.dry_from_wet(
                o2p_plot.num(r, "o2_comp_pct"),
                o2p_plot.num(r, "t_chamber_c"),
                o2p_plot.num(r, "rh_pct"),
                args.pressure_hpa)
            r["o2_dry_pct"] = "" if v is None else "%.4f" % v
            if v is None:
                refused[why] = refused.get(why, 0) + 1
            else:
                n += 1
        print("dry-basis correction applied to %d of %d rows at %.2f hPa"
              % (n, len(rows), args.pressure_hpa))
        for why, k in sorted(refused.items(), key=lambda kv: -kv[1]):
            print("  %5d row(s) left as a gap: %s" % (k, why))

    note = o2p_plot.plot(
        rows, args.out,
        source=args.csv,
        title=args.title or ("o2-probe over Modbus - %s"
                             % os.path.basename(args.csv)))
    print("wrote %s  (%d rows, %s)" % (args.out, len(rows), note))


if __name__ == "__main__":
    main()
