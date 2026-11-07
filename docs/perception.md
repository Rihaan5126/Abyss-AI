# Marine perception runbook

Owner: Ammar. The package follows the master brief's `Perception.predict(image)`
interface. It does not define or change the team's shared simulation contract.
Python 3.11+ is supported. Inference works on CPU; no fine-tuning or YOLO is required.

## Prepare data

Choose manageable categories with enough independent imaging sources. Start with
three familiar categories and one withheld category. The FathomNet API searches
concepts, but the downloader accepts only boxes whose concept matches the chosen
category (case insensitive), and samples at most one organism per original image.

```bash
python -m perception download \
  --categories Benthocodon Bathochordaeus 'Vampyroteuthis infernalis' Grimpoteuthis \
  --per-category 15 \
  --allow-license CC-BY-NC-ND-4.0 CC-BY-NC-4.0
python -m perception split data/fathomnet/manifest.json \
  --familiar Benthocodon Bathochordaeus 'Vampyroteuthis infernalis' \
  --seed 42
```

The downloader defaults to `CC-BY-4.0` and `CC0-1.0` for both images and annotations.
The example explicitly includes the more restrictive licences found on these
FathomNet categories. **Use those crops for local non-commercial analysis only;
do not redistribute or publish ND crops or the generated gallery.** Choose
appropriately licensed material or obtain permission for a public presentation.
This is not a blanket clearance of FathomNet imagery. The API's licence metadata
must be checked against the original source's terms. Source URLs, FathomNet UUIDs,
contributor attribution, tags, bounding boxes, image/annotation licences and
checksums are retained in the local manifest. Nothing under `data/`, `results/`,
or `.cache/` is committed. FathomNet: <https://database.fathomnet.org/>.

Downloads are capped by per-category count, response size and request timeout.
Failures and actual counts appear in `data/fathomnet/download_report.json`.
API metadata is cached locally so retrying preserves the sampled ordering.
An image download failure is reported; no synthetic image replaces it.

## Split before fitting

`split` groups images by `source_id`, initially the original image URL's parent
directory, which usually identifies a dive archive. Review these IDs before final
evaluation and replace them with better dive/source identifiers when available.
The grouping is conservative, not a proof of biological independence. Exact
duplicate originals and crops merge groups; split validation rejects shared
sources, original IDs, paths and supplied content checksums across splits.
Near-duplicates without identical hashes still need review.

Familiar categories must occur in reference, validation and test sources.
Withheld categories are retained only from test sources and never enter the
reference index or threshold calibration. Withheld rows in other sources are
discarded. Too few sources causes a clear error: collect more independent dives
rather than substituting a random image-level split.

Split creation uses only category/source metadata, never embeddings or recognition
outcomes. Freeze categories, split seed and settings before final evaluation.
The `.config.json` sidecar records the split seed and input manifest checksum.

## Prepare DINOv2 and fit

```bash
python -m perception prepare-model \
  --revision ed25f3a31f01632728cabb09d1542f84ab7b0056
python -m perception fit data/fathomnet/splits.json \
  --familiar Benthocodon Bathochordaeus 'Vampyroteuthis infernalis' \
  --false-alert-rate 0.05 --offline
python -m perception evaluate data/fathomnet/splits.json --offline
python -m perception gallery results/perception.json
python -m perception predict data/fathomnet/crops/YOUR_IMAGE.png --offline
```

`prepare-model` explicitly downloads the actual pretrained model. Later commands
use `--offline` to forbid model network access. Keep `.cache/huggingface`, the
reference artifact, and the image pool with the demonstration. `--model-cache`,
`--embedding-cache` and `--artifact` can point to portable local directories.
DINOv2-small defaults to the pinned commit above. If you override `--revision`,
pass the same value on later commands, including offline ones.
Importing `perception` never downloads a model.

The encoder applies the DINOv2 preprocessing recipe (RGB, shortest edge 256,
bicubic resize, 224 centre crop, ImageNet normalisation) and extracts its CLS
embedding. Weights stay frozen. Embedding caches are keyed by decoded RGB pixels,
dimensions, model commit, Pillow version and preprocessing version, so file renames reuse entries
and changed content/weights do not. Artifacts refuse a mismatched encoder identity.
There is no fallback that presents handcrafted or random features as DINOv2.

Fitting builds a cosine nearest-neighbour index from familiar reference images.
Calibration uses only familiar validation distances. The threshold is their
empirical upper quantile; a score **strictly greater** than it raises an unknown
flag. On a tiny validation set, 5% may round up to the largest observed score.
This controls empirical calibration alerts, not a guaranteed unseen false alert
rate. Novelty is cosine distance in [0, 2], **not a probability**; similarity is
one minus distance in [-1, 1].

