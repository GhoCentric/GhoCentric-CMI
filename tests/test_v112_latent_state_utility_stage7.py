from copy import deepcopy
import inspect

import pytest

from ghost.api import GhostAPI
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_structural_complexity_stage6 as s6


@pytest.fixture(scope="module")
def short_full():
    return ex.blind_exposure(ex.canonical_levels()[0], "full")


@pytest.fixture(scope="module")
def short_base():
    return ex.blind_exposure(ex.canonical_levels()[0], "baseline")


@pytest.fixture(scope="module")
def overflow_full():
    return ex.blind_exposure(ex.canonical_levels()[1], "full")


@pytest.fixture(scope="module")
def overflow_base():
    return ex.blind_exposure(ex.canonical_levels()[1], "baseline")


def test_canonical_levels_are_pre_registered():
    assert ex.canonical_levels() == [
        {"id": "within_window", "ambient_events": 64},
        {"id": "first_overflow", "ambient_events": 128},
        {"id": "deep_overflow", "ambient_events": 224},
    ]


@pytest.mark.parametrize(
    "raw,message",
    [
        (None, "invalid shape"),
        ({"id": "x"}, "invalid shape"),
        ({"id": "x", "ambient_events": -1}, "non-negative integer"),
        ({"id": "x", "ambient_events": True}, "non-negative integer"),
    ],
)
def test_level_validation_rejects_bad_inputs(raw, message):
    with pytest.raises(ValueError, match=message):
        ex.level(raw)



@pytest.mark.parametrize(
    "signal,expected",
    [
        (1.0, ({"threat": {"hostile": 1.0}}, {"threat": {"benign": 0.5}})),
        (-0.6, ({"threat": {"benign": 0.6}}, {"threat": {"hostile": 0.3}})),
        (0.0, ({}, {})),
    ],
)
def test_evidence_adjustments_cover_all_directions(signal, expected):
    assert ex._evidence_adjustments(signal) == expected



def test_evidence_rejects_missing_ghost_seed(monkeypatch):
    contender = s6.StructuralContender("full", 3)
    monkeypatch.setattr(contender.api, "get_belief", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="belief seed disappeared"):
        ex._evidence(contender, [], "probe", ex.WITNESS_A, 0.5, "probe_token")

def test_blind_exposure_does_not_reference_posthoc_tasks():
    source = inspect.getsource(ex.blind_exposure)
    assert "reveal_tasks" not in source
    assert "post-hoc" not in source.lower()


def test_blind_exposure_rejects_unknown_mode():
    with pytest.raises(ValueError, match="unsupported structural contender mode"):
        ex.blind_exposure(ex.canonical_levels()[0], "mystery")


def test_short_exposure_preserves_both_histories(short_full, short_base):
    assert ex.token_in_perception(short_full["frozen"], "life_begin")
    assert ex.token_in_epistemic(short_full["frozen"], "life_begin")
    assert ex.baseline_history_complete(short_base["frozen"])
    assert short_full["snapshot_bytes"] > short_base["snapshot_bytes"]


def test_overflow_exposure_is_cross_layer_not_bigger_perception(overflow_full, overflow_base):
    assert not ex.token_in_perception(overflow_full["frozen"], "life_begin")
    assert ex.token_in_epistemic(overflow_full["frozen"], "life_begin")
    assert ex.token_in_epistemic(overflow_full["frozen"], "life_end")
    assert not ex.baseline_history_complete(overflow_base["frozen"])


def test_perception_history_absence_branches():
    assert ex.ghost_perception_history({"api": {}}) == []
    assert ex.ghost_perception_history({"api": {"perception": {"observers": {}}}}) == []


def test_task_battery_is_fixed_and_unique():
    tasks = s7.reveal_tasks()
    assert len(tasks) == 10
    assert len({row["id"] for row in tasks}) == 10
    assert {row["kind"] for row in tasks} == s7._SUPPORTED_KINDS


@pytest.mark.parametrize(
    "raw,message",
    [
        (None, "invalid shape"),
        ({"id": "x", "kind": "recent_marker_source"}, "invalid shape"),
        ({"id": "x", "kind": "not_real", "args": {}}, "unsupported"),
        ({"id": "x", "kind": "recent_marker_source", "args": []}, "args must be a dict"),
    ],
)
def test_task_validation_rejects_bad_shapes(raw, message):
    with pytest.raises(ValueError, match=message):
        s7._validated_task(raw)


