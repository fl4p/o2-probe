#!/usr/bin/env python3
"""Plot a CSV written by firmware/tools/o2p_poll.py.

    python3 bench-logs/plot_poll.py modbus-poll-2026-09-06.csv -o poll.png

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
import o2p_plot  # noqa: E402  # type: ignore[import-not-found]


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("csv")
    ap.add_argument("-o", "--out", default="poll.png")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    with open(args.csv) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("!! %s has no rows" % args.csv)

    note = o2p_plot.plot(
        rows, args.out,
        title=args.title or ("o2-probe over Modbus - %s"
                             % os.path.basename(args.csv)))
    print("wrote %s  (%d rows, %s)" % (args.out, len(rows), note))


if __name__ == "__main__":
    main()
