// 3D view of logged missions. Everything shown comes from the mission and reveal logs:
// it adds no results, and the robots don't "see" this scene. The vision model works on
// real photographs. Terrain is smoothed between grid cells, with its height exaggerated.
// Between cell centres it also gets small decorative relief and boulders, so it reads as
// seafloor. The relief fades to zero at every cell centre, so each logged depth is exact,
// and boulders are hidden whenever a data layer is shown.

import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const SUBDIVISIONS = 8;
const VERTICAL_EXAGGERATION = 3;
const ALTITUDE = 0.9;
const BACKGROUND = 0x020b12;
const SNOW_COUNT = 3200;
// How much of its colour the deepest seafloor keeps. Lower is closer to true darkness.
const DEEP_LIGHT = 0.3;
const CAUSTIC_STRENGTH = 0.09;
const NO_FINDS_COLOR = 0x7f93a3;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Sandy shelf down to blue canyon floor. The deep end stays brighter than the background.
const SEAFLOOR_STOPS = [[176, 206, 208], [112, 172, 186], [62, 126, 170], [50, 84, 166], [46, 48, 134]];
const DIVE_SECONDS = 9;
const DIVE_DESCENT_SHARE = 0.72; // the rest of the dive pulls the camera back to the overview
const GAUGE_MAX_M = 1800;
const SPOTLIGHT_ON = 64;
const SPOTLIGHT_PARKED = 7;
const BEAM_ON = 0.055;
const BEAM_PARKED = 0.012;
const DETAIL_M = 26; // decorative relief between cell centres, in metres before exaggeration
const ROCK_COUNT = 900;

const ease = (t) => t * t * (3 - 2 * t);

function seafloorRamp(t) {
  const x = Math.min(1, Math.max(0, t)) * (SEAFLOOR_STOPS.length - 1);
  const i = Math.min(Math.floor(x), SEAFLOOR_STOPS.length - 2);
  return SEAFLOOR_STOPS[i].map((v, k) => v + (SEAFLOOR_STOPS[i + 1][k] - v) * (x - i));
}

function cubic(p0, p1, p2, p3, t) {
  return p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)));
}

// Catmull-Rom upsampling, so the mesh is smooth while passing through every logged value.
function upsample(grid) {
  const rows = grid.length;
  const cols = grid[0].length;
  const at = (r, c) => grid[Math.min(rows - 1, Math.max(0, r))][Math.min(cols - 1, Math.max(0, c))];
  const height = (rows - 1) * SUBDIVISIONS + 1;
  const width = (cols - 1) * SUBDIVISIONS + 1;
  const out = new Float32Array(height * width);
  for (let i = 0; i < height; i += 1) {
    const r = Math.floor(i / SUBDIVISIONS);
    const v = i / SUBDIVISIONS - r;
    for (let j = 0; j < width; j += 1) {
      const c = Math.floor(j / SUBDIVISIONS);
      const u = j / SUBDIVISIONS - c;
      const line = [-1, 0, 1, 2].map((d) => cubic(at(r + d, c - 1), at(r + d, c), at(r + d, c + 1), at(r + d, c + 2), u));
      out[i * width + j] = cubic(line[0], line[1], line[2], line[3], v);
    }
  }
  return { values: out, height, width };
}

// Deterministic hash noise, so the decorative detail is identical on every load.
function hash(x, y, seed) {
  let h = (x * 374761393 + y * 668265263 + seed * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function valueNoise(x, y, seed) {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const u = x - x0;
  const v = y - y0;
  const su = u * u * (3 - 2 * u);
  const sv = v * v * (3 - 2 * v);
  const top = hash(x0, y0, seed) * (1 - su) + hash(x0 + 1, y0, seed) * su;
  const bottom = hash(x0, y0 + 1, seed) * (1 - su) + hash(x0 + 1, y0 + 1, seed) * su;
  return (top * (1 - sv) + bottom * sv) * 2 - 1;
}

// Ridged fractal noise: sharp crests and gullies, like eroded rock and sediment.
function relief(x, y) {
  let total = 0;
  let amplitude = 1;
  let frequency = 1.3;
  for (let octave = 0; octave < 4; octave += 1) {
    const n = 1 - Math.abs(valueNoise(x * frequency, y * frequency, 11 + octave));
    total += (n * n - 0.45) * amplitude;
    amplitude *= 0.5;
    frequency *= 2.1;
  }
  return total;
}

// Adds decorative relief between cell centres, scaled by local steepness. The weight is zero
// at every cell centre, so the mesh still passes exactly through each logged depth.
function addDetail(fine, slope) {
  const rows = slope.length;
  const cols = slope[0].length;
  let maxSlope = 1;
  for (const row of slope) for (const value of row) maxSlope = Math.max(maxSlope, value);
  for (let i = 0; i < fine.height; i += 1) {
    const fr = i / SUBDIVISIONS;
    const wr = Math.sin(Math.PI * (fr - Math.floor(fr))) ** 2;
    for (let j = 0; j < fine.width; j += 1) {
      const fc = j / SUBDIVISIONS;
      const weight = wr * Math.sin(Math.PI * (fc - Math.floor(fc))) ** 2;
      if (!weight) continue;
      const steep = slope[Math.min(rows - 1, Math.round(fr))][Math.min(cols - 1, Math.round(fc))] / maxSlope;
      // Depth grows downward, so subtracting raises crests.
      fine.values[i * fine.width + j] -= DETAIL_M * (0.45 + 1.1 * steep) * weight * relief(fc, fr);
    }
  }
}

class Polyline extends THREE.Curve {
  constructor(points) {
    super();
    this.points = points;
  }

  getPoint(t, target = new THREE.Vector3()) {
    const scaled = t * (this.points.length - 1);
    const index = Math.min(Math.floor(scaled), this.points.length - 2);
    return target.lerpVectors(this.points[index], this.points[index + 1], scaled - index);
  }
}

function disposeGroup(group) {
  group.traverse((object) => {
    object.geometry?.dispose();
    if (object.material?.map) object.material.map.dispose();
    object.material?.dispose();
  });
  group.clear();
}

function labelSprite(text, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 72;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgba(4,14,22,.82)";
  ctx.beginPath();
  ctx.roundRect(4, 8, 312, 56, 12);
  ctx.fill();
  ctx.font = "600 34px 'Segoe UI', system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.fillText(text, 160, 37);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas),
    depthTest: false,
    transparent: true,
    fog: false,
    sizeAttenuation: false, // labels stay readable at every camera distance
  }));
  sprite.scale.set(0.115, 0.026, 1);
  sprite.position.y = 0.75;
  sprite.renderOrder = 10;
  return sprite;
}

