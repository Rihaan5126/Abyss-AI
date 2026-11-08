# Developer guide

How to run, extend and regenerate each part of ABYSS. For what the project is and its
results, start with the [README](../README.md).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Run one mission from the command line. It writes a mission log and a `.reveal.json`
answer file to `results/missions/`:

```bash
python -m abyss.run_mission --scenario ridge --seed 0 --planner abyss
```

## Benchmark and results

```bash
python -m abyss.evaluation.full_run
python -m abyss.evaluation.report
python -m abyss.evaluation.plots --csv results/benchmark.csv --out results/figures
```

`full_run` uses the frozen weights in `abyss/planners/adaptive.py` on evaluation seeds (1000+).
Tuning stays on development seeds (0-999). See
[abyss/evaluation/README.md](../abyss/evaluation/README.md) for the benchmark itself.

[novelty-experiment.md](novelty-experiment.md) records a separate experiment on
targeting new categories, which did not improve on ABYSS.
[Experimental category-aware Discovery](discovery-planner.md) adds observed-category
habitat models, rarity weighting, initial sampling, optional route lookahead and conservative
vision updates. It has a separate fresh-seed evaluation; original ABYSS and the published
benchmark stay unchanged.

## Replay UI

For input images, actual reference matches, threshold explanations, the
observation-to-decision trace and optional fresh local inference, see
[Observation Inspector](observation-inspector.md). Regenerate a vision replay
to capture evidence, then click an animal photo or survey-feed inspect button.

When local `ui/vision-logs/index.json` exists, opening the viewer automatically
loads that real-image replay. Otherwise it uses the bundled ideal-perception
examples, which contain no animal photos. An explicit `?missions=logs/index.json`
still selects the ideal examples. The side panels show the latest photographed
encounter with per-image predicted labels or unfamiliarity flags; an empty later
survey does not erase the previous photos. These are recorded image predictions,
not live detections in the rendered ocean.

After playback finishes, press **Findings report** in the bottom controls or
**Download findings report** on the end-of-dive summary. This explicitly loads
the evaluator's answer sheet and downloads `abyss-expedition-findings.html`.
Open the file and use **Print / save as PDF** for a plain-English expedition
sheet with actual and perceived category counts, surveys, energy, unfamiliar
images, safe return, experiment identifiers and limitations. It contains no
animal image crops. Reports are unavailable before the timeline reaches the end.

For the integrated **3D view with real image perception**, follow
[Watch the full system in 3D](vision-3d.md). It generates a local paired
replay using your existing expanded image dataset and model, with actual photos
in the discovery feed. Computed missions finish before browser playback.

```bash
python -m scripts.build_ui_logs
```

```bash
python -m http.server 8000 --directory ui
```

Then open <http://localhost:8000>. The first command runs real missions and rewrites
`ui/logs/`; rerun it after adding a planner so that planner appears in the UI. Both panels
share a clock in energy units, so they are always compared at equal spend. Reveal files
are only fetched when the viewer presses Reveal.

