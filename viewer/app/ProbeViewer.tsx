import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

type PartKey = "enclosure" | "probe" | "membrane" | "head" | "cap";

type ViewerModel = {
  groups: Record<PartKey, THREE.Group>;
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  clippedMaterials: THREE.Material[];
};

const PARTS: Array<{ key: PartKey; label: string; detail: string; color: string }> = [
  { key: "enclosure", label: "Enclosure", detail: "Ø32 / Ø28 × 129 mm", color: "#b9c2ca" },
  { key: "probe", label: "O₂ probe", detail: "20 × 119 mm PCB", color: "#2b7f67" },
  { key: "membrane", label: "Membrane", detail: "PMV15T coupon", color: "#f1ead8" },
  { key: "head", label: "Diffusion head", detail: "passive drained guard", color: "#de713b" },
  { key: "cap", label: "Cable cap", detail: "potting + strain relief", color: "#262c31" },
];

const EXPLODED: Record<PartKey, THREE.Vector3> = {
  enclosure: new THREE.Vector3(0, 0, 0),
  probe: new THREE.Vector3(-50, 0, 0),
  membrane: new THREE.Vector3(42, 8, 0),
  head: new THREE.Vector3(58, 2, 0),
  cap: new THREE.Vector3(-28, -8, 0),
};

const ASSEMBLED: Record<PartKey, THREE.Vector3> = {
  enclosure: new THREE.Vector3(),
  probe: new THREE.Vector3(),
  membrane: new THREE.Vector3(),
  head: new THREE.Vector3(),
  cap: new THREE.Vector3(),
};

function standard(color: THREE.ColorRepresentation, options: Partial<THREE.MeshStandardMaterialParameters> = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.62, metalness: 0.04, ...options });
}

function tubeGeometry(innerRadius: number, outerRadius: number, height: number, segments = 96) {
  const half = height / 2;
  return new THREE.LatheGeometry(
    [
      new THREE.Vector2(innerRadius, -half),
      new THREE.Vector2(outerRadius, -half),
      new THREE.Vector2(outerRadius, half),
      new THREE.Vector2(innerRadius, half),
    ],
    segments,
  );
}

function mesh(geometry: THREE.BufferGeometry, material: THREE.Material, part: PartKey) {
  const value = new THREE.Mesh(geometry, material);
  value.castShadow = true;
  value.receiveShadow = true;
  value.userData.part = part;
  return value;
}

function horizontalDisc(radius: number, material: THREE.Material, part: PartKey) {
  const value = mesh(new THREE.CircleGeometry(radius, 72), material, part);
  value.rotation.x = -Math.PI / 2;
  return value;
}

function horizontalRing(inner: number, outer: number, material: THREE.Material, part: PartKey) {
  const value = mesh(new THREE.RingGeometry(inner, outer, 72), material, part);
  value.rotation.x = -Math.PI / 2;
  return value;
}