@pytest.mark.parametrize("signals,expected", [([1.0], "hostile"), ([-1.0], "benign"), ([1.0, -1.0], "tie")])
def test_signal_dominant(signals, expected):
    assert s7._signal_dominant(signals) == expected


@pytest.mark.parametrize("value,expected", [(0.2, "positive"), (-0.2, "negative"), (0.0, "neutral")])
def test_trust_sign(value, expected):
    assert s7._trust_sign(value) == expected


def test_marker_source_handles_full_baseline_and_missing(short_full, short_base):
    full_records = ex.ghost_epistemic_records(short_full["frozen"])
    base_records = ex.baseline_observations(short_base["frozen"])
    assert s7._marker_source(full_records, "early_promise", ghost=True) == ex.WITNESS_A
    assert s7._marker_source(base_records, "early_promise", ghost=False) == ex.WITNESS_A
    assert s7._marker_source(full_records, "absent", ghost=True) is None
    assert s7._marker_source(base_records, "absent", ghost=False) is None


def test_short_level_all_posthoc_tasks_match_ground_truth(short_full, short_base):
    tasks = s7.reveal_tasks()
    full = s7._score_tasks(short_full, tasks)
    baseline = s7._score_tasks(short_base, tasks)
    assert (full["correct"], full["supported"], full["unsupported"]) == (10, 10, 0)
    assert (baseline["correct"], baseline["supported"], baseline["unsupported"]) == (10, 10, 0)
    assert [row["answer"] for row in full["rows"]] == [row["answer"] for row in baseline["rows"]]


def test_overflow_baseline_reports_missing_history_instead_of_guessing(overflow_full, overflow_base):
    tasks = s7.reveal_tasks()
    full = s7._score_tasks(overflow_full, tasks)
    baseline = s7._score_tasks(overflow_base, tasks)
    assert (full["correct"], full["unsupported"]) == (10, 0)
    assert (baseline["correct"], baseline["unsupported"]) == (3, 7)
    assert all(row["status"] == "unsupported" for row in baseline["rows"] if row["history_dependent"])


def test_full_evidence_returns_empty_when_belief_missing():
    api = GhostAPI()
    api.register_agent(ex.AGENT, role="guard")
    frozen = {"mode": "full", "api": api.snapshot()}
    assert s7._full_evidence(frozen, ex.SUBJECT) == []
    assert s7._full_belief(frozen, {"subject": ex.SUBJECT}) is None


def test_full_delegate_rejects_snapshot_without_agent():
    api = GhostAPI()
    frozen = {"mode": "full", "api": api.snapshot()}
    with pytest.raises(RuntimeError, match="disappeared"):
        s7._full_delegate(frozen, {"sources": [ex.WITNESS_A, ex.WITNESS_B], "duty_threshold": 0.8})


def test_delegate_low_duty_uses_current_trust(short_full, short_base):
    full = deepcopy(short_full["frozen"])
    api = GhostAPI.from_snapshot(full["api"])
    agent = api.agent(ex.AGENT)
    assert agent is not None
    agent.set_value("duty", 0.1)
    full["api"] = api.snapshot()
    base = deepcopy(short_base["frozen"])
    base["flat"]["decision_state"]["values"]["duty"] = 0.1
    args = {"sources": [ex.WITNESS_A, ex.WITNESS_B], "duty_threshold": 0.8}
    assert s7._full_delegate(full, args) == ex.WITNESS_A
    assert s7._baseline_delegate(base, args) == ex.WITNESS_A


def test_baseline_history_helpers_return_none_after_overflow(overflow_base):
    frozen = overflow_base["frozen"]
    assert s7._baseline_relationship_count(frozen, ex.WITNESS_A) is None
    assert s7._baseline_evidence(frozen, ex.SUBJECT) is None
    assert s7._baseline_counts(frozen, [ex.WITNESS_A, ex.WITNESS_B]) is None


def test_baseline_counterfactual_none_after_overflow(overflow_base):
    answer = s7._baseline_counterfactual(
        overflow_base["frozen"],
        {"subject": ex.SUBJECT, "excluded_source": ex.WITNESS_A},
    )
    assert answer is None


def test_baseline_deeper_none_after_overflow(overflow_base):
    assert s7._baseline_deeper(
        overflow_base["frozen"], {"sources": [ex.WITNESS_A, ex.WITNESS_B]}
    ) is None


def test_baseline_delegate_none_after_overflow(overflow_base):
    assert s7._baseline_delegate(
        overflow_base["frozen"],
        {"sources": [ex.WITNESS_A, ex.WITNESS_B], "duty_threshold": 0.8},
    ) is None


