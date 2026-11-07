import hashlib
from http.server import HTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
import pytest

from perception import Perception
from perception.novelty import ReferenceIndex
from perception.inspector_server import handler_for


class Encoder:
    identity='test encoder'
    calls=0
    def encode(self, images):
        self.calls+=1
        return np.array([[1.,0.] for image in images])


def model(k=1):
    return Perception(Encoder(),ReferenceIndex(np.array([[1,.01],[1,.011],[1,.012]]),
                      ['a','b','b'],['/private/a.png','/private/b.png','/private/c.png']),1,k)


def test_evidence_is_same_pass_and_same_prediction():
    m=model(3);result,e=m.predict_with_evidence('input')
    assert m.encoder.calls==1
    assert result.predicted_category=='b'
    assert e['result']['predicted_category']==result.predicted_category
    assert e['neighbors'][0]['label']=='a'
    assert len(e['neighbors'])==3 and e['vote_winner']=='b'
    assert e['neighbors'][0]['similarity']==result.similarity_score
    assert not any(k in e['result'] for k in ('true_category','image_reference','nearest_reference'))
    assert m.predict('input')==result


def test_reanalysis_is_fresh_registered_only_and_reports_mismatch(tmp_path):
    path=tmp_path/'input.png';Image.new('RGB',(3,3)).save(path)
    m=model();original=(m.threshold,list(m.index.labels))
    registry={'opaque':{'input_path':str(path),'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'artifact_id':'different artifact'}}
    server=HTTPServer(('127.0.0.1',0),handler_for(m,registry,tmp_path));thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(payload):
        return urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/reanalyse',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
    try:
        with request({'id':'opaque'}) as r:result=json.load(r)
        assert m.encoder.calls==1 and result['embedding_cached'] is False
        assert result['artifact_matches'] is False
        assert '/private/' not in json.dumps(result) and 'input_path' not in result
        assert original==(m.threshold,m.index.labels)
        for invalid in [{'id':'../../etc/passwd'}, {'path':str(path)}, []]:
            with pytest.raises(HTTPError):request(invalid)
        assert m.encoder.calls==1
        path.write_bytes(b'changed')
        with pytest.raises(HTTPError):request({'id':'opaque'})
        assert m.encoder.calls==1
    finally:server.shutdown();server.server_close();thread.join()


def test_cached_encoder_cannot_be_advertised_as_fresh(tmp_path):
    from perception.embed import CachedEncoder
    m=model();m.encoder=CachedEncoder(m.encoder,tmp_path/'cache')
    with pytest.raises(ValueError,match='uncached'):
        handler_for(m,{},tmp_path)


def test_replay_evidence_is_public_and_matches_observation(tmp_path):
    from test_fathomnet_perception import write_manifest, FAMILIAR, FakeEncoder
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception
    from abyss.fathomnet_perception import build_kit
    from scripts.build_vision_replay import build
    data=tmp_path/'data';data.mkdir()
    manifest=write_manifest(data)
    m=fit_perception(read_manifest(manifest),FAMILIAR,FakeEncoder())
    ui=tmp_path/'ui'
    index=build('config.yaml',build_kit(m,manifest),ui/'vision-logs',ui_root=ui,registry_path=data/'registry.json')
    registry=json.loads((data/'registry.json').read_text())
    for entry in index['entries']:
        log=json.loads((ui/entry['log']).read_text());evidence=json.loads((ui/entry['evidence']).read_text())
        assert 'true_category' not in json.dumps(evidence)
        assert str(tmp_path) not in json.dumps(evidence)
        for step in log['steps']:
            obs=step['observation']
            if not obs:continue
            for i,key in enumerate(obs.get('evidence_ids',[])):
                e=evidence[key]
                assert e['result']['predicted_category']==obs['image_labels'][i]
                assert e['result']['novelty_score']==pytest.approx(obs['novelty_scores'][i],abs=1e-6)
                assert (ui/e['input']).is_file()
                assert all((ui/n['image']).is_file() for n in e['neighbors'])
                assert key in registry
