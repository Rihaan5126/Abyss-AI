# Benchmark (Cam)

```bash
python -m abyss.evaluation.benchmark --seeds 10
```

Runs every planner on the same hidden world per seed and prints paired differences
(`abyss` minus each planner) with 95% bootstrap intervals and win/tie/loss counts.
The metric is true distinct categories from the reveal file. Seeds 0-999 are for
development and tuning; the final run uses `--seed-offset 1000` with frozen weights.

Planners: `abyss`, `abyss-nolearn` (model never updates), `abyss-noinfo` (beta = 0),
`frontier`, `heuristic` (fixed "steep is good"), `lawnmower`, `random`.

## Tuning and charts

```bash
python -m abyss.evaluation.tune                      # dev seeds 0-19 only
python -m abyss.evaluation.benchmark --seeds 20 --out results/benchmark.csv
python -m abyss.evaluation.plots --csv results/benchmark.csv --out results/figures
```

ABYSS weights are frozen (see the note above `DEFAULTS` in `planners/adaptive.py`).
The 27-setting dev grid moved the mean by less than seed noise, and `coverage: habitat`
(distance in terrain-feature space) did not help, so the original defaults stand.

Known limitation: on `reversed`, ABYSS learns the right sign (negative slope weight)
and finds richer cells, but `lawnmower` finds more *distinct* categories. The model
predicts richness, not novelty, so it keeps returning to one rich habitat full of
already-seen organisms; lawnmower's rows cross every depth niche. A per-category
occurrence model is the planned fix (brief section 11, stretch goal).
