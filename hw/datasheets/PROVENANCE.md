# Datasheet provenance

Where each PDF in this directory came from, so a claim sourced from one can be
re-checked without guessing which document or revision was read.

| file | part | document | retrieved | source URL |
|---|---|---|---|---|
| `BAT54W-G-vishay-86409.pdf` | Vishay **BAT54W-G** (D8) | Vishay doc 86409 | 2026-09-12 | `http://www.farnell.com/datasheets/3273859.pdf` |
| `BAT54-diodes-DS11005-rev34-2.pdf` | Diodes **BAT54 /A /C /S** | DS11005 Rev. 34 - 2, Nov 2023 | 2026-09-12 | `https://www.diodes.com/assets/Datasheets/ds11005.pdf` |
| `DS-0637-SGX-OX-ROHS-Mini-Issue2.pdf` | SGX-OX-ROHS-Mini (U11) | DS-0637 Issue 2 | — | — |
| `DS-0637-SGX-OX-ROHS-Mini-Issue1-SUPERSEDED.pdf` | same, superseded | DS-0637 Issue 1 | — | — |
| `tps7a20-SBVS338H.pdf` | TPS7A20 | SBVS338H | — | — |

SHA-256:

```
018c2d13b5848f4017e8e4e51db965a4a9b13c719307e30928804b2ad591cb13  BAT54W-G-vishay-86409.pdf
50b04e4e17bcf5db62164f6e5422e91546d0cace0ab2efed61660c3044b4fef0  BAT54-diodes-DS11005-rev34-2.pdf
```

## What the two BAT54 documents establish

Both are here because the D8 correction of 2026-09-12 needed *both*: one to
condemn the original part, one to qualify the replacement.

**`BAT54-diodes-DS11005-rev34-2.pdf`** — Ordering Information (p. 1) lists
`BAT54-7-F` as **SOT23 (Standard)**. This is what makes the original
`BAT54-7-F` + `Diode_SMD:D_SOD-123` pairing wrong. The pinout figure on the same
page, read at 600 dpi, gives the single BAT54 as pin 1 = anode, pin 3 = cathode,
pin 2 unconnected.

**`BAT54W-G-vishay-86409.pdf`** — Mechanical Data (p. 1) gives **Case: SOD-123**
and the Parts Table gives circuit configuration **Single**, which is what makes
`BAT54W-G` a drop-in for the existing two-terminal footprint and authoritative
symbol. Electrical Characteristics gives `IR` **2 µA max at VR = 25 V**,
identical to the Diodes headline, so the leakage budget did not move with the
part.

**Note the suffix trap.** "W" means SOT-323 at Diodes *and* at Nexperia, but
SOD-123 at Vishay. `BAT54W-7-F` (Diodes) is SOT323; `BAT54W-G` (Vishay) is
SOD-123. These are not interchangeable and the part numbers look alike.

## The leakage gate is NOT closed by either document

D8's selection gate is `Ir ≤ 1 µA at 1.2 V reverse, 85 °C`. Vishay 86409
**Fig. 3** (Typical Reverse Current vs. Reverse Voltage vs. junction temperature)
plots **−40 °C, 25 °C and 125 °C only**. 85 °C is an interpolation between
plotted curves, not a specified value, and the 2 µA headline is quoted at 25 V,
not at the 1.2 V this node applies.

Digitize Fig. 3 with `dsdig` (`~/dev/pv/ee/datasheet-chart-digitizer`) rather
than reading it by eye. Until that is done the gate is **unmet**.
