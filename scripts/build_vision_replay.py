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


def copy_asset(source, images, prefix):
    source = Path(source)
    filename = hashlib.sha256(source.read_bytes()).hexdigest() + source.suffix
    shutil.copyfile(source, images / filename)
    return f'{prefix}/images/{filename}'


def build(config_path, kit, out_dir=Path('ui/vision-logs'), seed=1000,
          scenario='ridge', ui_root=Path('ui'), rows=(), registry_path=None):
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
    registry = {}
    for name in ('frontier', 'abyss'):
        print(f'Computing {name} with real image predictions...', flush=True)
        start = len(getattr(kit['perception'], 'evidence_records', []))
        log, reveal = run_mission(config, PLANNERS[name](), seed, **kit)
        events = iter(getattr(kit['perception'], 'evidence_records', [])[start:])
        evidence_records = {}
        validate_mission_log(log)
        # Rewrite display references only after the planner has finished. No labels
        # or private reveal data enter the planner, and all filenames stay opaque.
        for step in log['steps']:
            obs = step['observation']
            if obs is None:
                continue
            display_refs = []
            evidence_ids = []
            for image_index, ref in enumerate(obs['image_refs']):
                source = Path(kit['image_pool'].load(ref))
                filename = hashlib.sha256(ref.encode()).hexdigest() + source.suffix
                target = images / filename
                shutil.copyfile(source, target)
                display_refs.append(f'{prefix}/images/{filename}')
                event = next(events, None)
                if event is not None:
                    if event['input_path'] != str(source):
                        raise ValueError('Inference evidence does not match the surveyed image')
                    evidence = json.loads(json.dumps(event['evidence']))
                    input_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                    key = hashlib.sha256(f'{log["world"]["id"]}:{name}:{step["step"]}:{image_index}:{input_hash}:{evidence["artifact_id"]}'.encode()).hexdigest()
                    for neighbor in evidence['neighbors']:
                        reference = neighbor.pop('reference')
                        neighbor['image'] = copy_asset(reference, images, prefix)
                        reference_meta = by_path.get(str(Path(reference).resolve()), {})
                        neighbor['credit'] = {k: reference_meta.get(k) for k in ('attribution','image_license','annotation_license')}
                    evidence.update({'id': key, 'step': step['step'], 'image_index': image_index,
                                     'input': display_refs[-1]})
                    row_meta = by_path.get(str(source), {})
                    evidence['credit'] = {k: row_meta.get(k) for k in ('attribution','image_license','annotation_license')}
                    evidence_records[key] = evidence
                    evidence_ids.append(key)
                    registry[key] = {'input_path': str(source.resolve()), 'artifact_id': evidence['artifact_id'],
                                     'input_sha256': input_hash}
                row = by_path.get(str(source))
                if row:
                    credits[f'{prefix}/images/{filename}'] = {
                        'source': 'FathomNet', 'license': row.get('image_license', 'licence not recorded'),
                    }
            obs['image_refs'] = display_refs
            if evidence_ids: obs['evidence_ids'] = evidence_ids
        stem = f'{log["world"]["id"]}-{name}'
        (out_dir / f'{stem}.json').write_text(json.dumps(log, separators=(',', ':')))
        (out_dir / f'{stem}.reveal.json').write_text(json.dumps(reveal, separators=(',', ':')))
        (out_dir / f'{stem}.evidence.json').write_text(json.dumps(evidence_records, separators=(',', ':')))
        entries.append({'world_id': log['world']['id'], 'scenario': scenario, 'rho': config.rho,
                        'seed': seed, 'planner': name, 'label': 'ABYSS' if name == 'abyss' else 'Frontier',
                        'log': f'{prefix}/{stem}.json', 'reveal': f'{prefix}/{stem}.reveal.json',
                        'evidence': f'{prefix}/{stem}.evidence.json'})
        print(f'{name}: {log["outcome"]["surveys"]} surveys; safe home: {log["outcome"]["safe_return"]}', flush=True)
    manifest = {'entries': entries, 'image_credits': credits, 'notice': (
        'Real-image perception replay of computed missions. Biology is simulated. '
        'Local analysis only: image credits and licences are in your source dataset manifest; '
        'do not publish restricted crops. The 3D scene is a visualisation, not camera footage.')}
    (out_dir / 'index.json').write_text(json.dumps(manifest, indent=2))
    if registry_path is not None:
        registry_path = Path(registry_path)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--manifest', default='data/perception-expanded-images/manifest.json')
    parser.add_argument('--artifact', default='data/perception-expanded')
    parser.add_argument('--seed', type=int, default=1000)
    parser.add_argument('--scenario', choices=SCENARIOS, default='ridge')
    parser.add_argument('--registry', default='data/inspector-registry.json')
    args = parser.parse_args()
    print('Loading the cached DINOv2 model; no image downloads are needed.', flush=True)
    kit = load_fathomnet(args.manifest, args.artifact)
    from perception.dataset import read_manifest
    build(args.config, kit, seed=args.seed, scenario=args.scenario, rows=read_manifest(args.manifest), registry_path=args.registry)
    print('Run: python -m http.server 8000 --directory ui', flush=True)
    print('Open: http://localhost:8000/?missions=vision-logs/index.json', flush=True)


if __name__ == '__main__':
    main()
