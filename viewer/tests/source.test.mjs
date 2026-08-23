import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("build contains the local viewer entry point", async () => {
  const html = await readFile(new URL("../dist/index.html", import.meta.url), "utf8");
  assert.match(html, /O₂ Probe · Rev-A 3D Model/);
  assert.match(html, /<div id="root"><\/div>/);
  await access(new URL("../dist/assets/", import.meta.url));
});

test("viewer exposes all requested mechanical parts", async () => {
  const source = await readFile(new URL("../app/ProbeViewer.tsx", import.meta.url), "utf8");
  for (const label of ["Enclosure", "O₂ probe", "Membrane", "Diffusion head", "Cable cap"])
    assert.match(source, new RegExp(label));
  assert.doesNotMatch(source, /Wieselhof/);
});

test("viewer uses the controlled shortened Rev-A datums", async () => {
  const source = await readFile(new URL("../app/ProbeViewer.tsx", import.meta.url), "utf8");
  assert.match(source, /Ø32 \/ Ø28 × 129 mm/);
  assert.match(source, /20 × 119 mm PCB/);
  assert.match(source, /tubeGeometry\(14, 16, 129\)/);
  assert.match(source, /BoxGeometry\(20, 119, 1\)/);
  assert.doesNotMatch(source, /20 × 125/);
  assert.doesNotMatch(source, /135 mm long PVC-U sleeve/);
});
