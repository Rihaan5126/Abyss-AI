> **About this document.** This is the team's original master brief, kept word for word below.
> It is the baseline for what we set out to build. Where the project has moved on:
>
> - **3D explorer:** the brief's default interface is HTML, Canvas and logs. We added a 3D
>   visualisation of the logged missions using Three.js. It is not a physics simulation, and
>   the robots don't see that scene. This is on the `explorer-3d` branch.
> - **Habitat or biome detection:** proposed as a display-only addition, not built, and not part
>   of this brief. At this grid scale it would mean terrain-based habitat classes, not true biomes.
> - **Results and seeds:** see [results.md](results.md) for measured results. They use ideal
>   perception. Development seeds are 0-999, and evaluation seeds are 1000 and above.
> - **Real perception:** connected through an adapter, but the real model has not yet run inside
>   missions.

# ABYSS — FINAL MASTER PROJECT BRIEF
**WHACK 2026 | Marshall Wace — New Worlds Challenge**

**Team:** Rihaan, Cam and Ammar  
**Project:** ABYSS — Adaptive Biodiversity Exploration  
**Format:** 24-hour hackathon  
**Prototype:** Software-based autonomous underwater exploration system  
**Status:** Finalised technical direction and implementation specification

---

# PART I — PROJECT VISION

## 1. What We're Building

ABYSS is a curiosity-driven autonomous underwater robotic exploration system that learns which environmental conditions are associated with marine biodiversity and uses that knowledge to decide where to explore next.

The motivation is straightforward.

Much of the deep ocean remains poorly explored. Underwater robotic vehicles can collect images, survey habitats and document marine organisms, but many survey missions follow routes planned before the vehicle has collected new biological observations.

ABYSS explores a different approach.

**What if an autonomous underwater robot could learn which parts of an unfamiliar environment are biologically promising, then independently change its trajectory to investigate them?**

Instead of following a predetermined route, ABYSS continuously:

1. Explores an initially unknown biological environment.
2. Collects observations using simulated sensors and a real computer-vision pipeline.
3. Learns relationships between environmental features and observed biodiversity.
4. Predicts which unexplored locations might be scientifically valuable.
5. Selects new survey destinations using expected discovery value, uncertainty and energy costs.
6. Replans its mission as new observations arrive.

The vehicle must balance exploration, scientific interest and a limited energy budget while maintaining enough energy to return home.

**We are building the decision-making intelligence for an underwater exploration robot, not a physical submarine.**

For WHACK, the system will operate in a data-informed ocean simulation. A future version could be adapted to a real autonomous underwater vehicle (AUV).

## 2. The Central Research Question

**Can an autonomous underwater vehicle learn habitat–biodiversity relationships during an expedition and use that knowledge to discover more distinct marine organism categories within a fixed energy budget than conventional exploration strategies?**

A second question is equally important:

**Under what environmental conditions does adaptive exploration actually outperform conventional surveying?**

We are not assuming ABYSS will always win.

If biodiversity is distributed randomly, its learning algorithm should have little useful environmental structure to exploit.

If biodiversity is related to terrain characteristics, adaptive learning may provide an advantage.

If the relationship differs from the robot's initial assumptions, we want to determine whether it can adapt.

The project succeeds by producing credible, measurable experimental results, even if some results contradict our hypotheses.

## 3. Connection to Marshall Wace's New Worlds Challenge

The deep ocean represents a real world that remains largely inaccessible to direct human exploration.

ABYSS combines robotics, artificial intelligence, optimisation and marine biology to investigate how machines could explore these environments more intelligently.

The key connection is not simply that the ocean is unexplored.

**ABYSS develops a method for autonomously deciding what parts of an unfamiliar world are worth investigating.**

There is also an optimisation parallel to quantitative research: allocating limited resources among uncertain opportunities while respecting risk constraints.

That parallel can be mentioned during the presentation, but the underwater scientific application should remain central.

---

# PART II — SCIENTIFIC DATA AND SIMULATION

## 4. What We Have and What We Don't

We do not have:

- A physical underwater robot.
- Thrusters, sonar or underwater navigation hardware.
- A microscope or live marine imaging equipment.
- The resources to reproduce realistic underwater hydrodynamics during the hackathon.

We do have:

- Python and machine-learning tools.
- Public scientific datasets.
- Pretrained computer-vision models.
- Open-source numerical and path-planning libraries.
- The ability to create reproducible simulations.
- Three developers working on separate systems.

**The objective is to build the actual exploration and perception software in a simulated environment.**

We must not describe the prototype as a physically validated underwater vehicle or an accurate digital twin of a particular ocean ecosystem.

## 5. Scientific Data Sources

### GEBCO — Seafloor Bathymetry

Website: https://www.gebco.net/

GEBCO provides global seafloor elevation data.

We will preferably use a small subset around Monterey Canyon to create a realistic terrain foundation.

Environmental features will include:

- Depth.
- Slope.
- Local bathymetric position or curvature.
- Geographic or grid coordinates.

