// Escena isométrica del hero: estación de servicio, tanques de almacenamiento,
// torre de proceso, paneles solares y camiones cisterna circulando.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { gsap } from 'gsap';

const C = {
  platformTop: 0x1d3b47,
  platformSide: 0x112a33,
  grid: 0x3a6372,
  slab: 0x2a4b57,
  road: 0x0d171c,
  roadLine: 0xe9eadf,
  cream: 0xece3cf,
  creamDark: 0xd8ccb0,
  gold: 0xc9a15a,
  lime: 0xb5c425,
  limeBright: 0xd4e021,
  navy: 0x17384a,
  navyDark: 0x0f2531,
  steel: 0x8fa7b3,
  white: 0xf1f2ea,
  glass: 0x7fd0d4,
  tire: 0x161b1e,
  flame: 0xffa63d,
  leaf: 0x8fae2a,
};

const matCache = new Map();
function mat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!matCache.has(key)) {
    matCache.set(key, new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05, ...opts }));
  }
  return matCache.get(key);
}
function glow(color, intensity = 1.4) {
  return new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: intensity, roughness: 0.4 });
}

/** Caja apoyada en el suelo: (x, z) es el centro, y es la base. */
function box(w, h, d, material, x = 0, y = 0, z = 0, radius = 0.04) {
  const geo = radius > 0 ? new RoundedBoxGeometry(w, h, d, 2, Math.min(radius, w / 2, h / 2, d / 2)) : new THREE.BoxGeometry(w, h, d);
  const m = new THREE.Mesh(geo, material);
  m.position.set(x, y + h / 2, z);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}
function cyl(r, h, material, x = 0, y = 0, z = 0, seg = 28) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), material);
  m.position.set(x, y + h / 2, z);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

/* ------------------------------------------------------------------ */
/* Piezas                                                              */
/* ------------------------------------------------------------------ */

function makePlatform() {
  const g = new THREE.Group();
  const base = new THREE.Mesh(new RoundedBoxGeometry(15, 0.8, 11, 3, 0.18), [
    mat(C.platformSide), mat(C.platformSide), mat(C.platformTop), mat(C.platformSide), mat(C.platformSide), mat(C.platformSide),
  ]);
  base.position.y = -0.4;
  base.receiveShadow = true;
  g.add(base);

  // Rejilla
  const pts = [];
  for (let x = -7; x <= 7; x += 1) pts.push(x, 0.005, -5.5, x, 0.005, 3.3);
  for (let z = -5; z <= 3; z += 1) pts.push(-7.5, 0.005, z, 7.5, 0.005, z);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  g.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: C.grid, transparent: true, opacity: 0.45 })));
  return g;
}

function makeRoad() {
  const g = new THREE.Group();
  g.add(box(15, 0.06, 1.9, mat(C.road), 0, 0, 4.45, 0));
  g.add(box(15, 0.1, 0.12, mat(C.lime), 0, 0, 3.45, 0));
  for (let x = -7; x < 7.5; x += 1.25) g.add(box(0.6, 0.075, 0.08, mat(C.roadLine), x, 0, 4.45, 0));
  return g;
}

