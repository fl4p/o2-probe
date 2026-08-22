# Local Three.js viewer

This is a local-only Vite/React/Three.js viewer for the O₂ probe Rev-A model.
It has no hosting integration, remote data, analytics, authentication or
external runtime dependency.

Run `npm install`, then `npm run dev`, and open the local URL printed by Vite.
Use `npm test` for a production build and basic source/output checks.

The model includes the enclosure, PCB/probe, PMV15T membrane cartridge,
passive drained diffusion head and cable cap. Dimensions remain provisional as
documented in `../cad/README.md`.
