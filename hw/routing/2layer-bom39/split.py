#!/usr/bin/env python3
"""Split a board's unconnected items into GND pour islands and real signal opens.

Measured 2026-09-05: the DRC total everyone has been ranking on mixes two different
quantities.  Signal opens are deterministic and are the routing result.  Pour-island
items depend on WHICH refill ran -- the same Freerouting board graded 26 islands under
`kicad-cli --refill-zones` and 36 under a `pcbnew.ZONE_FILLER` refill, moving its total
from 42 to 52 while its signal count did not move at all.  Rank on signal opens.
"""
import json, re, sys, collections, subprocess, pathlib
K = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
HERE = pathlib.Path(__file__).resolve().parent
for board in sys.argv[1:]:
    b = pathlib.Path(board).with_suffix("")
    for ext in (".kicad_pro", ".kicad_dru"):
        (b.parent / (b.name + ext)).write_bytes((HERE / ("o2-probe" + ext)).read_bytes())
    out = str(b) + ".rz.json"
    subprocess.run([K, "pcb", "drc", "--severity-all", "--refill-zones", "--format", "json",
                    "-o", out, str(b) + ".kicad_pcb"], capture_output=True)
    d = json.load(open(out))
    islands, nets = 0, collections.Counter()
    for u in d["unconnected_items"]:
        if all("Zone" in it["description"] for it in u["items"]):
            islands += 1
            continue
        m = re.search(r"\[(/[^\]]+)\]", u["items"][0]["description"])
        nets[m.group(1) if m else "?"] += 1
    bad = {v["type"]: 0 for v in d["violations"]}
    for v in d["violations"]:
        bad[v["type"]] += 1
    copper = {k: v for k, v in bad.items() if k in
              ("clearance", "shorting_items", "tracks_crossing", "hole_clearance",
               "copper_edge_clearance", "track_dangling", "via_dangling", "isolated_copper")}
    print(f"{b.name:16} SIGNAL {sum(nets.values()):3} | pour islands {islands:3} "
          f"| total {len(d['unconnected_items']):3} | copper {copper}")
    print(f"{'':16} {dict(nets.most_common(10))}")
