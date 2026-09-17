# Attachments for the AISLER ODB++ bug report

Evidence for [`../2026-09-16-aisler-push-odb-bug-report.md`](../2026-09-16-aisler-push-odb-bug-report.md).
These files live in the repository rather than a scratch directory because the
email offers them to AISLER support and they have to still exist when it is sent.

Every archive is what AISLER Push for KiCad 0.3.2 uploads, reproduced by
`.work/aisler/plugin_export.py`, which mirrors `push_thread.py`'s `run()`. The
`-withodb` / `-noodb` pairs differ by exactly one file, `odb.zip`.

| file | board | `odb.zip` | AISLER result |
|---|---|---|---|
| `ring-board-withodb.zip` | o2-probe Rev B ring, 20 × 86 mm, as designed | present | **Failed to prepare production data** |
| `ring-board-noodb.zip` | the same board | absent | ready — 20 × 86 mm, 2 layers, 0.2 mm drill, 4 elongated holes |
| `minimal-repro-withodb.zip` | the same board with all 2 414 tracks, 209 vias and 6 zones deleted; 87 footprints remain | present | **Failed to prepare production data** |
| `minimal-repro-noodb.zip` | the same stripped board | absent | ready |
| `minimal-repro.kicad_pcb` | the stripped board's source, for regenerating the pair | — | — |

The stripped pair is the useful one: its ODB++ holds 171 + 98 copper features,
fewer than any board that passes, so the failure is not a size or complexity
limit and is not in the routing.

Regenerate the pair:

```sh
curl -sSL -o plugin.zip https://packages.aisler.net/packages/2/download.zip   # sha256 bec5d737…eaac7
unzip -q plugin.zip -d plugin
echo '[["minimal-repro.kicad_pcb", "minimal-repro"]]' > job.json
AISLER_PLUGIN=$PWD/plugin /Applications/KiCad/KiCad.app/Contents/Frameworks/\
Python.framework/Versions/Current/bin/python3 plugin_export.py job.json
```

The export is deterministic: regenerating `minimal-repro-withodb.zip` a day
later reproduced the same 120 636 bytes.

SHA-256, recorded 2026-09-17:

```
c4b9463b58eb1498b564fe7bf5fb34deeadce6d148de53e59035b362dfdfa857  ring-board-withodb.zip
8586fd3505299d39fc1c73bb0f78423b0f15299fd99de2e95ad06cf56704d3c8  ring-board-noodb.zip
2412fb023a44e78f6d54c754103e811d4520491e386fb5d053730aa02366c47c  minimal-repro-withodb.zip
a60e0cec4c7bf21ca470760ce594d1d681b986d30b5ac14b49875b40cfcda060  minimal-repro-noodb.zip
2b5e7ed2d0c3d2e374e1431b3a10d20b26c5f440e95150c99e8ad3eb1c4e7c74  minimal-repro.kicad_pcb
```
