"""Mission flow, log format and discovery accounting."""

import json

from helpers import RepeatPlanner

from abyss.config import SimConfig
from abyss.contract import HOME, MissionStatus
from abyss.env import Environment
from abyss.planners import PLANNERS, RandomPlanner
from abyss.run_mission import run_mission, validate_mission_log, write_logs


def test_step_returns_contract_fields():
    env = Environment(SimConfig())
    state = env.reset(0)
    assert state.status is MissionStatus.RUNNING
    assert state.position == env.public_map.home

    result = env.step((2, 3))
    assert result.accepted and not result.done
    assert result.route[0] == (0, 0) and result.route[-1] == (2, 3)
    assert result.observation.waypoint == (2, 3)
    assert result.state.surveyed[2, 3]
    assert result.energy_survey == SimConfig().survey_cost

    final = env.step(HOME)
    assert final.done and final.observation is None
    assert final.state.position == env.public_map.home
    assert not final.state.feasible.any()


def test_repeat_surveys_do_not_inflate_discoveries():
    log, reveal = run_mission(SimConfig(), RepeatPlanner((3, 3)), 0)
    observed = [s["observation"]["categories"] for s in log["steps"] if s["observation"]]
    assert len(observed) > 1
    assert all(categories == observed[0] for categories in observed)
    assert log["outcome"]["distinct_categories"] == len(observed[0])
    assert reveal["true_distinct_count"] == len(observed[0])


def test_ideal_perception_matches_private_record():
    log, reveal = run_mission(SimConfig(), RandomPlanner(), 1)
    perceived = [s["observation"]["categories"] for s in log["steps"] if s["observation"]]
    assert perceived == [o["categories"] for o in reveal["true_observations"]]
    assert log["outcome"]["distinct_categories"] == reveal["true_distinct_count"]


def test_logs_round_trip_through_json(tmp_path):
    log, reveal = run_mission(SimConfig(), RandomPlanner(), 0)
    validate_mission_log(log)
    log_path, reveal_path = write_logs(log, reveal, tmp_path)
    assert json.loads(log_path.read_text()) == log
    assert json.loads(reveal_path.read_text()) == reveal
    assert log["provenance"]["biology"] == "simulated"


def test_diagnostics_reach_the_log():
    class Reporting(RandomPlanner):
        name = "reporting"

        def diagnostics(self):
            return {"note": "hello"}

    log, _ = run_mission(SimConfig(), Reporting(), 0)
    assert log["steps"][0]["planner_diagnostics"] == {"note": "hello"}


def test_registry_builds_planners():
    assert PLANNERS["random"]().name == "random"