function noiseTexture(size, repeat, low, high) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(size, size);
  // Layered value noise, wrapped at the edges so the texture tiles without seams.
  const layers = [8, 16, 32, 64, 128].map((cells, n) => {
    const values = Float32Array.from({ length: cells * cells }, () => Math.random());
    return { cells, values, weight: 0.5 ** (n + 1) };
  });
  const smooth = (t) => t * t * (3 - 2 * t);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let total = 0;
      for (const { cells, values, weight } of layers) {
        const fx = (x / size) * cells;
        const fy = (y / size) * cells;
        const x0 = Math.floor(fx);
        const y0 = Math.floor(fy);
        const x1 = (x0 + 1) % cells;
        const y1 = (y0 + 1) % cells;
        const u = smooth(fx - x0);
        const v = smooth(fy - y0);
        const top = values[y0 * cells + x0] * (1 - u) + values[y0 * cells + x1] * u;
        const bottom = values[y1 * cells + x0] * (1 - u) + values[y1 * cells + x1] * u;
        total += (top * (1 - v) + bottom * v) * weight;
      }
      const value = Math.round((low + (high - low) * Math.min(1, total * 1.03)) * 255);
      const i = (y * size + x) * 4;
      image.data[i] = value;
      image.data[i + 1] = value;
      image.data[i + 2] = value;
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat, repeat);
  return texture;
}

function softDotTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.45, "rgba(255,255,255,.35)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 32, 32);
  return new THREE.CanvasTexture(canvas);
}

function waterBackground() {
  const canvas = document.createElement("canvas");
  canvas.width = 4;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 256);
  gradient.addColorStop(0, "#0b3346");
  gradient.addColorStop(0.45, "#051a27");
  gradient.addColorStop(1, "#010609");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 4, 256);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

// Shared by both vehicles: a seafloor spotlight, a faint beam and the name tag.
function addLightsAndTag(group, color, label, index, lampY, lampZ) {
  const spot = new THREE.SpotLight(0xffe8c4, SPOTLIGHT_ON, 11, 0.75, 0.85, 1.5);
  spot.position.set(0, lampY, lampZ);
  spot.target.position.set(0, -2.2, 1.35);
  group.add(spot, spot.target);
  const beam = new THREE.Mesh(
    new THREE.ConeGeometry(0.72, 1.45, 24, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0xfff0d0,
      transparent: true,
      opacity: BEAM_ON,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  beam.position.set(0, lampY - 0.62, lampZ + 0.32);
  beam.rotation.x = -0.46;
  group.add(beam);
  group.userData.spot = spot;
  group.userData.beam = beam;
  const tag = labelSprite(label, `#${new THREE.Color(color).getHexString()}`);
  tag.position.y += index * 0.5; // so labels don't overlap while the robots are side by side
  group.add(tag);
}

// ABYSS: a hovering survey drone, unlike the conventional submarine. A flat pod carries a
// glowing sensor eye, four ducted thrusters on swept arms, and two folded sampling arms.
// Forward is +z. The accent colour is the panel colour.
function buildRobot(color, label, index) {
  const group = new THREE.Group();
  const shell = new THREE.MeshStandardMaterial({ color: 0x1d2a33, roughness: 0.38, metalness: 0.6 });
  const plate = new THREE.MeshStandardMaterial({ color: 0xc9d6da, roughness: 0.3, metalness: 0.35 });
  const glow = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.6, roughness: 0.3 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x5a6872, roughness: 0.3, metalness: 0.9 });

  const pod = new THREE.Mesh(new THREE.SphereGeometry(0.3, 32, 20), shell);
  pod.scale.set(1.15, 0.5, 1.45);
  group.add(pod);
  const canopy = new THREE.Mesh(new THREE.SphereGeometry(0.3, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), plate);
  canopy.scale.set(0.95, 0.42, 1.2);
  canopy.position.y = 0.02;
  group.add(canopy);

  // Accent light strip around the waist of the pod.
  const strip = new THREE.Mesh(new THREE.TorusGeometry(0.335, 0.012, 8, 48), glow);
  strip.rotation.x = Math.PI / 2;
  strip.scale.set(1.04, 1.32, 1);
  group.add(strip);

  // Sensor eye: a dark lens ringed in colour, looking forward and down.
  const eyeRing = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.018, 10, 32), glow);
  eyeRing.position.set(0, -0.03, 0.42);
  eyeRing.rotation.x = 0.35;
  group.add(eyeRing);
  const lens = new THREE.Mesh(
    new THREE.SphereGeometry(0.075, 20, 14),
    new THREE.MeshStandardMaterial({ color: 0x050b10, emissive: color, emissiveIntensity: 0.35, roughness: 0.05, metalness: 0.2 }),
  );
  lens.position.set(0, -0.03, 0.41);
  group.add(lens);

  // Four ducted thrusters on swept arms. Their rotors spin while it travels.
  const rotors = [];
  for (const [x, z] of [[0.48, 0.3], [-0.48, 0.3], [0.48, -0.32], [-0.48, -0.32]]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(Math.abs(x) * 0.95, 0.035, 0.07), shell);
    arm.position.set(x / 2, 0, z * 0.85);
    arm.rotation.y = Math.atan2(z * 0.15, x);
    group.add(arm);
    const duct = new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.028, 10, 28), plate);
    duct.position.set(x, 0, z);
    duct.rotation.x = Math.PI / 2;
    group.add(duct);
    const tip = new THREE.Mesh(new THREE.TorusGeometry(0.121, 0.006, 6, 28), glow);
    tip.position.set(x, 0.03, z);
    tip.rotation.x = Math.PI / 2;
    group.add(tip);
    const rotor = new THREE.Group();
    for (let n = 0; n < 3; n += 1) {
      const blade = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.006, 0.1), metal);
      blade.position.z = 0.05;
      const holder = new THREE.Group();
      holder.rotation.y = (n * Math.PI * 2) / 3;
      holder.add(blade);
      rotor.add(holder);
    }
    rotor.position.set(x, 0, z);
    group.add(rotor);
    rotors.push({ object: rotor, axis: "y" });
  }

  // Folded sampling arms under the nose.
  for (const x of [-0.1, 0.1]) {
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.2, 8), metal);
    upper.position.set(x, -0.15, 0.24);
    upper.rotation.x = 0.9;
    group.add(upper);
    const claw = new THREE.Mesh(new THREE.ConeGeometry(0.025, 0.07, 8), glow);
    claw.position.set(x, -0.21, 0.33);
    claw.rotation.x = Math.PI * 0.55;
    group.add(claw);
  }

  // Sensor fin with a blinking tip.
  const fin = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.14, 0.18), shell);
  fin.position.set(0, 0.2, -0.12);
  fin.rotation.x = -0.35;
  group.add(fin);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 8), glow);
  beacon.position.set(0, 0.28, -0.17);
  group.add(beacon);
  group.userData.beacon = beacon;

  for (const x of [-0.16, 0.16]) {
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.02, 10, 8), new THREE.MeshBasicMaterial({ color: 0xfff6dc }));
    lamp.position.set(x, -0.1, 0.36);
    group.add(lamp);
  }

  group.userData.rotors = rotors;
  addLightsAndTag(group, color, label, index, -0.1, 0.3);
  group.scale.setScalar(1.25);
  return group;
}

