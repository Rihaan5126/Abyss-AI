import json
from pathlib import Path

from abyss.run_mission import validate_mission_log
from scripts.build_vision_replay import build


def test_real_replay_has_valid_paired_logs_and_resolvable_opaque_photos(tmp_path):
    from test_fathomnet_perception import write_manifest, FAMILIAR, FakeEncoder
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception
    from abyss.fathomnet_perception import build_kit, read_test_rows

    data = tmp_path / 'data'
    data.mkdir()
    source = write_manifest(data)
    model = fit_perception(read_manifest(source), FAMILIAR, FakeEncoder())
    ui = tmp_path / 'ui'
    rows = [{**row, 'image_license': 'CC0-1.0'} for row in read_test_rows(source)]
    manifest = build('config.yaml', build_kit(model, source), ui / 'vision-logs', ui_root=ui, rows=rows)
    assert manifest['image_credits']
    assert set(next(iter(manifest['image_credits'].values()))) == {'source', 'license'}
    assert all((ui / path).is_file() for path in manifest['image_credits'])
    assert [e['planner'] for e in manifest['entries']] == ['frontier', 'abyss']
    assert len({e['world_id'] for e in manifest['entries']}) == 1
    count = 0
    for entry in manifest['entries']:
        log = json.loads((ui / entry['log']).read_text())
        validate_mission_log(log)
        assert log['provenance']['perception'] == FakeEncoder.identity
        assert 'expected_richness_map' not in json.dumps(log)
        for step in log['steps']:
            obs = step['observation']
            if obs:
                for ref in obs['image_refs']:
                    count += 1
                    assert (ui / ref).is_file()
                    assert not any(c in ref for c in ('jelly', 'squid', 'ghostfish'))
        assert (ui / entry['reveal']).is_file()
    assert count > 0


def test_all_terrains_oceans_keep_pairs_and_a_combined_registry(tmp_path):
    from test_fathomnet_perception import write_manifest, FAMILIAR, FakeEncoder
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception
    from abyss.fathomnet_perception import build_kit
    data=tmp_path/'data';data.mkdir();source=write_manifest(data)
    model=fit_perception(read_manifest(source),FAMILIAR,FakeEncoder())
    ui=tmp_path/'ui';registry=data/'registry.json'
    manifest=build('config.yaml',build_kit(model,source),ui/'vision-logs',ui_root=ui,
                   all_worlds=True,oceans=2,registry_path=registry)
    assert len(manifest['entries'])==36
    assert {e['terrain'] for e in manifest['entries']}=={
        'gebco_2025','synthetic_seamount','synthetic_abyssal_hills','synthetic_trench','synthetic_basin'}
    registered=json.loads(registry.read_text())
    groups={}
    for e in manifest['entries']:
        groups.setdefault((e['terrain'],e['scenario']),set()).add(e['seed'])
        evidence=json.loads((ui/e['evidence']).read_text())
        assert evidence and set(evidence)<=set(registered)
        validate_mission_log(json.loads((ui/e['log']).read_text()))
    assert len(groups)==9
    assert all(seeds=={1000,1001} for seeds in groups.values())
