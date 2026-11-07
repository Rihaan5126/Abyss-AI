# Experimental category-aware discovery planner

Generated from recorded matched missions; every world setting is included.

Perception: ideal. Biology is simulated. Seeds: 3000–3004.

300/300 safe returns; 0 forced returns.

The discovery score is a rare-habitat proxy, not a calibrated number of unseen species. Fewer surveys are not themselves success. Original ABYSS and Frontier are unchanged.

| Planner | Mean true categories | Mean perceived labels | Mean survey stops | Discovery minus planner [95% CI] |
| --- | --- | --- | --- | --- |
| abyss-discovery | 12.92 | 12.92 | 39.17 | — |
| abyss | 12.87 | 12.87 | 34.62 | +0.05 [-0.26, +0.35] |
| frontier | 11.32 | 11.32 | 41.00 | +1.60 [+0.95, +2.25] |

Intervals resample whole seeds across settings. No multiple-comparison correction; these estimates do not prove general superiority or real-ocean performance.

| Terrain | Ecology / signal | Discovery | ABYSS | Frontier | Discovery − Frontier [95% CI] |
| --- | --- | --- | --- | --- | --- |
| synthetic_seamount | random / 0 | 13.20 | 12.20 | 12.60 | +0.60 [+0.20, +1.00] |
| synthetic_seamount | clustered / 1 | 11.80 | 12.20 | 10.40 | +1.40 [+0.00, +2.80] |
| synthetic_seamount | ridge / 1 | 15.00 | 15.00 | 12.00 | +3.00 [+1.60, +4.40] |
| synthetic_seamount | reversed / 1 | 14.00 | 14.00 | 14.00 | +0.00 [-0.60, +0.60] |
| synthetic_seamount | nonlinear / 1 | 11.80 | 10.80 | 11.60 | +0.20 [-4.00, +2.80] |
| synthetic_abyssal_hills | random / 0 | 12.40 | 12.00 | 12.60 | -0.20 [-1.20, +0.60] |
| synthetic_abyssal_hills | clustered / 1 | 10.40 | 9.60 | 11.00 | -0.60 [-4.20, +2.40] |
| synthetic_abyssal_hills | ridge / 1 | 16.00 | 16.00 | 9.40 | +6.60 [+5.60, +7.60] |
| synthetic_abyssal_hills | reversed / 1 | 12.20 | 13.80 | 10.60 | +1.60 [+0.80, +2.40] |
| synthetic_abyssal_hills | nonlinear / 1 | 12.60 | 13.60 | 11.80 | +0.80 [-5.20, +6.00] |
| synthetic_trench | random / 0 | 12.00 | 12.80 | 12.80 | -0.80 [-2.40, +0.60] |
| synthetic_trench | clustered / 1 | 12.20 | 11.80 | 10.80 | +1.40 [+0.20, +3.20] |
| synthetic_trench | ridge / 1 | 15.80 | 13.00 | 4.20 | +11.60 [+10.80, +12.40] |
| synthetic_trench | reversed / 1 | 11.60 | 13.00 | 12.20 | -0.60 [-3.20, +1.40] |
| synthetic_trench | nonlinear / 1 | 14.00 | 11.20 | 11.00 | +3.00 [+0.40, +5.60] |
| synthetic_basin | random / 0 | 11.60 | 11.40 | 14.00 | -2.40 [-4.40, -0.80] |
| synthetic_basin | clustered / 1 | 10.40 | 11.40 | 11.00 | -0.60 [-3.40, +2.60] |
| synthetic_basin | ridge / 1 | 14.80 | 15.40 | 7.80 | +7.00 [+4.80, +9.40] |
| synthetic_basin | reversed / 1 | 13.20 | 15.80 | 14.00 | -0.80 [-2.00, +0.20] |
| synthetic_basin | nonlinear / 1 | 13.40 | 12.40 | 12.60 | +0.80 [-1.40, +3.00] |

All per-mission scores, perceived counts, survey counts, available categories, energy and safety are retained in the accompanying JSON. See [the protocol](discovery-protocol.md) and [implementation and usage](discovery-planner.md).