function makeStation() {
  const g = new THREE.Group();
  g.position.set(-3.7, 0, 0.9);
  g.add(box(4.8, 0.08, 3.4, mat(C.slab), 0, 0, 0, 0.02));

  // Pilares y techo
  for (const [px, pz] of [[-1.9, -1.2], [1.9, -1.2], [-1.9, 1.2], [1.9, 1.2]]) g.add(box(0.18, 1.75, 0.18, mat(C.white), px, 0.08, pz));
  g.add(box(4.9, 0.32, 3.3, mat(C.white), 0, 1.82, 0, 0.08));
  g.add(box(4.96, 0.12, 3.36, glow(C.lime, 0.55), 0, 1.86, 0, 0.03));

  // Surtidores
  const screens = [];
  for (const px of [-0.9, 0.9]) {
    g.add(box(0.55, 0.14, 1.5, mat(C.creamDark), px, 0.08, 0));
    for (const pz of [-0.35, 0.35]) {
      g.add(box(0.4, 0.95, 0.3, mat(C.navy), px, 0.22, pz));
      g.add(box(0.42, 0.1, 0.32, mat(C.lime), px, 1.17, pz, 0.02));
      const s = new THREE.Mesh(new THREE.PlaneGeometry(0.26, 0.2), glow(C.glass, 1.2).clone());
      s.position.set(px + 0.205, 0.85, pz);
      s.rotation.y = Math.PI / 2;
      g.add(s);
      screens.push(s);
    }
  }

  // Tienda
  const shop = new THREE.Group();
  shop.position.set(-0.2, 0, -2.75);
  shop.add(box(3.2, 1.25, 1.3, mat(C.cream), 0, 0, 0, 0.06));
  shop.add(box(3.25, 0.16, 1.35, mat(C.navy), 0, 1.25, 0, 0.03));
  const win = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 0.5), glow(C.glass, 0.7));
  win.position.set(0, 0.62, 0.66);
  shop.add(win);
  g.add(shop);

  // Tótem de precios
  const totem = new THREE.Group();
  totem.position.set(2.75, 0, 1.55);
  totem.add(box(0.14, 1.6, 0.14, mat(C.steel), 0, 0, 0));
  totem.add(box(0.8, 1.1, 0.16, mat(C.navy), 0, 1.4, 0, 0.05));
  const price = new THREE.Mesh(new THREE.PlaneGeometry(0.58, 0.55), glow(C.limeBright, 0.9));
  price.position.set(0, 1.85, 0.085);
  totem.add(price);
  const capDrop = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), mat(C.gold, { metalness: 0.6, roughness: 0.3 }));
  capDrop.position.set(0, 2.68, 0);
  totem.add(capDrop);
  g.add(totem);

  return { group: g, screens, anchor: new THREE.Vector3(-3.7, 2.4, 0.9) };
}

function makeTankFarm() {
  const g = new THREE.Group();
  g.position.set(4.1, 0, -2.6);

  // Muro de contención
  const wall = mat(C.slab);
  g.add(box(5.4, 0.08, 4.2, mat(0x24434f), 0, 0, 0, 0.02));
  g.add(box(5.4, 0.3, 0.12, wall, 0, 0, 2.05));
  g.add(box(5.4, 0.3, 0.12, wall, 0, 0, -2.05));
  g.add(box(0.12, 0.3, 4.2, wall, 2.65, 0, 0));
  g.add(box(0.12, 0.3, 4.2, wall, -2.65, 0, 0));

  const tanks = [];
  const spots = [[-1.3, 0.85, 2.3], [1.2, 0.85, 2.0], [-0.05, -1.05, 2.6]];
  spots.forEach(([x, z, h], i) => {
    const t = new THREE.Group();
    t.position.set(x, 0.08, z);
    t.add(cyl(0.88, h, mat(C.cream), 0, 0, 0, 40));
    const dome = new THREE.Mesh(new THREE.SphereGeometry(0.88, 40, 16, 0, Math.PI * 2, 0, Math.PI / 2), mat(i === 2 ? C.gold : C.navy, { metalness: i === 2 ? 0.5 : 0.1, roughness: 0.4 }));
    dome.scale.y = 0.32;
    dome.position.y = h;
    dome.castShadow = true;
    t.add(dome);
    for (const yy of [h * 0.3, h * 0.66]) t.add(cyl(0.9, 0.07, mat(C.navy), 0, yy, 0, 40));
    // indicador de nivel (franja lima)
    const level = box(0.06, h * 0.8, 0.14, glow(C.lime, 0.4), 0, h * 0.1, 0.89, 0);
    t.add(level);
    g.add(t);
    tanks.push(t);
  });
  return { group: g, tanks, anchor: new THREE.Vector3(4.1, 3.6, -3.6) };
}

function makeTower() {
  const g = new THREE.Group();
  g.position.set(6.2, 0, 1.5);
  g.add(box(1.1, 0.12, 1.1, mat(C.slab), 0, 0, 0, 0.03));
  g.add(cyl(0.24, 3.4, mat(C.steel, { metalness: 0.4, roughness: 0.45 }), 0, 0.1, 0, 20));
  for (const y of [1.1, 2.2]) g.add(cyl(0.45, 0.06, mat(C.navy), 0, y, 0, 20));
  g.add(cyl(0.3, 0.2, mat(C.navy), 0, 3.5, 0, 20));
  const flame = new THREE.Mesh(new THREE.ConeGeometry(0.17, 0.6, 14), glow(C.flame, 2.4));
  flame.position.y = 4.0;
  g.add(flame);
  const light = new THREE.PointLight(C.flame, 6, 5, 2);
  light.position.y = 4.1;
  g.add(light);
  return { group: g, flame, light, anchor: new THREE.Vector3(6.2, 4.7, 1.5) };
}

