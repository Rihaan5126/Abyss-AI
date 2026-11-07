"use strict";

// Replays executed mission logs. It draws what the logs record and never computes
// scientific results of its own. Route interpolation between recorded cells is visual only.
// Both panels share one clock in energy units, so they are always compared at equal spend.
// Reveal files hold the simulator's hidden truth. They are not fetched until the viewer
// requests the findings report, and the hidden world is never drawn on the map.

const PANE_COLORS = ["#ff9d76", "#5ef2d6"];
// The committed GEBCO crop's position, from data/gebco/monterey_canyon_30x30.json.
const GEBCO_CROP = { west: -122.0625, north: 36.754167, cellsPerDegree: 240 };
const CAPTION_MS = 6500;
const SUMMARY_DELAY_MS = 2600;
const ISOBATH_STEP_M = 250;
const SCENARIO_NAMES = {
  random: "Independent random",
  clustered: "Spatial clusters",
  ridge: "Ridge-associated",
  reversed: "Flat-associated (reversed)",
  nonlinear: "Nonlinear mixed",
};
const TERRAIN_NAMES = {
  gebco_2025: "Real bathymetry: GEBCO 2025, Monterey Canyon area, 30 x 30 planning grid.",
  synthetic: "Synthetic procedural terrain.",
};
// Extra demo landforms from abyss/landforms.py. Illustrative shapes, not real places.
const LANDFORM_NAMES = {
  synthetic_seamount: "Seamount",
  synthetic_abyssal_hills: "Abyssal hills",
  synthetic_trench: "Trench",
  synthetic_basin: "Basin",
};
for (const [source, name] of Object.entries(LANDFORM_NAMES)) {
  TERRAIN_NAMES[source] = `Synthetic landform: ${name.toLowerCase()}. Not a real place, and not part of the benchmark.`;
}
const PERCEPTION_NAMES = {
  ideal: "Ideal perception: labels come directly from the simulator.",
  stub: "Stub perception: a fake model with made-up error rates.",
};
const GEBCO_CREDIT =" GEBCO Compilation Group (2025) GEBCO 2025 Grid (doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29).";
// Differ in lightness as well as hue, and each class is also named in the legend.
const HABITAT_COLOURS = [[214, 226, 190], [255, 139, 120], [96, 66, 190], [48, 176, 186], [168, 206, 255]];
const LAYER_LABELS = {
  habitat: "Habitat classes",
  predicted_richness: "Predicted richness",
  discovery_proxy: "Rare-habitat discovery clues (proxy, not unseen-species count)",
  uncertainty: "Model uncertainty",
  hidden: "Hidden expected richness (simulated)",
};
const UTILITY_LABELS = {
  expected_richness: "Predicted richness",
  information_gain: "Information gain",
  coverage: "Coverage incentive",
  energy_cost: "Energy cost",
  utility: "Utility",
  candidates: "Safe targets considered",
  discovery_proxy: "Rare-habitat discovery proxy",
  habitat_coverage: "Habitat coverage incentive",
  exploration_bonus: "Exploration bonus",
  route_score: "Planned route value per energy",
  planned_stops: "Provisional survey stops",
  planned_energy: "Planned travel and survey energy",
  warmup: "Initial habitat sampling (1 = yes)",
};

const $ = (id) => document.getElementById(id);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const fmt = (v, digits = 1) => Number(v).toFixed(digits);

const app = {
  entries: [],
  view: "2d",
  explorer: null,
  worldId: null,
  panes: [],
  energy: 0,
  maxEnergy: 150,
  budget: 150,
  playing: false,
  revealed: false,
  layer: "terrain",
  lastFrame: 0,
  loadToken: 0,
  tourIndex: -1,
  sequence: null,
  captionTimer: 0,
  summaryTimer: 0,
  manifestNotice: "",
  imageCredits: {},
  benchmark: null,
};

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function showNotice(message, isError = false) {
  const notice = $("notice");
  notice.textContent = message;
  notice.hidden = !message;
  notice.classList.toggle("error", isError);
}

// Timeline -------------------------------------------------------------------

function buildTimeline(log) {
  let energy = 0;
  return log.steps.map((step) => {
    const start = energy;
    const arrive = start + step.energy_travel;
    const end = step.cumulative.energy_used;
    energy = end;
    return { step, start, arrive, end };
  });
}

function missionAt(pane, energy) {
  const completed = [];
  let current = null;
  for (const segment of pane.timeline) {
    if (segment.end <= energy + 1e-6) completed.push(segment);
    else { current = segment; break; }
  }
  const home = pane.log.terrain.home;
  const last = completed[completed.length - 1];
  let position = last ? last.step.position : home;
  const trail = completed.flatMap((s) => s.step.route);
  let phase = last ? "idle" : "start";

  if (current && energy > current.start) {
    const route = current.step.route;
    const travel = current.arrive - current.start;
    const progress = travel > 0 ? clamp((energy - current.start) / travel, 0, 1) : 1;
    const along = progress * (route.length - 1);
    const index = Math.floor(along);
    const a = route[index];
    const b = route[Math.min(index + 1, route.length - 1)];
    const f = along - index;
    position = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
    trail.push(...route.slice(0, index + 1), position);
    phase = progress < 1 ? "travel" : "survey";
  }
  if (!current) phase = "done";
  return { completed, current, position, trail, phase };
}

// Colour ---------------------------------------------------------------------

function ramp(stops) {
  return (t) => {
    const x = clamp(t, 0, 1) * (stops.length - 1);
    const i = Math.min(Math.floor(x), stops.length - 2);
    const f = x - i;
    return stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  };
}

const DEPTH_RAMP = ramp([[158, 214, 214], [76, 158, 180], [38, 100, 156], [28, 56, 118], [14, 20, 66]]);
const BELIEF_RAMP = ramp([[10, 14, 48], [32, 52, 132], [28, 136, 168], [112, 232, 206], [236, 255, 236]]);
const HIDDEN_RAMP = ramp([[22, 8, 46], [88, 20, 112], [176, 40, 132], [250, 110, 132], [255, 222, 192]]);

function gridExtent(grid) {
  const values = grid.flat();
  return [Math.min(...values), Math.max(...values)];
}

function fieldImage(grid, color, shade) {
  const rows = grid.length;
  const cols = grid[0].length;
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(cols, rows);
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const rgb = color(grid[r][c]);
      const light = shade ? shade(r, c) : 1;
      const i = (r * cols + c) * 4;
      image.data[i] = clamp(rgb[0] * light, 0, 255);
      image.data[i + 1] = clamp(rgb[1] * light, 0, 255);
      image.data[i + 2] = clamp(rgb[2] * light, 0, 255);
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas;
}

function terrainImage(terrain) {
  const depth = terrain.depth_m;
  const [lo, hi] = gridExtent(depth);
  const rows = depth.length;
  const cols = depth[0].length;
  const at = (r, c) => depth[clamp(r, 0, rows - 1)][clamp(c, 0, cols - 1)];
  // Hillshade lit from the north-west. Elevation is the negative of depth.
  const shade = (r, c) => {
    const dx = -(at(r, c + 1) - at(r, c - 1));
    const dy = -(at(r + 1, c) - at(r - 1, c));
    return clamp(1 + (dy - dx) / (0.35 * (hi - lo || 1)), 0.6, 1.5);
  };
  return fieldImage(depth, (d) => DEPTH_RAMP((d - lo) / (hi - lo || 1)), shade);
}

function isobaths(depth) {
  const [lo, hi] = gridExtent(depth);
  const segments = [];
  const first = Math.ceil(lo / ISOBATH_STEP_M) * ISOBATH_STEP_M;
  for (let level = first; level <= hi; level += ISOBATH_STEP_M) {
    for (let r = 0; r < depth.length - 1; r += 1) {
      for (let c = 0; c < depth[0].length - 1; c += 1) {
        const corners = [[r, c], [r, c + 1], [r + 1, c + 1], [r + 1, c]];
        const points = [];
        corners.forEach((a, k) => {
          const b = corners[(k + 1) % 4];
          const va = depth[a[0]][a[1]];
          const vb = depth[b[0]][b[1]];
          if ((va < level) !== (vb < level)) {
            const f = (level - va) / (vb - va);
            points.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]);
          }
        });
        if (points.length >= 2) segments.push([points[0], points[1]]);
        if (points.length === 4) segments.push([points[2], points[3]]);
      }
    }
  }
  return segments;
}