GEBCO's 15-arc-second grid corresponds to hundreds of metres horizontally at many latitudes. These cells are regional planning units, not detailed camera footprints or collision-avoidance maps.

GEBCO terrain is real data. Our biological ecosystem will be simulated.

**Implementation priority:** Begin with a synthetic grid so development is never blocked by terrain downloads. Replace it with GEBCO once the core simulation runs.

### FathomNet — Marine Computer Vision

Website: https://database.fathomnet.org/

FathomNet contains real underwater imagery and organism annotations.

We'll select a manageable subset of marine organism categories.

These images provide real visual observations for testing computer vision, classification and reference-unfamiliarity detection.

The images are not necessarily from our selected GEBCO region. They represent simulated camera encounters, not verified sightings at those coordinates.

We must preserve source attribution and check relevant image-licensing requirements.

### OBIS — Ocean Biodiversity Information System

Website: https://obis.org/

OBIS contains recorded marine biodiversity occurrences across geographical regions.

It may help inform plausible ecological relationships or provide scientific background.

However, OBIS is affected by geographic sampling bias. A lack of recorded organisms does not mean an area is biologically empty.

**OBIS integration is a stretch goal, not a requirement for the MVP.**

The simulator's generated biodiversity must always be labelled as simulated rather than observed ground truth.

---

## 6. Ocean Simulation Architecture

### Initial Environment

Begin with a **30 × 30 grid** containing 900 planning waypoints.

Increase resolution only if performance and integration are satisfactory.

The map contains:

- Environmental features at each waypoint.
- A hidden biodiversity distribution.
- An initial robot location and home station.
- A finite energy budget.
- Local surveying costs.
- Travel costs.
- Optional explicitly simulated no-go regions.

Movement can use an eight-connected grid graph.

Travel costs may depend on distance and a documented terrain-related cost term.

These are abstract energy units, not measured consumption values from a real AUV.

### Hidden Biological World

We will generate approximately 12–20 organism categories initially, expanding towards 20–30 if practical.

Each organism category has a hidden probability of occurring in different regions.

The distribution can depend on:

- Preferred environmental depth.
- Slope or ridge characteristics.
- Spatial clustering.
- Random environmental variation.

Some categories will be relatively uncommon.

When the world is created, the simulator should pre-generate the organism encounters available at each waypoint or otherwise guarantee identical observations for the same world and survey action.

**Every planner must experience the same underlying environment.**

This prevents performance differences arising merely because one planner received luckier random encounters.

One local survey can return zero, one or several organism categories.

Repeated surveys must not artificially inflate distinct-discovery counts.

### Observation Resolution

A GEBCO planning waypoint represents a large region.

A simulated camera observation represents a limited survey footprint within that region.

We must not claim that one camera image surveys hundreds of square metres or an entire 500-metre grid cell.

The simulation may abstract each waypoint as a fixed local sampling opportunity, with this simplification documented.

---

## 7. Required World Types

We'll test the same planners in different ecological environments.

### World A — Independent Random Biodiversity

Biological encounters are independent of depth, slope, coordinates and neighbouring observations.

There should be no meaningful environmental relationship for ABYSS to learn.

Do not apply spatial smoothing to this scenario.

### World B — Spatially Clustered Biodiversity

Organisms form spatial clusters, but these clusters are independent of terrain features.

This tests whether geographic proximity and previous encounters help exploration.

### World C — Terrain-Dependent Biodiversity

Biological richness or category occurrence varies with environmental features such as slope, depth or bathymetric position.

The relationship is hidden from ABYSS.

### World D — Reversed Habitat Relationships

Organisms favour different environmental conditions from those favoured by a fixed terrain heuristic.

This tests whether ABYSS learns from evidence rather than following hard-coded assumptions.

### World E — Nonlinear or Mixed Ecology

Organisms depend on combinations of features and spatial effects that may be difficult for the initial learning model to represent.

This exposes limitations and model misspecification.

### Predictability Parameter

Where appropriate, introduce a parameter \(\rho \in [0,1]\), controlling how strongly terrain characteristics influence the simulated ecological distribution.

Be careful to distinguish terrain predictability from spatial predictability.

The \(\rho=0\) independent-random scenario must genuinely contain no spatial or terrain signal.

**MVP scenarios:** Independent random, ridge-associated and reversed/flat-associated ecology.

**Extended benchmark:** Spatial clusters, nonlinear ecology and additional predictability strengths.

---

# PART III — ROBOTICS AND AUTONOMOUS INTELLIGENCE

## 8. Robot State and Sensor Interface

The simulated robot has access to:

- Its position.
- Home position.
- Remaining energy.
- Public terrain features.
- Previously visited waypoints.
- Its own biological observations.
- Its learned habitat model.

It does not have access to:

- Hidden organism locations.
- The simulator's biological richness map.
- Species-distribution generation parameters.
- Future survey observations.
- Other hidden evaluation data.

This separation is non-negotiable.

