# ABYSS: Adaptive Biodiversity Exploration

WHACK 2026, Marshall Wace New Worlds Challenge. Team: Rihaan, Cam and Ammar.

ABYSS is the decision-making software for a simulated underwater exploration robot. It
learns which environments are associated with biodiversity during a mission and uses
that to choose where to survey next, within a fixed energy budget.

**This is a simulation.** Biology is always simulated, terrain is currently synthetic,
and energy is in abstract units. It is not a validated AUV or a model of a real ecosystem.

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

This writes a mission log and a `.reveal.json` file to `results/missions/`. There is an
example pair in `ui/logs/`.

## Status

| Area | Owner | State |
| --- | --- | --- |
| Contract, terrain, worlds, environment, mission runner, logs | Rihaan | Working, on synthetic terrain |
| Random baseline | Shared | Working |
| GEBCO terrain, replay UI | Rihaan | Not started |
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

Planned: [GEBCO](https://www.gebco.net/) bathymetry, [FathomNet](https://database.fathomnet.org/)
imagery and, as a stretch goal, [OBIS](https://obis.org/) occurrence records. None are
integrated yet.
