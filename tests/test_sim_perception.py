"""Real perception mode: planners see predictions, and truth stays with the evaluator."""

import json
from dataclasses import replace

import pytest
from helpers import RepeatPlanner

from abyss.config import SimConfig
from abyss.contract import PerceptionResult
from abyss.env import Environment
from abyss.planners import RandomPlanner
from abyss.run_mission import run_mission, validate_mission_log
from abyss.stub_perception import StubImagePool, StubPerception

REAL = SimConfig(perception_mode="real", prevalence_max=0.5, prevalence_min=0.1)


def stub_kit(config=REAL, **kwargs):
    pool = StubImagePool(config.n_categories)
    return {"perception": StubPerception(pool, **kwargs), "image_pool": pool}


class ConstantPerception:
    """Always gives the same answer, so its output cannot carry the true label."""

    name = "constant"

    def predict(self, image):
        return PerceptionResult("category_00", 1.0, 0.0, False, image.ref)


class AllUnknownPerception:
    name = "all_unknown"

    def predict(self, image):
        return PerceptionResult(None, 0.0, 1.0, True, image.ref)


class CountingPerception(ConstantPerception):
    def __init__(self):
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return super().predict(image)


class LeakyPool(StubImagePool):
    def images_for(self, category):
        return (f"images/{category}/001.jpg",)


def _survey_until_seen(env, count=12):
    observations = []
    for row in range(count):
        observations.append(env.step((row, 2)).observation)
    return observations


def test_modes_require_matching_arguments():
    with pytest.raises(ValueError):
        Environment(REAL)
    with pytest.raises(ValueError):
        Environment(SimConfig(), **stub_kit())


def test_planner_sees_model_output_not_truth():
    pool = StubImagePool(REAL.n_categories)
    env = Environment(REAL, perception=ConstantPerception(), image_pool=pool)
    env.reset(0)
    observations = _survey_until_seen(env)
    assert all(set(o.categories) <= {"category_00"} for o in observations)
    assert any(len(o.image_refs) > 1 for o in observations)
    truth = env.evaluation_record()["true_observations"]
    assert any(set(t["categories"]) - {"category_00"} for t in truth)


def test_image_refs_that_reveal_the_category_are_refused():
    pool = LeakyPool(REAL.n_categories)
    env = Environment(REAL, perception=ConstantPerception(), image_pool=pool)
    with pytest.raises(ValueError, match="reveals category"):
        env.reset(0)


def test_public_log_holds_no_true_labels():
    log, reveal = run_mission(REAL, RandomPlanner(), 0, **stub_kit())
    validate_mission_log(log)
    text = json.dumps(log)
    assert "true_category" not in text and "true_observations" not in text
    assert "true_category" in json.dumps(reveal)
    assert log["provenance"]["perception"] == "stub"


def test_same_cell_gives_same_images_regardless_of_history():
    first = Environment(REAL, **stub_kit())
    second = Environment(REAL, **stub_kit())
    first.reset(3)
    second.reset(3)
    second.step((9, 9))
    obs_a = first.step((5, 5)).observation
    obs_b = second.step((5, 5)).observation
    assert (obs_a.step, obs_b.step) == (1, 2)
    assert replace(obs_a, step=0) == replace(obs_b, step=0)


def test_every_planner_gets_the_same_images_for_a_world():
    kit = stub_kit()
    first, _ = run_mission(REAL, RandomPlanner(), 1, **kit)
    second, _ = run_mission(REAL, RandomPlanner(), 1, **kit)
    assert first == second


def test_repeat_surveys_do_not_inflate_counts_or_rerun_the_model():
    counting = CountingPerception()
    pool = StubImagePool(REAL.n_categories)
    log, _ = run_mission(REAL, RepeatPlanner((3, 3)), 0, perception=counting, image_pool=pool)
    surveys = [s for s in log["steps"] if s["observation"]]
    assert len(surveys) > 1
    assert counting.calls == len(surveys[0]["observation"]["image_refs"])

    log, _ = run_mission(REAL, RepeatPlanner((3, 3)), 0, perception=AllUnknownPerception(), image_pool=pool)
    surveys = [s for s in log["steps"] if s["observation"]]
    images = len(surveys[0]["observation"]["image_refs"])
    assert images > 0
    assert log["outcome"]["unknown_encounters"] == images


def test_unknown_images_count_toward_richness_but_not_discoveries():
    pool = StubImagePool(REAL.n_categories)
    env = Environment(REAL, perception=AllUnknownPerception(), image_pool=pool)
    env.reset(0)
    observations = _survey_until_seen(env)
    seen = [o for o in observations if o.image_refs]
    assert seen
    assert all(o.categories == () for o in seen)
    assert all(o.richness == len(o.image_refs) for o in seen)
    assert env.step((0, 0)).state.discovered == ()


def test_stub_makes_mistakes_and_summary_scores_them():
    _, reveal = run_mission(REAL, RandomPlanner(), 0, **stub_kit())
    summary = reveal["perception_summary"]
    assert summary["model"] == "stub"
    assert summary["images"] == summary["familiar_images"] + summary["withheld_images"]
    assert 0 < summary["familiar_accuracy"] < 1


def test_summary_is_exact_for_known_behaviour():
    pool = StubImagePool(REAL.n_categories)
    _, reveal = run_mission(REAL, RandomPlanner(), 0, perception=AllUnknownPerception(), image_pool=pool)
    summary = reveal["perception_summary"]
    assert summary["familiar_accuracy"] == 0
    assert summary["false_novelty_rate"] == 1
    assert summary["unknown_recall"] in (1, None)


def test_true_discovery_metric_uses_truth_not_predictions():
    pool = StubImagePool(REAL.n_categories)
    log, reveal = run_mission(REAL, RandomPlanner(), 0, perception=ConstantPerception(), image_pool=pool)
    assert log["outcome"]["distinct_categories"] == 1
    assert reveal["true_distinct_count"] > 1


def test_ideal_mode_has_no_images_or_summary():
    log, reveal = run_mission(SimConfig(), RandomPlanner(), 0)
    assert reveal["perception_summary"] is None
    assert all(not s["observation"]["image_refs"] for s in log["steps"] if s["observation"])