The evaluation command loads the saved artifact and verifies the split manifest
checksum against its fitting provenance. It does not refit or recalibrate. It
reports familiar NN accuracy, familiar classification accuracy including unknown
rejections, unknown-category recall, false novelty-alert rate and novelty AUROC.
Counts and per-image predictions make each metric auditable. If performance is
weak, retain the result rather than adjusting the final test split or threshold.

`gallery.html` is a local diagnostic report using the real held-out image crops;
open it directly from disk. It includes evaluator labels, so it must not be used
as planner input. It is not the mission replay frontend owned by Rihaan.

## Integration for Cam and Rihaan

```python
from perception import Perception
from perception.embed import CachedEncoder, DinoV2Encoder

encoder = CachedEncoder(DinoV2Encoder(offline=True))
perception = Perception.load('data/perception', encoder)
result = perception.predict('local/organism_crop.png')
payload = result.to_dict()  # JSON-serialisable; no true biological label
```

Result fields:

| Field | Meaning |
| --- | --- |
| `predicted_category` | Closest familiar category, or `None` when unfamiliar |
| `similarity_score` | Cosine similarity to the closest reference, not confidence |
| `novelty_score` | Cosine distance to that reference |
| `is_unknown` | Distance exceeds the frozen validation threshold |
| `image_reference` | Input path, or `None` for an in-memory Pillow image |
| `nearest_reference` | Reference crop path for inspection |

The simulator chooses an image using its private encounter truth, then passes
**only the image** to perception. Build the public observation from these result
fields. Keep ground-truth category, image-pool labels, the split manifest and
`evaluate` output private to the simulator/evaluator. The planner should not parse
paths as labels. The novelty flag is an encounter attribute, not a new distinct
organism category; repeated unknown alerts must not inflate discovery counts.
Ground-truth discovery metrics belong to the private evaluator.

Ideal perception remains a simulator-side alternative, allowing planning quality
to be benchmarked separately from perception errors. This module deliberately
has no simulator dependency and cannot inspect a hidden map.

## Validation and limitations

The first real-image smoke test is archived in
[`examples/perception_smoke_results.json`](../examples/perception_smoke_results.json),
with source metadata, fixed splits and checksums in
[`examples/perception_smoke_manifest.json`](../examples/perception_smoke_manifest.json).
These contain metadata and numeric results, not images or model weights.
The report's original fit checksum refers to the local split manifest; the archived
manifest rewrites crop paths for portability while retaining sample IDs and splits.

The run downloaded 60 images and retained 46 after excluding withheld categories
from reference/validation sources: 27 references, 9 validation images, 9 familiar
test images, and **only 1 withheld-category test image**.

| Measured smoke-test metric | Result |
| --- | --- |
| Familiar nearest-neighbour accuracy before rejection | 7/9 |
| Familiar classification accuracy including rejection | 5/9 |
| False novelty alerts on familiar test images | 3/9 |
| Withheld-category test images flagged | 1/1 |
| Novelty AUROC | 1.0, based on only one unknown image |

This verifies execution, not reliable open-set recognition. The high AUROC and
unknown recall are particularly uninformative at this sample size. The false
alert rate is much higher than the 5% calibration target. Collect more independent
sources and enlarge validation before drawing conclusions. The frozen test
results have not been used to change the threshold or split.

To recreate the exact image selection without querying current category results:

```bash
python -m perception restore examples/perception_smoke_manifest.json \
  --output data/perception-smoke \
  --allow-license CC-BY-NC-ND-4.0 CC-BY-NC-4.0
python -m perception prepare-model
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m perception fit data/perception-smoke/manifest.json \
  --familiar Benthocodon Bathochordaeus 'Vampyroteuthis infernalis' --offline
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m perception evaluate data/perception-smoke/manifest.json --offline
```

Restoration verifies original file checksums and refuses a changed source image.
It preserves the archived split and licences. The same restrictions on local
analysis apply. Package versions are recorded in the smoke report; matching them
provides a closer reproduction than using unconstrained newer versions.

```bash
python -m pytest -q
```

Tests cover source and duplicate leakage, held-out independence of fitting,
cosine scoring, unknown rejection, calibration ties, artifact compatibility,
pixel/model cache invalidation and annotation cropping. Tests use an explicitly
fake encoder for deterministic arithmetic; they do not claim CV accuracy.
Measured marine recognition results must come from the real DINOv2 pipeline.

This detects unfamiliarity relative to selected references, not species new to
science. Pretraining may have included similar imagery. Crops assume provided
annotations and do not demonstrate detection in raw video. Similar organisms,
backgrounds, lighting and near-duplicates can dominate the embedding distance.
Small samples provide a pipeline smoke test, not a validated marine classifier.
YOLO localisation and larger, dive-reviewed evaluation can be added after the
end-to-end pipeline works.
