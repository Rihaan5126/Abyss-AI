"""Collect fresh-source crops and freeze splits before running any model."""

import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import shutil

from .dataset import read_manifest, make_splits
from .download import download_categories
from .quality import audit, group_duplicates


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='data/quality')
    p.add_argument('--snapshot',default='examples/perception_quality_manifest.json')
    p.add_argument('--old-manifest',default='examples/perception_expanded_manifest.json')
    p.add_argument('--freeze-only',action='store_true')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    config=json.loads(Path('examples/perception_expanded_config.json').read_text())
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    old=read_manifest(args.old_manifest)
    unknown=['Periphylla periphylla','Crossota rufobrunnea','Gonatus onyx']
    if not args.freeze_only:
        for categories,n,name in [(config['familiar'],60,'familiar'),(unknown,30,'unknown')]:
            manifest=download_categories(categories,output,n,20261107,config['allowed_licenses'],
                                         max_per_source=2,excluded_sources={r['source_id'] for r in old})
            shutil.copyfile(manifest,output/f'{name}.json')
    rows=read_manifest(output/'familiar.json')+read_manifest(output/'unknown.json')
    audited=audit(rows)
    (output/'collection-audit.json').write_text(json.dumps(audited,indent=2)+'\n')
    if any('crop checksum mismatch' in r['flags'] for r in audited['issues']):
        raise ValueError('Corrupted downloaded crop; inspect collection-audit.json')
    if any(p['different_labels'] for p in audited['duplicate_candidates']):
        raise ValueError('Duplicate candidates have conflicting labels; review before freezing')
    grouped=group_duplicates(rows,audited)
    split=make_splits(grouped,config['familiar'],seed=20261107,
                      test_sources={r['source_id'] for r in rows if r['category'] in unknown})
    local=output/'splits.json';local.write_text(json.dumps(split,indent=2)+'\n')
    for row in split:
        row['image_path']='../data/perception-quality-images/crops/'+Path(row['image_path']).name
    snapshot=Path(args.snapshot)
    if snapshot.exists():raise ValueError('Frozen snapshot exists; choose a new snapshot path')
    snapshot.write_text(json.dumps(split,indent=2)+'\n')
    record={'seed':20261107,'familiar':config['familiar'],'withheld':unknown,
            'requested_familiar_per_category':60,'requested_withheld_per_category':30,
            'max_per_source':2,'excluded_old_source_directories':len({r['source_id'] for r in old}),
            'counts':dict(Counter(r['category'] for r in rows)),
            'splits':dict(Counter(r['split'] for r in split)),
            'selection':'Source metadata and conservative thumbnail duplicate grouping only; no model predictions inspected',
            'allowed_licenses':config['allowed_licenses']}
    snapshot.with_suffix('.config.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2),flush=True)


if __name__=='__main__':main()
