# AISLER: the ODB++ archive in Push-for-KiCad 0.3.2 fails on this board

Bug report prepared 2026-09-16 for AISLER support. Section 1 is the email body;
the rest is the supporting evidence, included so the report can be checked
rather than believed.

Related: [the fab-readiness dispositions](2026-09-14-revb-86-ring-dispositions.md).
The local workaround applied to this machine is `tools/fix_aisler_push_plugin.py`.

> **Scope correction, 2026-09-16.** An earlier draft of this report claimed the
> bug hits every KiCad 10 push. That was an inference from one board and it is
> **wrong**: four other KiCad 10 boards, exported through the identical code
> path with `odb.zip` included, prepared without complaint. The report below
> reflects the measurement, not the inference.

> **Revised 2026-09-17, before sending.** The fourteen sandbox projects this
> report originally cited by ID have been deleted from the account, so those IDs
> now 404 and are no longer usable as references. Section 1 was rewritten to rest
> on two things that still exist and can be checked: the revision history of
> project **HAYAMAZV**, where the failing and succeeding uploads sit side by side
> and are individually addressable, and the archives in
> [`2026-09-16-aisler-evidence/`](2026-09-16-aisler-evidence/README.md), which are
> attached to the mail. The deleted IDs are kept in section 2 as a record of what
> was run, marked as no longer resolvable.
>
> Note also that HAYAMAZV has since moved on: revisions 9–11 are a **different
> board** — the merged tpsm-o2-psu panel, 20 × 112.83 mm — which inherited this
> project's ID from the KiCad title block, and revision 11 carries a live order.
> The bug report concerns revisions 1–8 only, and says so.

---

## 1. Email

**To:** support@aisler.net
**Subject:** Push-for-KiCad 0.3.2: the `odb.zip` it uploads makes one of my boards fail "Failed to prepare production data"

Hello,

I have a board that your CAM cannot prepare, and I have narrowed the cause to a
single file inside the archive the KiCad Push plugin uploads. I have a
workaround, so nothing is blocked at my end and this concerns no order of mine
— it is a bug report, and I have tried to do the isolation work for you.

**Symptom.** Project **HAYAMAZV** (`o2-probe`, 20 × 86 mm, 2 layers). Every
push of it landed on *"Failed to prepare production data — Our algorithms were
unfortunately not able to the prepare the production data for your project."*
The specification panel showed every field as *Not present*: Dimension / Size,
Layer Count, Minimal Drill Diameter, Elongated Hole Count, Castellated Hole
Count.

**Please look at revisions 1–8 of that project only.** Revisions 9–11 are a
different board — a merged panel that inherited this project's ID from the KiCad
title block — and revision 11 has an order against it. Nothing in this report
concerns them, and I am not asking for anything to be changed on that order.

**The trigger is `odb.zip`.** Plugin 0.3.2 added an ODB++ export and includes
the result in the upload. Re-uploading the same gerber and drill set with and
without that one file, changing nothing else:

| revision | `.kicad-push` marker | `odb.zip` | result |
|---|---|---|---|
| 1–4 | absent | **present** | **Failed to prepare production data** |
| 6 | present | **present** | **Failed to prepare production data** |
| 5, 7 | present | absent | Production data ready |
| 8 | absent | absent | Production data ready |

Revisions 1–4 are the plugin's own unmodified output. 5–8 are the same files
re-uploaded via `POST /p/HAYAMAZV/uploads.json` with only `odb.zip` added or
removed. It is necessary and sufficient; the marker file makes no difference.

Those revisions are still there and individually addressable — appending
`?revision_no=4` or `?revision_no=6` to the project URL shows the failure and
the five *Not present* fields; `?revision_no=8` shows the same design read
correctly and quoted: 20 mm × 86 mm, 2 layers, minimal drill 0.2 mm, 4 elongated
holes, from €19.01. I re-checked all three on 2026-09-17.

**Two attached archives make the same point offline.** They are what the plugin
uploads, and they differ by exactly one file:

- `ring-board-withodb.zip` — fails
- `ring-board-noodb.zip` — prepares

**It is not every board.** I exported four other KiCad 10 designs through the
same plugin code path, `odb.zip` included, and pushed each one — a 26 × 35 mm
2-layer board, a 110 × 75 mm one, a 31.5 × 12.5 mm one and an 85 × 60 mm one,
with 3 371 to 7 444 ODB++ features. All four prepared without complaint. So
something specific to my board's ODB++ defeats the importer, rather than
KiCad 10's ODB++ output in general.

**What I ruled out.** Each was tested by pushing a modified variant of the same
board with `odb.zip` still included. Every one still failed:

| variant | result |
|---|---|
| four internal cutouts removed from the outline | still fails |
| the 3 × 6 mm oval NPTH slot changed to a round hole | still fails |
| all 103 per-via tenting overrides stripped (removes the `TENTING_FRONT` / `TENTING_BACK` layers KiCad emits) | still fails |
| **all 2 414 tracks, 209 vias and 6 zones deleted** — ODB++ down to 171 + 98 copper features, far fewer than any of the four boards that pass | still fails |

