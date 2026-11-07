# Running the ABYSS demo

This is the one set of instructions for the demonstration. Everything runs from `main` and
works offline once set up. The model runs when mission logs are generated, not in the browser,
so the demo needs no FathomNet access, model downloads, GitHub or inference service.

## Choose a mode

| | Real-image replay | Ideal-perception replay |
| --- | --- | --- |
| Observations | DINOv2 predictions on real FathomNet crops | Simulator labels, no photos |
| Needs local data | Yes, see below | No, the logs are in the repo |
| Top-left badge | `Real images: dinov2-small...` | `Ideal perception, no images` |
| Benchmark panel | Hidden: it is a different experiment | Shown |

The app picks the real-image replay when `ui/vision-logs/index.json` exists. Otherwise it uses
the ideal logs, and a 404 for that file in the browser console is expected. Check the badge
before presenting, so you know which one is running.

## Set up once, while online

```bash
git switch main
git pull --ff-only origin main
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e '.[vision]'
python -m pytest -q
```

On Windows, activate with `.venv\Scripts\activate` instead.

## Real-image replay

These local files are not in Git, so prepare them once using
[expanded-perception.md](expanded-perception.md):

- `data/perception-expanded-images/manifest.json` and its image crops
- `data/perception-expanded`, the saved operational model
- the cached DINOv2-small weights

Then generate the logs, which runs real inference:

```bash
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay
python -m http.server 8000 --directory ui
```

Open <http://localhost:8000/?missions=vision-logs/index.json>.

Generate another world with `--scenario reversed --seed 1001`. The default, ridge on seed 1000,
was not chosen by outcome. Generated logs and copied crops stay in the ignored `ui/vision-logs/`.
Do not commit or publish them: see [Image licences](#image-licences).

To go back to ideal perception, open <http://localhost:8000/?missions=logs/index.json>.

## Ideal-perception replay

This is also the fallback if anything goes wrong with real images:

```bash
python -m http.server 8000 --directory ui
```

Open <http://localhost:8000/?missions=logs/index.json>.

## During the demo

1. Press **Begin dive**, or **Open console** to skip the sequence. The descent is illustrative.
2. Use **Play**, the timeline, the arrows and the **Speed** menu. **Slow** suits narration.
3. Use **Step through** to control each stage by hand.
4. Use the layers: **Habitats**, **Predicted** and **Uncertainty**. **Charts** is the 2D view.
   In ideal mode, the **World** menu also lists synthetic landforms: a seamount, abyssal hills,
   a trench and a basin. They show other seafloor shapes, but they are not real places and are
   not in the benchmark. Regenerate them with `python -m scripts.build_ui_logs`.
5. Press **Reveal the hidden world** at the end. Hidden data is not loaded before you choose it,
   or before you request the report.
6. Press **Download findings report**, open the file and use **Print / save as PDF**.

## What to say

- Terrain is real GEBCO data. Biology is simulated. Energy is in abstract units.
- The 3D ocean is a visualisation. The robots do not see it, and the model classifies supplied
  crops rather than detecting animals in the scene.
- Photos are simulated encounters, not sightings at those coordinates.
- Novelty is a cosine distance, not a probability. Unfamiliar means unlike our references, not a
  new species.
- The 6,300-mission benchmark uses ideal perception, so vision errors are not in those numbers.
- One mission settles nothing. All GEBCO results share one terrain crop, so they do not show
  performance across other ocean regions.

## Vision results

The operational model stays the default. The follow-up experiment shows trade-offs rather than a
better model. See [perception-quality.md](perception-quality.md).

| Method, on 93 familiar and 71 withheld test images | Familiar correct | False alerts | Withheld flagged |
| --- | --- | --- | --- |
| Old references, nearest neighbour (operational) | 67/93 | 4/93 | 26/71 |
| Fresh references, nearest neighbour | 79/93 | 1/93 | 7/71 |
| Fresh references, frozen voting method | 73/93 | 1/93 | 7/71 |

## Image licences

Some FathomNet crops are non-commercial and no-derivatives, and are marked for local analysis.
The app labels each displayed photo with its source and licence, but that doesn't grant permission.
Do not commit, upload or publish them, including in a recording, unless the licence allows it.
Check the competition's rules before showing them to judges. If in doubt, present ideal perception
and describe the vision results from the table above.

## If something goes wrong

| Problem | Fix |
| --- | --- |
| Page will not load | Check the server is running, then use `http://localhost:8000` on the same laptop |
| Old design appears | Press Ctrl+Shift+R, or Cmd+Shift+R on a Mac |
| No 3D view | The app falls back to **Charts**, which shows the same missions |
| Real-image replay fails | Use the ideal-perception link above |
| Laptop fails | Play the backup recording and present the PDF |

## Release checklist

Automated, and rerun with `python -m pytest -q`:

- [ ] All tests pass on the presenting laptop's Python
- [ ] `git status` is clean at the release tag

By hand, on the presenting laptop:

- [ ] Real-image replay generated, with the badge naming the real model
- [ ] Photos show predictions and unfamiliar flags
- [ ] Full dive watched at full screen with Wi-Fi off
- [ ] Reveal works, and the report downloads and prints to PDF
- [ ] Ideal-perception link tested as the fallback
- [ ] Backup recording made, without restricted images unless permitted
- [ ] Deck exported to PDF
- [ ] Deadline, talk length and image rules confirmed with organisers
