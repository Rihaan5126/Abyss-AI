"""Frozen development selection and fresh-source evaluation. No downloads."""

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np

from .dataset import read_manifest, validate_splits
from .embed import CachedEncoder, DinoV2Encoder
from .evaluate import evaluate, fit_perception
from .gallery import write_gallery
from .perception import Perception
from .quality import audit, diagnostics, mission_analysis


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def run(args):
    output=Path(args.output)
    if output.exists():
        raise ValueError('Output already exists; choose a new run directory to preserve earlier results')
    development=read_manifest(args.development_manifest)
    fresh=read_manifest(args.manifest)
    if {r['source_id'] for r in development}&{r['source_id'] for r in fresh}:
        raise ValueError('Fresh evaluation must exclude all previously inspected imaging sources')
    for field in ('image_uuid','original_sha256','crop_sha256'):
        if {r[field] for r in development if r.get(field)} & {r[field] for r in fresh if r.get(field)}:
            raise ValueError(f'Fresh dataset overlaps development {field}')
    output.mkdir(parents=True)
    print('Loading cached DINOv2 and preserving the old baseline...',flush=True)
    encoder=CachedEncoder(DinoV2Encoder(cache_dir=args.model_cache,offline=True),args.embedding_cache)
    old=Perception.load(args.baseline_artifact,encoder)
    if old.neighbors != 1:
        raise ValueError('Baseline must be the original single-neighbor model')
    familiar=sorted(set(old.index.labels))
    validate_splits(fresh,familiar)
    baseline=evaluate(old,development,familiar)
    baseline['diagnostics']=diagnostics(baseline['predictions'])
    write(output/'historical-baseline.json',baseline)
    write_gallery(baseline,output/'historical-errors.html')
    write(output/'development-audit.json',audit(development))
    fresh_audit=audit(fresh)
    write(output/'fresh-audit.json',fresh_audit)
    if any(p['cross_split'] for p in fresh_audit['duplicate_candidates']):
        raise ValueError('Fresh split contains near-duplicate candidates across splits; group them before evaluating')
    combined=audit(development+fresh)
    old_ids={r['sample_id'] for r in development}
    cross=[p for p in combined['duplicate_candidates'] if (p['a'] in old_ids)!=(p['b'] in old_ids)]
    write(output/'cross-development-audit.json',cross)
    if cross:
        raise ValueError('Fresh data has duplicate candidates against inspected development images; review before evaluation')
    # The old test is now explicitly development material. Only familiar rows
    # select k; new final-test pixels and outcomes are not read by selection.
    dev=[r for r in development if r['split']=='test' and r['category'] in familiar]
    embeddings=encoder.encode([r['image_path'] for r in dev])
    candidates=[]
    for k in (1,3,5):
        predicted=old.index.classify(embeddings,k)
        macro=np.mean([np.mean([p==r['category'] for p,r in zip(predicted,dev) if r['category']==c]) for c in familiar])
        candidates.append({'neighbors':k,'development_macro_recall':float(macro),'count':len(dev)})
    selected=max(candidates,key=lambda c:c['development_macro_recall'])['neighbors']
    write(output/'selection.json',{'candidates':candidates,'selected':selected,
                                'rule':'Highest familiar development macro recall; ties prefer smaller k',
                                'old_test_status':'Development; not a new held-out result'})
    print(f'Frozen neighbor count: {selected}. Fitting fresh references and calibration...',flush=True)
    model=fit_perception(fresh,familiar,encoder,.05)
    model.neighbors=selected
    model.save(args.artifact)
    provenance={'manifest_sha256':hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
                'development_manifest_sha256':hashlib.sha256(Path(args.development_manifest).read_bytes()).hexdigest(),
                'familiar':familiar,'false_alert_rate':.05,'neighbors':selected,
                'software_versions':{p:version(p) for p in ('numpy','Pillow','scikit-learn','torch','transformers')}}
    write(Path(args.artifact)/'provenance.json',provenance)
    reports={}
    for name,predictor in [('old-references-1nn',old),('fresh-references-1nn',Perception(encoder,model.index,model.threshold)),
                           ('fresh-references-selected',model)]:
        print(f'Evaluating frozen variant: {name}',flush=True)
        report=evaluate(predictor,fresh,familiar)
        report['diagnostics']=diagnostics(report['predictions']);report['provenance']=provenance
        write(output/f'{name}.json',report)
        reports[name]=report
    write_gallery(reports['fresh-references-selected'],output/'errors.html')
    for i,path in enumerate(args.mission_reveal):
        write(output/f'mission-{i}.json',mission_analysis(json.loads(Path(path).read_text())))
    lines=['# Marine perception findings','',
           'Real underwater crops were evaluated on sources excluded from the previously inspected dataset.',
           'The earlier test set was used only as development data to choose a neighbor-voting method.',
           '', '| Frozen method | Correct familiar | False unfamiliar alerts | Unknowns flagged |',
           '| --- | --- | --- | --- |']
    for name,r in reports.items():
        d=r['diagnostics']
        cell=lambda k:f"{d[k]['hits']}/{d[k]['total']}"
        lines.append(f"| {name} | {cell('classification')} | {cell('false_alerts')} | {cell('unknown_recall')} |")
    lines += ['',f"Selected neighbors: {selected}. Fresh split counts: {dict(Counter(r['split'] for r in fresh))}.",
              'The first comparison changes references and calibration; the next isolates neighbor voting on the same new references.',
              'No method was chosen using the new test outcomes. A worse result remains a result.',
              'Unknown means unfamiliar to the reference collection, not a new species.',
              'Source directories and thumbnail checks reduce leakage but do not establish independent dives.',
              'Image-level Wilson intervals are in the JSON; correlated images can make these intervals optimistic.',
              'Classification metrics do not establish improved mission discoveries. Use matched mission comparisons separately.',
              'Images are local analysis material; do not publish restricted crops or this image gallery.']
    old_d=reports['old-references-1nn']['diagnostics']
    new_d=reports['fresh-references-selected']['diagnostics']
    lines += ['',f"The frozen candidate changed correct familiar identifications from {old_d['classification']['hits']} to {new_d['classification']['hits']}, "
              f"and unknown images flagged from {old_d['unknown_recall']['hits']} to {new_d['unknown_recall']['hits']} on the same test images.",
              'Recommendation: treat this as an experimental artifact; no operational default is replaced. '
              'A recognition gain with worse unfamiliarity detection is a trade-off, not an overall reliability improvement.']
    (output/'findings.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True)
    p.add_argument('--development-manifest',default='data/perception-expanded-images/manifest.json')
    p.add_argument('--baseline-artifact',default='data/perception-expanded')
    p.add_argument('--artifact',default='data/perception-quality')
    p.add_argument('--output',default='results/perception-quality')
    p.add_argument('--model-cache',default='.cache/huggingface')
    p.add_argument('--embedding-cache',default='.cache/embeddings')
    p.add_argument('--mission-reveal',action='append',default=[])
    args=p.parse_args()
    if Path(args.artifact).exists():p.error('Choose a new artifact directory; existing models are preserved')
    run(args)


if __name__=='__main__':main()
