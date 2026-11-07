# Watch the full system in 3D

This branch combines Rihaan's 3D explorer with Ammar's expanded perception and
Cam's adaptive planner. Two computed missions use the same world, seed, battery
budget and real image model: frontier exploration and ABYSS. The replay displays
their actual routes, discoveries, model beliefs and unfamiliarity flags.

In your Mac project terminal, stop any running demo with Control-C:

```bash
git fetch origin
git switch ammar/vision-3d
source .venv/bin/activate
python -m pip install -r requirements.txt
OMP_NUM_THREADS=2 python -m scripts.build_vision_replay
python -m http.server 8000 --directory ui
```

Open <http://localhost:8000/?missions=vision-logs/index.json>. The view starts in
3D when WebGL is available. Press **Play** or **Guided demo**. Drag to orbit,
scroll to zoom, and use the camera controls to follow a robot. The discovery
feed shows the actual held-out image crops passed to perception. Predicted and
uncertainty layers come from the learned model. Reveal exposes simulated truth
only after you choose it. Before reveal, counters show perceived categories;
after reveal, they can show true encountered categories.

The command uses your existing dataset and artifact at
`data/perception-expanded-images/manifest.json` and `data/perception-expanded`.
It downloads no images or weights. If you have not prepared them, follow
`docs/expanded-perception.md` first. Running from the same project folder keeps
your existing ignored data files available when switching branches.

You are watching a replay of real calculations. The simulation and image
predictions finish before Play; the browser animates their recorded results.
This is not a live simulation backend or physical robot footage. Terrain
interpolation, vehicle altitude and lighting are presentation effects.

Generate another world with `--scenario reversed --seed 1001`, then refresh the
page. The default uses ridge ecology, seed 1000; it was not selected by result.
Generated files stay under ignored `ui/vision-logs/`, including copied image
crops. The standard ideal-perception logs are preserved and still accessible
at <http://localhost:8000/>. The official ideal-perception benchmark panel is
not shown for this separate real-image replay.

This is a local analysis demo. Original source attribution, image and annotation
licences remain in your dataset manifest. Restricted image crops are excluded
from Git; do not publish or redistribute ND crops without appropriate rights.
