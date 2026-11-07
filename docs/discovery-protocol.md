# Discovery planner experiment protocol

This experiment keeps the frozen `abyss`, `abyss-novelty`, Frontier and the
published benchmark unchanged. Biology is simulated. All planners receive the
same public navigation facts, images, survey costs, budget and return reserve.

The new `abyss-discovery` variant will estimate category occurrence from observed
surveys using terrain and spatial kernels with a global shrinkage prior. Categories
seen frequently receive less weight. Rare-category habitat is a **proxy** for
further discoveries: the robot has no catalogue of undiscovered categories and
cannot claim a calibrated probability for an unseen animal. Short routes discount
overlapping predicted categories. A short initial phase values habitat information.
Unfamiliar-image flags are capped and never counted as new species. Image similarity
is never interpreted as a probability.

Development uses seeds 0–9, all five ecologies on GEBCO and synthetic terrain,
with the unmodified simulation configuration. The fixed candidate grid is rarity
power {0, 0.5, 1} × lookahead {1, 3}; other defaults are fixed before development.
Selection uses the equally weighted mean true distinct count across settings.
All candidates and scores will be retained. No evaluation seed selects parameters.

After selection, evaluate on fresh seeds 3000–3019, across the 18 original terrain /
ecology / signal settings. Compare the selected variant, original ABYSS, Frontier,
lawnmower, Cam's discovery-rate variant, and ablations without learning, rarity,
lookahead, or initial habitat sampling. Report every setting, paired differences,
seed-bootstrap intervals, survey counts, safety and ties. Aggregate intervals
resample whole seeds, retaining the settings belonging to each seed. These are
exploratory intervals, without correction for multiple comparisons.

Also check the four new landforms with the five ecologies on seeds 3000–3004.
Report these separately. Real-image comparisons use the same held-out image pool
and reference artifact for both planners, all five ecologies on seeds 3000–3002;
score both true encounters and perceived labels, and compare robust vision updates
with the same planner without those safeguards. Any unavailable image/model assets
must be reported. Do not change the world distribution, evaluation seeds, Frontier,
or safety rules to manufacture wins. Losses remain in the report.

Development outcome: the six candidates completed 600 missions. Rarity power 1
and one-stop planning scored highest (12.54 mean categories; the full table and
individual rows are in `discovery-development.json`). Before opening the fresh
evaluation, those settings were frozen. The three-stop option remains available
as `abyss-discovery-route` and is compared explicitly instead of repeating the
identical one-stop ablation. Enabling every module is not assumed to help.

The original planner remains the default. Replay generation will accept an explicit
planner selection so the experimental variant and its observation inspector can
be viewed without relabelling old logs or overwriting published results.
