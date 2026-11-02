# Rev B — 20 × 89 mm power-compaction candidate

The [board](o2-probe.kicad_pcb) reduces the [93 mm candidate](../revb-93/README.md)
by 4 mm through power-section placement and routing changes.
See the [power review](../../docs/REVB-89-POWER-REVIEW.md) for geometry and limits.

Revalidate/export from the project directory:

```sh
python3 make_review_revb_95.py --tip-trim-mm 2 --power-compact-mm 4
```

`review/` contains DRC/ERC, Gerbers, drills, assembly PDFs and a fingerprinted
manifest. Engineering review only; physical and analog-noise qualification remain open.
`power-seed.json` records the initial placement stage, before final local routing.