// The conventional robot: a torpedo-shaped submarine with a sail and dive planes.
// Forward is +z. Only the band carries the panel colour.
function buildSubmarine(color, label, index) {
  const group = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ color: 0xdfe8ea, roughness: 0.34, metalness: 0.25 });
  const band = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.5, roughness: 0.4 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x4f5c66, roughness: 0.32, metalness: 0.85 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x11181e, roughness: 0.55 });

  // Radius along the hull, from tail to nose.
  const profile = [[0, -0.62], [0.05, -0.62], [0.1, -0.54], [0.17, -0.34], [0.19, -0.1], [0.19, 0.3], [0.165, 0.46], [0.1, 0.57], [0, 0.62]];
  const hull = new THREE.Mesh(
    new THREE.LatheGeometry(profile.map(([r, h]) => new THREE.Vector2(r, h)), 28),
    paint,
  );
  hull.rotation.x = Math.PI / 2;
  group.add(hull);

  const stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.193, 0.193, 0.14, 28, 1, true), band);
  stripe.rotation.x = Math.PI / 2;
  stripe.position.z = 0.1;
  group.add(stripe);

  for (const [x, y, width, height] of [[0, 0.17, 0.018, 0.18], [0, -0.17, 0.018, 0.18], [0.17, 0, 0.18, 0.018], [-0.17, 0, 0.18, 0.018]]) {
    const fin = new THREE.Mesh(new THREE.BoxGeometry(width, height, 0.17), dark);
    fin.position.set(x, y, -0.43);
    group.add(fin);
  }

  const shroud = new THREE.Mesh(new THREE.TorusGeometry(0.135, 0.018, 8, 26), metal);
  shroud.position.z = -0.63;
  group.add(shroud);
  const propeller = new THREE.Group();
  for (let n = 0; n < 3; n += 1) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.12, 0.008), metal);
    blade.position.y = 0.065;
    const holder = new THREE.Group();
    holder.rotation.z = (n * Math.PI * 2) / 3;
    holder.add(blade);
    propeller.add(holder);
  }
  propeller.position.z = -0.63;
  group.add(propeller);

  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.007, 0.007, 0.2, 6), dark);
  mast.position.set(0, 0.38, 0.08);
  group.add(mast);
  const camera = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.05, 0.13), dark);
  camera.position.set(0, -0.2, 0.28);
  group.add(camera);

  for (const x of [-0.07, 0.07]) {
    const lamp = new THREE.Mesh(
      new THREE.SphereGeometry(0.022, 10, 8),
      new THREE.MeshBasicMaterial({ color: 0xfff6dc }),
    );
    lamp.position.set(x, -0.2, 0.35);
    group.add(lamp);
  }

  // Conning tower (sail) with its own small dive planes, like a classic submarine.
  const sail = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.16, 6, 14), paint);
  sail.rotation.x = Math.PI / 2;
  sail.scale.set(1, 1, 2.2);
  sail.position.set(0, 0.24, 0.12);
  group.add(sail);
  const sailPlanes = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.012, 0.06), dark);
  sailPlanes.position.set(0, 0.27, 0.16);
  group.add(sailPlanes);
  const bowPlanes = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.012, 0.07), dark);
  bowPlanes.position.set(0, 0, 0.38);
  group.add(bowPlanes);

  group.userData.rotors = [{ object: propeller, axis: "z" }];
  addLightsAndTag(group, color, label, index, -0.2, 0.3);
  group.scale.setScalar(1.25);
  return group;
}

