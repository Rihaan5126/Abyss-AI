"""Prepare the frozen expanded image set: python -m perception.expand."""

import argparse
from importlib.metadata import version
import json
import logging
from pathlib import Path

from .dataset import read_manifest
from .download import restore_manifest
from .embed import CachedEncoder, DinoV2Encoder
from .evaluate import evaluate, fit_perception


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='examples/perception_expanded_manifest.json')
    parser.add_argument('--config', default='examples/perception_expanded_config.json')
    parser.add_argument('--images', default='data/perception-expanded-images')
    parser.add_argument('--artifact', default='data/perception-expanded')
    parser.add_argument('--skip-download', action='store_true', help='Reuse a completed local restoration')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    config = json.loads(Path(args.config).read_text())
    manifest = Path(args.images) / 'manifest.json'
    if not args.skip_download:
        print('Downloading the frozen expanded image set (local analysis only)...', flush=True)
        manifest = restore_manifest(args.manifest, args.images, config['allowed_licenses'])
    print('Loading cached DINOv2; run python -m perception prepare-model first if needed.', flush=True)
    encoder = CachedEncoder(DinoV2Encoder(offline=True))
    rows = read_manifest(manifest)
    print('Building references and calibrating on familiar validation images...', flush=True)
    perception = fit_perception(rows, config['familiar'], encoder, config['false_alert_rate'])
    perception.save(args.artifact)
    # Match the regular CLI artifact format so subsequent evaluate commands work.
    import hashlib
    provenance = {
        'manifest_sha256': hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
        'familiar': config['familiar'], 'false_alert_rate': config['false_alert_rate'],
        'software_versions': {p: version(p) for p in ('numpy', 'Pillow', 'scikit-learn', 'torch', 'transformers')},
        'reference_sample_ids': [r['sample_id'] for r in rows if r['split'] == 'reference'],
        'calibration_sample_ids': [r['sample_id'] for r in rows if r['split'] == 'validation'],
    }
    (Path(args.artifact) / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print('Evaluating the held-out images...', flush=True)
    report = evaluate(perception, rows, config['familiar'])
    report['provenance'] = provenance
    Path('results').mkdir(exist_ok=True)
    Path('results/perception-expanded.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report[k] for k in ('counts', 'familiar_nn_accuracy',
                     'familiar_classification_accuracy', 'false_novelty_alert_rate',
                     'unknown_category_recall', 'novelty_auroc')}, indent=2))
    print(f'Ready: python -m perception.demo --artifact {args.artifact}', flush=True)


if __name__ == '__main__':
    main()
