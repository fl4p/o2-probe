# Datasheet provenance

Where each PDF in this directory came from, so a claim sourced from one can be
re-checked without guessing which document or revision was read.

| file | part | document | retrieved | source URL |
|---|---|---|---|---|
| `BAT54W-G-vishay-85885-rev1.1.pdf` | Vishay **BAT54W-G** (D8) | **Document Number 85885, Rev. 1.1, 22-Feb-2018** | 2026-09-12 | `http://www.farnell.com/datasheets/3273859.pdf` |
| `BAT54-diodes-DS11005-rev34-2.pdf` | Diodes **BAT54 /A /C /S** | DS11005 Rev. 34 - 2, Nov 2023 | 2026-09-12 | `https://www.diodes.com/assets/Datasheets/ds11005.pdf` |
| `AP63203-diodes-DS41326-rev3-2.pdf` | Diodes **AP63203WU-7** (U1, buck) | DS41326 Rev. 3 - 2 | 2026-09-12 | `https://www.diodes.com/assets/Datasheets/AP63200-AP63201-AP63203-AP63205.pdf` |
| `PMEG4010CEH-nexperia-2023-10-12.pdf` | Nexperia **PMEG4010CEH** (D3) | Product data sheet, 12 Oct 2023 | 2026-09-12 | `https://assets.nexperia.com/documents/data-sheet/PMEG4010CEH.pdf` |
| `DS-0637-SGX-OX-ROHS-Mini-Issue2.pdf` | SGX-OX-ROHS-Mini (U11) | DS-0637 Issue 2 | — | — |
| `DS-0637-SGX-OX-ROHS-Mini-Issue1-SUPERSEDED.pdf` | same, superseded | DS-0637 Issue 1 | — | — |
| `tps7a20-SBVS338H.pdf` | TPS7A20 | SBVS338H | — | — |

SHA-256:

```
018c2d13b5848f4017e8e4e51db965a4a9b13c719307e30928804b2ad591cb13  BAT54W-G-vishay-85885-rev1.1.pdf
50b04e4e17bcf5db62164f6e5422e91546d0cace0ab2efed61660c3044b4fef0  BAT54-diodes-DS11005-rev34-2.pdf
ef99daa3789d835bc025dfcb4c605c5c2e6d3e7223e86d40b33e6b497ea5a722  AP63203-diodes-DS41326-rev3-2.pdf
b9130b677bcc15cb8aab672279f0ed5750e84380a6f512f717f7656401fac1f6  PMEG4010CEH-nexperia-2023-10-12.pdf
```

The AP63203 and PMEG4010CEH documents were added for the power-layout work:
the buck's own datasheet (loop geometry, BST/SW, thermal) and the series
reverse-polarity Schottky's (VF at load, and the reverse-leakage figure that D1
is there to clamp). Note the AP63203 file is the **family** datasheet covering
AP63200/01/03/05 — check the column, since `audit_bom` currently flags that the
purchase orders carry `AP63205WU-7` where the schematic asks for `AP63203WU-7`.

## What the two BAT54 documents establish

Both are here because the D8 correction of 2026-09-12 needed *both*: one to
condemn the original part, one to qualify the replacement.

**`BAT54-diodes-DS11005-rev34-2.pdf`** — Ordering Information (p. 1) lists
`BAT54-7-F` as **SOT23 (Standard)**. This is what makes the original
`BAT54-7-F` + `Diode_SMD:D_SOD-123` pairing wrong. The pinout figure on the same
page, read at 600 dpi, gives the single BAT54 as pin 1 = anode, pin 3 = cathode,
pin 2 unconnected.

**`BAT54W-G-vishay-85885-rev1.1.pdf`** — Mechanical Data (p. 1) gives **Case: SOD-123**
and the Parts Table gives circuit configuration **Single**, which is what makes
`BAT54W-G` a drop-in for the existing two-terminal footprint and authoritative
symbol. Electrical Characteristics gives `IR` **2 µA max at VR = 25 V**,
identical to the Diodes headline, so the leakage budget did not move with the
part.

**Note the suffix trap.** "W" means SOT-323 at Diodes *and* at Nexperia, but
SOD-123 at Vishay. `BAT54W-7-F` (Diodes) is SOT323; `BAT54W-G` (Vishay) is
SOD-123. These are not interchangeable and the part numbers look alike.

## The leakage gate: the curve is better than I claimed, and the part is worse

D8's selection gate is `Ir ≤ 1 µA at 1.2 V reverse, 85 °C`.

**Correction, 2026-09-12, from the Codex PCB session, verified here.** An earlier
version of this file and of the `gen_sch.py` comment said Fig. 3 plots
"−40 / 25 / 125 °C only", making 85 °C a wide interpolation. That was wrong, and
wrong in a specific way worth recording: **−40 / 25 / 125 °C is Fig. 1**, the
*forward* curve. **Fig. 3, the reverse-leakage curve, plots 25, 50, 75, 100 and
125 °C.** I read the two figures out of a `pdftotext` dump in which their legends
interleave, and assigned Fig. 1's legend to Fig. 3 — the exact merged-render trap
that the two-render rule exists to prevent, not applied to the document it was
adopted for.

So 85 °C is bracketed by two *plotted* curves, 75 °C and 100 °C, and the gate is
far more answerable than claimed. It is also, on a first reading, **failed**:

| Tj | Ir at VR ≈ 1.2 V (read off Fig. 3) |
|---|---|
| 25 °C | ~0.05 µA |
| 50 °C | ~0.8 µA |
| 75 °C | ~4.5 µA |
| 100 °C | ~21 µA |
| 125 °C | ~90 µA |

Log-interpolating 75 → 100 °C puts **85 °C at roughly 8 µA — about 8× the
gate**. Through the divider's 9.0 kΩ (R26‖R27) that is ~75 mV on VIN_MON, not
the 18 mV the `gen_sch.py` block comment budgets. These are *typical* curves; the
2 µA at 25 V / 25 °C maximum implies a max/typ spread of roughly 40×.

**This reading is by eye and is NOT the verdict.** Digitize Fig. 3 with `dsdig`
(`~/dev/pv/ee/datasheet-chart-digitizer`) before anything depends on the number.

The decision it feeds is not purely numeric, and belongs to Fab or the schematic
owner rather than to whoever digitizes the curve: VIN_MON is *health only*,
nothing scales by it, and its thresholds are 7 V and 15 V on a 12 V rail, so ~75 mV
of offset may well be acceptable — in which case the gate is too strict and should
be relaxed **explicitly, with the number written down**, not left silently unmet.
The alternative is a lower-leakage part. Either way, `85 °C` here is a worst-case
*ambient* assumption for a buried potted probe with no dissipation at this node.
