# Expanded marine image set

The original four categories all include deep-sea animals, although their depth
ranges vary. This set adds five familiar reference categories:

| Category | Common description |
| --- | --- |
| Atolla | Helmet jellyfish |
| Solmissus | Midwater jellyfish |
| Scotoplanes | Sea pigs (deep-sea sea cucumbers) |
| Chiroteuthis calyx | Swordtail squid |
| Nanomia bijuga | A colonial siphonophore |

These are organism categories at mixed taxonomic ranks, not nine individual
species. The existing Benthocodon, Bathochordaeus and Vampyroteuthis infernalis
remain familiar. Grimpoteuthis (dumbo octopus) remains withheld from references
and calibration, so the demo still has a reference-unfamiliar test category.
Nanomia can occur across a broad depth range; the collection is marine midwater
and deep-sea imagery, not a claim that every category is exclusively abyssal.

## On your Mac

Stop the running demo with **Control-C**. In the project folder with your virtual
environment activated:

```bash
git pull --ff-only origin ammar/perception-mvp
export SSL_CERT_FILE="$(python -m certifi)"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
OMP_NUM_THREADS=2 python -m perception.expand
OMP_NUM_THREADS=2 python -m perception.demo --artifact data/perception-expanded
```

Open http://localhost:7860. The familiar category list now comes from the loaded
reference artifact. Images for trying the expanded demo are in
`data/perception-expanded-images/crops`. As before, use tightly cropped individual
organisms. The old four-category artifact stays available in `data/perception`.

The preparation command downloads the frozen image selection with a progress
line for every crop, uses your already cached DINOv2 model offline, builds the
new index, calibrates using familiar validation images, and writes actual
held-out metrics to `results/perception-expanded.json`. If DINOv2 is missing,
run `python -m perception prepare-model` first. After a successful image download,
you can repeat fitting without downloading using `python -m perception.expand
--skip-download`.

The snapshot retains original source URLs, image and annotation licences,
attribution, bounding boxes and checksums. Restricted crops are for local
non-commercial analysis; do not redistribute ND crops or publish a gallery
without appropriate permission. Images and weights are not stored in Git.

## Evaluation

The snapshot contains **243 crops**: 134 references, 64 familiar validation crops,
42 familiar test crops, and 3 withheld dumbo-octopus test crops. We initially
downloaded 254 crops; 11 withheld crops in non-test source groups were excluded.
The actual measured results are saved in
`examples/perception_expanded_results.json`:

| Metric | Measured result |
| --- | --- |
| Familiar nearest-neighbour classification before rejection | 30/42 |
| Familiar correct classification after novelty rejection | 28/42 |
| Familiar images falsely flagged unfamiliar | 2/42 |
| Withheld images flagged unfamiliar | 3/3 |
| Novelty AUROC | 0.9841 |

Three unknown test images are too few to establish reliable open-set performance.
Some familiar categories also have very few independent test examples (sea pig:
one; swordtail squid and larvacean: two each). Keep these small counts visible
when presenting the results. The archived report's provenance checksum refers
to the local fit manifest; archived image paths are rewritten for portability.

The category list, seeds and 5% calibration target are frozen in
`examples/perception_expanded_config.json`. Source groups and duplicate originals
are kept across a single split. The original smoke-test results are unchanged.
This expanded set is a separate experiment: different class composition and
held-out samples mean its accuracy cannot be compared directly with the earlier
7/9 result as evidence of improvement. Adding visually similar jellyfish can
make classification harder. An unknown flag remains reference-unfamiliarity,
not proof of a species new to science.
