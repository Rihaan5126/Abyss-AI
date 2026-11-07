# ABYSS — Adaptive Biodiversity Exploration

WHACK 2026 · Rihaan, Cam and Ammar.

ABYSS investigates whether an underwater explorer can learn habitat relationships
and discover more organism categories within a fixed energy budget. Terrain and
biological encounters belong to a simulator; this is a software research prototype.

## Ammar's perception pipeline

The `perception/` package implements FathomNet organism cropping, frozen
DINOv2-small embeddings, nearest-neighbour familiar-category recognition,
validation-calibrated reference-unfamiliarity detection, and held-out evaluation.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
# CPU-only PyTorch avoids downloading CUDA libraries on a laptop/server:
python -m pip install 'torch>=2.4,<3' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[vision]'
python -m perception --help
python -m pytest -q
```

See [the perception runbook](docs/perception.md) for data preparation, offline
inference, evaluation, image licensing and the simulator integration interface.
For eight familiar categories plus a withheld dumbo-octopus category, see
[the expanded dataset and Mac demo instructions](docs/expanded-perception.md).
This branch supplies Ammar's module; the simulator, planners and shared mission
contract remain with Rihaan and Cam.
