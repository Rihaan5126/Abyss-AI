// 3D view of logged missions. Everything shown comes from the mission and reveal logs:
// it adds no results, and the robots don't "see" this scene. The vision model works on
// real photographs. Terrain is smoothed between grid cells, with its height exaggerated.

import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const SUBDIVISIONS = 4;
const VERTICAL_EXAGGERATION = 3;
const ALTITUDE = 0.9;
const BACKGROUND = 0x06151f;
const SNOW_COUNT = 1400;
const NO_FINDS_COLOR = 0x7f93a3;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Sandy shelf down to blue canyon floor. The deep end stays brighter than the background.
const SEAFLOOR_STOPS = [[199, 186, 143], [128, 158, 140], [70, 128, 148], [52, 92, 150], [46, 62, 128]];

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

function buildVehicle(color, label) {
  const group = new THREE.Group();
  const hull = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.35, roughness: 0.4 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x18242e, roughness: 0.6 });

  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.75, 6, 14), hull);
  body.rotation.x = Math.PI / 2;
  group.add(body);
  const fin = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.3, 0.26), dark);
  fin.position.set(0, 0.17, -0.42);
  group.add(fin);
  const planes = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.04, 0.2), dark);
  planes.position.z = -0.42;
  group.add(planes);

  const beam = new THREE.Mesh(
    new THREE.ConeGeometry(0.72, ALTITUDE / 1.5, 20, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0xdff4ff,
      transparent: true,
      opacity: 0.14,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  beam.position.y = -ALTITUDE / 3;
  group.add(beam);

  const glow = new THREE.PointLight(0xdff4ff, 6, 5, 2);
  glow.position.y = -0.3;
  group.add(glow);
  group.add(labelSprite(label, `#${new THREE.Color(color).getHexString()}`));
  group.scale.setScalar(1.5);
  return group;
}

export function createExplorer(api) {
  const { app, overlayGrid, abyssPane, gridExtent, BELIEF_RAMP, HIDDEN_RAMP, LAYER_LABELS, categoryLabel } = api;
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("stage-canvas");
  const legend = document.getElementById("stage-legend");
  const hud = document.getElementById("stage-hud");
  const cameraSelect = document.getElementById("stage-camera");

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BACKGROUND);
  scene.fog = new THREE.FogExp2(BACKGROUND, 0.011);
  const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 400);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 5;
  controls.maxDistance = 140;

  scene.add(new THREE.HemisphereLight(0xcfeaff, 0x1b3a4b, 2.2));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(-20, 30, -15);
  scene.add(sun);

  const world = new THREE.Group();
  scene.add(world);

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

  function heightAt(r, c) {
    const { fine, yOf, rows, cols } = terrain;
    const fr = Math.min(rows - 1, Math.max(0, r)) * SUBDIVISIONS;
    const fc = Math.min(cols - 1, Math.max(0, c)) * SUBDIVISIONS;
    const r0 = Math.min(Math.floor(fr), fine.height - 2);
    const c0 = Math.min(Math.floor(fc), fine.width - 2);
    const u = fc - c0;
    const v = fr - r0;
    const at = (i, j) => fine.values[i * fine.width + j];
    const top = at(r0, c0) * (1 - u) + at(r0, c0 + 1) * u;
    const bottom = at(r0 + 1, c0) * (1 - u) + at(r0 + 1, c0 + 1) * u;
    return yOf(top * (1 - v) + bottom * v);
  }

  const toWorld = (r, c, lift = 0) => new THREE.Vector3(c - terrain.centreC, heightAt(r, c) + lift, r - terrain.centreR);

  function buildTerrain(pane) {
    const { fine, yOf, centreC, centreR } = terrain;
    const count = fine.height * fine.width;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < fine.height; i += 1) {
      for (let j = 0; j < fine.width; j += 1) {
        const k = (i * fine.width + j) * 3;
        positions[k] = j / SUBDIVISIONS - centreC;
        positions[k + 1] = yOf(fine.values[i * fine.width + j]);
        positions[k + 2] = i / SUBDIVISIONS - centreR;
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
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    terrain.mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0 }));
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
    world.add(new THREE.Mesh(skirtGeometry, new THREE.MeshBasicMaterial({ color: 0x0a2230, side: THREE.DoubleSide })));

    const lines = [];
    for (const [a, b] of pane.isobaths) lines.push(toWorld(a[0], a[1], 0.03), toWorld(b[0], b[1], 0.03));
    terrain.contours = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(lines),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.16 }),
    );
    world.add(terrain.contours);
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
      colour.setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace);
      colours.setXYZ(n, colour.r, colour.g, colour.b);
    }
    colours.needsUpdate = true;
  }

  function updateColours() {
    const pane = abyssPane();
    if (!pane?.mission || !terrain) return;
    const grid = overlayGrid(pane, pane.mission);
    if (colourKey === (grid || "terrain")) return;
    colourKey = grid || "terrain";
    recolour(grid, !grid ? seafloorRamp : app.layer === "hidden" ? HIDDEN_RAMP : BELIEF_RAMP);
    if (grid) {
      const [low, high] = gridExtent(grid);
      legend.textContent = `${LAYER_LABELS[app.layer]}: ${low.toFixed(2)} (dark) to ${high.toFixed(2)} (bright)`;
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
    return new THREE.Mesh(new THREE.TubeGeometry(new Polyline(points), Math.min(points.length * 2, 1500), 0.07, 5, false), material);
  }

  function buildView(pane, index) {
    const color = new THREE.Color(pane.color).getHex();
    const view = {
      pane,
      index,
      color,
      vehicle: buildVehicle(color, pane.entry.label),
      trailMaterial: new THREE.MeshBasicMaterial({ color }),
      completed: new THREE.Group(),
      markers: new THREE.Group(),
      current: null,
      completedCount: -1,
      feedKey: null,
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
    hud.append(card);
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

    const ring = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const found = new THREE.MeshStandardMaterial({ color: view.color, emissive: view.color, emissiveIntensity: 0.55 });
    const empty = new THREE.MeshStandardMaterial({ color: NO_FINDS_COLOR, roughness: 0.8 });
    for (const { step } of mission.completed) {
      if (!step.observation) continue;
      const [r, c] = step.observation.waypoint;
      const richness = step.observation.richness;
      const radius = richness ? 0.13 + Math.sqrt(richness) * 0.09 : 0.09;
      const marker = new THREE.Mesh(new THREE.SphereGeometry(radius, 14, 10), richness ? found.clone() : empty.clone());
      marker.position.copy(toWorld(r, c, radius + 0.06));
      view.markers.add(marker);
      if (step.new_discoveries.length) {
        const halo = new THREE.Mesh(new THREE.TorusGeometry(radius + 0.16, 0.022, 8, 28), ring.clone());
        halo.rotation.x = Math.PI / 2;
        halo.position.copy(marker.position);
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
    // Pull back on narrow screens so the whole block fits.
    const fit = Math.max(1, 1.75 / camera.aspect) ** 0.6;
    camera.position.set(-5 * fit, 25 * fit, 35 * fit);
    controls.target.set(0, -1, 1);
    controls.update();
  }

  function setFollow(index) {
    followIndex = index;
    controls.enabled = index < 0;
    cameraSelect.value = String(index);
    if (index < 0) resetCamera();
  }

  function buildSnow() {
    const positions = new Float32Array(SNOW_COUNT * 3);
    for (let n = 0; n < SNOW_COUNT; n += 1) {
      positions[n * 3] = (Math.random() - 0.5) * 44;
      positions[n * 3 + 1] = Math.random() * 26 - 10;
      positions[n * 3 + 2] = (Math.random() - 0.5) * 44;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    snow = new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xd5ecf7,
      size: 0.055,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    }));
    scene.add(snow);
  }

  function updateVehicle(view, time, delta) {
    const { pane, vehicle } = view;
    const { mission } = pane;
    if (!mission) return;
    if (mission.completed.length !== view.completedCount) rebuildCompleted(view);

    const [r, c] = mission.position;
    const position = toWorld(r, c, ALTITUDE);
    const dx = position.x - vehicle.position.x;
    const dz = position.z - vehicle.position.z;
    if (dx * dx + dz * dz > 1e-5) {
      const desired = Math.atan2(dx, dz);
      let turn = desired - view.heading;
      turn = Math.atan2(Math.sin(turn), Math.cos(turn));
      view.heading += turn * Math.min(1, delta * 8);
    }
    vehicle.position.copy(position);
    if (!reducedMotion) vehicle.position.y += Math.sin(time * 1.4 + view.index) * 0.035;
    vehicle.rotation.y = view.heading;

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
    const { vehicle, heading } = { vehicle: view.vehicle, heading: view.heading };
    const behind = new THREE.Vector3(-Math.sin(heading) * 9, 4.5, -Math.cos(heading) * 9);
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
    camera.updateProjectionMatrix();
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
      if (followIndex >= 0) updateFollowCamera(delta);
      else controls.update();
    }
    if (snow && !reducedMotion) {
      const positions = snow.geometry.getAttribute("position");
      for (let n = 0; n < SNOW_COUNT; n += 1) {
        let y = positions.getY(n) - delta * 0.12;
        if (y < -10) y = 16;
        positions.setY(n, y);
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
    disposeGroup(world);
    hud.replaceChildren();
    views = [];
    colourKey = null;
    if (!app.panes.length) return;
    terrain = terrainData(app.panes[0].log);
    buildTerrain(app.panes[0]);
    views = app.panes.map(buildView);
    if (followIndex >= views.length) followIndex = -1;
    updateCameraOptions();
    views.forEach((view) => { view.vehicle.position.copy(toWorld(...view.pane.log.terrain.home, ALTITUDE)); });
    const home = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.26, 0.5),
      new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.5 }),
    );
    home.position.copy(toWorld(...app.panes[0].log.terrain.home, 0.14));
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
