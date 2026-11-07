# Experimental category-aware ABYSS

Original ABYSS learns **how many categories a habitat contains**. The experimental
`abyss-discovery` learns **which observed categories occur in which habitats** and
reduces the reward for categories it encounters frequently. Frontier still selects
nearby unexplored boundary cells. All three get identical observations and budgets.
Computer vision remains the shared observation system; the learned choice of where
to go next is the difference between the planners.

This is an experiment, not an assumed improvement. Original ABYSS, Cam's earlier
`abyss-novelty` experiment, published benchmark, existing terrain options and random
ocean generation remain available. The new planner never receives ecology labels,
animal placements, the hidden category catalogue or private evaluation records.

## Measured results

All 3,600 evaluation missions returned safely, with zero forced returns. The main
experiment uses 20 fresh seeds and all 18 original settings; the landform and vision
checks are smaller and reported separately.

| Check | Category pool | Discovery | Frontier | Original ABYSS |
| --- | --- | --- | --- | --- |
| [Main ideal-perception evaluation](discovery-evaluation.md) | 16 | 12.67 | 11.43 | 13.15 |
| [Four landforms, ideal perception](discovery-landforms.md) | 16 | 12.92 | 11.32 | 12.87 |
| [Real-image perception](discovery-vision.md) | 11 | 7.87 | 6.67 | 8.27 |

Values are mean **true distinct categories**, not recognition accuracy. In the main
experiment Discovery beat Frontier by 1.24 [95% paired interval 0.86, 1.62] while
using 40.14 versus 43.88 survey stops. Original ABYSS still scored 0.48 categories
higher than Discovery [0.19, 0.79]. It therefore stays the default.

Disabling biological learning reduced Discovery's mean to 11.86, a paired decrease
of 0.81 [0.44, 1.18]. The separate effects of rarity weighting, initial sampling and
three-stop lookahead were not clear at this sample size. Guarded real-image updates
scored 7.87 versus 8.13 without safeguards; the difference interval included zero.
The safeguards have not demonstrated a route-performance benefit. These exploratory
intervals are uncorrected for multiple comparisons, and some settings favour Frontier.

The new variant demonstrates learning and improves on Frontier in the aggregate
tested here. It does **not** improve on original ABYSS overall. No failed setting
was removed, and final evaluation did not choose the defaults.

## The model

Each surveyed cell supplies presence/absence observations for the categories the
robot has observed so far. An empty survey supplies absence evidence. Three models
estimate their occurrence rates: the overall frequency, similar terrain (standardised
depth, slope and bathymetric position), and nearby positions. The terrain and spatial
models use Gaussian kernels with a Beta-style shrinkage prior based on observed
frequencies. Weighted local counts are a smoothing approximation, not independent
samples or calibrated probabilities. Global frequencies use a Jeffreys-style prior.

The models' mixture changes using their prediction error **before** each new survey
is learned. This lets terrain associations or spatial patches help when predictive,
while retaining a global component when the observations have little structure.
No mixture component reads the world's ecology type. The model is fitted online
from the current expedition; no hidden test labels train it in advance.

The category weight is `(1 + observed incidence count) ** -rarity_power`. Predicted
rates multiplied by these weights yield a rare-habitat discovery proxy. Every modelled
category has already been observed. The proxy exploits the hypothesis that rare
organisms' habitats can lead to further finds; it does **not** estimate the identity
or calibrated probability of a never-seen category. Summing predictions over a secret
list of undiscovered labels would violate the original vision.

For the first five surveys, a habitat coverage incentive encourages sampling
different terrain. Later decisions retain a smaller uncertainty/coverage incentive.
The logged `information_gain` field is retained for existing UI compatibility; in
this variant it is a support-based uncertainty score, not Bayesian entropy reduction.

## Travel and lookahead

The bounded beam search compares one-, two- or three-stop routes. Candidate cells
include efficient, high-value and nearby feasible destinations. Further stops discount
overlapping category predictions and similar habitat exploration bonuses. This is
approximate planning, not an optimal full-mission solver.

Travel legs use the same eight-connected depth-dependent navigation graph as the
simulator. `PublicMap.terrain_cost_factor` is an additive public navigation fact,
available to every planner; it reveals no biology. Older callers can omit it, in
which case Discovery falls back to one-step planning using supplied costs.
Every proposed partial route must afford its travel, surveys, home journey and
reserve. Only its first stop is executed, then the robot observes and replans.