// Map ------------------------------------------------------------------------

function sizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}

function latestDiagnostics(mission) {
  for (let i = mission.completed.length - 1; i >= 0; i -= 1) {
    const diagnostics = mission.completed[i].step.planner_diagnostics;
    if (diagnostics && Object.keys(diagnostics).length) return diagnostics;
  }
  return {};
}

function overlayGrid(pane, mission) {
  if (app.layer === "hidden") return app.revealed ? pane.reveal.expected_richness_map : null;
  if (app.layer === "terrain") return null;
  if (app.layer === "habitat") return pane.log.terrain.habitat?.classes || null;
  return latestDiagnostics(mission)[app.layer] || null;
}

function drawMap(pane, mission) {
  const { ctx, width } = sizeCanvas(pane.el.map);
  const [rows, cols] = pane.log.terrain.shape;
  const cell = width / cols;
  const toXY = ([r, c]) => [(c + 0.5) * cell, (r + 0.5) * cell];

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(pane.terrainImage, 0, 0, width, rows * cell);

  const grid = overlayGrid(pane, mission);
  let legend = "";
  const isHabitat = app.layer === "habitat" && grid;
  if (isHabitat) {
    // Classes are categories, so they are drawn without blending between neighbours.
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(fieldImage(grid, (v) => HABITAT_COLOURS[v]), 0, 0, width, rows * cell);
    ctx.imageSmoothingEnabled = true;
    fillHabitatLegend(pane.el.legend, pane.log.terrain.habitat.names);
  } else if (grid) {
    const [lo, hi] = gridExtent(grid);
    const color = app.layer === "hidden" ? HIDDEN_RAMP : BELIEF_RAMP;
    const span = hi - lo || 1;
    ctx.drawImage(fieldImage(grid, (v) => color((v - lo) / span)), 0, 0, width, rows * cell);
    legend = `${LAYER_LABELS[app.layer]}: ${fmt(lo, 2)} (dark) to ${fmt(hi, 2)} (bright)`;
  } else if (app.layer === "terrain") {
    const [lo, hi] = gridExtent(pane.log.terrain.depth_m);
    legend = `Depth ${Math.round(lo)} to ${Math.round(hi)} m. Lines every ${ISOBATH_STEP_M} m. North is up.`;
  } else if (pane.timeline.some((s) => s.step.planner_diagnostics?.[app.layer])) {
    legend = `${LAYER_LABELS[app.layer]}: no data yet. The first survey hasn't finished.`;
  } else {
    legend = `${LAYER_LABELS[app.layer] || "Layer"}: this planner has no model, so it logs no map.`;
  }
  if (!isHabitat) pane.el.legend.textContent = legend;

  ctx.lineWidth = 0.8;
  ctx.strokeStyle = grid ? "rgba(0,0,0,.28)" : "rgba(230,250,255,.24)";
  ctx.beginPath();
  for (const [a, b] of pane.isobaths) {
    const [x1, y1] = toXY(a);
    const [x2, y2] = toXY(b);
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }
  ctx.stroke();

  const color = pane.color;
  const line = (points, stroke, lineWidth) => {
    if (points.length < 2) return;
    ctx.beginPath();
    points.forEach((p, i) => {
      const [x, y] = toXY(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.lineJoin = "round";
    ctx.stroke();
  };
  line(mission.trail, "rgba(4,10,18,.75)", 3.5);
  line(mission.trail, color, 1.6);

  if (mission.current && mission.current.step.observation) {
    const target = mission.current.step.route[mission.current.step.route.length - 1];
    const [tx, ty] = toXY(target);
    const [rx, ry] = toXY(mission.position);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(rx, ry);
    ctx.lineTo(tx, ty);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(tx, ty, Math.max(5, cell * 0.45), 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  for (const { step } of mission.completed) {
    if (!step.observation) continue;
    const [x, y] = toXY(step.observation.waypoint);
    const richness = step.observation.richness;
    const radius = richness ? 2.5 + Math.sqrt(richness) * 1.8 : 2.2;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "rgba(4,10,18,.9)";
    ctx.fillStyle = richness ? color : "rgba(4,10,18,.75)";
    ctx.fill();
    ctx.stroke();
    if (step.new_discoveries.length) {
      ctx.beginPath();
      ctx.arc(x, y, radius + 2.5, 0, Math.PI * 2);
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
  }

  const [hx, hy] = toXY(pane.log.terrain.home);
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "#04101c";
  ctx.lineWidth = 1.5;
  ctx.fillRect(hx - 5, hy - 5, 10, 10);
  ctx.strokeRect(hx - 5, hy - 5, 10, 10);

  const [px, py] = toXY(mission.position);
  ctx.beginPath();
  ctx.arc(px, py, 6.5, 0, Math.PI * 2);
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = color;
  ctx.stroke();
}

// Panel text -----------------------------------------------------------------

const STATUS_TEXT = {
  start: "At home station",
  idle: "Choosing target",
  travel: "Travelling",
  survey: "Surveying",
  done: "Home safely",
};

function updatePaneText(pane, mission) {
  const { el, log, reveal } = pane;
  const last = mission.completed[mission.completed.length - 1];
  let found = last ? last.step.cumulative.distinct_categories : 0;
  const isReal = log.provenance.perception !== "ideal";
  if (app.revealed && isReal) {
    // After the reveal, score against the true labels rather than the model's predictions.
    const lastStep = last ? last.step.step : 0;
    const seen = reveal.true_observations.filter((o) => o.step <= lastStep).flatMap((o) => o.categories);
    found = new Set(seen).size;
  }
  el.foundLabel.textContent = !isReal ? "Categories found" : app.revealed ? "True categories found" : "Categories perceived";
  el.unknownStat.hidden = !isReal;
  el.unknown.textContent = last ? last.step.cumulative.unknown_encounters : 0;
  const surveys = last ? last.step.cumulative.surveys : 0;
  const used = last ? last.step.cumulative.energy_used : 0;
  const budget = log.energy.budget;
  const shown = Math.min(app.energy, log.outcome.energy_used);

  el.found.textContent = found;
  if (app.revealed) {
    const small = document.createElement("small");
    small.textContent = ` of ${reveal.categories_available_count}`;
    el.found.append(small);
  }
  el.surveys.textContent = surveys;
  const lastSurvey = mission.completed.filter((s) => s.step.observation).at(-1);
  const classCount = log.terrain.habitat?.names.length || 0;
  el.habitats.textContent = `${lastSurvey?.step.observation.habitat?.classes_sampled || 0} of ${classCount}`;
  el.left.textContent = fmt(budget - Math.max(used, shown));
  el.energyBar.style.width = `${(100 * (budget - shown)) / budget}%`;
  el.reserve.style.width = `${(100 * log.energy.reserve) / budget}%`;

  let status = STATUS_TEXT[mission.phase];
  if (mission.phase === "done") {
    status = log.outcome.safe_return ? STATUS_TEXT.done : "Return not verified";
    if (log.outcome.forced_return) status += " (target rejected)";
  }
  el.status.textContent = status;

  const logged = mission.current ? mission.current.step.planner_diagnostics?.target_utility : null;
  const utility = logged && Object.keys(logged).length ? logged : null;
  el.why.hidden = !utility;
  if (utility) {
    el.why.replaceChildren();
    const title = document.createElement("summary");
    title.textContent = "The numbers behind this choice";
    el.why.append(title);
    for (const [key, value] of Object.entries(utility)) {
      const row = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = key === "information_gain" && pane.entry.planner.startsWith("abyss-discovery")
        ? "Uncertainty score" : UTILITY_LABELS[key] || key;
      const number = document.createElement("span");
      number.textContent = Array.isArray(value) ? value.map(cell => `(${cell.join(", ")})`).join(" → ") : fmt(value, 3);
      row.append(name, number);
      el.why.append(row);
    }
  }
}

// Plain-English story ----------------------------------------------------------
// Turns the logged mission into short sentences for viewers with no background.
// Every fact comes from the public mission log; nothing here reads hidden data.

const STORY_HOLD_MS = 4000;
const STRATEGY_TEXT = {
  frontier: "This robot doesn't learn. It simply moves to the nearest unexplored spot next to where it has already been.",
  lawnmower: "This robot doesn't learn. It follows a back-and-forth pattern planned before the dive, like mowing a lawn.",
  heuristic: "This robot doesn't learn. It always heads for steep ground, a fixed rule it never changes.",
  random: "This robot doesn't learn. It picks a random spot it can reach.",
  "abyss-nolearn": "This is ABYSS with learning switched off, so its guesses never improve.",
  "abyss-noinfo": "This is ABYSS without its curiosity bonus: it learns, but never goes somewhere just to find out.",
};

function depthWords(m) {
  if (m < 400) return "shallow";
  if (m < 1000) return "mid-depth";
  return "deep";
}

function slopeWords(deg) {
  if (deg < 3) return "flat";
  if (deg < 8) return "gently sloping";
  return "steep";
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

// ABYSS's current guess, in words. Weights are on standardised features; small ones are
// treated as "no clear pattern". This describes a model, not a proven cause.
function guessWords(model) {
  if (!model || !model.observations) return "It hasn't surveyed anywhere yet, so it has no idea where life is.";
  if (model.kind) {
    const mix = model.mixture || {};
    const strongest = Object.entries(mix).sort((a, b) => b[1] - a[1])[0]?.[0];
    const pattern = strongest === "terrain" ? "similar seafloor habitats" : strongest === "spatial" ? "nearby patches" : "the overall sighting rate";
    return `After ${plural(model.observations, "survey", "surveys")}, it models ${plural(model.categories_modelled, "observed category", "observed categories")}. Its predictions currently give most weight to ${pattern}. Rare sightings provide clues to further discoveries; they don't identify animals it has never seen.`;
  }
  const w = model.weights || {};
  const parts = [];
  if (Math.abs(w.slope || 0) > 0.15) parts.push(w.slope > 0 ? "steeper ground" : "flatter ground");
  if (Math.abs(w.depth || 0) > 0.15) parts.push(w.depth > 0 ? "deeper water" : "shallower water");
  const after = `After ${plural(model.observations, "survey", "surveys")}`;
  if (!parts.length) return `${after}, it hasn't spotted a clear pattern yet.`;
  return `${after}, its best guess is that ${parts.join(" and ")} ${parts.length > 1 ? "have" : "has"} more life. It will change its mind if new surveys disagree.`;
}

function reasonWords(utility) {
  if (utility.discovery_proxy !== undefined) {
    const stops = utility.planned_stops?.length || 1;
    return `${utility.warmup ? "It is sampling different habitats to learn early. " : ""}It favours habitats associated with less frequent sightings (discovery proxy ${fmt(utility.discovery_proxy, 2)}), balanced against uncertainty and energy. It compared routes of up to ${stops} stop${stops === 1 ? "" : "s"}; only the first stop is committed before observing again. This stop costs ${fmt(utility.energy_cost)} energy, with the return reserve protected.`;
  }
  const reasons = [];
  const expected = Math.max(0, utility.expected_richness);
  reasons.push(expected < 0.3
    ? "It doesn't expect much life there"
    : `It expects about ${expected.toFixed(1)} kinds of creature there`);
  if (utility.information_gain >= 0.25) reasons.push("it's still unsure what lives on that kind of ground, so checking will teach it something");
  if (utility.coverage >= 0.99) reasons.push("it's away from everywhere it has already checked");
  const trip = `Getting there and checking it costs ${utility.energy_cost.toFixed(1)} energy.`;
  return `${reasons.join(", and ")}. ${trip}`;
}

function storyFor(pane, mission) {
  const { log } = pane;
  const surveys = mission.completed.filter((s) => s.step.observation);
  const last = surveys.at(-1)?.step;
  const isAbyss = pane.entry.planner === "abyss" || pane.entry.planner.startsWith("abyss-discovery");
  const found = mission.completed.at(-1)?.step.cumulative.distinct_categories || 0;
  const story = { kicker: "", headline: "", lines: [], priority: 0 };

  if (mission.phase === "done") {
    story.kicker = "Mission over";
    story.headline = log.outcome.safe_return ? "Back home safely" : "Mission ended";
    const verb = log.provenance.perception !== "ideal" ? "reported" : "found";
    story.lines.push(`It made ${plural(surveys.length, "survey", "surveys")} and ${verb} ${plural(found, "kind", "kinds")} of creature.`);
    return story;
  }
  if (!last) {
    story.kicker = "Starting out";
    story.headline = "Setting off";
    story.lines.push("It knows the shape of the seafloor, but not what lives there.");
  } else {
    const obs = last.observation;
    const [r, c] = obs.waypoint;
    const depth = Math.round(log.terrain.depth_m[r][c]);
    const where = `${slopeWords(log.terrain.slope_deg[r][c])}, ${depthWords(depth)} seabed, ${depth} m down`;
    const fresh = last.new_discoveries.length;
    const seen = new Set(obs.categories).size;
    const unfamiliar = obs.unknown_flags.filter(Boolean).length;
    // With real perception, these are the model's labels and may be wrong.
    const isReal = log.provenance.perception !== "ideal";
    story.kicker = `Survey ${surveys.length}`;
    if (fresh) {
      story.headline = `${isReal ? "Reported" : "Found"} ${plural(fresh, "new kind", "new kinds")} of creature!`;
      story.priority = 1;
    } else if (unfamiliar) {
      story.headline = "Something unfamiliar to its references";
      story.priority = 1;
    } else if (seen) {
      story.headline = isReal ? "Only labels it had already reported" : "Only creatures it had already seen";
    } else {
      story.headline = "No organisms in this survey";
    }
    story.lines.push(`It checked a patch of ${where}.`);
    if (unfamiliar) {
      story.lines.push(`The image model flagged ${plural(unfamiliar, "image", "images")} as unfamiliar. That does not mean a new species.`);
    }
    story.lines.push(`So far it has ${isReal ? "reported" : "found"} ${plural(found, "different kind", "different kinds")} of creature.`);
  }

  if (isAbyss) {
    const utility = mission.current?.step.planner_diagnostics?.target_utility;
    if (utility && Object.keys(utility).length && mission.phase !== "done") {
      story.why = reasonWords(utility);
    }
    const model = (mission.completed.at(-1)?.step || mission.current?.step)?.planner_diagnostics?.model;
    story.guess = guessWords(model);
  } else {
    story.why = STRATEGY_TEXT[pane.entry.planner] || "This robot follows a fixed plan and doesn't learn.";
  }
  return story;
}

function renderStory(pane, story) {
  const box = pane.el.story;
  const kicker = document.createElement("p");
  kicker.className = "story-kicker";
  kicker.textContent = story.kicker;
  const headline = document.createElement("h3");
  headline.className = story.priority ? "story-headline new" : "story-headline";
  headline.textContent = story.headline;
  const parts = [kicker, headline];
  for (const text of story.lines) {
    const line = document.createElement("p");
    line.textContent = text;
    parts.push(line);
  }
  if (story.why) {
    const label = document.createElement("p");
    label.className = "story-label";
    label.textContent = pane.entry.planner.startsWith("abyss") ? "Why it chose its next spot" : "How it decides";
    const why = document.createElement("p");
    why.textContent = story.why;
    parts.push(label, why);
  }
  if (story.guess) {
    const label = document.createElement("p");
    label.className = "story-label";
    label.textContent = "What it has guessed so far";
    const guess = document.createElement("p");
    guess.textContent = story.guess;
    parts.push(label, guess);
  }
  box.replaceChildren(...parts);
  box.classList.remove("fresh");
  void box.offsetWidth; // restart the fade-in
  box.classList.add("fresh");
}

// Each message stays up long enough to read. New discoveries, pausing and scrubbing skip
// the wait, so the story never falls behind what the viewer chose to look at.
function updateStory(pane, mission) {
  const story = storyFor(pane, mission);
  const key = [story.kicker, story.headline, story.why, story.guess].join("|");
  const state = pane.storyState || (pane.storyState = { key: null, shownAt: 0 });
  if (key === state.key) return;
  const now = performance.now();
  const waited = now - state.shownAt >= STORY_HOLD_MS;
  if (state.key && app.playing && !waited && !story.priority) return;
  state.key = key;
  state.shownAt = now;
  renderStory(pane, story);
}

function readout(pane, cell) {
  if (!cell) {
    pane.el.readout.textContent = "Hover over the map to inspect a cell.";
    return;
  }
  const [r, c] = cell;
  const terrain = pane.log.terrain;
  const parts = [
    `(${r}, ${c})`,
    `${Math.round(terrain.depth_m[r][c])} m`,
    `slope ${fmt(terrain.slope_deg[r][c])}°`,
    `BPI ${Math.round(terrain.bpi_m[r][c])} m`,
    ...(terrain.habitat ? [terrain.habitat.names[terrain.habitat.classes[r][c]]] : []),
  ];
  if (app.revealed) {
    parts.push(`hidden: ${pane.reveal.encounter_richness_map[r][c]} categories here`);
  }
  pane.el.readout.textContent = parts.join("  |  ");
}

function habitatChip(obs) {
  if (!obs.habitat) return null;
  const chip = document.createElement("span");
  const unfamiliar = obs.unknown_flags.some(Boolean);
  chip.className = obs.habitat.new_class ? "chip habitat-new" : "chip habitat";
  chip.textContent = obs.habitat.new_class
    ? `New habitat class: ${obs.habitat.name}${unfamiliar ? ", with an unfamiliar organism" : ""}`
    : `Habitat: ${obs.habitat.name}`;
  return chip;
}

function fillHabitatLegend(element, names) {
  const keys = names.map((name, index) => {
    const key = document.createElement("span");
    key.className = "habitat-key";
    const swatch = document.createElement("i");
    swatch.style.background = `rgb(${HABITAT_COLOURS[index].join(",")})`;
    key.append(swatch, name);
    return key;
  });
  element.replaceChildren(...keys);
}

function categoryLabel(name) {
  return name.replace("category_", "Cat ");
}

function renderFeed(pane, mission) {
  const surveys = mission.completed.filter((s) => s.step.observation);
  if (pane.feedCount === surveys.length) return;
  pane.feedCount = surveys.length;
  const items = surveys.slice().reverse().map(({ step, end }) => {
    const item = document.createElement("li");
    const obs = step.observation;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `Energy ${fmt(end)} at (${obs.waypoint[0]}, ${obs.waypoint[1]})`;
    item.append(meta);
    const inspect = document.createElement("button");
    inspect.textContent = "Inspect observation";
    inspect.onclick = () => app.inspector?.open(pane, step.step);
    item.append(inspect);
    if (!obs.categories.length && !obs.image_refs.length) {
      const none = document.createElement("span");
      none.className = "none";
      none.textContent = "No organisms in this survey";
      item.append(none);
    }
    for (const category of obs.categories) {
      const chip = document.createElement("span");
      const isNew = step.new_discoveries.includes(category);
      chip.className = isNew ? "chip new" : "chip";
      chip.textContent = isNew ? `New: ${categoryLabel(category)}` : categoryLabel(category);
      item.append(chip);
    }
    obs.unknown_flags.forEach((unknown, index) => {
      if (!unknown) return;
      const chip = document.createElement("span");
      chip.className = "chip unknown";
      chip.textContent = `Unfamiliar, novelty ${fmt(obs.novelty_scores[index], 2)}`;
      item.append(chip);
    });
    const habitat = habitatChip(obs);
    if (habitat) item.append(habitat);
    for (const [imageIndex, ref] of obs.image_refs.entries()) {
      if (ref.includes("://")) continue; // opaque IDs, not image URLs
      const image = document.createElement("img");
      image.addEventListener("error", () => image.remove());
      image.src = ref;
      image.alt = "Marine image used as a simulated camera encounter";
      image.tabIndex = 0;
      image.style.cursor = "pointer";
      image.onclick = () => app.inspector?.open(pane, step.step, imageIndex);
      image.onkeydown = event => { if (event.key === "Enter") image.click(); };
      item.append(image);
    }
    return item;
  });
  pane.el.feedList.replaceChildren(...items);
}

// Chart ----------------------------------------------------------------------

function drawChart() {
  const canvas = $("chart");
  const { ctx, width, height } = sizeCanvas(canvas);
  const margin = { left: 34, right: 16, top: 10, bottom: 34 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  ctx.clearRect(0, 0, width, height);
  if (!app.panes.length) return;

  const available = app.revealed ? Math.max(...app.panes.map((p) => p.reveal.categories_available_count)) : 0;
  const finals = app.panes.map((p) => p.log.outcome.distinct_categories);
  const yMax = Math.max(4, available, ...finals);
  const x = (e) => margin.left + (e / app.budget) * plotW;
  const y = (v) => margin.top + plotH - (v / yMax) * plotH;

  ctx.font = "11px 'Plex Mono', Consolas, monospace";
  ctx.fillStyle = "#7c9aab";
  ctx.strokeStyle = "rgba(170,215,240,.14)";
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  const yStep = yMax > 10 ? 4 : 2;
  for (let v = 0; v <= yMax; v += yStep) {
    ctx.beginPath();
    ctx.moveTo(margin.left, y(v));
    ctx.lineTo(width - margin.right, y(v));
    ctx.stroke();
    ctx.fillText(String(v), margin.left - 6, y(v));
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let e = 0; e <= app.budget; e += 30) ctx.fillText(String(e), x(e), height - margin.bottom + 5);
  ctx.fillText("Energy used", margin.left + plotW / 2, height - 14);

  if (app.revealed) {
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "#ff8fb4";
    ctx.beginPath();
    ctx.moveTo(margin.left, y(available));
    ctx.lineTo(width - margin.right, y(available));
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = "#ffd0df";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText("In this world", margin.left + 6, y(available) + 3);
  }

  const labels = [];
  app.panes.forEach((pane) => {
    const mission = pane.mission;
    let value = 0;
    ctx.beginPath();
    ctx.moveTo(x(0), y(0));
    for (const segment of mission.completed) {
      ctx.lineTo(x(segment.end), y(value));
      value = segment.step.cumulative.distinct_categories;
      ctx.lineTo(x(segment.end), y(value));
    }
    const end = Math.min(app.energy, pane.log.outcome.energy_used);
    ctx.lineTo(x(end), y(value));
    ctx.strokeStyle = pane.color;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.stroke();
    labels.push({ px: x(end), py: y(value), text: pane.entry.label, color: pane.color });
  });

  labels.sort((a, b) => a.py - b.py);
  labels.forEach((label, i) => {
    if (i && label.py - labels[i - 1].py < 13) label.py = labels[i - 1].py + 13;
    ctx.fillStyle = label.color;
    const flip = label.px > width - 110;
    ctx.textAlign = flip ? "right" : "left";
    ctx.textBaseline = "bottom";
    ctx.fillText(label.text, label.px + (flip ? -4 : 4), label.py - 2);
  });
}

// Render loop ----------------------------------------------------------------

function render() {
  for (const pane of app.panes) {
    pane.mission = missionAt(pane, app.energy);
    if (app.view === "2d") drawMap(pane, pane.mission);
    updatePaneText(pane, pane.mission);
    updateStory(pane, pane.mission);
    renderFeed(pane, pane.mission);
  }
  drawChart();
  if (app.view === "3d") drawInset();
  app.explorer?.sync();
  $("scrub").value = app.energy;
  $("clock").textContent = `${fmt(app.energy)} / ${fmt(app.maxEnergy)} energy`;
}

function tick(now) {
  if (!app.playing) return;
  const elapsed = (now - app.lastFrame) / 1000;
  app.lastFrame = now;
  app.energy = Math.min(app.maxEnergy, app.energy + elapsed * Number($("speed").value));
  if (app.energy >= app.maxEnergy) setPlaying(false);
  render();
  if (app.sequence) advanceSequence();
  if (app.playing) requestAnimationFrame(tick);
}

function setPlaying(playing) {
  if (playing && app.energy >= app.maxEnergy) app.energy = 0;
  app.playing = playing;
  $("play").textContent = playing ? "Pause" : "Play";
  if (playing) {
    app.lastFrame = performance.now();
    requestAnimationFrame(tick);
  }
}

function jumpEvent(direction) {
  cancelSequence();
  setPlaying(false);
  const events = app.panes.flatMap((p) => p.timeline.map((s) => s.end)).sort((a, b) => a - b);
  const target = direction > 0
    ? events.find((e) => e > app.energy + 1e-6)
    : events.reverse().find((e) => e < app.energy - 1e-6);
  app.energy = target === undefined ? (direction > 0 ? app.maxEnergy : 0) : target;
  render();
}

// Loading --------------------------------------------------------------------

function worlds() {
  const seen = new Map();
  for (const entry of app.entries) if (!seen.has(entry.world_id)) seen.set(entry.world_id, entry);
  return [...seen.values()];
}

// Another hidden ocean of the same world type, chosen at random. Seeds were fixed when
// the logs were built and never picked by outcome; both robots always share the ocean.
function newOcean() {
  const current = worlds().find((w) => w.world_id === app.worldId);
  if (!current) return;
  const others = worlds().filter((w) => w.scenario === current.scenario && w.rho === current.rho && w.world_id !== app.worldId);
  if (!others.length) {
    showNotice("Only one ocean was built for this world type. Run: python -m scripts.build_ui_logs --oceans 8");
    return;
  }
  const next = others[Math.floor(Math.random() * others.length)];
  $("world").value = next.world_id;
  selectWorld(next.world_id);
  say(`A new hidden ocean: same seafloor, but the creatures now live in different places (seed ${next.seed}).`);
}

function createPane(index) {
  const node = $("pane-template").content.firstElementChild.cloneNode(true);
  node.style.setProperty("--pane-color", PANE_COLORS[index]);
  const feed = document.createElement("section");
  feed.className = "feed";
  feed.style.setProperty("--pane-color", PANE_COLORS[index]);
  const title = document.createElement("h2");
  const list = document.createElement("ol");
  feed.append(title, list);
  const el = {
    root: node,
    map: node.querySelector(".map"),
    planner: node.querySelector(".planner"),
    status: node.querySelector(".status"),
    readout: node.querySelector(".readout"),
    legend: node.querySelector(".legend"),
    found: node.querySelector(".found"),
    habitats: node.querySelector(".habitats"),
    foundLabel: node.querySelector(".found-label"),
    unknown: node.querySelector(".unknown-count"),
    unknownStat: node.querySelector(".unknown-stat"),
    surveys: node.querySelector(".surveys"),
    left: node.querySelector(".left"),
    energyBar: node.querySelector(".energy i"),
    reserve: node.querySelector(".energy b"),
    why: node.querySelector(".why"),
    story: node.querySelector(".story"),
    feed,
    feedTitle: title,
    feedList: list,
  };
  $("panes").append(node);
  $("feeds").append(feed);
  return el;
}

async function loadPane(pane, entry) {
  app.inspector?.close();
  const log = await getJson(entry.log);
  pane.entry = entry;
  pane.el.root.dataset.planner = entry.planner;
  pane.log = log;
  pane.reveal = null;
  pane.inferenceEvidence = null;
  pane.timeline = buildTimeline(log);
  pane.terrainImage = terrainImage(log.terrain);
  pane.isobaths = isobaths(log.terrain.depth_m);
  pane.feedCount = -1;
  pane.el.feedTitle.textContent = `${entry.label}: survey feed`;
}

async function fetchReveals() {
  await Promise.all(app.panes.map(async (pane) => {
    if (!pane.reveal) pane.reveal = await getJson(pane.entry.reveal);
  }));
}

function updateLayerControls() {
  const hasBelief = (key) => app.panes.some((pane) =>
    pane.timeline.some((s) => s.step.planner_diagnostics && s.step.planner_diagnostics[key]));
  for (const input of document.querySelectorAll('input[name="layer"]')) {
    if (input.value === "terrain" || input.value === "habitat") continue;
    input.disabled = input.value === "hidden" ? !app.revealed : !hasBelief(input.value);
    input.parentElement.title = input.disabled
      ? (input.value === "hidden" ? "Reveal the hidden world first" : "This mission's planner does not log this map")
      : "";
    if (input.disabled && input.checked) {
      document.querySelector('input[name="layer"][value="terrain"]').checked = true;
      app.layer = "terrain";
    }
  }
}

function updateClockRange() {
  app.budget = Math.max(...app.panes.map((p) => p.log.energy.budget));
  app.maxEnergy = Math.max(...app.panes.map((p) => p.log.outcome.energy_used));
  app.energy = Math.min(app.energy, app.maxEnergy);
  $("scrub").max = app.maxEnergy;
  buildTicks();
}

// Marks each logged discovery on the timeline, one row per robot.
function buildTicks() {
  const ticks = app.panes.flatMap((pane, index) => pane.timeline
    .filter((segment) => segment.step.new_discoveries.length)
    .map((segment) => {
      const tick = document.createElement("i");
      tick.className = index === 0 ? "top" : "bottom";
      tick.style.left = `${(100 * segment.end) / app.maxEnergy}%`;
      tick.style.setProperty("--c", pane.color);
      return tick;
    }));
  $("ticks").replaceChildren(...ticks);
}

function updateProvenance() {
  const log = app.panes[0].log;
  const source = log.provenance.terrain;
  const credit = source === "gebco_2025" ? GEBCO_CREDIT : "";
  const model = log.provenance.perception;
  $("provenance").textContent =
    `${TERRAIN_NAMES[source] || source}${credit} Biology is simulated, not observed. ` +
    `${PERCEPTION_NAMES[model] || `Perception model: ${model}.`} ` +
    "Energy is in abstract units. Every route and count comes from an executed mission log.";
  // Always say which perception made these results, so a fallback is never silent.
  const modeText = model === "ideal"
    ? "Ideal perception, no images"
    : model === "stub"
      ? "Stub perception: fake test model"
      : `Real images: ${String(model).split("@")[0].split("/").pop()}`;
  for (const id of ["mode-badge", "intro-mode"]) {
    $(id).textContent = modeText;
    $(id).title = `Perception model: ${model}`;
  }
  $("mode-badge").classList.toggle("real", model !== "ideal" && model !== "stub");
  const isReal = app.panes.some((p) => p.log.provenance.perception !== "ideal");
  $("chart-title").textContent = `Distinct categories ${isReal ? "perceived" : "found"} against energy used`;
  const stub = app.panes.some((p) => p.log.provenance.perception === "stub");
  if (stub) showNotice("Stub perception: a fake model for testing, with no real images. Not a vision result.");
  const landform = LANDFORM_NAMES[source];
  $("inset-caption").textContent = source === "gebco_2025"
    ? "GEBCO 2025 chart. Contours every 250 m."
    : `Synthetic ${landform ? landform.toLowerCase() : "terrain"}, not a real location.`;
  $("intro-place").textContent = source === "gebco_2025"
    ? "Monterey Canyon · 36°45′N 122°04′W"
    : landform ? `${landform} · synthetic seafloor` : "Synthetic seafloor";
}

// Nautical chart ---------------------------------------------------------------

function formatCoordinate(value, positive, negative) {
  const total = Math.round(Math.abs(value) * 60);
  const degrees = Math.floor(total / 60);
  return `${degrees}°${String(total - degrees * 60).padStart(2, "0")}′${value >= 0 ? positive : negative}`;
}

function drawChartBase(ctx, pane, size) {
  const terrain = pane.log.terrain;
  const [rows, cols] = terrain.shape;
  const cell = size / cols;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(pane.terrainImage, 0, 0, size, rows * cell);

  ctx.lineWidth = 0.6;
  ctx.strokeStyle = "rgba(235,250,255,.34)";
  ctx.beginPath();
  for (const [a, b] of pane.isobaths) {
    ctx.moveTo((a[1] + 0.5) * cell, (a[0] + 0.5) * cell);
    ctx.lineTo((b[1] + 0.5) * cell, (b[0] + 0.5) * cell);
  }
  ctx.stroke();
  if (pane.log.provenance.terrain !== "gebco_2025") return;

  // Graticule every three minutes of arc, positioned from the crop's real coordinates.
  const { west, north, cellsPerDegree } = GEBCO_CROP;
  const span = rows / cellsPerDegree;
  const stepDegrees = 3 / 60;
  ctx.font = "9px 'Plex Mono', Consolas, monospace";
  ctx.lineWidth = 0.5;
  for (let lat = Math.ceil((north - span) / stepDegrees) * stepDegrees; lat < north; lat += stepDegrees) {
    const y = (north - lat) * cellsPerDegree * cell;
    ctx.strokeStyle = "rgba(255,255,255,.2)";
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
    ctx.fillStyle = "rgba(235,250,255,.86)";
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.fillText(formatCoordinate(lat, "N", "S"), 3, y - 1);
  }
  for (let lon = Math.ceil(west / stepDegrees) * stepDegrees; lon < west + span; lon += stepDegrees) {
    const x = (lon - west) * cellsPerDegree * cell;
    ctx.strokeStyle = "rgba(255,255,255,.2)";
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, size);
    ctx.stroke();
    ctx.save();
    ctx.translate(x - 1, size - 3);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "rgba(235,250,255,.86)";
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.fillText(formatCoordinate(lon, "E", "W"), 0, 0);
    ctx.restore();
  }
}

function drawInset() {
  if (!app.panes.length) return;
  const canvas = $("inset-chart");
  const { ctx, width } = sizeCanvas(canvas);
  if (width < 2) return;
  drawChartBase(ctx, app.panes[0], width);
  const [, cols] = app.panes[0].log.terrain.shape;
  const cell = width / cols;
  const toXY = ([r, c]) => [(c + 0.5) * cell, (r + 0.5) * cell];

  for (const pane of app.panes) {
    const { mission } = pane;
    if (!mission) continue;
    if (mission.trail.length > 1) {
      ctx.beginPath();
      mission.trail.forEach((point, i) => {
        const [x, y] = toXY(point);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineJoin = "round";
      ctx.lineWidth = 2.6;
      ctx.strokeStyle = "rgba(2,8,16,.6)";
      ctx.stroke();
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = pane.color;
      ctx.stroke();
    }
    for (const { step } of mission.completed) {
      if (!step.new_discoveries.length) continue;
      const [x, y] = toXY(step.observation.waypoint);
      ctx.beginPath();
      ctx.arc(x, y, 1.9, 0, Math.PI * 2);
      ctx.fillStyle = "#fff";
      ctx.fill();
    }
    const [x, y] = toXY(mission.position);
    ctx.beginPath();
    ctx.arc(x, y, 3.4, 0, Math.PI * 2);
    ctx.fillStyle = pane.color;
    ctx.shadowColor = pane.color;
    ctx.shadowBlur = 8;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // North arrow
  const nx = width - 13;
  ctx.fillStyle = "rgba(245,252,255,.92)";
  ctx.beginPath();
  ctx.moveTo(nx, 7);
  ctx.lineTo(nx + 4, 18);
  ctx.lineTo(nx, 15);
  ctx.lineTo(nx - 4, 18);
  ctx.closePath();
  ctx.fill();
  ctx.font = "9px 'Plex Mono', Consolas, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText("N", nx, 20);
}

// Mission sequence -------------------------------------------------------------
// Sets the stage around the logged mission: its timing and camera work are presentation,
// and every position and count still comes from the logs.

function leaveTitle() {
  document.body.classList.remove("pre-dive");
  $("intro").classList.add("leaving");
  setTimeout(() => { $("intro").hidden = true; }, 800);
}

function say(text, duration = CAPTION_MS) {
  clearTimeout(app.captionTimer);
  $("caption").textContent = text;
  $("caption").hidden = !text;
  if (text && duration) app.captionTimer = setTimeout(() => { $("caption").hidden = true; }, duration);
}

function hideSummary() {
  clearTimeout(app.summaryTimer);
  $("summary").hidden = true;
}

function cancelSequence() {
  app.sequence = null;
  say("");
  hideSummary();
  document.body.classList.remove("diving");
  $("skip-dive").hidden = true;
  app.explorer?.endDive(false);
}

function homeDepth() {
  const { terrain } = app.panes[0].log;
  return Math.round(terrain.depth_m[terrain.home[0]][terrain.home[1]]);
}

async function beginDive() {
  if (!app.explorer || !app.panes.length) return;
  cancelSequence();
  exitTour();
  setPlaying(false);
  leaveTitle();
  setView("3d");
  setLayer("terrain");
  app.energy = 0;
  document.body.classList.add("diving");
  $("skip-dive").hidden = false;
  render();
  window.scrollTo(0, 0);
  say(`Descending to the home station at ${homeDepth()} m. This descent is illustrative.`, 0);
  app.explorer.dive(startExploring);
}

function startExploring() {
  document.body.classList.remove("diving");
  $("skip-dive").hidden = true;
  say("Two robots, the same terrain and the same energy. Neither knows what lives here.");
  const abyss = abyssPane();
  const line = abyss.timeline;
  app.sequence = {
    fired: new Set(),
    first: line.find((s) => s.step.new_discoveries.length) || null,
    belief: line[Math.min(5, Math.max(0, line.length - 2))],
    back: app.maxEnergy * 0.72,
  };
  setPlaying(true);
}

function advanceSequence() {
  const seq = app.sequence;
  const once = (key, condition, action) => {
    if (!seq.fired.has(key) && condition) {
      seq.fired.add(key);
      action();
    }
  };
  once("first", seq.first && app.energy >= seq.first.end, () => {
    say(`ABYSS logs its first discovery at energy ${fmt(seq.first.end)}, and its habitat model updates.`);
  });
  once("belief", seq.belief && app.energy >= seq.belief.start, () => {
    setLayer("predicted_richness");
    render();
    const discovery = abyssPane().entry.planner.startsWith("abyss-discovery");
    say(discovery
      ? "The map shows category occurrence estimates. Discovery favours rare-category habitats, checks short routes and replans after each survey."
      : "The seafloor now shows what ABYSS believes. Each target weighs predicted richness, uncertainty and coverage per unit of energy.", 8500);
  });
  once("back", app.energy >= seq.back, () => {
    setLayer("terrain");
    render();
    say("Each robot must always keep enough energy to get home.");
  });
  if (app.energy >= app.maxEnergy) finishMission();
}

function finishMission() {
  app.sequence = null;
  setLayer("terrain");
  render();
  app.explorer?.park();
  say("Both missions are over. Propellers stop, and lights go down.", SUMMARY_DELAY_MS);
  app.summaryTimer = setTimeout(showSummary, SUMMARY_DELAY_MS);
}

function showSummary() {
  const safe = app.panes.every((p) => p.log.outcome.safe_return);
  $("summary-title").textContent = safe
    ? "Both robots returned home safely."
    : "Check the return status of each robot.";
  const rows = app.panes.map((pane) => {
    const { outcome, energy, terrain } = pane.log;
    const isReal = pane.log.provenance.perception !== "ideal";
    const lastSurvey = pane.timeline.filter((s) => s.step.observation).at(-1);
    const classes = lastSurvey?.step.observation.habitat?.classes_sampled;
    const row = document.createElement("div");
    row.className = "summary-row";
    row.style.setProperty("--c", pane.color);
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = pane.entry.label;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = outcome.distinct_categories;
    const unit = document.createElement("small");
    unit.textContent = isReal ? " perceived" : " categories";
    count.append(unit);
    const detail = document.createElement("span");
    detail.className = "detail";
    const habitat = classes ? `, ${classes} of ${terrain.habitat.names.length} habitat classes` : "";
    detail.textContent = `${outcome.surveys} surveys, ${fmt(outcome.energy_used)} of ${energy.budget} energy${habitat}`;
    row.append(who, count, detail);
    return row;
  });
  $("summary-rows").replaceChildren(...rows);
  $("summary").hidden = false;
}

async function selectWorld(worldId) {
  app.inspector?.close();
  const token = (app.loadToken += 1);
  setPlaying(false);
  cancelSequence();
  exitTour();
  app.worldId = worldId;
  const options = app.entries.filter((e) => e.world_id === worldId);
  $("panes").replaceChildren();
  $("feeds").replaceChildren();
  app.panes = [];
  app.revealed = false;

  const count = Math.min(options.length, 2);
  $("panes").style.gridTemplateColumns = count === 1 ? "minmax(0, 720px)" : "";
  const panes = [];
  for (let i = 0; i < count; i += 1) {
    const el = createPane(i);
    const pane = { el, color: PANE_COLORS[i] };
    for (const entry of options) {
      const option = document.createElement("option");
      option.value = entry.log;
      option.textContent = entry.label;
      el.planner.append(option);
    }
    el.planner.value = options[i].log;
    el.planner.addEventListener("change", () => changePlanner(pane, options));
    el.map.addEventListener("mousemove", (event) => {
      const rect = el.map.getBoundingClientRect();
      const [rows, cols] = pane.log.terrain.shape;
      const r = clamp(Math.floor(((event.clientY - rect.top) / rect.height) * rows), 0, rows - 1);
      const c = clamp(Math.floor(((event.clientX - rect.left) / rect.width) * cols), 0, cols - 1);
      readout(pane, [r, c]);
    });
    el.map.addEventListener("mouseleave", () => readout(pane, null));
    panes.push(pane);
  }
  await Promise.all(panes.map((pane, i) => loadPane(pane, options[i])));
  if (token !== app.loadToken) return;

  app.panes = panes;
  // A manifest's notice can carry licence terms, so it stays up for every world.
  const single = count === 1 ? "Only one mission has been logged for this world." : "";
  showNotice([app.manifestNotice, single].filter(Boolean).join(" "));
  app.energy = 0;
  updateClockRange();
  updateLayerControls();
  updateProvenance();
  app.explorer?.loadWorld();
  render();
}

async function changePlanner(pane, options) {
  const entry = options.find((e) => e.log === pane.el.planner.value);
  setPlaying(false);
  await loadPane(pane, entry);
  if (app.revealed) await fetchReveals();
  app.explorer?.loadWorld();
  updateClockRange();
  updateLayerControls();
  render();
}

function setLayer(layer) {
  const input = document.querySelector(`input[name="layer"][value="${layer}"]`);
  if (input.disabled) return;
  input.checked = true;
  app.layer = layer;
}


// Benchmark ------------------------------------------------------------------

const PLANNER_NAMES = {
  abyss: "ABYSS",
  frontier: "Frontier",
  heuristic: "Heuristic",
  lawnmower: "Lawnmower",
  random: "Random",
  "abyss-noinfo": "No uncertainty",
  "abyss-nolearn": "No learning",
};
const TERRAIN_LABELS = { gebco: "GEBCO Monterey crop", synthetic: "Synthetic (one per seed)" };

function worldLabel(world) {
  const name = SCENARIO_NAMES[world.scenario] || world.scenario;
  return world.scenario === "random" ? name : `${name}, signal ${world.rho}`;
}

function renderBenchmark() {
  const data = app.benchmark;
  const terrain = $("bench-terrain").value;
  const other = $("bench-other").value;
  const worlds = data.worlds.filter((w) => w.terrain === terrain);
  const span = Math.max(1, ...worlds.flatMap((w) => {
    const c = w.abyss_vs[other];
    return [Math.abs(c.ci95_low), Math.abs(c.ci95_high)];
  }));
  const position = (v) => `${50 + (50 * v) / span}%`;

  const rows = worlds.map((world) => {
    const c = world.abyss_vs[other];
    const verdict = c.ci95_low > 0 ? "higher" : c.ci95_high < 0 ? "lower" : "unclear";
    const row = document.createElement("div");
    row.className = `forest-row ci-${verdict}`;
    const label = document.createElement("span");
    label.textContent = worldLabel(world);
    const track = document.createElement("div");
    track.className = "forest-track";
    const zero = document.createElement("i");
    zero.className = "forest-zero";
    zero.style.left = "50%";
    const ci = document.createElement("i");
    ci.className = "forest-ci";
    ci.style.left = position(c.ci95_low);
    ci.style.width = `${(50 * (c.ci95_high - c.ci95_low)) / span}%`;
    const dot = document.createElement("i");
    dot.className = "forest-dot";
    dot.style.left = position(c.mean_difference);
    track.append(zero, ci, dot);
    const value = document.createElement("span");
    value.className = "forest-value";
    const word = document.createElement("b");
    word.textContent = { higher: "ABYSS higher", lower: "ABYSS lower", unclear: "No clear difference" }[verdict];
    const sign = c.mean_difference >= 0 ? "+" : "";
    value.append(word, ` ${sign}${fmt(c.mean_difference, 2)} [${fmt(c.ci95_low, 2)}, ${fmt(c.ci95_high, 2)}]`);
    row.append(label, track, value);
    return row;
  });
  $("bench-forest").replaceChildren(...rows);
  $("bench-note").textContent =
    `Difference in distinct categories found, ABYSS minus ${PLANNER_NAMES[other]}, on the same ${data.seeds.length} worlds. ` +
    "Bars show 95% intervals. Zero is the centre line.";

  const planners = Object.keys(PLANNER_NAMES);
  const head = document.createElement("tr");
  for (const title of ["Mean categories found", ...planners.map((p) => PLANNER_NAMES[p])]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = title;
    head.append(th);
  }
  const body = worlds.map((world) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = worldLabel(world);
    tr.append(name);
    const best = Math.max(...planners.map((p) => world.planners[p].mean));
    for (const planner of planners) {
      const td = document.createElement("td");
      const mean = world.planners[planner].mean;
      td.textContent = fmt(mean, 2);
      if (planner === "abyss") td.classList.add("abyss-col");
      if (mean === best) td.classList.add("best");
      tr.append(td);
    }
    return tr;
  });
  $("bench-table").replaceChildren(head, ...body);

  const safety = data.safety;
  $("bench-meta").textContent =
    `${safety.missions} missions, ${safety.safe_returns} safe returns, ${safety.forced_returns} forced returns. ` +
    `Scored on true labels with ideal perception. Biology is simulated and energy is in abstract units. ` +
    `ABYSS settings were frozen on separate development seeds. The maximum is ` +
    `${data.frozen_config.simulation.n_categories} categories, so results near it can't show larger differences. ` +
    "Intervals are not corrected for multiple comparisons.";
}

async function loadBenchmark() {
  const response = await fetch("logs/benchmark.json");
  if (!response.ok) return; // only appears once a real benchmark has been run
  app.benchmark = await response.json();
  const terrains = [...new Set(app.benchmark.worlds.map((w) => w.terrain))];
  $("bench-terrain").replaceChildren(...terrains.map((t) => new Option(TERRAIN_LABELS[t] || t, t)));
  const others = Object.keys(app.benchmark.worlds[0].abyss_vs);
  $("bench-other").replaceChildren(...others.map((p) => new Option(PLANNER_NAMES[p] || p, p)));
  $("bench-terrain").addEventListener("change", renderBenchmark);
  $("bench-other").addEventListener("change", renderBenchmark);
  $("bench").hidden = false;
  renderBenchmark();
}

// Guided demo ----------------------------------------------------------------

function abyssPane() {
  return app.panes.find((p) => p.entry.planner === "abyss-discovery") ||
    app.panes.find((p) => p.entry.planner.startsWith("abyss-discovery")) ||
    app.panes.find((p) => p.entry.planner === "abyss") || app.panes[0];
}

function otherPane() {
  return app.panes.find((p) => p !== abyssPane()) || app.panes[0];
}

const TOUR_STAGES = [
  {
    title: "Stage 1: Deployment",
    apply: async () => { setLayer("terrain"); app.energy = 0; },
    body: () => "Two robots start at the same station on the same terrain, with the same energy. " +
      "Neither knows where the organisms are. This terrain is real bathymetry; the biology is simulated.",
  },
  {
    title: "Stage 2: First observations",
    apply: async () => {
      setLayer("terrain");
      const first = abyssPane().timeline.find((s) => s.step.new_discoveries.length);
      app.energy = first ? first.end : 0;
    },
    body: () => {
      const first = abyssPane().timeline.find((s) => s.step.new_discoveries.length);
      return first
        ? `ABYSS makes its first discovery at energy ${fmt(first.end)}. Each survey now updates its habitat model. The camera follows ABYSS, and its feed card shows what it found.`
        : "ABYSS found no organisms in this mission.";
    },
  },
  {
    title: "Stage 3: Behaviour emerges",
    apply: async () => {
      setLayer("predicted_richness");
      const line = abyssPane().timeline;
      app.energy = line[Math.min(5, line.length - 2)].start + 0.01;
    },
    body: () => {
      const line = abyssPane().timeline;
      const terms = line[Math.min(5, line.length - 2)].step.planner_diagnostics?.target_utility;
      if (terms?.discovery_proxy !== undefined) return reasonWords(terms) +
        " The map shows estimated occurrence of observed categories; Discovery clues shows the rarity-weighted proxy. No discovery triggers a scripted route.";
      const numbers = terms?.utility !== undefined
        ? ` For this target: predicted richness ${fmt(terms.expected_richness, 2)}, information gain ${fmt(terms.information_gain, 2)}, ` +
          `coverage ${fmt(terms.coverage, 2)}, energy ${fmt(terms.energy_cost, 2)}.`
        : "";
      return "The seafloor colours now show what ABYSS currently believes. Its next target comes from a single formula: " +
        `predicted richness, uncertainty and coverage, per unit of energy.${numbers} No discovery triggers a scripted route.`;
    },
  },
  {
    title: "Stage 4: Mission complete",
    apply: async () => { setLayer("terrain"); app.energy = app.maxEnergy; },
    body: () => {
      const safe = app.panes.every((p) => p.log.outcome.safe_return);
      const counts = app.panes.map((p) => `${p.entry.label} found ${p.log.outcome.distinct_categories}`).join(", ");
      return `${counts}. ${safe ? "Both returned home within budget." : "Check the return status."} One world can't settle anything, whichever planner did better.`;
    },
  },
  {
    title: "Stage 5: The evidence",
    apply: async () => {
      app.energy = app.maxEnergy;
      ($("bench").hidden ? $("lower") : $("bench")).scrollIntoView({ behavior: "smooth", block: "start" });
    },
    body: () => (app.benchmark
      ? "One mission can't settle anything. The benchmark compares the planners across many worlds, including those where ABYSS has no advantage."
      : "One mission can't settle anything. The charts below compare both robots across this mission."),
  },
];

async function showTourStage(index) {
  app.tourIndex = index;
  cancelSequence();
  leaveTitle();
  if (app.explorer) {
    setView("3d");
    if (index === 1) app.explorer.followAbyss();
    else app.explorer.setFollow(-1);
  }
  setPlaying(false);
  const stage = TOUR_STAGES[index];
  await stage.apply();
  $("tour").hidden = false;
  $("tour-title").textContent = stage.title;
  $("tour-body").textContent = stage.body();
  $("tour-back").disabled = index === 0;
  $("tour-next").disabled = index === TOUR_STAGES.length - 1;
  if (index < TOUR_STAGES.length - 1) window.scrollTo({ top: 0, behavior: "smooth" });
  render();
}

function exitTour() {
  app.tourIndex = -1;
  $("tour").hidden = true;
}

function bindControls() {
  const downloadReport = async () => {
    // The range control rounds to its step, while logged energy has more decimals.
    if (app.energy + Number($("scrub").step || 0.1) < app.maxEnergy) {
      showNotice("Finish the expedition, or move the timeline to the end, before generating its findings report.");
      return;
    }
    try {
      await fetchReveals();
      const { buildReport } = await import("./report.js");
      const url = URL.createObjectURL(new Blob([buildReport(app.panes)], {type:"text/html;charset=utf-8"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = "abyss-expedition-findings.html";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) { showNotice(`Could not generate report: ${error.message}`, true); }
  };
  $("summary-report").addEventListener("click", downloadReport);
  $("mission-report").addEventListener("click", downloadReport);
  $("world").addEventListener("change", (event) => selectWorld(event.target.value));
  $("new-ocean").addEventListener("click", newOcean);
  $("play").addEventListener("click", () => setPlaying(!app.playing));
  $("prev").addEventListener("click", () => jumpEvent(-1));
  $("next").addEventListener("click", () => jumpEvent(1));
  $("begin-dive").addEventListener("click", () => beginDive().catch((e) => showNotice(e.message, true)));
  $("summary-replay").addEventListener("click", () => beginDive().catch((e) => showNotice(e.message, true)));
  $("skip-dive").addEventListener("click", () => app.explorer?.endDive(true));
  $("skip-intro").addEventListener("click", leaveTitle);
  $("summary-evidence").addEventListener("click", () => {
    hideSummary();
    ($("bench").hidden ? $("lower") : $("bench")).scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("scrub").addEventListener("input", (event) => {
    cancelSequence();
    setPlaying(false);
    app.energy = Number(event.target.value);
    render();
  });
  const tourStep = (index) => showTourStage(index).catch((e) => showNotice(e.message, true));
  $("tour-start").addEventListener("click", () => { if (app.panes.length) tourStep(0); });
  $("tour-back").addEventListener("click", () => tourStep(app.tourIndex - 1));
  $("tour-next").addEventListener("click", () => tourStep(app.tourIndex + 1));
  $("tour-exit").addEventListener("click", exitTour);
  $("views").addEventListener("change", (event) => setView(event.target.value));
  $("layers").addEventListener("change", (event) => {
    app.layer = event.target.value;
    render();
  });
  document.addEventListener("keydown", (event) => {
    // Focused controls keep their own keyboard behaviour.
    if (event.target.closest("select, input, button")) return;
    if (event.code === "Space") { event.preventDefault(); setPlaying(!app.playing); }
    if (event.key === "ArrowRight") jumpEvent(1);
    if (event.key === "ArrowLeft") jumpEvent(-1);
    if (event.key === "n" || event.key === "N") newOcean();
  });
  new ResizeObserver(() => { if (app.panes.length) render(); }).observe($("panes"));
}

function setView(view) {
  if (view === "2d") {
    cancelSequence();
    document.body.classList.remove("pre-dive");
  }
  app.view = view;
  document.querySelector(`input[name="view"][value="${view}"]`).checked = true;
  document.body.classList.toggle("view-3d", view === "3d");
  $("stage").hidden = view !== "3d";
  $("stage-note").hidden = view !== "3d";
  app.explorer?.setActive(view === "3d");
  if (app.panes.length) render();
}

async function loadExplorer() {
  try {
    const { createExplorer } = await import("./explorer.js");
    $("stage").hidden = false; // the renderer needs a real size to start
    app.explorer = createExplorer({
      app, overlayGrid, abyssPane, gridExtent, BELIEF_RAMP, HIDDEN_RAMP, LAYER_LABELS, categoryLabel,
      HABITAT_COLOURS, fillHabitatLegend, habitatChip,
    });
    document.querySelector('input[name="view"][value="3d"]').disabled = false;
    app.explorer.loadWorld();
    setView("3d");
  } catch (error) {
    // WebGL can be unavailable on some machines, and the 2D view shows the same missions.
    console.warn("3D view unavailable:", error);
    app.explorer = null;
    setView("2d");
  }
}

async function init() {
  const { installInspector } = await import("./inspector.js");
  app.inspector = installInspector({app});
  bindControls();
  let manifestPath = new URLSearchParams(location.search).get("missions");
  if (!manifestPath) {
    try {
      await getJson("vision-logs/index.json");
      manifestPath = "vision-logs/index.json";
    } catch (_) { manifestPath = "logs/index.json"; }
  }
  if (!/^[a-zA-Z0-9_/-]+\/index\.json$/.test(manifestPath) || manifestPath.includes("..")) {
    throw new Error("Choose a local mission index inside the UI directory.");
  }
  try {
    const manifest = await getJson(manifestPath);
    app.entries = manifest.entries;
    app.manifestNotice = manifest.notice || "";
    app.imageCredits = manifest.image_credits || {};
  } catch (error) {
    const hint = location.protocol === "file:"
      ? "Browsers block loading logs from file:// pages. Run: python -m http.server 8000 --directory ui"
      : "Build the logs with: python -m scripts.build_ui_logs";
    showNotice(`Could not load mission logs. ${hint}`, true);
    return;
  }
  const select = $("world");
  const groups = new Map();
  for (const world of worlds()) {
    const landform = LANDFORM_NAMES[world.terrain];
    const group = landform ? "Synthetic landforms" : "Monterey Canyon, real terrain";
    if (!groups.has(group)) groups.set(group, []);
    const option = document.createElement("option");
    option.value = world.world_id;
    // Two worlds can share an ecology at different strengths, so the label names the signal.
    const scenario = `${worldLabel(world)}, seed ${world.seed}`;
    option.textContent = landform ? `${landform} · ${scenario}` : scenario;
    groups.get(group).push(option);
  }
  // Group only when there is more than one kind of terrain, such as in the ideal logs.
  for (const [label, options] of groups) {
    if (groups.size === 1) { select.append(...options); continue; }
    const optgroup = document.createElement("optgroup");
    optgroup.label = label;
    optgroup.append(...options);
    select.append(optgroup);
  }
  await selectWorld(select.value);
  if (manifestPath === "logs/index.json") await loadBenchmark();
  await loadExplorer();
}

init().catch((error) => showNotice(error.message, true));