That last one is the interesting one. With the copper gone the archive is
*smaller and simpler* than every board that succeeds, and it still fails — so
this is not a size or complexity limit, and it is not in the routing. It is
something in the footprints, pads, drills, outline, documentation layers or
stackup that survives that strip.

It is attached as the minimal reproducer, again as a pair:

- `minimal-repro-withodb.zip` — fails
- `minimal-repro-noodb.zip` — prepares

**What would help.** Your importer presumably logs why it gave up on this
archive. That one line would finish this off, and I am happy to test any
candidate fix.

**The ODB++ itself** is generated by KiCad, not by the plugin — `push_thread.py`
calls `pcbnew.PCB_IO_MGR.Save(PCB_IO_MGR.ODBPP, ...)` with `units=mm`,
`sigfig=6`. Its `misc/info`:

```
ODB_VERSION_MAJOR=8
ODB_VERSION_MINOR=1
ODB_SOURCE=KiCad EDA
SAVE_APP=KiCad EDA 10.0.5
```

**A second, unrelated bug in the same function.** `push_thread.py` does:

```python
open(magicFilename, 'a').close()
```

`magicFilename` is the bare relative name `.kicad-push`, so the marker is
created in whatever directory the pcbnew process happens to be in — never in
`temp_dir`, which is the directory that gets zipped a few lines later. The
marker therefore never reaches you, and a stray zero-byte `.kicad-push`
accumulates in the user's project folder instead. Mine landed in my board's
source directory. Presumably it should be:

```python
open(os.path.join(temp_dir, magicFilename), 'a').close()
```

My table above shows this one is harmless to the upload, but it is still litter.

**Environment.** macOS 15 (Darwin 24.6.0), KiCad 10.0.5, AISLER Push for KiCad
0.3.2 (`packages.aisler.net/packages/2/download.zip`, sha256
`bec5d737bd7837362b396ee3941864033ae3e339426f2ee9d6fe8089514eaac7`), board
`o2-probe` Rev B, 20 × 86 mm, 2 layers, 87 footprints, 216 PTH, 8 NPTH.

I have already deleted the sandbox projects I created while isolating this, so
the only one left is HAYAMAZV.

Best regards,
Fabian

---

## 2. Evidence

### 2.1 What the plugin uploads

`push_thread.py` builds a temp directory with the gerbers (`plotPlan`),
Excellon PTH/NPTH, `netlist.ipc` (IPC-356), `components.json`, and — new in
0.3.2 — `odb.zip`, zips it and POSTs it to `/p/<PROJECT_ID>/uploads.json`.

The stored revision-4 archive, downloaded back from AISLER, held 16 files: nine
gerbers, two drill files, `netlist.ipc`, `components.json`, `odb.zip`, and no
`.kicad-push`.

### 2.2 The three outcomes AISLER shows

Worth distinguishing, because two of them look similar at a glance:

- **"Your production data is ready"** — the specification table is filled in.
- **"Failed to prepare production data"** — table all *Not present*. This is
  the bug.
- **"Critical issues with your board"** — table also all *Not present*, but the
  design was parsed and rejected on DFM grounds. Not the same thing.

### 2.3 Revision log, project HAYAMAZV

| rev | created | source | `.kicad-push` | `odb.zip` | result |
|---|---|---|---|---|---|
| 1 | 2026-09-14 19:01 | plugin | absent | present | failed |
| 2 | 2026-09-14 19:02 | plugin | absent | present | failed |
| 3 | 2026-09-14 19:03 | plugin | absent | present | failed |
| 4 | 2026-09-16 10:41 | plugin | absent | present | failed |
| 5 | 2026-09-16 | manual | present | absent | **ready** |
| 6 | 2026-09-16 | manual | present | present | failed |
| 7 | 2026-09-16 | manual | present | absent | **ready** |
| 8 | 2026-09-16 11:42 | manual | absent | absent | **ready** |
| 9–11 | 2026-09-16 13:00 / 13:25 / 15:10 | plugin | — | — | **different board** |

Revisions 9–11 are not part of this report. They are the merged tpsm-o2-psu
panel, 20 × 112.83 mm with 6 elongated holes, which inherited the `HAYAMAZV`
project ID from the KiCad title block because the panel was derived from this
project's files. Revision 11 carries order 2026-59303. Worth knowing as a hazard
of the plugin's ID-in-title-block scheme: a derived board silently orders into
the parent's project.

States re-verified 2026-09-17 by rendering each revision page: rev 4 FAILED with
5 × *Not present*, rev 6 FAILED with 5 × *Not present*, rev 8 shows 20 mm × 86 mm
with none.