Six predefined development candidates used seeds 0–9 across both terrain modes and
all five ecologies. Rarity power **1** and lookahead **1** had the highest mean
(12.54 categories). These settings were frozen before fresh evaluation. Three-stop
planning did not win development and remains explicitly available through
`abyss-discovery-route`. Enabling every feature is not evidence of better performance.
The complete development table and mission scores are in
[discovery-development.json](discovery-development.json).

## Computer vision safeguards

DINOv2 still encodes each supplied animal crop. The reference model chooses a label
or flags it unfamiliar, and those public predictions drive the planner. Animal
photographs represent simulated encounters; no camera is reading the 3D animation.

The new planner halves an isolated real-image label's influence until it has been
reported from two distinct opaque image references. Replaying the same image at
different cells does not supply independent confirmation. An uncertain survey gives
weaker absence evidence in the local models; the global-frequency prior still uses
all surveys. Familiar-label inventory scores are still the robot's
reported labels and may contain mistakes.

Unfamiliar flags contribute at most 0.25 discovery-proxy units per survey and only
for image references not flagged earlier in the mission. They do not become animal
categories. Multiple different crops may depict the same category, so even deduplicated
images do not establish new species. Similarity and unfamiliarity distance are never
converted into a confidence probability. These safeguards are conservative heuristics;
the vision experiment tests whether they improve routes, including negative results.

## Run and inspect it

Use your updated checkout and activated Python environment. A quick ideal-perception
mission needs no animal downloads:

```bash
OMP_NUM_THREADS=2 python -m abyss.run_mission \
  --planner abyss-discovery --scenario ridge --seed 3000
```

For a real-image replay, reuse the quality dataset and artifact already downloaded
on your laptop. This generates new local logs without changing the original replay:

```bash
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay \
  --all-worlds --oceans 1 --seed 3000 \
  --manifest data/perception-quality-images/manifest.json \
  --artifact data/perception-quality \
  --planners frontier abyss-discovery abyss \
  --out ui/discovery-vision \
  --registry data/discovery-inspector-registry.json

OMP_NUM_THREADS=2 python -m perception.inspector_server \
  --artifact data/perception-quality \
  --registry data/discovery-inspector-registry.json \
  --port 8001
```

Open **http://localhost:8001/?missions=discovery-vision/index.json**. The first panes
compare Frontier and experimental Discovery; their planner menus also include
original ABYSS. Add `abyss-discovery-route` to `--planners` to compare three-stop
lookahead. Use `--oceans 8` later for eight seeds per world; start with one to check
the setup quickly. Images/model weights are reused, not downloaded again.

During playback, **Discovery clues** shows the learned proxy map. The explanation
shows the selected destination's value and provisional route. Click an observation
image to inspect DINOv2 references, prediction, the model update, and category clues
for the following destination. Fresh local reanalysis still runs the actual encoder
on the selected registered image. The post-expedition report describes the planner
actually selected and distinguishes true encounters from perceived labels.

For ideal-perception replays without vision assets:

```bash
python -m scripts.build_ui_logs --out ui/discovery-logs --seed 3000 \
  --planners frontier abyss-discovery abyss
python -m http.server 8001 --directory ui
```

Open **http://localhost:8001/?missions=discovery-logs/index.json**. This mode explicitly
uses simulator labels and supplies no image inference evidence.

## Reproduce evaluation

The [protocol](discovery-protocol.md) was written before development and evaluation.
Development and fresh evaluation use separate seeds; the old 6,300-mission benchmark
files are untouched. Commands write separate experimental reports and retain every
per-mission score, including losses, true and perceived counts, energy and safety.

```bash
OMP_NUM_THREADS=2 python -m abyss.evaluation.discovery_experiment tune --workers 4
OMP_NUM_THREADS=2 python -m abyss.evaluation.discovery_experiment run --workers 4
OMP_NUM_THREADS=2 python -m abyss.evaluation.discovery_experiment landforms --workers 4
OMP_NUM_THREADS=2 python -m abyss.evaluation.discovery_experiment vision \
  --manifest data/perception-quality-images/manifest.json \
  --artifact data/perception-quality
```

See the generated evaluation, landform and vision reports alongside this document.
The main experiment reports all 18 original terrain/ecology/signal settings and
ablations: no learning, no rarity weighting, no initial habitat sampling and the
three-stop alternative. Aggregate confidence intervals resample complete seeds,
keeping paired world settings together. They are exploratory and uncorrected for
multiple comparisons. The smaller landform and vision checks have limited precision.
Only repeated matched results can support an improvement claim.
