# Rev B — 20 × 93 mm tip-trim candidate

The [board](o2-probe.kicad_pcb) removes 2 mm from the tip of the retained
[95 mm comparison](../revb-95/README.md), with component and slot positions fixed.
See the [tip review](../../docs/REVB-93-TIP-REVIEW.md) for copper changes and limits.

Revalidate/export from the project directory:

```sh
python3 make_review_revb_95.py --tip-trim-mm 2
```

`review/` contains DRC/ERC, Gerbers, drills, assembly PDFs and a fingerprinted
manifest. Engineering review only; existing physical qualification remains open.