def test_answer_dispatches_both_modes(short_full, short_base):
    task = s7.reveal_tasks()[0]
    assert s7._answer(short_full["frozen"], task) == {"status": "supported", "answer": ex.WITNESS_C}
    assert s7._answer(short_base["frozen"], task) == {"status": "supported", "answer": ex.WITNESS_C}


def test_ground_truth_task_handlers_cover_all_kinds(short_full):
    tasks = s7.reveal_tasks()
    answers = {task["kind"]: s7._ground_truth(short_full["host_ledger"], task) for task in tasks}
    assert answers == {
        "recent_marker_source": ex.WITNESS_C,
        "current_trust_sign": "positive",
        "current_belief_dominant": "hostile",
        "early_marker_source": ex.WITNESS_A,
        "relationship_event_count": 5,
        "evidence_sources": [ex.WITNESS_A, ex.WITNESS_B, ex.WITNESS_C],
        "belief_revision_count": 4,
        "counterfactual_without_source": "benign",
        "deeper_relationship": ex.WITNESS_A,
        "novel_delegate_choice": ex.WITNESS_A,
    }


def test_truth_delegate_low_duty_branch(short_full):
    task = s7._task(
        "low_duty_delegate",
        "novel_delegate_choice",
        sources=[ex.WITNESS_A, ex.WITNESS_B],
        duty_threshold=0.95,
    )
    assert s7._ground_truth(short_full["host_ledger"], task) == ex.WITNESS_A


@pytest.mark.parametrize(
    "full,baseline,expected",
    [
        (2, 1, "directional_ghost_latent_state_advantage"),
        (1, 2, "directional_baseline_latent_state_advantage"),
        (2, 2, "latent_state_parity_on_revealed_tasks"),
    ],
)
def test_outcome_all_directions(full, baseline, expected):
    assert s7._outcome(full, baseline) == expected


def test_overflow_recovery_true_and_each_false_branch():
    good = {
        "state": {
            "ghost_perception_history_complete": False,
            "ghost_epistemic_ledger_complete": True,
            "baseline_observation_history_complete": False,
        }
    }
    assert s7._overflow_recovery([good])
    for key, value in [
        ("ghost_perception_history_complete", True),
        ("ghost_epistemic_ledger_complete", False),
        ("baseline_observation_history_complete", True),
    ]:
        bad = deepcopy(good)
        bad["state"][key] = value
        assert not s7._overflow_recovery([bad])


def test_default_matrix_records_latent_state_advantage():
    matrix = s7.run_matrix()
    assert matrix["scored_tasks_per_contender"] == 30
    assert matrix["totals"] == {
        "full": {"correct": 30, "supported": 30, "unsupported": 0},
        "baseline": {"correct": 16, "supported": 16, "unsupported": 14},
    }
    assert matrix["comparative_outcome"] == "directional_ghost_latent_state_advantage"
    assert matrix["control_level_parity"] is True
    assert matrix["overflow_cross_layer_recovery"] is True
    assert matrix["same_external_exposure"] is True


def test_custom_matrix_path():
    matrix = s7.run_matrix([{"id": "custom_short", "ambient_events": 0}])
    assert matrix["scored_tasks_per_contender"] == 10
    assert matrix["totals"]["full"]["correct"] == 10
    assert matrix["totals"]["baseline"]["correct"] == 10
    assert matrix["comparative_outcome"] == "latent_state_parity_on_revealed_tasks"


def test_matrix_rejects_empty_levels():
    with pytest.raises(ValueError, match="requires at least one level"):
        s7.run_matrix([])


def test_matrix_detects_task_count_drift(monkeypatch):
    original = s7._level_result
    calls = {"count": 0}

    def drifting(raw):
        row = original(raw)
        calls["count"] += 1
        if calls["count"] == 2:
            row["task_count"] += 1
        return row

    monkeypatch.setattr(s7, "_level_result", drifting)
    with pytest.raises(RuntimeError, match="task count changed"):
        s7.run_matrix(ex.canonical_levels()[:2])


def test_experiment_claim_boundary_and_constraints():
    result = s7.run_experiment()
    assert result["schema"] == s7.SCHEMA
    assert result["strict_verdict"] == s7.VERDICT
    assert result["constraints"] == {
        "state_frozen_before_task_reveal": True,
        "history_replay": False,
        "schema_changes_after_reveal": False,
        "baseline_state_redesign": False,
        "ghost_state_redesign": False,
        "posthoc_queries_read_only": True,
    }
    assert "does not establish general intelligence" in result["claim_boundary"]