Revision 4 additionally went up as a 4-layer board — the board was open in
pcbnew with two extra copper layers enabled, carrying nothing but the 216
through-hole pads. A local mistake, not part of this report: revision 1 was a
clean 2-layer package and failed identically.

### 2.4 Cross-project control set

> The eight-character project IDs below were deleted from the AISLER account on
> 2026-09-17 and **no longer resolve**. They are kept as a record of which upload
> produced which result, not as links.

Exported with `tools/../.work/aisler/plugin_export.py`, which mirrors
`push_thread.py`'s `run()` and emits both a `-withodb` and a `-noodb` archive.

| project | board | verdict |
|---|---|---|
| GACGHXGG | dmm-mux | ready |
| FWQCJIRA | relay-mux | ready |
| WIFZYLLR | heliosync sensor | ready |
| UNWDNQWL | debug-probe | ready |
| AMBGDYOJ / HQJLHXQP | AISLER's own `aisler-2-layer-simple-drc` sample, with / without odb | critical DFM — inconclusive |
| CNGVLHWG / TKWYOEZL | spi-iso-150, with / without odb | critical DFM — inconclusive |
| RKXCHRUX / WQFQVHYR | pwr-protect, with / without odb | critical DFM — inconclusive |

The three inconclusive boards produced a near-empty ODB++ (16.5 kB, zero
features) with KiCad logging *"Failed to get board outline"*, so their CAM
result came from the gerbers and says nothing about `odb.zip`. Kept here only
so the record is complete.

### 2.5 Variants of the failing board

> The eight-character project IDs below were deleted from the AISLER account on
> 2026-09-17 and **no longer resolve**. They are kept as a record of which upload
> produced which result, not as links.

| variant | project | ODB++ change | result |
|---|---|---|---|
| cutouts removed | WBNJUHEV | profile 1 island + 4 holes → 1 island | fails |
| oval NPTH made round | PNUBDUKN | `oval3000.0x6000.0` → `r3000.0` | fails |
| per-via tenting stripped | JPZSXBWD | `TENTING_FRONT` / `TENTING_BACK` layers gone | fails |
| tracks, vias and zones deleted | OLBVWPNB | f.cu 1867 → 171, b.cu 1274 → 98 | fails |

The `tracks, vias and zones deleted` variant is attached to the email as
`minimal-repro-withodb.zip` / `minimal-repro-noodb.zip`, with its board source,
in [`2026-09-16-aisler-evidence/`](2026-09-16-aisler-evidence/README.md).

Also checked and exonerated without an upload: `comp_+_bot` (the heliosync
sensor has it and passes) and the `matrix/matrix` layer table (structurally
identical to a passing board, row for row).

### 2.6 Not the cause

Checked against the exported artifacts before the isolation test, each one ruled
out:

- **Board outline.** One closed outer contour plus four closed cutouts; no
  dangling endpoints, no self-intersections, no overlap; Edge.Cuts stroke
  0.05 mm, under the 0.45 mm contour-conversion threshold.
- **Cutouts.** 2 × (0.8 × 14 mm) and 2 × (1.5 × 6.75 mm) — under AISLER's
  preferred 1.8 mm milling width but at or above the 0.8 mm NPTH-slot minimum,
  and nibbled rather than milled. ~41 mm total, inside the 75 mm fair-use
  allowance.
- **Copper near cutouts.** Nothing within 0.25 mm.
- **Degenerate geometry.** No zero-chord or collinear arcs; every zero-annular-
  ring pad is NPTH, which is normal.
- **Design-rule violations.** Real, but not this: AISLER reads and quotes the
  board once `odb.zip` is gone. 202 vias at 0.20 mm drill against a 0.25 mm
  ENIG minimum, and 408 track segments at 0.10 mm against 0.125 mm. Those stay
  a live question for checkout and are tracked in the dispositions document,
  not here.

## 3. The local fix

`tools/fix_aisler_push_plugin.py` comments out the `exportODB` call and
corrects the marker-file path in the installed plugin. It backs the original up
as `push_thread.py.aisler-orig`, compile-checks the result, rolls back if the
patch does not compile, and takes `--revert`.

Applied 2026-09-16 to both installed copies on this machine:

```
~/Documents/KiCad/10.0/3rdparty/plugins/com_github_aislerhq_PushForKiCad/push_thread.py
~/Documents/KiCad/9.0/3rdparty/plugins/com_github_aislerhq_PushForKiCad/push_thread.py
```

Two notes for whoever runs this next:

- The PCM flattens the package — the modules sit directly in the package
  directory, not in the `plugins/` subdirectory the source zip uses — and it
  replaces the dots in the identifier with underscores.
- `~/Documents` is TCC-protected on macOS. A shell without Documents or Full
  Disk Access sees the path as "Operation not permitted", which `glob` reports
  as simply no match. Run the script from Terminal.app.

Re-run it after any PCM update: an update reinstalls the upstream file.

Given section 2.4, the patch is a local workaround for this board, not
something every KiCad 10 user needs.