The app opens in a **3D explorer** view of the logged missions, built with a local copy of
[Three.js](https://threejs.org/) r160 in `ui/vendor/three` (MIT licence), so it runs without
internet. It's a visualisation: robots don't see this scene, and the vision model works on
real photographs. Terrain is smoothed between grid cells, and its height is exaggerated 3×.
Its descent animation is illustrative, because missions start at the home station. Fonts are
stored in `ui/vendor/fonts` under their open licences. If WebGL isn't available, the app falls
back to the **Charts** view.

The **Habitats** layer shows five classes clustered from public depth, slope and bathymetric
position, and the feed flags a robot's first survey of each class. This is display-only:
planners never receive it, and all routes and results are unchanged. These are terrain-based
classes, not biomes, because we have no temperature, oxygen or substrate data at this scale.

Press **Begin dive** for the full sequence: descent, exploration with captions, then a mission
summary. **Step through** moves through the same story one stage at a time. The benchmark section appears once
`ui/logs/benchmark.json` exists.


## Adding a planner

Subclass `Planner` from `abyss/planners/base.py`, then add it to `PLANNERS` in
`abyss/planners/__init__.py`. It then works with `--planner <name>`.

```python
class MyPlanner(Planner):
    name = "mine"

    def reset(self, public_map, config, seed): ...
    def choose_target(self, public_state, observation_history): ...  # (row, col) or HOME
    def observe(self, observation): ...  # observation.richness is the model target
    def diagnostics(self): ...  # predicted maps and utility terms for the log
```

- `public_state.feasible` marks every target the simulator will accept, and
  `public_state.travel_cost` gives the cost of reaching each cell.
- `public_map.features` holds standardised depth, slope and BPI.
- A rejected target sends the robot home and is recorded as a violation in the log.

To show beliefs in the UI, return these optional keys from `diagnostics()`. It is called
after `observe()`, so `target_utility` describes the target just travelled to, and the maps
are the updated beliefs. Each map is a `[row][col]` nested list.

```python
{
    "predicted_richness": ...,
    "uncertainty": ...,
    "target_utility": {
        "expected_richness": ..., "information_gain": ..., "coverage": ...,
        "energy_cost": ..., "utility": ...,
    },
}
```

## Adding perception

The simulator side is ready and tested with a fake model. To try it:

```bash
python -m abyss.run_mission --scenario ridge --seed 0 --perception stub
```

Implement these two interfaces from `abyss/contract.py`. `abyss/stub_perception.py` is a
working example of both, and `run_mission()` takes them as `perception=` and `image_pool=`,
with `perception_mode="real"` in the config.

- **`ImagePool`** provides `categories` (common first; the count must equal `n_categories`),
  `withheld`, `images_for(category)` and `load(ref)`. Your categories replace the
  `category_00` names.
- **`Perception`** provides `name` (recorded in the log) and `predict(image)`, which returns
  a `PerceptionResult`. The same image must always give the same result.

Image refs reach the planner, so they must not reveal the category: the simulator refuses
a path like `images/squid/001.jpg`. Use opaque IDs. Refs are also the UI's image URLs, so
they should resolve from `ui/` for the gallery to show them.

Each survey runs the model once per cell. Images flagged unknown count towards richness,
but not towards discovered categories. True labels and the scores in `perception_summary`
stay in the `.reveal.json` file. These scores cover only images seen on that mission, so
they don't replace your held-out evaluation.

`abyss/stub_perception.py` has no real images and made-up error rates. Never report its
numbers as vision results.

`abyss/fathomnet_perception.py` connects the `perception` package to these interfaces.
After following the perception runbook to fit a model:

```bash
python -m abyss.run_mission --scenario ridge --seed 0 --perception fathomnet --manifest data/fathomnet/splits.json --artifact data/perception
```

This sets `n_categories` to the manifest's category count, and only held-out test images
are used. Familiar categories come first, so withheld categories are the rarest in the
world. A small pool means each image is seen repeatedly, with the same result each time,
so use enough test images per category for the final run.

To measure what vision errors cost the planner, compare ideal and real perception on the
same worlds. It writes `results/perception_comparison.json`:

```bash
python -m abyss.evaluation.perception_compare --manifest data/fathomnet/splits.json --artifact data/perception
```


## Perception pipeline

For the fresh-source evaluation, error gallery, neighbour voting and matched
old/new mission analysis, see [Perception quality](perception-quality.md).

The `perception/` package implements FathomNet organism cropping, frozen
DINOv2-small embeddings, nearest-neighbour familiar-category recognition,
validation-calibrated reference-unfamiliarity detection, and held-out evaluation.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
# CPU-only PyTorch avoids downloading CUDA libraries on a laptop/server:
python -m pip install 'torch>=2.4,<3' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[vision]'
python -m perception --help
python -m pytest -q
```

See [the perception runbook](perception.md) for data preparation, offline
inference, evaluation, image licensing and the simulator integration interface.
For eight familiar categories plus a withheld dumbo-octopus category, see
[the expanded dataset and Mac demo instructions](expanded-perception.md).
