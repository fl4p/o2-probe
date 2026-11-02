# Rev B — 20 × 89 mm with autonomous heater cutoff

Current engineering-review candidate: U16 TMP302BDRLR and C35 100 nF.
85 °C nominal trip; 10 °C nominal hysteresis. OUT clamps HEATER_GATE.
See [review and qualification limits](../../docs/REVB-TMP302-REVIEW.md).

From the project directory, run `python3 make_review_tmp302.py`.
The older `make_review_revb_95.py` selects historical candidates.

`review/` contains fresh ERC/DRC, schematic/assembly PDFs, fabrication-format
review exports and a fingerprinted manifest. **Not order-ready.**
