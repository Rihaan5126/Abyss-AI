# ABYSS: Adaptive Biodiversity Exploration

WHACK 2026, Marshall Wace New Worlds Challenge. Team: Rihaan, Cam and Ammar.

ABYSS is the decision-making software for a simulated underwater exploration robot. It
learns which environments are associated with biodiversity during a mission and uses
that to choose where to survey next, within a fixed energy budget.

**This is a simulation.** The terrain is real GEBCO bathymetry, but the biology on it is
always simulated and energy is in abstract units. It is not a validated AUV or a model
of a real ecosystem.

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

```bash
python -m abyss.run_mission --scenario ridge --seed 0 --planner random
```

This writes a mission log and a `.reveal.json` file to `results/missions/`.

## Replay UI

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

While only the random planner exists, the second panel shows a second random run with a
different planner seed.

## Status

| Area | Owner | State |
| --- | --- | --- |
| Contract, GEBCO terrain, worlds, environment, mission runner, logs | Rihaan | Working |
| Replay UI | Rihaan | Working; belief layers tested only with temporary data until the adaptive planner logs them |
| Random baseline | Shared | Working |
| Learner, adaptive planner, other baselines, benchmark | Cam | Not started |
| Perception pipeline | Ammar | Not started; `Environment` currently supports ideal perception only |

## Adding a planner (Cam)

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

## Adding perception (Ammar)

Implement the `Perception` protocol in `abyss/contract.py`, returning a `PerceptionResult`
from `predict(image)`. Category names are currently `category_00` and so on; these still
need mapping to the FathomNet categories you select.

## Rules the code enforces

- **No leakage.** Planners receive only `PublicMap`, `PublicState` and `Observation`.
  These exclude hidden ecology, including the scenario name and rho.
- **Safe return.** A target is accepted only if
  `E_remaining >= E_travel + E_survey + E_return + E_reserve`.
- **Fair worlds.** Encounters are generated once per world seed and do not depend on the
  planner. Repeat surveys return the same categories, so they cannot inflate discoveries.
- **Separate RNG streams.** Terrain, world and planner randomness never share a stream.
- **Separate truth.** Mission logs hold public data. Hidden maps go in `.reveal.json`.

## Scenarios

Each scenario keeps every category's mean prevalence the same, so scenarios change where
organisms are, not how many exist. `rho` in `[0, 1]` scales signal strength, and `rho = 0`
removes all signal.

| Scenario | Hidden distribution |
| --- | --- |
| `random` | Independent of terrain, location and neighbours, at any `rho` |
| `clustered` | Spatial clusters, with linear and squared terrain trends removed |
| `ridge` | Favours steep, ridge-like terrain, with per-category depth niches |
| `reversed` | Favours flat terrain, with the same depth niches as `ridge` |
| `nonlinear` | Depth-slope interaction plus a spatial field; outside the quadratic features |

## Data sources

**Bathymetry:** GEBCO Compilation Group (2025) GEBCO 2025 Grid
(doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29).

- The committed crop is `data/gebco/monterey_canyon_30x30.json`, so nobody needs to
  download anything. `python -m scripts.fetch_gebco` regenerates it from the
  [UNH image service](https://gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_IS/ImageServer).
- It is the all-ocean 30 x 30 window with the most varied slope, chosen from terrain alone.
- Cells are about 464 m by 372 m. They are regional planning units, not camera footprints
  or collision maps. Slope uses the true spacing, but travel costs treat the grid as square.
- All seeds share this one crop, so repeated seeds do not show generalisation to other
  regions. Set `terrain_source: synthetic` in `config.yaml` to vary terrain by seed.

**Planned:** [FathomNet](https://database.fathomnet.org/) imagery and, as a stretch goal,
[OBIS](https://obis.org/) occurrence records. Neither is integrated yet.
