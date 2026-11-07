"""Build a local 3D-compatible replay using real perception and held-out images."""

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil

from abyss.config import SCENARIOS, load_config
from abyss.fathomnet_perception import load_fathomnet, read_test_rows
from abyss.planners import PLANNERS
from abyss.run_mission import run_mission, validate_mission_log


def build(config_path, kit, out_dir=Path('ui/vision-logs'), seed=1000,
          scenario='ridge', ui_root=Path('ui'), rows=()):
    """``rows`` are manifest rows, used only to credit each displayed photo on screen."""
    by_path = {row['image_path']: row for row in rows}
    credits = {}
    out_dir, ui_root = Path(out_dir).resolve(), Path(ui_root).resolve()
    prefix = out_dir.relative_to(ui_root).as_posix()
    images = out_dir / 'images'
    images.mkdir(parents=True, exist_ok=True)
    config = replace(load_config(config_path), scenario=scenario, perception_mode='real',
                     n_categories=len(kit['image_pool'].categories))
    entries = []
    for name in ('frontier', 'abyss'):
        print(f'Computing {name} with real image predictions...', flush=True)
        log, reveal = run_mission(config, PLANNERS[name](), seed, **kit)
        validate_mission_log(log)
        # Rewrite display references only after the planner has finished. No labels
        # or private reveal data enter the planner, and all filenames stay opaque.
        for step in log['steps']:
            obs = step['observation']
            if obs is None:
                continue
            display_refs = []
            for ref in obs['image_refs']:
                source = Path(kit['image_pool'].load(ref))
                filename = hashlib.sha256(ref.encode()).hexdigest() + source.suffix
                target = images / filename
                shutil.copyfile(source, target)
                display_refs.append(f'{prefix}/images/{filename}')
                row = by_path.get(str(source))
                if row:
                    credits[f'{prefix}/images/{filename}'] = {
                        'source': 'FathomNet', 'license': row.get('image_license', 'licence not recorded'),
                    }
            obs['image_refs'] = display_refs
        stem = f'{log["world"]["id"]}-{name}'
        (out_dir / f'{stem}.json').write_text(json.dumps(log, separators=(',', ':')))
        (out_dir / f'{stem}.reveal.json').write_text(json.dumps(reveal, separators=(',', ':')))
        entries.append({'world_id': log['world']['id'], 'scenario': scenario, 'rho': config.rho,
                        'seed': seed, 'planner': name, 'label': 'ABYSS' if name == 'abyss' else 'Frontier',
                        'log': f'{prefix}/{stem}.json', 'reveal': f'{prefix}/{stem}.reveal.json'})
        print(f'{name}: {log["outcome"]["surveys"]} surveys; safe home: {log["outcome"]["safe_return"]}', flush=True)
    manifest = {'entries': entries, 'image_credits': credits, 'notice': (
        'Real-image perception replay of computed missions. Biology is simulated. '
        'Local analysis only: image credits and licences are in your source dataset manifest; '
        'do not publish restricted crops. The 3D scene is a visualisation, not camera footage.')}
    (out_dir / 'index.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--manifest', default='data/perception-expanded-images/manifest.json')
    parser.add_argument('--artifact', default='data/perception-expanded')
    parser.add_argument('--seed', type=int, default=1000)
    parser.add_argument('--scenario', choices=SCENARIOS, default='ridge')
    args = parser.parse_args()
    print('Loading the cached DINOv2 model; no image downloads are needed.', flush=True)
    kit = load_fathomnet(args.manifest, args.artifact)
    build(args.config, kit, seed=args.seed, scenario=args.scenario, rows=read_test_rows(args.manifest))
    print('Run: python -m http.server 8000 --directory ui', flush=True)
    print('Open: http://localhost:8000/?missions=vision-logs/index.json', flush=True)


if __name__ == '__main__':
    main()