**The planner must only receive information the robot could legitimately know.**

The simulation environment alone manages hidden truth.

## 9. Robot Mission Loop

The fundamental execution loop is:

**Observe → Learn → Evaluate → Plan → Travel → Observe again.**

More explicitly:

1. Initialise the mission using public terrain and navigation information.
2. Select a feasible survey waypoint.
3. Travel using the grid path planner.
4. Spend survey energy and receive local observations.
5. Pass images through the perception module when real perception is enabled.
6. Update the learned environmental model.
7. Recalculate expected biodiversity and uncertainty.
8. Choose another feasible waypoint.
9. Return home when additional surveying is no longer possible within the energy constraints.

There should be no manually scripted "interesting discovery" event.

The robot's trajectory must change because its observations and predictions change.

## 10. Energy and Navigation

Movement will use a grid graph.

Use SciPy Dijkstra or A* to calculate feasible routes.

For symmetric movement costs, shortest return-home costs can be precomputed once from home.

All planners must obey the same energy equation:

\[
E_{\mathrm{remaining}}
\geq
E_{\mathrm{travel}}
+
E_{\mathrm{survey}}
+
E_{\mathrm{return}}
+
E_{\mathrm{reserve}}
\]

If a candidate destination would violate this constraint, it cannot be selected.

The simulator enforces movement and energy consumption. Individual planners cannot bypass these checks.

When further surveying is infeasible, the robot returns home.

Safe return is an invariant that must always hold, not an optimisation objective that can be sacrificed for discoveries.

**This is high-level autonomous mission planning, not a detailed six-degree-of-freedom underwater motion controller.**

---

## 11. Online Habitat Learning

**Owner: Cam**

This is ABYSS's core machine-learning component.

The robot begins without knowing which environmental characteristics are associated with biodiversity.

After each survey, it updates its statistical model using environmental features and the biological observations collected there.

### The Prediction Target

Initially, predict **local observed organism-category richness**.

This is the number of distinct categories observed during a survey.

Do not directly train the model to predict "new categories discovered", because novelty depends on the robot's changing discovery history.

The robot separately tracks which categories it has already encountered.

This is a simplified proxy for potential scientific value. A rich waypoint containing only previously known categories may contribute little to the primary discovery metric.

A per-category occurrence model would address this limitation more directly, but it is a stretch goal.

### Primary Model: Bayesian Linear Regression

Use Bayesian linear regression for the first implementation.

Advantages:

- Fast incremental updates.
- Low computational cost.
- Estimates prediction uncertainty.
- Works without GPU training.
- Easy to debug.
- Can learn positive and negative environmental relationships.

A feature vector might be:

\[
\phi(x)=[1,d,s,c,d^2,s^2]
\]

Where:

- \(d\) = standardised depth.
- \(s\) = standardised slope.
- \(c\) = standardised curvature or BPI.

Optional spatial coordinates can be included for experiments investigating geographic relationships.

The model estimates expected survey richness and epistemic uncertainty.

Bayesian linear regression is an approximation for count-valued richness data; its Gaussian noise assumption and uncertainty estimates should be acknowledged and evaluated.

Normalise features consistently using permitted terrain information or development-set statistics, without leaking hidden ecological outcomes.

### Alternative Model: Gaussian Process

If the core system works and benchmark runtime permits, investigate Gaussian process regression using a Matérn kernel.

Possible features:

- Spatial coordinates.
- Depth.
- Slope.
- Bathymetric position.

The GP may offer more flexible spatial predictions, but repeated fitting is computationally expensive.

**Do not make the GP mandatory.**

### What the Interface Should Show

The replay should expose:

- Predicted biodiversity value.
- Model uncertainty.
- How predictions change after surveys.
- Which features influence the model.
- Why particular destinations were selected.

Do not present raw regression coefficients or GP length-scales as definitive causal explanations.

Use feature ablations as stronger evidence of what contributes to performance.

---

## 12. Adaptive Exploration Planning

**Owner: Cam**

The planner chooses where ABYSS should survey next.

It balances:

1. Expected biological value.
2. Information gained by visiting uncertain regions.
3. Exploration of unvisited areas.
4. Energy required to reach and survey a target.
5. Hard return-home constraints.

A simplified objective is:

\[
U(x)=
\frac{
\max(0,\hat y(x))
+
\beta I(x)
+
\gamma C(x)
}{
E_{\mathrm{travel}}(x)+E_{\mathrm{survey}}+\epsilon
}
\]

Where:

- \(\hat y(x)\) = predicted local biological richness or survey value.
- \(I(x)\) = predicted information gain.
- \(C(x)\) = exploration or coverage incentive.
- \(\beta\) = information-gain weight.
- \(\gamma\) = coverage weight.
- \(\epsilon\) = small numerical stabiliser.

For the Bayesian linear model, an approximate information-gain term is:

\[
I(x)=\frac12\log\left(
1+\frac{\phi(x)^T\Sigma\phi(x)}{\sigma_n^2}
\right)
\]

