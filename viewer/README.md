# Local Three.js viewer — superseded

> **This viewer shows the superseded Rev-A geometry, not the current probe.**
> Use `../cad/tools/view.py` (the three.js viewer in `../cad/viewer/`), or just
> run `./start.sh` here, which launches it on the whole-probe scene.
>
> Recorded 2026-09-23: this app was written on 2026-08-22 and last changed
> 2026-08-23. It does not load the CAD meshes; every dimension is typed into
> `app/ProbeViewer.tsx` (Ø32 tube, 20 × 119 mm board, finger diffusion head),
> so it cannot follow the model. The current design — membrane bed with
> carrier and retainer, radial-ring seal, monobody, bayonet cable-end cap —
> replaced it from 2026-09-05, and `cad/viewer` was built for it then rather
> than extending this app (commit `84ef6e3` says why). Kept for reference only.

```sh
./start.sh            # CURRENT probe: ../cad/tools/view.py --scene probe
./start.sh bed        # any other current scene (python3 ../cad/tools/view.py --list)
./start.sh legacy     # this superseded React viewer, on http://localhost:3333/
```

## The legacy app

This is a local-only Vite/React/Three.js viewer for the O₂ probe Rev-A model.
It has no hosting integration, remote data, analytics, authentication or
external runtime dependency.

`./start.sh legacy` installs dependencies on first use, starts Vite on
<http://localhost:3333/> and opens the browser (or just opens it if the viewer
is already running). A static server such as `python3 -m http.server` does not
work — it serves `src/main.tsx` uncompiled and the page stays blank.
Use `npm test` for a production build and basic source/output checks.

The model includes the enclosure, PCB/probe, PMV15T membrane cartridge,
passive drained diffusion head and cable cap. Dimensions remain provisional as
documented in `../cad/README.md`.
