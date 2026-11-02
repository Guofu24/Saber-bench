import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { TEAM_ORDER, TEAM_ZONES, DEFAULT_TEAM_SEATS, MAX_TEAM_SEATS, teamSeat } from './office-layout.js';

// ================= renderer / camera =================
const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
stage.appendChild(renderer.domElement);
const labelR = new CSS2DRenderer();
labelR.domElement.className = 'labels';
stage.appendChild(labelR.domElement);

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 600);
camera.position.set(38, 36, 44);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.8, -1);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.minZoom = 0.65; controls.maxZoom = 4.5;
controls.minPolarAngle = 0.7; controls.maxPolarAngle = 1.22;
controls.minAzimuthAngle = Math.PI / 4 - 0.75; controls.maxAzimuthAngle = Math.PI / 4 + 0.75;
controls.update();

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.6, 0.55, 0.88);
composer.addPass(bloom);
composer.addPass(new OutputPass());

function layout() {
  const W = innerWidth, H = innerHeight, mobile = W < 900;
  let fx = 0, fw = W, fy = 0, fh = H;
  if (mobile) { fh = H * 0.58; } else { fx = 288; fw = W - 288 - 348; }
  const V = Math.max(20.4 * H / fh, 26.8 * H / fw);
  const asp = W / H;
  camera.left = -V * asp; camera.right = V * asp; camera.top = V; camera.bottom = -V;
  camera.setViewOffset(W, H, -(fx + fw / 2 - W / 2), -(fy + fh / 2 - H / 2), W, H);
  camera.updateProjectionMatrix();
  renderer.setSize(W, H); labelR.setSize(W, H); composer.setSize(W, H);
}
addEventListener('resize', layout);

function focusOffice(team = 'all') {
  const zone = TEAM_ZONES[team];
  const target = new THREE.Vector3(zone ? zone.x : 0, 0.8, zone ? -7 : -1);
  const delta = target.clone().sub(controls.target);
  camera.position.add(delta); controls.target.copy(target);
  camera.zoom = zone ? 2.45 : 1; camera.updateProjectionMatrix(); controls.update();
  document.querySelectorAll('[data-office-focus]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.officeFocus === team));
  });
}
document.querySelectorAll('[data-office-focus]').forEach(button => {
  button.addEventListener('click', () => focusOffice(button.dataset.officeFocus));
});

// ================= helpers =================
const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.6, metalness: 0.1, ...o });
const glowMat = (hex, k = 2.2) => new THREE.MeshBasicMaterial({ color: new THREE.Color(hex).multiplyScalar(k) });
function add(parent, obj, x = 0, y = 0, z = 0, shadow = true) {
  obj.position.set(x, y, z);
  obj.traverse(o => { if (o.isMesh) { o.castShadow = shadow; o.receiveShadow = true; } });
  parent.add(obj); return obj;
}
const box = (w, h, d, m) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
const cyl = (rt, rb, h, m, s = 24) => new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, s), m);
const cap = (r, l, m) => new THREE.Mesh(new THREE.CapsuleGeometry(r, l, 4, 12), m);
const sph = (r, m, a = 20, b = 14) => new THREE.Mesh(new THREE.SphereGeometry(r, a, b), m);
function canvasTex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  t.userData = { c, g }; return t;
}
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = a => a[Math.floor(Math.random() * a.length)];
const wait = ms => new Promise(r => setTimeout(r, ms));
function lerpAngle(a, b, k) { let d = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI; return a + d * k; }
function label(html, cls, parent, y, x = 0, z = 0) {
  const el = document.createElement('div'); el.className = cls; el.innerHTML = html;
  const o = new CSS2DObject(el); o.position.set(x, y, z); parent.add(o); return o;
}

