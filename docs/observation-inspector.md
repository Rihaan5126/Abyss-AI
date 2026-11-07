# Observation Inspector

The inspector connects an actual image prediction to the public mission record.
It does not add full-frame animal detection or a live camera. The 3D scene remains
a replay of calculated routes; animal crops are supplied as simulated encounters.

## Run on your Mac

Stop your previous server with Control-C. From the project folder with the
virtual environment active. Use a checkout containing this feature (the PR
branch before merge, or updated main after merge):

```bash
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay
OMP_NUM_THREADS=2 python -m perception.inspector_server --port 8001
```

Open <http://localhost:8001>. Generate a replay after updating: old logs do not
contain rich inference evidence. The default commands use the original expanded
model and images, preserving the operational default. No images or weights are
downloaded; the existing offline model cache and dataset must be available.

To explicitly use the experimental quality model instead, supply matching
options to both commands:

```bash
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay \
  --manifest data/perception-quality-images/manifest.json \
  --artifact data/perception-quality
OMP_NUM_THREADS=2 python -m perception.inspector_server \
  --artifact data/perception-quality --port 8001
```

The registry defaults to `data/inspector-registry.json`; keep the same generated
registry with its replay. On Safari use Option-Command-R after changing versions.

## Use it

Open the console or begin a dive. After a survey, click a side-panel animal photo
or **Inspect observation** in a survey-feed entry. Each image has a numbered
selector. The panel shows the exact crop, predicted category, unfamiliarity
distance, frozen threshold, and reference evidence. A multi-neighbor artifact
shows every neighbor used, its known reference label and inverse-distance vote.
The nearest reference need not have the same category as the voting winner.
Similarity is resemblance, not calibrated confidence. Unfamiliarity is relative
to the reference collection, not a new species.

The **How this entered the mission** section uses public observations and
diagnostics only: delivered richness, update counts when recorded, and the next
planned action. Next-target utility comes from the following step's decision,
not the target just visited. Returning home is named explicitly. Before/after
predicted richness is shown at the surveyed cell where maps exist. Missing
prior values and non-learning planners are labelled rather than invented.
Chronological links do not establish that an individual image caused a turn.

The selection stays fixed during playback, pause and scrubbing. Close the panel
to return to side cards or select another robot. Mission/world changes clear
stale selections. Empty surveys, ideal perception and old logs have explicit
explanations. Map-marker picking is not added: photos and survey-feed entries
provide the selection controls without changing the renderer's geometry.

## Recorded evidence versus fresh inference

Mission generation captures prediction and evidence together from one encoder
call. The JSON records whether that call reused a cached embedding, its measured
encoding/matching duration, model identity, threshold, neighbors and votes.
It does not pretend that playback is live inference.

**Reanalyse this image** calls the locally loaded raw DINOv2 encoder, bypassing
the embedding cache. Saved weights and reference vectors are reused; model
loading is excluded from the displayed timing. Results appear separately and
never overwrite the replay, routes, counters, model updates or report. If the
loaded artifact differs, the panel says so before reanalysis and with its result.

Static hosting remains supported:

```bash
python -m http.server 8001 --directory ui
```

Recorded evidence still opens there, but reanalysis is disabled with an
explanation. Use the inference server to enable it. No external image upload or
new web framework is involved.

## Data boundaries and compatibility

No shared simulation contract or planner input changes. The adapter captures
evidence privately; after execution, the replay builder exports optional
`evidence_ids` and per-mission `.evidence.json` files. It copies opaque-named
input/reference assets with source attribution/licence metadata. It does not
export the input's true category, withheld status, hidden map or private paths.
Reference labels are legitimate model knowledge. Existing logs remain readable.

The private registry is outside the served `ui/` tree. The API accepts registered
image IDs only, verifies input checksums, rejects cross-origin requests, and
returns no file paths. It binds to 127.0.0.1 by default. Do not expose this local
analysis server publicly. Evidence files, registry, image crops and weights
remain uncommitted. Restricted image licences still apply to local galleries
and reference crops; the inspector does not clear public redistribution rights.

The findings report remains evaluator-facing and loads hidden truth only on an
explicit report action. The latest team's removal of the map-reveal control is
preserved. Opening the inspector never fetches hidden-truth files.
