# Perception quality experiment

This continues the existing DINOv2 system without changing the planner, simulator
contract, energy rules or published 6,300-mission ideal-perception benchmark.
The earlier 243-image experiment and model remain available.

## What changed

The baseline is preserved and rerun. Reports now separate wrong labels, false
unfamiliarity alerts and missed unknowns; show input and nearest-reference crops;
include per-category counts and confusion matrices; and offer printable local
HTML for inspection. Source attribution and image licences are displayed. These
are evaluator-only reports and must never enter planner observations.

The dataset audit flags small and low-contrast crops, invalid boxes, checksum
errors and duplicate/near-duplicate candidates. A 64-bit difference hash plus a
strict thumbnail pixel-distance test screens near duplicates; conservative
matches are grouped before splitting. It does not prove independent dives or
correct taxonomy. Flagged crops need human review, not automatic deletion.

The new collection excludes all 186 source directories in the inspected old
snapshot and caps each source at two images per category. It contains 547 crops:
60 each for seven familiar categories and 56 sea-pig crops, plus 30 Periphylla
periphylla, 11 Crossota rufobrunnea and 30 Gonatus onyx withheld images. These
three unfamiliar categories include animals visually related to familiar ones.
The original dumbo-octopus test remains in the historical experiment, not the
fresh test. Labels remain at mixed taxonomic ranks; they are organism categories.

The frozen split has 285 references, 98 familiar calibration images, and 164
test images (93 familiar and 71 withheld). All withheld-source groups are test
groups, including familiar samples sharing those sources. No model outcomes
were used to choose sources or splits. Sources, hashes, metadata and settings
are in `examples/perception_quality_manifest.json` and its config sidecar.
Actual counts are recorded when the requested target cannot be reached.

The old test is explicitly development data now. Three predefined methods
(1, 3, 5 inverse-distance-weighted neighbors) were compared on familiar old
development images, using macro category recall before rejection. Five neighbors
was selected, then frozen before fresh-test prediction. Unfamiliarity remains
nearest-reference cosine distance, calibrated only on familiar validation images.
Similarity is not a probability and need not describe the category winning a
multi-neighbor vote. The gallery names its reference accordingly.

The fresh test compares old references/1NN, fresh references/1NN, and fresh
references/the frozen voting method. The second comparison isolates voting;
the first changes both the reference collection and calibration data. Negative
results remain visible. Image-level Wilson intervals assume independence, which
shared dives can violate. A public-ready species recognizer is not established.

## Run on your Mac

**Measured result:** the selected experimental model improves familiar recognition
over the old references (73/93 versus 67/93) but detects fewer unfamiliar examples
(7/71 versus 26/71). Fresh references with plain 1NN score 79/93, better than the
development-selected five-neighbor method. This is retained as a negative voting
result; the final test was not used to switch methods. The existing model remains
the operational default. Do not interpret these changes as uniformly better vision.

The original mission's encounter accuracies were 15/29 (frontier) and 44/95
(ABYSS). On unique familiar images they were 10/17 and 19/32 respectively,
approximately 59% for both. Repeated-image weighting affects those mission
headlines; it does not establish performance on new sources.

From the project folder with the existing virtual environment active:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
export SSL_CERT_FILE="$(python -m certifi)"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
python -m perception restore examples/perception_quality_manifest.json \
  --output data/perception-quality-images \
  --allow-license CC-BY-NC-ND-4.0 CC-BY-NC-4.0 CC-BY-4.0 CC0-1.0
OMP_NUM_THREADS=2 python -m perception.quality_run \
  --manifest data/perception-quality-images/manifest.json
open results/perception-quality/errors.html
open results/perception-quality/findings.md
```

Your old expanded model and manifest must already exist in `data/perception-expanded`
and `data/perception-expanded-images/manifest.json`. DINOv2 is loaded offline from
the existing cache. Restoration reuses checksum-verified crops and shows progress;
reference embeddings are cached by pixels, model and preprocessing identity.
Output and artifact directories must be new to preserve previous experiments.

The error gallery has a portable companion images folder. Use browser Print to
save a local PDF. Do not publish this report's restricted image crops. The JSON
includes a confusion matrix (rows true, columns predicted), per-category metrics
and denominators. Withheld categories have no possible familiar label; their
classification recall is zero by design, and rejection is evaluated separately.

To try the new model interactively:

```bash
OMP_NUM_THREADS=2 python -m perception.demo --artifact data/perception-quality
```

To use it in Rihaan's existing 3D replay:

```bash
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay \
  --manifest data/perception-quality-images/manifest.json \
  --artifact data/perception-quality
python -m http.server 8000 --directory ui
```

Open http://localhost:8000/?missions=vision-logs/index.json. This replays actual
computed routes. It is not a live simulation backend. Unknown alerts do not
become distinct new categories.

For matched old/new/ideal mission analysis:

```bash
OMP_NUM_THREADS=2 python -m scripts.compare_perception_quality \
  --manifest data/perception-quality-images/manifest.json
```

This uses the same 11-category pool and seeds for all modes across ridge, reversed
and random scenarios, two seeds each and two planners (36 missions). It reports
true evaluator discoveries separately from perceived categories and unique-image
vision scores separately from repeated encounters. It is an exploratory mission
check, not an update to the frozen ideal-perception benchmark.

## Further acquisition

The recorded numbers and plain-English findings are in
[`examples/perception_quality_results/findings.md`](../examples/perception_quality_results/findings.md).
That directory also contains the numeric test reports, development selection,
audits and all 36 matched mission records. Image paths in archived numeric reports
use `LOCAL_CROP` placeholders; generate local HTML using the runner instead.
The archived manifests retain source URLs and checksums to restore actual crops.

Validation for this implementation: 225 tests passed; the real DINOv2 upload demo
returned a prediction; the input/reference error gallery loaded in Chromium;
and the experimental artifact ran in the 3D replay with photos and no JavaScript
errors. All 36 matched missions returned safely. Old and new models had identical
true discovery counts for every matched seed/planner/scenario in that small check.
This does not establish equivalence across more seeds or other image pools.

`python -m perception.collect_quality` collects a new bounded snapshot and freezes
it before any model evaluation. Use a new snapshot path; never silently replace
the evaluated one. Crop sidecars support resumption; metadata and crop checksums
prevent unnecessary repeated downloads. Local image rights remain restrictive:
inspect each image and annotation licence before any public presentation.
Neither private processing nor repository metadata clears redistribution rights.

The current audit does not provide expert biological label verification. Neither
source directories nor thumbnail checks guarantee regional independence. Crop
padding, YOLO training and fine-tuning were deferred to keep this experiment
small and distinguish data effects from voting effects.