function createProbeModel(scene: THREE.Scene, renderer: THREE.WebGLRenderer, camera: THREE.PerspectiveCamera, controls: OrbitControls): ViewerModel {
  const groups = {} as Record<PartKey, THREE.Group>;
  PARTS.forEach(({ key }) => {
    const group = new THREE.Group();
    group.name = key;
    group.userData.part = key;
    group.userData.target = new THREE.Vector3();
    groups[key] = group;
    scene.add(group);
  });

  const clippedMaterials: THREE.Material[] = [];

  // Enclosure: 32 mm OD, provisional 28 mm ID, 129 mm long PVC-U sleeve.
  const shellMaterial = standard("#b7c1c9", {
    transparent: true,
    opacity: 0.28,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  clippedMaterials.push(shellMaterial);
  const shell = mesh(tubeGeometry(14, 16, 129), shellMaterial, "enclosure");
  groups.enclosure.add(shell);

  const railMaterial = standard("#87939c", { transparent: true, opacity: 0.72 });
  for (const x of [-10.75, 10.75]) {
    const rail = mesh(new THREE.BoxGeometry(1.5, 105, 2.4), railMaterial, "enclosure");
    rail.position.set(x, -4, 0);
    groups.enclosure.add(rail);
  }

  const potMaterial = standard("#75a8bd", { transparent: true, opacity: 0.12, depthWrite: false });
  const pot = mesh(new THREE.CylinderGeometry(13.65, 13.65, 82, 72), potMaterial, "enclosure");
  pot.position.y = -18.5;
  groups.enclosure.add(pot);

  // The actual PCB datum: 20 × 119 × 1 mm, cable end at y=-59.5.
  const board = mesh(new THREE.BoxGeometry(20, 119, 1), standard("#236a55"), "probe");
  groups.probe.add(board);

  const copper = standard("#d7a83a", { metalness: 0.48, roughness: 0.35 });
  for (let i = 0; i < 4; i += 1) {
    const pad = mesh(new THREE.BoxGeometry(3.2, 6.2, 0.18), copper, "probe");
    pad.position.set(-7.5 + i * 5, -55, 0.6);
    groups.probe.add(pad);
  }

  const componentMaterial = standard("#171d22", { roughness: 0.45 });
  const componentSpecs: Array<[number, number, number, number, number, number]> = [
    [-5, -42, 6, 8, 3.4, 1.9],
    [4.5, -40, 7.2, 9, 4.5, 2.2],
    [0, -22, 10, 12, 4.2, 2.5],
    [-5.8, -3, 5.4, 7.2, 3.1, 1.8],
    [4.8, 11, 6.4, 8.4, 3.5, 2.0],
  ];
  componentSpecs.forEach(([x, y, w, h, d, z]) => {
    const component = mesh(new THREE.BoxGeometry(w, h, d), componentMaterial, "probe");
    component.position.set(x, y, z);
    groups.probe.add(component);
  });

  const potLine = mesh(new THREE.BoxGeometry(20.4, 0.55, 1.25), standard("#ef6c4a"), "probe");
  potLine.position.set(0, 22.5, 0);
  groups.probe.add(potLine);

  const heater = mesh(new THREE.BoxGeometry(18, 22, 0.16), standard("#c8823d", { metalness: 0.3 }), "probe");
  heater.position.set(0, 37.5, -0.6);
  groups.probe.add(heater);

  // SGX-OX-ROHS-Mini body: Ø14.4 × 8.3 mm at board y=93.5 mm datum.
  const cellBody = mesh(new THREE.CylinderGeometry(7.2, 7.2, 8.3, 64), standard("#d8d9d5", { metalness: 0.28 }), "probe");
  cellBody.rotation.x = Math.PI / 2;
  cellBody.position.set(0, 34, 4.65);
  groups.probe.add(cellBody);
  const cellFace = mesh(new THREE.CylinderGeometry(5.3, 5.3, 0.4, 64), standard("#989e9d"), "probe");
  cellFace.rotation.x = Math.PI / 2;
  cellFace.position.set(0, 34, 8.98);
  groups.probe.add(cellFace);
  for (const x of [-2.54, 0, 2.54]) {
    const pin = mesh(new THREE.CylinderGeometry(0.32, 0.32, 2.5, 16), copper, "probe");
    pin.rotation.x = Math.PI / 2;
    pin.position.set(x, 31.5, -1.1);
    groups.probe.add(pin);
  }

  for (const [x, y] of [[0, 56.5], [6, 50.5]] as Array<[number, number]>) {
    const gasSensor = mesh(new THREE.BoxGeometry(3, 3, 1.2), standard("#2d3338"), "probe");
    gasSensor.position.set(x, y, 1.15);
    groups.probe.add(gasSensor);
  }

  // Replaceable carrier, support grid, 0.18 mm PTFE coupon and gasket.
  const carrierMaterial = standard("#ece7d9");
  const carrier = mesh(tubeGeometry(9.4, 13.65, 2), carrierMaterial, "membrane");
  carrier.position.y = 67.5;
  groups.membrane.add(carrier);
  const membraneMaterial = standard("#f7f4e8", { transparent: true, opacity: 0.78, side: THREE.DoubleSide });
  const membrane = horizontalDisc(9.25, membraneMaterial, "membrane");
  membrane.position.y = 68.6;
  groups.membrane.add(membrane);
  const supportMaterial = standard("#f0eee5", { roughness: 0.78 });
  for (const offset of [-4.5, 0, 4.5]) {
    const barX = mesh(new THREE.BoxGeometry(17.4, 0.25, 0.75), supportMaterial, "membrane");
    barX.position.set(0, 68.82, offset);
    groups.membrane.add(barX);
    const barZ = mesh(new THREE.BoxGeometry(0.75, 0.25, 17.4), supportMaterial, "membrane");
    barZ.position.set(offset, 68.84, 0);
    groups.membrane.add(barZ);
  }
  const gasket = horizontalRing(9.3, 13.6, standard("#242a2e"), "membrane");
  gasket.position.y = 66.45;
  groups.membrane.add(gasket);

  // Passive diffusion head: clamp collar, drainage gap, coarse PP guard and end spokes.
  const headMaterial = standard("#d96735", { roughness: 0.72 });
  const collar = mesh(tubeGeometry(16.2, 18, 13), headMaterial, "head");
  collar.position.y = 61;
  groups.head.add(collar);
  const shoulder = horizontalRing(12, 17.95, headMaterial, "head");
  shoulder.position.y = 68.8;
  groups.head.add(shoulder);
  const topRing = mesh(tubeGeometry(12, 18, 4), headMaterial, "head");
  topRing.position.y = 92.5;
  groups.head.add(topRing);
  const strutMaterial = standard("#ca5b2f");
  for (let i = 0; i < 8; i += 1) {
    const angle = (i / 8) * Math.PI * 2;
    const strut = mesh(new THREE.BoxGeometry(3.1, 21, 2.5), strutMaterial, "head");
    strut.position.set(Math.cos(angle) * 16.6, 80.7, Math.sin(angle) * 16.6);
    strut.rotation.y = -angle;
    groups.head.add(strut);
  }
  const noseRing = horizontalRing(4.2, 17.9, headMaterial, "head");
  noseRing.position.y = 94.6;
  groups.head.add(noseRing);
  for (let i = 0; i < 6; i += 1) {
    const spoke = mesh(new THREE.BoxGeometry(28, 1.3, 2.0), strutMaterial, "head");
    spoke.position.y = 95.1;
    spoke.rotation.y = (i / 6) * Math.PI;
    groups.head.add(spoke);
  }

  // Cable-end cap with a simple water-blocked lead representation.
  const capMaterial = standard("#242a2e", { roughness: 0.7 });
  const plug = mesh(new THREE.CylinderGeometry(13.7, 13.7, 14, 72), capMaterial, "cap");
  plug.position.y = -57.5;
  groups.cap.add(plug);
  const flange = mesh(new THREE.CylinderGeometry(18, 18, 3.5, 72), capMaterial, "cap");
  flange.position.y = -66.25;
  groups.cap.add(flange);
  const cable = mesh(new THREE.CylinderGeometry(3.2, 3.2, 24, 36), standard("#111619"), "cap");
  cable.position.set(0, -80, 4.8);
  groups.cap.add(cable);
  [["#714126", -1.8], ["#e7e2d5", -0.6], ["#5a9b66", 0.6], ["#d6b947", 1.8]].forEach(([color, x]) => {
    const conductor = mesh(new THREE.CylinderGeometry(0.32, 0.32, 7, 12), standard(color as string), "cap");
    conductor.position.set(x as number, -49.5, 0);
    groups.cap.add(conductor);
  });

  return { groups, renderer, camera, controls, clippedMaterials };
}

export default function ProbeViewer() {
  const mountRef = useRef<HTMLDivElement>(null);
  const modelRef = useRef<ViewerModel | null>(null);
  const frameRef = useRef<number | null>(null);
  const [exploded, setExploded] = useState(false);
  const [cutaway, setCutaway] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const [activePart, setActivePart] = useState<PartKey>("probe");
  const [visible, setVisible] = useState<Record<PartKey, boolean>>({
    enclosure: true,
    probe: true,
    membrane: true,
    head: true,
    cap: true,
  });

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#e9edf0");
    scene.fog = new THREE.Fog("#e9edf0", 270, 520);

    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 1000);
    camera.position.set(150, 50, 185);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.055;
    controls.target.set(0, 5, 0);
    controls.minDistance = 100;
    controls.maxDistance = 430;
    controls.update();

    scene.add(new THREE.HemisphereLight("#f7fbff", "#64706d", 2.25));
    const key = new THREE.DirectionalLight("#fff7e8", 4.2);
    key.position.set(90, 150, 120);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    scene.add(key);
    const fill = new THREE.DirectionalLight("#9ec8da", 1.8);
    fill.position.set(-120, 20, -80);
    scene.add(fill);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(175, 96),
      new THREE.MeshStandardMaterial({ color: "#dce2e5", roughness: 0.96 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -97;
    floor.receiveShadow = true;
    scene.add(floor);
    const grid = new THREE.GridHelper(280, 28, "#aeb9bf", "#d0d7db");
    grid.position.y = -96.7;
    scene.add(grid);

    const model = createProbeModel(scene, renderer, camera, controls);
    modelRef.current = model;

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      renderer.setSize(rect.width, rect.height, false);
      camera.aspect = rect.width / Math.max(rect.height, 1);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    resize();

    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    const selectPart = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(Object.values(model.groups), true);
      const part = hits.find((hit) => hit.object.userData.part)?.object.userData.part as PartKey | undefined;
      if (part) setActivePart(part);
    };
    renderer.domElement.addEventListener("pointerdown", selectPart);

    const animate = () => {
      Object.values(model.groups).forEach((group) => {
        group.position.lerp(group.userData.target as THREE.Vector3, 0.085);
      });
      controls.update();
      renderer.render(scene, camera);
      frameRef.current = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", selectPart);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      controls.dispose();
      renderer.dispose();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => material.dispose());
        }
      });
      mount.removeChild(renderer.domElement);
      modelRef.current = null;
    };
  }, []);

  useEffect(() => {
    const model = modelRef.current;
    if (!model) return;
    const targets = exploded ? EXPLODED : ASSEMBLED;
    (Object.keys(targets) as PartKey[]).forEach((key) => {
      (model.groups[key].userData.target as THREE.Vector3).copy(targets[key]);
    });
  }, [exploded]);

  useEffect(() => {
    const model = modelRef.current;
    if (!model) return;
    (Object.keys(visible) as PartKey[]).forEach((key) => {
      model.groups[key].visible = visible[key];
    });
  }, [visible]);

  useEffect(() => {
    const model = modelRef.current;
    if (!model) return;
    model.controls.autoRotate = autoRotate;
    model.controls.autoRotateSpeed = 1.3;
  }, [autoRotate]);

  useEffect(() => {
    const model = modelRef.current;
    if (!model) return;
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
    model.renderer.localClippingEnabled = cutaway;
    model.clippedMaterials.forEach((material) => {
      const clipped = material as THREE.MeshStandardMaterial;
      clipped.clippingPlanes = cutaway ? [plane] : [];
      clipped.needsUpdate = true;
    });
  }, [cutaway]);

  const resetCamera = () => {
    const model = modelRef.current;
    if (!model) return;
    model.camera.position.set(150, 50, 185);
    model.controls.target.set(0, 5, 0);
    model.controls.update();
  };

  const togglePart = (key: PartKey) => {
    setVisible((current) => ({ ...current, [key]: !current[key] }));
  };

  const selected = PARTS.find((part) => part.key === activePart) ?? PARTS[1];

  return (
    <main className="viewer-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="project-mark">O₂</span>
          <div>
            <p className="eyebrow">O₂ probe · instrumentation</p>
            <h1>Compost probe <span>Rev-A</span></h1>
          </div>
        </div>
        <div className="status-chip"><i /> Provisional mechanical study</div>
      </header>

      <section className="stage">
        <div className="canvas-wrap" ref={mountRef} aria-label="Interactive 3D model of the oxygen probe" />
        <div className="canvas-note">
          <span>Drag to orbit</span>
          <b>·</b>
          <span>Scroll to zoom</span>
          <b>·</b>
          <span>Select a part</span>
        </div>

        <aside className="part-panel">
          <div className="panel-heading">
            <span>Assembly</span>
            <strong>5 parts</strong>
          </div>
          <div className="part-list">
            {PARTS.map((part, index) => (
              <button
                className={`part-row ${activePart === part.key ? "is-active" : ""} ${visible[part.key] ? "" : "is-hidden"}`}
                key={part.key}
                onClick={() => {
                  setActivePart(part.key);
                  if (!visible[part.key]) togglePart(part.key);
                }}
                type="button"
              >
                <span className="part-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="swatch" style={{ background: part.color }} />
                <span className="part-copy"><b>{part.label}</b><small>{part.detail}</small></span>
                <span
                  className="visibility-toggle"
                  role="checkbox"
                  aria-checked={visible[part.key]}
                  aria-label={`${visible[part.key] ? "Hide" : "Show"} ${part.label}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    togglePart(part.key);
                  }}
                >{visible[part.key] ? "●" : "○"}</span>
              </button>
            ))}
          </div>
          <div className="selected-card">
            <span>Selected component</span>
            <div><i style={{ background: selected.color }} /><strong>{selected.label}</strong></div>
            <p>{selected.detail}</p>
          </div>
        </aside>

        <div className="toolbar" role="toolbar" aria-label="3D view controls">
          <button className={exploded ? "is-on" : ""} onClick={() => setExploded((value) => !value)} type="button">
            <span className="tool-icon">↔</span>{exploded ? "Assemble" : "Explode"}
          </button>
          <button className={cutaway ? "is-on" : ""} onClick={() => setCutaway((value) => !value)} type="button">
            <span className="tool-icon">◐</span>Cutaway
          </button>
          <button className={autoRotate ? "is-on" : ""} onClick={() => setAutoRotate((value) => !value)} type="button">
            <span className="tool-icon">↻</span>Rotate
          </button>
          <button onClick={resetCamera} type="button"><span className="tool-icon">⌂</span>Reset</button>
        </div>

        <div className="dimension-card">
          <p>Controlled datums <span>mm</span></p>
          <dl>
            <div><dt>Tube</dt><dd>Ø32 × 129 <small>OD</small></dd></div>
            <div><dt>Board</dt><dd>20 × 119</dd></div>
            <div><dt>Cell</dt><dd>Ø14.4 × 8.3</dd></div>
            <div><dt>Pot line</dt><dd>82.0</dd></div>
          </dl>
          <p className="gate-note">Verify actual tube ID, component envelope, carrier and SGX port before fabrication.</p>
        </div>
      </section>

      <footer>
        <span>MODEL 01 / REV-A</span>
        <p>Parametric concept · enclosure dimensions not released for fabrication</p>
      </footer>
    </main>
  );
}