// ================= background =================
scene.background = canvasTex(4, 512, (g, w, h) => {
  const gr = g.createLinearGradient(0, 0, 0, h);
  gr.addColorStop(0, '#03050f'); gr.addColorStop(0.45, '#081236'); gr.addColorStop(0.8, '#11286e'); gr.addColorStop(1, '#1b3d96');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
const glowTex = canvasTex(128, 128, (g) => {
  const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,255,255,.55)'); r.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = r; g.fillRect(0, 0, 128, 128);
});
const camDir = camera.position.clone().normalize();
const starSets = [];
for (let s = 0; s < 2; s++) {
  const pts = [];
  while (pts.length < 900 * 3) {
    const v = new THREE.Vector3(rnd(-1, 1), rnd(-0.6, 1), rnd(-1, 1)).normalize();
    if (v.dot(camDir) < -0.15) pts.push(v.x * 180, v.y * 180, v.z * 180);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const p = new THREE.Points(g, new THREE.PointsMaterial({ color: s ? '#cfe0ff' : '#ffffff', size: s ? 1.3 : 2, sizeAttenuation: false, transparent: true, depthWrite: false }));
  scene.add(p); starSets.push(p);
}
// city skyline behind the walls
const winTex = canvasTex(64, 256, (g, w, h) => {
  g.fillStyle = '#060b20'; g.fillRect(0, 0, w, h);
  for (let y = 4; y < h; y += 9) for (let x = 4; x < w - 4; x += 8)
    if (Math.random() < 0.32) { g.fillStyle = pick(['#ffd88a', '#ffe9b8', '#9fd0ff', '#ffc46b']); g.fillRect(x, y, 4, 5); }
});
winTex.wrapS = winTex.wrapT = THREE.RepeatWrapping;
// soft blue clouds under the platform
for (const [x, y, z, s] of [[6, -8, 10, 18], [-8, -9, 7, 16], [11, -10, -3, 15], [1, -12, 15, 20], [-3, -11, -10, 14]]) {
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: '#4f86ff', transparent: true, opacity: 0.45, depthWrite: false, blending: THREE.AdditiveBlending }));
  sp.position.set(x, y, z); sp.scale.set(s, s * 0.5, 1); scene.add(sp);
}

// ================= lights =================
scene.add(new THREE.HemisphereLight('#a9bcff', '#1c2238', 1.15));
const sun = new THREE.DirectionalLight('#fff1dc', 2.1);
sun.position.set(16, 30, 18); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -28, right: 28, top: 28, bottom: -28, near: 1, far: 90 });
sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
scene.add(sun);
const fill = new THREE.DirectionalLight('#6f8cff', 0.6); fill.position.set(-10, 8, -4); scene.add(fill);

// ================= platform / walls =================
const N = 36, HALF = 18;
add(scene, box(N + 0.6, 0.9, N + 0.6, mat('#121830', { roughness: 0.8 })), 0, -0.45, 0);
{
  const tiles = new THREE.InstancedMesh(new THREE.BoxGeometry(0.965, 0.06, 0.965), mat('#ffffff', { roughness: 0.5, metalness: 0.2 }), N * N);
  const d = new THREE.Object3D(), c = new THREE.Color(); let k = 0;
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    d.position.set(-HALF + 0.5 + i, 0.03, -HALF + 0.5 + j); d.updateMatrix(); tiles.setMatrixAt(k, d.matrix);
    c.set('#3a4258').offsetHSL(0, 0, rnd(-0.015, 0.015)); tiles.setColorAt(k++, c);
  }
  tiles.receiveShadow = true; scene.add(tiles);
}
const gold = glowMat('#ffc94a', 2.4), goldDim = glowMat('#ffc94a', 1.3);
for (let i = -HALF + 0.5; i < HALF; i += 1) {
  add(scene, box(0.45, 0.05, 0.07, gold), i, 0.0, HALF + 0.32, false);
  add(scene, box(0.07, 0.05, 0.45, gold), HALF + 0.32, 0.0, i, false);
}
const cityWall = canvasTex(1024, 256, (g, w, h) => {
  g.fillStyle = '#050a1c'; g.fillRect(0, 0, w, h);
  let x = 0; while (x < w) {
    const bw = rnd(30, 80), bh = rnd(80, 240); g.fillStyle = '#0a1230'; g.fillRect(x, h - bh, bw, bh);
    for (let y = h - bh + 6; y < h - 4; y += 9) for (let xx = x + 4; xx < x + bw - 5; xx += 8)
      if (Math.random() < 0.28) { g.fillStyle = pick(['#ffd27a', '#fff0c4', '#8fc8ff']); g.fillRect(xx, y, 3, 4); }
    x += bw + 3;
  }
});
const wallMat = mat('#0b1128', { roughness: 0.25, metalness: 0.4, emissive: '#ffffff', emissiveMap: cityWall, emissiveIntensity: 0.55 });
add(scene, box(N + 0.6, 5.2, 0.15, wallMat), 0, 2.6, -HALF - 0.37);
const wallMat2 = wallMat.clone(); wallMat2.emissiveMap = cityWall.clone(); wallMat2.emissiveMap.needsUpdate = true; wallMat2.emissiveMap.offset.x = 0.4;
add(scene, box(0.15, 5.2, N + 0.6, wallMat2), -HALF - 0.37, 2.6, 0);
add(scene, box(N + 0.6, 0.06, 0.06, gold), 0, 5.22, -HALF - 0.3, false);
add(scene, box(0.06, 0.06, N + 0.6, gold), -HALF - 0.3, 5.22, 0, false);
add(scene, box(0.06, 5.2, 0.06, gold), -HALF - 0.3, 2.6, -HALF - 0.3, false);