export function createExplorer(api) {
  const {
    app, overlayGrid, abyssPane, gridExtent, BELIEF_RAMP, HIDDEN_RAMP, LAYER_LABELS, categoryLabel,
    HABITAT_COLOURS, fillHabitatLegend, habitatChip,
  } = api;
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("stage-canvas");
  const legend = document.getElementById("stage-legend");
  const gauge = document.getElementById("gauge");
  const cameraSelect = document.getElementById("stage-camera");

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  const scene = new THREE.Scene();
  const deepBackground = waterBackground();
  scene.background = deepBackground;
  scene.fog = new THREE.FogExp2(0x03151f, 0.016);
  const shallowWater = new THREE.Color(0x2a93ad);
  const deepWater = new THREE.Color(0x03151f);
  const skyWater = new THREE.Color(0x3fb2c6);
  const trenchWater = new THREE.Color(0x020b12);
  const causticTime = { value: 0 };
  const causticStrength = { value: CAUSTIC_STRENGTH };
  const sedimentColour = noiseTexture(512, 7, 0.55, 1);
  sedimentColour.colorSpace = THREE.SRGBColorSpace;
  const sedimentBump = noiseTexture(512, 14, 0, 1);
  const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 400);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 5;
  controls.maxDistance = 140;

  // Water absorbs red first, so surface light reaches the seafloor blue-green.
  const ambient = new THREE.HemisphereLight(0x9fd8e8, 0x0b1c26, 1.25);
  scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xbfeaf0, 1.5);
  sun.position.set(-14, 34, -10);
  scene.add(sun);

  const world = new THREE.Group();
  scene.add(world);

  // The sea surface and its light shafts appear only during the illustrative descent.
  const surfaceTexture = noiseTexture(256, 26, 0.15, 1);
  const surface = new THREE.Mesh(
    new THREE.PlaneGeometry(320, 320),
    new THREE.MeshBasicMaterial({
      color: 0xbff4f2,
      map: surfaceTexture,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
      depthWrite: false,
      fog: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  surface.rotation.x = -Math.PI / 2;
  surface.visible = false;
  scene.add(surface);
  const shafts = new THREE.Group();
  const shaftMaterial = new THREE.MeshBasicMaterial({
    color: 0xd6fbf6,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
    depthWrite: false,
    fog: false,
    blending: THREE.AdditiveBlending,
  });
  [[-3.5, -2, 0.22], [1.5, -5, -0.16], [5, 1, 0.12], [-1, 4.5, -0.26], [7.5, -4, 0.3], [3, 6.5, -0.1], [-6, 3, 0.18]].forEach(([x, z, lean]) => {
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 1.5, 15, 14, 1, true), shaftMaterial);
    shaft.position.set(x, -7.5, z);
    shaft.rotation.z = lean;
    shafts.add(shaft);
  });
  shafts.visible = false;
  scene.add(shafts);

  let dive = null;
  let parked = false;
  let parkAngle = 0;

  let terrain = null;
  let views = [];
  let active = false;
  let frameRequested = false;
  let followIndex = -1;
  let colourKey = null;
  let snow = null;
  let lastTime = 0;

  function terrainData(log) {
    const depth = log.terrain.depth_m;
    const fine = upsample(depth);
    addDetail(fine, log.terrain.slope_deg);
    const [lo, hi] = gridExtent(depth);
    const scale = VERTICAL_EXAGGERATION / log.terrain.cell_size_m;
    const middle = (lo + hi) / 2;
    return {
      fine,
      lo,
      hi,
      rows: depth.length,
      cols: depth[0].length,
      yOf: (d) => -(d - middle) * scale,
      centreR: (depth.length - 1) / 2,
      centreC: (depth[0].length - 1) / 2,
    };
  }

  const heightAt = (r, c) => terrain.yOf(depthAt(r, c));

  function depthAt(r, c) {
    const { fine, rows, cols } = terrain;
    const fr = Math.min(rows - 1, Math.max(0, r)) * SUBDIVISIONS;
    const fc = Math.min(cols - 1, Math.max(0, c)) * SUBDIVISIONS;
    const r0 = Math.min(Math.floor(fr), fine.height - 2);
    const c0 = Math.min(Math.floor(fc), fine.width - 2);
    const u = fc - c0;
    const v = fr - r0;
    const at = (i, j) => fine.values[i * fine.width + j];
    const top = at(r0, c0) * (1 - u) + at(r0, c0 + 1) * u;
    const bottom = at(r0 + 1, c0) * (1 - u) + at(r0 + 1, c0 + 1) * u;
    return top * (1 - v) + bottom * v;
  }

  const toWorld = (r, c, lift = 0) => new THREE.Vector3(c - terrain.centreC, heightAt(r, c) + lift, r - terrain.centreR);

  function buildTerrain(pane) {
    const { fine, yOf, centreC, centreR } = terrain;
    const count = fine.height * fine.width;
    const positions = new Float32Array(count * 3);
    const uvs = new Float32Array(count * 2);
    for (let i = 0; i < fine.height; i += 1) {
      for (let j = 0; j < fine.width; j += 1) {
        const n = i * fine.width + j;
        positions[n * 3] = j / SUBDIVISIONS - centreC;
        positions[n * 3 + 1] = yOf(fine.values[n]);
        positions[n * 3 + 2] = i / SUBDIVISIONS - centreR;
        uvs[n * 2] = j / (fine.width - 1);
        uvs[n * 2 + 1] = i / (fine.height - 1);
      }
    }
    const indices = [];
    for (let i = 0; i < fine.height - 1; i += 1) {
      for (let j = 0; j < fine.width - 1; j += 1) {
        const a = i * fine.width + j;
        const b = a + 1;
        const c = a + fine.width;
        const d = c + 1;
        indices.push(a, c, b, b, c, d);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    // The sediment texture and caustics change only the surface's look, never its shape.
    const seabed = new THREE.MeshStandardMaterial({
      vertexColors: true,
      map: sedimentColour,
      bumpMap: sedimentBump,
      bumpScale: 1.6,
      roughness: 1,
      metalness: 0,
    });
    seabed.onBeforeCompile = (shader) => {
      shader.uniforms.causticTime = causticTime;
      shader.uniforms.causticStrength = causticStrength;
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying vec3 vSeabedPosition;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvSeabedPosition = (modelMatrix * vec4(position, 1.0)).xyz;");
      shader.fragmentShader = shader.fragmentShader
        .replace("#include <common>", "#include <common>\nvarying vec3 vSeabedPosition;\nuniform float causticTime;\nuniform float causticStrength;")
        .replace("#include <opaque_fragment>", `
          vec2 causticPoint = vSeabedPosition.xz * 2.3;
          causticPoint += 0.9 * vec2(sin(vSeabedPosition.z * 0.73 + causticTime * 0.4), cos(vSeabedPosition.x * 0.61 - causticTime * 0.3));
          float causticWave = sin(causticPoint.x * 1.17 + causticTime + 1.7 * sin(causticPoint.y * 0.83 - causticTime * 0.6))
            + sin(causticPoint.y * 1.31 - causticTime * 0.7 + 1.5 * sin(causticPoint.x * 0.71 + causticTime * 0.5));
          float shallowness = smoothstep(1.5, 5.4, vSeabedPosition.y);
          outgoingLight += vec3(0.4, 0.62, 0.58) * pow(1.0 - min(1.0, abs(causticWave)), 9.0) * causticStrength * shallowness;
          #include <opaque_fragment>`);
    };
    terrain.mesh = new THREE.Mesh(geometry, seabed);
    world.add(terrain.mesh);

    // Close the sides of the block, so its edges read as a cut-out of the seafloor.
    const bottom = yOf(terrain.hi) - 1.5;
    const skirt = [];
    const edge = (list) => {
      for (let n = 0; n < list.length - 1; n += 1) {
        const [ai, aj] = list[n];
        const [bi, bj] = list[n + 1];
        const top = (i, j) => [j / SUBDIVISIONS - centreC, yOf(fine.values[i * fine.width + j]), i / SUBDIVISIONS - centreR];
        const low = (i, j) => [j / SUBDIVISIONS - centreC, bottom, i / SUBDIVISIONS - centreR];
        skirt.push(...top(ai, aj), ...low(ai, aj), ...top(bi, bj), ...top(bi, bj), ...low(ai, aj), ...low(bi, bj));
      }
    };
    const across = [...Array(fine.width).keys()];
    const down = [...Array(fine.height).keys()];
    edge(across.map((j) => [0, j]));
    edge(across.map((j) => [fine.height - 1, j]));
    edge(down.map((i) => [i, 0]));
    edge(down.map((i) => [i, fine.width - 1]));
    const skirtGeometry = new THREE.BufferGeometry();
    skirtGeometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(skirt), 3));
    // Near the background colour, so the cut edges fade into dark water.
    world.add(new THREE.Mesh(skirtGeometry, new THREE.MeshBasicMaterial({ color: 0x041018, side: THREE.DoubleSide })));

    const lines = [];
    for (const [a, b] of pane.isobaths) lines.push(toWorld(a[0], a[1], 0.03), toWorld(b[0], b[1], 0.03));
    terrain.contours = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(lines),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.16 }),
    );
    world.add(terrain.contours);
    buildRocks(pane.log.terrain.slope_deg);
  }

  // Decorative boulders, denser on steep ground. Placement is seeded, so it never changes.
  function buildRocks(slope) {
    const { rows, cols } = terrain;
    let maxSlope = 1;
    for (const row of slope) for (const value of row) maxSlope = Math.max(maxSlope, value);
    const geometry = new THREE.DodecahedronGeometry(1, 0);
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95, flatShading: true });
    const rocks = new THREE.InstancedMesh(geometry, material, ROCK_COUNT);
    const matrix = new THREE.Matrix4();
    const rotation = new THREE.Quaternion();
    const euler = new THREE.Euler();
    const size = new THREE.Vector3();
    const tint = new THREE.Color();
    let placed = 0;
    for (let n = 0; placed < ROCK_COUNT && n < ROCK_COUNT * 12; n += 1) {
      const r = hash(n, 1, 7) * (rows - 1);
      const c = hash(n, 2, 7) * (cols - 1);
      const steep = slope[Math.round(r)][Math.round(c)] / maxSlope;
      if (hash(n, 3, 7) > 0.18 + 0.82 * steep) continue; // keep more boulders on steep ground
      const radius = 0.035 + 0.13 * hash(n, 4, 7) ** 2.2 * (0.6 + steep);
      euler.set(hash(n, 5, 7) * 6.3, hash(n, 6, 7) * 6.3, hash(n, 8, 7) * 6.3);
      rotation.setFromEuler(euler);
      size.set(radius * (0.8 + 0.5 * hash(n, 9, 7)), radius * (0.45 + 0.35 * hash(n, 10, 7)), radius);
      matrix.compose(toWorld(r, c, -radius * 0.2), rotation, size); // half-buried in sediment
      rocks.setMatrixAt(placed, matrix);
      // Match the seabed's colour and darkness at this depth, a little darker, so boulders
      // read as part of the floor rather than floating debris.
      const t = (depthAt(r, c) - terrain.lo) / (terrain.hi - terrain.lo || 1);
      const light = (1 - (1 - DEEP_LIGHT) * t) * (0.5 + 0.25 * hash(n, 12, 7));
      const [cr, cg, cb] = seafloorRamp(t);
      rocks.setColorAt(placed, tint.setRGB((cr * light) / 255, (cg * light) / 255, (cb * light) / 255, THREE.SRGBColorSpace));
      placed += 1;
    }
    rocks.count = placed;
    terrain.rocks = rocks;
    world.add(rocks);
  }

  function recolour(grid, ramp) {
    const { fine, lo, hi } = terrain;
    const colours = terrain.mesh.geometry.getAttribute("color");
    const colour = new THREE.Color();
    let values = fine.values;
    let low = lo;
    let span = hi - lo || 1;
    if (grid) {
      values = upsample(grid).values;
      const [gridLow, gridHigh] = gridExtent(grid);
      low = gridLow;
      span = gridHigh - gridLow || 1;
    }
    for (let n = 0; n < values.length; n += 1) {
      const [r, g, b] = ramp((values[n] - low) / span);
      // Plain terrain darkens with depth. Data layers stay at full strength to stay readable.
      const light = grid ? 1 : 1 - (1 - DEEP_LIGHT) * ((fine.values[n] - lo) / (hi - lo || 1));
      colour.setRGB((r * light) / 255, (g * light) / 255, (b * light) / 255, THREE.SRGBColorSpace);
      colours.setXYZ(n, colour.r, colour.g, colour.b);
    }
    colours.needsUpdate = true;
  }

  // Classes are categories, so each vertex takes its nearest cell's class with no blending.
  function recolourHabitats(classes) {
    const { fine } = terrain;
    const colours = terrain.mesh.geometry.getAttribute("color");
    const colour = new THREE.Color();
    for (let i = 0; i < fine.height; i += 1) {
      const row = classes[Math.round(i / SUBDIVISIONS)];
      for (let j = 0; j < fine.width; j += 1) {
        const [r, g, b] = HABITAT_COLOURS[row[Math.round(j / SUBDIVISIONS)]];
        colour.setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace);
        colours.setXYZ(i * fine.width + j, colour.r, colour.g, colour.b);
      }
    }
    colours.needsUpdate = true;
  }

  function updateColours() {
    const pane = abyssPane();
    if (!pane?.mission || !terrain) return;
    const grid = overlayGrid(pane, pane.mission);
    if (colourKey === (grid || "terrain")) return;
    colourKey = grid || "terrain";
    // Nothing decorative may distort a data layer.
    causticStrength.value = grid ? 0 : CAUSTIC_STRENGTH;
    if (terrain.rocks) terrain.rocks.visible = !grid;
    const seabed = terrain.mesh.material;
    seabed.map = grid ? null : sedimentColour;
    seabed.bumpMap = grid ? null : sedimentBump;
    seabed.needsUpdate = true;
    if (grid && app.layer === "habitat") {
      recolourHabitats(grid);
      fillHabitatLegend(legend, pane.log.terrain.habitat.names);
      return;
    }
    // Hidden richness is highly concentrated, so its colour scale lifts the low end to stay
    // visible on the unlit terrain. This changes the display only, never the values.
    const hiddenRamp = (t) => HIDDEN_RAMP(t ** 0.55);
    recolour(grid, !grid ? seafloorRamp : app.layer === "hidden" ? hiddenRamp : BELIEF_RAMP);
    if (grid) {
      const [low, high] = gridExtent(grid);
      const scale = app.layer === "hidden" ? ". Non-linear colour scale" : "";
      legend.textContent = `${LAYER_LABELS[app.layer]}: ${low.toFixed(2)} (dark) to ${high.toFixed(2)} (bright)${scale}`;
    } else if (app.layer === "terrain") {
      legend.textContent = `Depth ${Math.round(terrain.lo)} to ${Math.round(terrain.hi)} m. Lines every 250 m.`;
    } else {
      legend.textContent = `${LAYER_LABELS[app.layer] || "Layer"}: no data yet. The first survey hasn't finished.`;
    }
  }

  function densify(cells) {
    const points = [];
    for (let n = 0; n < cells.length; n += 1) {
      const [r, c] = cells[n];
      const previous = cells[n - 1];
      if (previous) {
        if (previous[0] === r && previous[1] === c) continue;
        for (let s = 1; s < 3; s += 1) {
          const f = s / 3;
          points.push(toWorld(previous[0] + (r - previous[0]) * f, previous[1] + (c - previous[1]) * f, ALTITUDE));
        }
      }
      points.push(toWorld(r, c, ALTITUDE));
    }
    return points;
  }

  function tube(cells, material) {
    const points = densify(cells);
    if (points.length < 2) return null;
    return new THREE.Mesh(new THREE.TubeGeometry(new Polyline(points), Math.min(points.length * 2, 1500), 0.024, 5, false), material);
  }

  function buildView(pane, index) {
    const color = new THREE.Color(pane.color).getHex();
    const view = {
      pane,
      index,
      color,
      vehicle: (pane === abyssPane() ? buildRobot : buildSubmarine)(color, pane.entry.label, index),
      trailMaterial: new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.72 }),
      completed: new THREE.Group(),
      markers: new THREE.Group(),
      current: null,
      completedCount: -1,
      feedKey: null,
      rest: 0,
      heading: 0,
      targetRing: new THREE.Mesh(
        new THREE.TorusGeometry(0.42, 0.035, 8, 32),
        new THREE.MeshBasicMaterial({ color }),
      ),
      targetLine: new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
        new THREE.LineDashedMaterial({ color, dashSize: 0.3, gapSize: 0.22, transparent: true, opacity: 0.85 }),
      ),
    };
    view.targetRing.rotation.x = Math.PI / 2;
    world.add(view.vehicle, view.completed, view.markers, view.targetRing, view.targetLine);

    const card = document.createElement("section");
    card.className = "hud";
    card.style.setProperty("--pane-color", pane.color);
    pane.el.root.querySelector(".hud-slot").append(card);
    view.card = card;
    return view;
  }

  function rebuildCompleted(view) {
    const { mission } = view.pane;
    disposeGroup(view.completed);
    disposeGroup(view.markers);
    const cells = mission.completed.flatMap((s) => s.step.route);
    const path = tube(cells, view.trailMaterial.clone());
    if (path) view.completed.add(path);

    // Survey sites are small seabed beacons, with a brighter head where organisms were found.
    const ring = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85 });
    const found = new THREE.MeshBasicMaterial({ color: view.color });
    const empty = new THREE.MeshStandardMaterial({ color: NO_FINDS_COLOR, roughness: 0.8 });
    const post = new THREE.MeshStandardMaterial({ color: 0x2c3841, roughness: 0.7 });
    const column = new THREE.MeshBasicMaterial({
      color: 0xcfe9ff,
      transparent: true,
      opacity: 0.28,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    for (const { step } of mission.completed) {
      if (!step.observation) continue;
      const [r, c] = step.observation.waypoint;
      if (step.observation.habitat?.new_class) {
        const beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.075, 2.6, 10, 1, true), column.clone());
        beacon.position.copy(toWorld(r, c, 1.3));
        view.markers.add(beacon);
      }
      const richness = step.observation.richness;
      const radius = richness ? 0.05 + Math.sqrt(richness) * 0.04 : 0.04;
      const height = 0.2 + radius;
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.02, height, 6), post.clone());
      stem.position.copy(toWorld(r, c, height / 2));
      view.markers.add(stem);
      const head = new THREE.Mesh(new THREE.SphereGeometry(radius, 14, 10), richness ? found.clone() : empty.clone());
      head.position.copy(toWorld(r, c, height + radius * 0.5));
      view.markers.add(head);
      if (step.new_discoveries.length) {
        const halo = new THREE.Mesh(new THREE.TorusGeometry(radius + 0.06, 0.01, 8, 32), ring.clone());
        halo.rotation.x = Math.PI / 2;
        halo.position.copy(head.position);
        view.markers.add(halo);
      }
    }
    view.completedCount = mission.completed.length;
  }

  function updateCard(view) {
    const { pane, card } = view;
    const surveys = pane.mission.completed.filter((s) => s.step.observation);
    const key = `${surveys.length}|${pane.mission.phase}`;
    if (view.feedKey === key) return;
    view.feedKey = key;

    const title = document.createElement("h3");
    title.textContent = `${pane.entry.label} camera feed`;
    const body = document.createElement("div");
    body.className = "hud-body";
    const last = surveys[surveys.length - 1]?.step;
    if (!last) {
      const wait = document.createElement("p");
      wait.textContent = "Waiting for the first survey";
      body.append(wait);
    } else {
      const obs = last.observation;
      const [r, c] = obs.waypoint;
      const meta = document.createElement("p");
      const depth = Math.round(pane.log.terrain.depth_m[r][c]);
      const slope = pane.log.terrain.slope_deg[r][c].toFixed(1);
      meta.className = "hud-meta";
      meta.textContent = `Survey ${surveys.length} at (${r}, ${c}), ${depth} m, slope ${slope}°`;
      body.append(meta);
      for (const ref of obs.image_refs) {
        if (ref.includes("://")) continue;
        const image = document.createElement("img");
        image.src = ref;
        image.alt = "Marine image used as a simulated camera encounter";
        image.addEventListener("error", () => image.remove());
        body.append(image);
      }
      const chips = document.createElement("p");
      chips.className = "hud-chips";
      for (const category of obs.categories) {
        const chip = document.createElement("span");
        const isNew = last.new_discoveries.includes(category);
        chip.className = isNew ? "chip new" : "chip";
        chip.textContent = isNew ? `New: ${categoryLabel(category)}` : categoryLabel(category);
        chips.append(chip);
      }
      obs.unknown_flags.forEach((unknown, n) => {
        if (!unknown) return;
        const chip = document.createElement("span");
        chip.className = "chip unknown";
        chip.textContent = `Unfamiliar, novelty ${obs.novelty_scores[n].toFixed(2)}`;
        chips.append(chip);
      });
      if (!chips.childElementCount) chips.textContent = "No organisms in this survey";
      body.append(chips);
      const habitat = habitatChip(obs);
      if (habitat) {
        const line = document.createElement("p");
        line.className = "hud-chips";
        line.append(habitat);
        body.append(line);
      }
      const note = document.createElement("p");
      note.className = "hud-note";
      const model = pane.log.provenance.perception;
      note.textContent = model === "ideal" ? "Simulated labels, ideal perception" : `Perception model: ${model}`;
      body.append(note);
    }
    card.replaceChildren(title, body);
  }

  function updateCameraOptions() {
    const options = [new Option("Orbit view", "-1")];
    views.forEach((view) => options.push(new Option(`Follow ${view.pane.entry.label}`, String(view.index))));
    cameraSelect.replaceChildren(...options);
    cameraSelect.value = String(followIndex);
  }

  function resetCamera() {
    camera.position.copy(orbitPosition());
    controls.target.set(0, -1, 1);
    controls.update();
  }

  function setFollow(index) {
    parked = false;
    followIndex = index;
    controls.enabled = index < 0;
    cameraSelect.value = String(index);
    if (index < 0) resetCamera();
  }

  function buildSnow() {
    const positions = new Float32Array(SNOW_COUNT * 3);
    for (let n = 0; n < SNOW_COUNT; n += 1) {
      positions[n * 3] = (Math.random() - 0.5) * 60;
      positions[n * 3 + 1] = Math.random() * 34 - 12;
      positions[n * 3 + 2] = (Math.random() - 0.5) * 60;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    snow = new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xcfe6ee,
      size: 0.11,
      map: softDotTexture(),
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
    }));
    scene.add(snow);
  }

  function updateVehicle(view, time, delta) {
    const { pane, vehicle } = view;
    const { mission } = pane;
    if (!mission) return;
    if (mission.completed.length !== view.completedCount) rebuildCompleted(view);
    vehicle.visible = !document.body.classList.contains("pre-dive");

    const [r, c] = mission.position;
    // At mission end the robot settles lower and powers down. This is presentation only.
    const finished = mission.phase === "done" && !dive;
    view.rest += ((finished ? 1 : 0) - view.rest) * Math.min(1, delta * 1.3);
    const position = toWorld(r, c, ALTITUDE - 0.5 * view.rest);
    // Both robots share a home cell, so they're drawn apart when close to it.
    const [homeRow, homeCol] = pane.log.terrain.home;
    const nearHome = Math.max(0, 1 - Math.hypot(r - homeRow, c - homeCol) / 2.5);
    position.x += nearHome * (view.index === 0 ? -0.6 : 0.6);

    let descent = 1;
    if (dive) {
      descent = ease(Math.min(1, (time - dive.start) / (DIVE_SECONDS * DIVE_DESCENT_SHARE)));
      position.y = terrain.yOf(0) + (position.y - terrain.yOf(0)) * descent;
    }
    const dx = position.x - vehicle.position.x;
    const dz = position.z - vehicle.position.z;
    if (dx * dx + dz * dz > 1e-5) {
      const desired = Math.atan2(dx, dz);
      let turn = desired - view.heading;
      turn = Math.atan2(Math.sin(turn), Math.cos(turn));
      view.heading += turn * Math.min(1, delta * 8);
    }
    vehicle.position.copy(position);
    if (!reducedMotion) {
      vehicle.position.y += Math.sin(time * 1.1 + view.index) * 0.025 * (1 - view.rest);
      if (mission.phase === "travel" || dive) {
        for (const { object, axis } of vehicle.userData.rotors) object.rotation[axis] += delta * 24;
      }
      const { beacon } = vehicle.userData;
      if (beacon) beacon.visible = view.rest > 0.5 || Math.sin(time * 3.2) > -0.2;
    }
    vehicle.rotation.y = view.heading;
    vehicle.rotation.x = dive ? 0.55 * (1 - descent) : 0;
    // Lights have no visible effect in bright surface water, so they grow with depth.
    vehicle.userData.spot.intensity = (SPOTLIGHT_ON + (SPOTLIGHT_PARKED - SPOTLIGHT_ON) * view.rest) * descent;
    vehicle.userData.beam.material.opacity = (BEAM_ON + (BEAM_PARKED - BEAM_ON) * view.rest) * descent;

    const shownDepth = depthAt(r, c) * descent;
    view.gaugeBot.style.top = `${(100 * Math.min(GAUGE_MAX_M, shownDepth)) / GAUGE_MAX_M}%`;
    view.gaugeLabel.textContent = `${Math.round(shownDepth)} m`;

    if (view.current) {
      view.current.geometry.dispose();
      view.current.parent.remove(view.current);
      view.current = null;
    }
    const current = mission.current;
    if (current && app.energy > current.start) {
      const done = mission.completed.flatMap((s) => s.step.route).length;
      const cells = mission.trail.slice(done);
      const last = mission.completed[mission.completed.length - 1]?.step.position;
      const leg = tube(last ? [last, ...cells] : cells, view.trailMaterial);
      if (leg) {
        world.add(leg);
        view.current = leg;
      }
    }

    const hasTarget = Boolean(current?.step.observation);
    view.targetRing.visible = hasTarget;
    view.targetLine.visible = hasTarget;
    if (hasTarget) {
      const route = current.step.route;
      const [tr, tc] = route[route.length - 1];
      view.targetRing.position.copy(toWorld(tr, tc, 0.09));
      view.targetLine.geometry.setFromPoints([position, toWorld(tr, tc, ALTITUDE)]);
      view.targetLine.computeLineDistances();
    }
  }

  function updateFollowCamera(delta) {
    const view = views[followIndex];
    if (!view) return;
    const { vehicle } = view;
    if (parked && !reducedMotion) parkAngle += delta * 0.14;
    const heading = parked ? parkAngle : view.heading;
    const behind = new THREE.Vector3(-Math.sin(heading) * 5.5, 2.3, -Math.cos(heading) * 5.5);
    const wanted = vehicle.position.clone().add(behind);
    const row = wanted.z + terrain.centreR;
    const col = wanted.x + terrain.centreC;
    wanted.y = Math.max(wanted.y, heightAt(row, col) + 1.2);
    camera.position.lerp(wanted, Math.min(1, delta * 2.5));
    camera.lookAt(vehicle.position);
  }

  function resize() {
    const { width, height } = canvas.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    // Keep the seafloor centred in the space left of the instrument column.
    if (width > 900) camera.setViewOffset(width, height, 130, 0, width, height);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  }

  function orbitPosition() {
    // Pull back on narrow screens so the whole block fits.
    const fit = Math.max(1, 1.75 / camera.aspect) ** 0.6;
    return new THREE.Vector3(-5 * fit, 25 * fit, 35 * fit);
  }

  function updateDive(time) {
    const elapsed = (time - dive.start) / DIVE_SECONDS;
    if (elapsed >= 1) {
      endDive(true);
      return;
    }
    const down = ease(Math.min(1, elapsed / DIVE_DESCENT_SHARE));
    const anchor = views.find((view) => view.pane === abyssPane())?.vehicle.position || new THREE.Vector3();
    const near = anchor.clone().add(new THREE.Vector3(6, -1.2 + 3.2 * down, 8));
    const pull = ease(Math.max(0, (elapsed - DIVE_DESCENT_SHARE) / (1 - DIVE_DESCENT_SHARE)));
    camera.position.lerpVectors(near, orbitPosition(), pull);
    camera.lookAt(anchor.clone().lerp(new THREE.Vector3(0, -1, 1), pull));

    // Light fades and the water darkens with depth.
    scene.fog.color.lerpColors(shallowWater, deepWater, down);
    scene.fog.density = 0.024 + (0.016 - 0.024) * down;
    scene.background.lerpColors(skyWater, trenchWater, down);
    ambient.intensity = 3.2 + (1.25 - 3.2) * down;
    renderer.toneMappingExposure = 1.55 + (1.15 - 1.55) * down;
    surface.material.opacity = 0.6 * (1 - down);
    shaftMaterial.opacity = 0.05 * (1 - down);
    surfaceTexture.offset.set(time * 0.012, time * 0.008);
  }

  function endDive(notify) {
    if (!dive) return;
    const { onDone } = dive;
    dive = null;
    scene.background = deepBackground;
    scene.fog.color.copy(deepWater);
    scene.fog.density = 0.016;
    ambient.intensity = 1.25;
    renderer.toneMappingExposure = 1.15;
    surface.visible = false;
    shafts.visible = false;
    setFollow(-1);
    if (notify) onDone();
  }

  function startDive(onDone) {
    if (!terrain) return;
    endDive(false);
    parked = false;
    followIndex = -1;
    cameraSelect.value = "-1";
    controls.enabled = false;
    dive = { start: performance.now() / 1000, onDone };
    views.forEach((view) => { view.rest = 0; });
    scene.background = skyWater.clone();
    surface.position.y = terrain.yOf(0) + 1.3;
    surface.visible = true;
    const [homeRow, homeCol] = app.panes[0].log.terrain.home;
    shafts.position.set(homeCol - terrain.centreC, surface.position.y, homeRow - terrain.centreR);
    shafts.visible = true;
  }

  function buildGauge() {
    gauge.replaceChildren();
    for (let depth = 0; depth <= 1500; depth += 500) {
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.style.top = `${(100 * depth) / GAUGE_MAX_M}%`;
      mark.textContent = depth === 0 ? "Surface" : `${depth} m`;
      gauge.append(mark);
    }
    views.forEach((view) => {
      const bot = document.createElement("span");
      bot.className = "bot";
      bot.style.setProperty("--c", view.pane.color);
      const label = document.createElement("b");
      if (view.index === 1) label.style.top = "6px";
      bot.append(label);
      gauge.append(bot);
      view.gaugeBot = bot;
      view.gaugeLabel = label;
    });
  }

  function frame(now) {
    frameRequested = false;
    if (!active) return;
    requestFrame();
    const time = now / 1000;
    const delta = Math.min(0.1, time - lastTime);
    lastTime = time;
    if (terrain) {
      for (const view of views) updateVehicle(view, time, delta);
      if (dive) updateDive(time);
      else if (followIndex >= 0) updateFollowCamera(delta);
      else controls.update();
    }
    if (snow && !reducedMotion) {
      causticTime.value = time * 0.55;
      const positions = snow.geometry.getAttribute("position");
      for (let n = 0; n < SNOW_COUNT; n += 1) {
        // During the descent, snow streams upward past the sinking camera.
        let y = positions.getY(n) + delta * (dive ? 1.5 : -0.09);
        if (y < -12) y = 22;
        if (y > 22) y = -12;
        positions.setY(n, y);
        positions.setX(n, positions.getX(n) + Math.sin(time * 0.3 + n) * delta * 0.03);
      }
      positions.needsUpdate = true;
    }
    renderer.render(scene, camera);
  }

  function requestFrame() {
    if (!frameRequested) {
      frameRequested = true;
      requestAnimationFrame(frame);
    }
  }

  function loadWorld() {
    endDive(false);
    disposeGroup(world);
    views.forEach((view) => view.card.remove());
    views = [];
    colourKey = null;
    if (!app.panes.length) return;
    terrain = terrainData(app.panes[0].log);
    buildTerrain(app.panes[0]);
    views = app.panes.map(buildView);
    buildGauge();
    if (followIndex >= views.length) followIndex = -1;
    updateCameraOptions();
    views.forEach((view) => { view.vehicle.position.copy(toWorld(...view.pane.log.terrain.home, ALTITUDE)); });
    // Home station: a low seabed dock with a lit ring.
    const home = new THREE.Group();
    const dock = new THREE.Mesh(
      new THREE.CylinderGeometry(0.62, 0.72, 0.1, 32),
      new THREE.MeshStandardMaterial({ color: 0x2b3944, roughness: 0.55, metalness: 0.5 }),
    );
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.62, 0.016, 8, 48),
      new THREE.MeshBasicMaterial({ color: 0xd8fff7 }),
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.06;
    home.add(dock, ring);
    home.position.copy(toWorld(...app.panes[0].log.terrain.home, 0.06));
    world.add(home);
    sync();
  }

  function sync() {
    if (!terrain || !views.length) return;
    updateColours();
    for (const view of views) if (view.pane.mission) updateCard(view);
  }

  cameraSelect.addEventListener("change", () => setFollow(Number(cameraSelect.value)));
  new ResizeObserver(resize).observe(stage);
  buildSnow();
  resize();
  resetCamera();

  return {
    loadWorld,
    sync,
    setFollow,
    followAbyss: () => setFollow(views.findIndex((view) => view.pane === abyssPane())),
    dive: startDive,
    endDive,
    park() {
      const index = views.findIndex((view) => view.pane === abyssPane());
      setFollow(index);
      parked = true;
      parkAngle = views[index]?.heading || 0;
    },
    setActive(value) {
      active = value;
      if (active) {
        resize();
        lastTime = performance.now() / 1000;
        requestFrame();
      }
    },
  };
}
