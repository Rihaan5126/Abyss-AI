# Experimental category-aware discovery planner

Generated from recorded matched missions; every world setting is included.

Perception: ideal. Biology is simulated. Seeds: 3000–3019.

3240/3240 safe returns; 0 forced returns.

The discovery score is a rare-habitat proxy, not a calibrated number of unseen species. Fewer surveys are not themselves success. Original ABYSS and Frontier are unchanged.

| Planner | Mean true categories | Mean perceived labels | Mean survey stops | Discovery minus planner [95% CI] |
| --- | --- | --- | --- | --- |
| abyss-discovery | 12.67 | 12.67 | 40.14 | — |
| abyss | 13.15 | 13.15 | 35.81 | -0.48 [-0.79, -0.19] |
| frontier | 11.43 | 11.43 | 43.88 | +1.24 [+0.86, +1.62] |
| lawnmower | 12.08 | 12.08 | 39.40 | +0.59 [+0.09, +1.13] |
| abyss-novelty | 12.48 | 12.48 | 30.58 | +0.19 [-0.11, +0.46] |
| abyss-discovery-nolearn | 11.86 | 11.86 | 38.77 | +0.81 [+0.44, +1.18] |
| abyss-discovery-norarity | 12.57 | 12.57 | 41.74 | +0.10 [-0.17, +0.39] |
| abyss-discovery-route | 12.69 | 12.69 | 39.34 | -0.01 [-0.29, +0.23] |
| abyss-discovery-nowarmup | 12.62 | 12.62 | 41.49 | +0.05 [-0.24, +0.34] |

Intervals resample whole seeds across settings. No multiple-comparison correction; these estimates do not prove general superiority or real-ocean performance.

| Terrain | Ecology / signal | Discovery | ABYSS | Frontier | Discovery − Frontier [95% CI] |
| --- | --- | --- | --- | --- | --- |
| gebco_2025 | random / 0 | 12.40 | 12.60 | 13.25 | -0.85 [-1.50, -0.15] |
| gebco_2025 | clustered / 1 | 12.90 | 11.50 | 11.20 | +1.70 [+0.25, +3.30] |
| gebco_2025 | ridge / 0.25 | 13.50 | 13.70 | 13.50 | +0.00 [-0.85, +0.85] |
| gebco_2025 | ridge / 0.5 | 13.95 | 14.80 | 12.75 | +1.20 [+0.45, +1.95] |
| gebco_2025 | ridge / 1 | 13.30 | 15.70 | 10.65 | +2.65 [+1.80, +3.40] |
| gebco_2025 | reversed / 0.25 | 11.80 | 11.85 | 12.80 | -1.00 [-1.75, -0.25] |
| gebco_2025 | reversed / 0.5 | 11.45 | 12.15 | 11.95 | -0.50 [-1.30, +0.25] |
| gebco_2025 | reversed / 1 | 9.90 | 10.65 | 10.50 | -0.60 [-1.40, +0.20] |
| gebco_2025 | nonlinear / 1 | 11.90 | 12.15 | 11.05 | +0.85 [-0.80, +2.65] |
| synthetic | random / 0 | 12.45 | 12.35 | 13.20 | -0.75 [-1.45, -0.05] |
| synthetic | clustered / 1 | 11.90 | 12.40 | 11.00 | +0.90 [-0.25, +2.00] |
| synthetic | ridge / 0.25 | 12.95 | 13.30 | 11.20 | +1.75 [+0.80, +2.75] |
| synthetic | ridge / 0.5 | 13.40 | 13.85 | 9.25 | +4.15 [+2.85, +5.40] |
| synthetic | ridge / 1 | 12.90 | 15.30 | 6.45 | +6.45 [+4.60, +8.15] |
| synthetic | reversed / 0.25 | 12.25 | 12.65 | 12.15 | +0.10 [-1.00, +1.25] |
| synthetic | reversed / 0.5 | 12.80 | 13.15 | 11.50 | +1.30 [+0.35, +2.35] |
| synthetic | reversed / 1 | 14.05 | 14.25 | 10.15 | +3.90 [+2.25, +5.60] |
| synthetic | nonlinear / 1 | 14.30 | 14.35 | 13.15 | +1.15 [+0.25, +2.15] |

All per-mission scores, perceived counts, survey counts, available categories, energy and safety are retained in the accompanying JSON. See [the protocol](discovery-protocol.md) and [implementation and usage](discovery-planner.md).