function carpet(x0, z0, x1, z1, color = '#14797e', trim = '#ffc94a') {
  const w = x1 - x0, d = z1 - z0, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  const edge = glowMat(trim, 1.25);
  add(scene, box(w, 0.03, d, mat(color, { roughness: 0.95 })), cx, 0.075, cz, false);
  add(scene, box(w, 0.025, 0.05, edge), cx, 0.09, z0, false);
  add(scene, box(w, 0.025, 0.05, edge), cx, 0.09, z1, false);
  add(scene, box(0.05, 0.025, d, edge), x0, 0.09, cz, false);
  add(scene, box(0.05, 0.025, d, edge), x1, 0.09, cz, false);
}
for (const zone of Object.values(TEAM_ZONES)) {
  carpet(zone.x - 5, -16.2, zone.x + 5, 0.6, zone.floor, zone.color);
  // Low partitions keep sightlines open while making the three wings distinct.
  const frame = mat('#26334a', { metalness: 0.5 });
  const glass = mat(zone.color, { transparent: true, opacity: 0.12, roughness: 0.15, depthWrite: false });
  for (const x of [zone.x - 5, zone.x + 5]) {
    add(scene, box(0.07, 0.65, 16.6, glass), x, 0.48, -7.8, false);
    add(scene, box(0.1, 0.06, 16.6, frame), x, 0.83, -7.8, false);
  }
  // Storage and equipment along the back; seats expand towards this wall.
  for (const offset of [-3.3, -1.1, 1.1, 3.3]) {
    add(scene, box(1.65, 1.05, 0.65, mat('#1a2335')), zone.x + offset, 0.6, -17.05);
    add(scene, box(1.5, 0.025, 0.03, glowMat(zone.color, 1.2)), zone.x + offset, 1.05, -16.71, false);
  }
}
carpet(-15, 6.8, -8, 12.5, '#173a3d', '#57dfc4');
carpet(-3, 5, 5, 11, '#24243c', '#ffc94a');
// Shared corridor in front of all three wings.
add(scene, box(32, 0.02, 0.045, glowMat('#799abb', 0.8)), 0, 0.08, 2.6, false);