This assumes the defined Bayesian linear model and observation-noise variance.

Keep the number of tunable weights small.

Set parameters on development environments and freeze them before final evaluation.

Potential candidates include:

- High predicted richness.
- High uncertainty.
- A habitat type the robot has rarely sampled.
- Regions close enough to investigate without violating energy constraints.

The planner should only evaluate reachable, safe targets.

Previously visited survey locations should be excluded or heavily discounted.

### Curiosity Must Emerge

The system must never contain a special rule such as:

"If an unusual organism appears, immediately visit the nearest ridge."

The decision should arise from its numerical objective and updated beliefs.

When a biologically interesting observation appears, we can highlight the resulting planning decision in the UI, but not artificially trigger a scripted route change.

---

# PART IV — COMPUTER VISION

## 13. Marine Perception System

**Owner: Ammar**

The computer-vision module processes real underwater biological imagery and produces recognitions or unfamiliarity scores.

The pipeline should initially use annotated organism image crops from FathomNet.

This avoids making the whole project depend on detecting objects in complicated raw underwater video.

### Primary Pipeline

1. Download a manageable collection of annotated FathomNet images.
2. Crop organisms using available bounding boxes.
3. Preprocess and resize images using OpenCV or Pillow.
4. Extract pretrained visual embeddings.
5. Build a nearest-neighbour reference database.
6. Compare test images with familiar-category references.
7. Return closest category, similarity score and novelty score.
8. Evaluate familiar and withheld categories separately.

### Preferred Model

Start with **DINOv2-small** or another available lightweight image encoder.

Use PyTorch and a pretrained model implementation.

Cache embeddings locally.

Use scikit-learn nearest-neighbour methods for identification and unfamiliarity scoring.

### YOLO26n

Ammar prefers OpenCV and YOLO26n.

YOLO26n can be investigated for organism localisation and object detection, particularly if an appropriate pretrained marine model or suitable annotated data is available.

However:

**YOLO26n is optional for the hackathon MVP.**

A generic object detector is not guaranteed to recognise specialised deep-sea organisms.

YOLO object detection and open-set novelty detection are separate capabilities.

Do not spend hours fine-tuning an object detector if embedding-based recognition already demonstrates the required perception capability.

### Controlled Unknown-Category Evaluation

Divide the selected FathomNet categories into:

- Familiar reference categories.
- Familiar validation/test images.
- Withheld reference-unknown categories.
- Held-out evaluation images.

Prefer separation by dive or original imaging source where practical to reduce near-duplicate leakage.

Use familiar validation images to calibrate a threshold without inspecting the final test outcomes.

Report:

- Familiar-category classification accuracy.
- Unknown-category recall.
- False novelty-alert rate.
- Novelty AUROC, if feasible.

A pretrained encoder may already have encountered similar marine imagery during pretraining. Therefore, this is **reference-unfamiliarity detection**, not proof of discovering a species unknown to science.

### Integration with Simulation

When the robot surveys a waypoint:

1. The simulator identifies the hidden organism categories available at that waypoint.
2. It selects appropriate real images from the prepared observation pool.
3. The perception model processes those images.
4. The robot receives predicted categories and novelty flags.
5. The evaluator retains hidden true categories for scoring.

The realistic-perception planner must not receive the simulator's hidden labels.

### Two Perception Modes

**Ideal perception:** Return the actual simulated organism categories through the observation interface.

**Real perception:** Return the predictions and novelty flags generated from images.

This allows us to isolate planning performance from computer-vision errors.

If real perception is unsuccessful, retain the functional ideal-perception exploration benchmark and present the computer-vision results separately and honestly.

---

# PART V — BASELINES AND EVALUATION

## 14. Exploration Baselines

**Primary owner: Cam, with Rihaan supporting the simulation and benchmark harness.**

Implement the following:

### Lawnmower

Fixed systematic survey pattern.

A simple conventional coverage strategy.

### Frontier

Select reachable, unexplored boundaries based on the survey footprint.

This is an essential baseline because it competes more directly with adaptive exploration.

### Terrain Heuristic

Uses a fixed rule favouring a particular environmental characteristic, such as steep terrain.

It does not learn from observations.

### Random

Selects random feasible targets.

Useful as a basic control, but less important than frontier.

### ABYSS

Uses online habitat learning, uncertainty and adaptive destination selection.

### Omniscient Greedy Reference — Optional

An offline comparison method with access to the hidden map.

This is for research analysis only.

It is not an operationally fair baseline and is not guaranteed to produce a globally optimal route.

Do not present it as a mathematical upper bound.

## 15. Fairness Rules

Every ordinary planner uses:

- Identical terrain.
- Identical hidden organism encounters.
- Identical energy budgets.
- Identical sensing capabilities.
- Identical movement and survey costs.
- Identical home positions.
- Identical safety constraints.

Only the exploration policies differ.

All random generators must use explicit seeds.

