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