// ================= furniture =================
const codeTex = canvasTex(256, 512, (g, w, h) => {
  g.fillStyle = '#06101f'; g.fillRect(0, 0, w, h);
  for (let y = 6; y < h; y += 13) {
    let x = 8 + Math.floor(rnd(0, 4)) * 14;
    const n = Math.floor(rnd(1, 5));
    for (let i = 0; i < n; i++) { const ww = rnd(14, 60); g.fillStyle = pick(['#7ee7ff', '#ffd36b', '#ff8cc0', '#8ef29b', '#b9c2ff', '#5f6a99']); g.fillRect(x, y, ww, 6); x += ww + 8; if (x > w - 20) break; }
  }
});
codeTex.wrapS = codeTex.wrapT = THREE.RepeatWrapping; codeTex.repeat.set(1, 0.42);
const deskTop = mat('#222839', { roughness: 0.35, metalness: 0.35 }), deskSide = mat('#161b29', { roughness: 0.5 });
const chairM = mat('#2b3042', { roughness: 0.6 }), metal = mat('#7c859c', { roughness: 0.3, metalness: 0.8 });
function makeDesk(x, z, w = 1.5, accent = '#ffd36b') {
  const g = new THREE.Group(); g.position.set(x, 0, z); scene.add(g);
  add(g, box(w, 0.07, 0.75, deskTop), 0, 0.74, 0);
  add(g, box(w - 0.12, 0.025, 0.025, glowMat(accent, 1.2)), 0, 0.755, 0.38, false);
  add(g, box(0.06, 0.72, 0.68, deskSide), -w / 2 + 0.05, 0.36, 0);
  add(g, box(0.06, 0.72, 0.68, deskSide), w / 2 - 0.05, 0.36, 0);
  add(g, box(w - 0.1, 0.35, 0.04, deskSide), 0, 0.5, -0.3);
  add(g, cyl(0.03, 0.05, 0.22, metal, 10), 0, 0.88, -0.2);
  add(g, box(0.84, 0.5, 0.045, mat('#0d111d', { roughness: 0.3, metalness: 0.5 })), 0, 1.12, -0.22);
  const tex = codeTex.clone(); tex.needsUpdate = true; tex.offset.y = Math.random();
  const scr = new THREE.MeshBasicMaterial({ map: tex, color: new THREE.Color(0.28, 0.28, 0.28) });
  add(g, new THREE.Mesh(new THREE.PlaneGeometry(0.78, 0.44), scr), 0, 1.12, -0.196, false);
  add(g, box(0.5, 0.02, 0.15, mat('#394058')), 0, 0.785, 0.05);
  add(g, box(0.09, 0.03, 0.12, mat('#394058')), 0.38, 0.785, 0.07);
  if (Math.random() < 0.5) add(g, cyl(0.045, 0.04, 0.1, mat(pick(['#ff8a5c', '#5cc8ff', '#f2f2f2'])), 12), -w / 2 + 0.22, 0.83, -0.1);
  // chair
  const ch = new THREE.Group(); ch.position.set(0, 0, 0.78); g.add(ch);
  add(ch, box(0.52, 0.08, 0.5, chairM), 0, 0.45, 0);
  add(ch, box(0.5, 0.56, 0.07, chairM), 0, 0.78, 0.25);
  add(ch, cyl(0.035, 0.035, 0.38, metal, 8), 0, 0.22, 0);
  add(ch, cyl(0.25, 0.25, 0.03, metal, 5), 0, 0.03, 0);
  return { g, scr, tex, on: false };
}
function plant(x, z, s = 1) {
  const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(s); scene.add(g);
  add(g, cyl(0.2, 0.15, 0.36, mat('#e9edf5', { roughness: 0.4 })), 0, 0.18, 0);
  add(g, cyl(0.18, 0.18, 0.02, mat('#3a2a1c')), 0, 0.36, 0);
  const leaf = mat('#2fa865', { roughness: 0.6 });
  for (let i = 0; i < 9; i++) {
    const l = new THREE.Mesh(new THREE.ConeGeometry(0.05, rnd(0.55, 0.9), 5), leaf);
    const a = (i / 9) * Math.PI * 2, t = rnd(0.25, 0.6);
    l.position.set(Math.cos(a) * 0.08, 0.6, Math.sin(a) * 0.08); l.rotation.set(Math.sin(a) * t, 0, -Math.cos(a) * t);
    l.castShadow = true; g.add(l);
  }
}
[[-16.5, 1.5], [-5.5, 1.5], [5.5, 1.5], [16.5, 1.5], [-16.5, 15.5], [16.5, 15.5], [-7, 8], [7, 8]].forEach(([x, z]) => plant(x, z, 1.3));
// lounge: L sofa
{
  const lounge = new THREE.Group(); lounge.position.set(-5, 0, 5); scene.add(lounge);
  const W = mat('#eef1f7', { roughness: 0.7 }), cush = mat('#59d1c8', { roughness: 0.8 });
  add(lounge, box(3.0, 0.4, 0.85, W), -6.1, 0.22, 3.15);
  add(lounge, box(3.0, 0.62, 0.22, W), -6.1, 0.55, 2.65);
  add(lounge, box(0.22, 0.55, 0.85, W), -4.5, 0.32, 3.15);
  add(lounge, box(0.85, 0.4, 2.6, W), -8.0, 0.22, 4.3);
  add(lounge, box(0.22, 0.62, 3.45, W), -8.5, 0.55, 3.9);
  add(lounge, box(0.45, 0.3, 0.12, cush), -7.3, 0.6, 2.82).rotation.x = -0.2;
  add(lounge, box(0.45, 0.3, 0.12, cush), -5.0, 0.6, 2.82).rotation.x = -0.2;
  add(lounge, box(0.12, 0.3, 0.45, cush), -8.32, 0.6, 5.0).rotation.z = 0.2;
  add(lounge, box(1.3, 0.06, 0.75, mat('#1c2133', { roughness: 0.3, metalness: 0.4 })), -6.2, 0.4, 5.0);
  add(lounge, box(1.1, 0.37, 0.55, mat('#151a29')), -6.2, 0.19, 5.0);
  add(lounge, cyl(0.06, 0.05, 0.12, mat('#ffffff')), -6.0, 0.49, 4.9);
  add(lounge, sph(0.1, glowMat('#ffd27a', 1.6)), -6.5, 0.5, 5.1);
}
// reception desk with lamps
{
  add(scene, box(3.0, 0.85, 0.65, mat('#1b2031', { roughness: 0.35, metalness: 0.4 })), -0.6, 0.43, 14.0);
  add(scene, box(3.05, 0.05, 0.7, mat('#2c3349', { roughness: 0.3, metalness: 0.5 })), -0.6, 0.88, 14.0);
  add(scene, box(2.9, 0.04, 0.02, gold), -0.6, 0.6, 14.34, false);
  for (const x of [-1.8, 0.6]) {
    add(scene, cyl(0.03, 0.08, 0.45, metal, 10), x, 1.12, 14.0);
    add(scene, sph(0.15, glowMat('#ffd27a', 2.6)), x, 1.42, 14.0, false);
    const L = new THREE.PointLight('#ffc879', 6, 4, 1.8); L.position.set(x, 1.5, 14.2); scene.add(L);
  }
}
// bookshelf
{
  const g = new THREE.Group(); g.position.set(9.0, 0, 10); scene.add(g);
  const fr = mat('#1a1f30', { roughness: 0.5 });
  add(g, box(1.9, 2.6, 0.08, fr), 0, 1.3, -0.18);
  add(g, box(0.07, 2.6, 0.42, fr), -0.92, 1.3, 0); add(g, box(0.07, 2.6, 0.42, fr), 0.92, 1.3, 0);
  for (let s = 0; s < 5; s++) {
    add(g, box(1.85, 0.05, 0.42, fr), 0, 0.05 + s * 0.62, 0);
    if (s === 4) break;
    let x = -0.82; while (x < 0.78) { const w = rnd(0.07, 0.13), h = rnd(0.32, 0.5);
      add(g, box(w, h, 0.3, mat(pick(['#e86a5a', '#f2c14e', '#4fb3d9', '#8ad17b', '#c98bd8', '#e8e1d0', '#3d6fd1']), { roughness: 0.7 })), x + w / 2, 0.08 + s * 0.62 + h / 2, 0.02); x += w + 0.015; }
  }
}
// wall boards with live canvases
const boards = [];
function board(x, y, z, rotY, w, h, draw) {
  const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = rotY; scene.add(g);
  add(g, box(w + 0.12, h + 0.12, 0.06, mat('#0c1020', { roughness: 0.3, metalness: 0.6 })), 0, 0, 0, false);
  const t = canvasTex(Math.round(w * 160), Math.round(h * 160), () => {});
  add(g, new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t, color: new THREE.Color(1.25, 1.25, 1.25) })), 0, 0, 0.035, false);
  const b = { t, draw }; boards.push(b); return b;
}