For a given world seed, generate the hidden biological environment once and reuse it for every planner.

No ordinary planner can access hidden biodiversity data.

The benchmark evaluator must be a separate trusted component.

---

## 16. Primary Evaluation Metric

The primary metric is:

**Distinct organism categories discovered within a fixed mission energy budget.**

This is easier to interpret than using energy efficiency alone.

Secondary metrics:

- Distinct categories discovered per energy unit.
- Cumulative discoveries versus energy consumed.
- Number of withheld-category encounters.
- Energy to first interesting discovery.
- Area or waypoint coverage.
- Habitat-prediction accuracy.
- Novelty-detection false-positive rate.
- Safe-return verification.

Discovery efficiency alone is insufficient because a robot that discovers one organism and consumes very little energy might appear disproportionately successful.

Always report the total discoveries as well.

## 17. Benchmark Methodology

Begin with approximately 10 independent seeds per scenario.

Increase to 20–50 if runtime allows.

Use the same seeds and environments for each baseline.

Report:

- Mean or median discoveries.
- Paired differences versus baselines.
- Variation across seeds.
- Confidence intervals where sample sizes permit.
- Performance broken down by ecological scenario.

If using multiple terrain crops, consider regional independence when calculating uncertainty intervals. Repeated seeds on a single crop do not establish generalisation across different geographical regions.

### Main Experiment

Evaluate ABYSS's advantage over conventional exploration as environmental predictability changes.

Our hypothesis:

- Random ecology: little advantage from habitat prediction.
- Spatial clusters: potential benefit from learning spatial structure.
- Terrain-dependent ecology: possible improvement from environmental learning.
- Reversed ecology: learned models may outperform fixed incorrect heuristics.
- Nonlinear ecology: the simple learner may struggle.

We will report negative results as well as positive results.

### Important Ablations

Prioritise:

1. ABYSS with online learning disabled.
2. ABYSS without uncertainty/information gain.
3. ABYSS with ideal versus real perception.

Additional feature ablations are optional.

The purpose is to show which components genuinely contribute to performance.

**Do not optimise or select the final benchmark worlds based on where ABYSS wins.**

---

# PART VI — SOFTWARE ARCHITECTURE

## 18. Final Technology Stack

### Shared Python Engine

- Python 3.11
- NumPy
- SciPy
- scikit-learn
- pandas
- Matplotlib
- pytest
- PyYAML
- xarray/netCDF4 for GEBCO if needed

### Computer Vision

- OpenCV
- Pillow
- PyTorch
- DINOv2 or another pretrained image encoder
- scikit-learn nearest neighbours
- FathomNet Python tools or API

### User Interface

**Default:** HTML, CSS, JavaScript Canvas and optional Chart.js.

**Alternative:** Next.js if the team can implement it equally quickly.

The interface will consume reproducible JSON mission logs.

Avoid making the initial product dependent on a continuously running simulation backend.

### Optional Extensions

- FastAPI for generating a new mission.
- Gaussian process regression.
- More sophisticated visualisations.
- YOLO26n detection.
- OBIS integration.

Do not introduce ROS, Gazebo, a heavy game engine, a full 3D physics stack or Docker unless an exceptional reason arises.

---

## 19. Final Repository Structure

Proposed structure:

```text
ABYSS/
│
├── abyss/
│   ├── contract.py
│   ├── config.py
│   ├── terrain.py
│   ├── world.py
│   ├── env.py
│   ├── robot.py
│   ├── run_mission.py
│   │
│   ├── planners/
│   │   ├── base.py
│   │   ├── lawnmower.py
│   │   ├── frontier.py
│   │   ├── random.py
│   │   ├── heuristic.py
│   │   └── adaptive.py
│   │
│   ├── learning/
│   │   └── bayesian.py
│   │
│   └── evaluation/
│       ├── benchmark.py
│       ├── metrics.py
│       └── plots.py
│
├── perception/
│   ├── download.py
│   ├── preprocess.py
│   ├── embed.py
│   ├── novelty.py
│   └── perception.py
│
├── ui/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── logs/
│
├── tests/
│   ├── test_no_leak.py
│   ├── test_safety.py
│   ├── test_reproducibility.py
│   └── test_interfaces.py
│
├── data/
├── results/
├── config.yaml
├── requirements.txt
└── README.md
```

This is the agreed structural direction.

Small adjustments are acceptable if the interfaces remain consistent.

---

## 20. Shared Integration Contracts

**The team must agree on these before independent implementation begins.**

The exact implementation can use Python dataclasses or typed dictionaries, but the fields and behaviour must be consistent.

### Environment

`Environment.reset(seed) -> PublicState`

Initialises a deterministic world and returns public information only.

`Environment.step(target) -> StepResult`

Executes travel and a survey where feasible, applies energy costs, and returns the new public state and observations.

The simulator owns hidden ecology, movement rules, safety and mission completion.

### PublicState

Should include:

