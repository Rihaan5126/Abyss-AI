# Experimental category-aware discovery planner

Generated from recorded matched missions; every world setting is included.

Perception: facebook/dinov2-small@ed25f3a31f01632728cabb09d1542f84ab7b0056:cls:resize256-crop224-imagenet:v1:pillow12.3.0:weighted-knn5. Biology is simulated. Seeds: 3000–3002.

60/60 safe returns; 0 forced returns.

The discovery score is a rare-habitat proxy, not a calibrated number of unseen species. Fewer surveys are not themselves success. Original ABYSS and Frontier are unchanged.

| Planner | Mean true categories | Mean perceived labels | Mean survey stops | Discovery minus planner [95% CI] |
| --- | --- | --- | --- | --- |
| abyss-discovery | 7.87 | 6.67 | 39.40 | — |
| abyss | 8.27 | 6.73 | 33.87 | -0.40 [-1.00, +0.40] |
| frontier | 6.67 | 5.87 | 44.00 | +1.20 [+0.20, +2.60] |
| abyss-discovery-unguarded | 8.13 | 7.00 | 40.07 | -0.27 [-0.60, +0.20] |

Intervals resample whole seeds across settings. No multiple-comparison correction; these estimates do not prove general superiority or real-ocean performance.

| Terrain | Ecology / signal | Discovery | ABYSS | Frontier | Discovery − Frontier [95% CI] |
| --- | --- | --- | --- | --- | --- |
| gebco_2025 | random / 0 | 8.33 | 7.67 | 9.00 | -0.67 [-1.00, +0.00] |
| gebco_2025 | clustered / 1 | 7.00 | 8.33 | 5.67 | +1.33 [-2.00, +6.00] |
| gebco_2025 | ridge / 1 | 9.67 | 11.00 | 7.00 | +2.67 [+1.00, +4.00] |
| gebco_2025 | reversed / 1 | 6.33 | 7.67 | 6.67 | -0.33 [-1.00, +0.00] |
| gebco_2025 | nonlinear / 1 | 8.00 | 6.67 | 5.00 | +3.00 [+0.00, +7.00] |

All per-mission scores, perceived counts, survey counts, available categories, energy and safety are retained in the accompanying JSON. See [the protocol](discovery-protocol.md) and [implementation and usage](discovery-planner.md).
