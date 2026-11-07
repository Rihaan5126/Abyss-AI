import json
from pathlib import Path

from abyss.run_mission import validate_mission_log
from scripts.build_vision_replay import build


def test_real_replay_has_valid_paired_logs_and_resolvable_opaque_photos(tmp_path):
    from test_fathomnet_perception import write_manifest, FAMILIAR, FakeEncoder
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception
    from abyss.fathomnet_perception import build_kit

    data = tmp_path / 'data'
    data.mkdir()
    source = write_manifest(data)
    model = fit_perception(read_manifest(source), FAMILIAR, FakeEncoder())
    ui = tmp_path / 'ui'
    manifest = build('config.yaml', build_kit(model, source), ui / 'vision-logs', ui_root=ui)
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
