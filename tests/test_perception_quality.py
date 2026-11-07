import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from perception.dataset import make_splits, validate_splits
from perception.novelty import ReferenceIndex
from perception.perception import Perception
from perception.quality import audit, diagnostics, group_duplicates, mission_analysis


def test_weighted_voting_is_not_the_nearest_label_and_survives_reload(tmp_path):
    vectors=np.array([[1,.01],[1,.011],[1,.012]])
    index=ReferenceIndex(vectors,['a','b','b'],['a.png','b.png','c.png'])
    encoder=SimpleNamespace(identity='fake',encode=lambda images:np.array([[1.,0.]]))
    assert Perception(encoder,index,1).predict('x').predicted_category=='a'
    model=Perception(encoder,index,1,3)
    assert model.predict('x').predicted_category=='b'
    model.save(tmp_path)
    assert Perception.load(tmp_path,encoder).predict('x')==model.predict('x')


def test_rejections_and_missed_unknowns_have_correct_denominators():
    rows=[dict(true_category='a',predicted_category='a',true_unknown=False,is_unknown=False),
          dict(true_category='a',predicted_category=None,true_unknown=False,is_unknown=True),
          dict(true_category='b',predicted_category='a',true_unknown=True,is_unknown=False)]
    report=diagnostics(rows)
    assert report['classification']['hits']==1
    assert report['classification']['total']==2
    assert report['false_alerts']['rate']==.5
    assert report['unknown_recall']['hits']==0
    assert report['per_category']['a']['precision']==.5
    json.dumps(report,allow_nan=False)


def test_mission_unique_images_are_not_repeated_encounters():
    a=dict(image_ref='opaque1',true_category='a',predicted_category='a',withheld=False,is_unknown=False)
    b=dict(image_ref='opaque2',true_category='a',predicted_category='b',withheld=False,is_unknown=False)
    result=mission_analysis({'true_observations':[{'images':[a,a,a,b]}]})
    assert result['unique_images']['classification']['rate']==.5
    assert result['encounter_weighted']['classification']['rate']==.75
    assert result['encounters']==4 and result['unique_count']==2


def test_audit_detects_same_pixels_in_different_files_and_labels(tmp_path):
    rows=[]
    for i in range(2):
        p=tmp_path/f'{i}.png';Image.new('RGB',(32,32),'blue').save(p)
        rows.append(dict(sample_id=str(i),category=str(i),image_path=str(p),source_id=str(i),split=str(i)))
    result=audit(rows)
    assert result['duplicate_candidates'][0]['cross_split']
    assert result['duplicate_candidates'][0]['different_labels']
    grouped=group_duplicates(rows,result)
    assert grouped[0]['near_duplicate_group']==grouped[1]['near_duplicate_group']


def test_fresh_sources_guard_before_model_loading(tmp_path):
    from perception.quality_run import run
    rows=[dict(sample_id='a',category='a',source_id='same',image_path='a.png')]
    manifest=tmp_path/'m.json';manifest.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='previously inspected'):
        run(SimpleNamespace(output=str(tmp_path/'out'),manifest=str(manifest),development_manifest=str(manifest)))


def test_forced_unknown_sources_stay_out_of_reference_and_calibration():
    rows=[]
    for i in range(20):
        for category in ('a','b'):
            rows.append(dict(sample_id=f'{i}{category}',category=category,source_id=f's{i}',image_path=f'{i}{category}.png'))
    rows.append(dict(sample_id='u',category='unknown',source_id='s1',image_path='u.png'))
    result=make_splits(rows,['a','b'],seed=42,test_sources=['s1'])
    validate_splits(result,['a','b'])
    assert all(r['split']=='test' for r in result if r['source_id']=='s1')
