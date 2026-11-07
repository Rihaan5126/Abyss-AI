"""Evaluator-only diagnostics. Never pass these labelled records to a planner."""

from collections import Counter
import hashlib
import math
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support


def rate(hits, total):
    if not total:
        return {'hits': hits, 'total': total, 'rate': None, 'wilson95': None}
    p, z = hits / total, 1.959963984540054
    den = 1 + z*z/total
    center = (p + z*z/(2*total))/den
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/den
    return {'hits': hits, 'total': total, 'rate': p, 'wilson95': [center-half, center+half]}


def diagnostics(predictions):
    labels = sorted({r['true_category'] for r in predictions} |
                    {r['predicted_category'] for r in predictions if r['predicted_category']}) + ['Unfamiliar']
    truth = [r['true_category'] for r in predictions]
    predicted = [r['predicted_category'] or 'Unfamiliar' for r in predictions]
    precision, recall, f1, counts = precision_recall_fscore_support(
        truth, predicted, labels=labels, zero_division=0)
    per_category = {label: {'count': int(n), 'precision': float(p), 'recall': float(r), 'f1': float(f),
                           'predicted_count': predicted.count(label)}
                    for label, p, r, f, n in zip(labels, precision, recall, f1, counts)}
    for label, stats in per_category.items():
        subset=[r for r in predictions if r['true_category']==label]
        stats['unfamiliar_flags']=sum(r['is_unknown'] for r in subset)
        stats['withheld']=bool(subset) and all(r['true_unknown'] for r in subset)
    known = [r for r in predictions if not r['true_unknown']]
    unknown = [r for r in predictions if r['true_unknown']]
    return {'confusion': {'labels': labels, 'rows_true_columns_predicted': confusion_matrix(
                truth, predicted, labels=labels).tolist()}, 'per_category': per_category,
            'classification': rate(sum(r['predicted_category']==r['true_category'] for r in known),len(known)),
            'false_alerts': rate(sum(r['is_unknown'] for r in known),len(known)),
            'unknown_recall': rate(sum(r['is_unknown'] for r in unknown),len(unknown)),
            'interval_note': 'Wilson intervals assume independent images; shared dives reduce independence.'}


def error_kind(row):
    if row['true_unknown']:
        return 'correct unknown' if row['is_unknown'] else 'missed unknown'
    if row['is_unknown']:
        return 'false alert'
    return 'correct classification' if row['predicted_category']==row['true_category'] else 'misclassification'


def audit(rows):
    """Flag suspicious data without silently relabelling or deleting real animals."""
    issues, thumbs, hashes = [], {}, {}
    per_category = {}
    for row in rows:
        info = per_category.setdefault(row['category'], {'images':0, 'sources':set()})
        info['images'] += 1
        info['sources'].add(row['source_id'])
        try:
            with Image.open(row['image_path']) as image:
                rgb = image.convert('RGB')
                pixels = np.asarray(rgb)
                thumb = np.asarray(rgb.resize((32,32)),dtype=float)
                gray = np.asarray(rgb.convert('L').resize((9,8)))
                bits = (gray[:,1:] > gray[:,:-1]).flatten()
                dhash = sum(int(bit)<<i for i,bit in enumerate(bits))
                digest = hashlib.sha256(pixels.tobytes()+str(rgb.size).encode()).hexdigest()
                flags = []
                if min(rgb.size)<24: flags.append('small crop')
                if pixels.std()<5: flags.append('low contrast; review before excluding')
                if row.get('crop_sha256') and hashlib.sha256(Path(row['image_path']).read_bytes()).hexdigest()!=row['crop_sha256']:
                    flags.append('crop checksum mismatch')
                box = row.get('bbox')
                if box and (not all(math.isfinite(float(box[k])) for k in ('x','y','width','height'))
                            or box['width']<=0 or box['height']<=0): flags.append('invalid annotation box')
                if flags: issues.append({'sample_id':row['sample_id'],'flags':flags})
                thumbs[row['sample_id']] = (thumb,dhash,digest,row)
                hashes.setdefault(digest,[]).append(row['sample_id'])
        except (OSError, ValueError) as exc:
            issues.append({'sample_id':row['sample_id'],'flags':[str(exc)]})
    pairs=[]
    keys=sorted(thumbs)
    for i,a in enumerate(keys):
        ta,ha,da,ra=thumbs[a]
        for b in keys[i+1:]:
            tb,hb,db,rb=thumbs[b]
            if da==db or ((ha^hb).bit_count()<=4 and np.abs(ta-tb).mean()<3):
                pairs.append({'a':a,'b':b,'cross_split':ra.get('split')!=rb.get('split'),
                              'different_labels':ra['category']!=rb['category']})
    return {'counts': {c:{'images':v['images'],'sources':len(v['sources'])} for c,v in per_category.items()},
            'issues':issues,'duplicate_candidates':pairs,
            'licences': dict(Counter(r.get('image_license','missing') for r in rows)),
            'warning':'Thumbnail matching is a screening heuristic, not proof of independence. Review labels and dives manually.'}


def group_duplicates(rows, audited):
    parent={r['sample_id']:r['sample_id'] for r in rows}
    def root(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]];a=parent[a]
        return a
    for pair in audited['duplicate_candidates']:
        parent[root(pair['a'])]=root(pair['b'])
    return [{**r,'near_duplicate_group':root(r['sample_id'])} for r in rows]


def mission_analysis(reveal):
    records=[r for obs in reveal['true_observations'] for r in obs['images']]
    def convert(r):
        return {**r,'true_unknown':r['withheld']}
    unique={}
    for row in records:
        ref=row['image_ref']
        if ref in unique and any(row[k]!=unique[ref][k] for k in (
                'true_category','predicted_category','is_unknown')):
            raise ValueError('Same image has inconsistent predictions or labels')
        unique[ref]=row
    return {'encounter_weighted': diagnostics([convert(r) for r in records]),
            'unique_images':diagnostics([convert(r) for r in unique.values()]),
            'encounters':len(records),'unique_count':len(unique),
            'explanation':'Repeated images change encounter weighting; neither view estimates generalisation to new dives.'}