- Robot position.
- Home location.
- Remaining energy.
- Public environmental features.
- Visited waypoint information.
- Current discovery inventory as perceived by the robot.
- Mission status.

It must not include hidden species distributions or future encounters.

### Observation

Should include:

- Survey waypoint.
- Environmental feature values.
- Observed or predicted organism categories.
- Image references where available.
- Novelty scores or flags.
- Observation energy cost.
- Relevant timestamps or mission-step identifiers.

Ground-truth labels should remain in private evaluation records in realistic-perception mode.

### Planner

`Planner.reset(public_map, config, seed)`

`Planner.choose_target(public_state, observation_history) -> target | HOME`

`Planner.observe(observation)`

The planner selects a feasible destination using its own permitted information.

The simulator independently validates that destination.

### Perception

`Perception.predict(image) -> PerceptionResult`

Contains:

- Predicted known category, if any.
- Classification or similarity score.
- Novelty score.
- Unknown flag.
- Image reference.

### Mission Log

Every planner must export a consistent JSON structure containing:

- World identifier and seed.
- Planner name and frozen configuration.
- Initial public terrain.
- Mission steps.
- Robot position after each step.
- Energy.
- Observations and discoveries.
- Planned target and route.
- Cumulative metrics.
- Completion and safe-return status.

ABYSS additionally exports:

- Predicted richness map.
- Uncertainty map.
- Learned model parameters or useful summaries.
- The numerical components of target-selection utility.

Hidden biodiversity maps may be included in a separate evaluation/reveal payload, never in planner-accessible state.

The UI should replay these logs directly without fabricating or recalculating scientific results.

---

# PART VII — RESPONSIBILITIES

## 21. Rihaan — Simulation, Integration and Frontend

**Role: World and Systems Engineer**

Rihaan owns the environment and the integrated user-facing demonstration.

### Primary Tasks

- Create and manage the shared repository.
- Coordinate `contract.py` and integration decisions.
- Implement the initial 30 × 30 simulation.
- Integrate GEBCO terrain or procedural fallback.
- Compute terrain features.
- Implement hidden organism distributions and world variants.
- Implement movement, sensing and energy accounting.
- Enforce return-home constraints.
- Implement mission execution and JSON logging.
- Support the benchmark harness and environmental tests.
- Build the initial HTML/Canvas replay interface.
- Integrate Cam's planning outputs.
- Integrate Ammar's perception outputs.
- Coordinate the final application and presentation.

### First Deliverable

A simulated robot can complete an entire mission using a dummy planner, return safely and produce a valid mission log.

### Primary Files

`terrain.py`, `world.py`, `env.py`, `robot.py`, `run_mission.py`, `contract.py`, `ui/`

### Important

Prioritise getting the working environment and integration contract finished.

Do not spend several hours polishing the frontend before the simulator and planners run together.

---

## 22. Cam — Machine Learning, Autonomy and Evaluation

**Role: Autonomous Intelligence and Research Engineer**

Cam owns the learning algorithm, exploration policies and scientific evidence.

### Primary Tasks

- Implement Bayesian linear regression with uncertainty.
- Implement online updates after biological observations.
- Create predicted richness and uncertainty maps.
- Implement adaptive survey-target selection.
- Implement information-gain and energy-aware utilities.
- Implement frontier and terrain-aware exploration baselines.
- Help implement random and fixed-coverage baselines.
- Develop benchmark comparisons and metric calculations.
- Tune hyperparameters on development environments only.
- Produce performance charts and ablations.
- Investigate GP regression only if time permits.
- Explain the research methodology during judging.

### First Deliverable

An adaptive planner running against a stub environment that updates its model after observations and changes its destination choices accordingly.

### Primary Files

`learning/bayesian.py`, `planners/adaptive.py`, `planners/frontier.py`, `planners/heuristic.py`, `evaluation/`

### Important

Test learning independently before integrating the full simulator.

The critical achievement is proving that observations genuinely change model predictions and exploration decisions.

---

## 23. Ammar — Computer Vision and Marine Discovery

**Role: Computer Vision Engineer**

Ammar owns the image-processing pipeline and marine biological perception.

### Primary Tasks

- Research suitable FathomNet organism categories.
- Download a manageable annotated image subset.
- Preprocess and crop images using OpenCV.
- Compute pretrained image embeddings.
- Implement nearest-neighbour recognition.
- Implement reference-unfamiliarity scoring.
- Calibrate the novelty threshold.
- Evaluate familiar and withheld categories.
- Investigate YOLO26n where useful.
- Build the image-based discovery gallery.
- Support the replay UI and visual demonstration.
- Provide a clean, offline-capable perception interface.

### First Deliverable

Given a marine organism image, the perception pipeline returns a predicted familiar category, similarity/novelty score and reference information.

### Primary Files

`perception/download.py`, `preprocess.py`, `embed.py`, `novelty.py`, `perception.py`

### Important

Do not make YOLO training the critical path.

Begin with FathomNet organism crops and pretrained visual embeddings.