function makeSolar() {
  const g = new THREE.Group();
  g.position.set(-4.4, 0, -4.4);
  const panels = [];
  for (const x of [-1.8, 0, 1.8]) {
    const p = new THREE.Group();
    p.position.x = x;
    p.add(box(0.1, 0.55, 0.1, mat(C.steel), 0, 0, 0));
    const panel = new THREE.Group();
    panel.position.y = 0.6;
    panel.rotation.x = -0.55;
    panel.add(box(1.5, 0.06, 0.95, mat(C.navyDark, { metalness: 0.4, roughness: 0.25 }), 0, -0.03, 0, 0.02));
    const cells = new THREE.Mesh(new THREE.PlaneGeometry(1.36, 0.82, 4, 2), new THREE.MeshStandardMaterial({ color: 0x2f6f8a, emissive: 0x2f6f8a, emissiveIntensity: 0.25, metalness: 0.6, roughness: 0.2, wireframe: false }));
    cells.rotation.x = -Math.PI / 2;
    cells.position.y = 0.035;
    panel.add(cells);
    const lines = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.PlaneGeometry(1.36, 0.82, 4, 2)), new THREE.LineBasicMaterial({ color: 0x9ad3e0, transparent: true, opacity: 0.5 }));
    lines.rotation.x = -Math.PI / 2;
    lines.position.y = 0.04;
    panel.add(lines);
    p.add(panel);
    g.add(p);
    panels.push(cells);
  }
  return { group: g, panels, anchor: new THREE.Vector3(-4.4, 1.7, -4.4) };
}

function makeDrop() {
  const pts = [];
  const N = 40;
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    pts.push(new THREE.Vector2(0.62 * Math.sin(Math.PI * Math.pow(t, 0.72)), t * 1.55));
  }
  return new THREE.LatheGeometry(pts, 48);
}

function makeHub() {
  const g = new THREE.Group();
  g.position.set(0.4, 0, 0.9);
  g.add(box(1.9, 0.45, 1.9, mat(C.navy), 0, 0, 0, 0.12));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.05, 10, 48), glow(C.lime, 1.6));
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.48;
  g.add(ring);
  const pulse = new THREE.Mesh(new THREE.RingGeometry(0.6, 0.68, 48), new THREE.MeshBasicMaterial({ color: C.limeBright, transparent: true, opacity: 0.7, side: THREE.DoubleSide }));
  pulse.rotation.x = -Math.PI / 2;
  pulse.position.y = 0.47;
  g.add(pulse);

  const drop = new THREE.Mesh(makeDrop(), new THREE.MeshStandardMaterial({ color: C.gold, metalness: 0.75, roughness: 0.25, emissive: 0x5a3d0f, emissiveIntensity: 0.35 }));
  drop.castShadow = true;
  const dropPivot = new THREE.Group();
  dropPivot.position.y = 1.1;
  dropPivot.add(drop);
  g.add(dropPivot);

  // haz de luz vertical
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.6, 6), new THREE.MeshBasicMaterial({ color: C.limeBright, transparent: true, opacity: 0.6 }));
  beam.position.y = 0.78;
  g.add(beam);
  return { group: g, drop: dropPivot, pulse, anchor: new THREE.Vector3(0.4, 3.0, 0.9) };
}

