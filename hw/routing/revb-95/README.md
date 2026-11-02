# Rev B — 20 × 95 mm review candidate

This is the routed 95 mm alternative requested on 10 September 2026: 12 mm
shorter (11.2%) than [the retained 107 mm candidate](../revb-interfaces/README.md).
Open [o2-probe.kicad_pcb](o2-probe.kicad_pcb) in KiCad. Its schematic, original
rules and local libraries are beside it.

The circuit is unchanged: 99 footprints, 299 assigned physical pins, two copper
layers, 1.0 mm board thickness. J5/F3 remain deferred to
[optional Rev C](../../plans/REVC-HEATED-RING.md).

[Review and assembly notes](../../docs/REVB-95-REVIEW.md) record the changes,
independent review, warning dispositions and qualification limits.
[The review exports](review/) contain saved/refilled DRC, ERC, Gerbers, drills,
assembly PDFs, source fingerprints and SHA256SUMS. This is an engineering-review
candidate; it is not order-ready.

Revalidate and export the authored PCB snapshot from the project directory:

```sh
python3 make_review_revb_95.py
python3 -m unittest test_revb_95 -q
```

`compact_revb_95.py --output /tmp/new-o2-95-seed` creates an **unrouted placement
seed** from the pinned 107 mm source. It is not a deterministic reconstruction
of this finished routing. Subsequent routing, ground repair, C16/C33 relocation,
TP5 feed and clearance fixes are preserved in this PCB snapshot. The seed tool
refuses to overwrite this accepted candidate or an existing output directory;
`seed-changes.json` records the initial copper-removal stage only.