Ammar should also help Rihaan with the UI after a basic perception pipeline is functioning.

---

# PART VIII — EXECUTION SCHEDULE

## 24. Initial Team Setup

Before working independently:

1. Create the repository.
2. Agree on the shared interfaces.
3. Create `contract.py`.
4. Create a simple environment stub.
5. Create an example mission log.
6. Ensure all three team members can run the same project locally.
7. Establish branches and integration responsibilities.

Use short, frequent commits and merge working code regularly.

Keep `main` runnable.

Only change the shared contract after notifying the other two developers.

Avoid committing huge raw datasets or unnecessary model weights.

## 25. Milestones

### Milestone 1 — Working Core

**Target: First 5–6 hours**

- Small synthetic ocean.
- Hidden biological encounters.
- Functional robot movement.
- Energy and safe-return constraints.
- Mission logging.
- One adaptive planner.
- One conventional baseline.

**Definition of done:** Two planners can independently complete the same deterministic simulated world, and the resulting mission logs are valid.

### Milestone 2 — First Scientific Result

**Target: By approximately hour 10–12**

- Bayesian learning works.
- Frontier baseline works.
- Repeated environment runs.
- At least three ecological scenarios.
- Discovery metrics.
- First comparison chart.

**Definition of done:** We can measure adaptive exploration against conventional exploration on repeated test environments.

### Milestone 3 — Perception and Demonstration

**Target: By approximately hour 17–19**

- FathomNet image pipeline.
- Familiar versus unfamiliar image testing.
- Perception results or documented fallback.
- Side-by-side mission replay.
- Energy and discovery counters.
- ABYSS belief and uncertainty displays.
- Hidden-map reveal.

**Definition of done:** A viewer can watch a real computed mission, inspect the observations and understand why ABYSS changed course.

### Milestone 4 — Final Evaluation and Submission

**Target: Complete before Sunday morning's submission deadline**

- Frozen planner configuration.
- Final benchmark charts.
- Safety and leakage tests.
- README.
- Limitations.
- Backup demonstration.
- Submission materials.
- Rehearsed presentation.

The previously published WHACK schedule lists an **11:00 AM Sunday, 8 November 2026 submission deadline**. Confirm the actual deadline with organisers; unless changed, aim to submit by **10:30 AM**, not 12:30 PM when judging is expected to begin.

Stop adding features early enough to validate and submit reliably.

The suggested checkpoints are targets rather than requirements to continue working without adequate rest. If a milestone slips, reduce scope rather than letting unfinished features block the core.

---

# PART IX — LIVE DEMO

## 26. What the Judges Will See

The application opens to **ABYSS Mission Control**.

Two underwater exploration robots are deployed into the same simulated ocean environment.

One uses conventional exploration.

The other uses ABYSS's adaptive exploration algorithm.

They have the same permitted terrain information, same survey capabilities, same energy budget and same home location.

### Stage 1 — Initial Deployment

Both robots begin surveying.

The biodiversity map is hidden.

The interface displays terrain, robot positions, energy and visited locations.

### Stage 2 — First Biological Observations

Each robot encounters marine organism categories.

The discovery feed can show genuine FathomNet images used as simulated observations.

ABYSS updates its habitat model.

### Stage 3 — Autonomous Behaviour Emerges

ABYSS starts selecting destinations based on the ecological information it has learned.

Its trajectory diverges from the conventional robot.

The interface shows:

- Predicted biological richness.
- Uncertainty.
- Intended next destination.
- The numerical reasons behind the selected target.

This is the most important moment in the presentation.

### Stage 4 — Mission Completion

Both vehicles return safely.

The interface displays:

- Distinct categories discovered.
- Energy consumed.
- Survey coverage.
- Novelty observations.
- Exploration trajectories.

### Stage 5 — Hidden World Reveal

Reveal the simulator's hidden biodiversity distribution.

Compare where the robots explored and what they found.

Then show the benchmark across multiple worlds.

Ideally, demonstrate a scenario where habitat learning helps and another where it does not.

**All numerical results and routes must come from actual execution logs.**

Do not fake a winning example or invent performance percentages.

---

# PART X — TESTING, VALIDATION AND RISK MANAGEMENT

## 27. Mandatory Technical Tests

### No Data Leakage

The planner cannot inspect hidden biodiversity arrays, species-generation parameters or future observations.

Use explicit public-state objects rather than exposing the full environment instance.

### Safe Return

Every ordinary planner completes missions without exceeding the shared energy budget.

### Reproducibility

Identical world seeds, planner seeds and frozen configurations reproduce identical results.

### Learning Behaviour

After receiving observations, ABYSS can update its model, uncertainty and destination preferences.

### Fair Baselines

Every ordinary planner receives the same observations when visiting the same waypoint in the same seeded world.

### Honest Results

The benchmark includes failures and scenarios where adaptive exploration has no meaningful advantage.

## 28. Fallback Strategy

If GEBCO integration fails, continue with documented procedural terrain.

If Gaussian processes are too expensive, use Bayesian regression.