// ================= core =================
const CORE = new THREE.Vector3(1.0, 0, 8);
const core = new THREE.Group(); core.position.copy(CORE); scene.add(core);
{
  const dm = mat('#1b2246', { roughness: 0.3, metalness: 0.7 });
  [[1.75, 0.09], [1.3, 0.27], [0.85, 0.45]].forEach(([r, y]) => {
    add(core, cyl(r, r + 0.05, 0.18, dm, 64), 0, y, 0);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r + 0.01, 0.022, 8, 96), gold); ring.rotation.x = Math.PI / 2; ring.position.y = y + 0.09; core.add(ring);
  });
}
const orbMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(3.2, 2.2, 0.75) });
const orb = add(core, sph(0.42, orbMat, 32, 24), 0, 1.4, 0, false);
const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: '#ffb84a', transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending }));
halo.scale.set(3.4, 3.4, 1); halo.position.y = 1.4; core.add(halo);
const rings = [0.72, 0.95].map((r, i) => { const m = new THREE.Mesh(new THREE.TorusGeometry(r, 0.014, 8, 96), gold); m.position.y = 1.4; core.add(m); return m; });
const orbLight = new THREE.PointLight('#ffc25c', 18, 9, 1.6); orbLight.position.y = 1.6; core.add(orbLight);
let flare = 0;
const pulses = [];
function pulse() {
  const m = new THREE.Mesh(new THREE.RingGeometry(0.9, 1.0, 64), new THREE.MeshBasicMaterial({ color: new THREE.Color(2.4, 1.7, 0.5), transparent: true, side: THREE.DoubleSide, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; m.position.y = 0.6; core.add(m); pulses.push({ m, t: 0 });
}

// particles (data packets)
const parts = [];
function burst(fromFn, toFn, color, n = 7) {
  for (let i = 0; i < n; i++) setTimeout(() => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    s.scale.setScalar(0.35); scene.add(s); parts.push({ s, fromFn, toFn, t: 0 });
  }, i * 80);
}
const orbPos = () => new THREE.Vector3(CORE.x, 1.4, CORE.z);

// ================= robots =================
const white = mat('#eef1f8', { roughness: 0.32, metalness: 0.05 });
const jointM = mat('#8f98ad', { roughness: 0.45, metalness: 0.3 });
const visorM = mat('#0a0e1a', { roughness: 0.12, metalness: 0.8 });
function makeRobot(accent, { suit = false } = {}) {
  const root = new THREE.Group();
  const shell = suit ? mat('#23283a', { roughness: 0.55 }) : white;
  const accM = mat(accent, { emissive: accent, emissiveIntensity: 0.7, roughness: 0.4 });
  const eyeM = glowMat(accent, 2.6);
  const hip = new THREE.Group(); root.add(hip);
  const torso = new THREE.Group(); hip.add(torso);
  add(torso, cap(0.2, 0.26, shell), 0, 0.3, 0).scale.set(1, 1, 0.85);
  const belt = add(torso, new THREE.Mesh(new THREE.TorusGeometry(0.185, 0.025, 8, 28), accM), 0, 0.17, 0); belt.rotation.x = Math.PI / 2;
  if (suit) {
    add(torso, box(0.13, 0.26, 0.02, mat('#f4f4f4')), 0, 0.4, -0.168);
    add(torso, box(0.05, 0.22, 0.025, mat('#c23b4a')), 0, 0.38, -0.175);
  } else add(torso, new THREE.Mesh(new THREE.CircleGeometry(0.045, 16), eyeM), 0, 0.42, -0.172, false).rotation.y = Math.PI;
  add(torso, cyl(0.06, 0.07, 0.08, jointM, 12), 0, 0.58, 0);
  const head = new THREE.Group(); head.position.y = 0.8; torso.add(head);
  add(head, sph(0.24, white, 28, 20)).scale.set(1.08, 0.92, 1);
  const vis = add(head, new THREE.Mesh(new THREE.SphereGeometry(0.247, 28, 12, Math.PI * 1.5 - 0.95, 1.9, Math.PI / 2 - 0.4, 0.68), visorM));
  vis.scale.set(1.08, 0.92, 1);
  add(head, sph(0.028, eyeM, 10, 8), -0.075, 0.0, -0.245, false);
  add(head, sph(0.028, eyeM, 10, 8), 0.075, 0.0, -0.245, false);
  for (const s of [-1, 1]) add(head, cyl(0.065, 0.065, 0.07, accM, 16), s * 0.26, 0, 0).rotation.z = Math.PI / 2;
  add(head, cyl(0.012, 0.012, 0.14, jointM, 6), 0, 0.27, 0);
  add(head, sph(0.035, eyeM, 10, 8), 0, 0.35, 0, false);
  const arms = [], legs = [];
  for (const s of [-1, 1]) {
    const sh = new THREE.Group(); sh.position.set(s * 0.27, 0.48, 0); sh.rotation.z = s * 0.08; torso.add(sh);
    add(sh, sph(0.075, jointM, 12, 10));
    add(sh, cap(0.062, 0.16, shell), 0, -0.14, 0);
    const el = new THREE.Group(); el.position.y = -0.29; sh.add(el);
    add(el, cap(0.058, 0.14, shell), 0, -0.11, 0);
    add(el, sph(0.066, jointM, 12, 10), 0, -0.24, 0);
    arms.push({ sh, el });
    const th = new THREE.Group(); th.position.set(s * 0.1, 0, 0); hip.add(th);
    add(th, cap(0.08, 0.18, shell), 0, -0.15, 0);
    const kn = new THREE.Group(); kn.position.y = -0.31; th.add(kn);
    add(kn, cap(0.072, 0.16, shell), 0, -0.13, 0);
    add(kn, box(0.13, 0.07, 0.24, visorM), 0, -0.29, -0.04);
    legs.push({ th, kn });
  }
  root.userData = { hip, torso, head, arms, legs, ph: Math.random() * 10, seed: Math.random() * 100 };
  return root;
}
const POSES = {
  stand: { hy: 0.645, tx: 0, th: [0, 0], kn: [0, 0], sh: [0.05, 0.05], el: [0.15, 0.15], hx: 0 },
  sit: { hy: 0.56, tx: 0, th: [1.57, 1.57], kn: [-1.45, -1.45], sh: [0.4, 0.4], el: [0.85, 0.85], hx: -0.05 },
  type: { hy: 0.56, tx: -0.1, th: [1.57, 1.57], kn: [-1.45, -1.45], sh: [0.6, 0.6], el: [0.95, 0.95], hx: -0.12 },
  lounge: { hy: 0.52, tx: 0.18, th: [1.5, 1.5], kn: [-1.3, -1.3], sh: [0.1, 0.1], el: [0.5, 0.5], hx: 0.05 },
};
function animateRobot(r, mode, t, dt) {
  const u = r.userData, k = 1 - Math.exp(-dt * 12);
  const P = POSES[mode === 'walk' ? 'stand' : mode] || POSES.stand;
  let hy = P.hy, tx = P.tx, hx = P.hx, hyaw = 0;
  const th = [...P.th], kn = [...P.kn], sh = [...P.sh], el = [...P.el];
  const tt = t + u.seed;
  if (mode === 'walk') {
    u.ph += dt * 9; const p = u.ph;
    for (let i = 0; i < 2; i++) { const s = Math.sin(p + i * Math.PI); th[i] = s * 0.55; kn[i] = -Math.max(0, -s) * 1.0; sh[i] = -s * 0.5; el[i] = 0.35; }
    hy += Math.abs(Math.sin(p)) * 0.03;
  } else if (mode === 'type') {
    for (let i = 0; i < 2; i++) el[i] += Math.sin(tt * 22 + i * Math.PI) * 0.12;
    hx += Math.sin(tt * 1.3) * 0.04; hyaw = Math.sin(tt * 0.6) * 0.12;
  } else if (mode === 'sit') {
    hyaw = Math.sin(tt * 0.35) * 0.35; hx += Math.sin(tt * 0.5) * 0.05;
  } else if (mode === 'lounge') {
    hyaw = Math.sin(tt * 0.3) * 0.5; tx += Math.sin(tt * 0.8) * 0.02;
  } else { hyaw = Math.sin(tt * 0.4) * 0.4; hy += Math.sin(tt * 2) * 0.005; }
  u.hip.position.y += (hy - u.hip.position.y) * k;
  u.torso.rotation.x += (tx - u.torso.rotation.x) * k;
  u.head.rotation.x += (hx - u.head.rotation.x) * k;
  u.head.rotation.y += (hyaw - u.head.rotation.y) * k;
  for (let i = 0; i < 2; i++) {
    const kk = mode === 'walk' ? 1 - Math.exp(-dt * 25) : k;
    u.legs[i].th.rotation.x += (th[i] - u.legs[i].th.rotation.x) * kk;
    u.legs[i].kn.rotation.x += (kn[i] - u.legs[i].kn.rotation.x) * kk;
    u.arms[i].sh.rotation.x += (sh[i] - u.arms[i].sh.rotation.x) * kk;
    u.arms[i].el.rotation.x += (el[i] - u.arms[i].el.rotation.x) * (mode === 'type' ? 1 - Math.exp(-dt * 30) : kk);
  }
}