function makeTruck({ tankColor = C.cream, cabColor = C.navy, stripe = C.lime } = {}) {
  const g = new THREE.Group();
  const body = new THREE.Group();
  g.add(body);
  body.add(box(3.1, 0.16, 0.78, mat(C.navyDark), 0, 0.28, 0, 0.03));
  // cabina
  body.add(box(0.95, 0.9, 0.86, mat(cabColor), 1.05, 0.38, 0, 0.12));
  const wind = box(0.05, 0.36, 0.7, glow(C.glass, 0.5), 1.53, 0.82, 0, 0);
  body.add(wind);
  for (const z of [-0.27, 0.27]) body.add(box(0.04, 0.1, 0.14, glow(0xfff3c4, 2.2), 1.53, 0.48, z, 0));
  // cisterna
  const tank = new THREE.Mesh(new THREE.CapsuleGeometry(0.43, 1.6, 8, 24), mat(tankColor, { roughness: 0.45, metalness: 0.15 }));
  tank.rotation.z = Math.PI / 2;
  tank.position.set(-0.45, 0.9, 0);
  tank.castShadow = true;
  body.add(tank);
  for (const z of [-0.435, 0.435]) body.add(box(1.7, 0.09, 0.01, mat(stripe), -0.45, 0.82, z, 0));
  body.add(box(0.3, 0.08, 0.3, mat(C.gold), -0.45, 1.3, 0, 0.03));

  const wheels = [];
  for (const x of [1.05, -0.4, -1.0]) {
    for (const z of [-0.41, 0.41]) {
      const pivot = new THREE.Group();
      pivot.position.set(x, 0.21, z);
      const w = new THREE.Mesh(new THREE.CylinderGeometry(0.21, 0.21, 0.14, 18), mat(C.tire));
      w.rotation.x = Math.PI / 2;
      w.castShadow = true;
      pivot.add(w);
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.15, 6), mat(C.steel));
      hub.rotation.x = Math.PI / 2;
      pivot.add(hub);
      g.add(pivot);
      wheels.push(pivot);
    }
  }
  return { group: g, body, wheels };
}

function makeTree(scale = 1) {
  const g = new THREE.Group();
  g.add(cyl(0.07 * scale, 0.4 * scale, mat(0x6b5236), 0, 0, 0, 8));
  const crown = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42 * scale, 0), mat(C.leaf, { flatShading: true }));
  crown.position.y = 0.65 * scale;
  crown.castShadow = true;
  g.add(crown);
  return g;
}

function makeBarrels() {
  const g = new THREE.Group();
  g.position.set(2.3, 0, 2.4);
  g.add(box(1.5, 0.1, 1.0, mat(0x6b5236), 0, 0, 0, 0.02));
  const colors = [C.navy, C.lime, C.navy, C.gold, C.navy, C.lime];
  let i = 0;
  for (const x of [-0.45, 0, 0.45]) for (const z of [-0.22, 0.22]) {
    const b = cyl(0.19, 0.5, mat(colors[i++ % colors.length]), x, 0.1, z, 16);
    g.add(b);
  }
  return g;
}

function makePipe(points, radius = 0.08) {
  const path = new THREE.CurvePath();
  for (let i = 0; i < points.length - 1; i++) path.add(new THREE.LineCurve3(points[i], points[i + 1]));
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(path, 80, radius, 10, false), mat(C.steel, { metalness: 0.35, roughness: 0.4 }));
  mesh.castShadow = true;
  const packets = [];
  for (let i = 0; i < 3; i++) {
    const p = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.5, 12, 10), glow(C.limeBright, 2));
    packets.push(p);
  }
  return { mesh, path, packets, offset: Math.random() };
}

/* ------------------------------------------------------------------ */
/* Escena                                                              */
/* ------------------------------------------------------------------ */