If Bayesian regression performs poorly, use a simpler regularised online model with clearly documented uncertainty limitations.

If computer vision is incomplete, retain ideal perception for the planning benchmark and demonstrate the vision experiments separately.

If YOLO26n fine-tuning proves impractical, omit it.

If the frontend is delayed, use a minimal HTML replay or Matplotlib animation generated from actual logs.

If ABYSS does not outperform baselines, investigate and report when and why.

**Never change the hidden evaluation environment merely to force a favourable result.**

---

# PART XI — WHAT WE ARE NOT CLAIMING

ABYSS does not currently:

- Operate a physical underwater vehicle.
- Provide validated real-world AUV navigation or hydrodynamics.
- Discover organisms previously unknown to science.
- Reconstruct the true biodiversity of a particular region from GEBCO and OBIS.
- Guarantee superior exploration in every environment.
- Establish that an observed habitat relationship is causal.
- Perform centimetre-scale collision avoidance using GEBCO terrain.

Our contribution is a working research prototype that investigates the effectiveness of online biodiversity learning for autonomous underwater exploration.

The scientific credibility of the project depends on keeping these distinctions clear.

---

# PART XII — THE FINAL DELIVERABLES

By the end of WHACK, we want:

**1. A working simulation**

A deterministic underwater grid environment containing hidden marine organism distributions and realistic planning constraints at an abstract level.

**2. A working adaptive exploration algorithm**

ABYSS learns from observations and uses its learned predictions to select future survey destinations.

**3. A reproducible benchmark**

Conventional exploration strategies are compared against ABYSS across multiple hidden environments.

**4. A computer-vision demonstration**

Actual marine imagery is used for familiar-category recognition and reference-unfamiliarity testing, with measured results.

**5. A compelling visual application**

A mission-control interface shows actual robot trajectories, discoveries, energy consumption and evolving model beliefs.

**6. A scientifically credible presentation**

Our conclusions are supported by actual experiment results, with limitations and negative cases clearly explained.

---

# PART XIII — FINAL PROJECT PITCH

**ABYSS — An autonomous explorer that learns where to look next.**

The deep ocean remains one of the least explored environments on Earth. Yet underwater exploration is expensive, time-consuming and limited by the energy available to robotic vehicles.

We're building ABYSS, a curiosity-driven underwater exploration system that learns which environmental conditions are associated with marine biodiversity as it travels.

Instead of following a predefined route, ABYSS analyses observations, estimates which unexplored regions may be biologically interesting, and autonomously adjusts its trajectory to investigate them.

Our system combines marine computer vision, online machine learning, uncertainty-aware exploration and energy-constrained path planning.

We're testing its intelligence in a data-informed simulated ocean, comparing it against conventional survey methods to understand when adaptive exploration can uncover more biological diversity with the same resources.

**Ultimately, we want underwater robots to do more than explore the unknown. We want them to learn from what they discover, and use that knowledge to decide what deserves to be explored next.**

---

# PART XIV — INSTRUCTIONS FOR OUR AI ASSISTANTS

Each team member may share this master specification with their preferred LLM.

When helping with ABYSS, follow these rules.

**1. Respect the agreed architecture.**

Don't independently redesign the project, change its research objective or introduce heavyweight infrastructure without a clear technical justification.

**2. Prioritise working code.**

The project must run and produce real results before adding sophistication.

**3. Respect role ownership.**

- Rihaan: Simulation, systems, integration and frontend.
- Cam: Machine learning, exploration algorithms and evaluation.
- Ammar: Computer vision and marine imagery.

Help each developer implement their assigned modules while keeping shared contracts compatible.

**4. Keep code modular.**

Use clear interfaces, deterministic random seeds, testable functions and reproducible outputs.

**5. Never leak hidden simulator information into the planner.**

Treat this as a strict engineering invariant.

**6. Never fabricate scientific performance.**

All benchmark metrics, discoveries, confidence intervals and model comparisons must be derived from executed experiments.

**7. Explain technical trade-offs.**

If a requested approach is computationally expensive, scientifically questionable or too ambitious for a 24-hour hackathon, identify the problem and propose a practical alternative.

**8. Keep the MVP achievable.**

Do not turn ABYSS into a full robotics operating system, a physical AUV simulation or a general-purpose scientific foundation model.

**9. Work with the current project state.**

When given files or code from another teammate, inspect those actual implementations before proposing modifications. Avoid rewriting functioning modules unnecessarily.

**10. Treat this specification as the baseline.**

If a genuine implementation conflict arises, raise it explicitly and propose the smallest consistent change rather than silently making incompatible architectural decisions.

## Immediate Priority

**The first goal is a complete end-to-end mission:**

A robot explores a hidden simulated ocean, collects biological observations, updates a learned habitat model, selects new destinations, obeys energy constraints, returns home and exports a reproducible mission log.

Everything else builds on that foundation.

**Build the system. Measure the results. Demonstrate what it actually learns.**