export function createHeroScene(container, { labelsEl, reducedMotion = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);
  camera.position.set(20, 16.5, 20);
  camera.lookAt(0, -0.3, 0);

  scene.add(new THREE.HemisphereLight(0xe3f1ea, 0x0a1a20, 1.25));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
  sun.position.set(9, 16, 6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 50 });
  sun.shadow.bias = -0.0005;
  sun.shadow.radius = 4;
  scene.add(sun);

  const stage = new THREE.Group(); // recibe scroll
  const world = new THREE.Group(); // recibe parallax
  stage.add(world);
  scene.add(stage);

  const platform = makePlatform();
  const road = makeRoad();
  const station = makeStation();
  const farm = makeTankFarm();
  const tower = makeTower();
  const solar = makeSolar();
  const hub = makeHub();
  const barrels = makeBarrels();

  const trees = new THREE.Group();
  for (const [x, z, s] of [[-0.9, -4.6, 1], [0.3, -4.1, 0.8], [-1.5, -3.4, 0.7], [7.0, -4.9, 0.9], [-6.9, 2.7, 0.8], [-6.7, -1.6, 1.1], [1.4, -1.6, 0.6], [6.9, -0.6, 0.7]]) {
    const t = makeTree(s);
    t.position.set(x, 0, z);
    trees.add(t);
  }

  const pipes = [
    makePipe([new THREE.Vector3(1.4, 0.3, -2.2), new THREE.Vector3(0.4, 0.3, -2.2), new THREE.Vector3(0.4, 0.3, -0.1)]),
    makePipe([new THREE.Vector3(-0.6, 0.3, 1.3), new THREE.Vector3(-2.2, 0.3, 1.3)]),
    makePipe([new THREE.Vector3(5.6, 0.3, -0.5), new THREE.Vector3(5.6, 0.3, 1.5), new THREE.Vector3(5.85, 0.3, 1.5)]),
  ];
  const pipeGroup = new THREE.Group();
  pipes.forEach((p) => { pipeGroup.add(p.mesh); p.packets.forEach((k) => pipeGroup.add(k)); });

  const truckA = makeTruck();
  truckA.group.position.set(-3, 0.03, 4.0);
  const truckB = makeTruck({ tankColor: C.gold, cabColor: C.lime, stripe: C.navy });
  truckB.group.position.set(4, 0.03, 4.95);
  truckB.group.rotation.y = Math.PI;
  truckB.group.scale.setScalar(0.85);

  world.add(platform, road, station.group, farm.group, tower.group, solar.group, hub.group, barrels, trees, pipeGroup, truckA.group, truckB.group);

  // centra la composición
  world.position.set(0, 0, -0.2);
  stage.visible = reducedMotion; // se muestra al arrancar la intro

  /* -------- etiquetas HTML proyectadas -------- */
  const labelDefs = [
    { text: 'Estaciones de servicio', anchor: station.anchor },
    { text: 'Almacenamiento', anchor: farm.anchor },
    { text: 'Distribución a granel', anchor: null, follow: truckA.group, offset: new THREE.Vector3(0, 1.9, 0) },
    { text: 'Energía limpia', anchor: solar.anchor },
    { text: 'Control 24/7', anchor: hub.anchor },
  ];
  const labels = labelDefs.map((d) => {
    const el = document.createElement('div');
    el.className = 'scene-label';
    el.innerHTML = `<span class="scene-label__dot"></span><span>${d.text}</span>`;
    labelsEl?.appendChild(el);
    return { ...d, el, v: new THREE.Vector3() };
  });

  /* -------- tamaño -------- */
  let width = 1, height = 1;
  function resize() {
    width = container.clientWidth || 1;
    height = container.clientHeight || 1;
    renderer.setSize(width, height);
    const aspect = width / height;
    const f = 15.5 * Math.max(1, 1.25 / aspect);
    camera.left = (-f * aspect) / 2;
    camera.right = (f * aspect) / 2;
    camera.top = f / 2;
    camera.bottom = -f / 2;
    camera.updateProjectionMatrix();
  }
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(container);

  /* -------- parallax -------- */
  const pointer = { x: 0, y: 0 };
  const onPointer = (e) => {
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
  };
  window.addEventListener('pointermove', onPointer, { passive: true });

  /* -------- bucle -------- */
  const clock = new THREE.Clock();
  let running = true;
  let visible = true;
  let labelsOn = false;
  let elapsed = 0;
  const trucksIn = { v: 0 }; // los camiones aparecen al terminar la intro

  function moveTruck(t, dt, speed, dir, laneZ) {
    const g = t.group;
    g.position.x += speed * dt * dir;
    if (dir > 0 && g.position.x > 9) g.position.x = -9;
    if (dir < 0 && g.position.x < -9) g.position.x = 9;
    const edge = THREE.MathUtils.clamp((7.6 - Math.abs(g.position.x)) / 1.2, 0, 1);
    const base = (t === truckB ? 0.85 : 1) * trucksIn.v;
    g.scale.setScalar(base * THREE.MathUtils.smoothstep(edge, 0, 1) + 0.0001);
    g.position.z = laneZ;
    t.body.position.y = Math.sin(elapsed * 18 + laneZ) * 0.012;
    t.wheels.forEach((w) => (w.rotation.z -= (speed * dt) / 0.21));
  }

  function tick() {
    if (!running) return;
    requestAnimationFrame(tick);
    if (!visible) { clock.getDelta(); return; }
    const dt = Math.min(clock.getDelta(), 0.05) * (reducedMotion ? 0.35 : 1);
    elapsed += dt;

    world.rotation.y += ((pointer.x * 0.12) - world.rotation.y) * 0.04;
    world.rotation.x += ((pointer.y * 0.035) - world.rotation.x) * 0.04;

    moveTruck(truckA, dt, 1.6, 1, 4.0);
    moveTruck(truckB, dt, 2.1, -1, 4.95);

    hub.drop.rotation.y += dt * 0.8;
    hub.drop.position.y = 1.1 + Math.sin(elapsed * 1.6) * 0.12;
    const pp = (elapsed * 0.6) % 1;
    hub.pulse.scale.setScalar(1 + pp * 1.6);
    hub.pulse.material.opacity = 0.7 * (1 - pp);

    tower.flame.scale.set(1 + Math.sin(elapsed * 23) * 0.08, 1 + Math.sin(elapsed * 17) * 0.18, 1 + Math.cos(elapsed * 21) * 0.08);
    tower.light.intensity = 5 + Math.sin(elapsed * 19) * 1.2;

    station.screens.forEach((s, i) => (s.material.emissiveIntensity = 0.8 + Math.max(0, Math.sin(elapsed * 2 + i * 1.3)) * 0.9));
    solar.panels.forEach((p, i) => (p.material.emissiveIntensity = 0.2 + (Math.sin(elapsed * 1.4 - i * 0.7) * 0.5 + 0.5) * 0.35));

    pipes.forEach((p) => p.packets.forEach((k, i) => {
      const u = (elapsed * 0.25 + p.offset + i / p.packets.length) % 1;
      p.path.getPointAt(u, k.position);
    }));

    renderer.render(scene, camera);

    if (labelsOn) {
      for (const l of labels) {
        if (l.follow) l.v.copy(l.offset).applyMatrix4(l.follow.matrixWorld);
        else l.v.copy(l.anchor).applyMatrix4(world.matrixWorld);
        l.v.project(camera);
        const x = (l.v.x * 0.5 + 0.5) * width;
        const y = (-l.v.y * 0.5 + 0.5) * height;
        const hidden = Boolean(l.follow) && Math.abs(l.follow.position.x) > 6;
        l.el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
        l.el.classList.toggle('is-hidden', hidden);
      }
    }
  }

  const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { threshold: 0 });
  io.observe(container);
  tick();

  /* -------- intro con GSAP -------- */
  function intro() {
    const pieces = [road, station.group, hub.group, farm.group, pipeGroup, tower.group, solar.group, barrels, trees, truckA.group, truckB.group];
    if (reducedMotion) {
      trucksIn.v = 1;
      labelsOn = true;
      labels.forEach((l) => l.el.classList.add('is-visible'));
      return gsap.timeline();
    }
    stage.visible = true;
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    tl.from(platform.position, { y: -3, duration: 1.2 }, 0)
      .from(platform.scale, { x: 0.6, y: 0.6, z: 0.6, duration: 1.2, ease: 'back.out(1.4)' }, 0)
      .from(stage.rotation, { y: -0.9, duration: 1.8, ease: 'power2.out' }, 0);
    pieces.forEach((p, i) => {
      if (p === truckA.group || p === truckB.group) return; // los camiones aparecen por su borde
      const y0 = p.position.y;
      tl.fromTo(p.position, { y: y0 + 5 }, { y: y0, duration: 0.9, ease: 'bounce.out' }, 0.45 + i * 0.09);
      tl.from(p.scale, { x: 0.01, y: 0.01, z: 0.01, duration: 0.7, ease: 'back.out(1.7)' }, 0.45 + i * 0.09);
    });
    tl.to(trucksIn, { v: 1, duration: 0.8, ease: 'back.out(2)' }, '-=0.5');
    tl.add(() => {
      labelsOn = true;
      labels.forEach((l, i) => setTimeout(() => l.el.classList.add('is-visible'), i * 120));
    }, '-=0.3');
    return tl;
  }

  /* -------- scroll -------- */
  function setScrollProgress(p) {
    stage.rotation.y = p * 0.7;
    stage.position.y = -p * 2.2;
    const s = 1 - p * 0.18;
    stage.scale.setScalar(s);
    if (labelsEl) labelsEl.style.opacity = String(1 - Math.min(1, p * 2.2));
  }

  function dispose() {
    running = false;
    ro.disconnect();
    io.disconnect();
    window.removeEventListener('pointermove', onPointer);
    renderer.dispose();
  }

  return { intro, setScrollProgress, dispose };
}
