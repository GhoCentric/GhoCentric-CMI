from copy import deepcopy

import pytest

from ghost_research import v112_ablation_stage4 as s4
from ghost_research import v112_continuity_stress_stage3 as s3


def test_preregistered_conditions_are_complete_and_copies():
    first = s4.preregistered_conditions()
    second = s4.preregistered_conditions()
    assert list(first) == [
        "full", "no_values", "no_goals", "no_beliefs", "no_recall",
        "no_values_goals", "no_values_beliefs", "no_goals_beliefs", "utility_only",
    ]
    first["full"]["weights"]["goals"] = 0.0
    assert second["full"]["weights"]["goals"] == 1.0


@pytest.mark.parametrize("bad", [None, [], {"weights": {}}, {"weights": {}, "recall_enabled": True, "x": 1}])
def test_condition_rejects_bad_shape(bad):
    with pytest.raises(ValueError, match="exactly weights"):
        s4._condition(bad)


@pytest.mark.parametrize("weights", [None, {}, {"utility": 1, "values": 1, "goals": 1}, {"utility": 1, "values": 1, "goals": 1, "beliefs": 1, "x": 1}])
def test_condition_rejects_bad_weight_shape(weights):
    with pytest.raises(ValueError, match="weights must contain"):
        s4._condition({"weights": weights, "recall_enabled": True})


def test_condition_rejects_non_boolean_recall():
    with pytest.raises(ValueError, match="must be bool"):
        s4._condition({"weights": {"utility": 1, "values": 1, "goals": 1, "beliefs": 1}, "recall_enabled": 1})


def test_condition_delegates_numeric_validation():
    with pytest.raises(ValueError, match="non-negative"):
        s4._condition({"weights": {"utility": 1, "values": -1, "goals": 1, "beliefs": 1}, "recall_enabled": True})


def test_run_condition_name_validation():
    with pytest.raises(ValueError, match="name"):
        s4.run_condition("", s4.preregistered_conditions()["full"], [s3.canonical_variants()[0]])


def test_run_condition_variants_validation():
    with pytest.raises(ValueError, match="at least one"):
        s4.run_condition("x", s4.preregistered_conditions()["full"], [])
    with pytest.raises(ValueError, match="at least one"):
        s4.run_condition("x", s4.preregistered_conditions()["full"], "bad")


def test_full_condition_one_variant_matches_stage3_decisions():
    variant = s3.canonical_variants()[0]
    stage3 = s3.run_trial(variant)
    stage4 = s4.run_condition("full", s4.preregistered_conditions()["full"], [variant])
    got = [(r["checkpoint"], r["ghost"], r["baseline"]) for r in stage4["trials"][0]["checkpoints"]]
    expected = [(r["checkpoint"], r["ghost"], r["baseline"]) for r in stage3["checkpoints"]]
    assert got == expected
    assert stage4["ghost_correct"] == stage3["ghost_correct"]
    assert stage4["baseline_correct"] == stage3["baseline_correct"]


@pytest.mark.parametrize("name", list(s4._PRE_REGISTERED))
def test_every_preregistered_condition_is_deterministic(name):
    variant = [s3.canonical_variants()[0]]
    cfg = s4.preregistered_conditions()[name]
    assert s4.run_condition(name, cfg, variant) == s4.run_condition(name, cfg, variant)


def test_full_matrix_reproduces_stage3_anchor_and_baseline():
    matrix = s4.run_ablation_matrix()
    assert matrix["schema"] == s4.SCHEMA
    assert matrix["strict_verdict"] == s4.VERDICT
    assert matrix["stage3_anchor"] == {"score_match": True, "decision_match": True, "invariant_match": True}
    assert matrix["scored_checkpoints_per_condition"] == 30
    assert matrix["conditions"]["full"]["ghost_correct"] == 30
    assert {r["baseline_correct"] for r in matrix["conditions"].values()} == {30}
    assert "do not establish general Ghost superiority" in matrix["claim_boundary"]


def test_no_belief_ablation_changes_only_ghost_not_baseline():
    cfg = s4.preregistered_conditions()["no_beliefs"]
    result = s4.run_condition("no_beliefs", cfg, [s3.canonical_variants()[0]])
    assert result["baseline_correct"] == 10
    assert result["ghost_correct"] <= 10
    assert result["invariant_failures"] == []


def test_no_recall_still_preserves_recorded_recall_state():
    cfg = s4.preregistered_conditions()["no_recall"]
    result = s4.run_condition("no_recall", cfg, [s3.canonical_variants()[0]])
    recall = result["trials"][0]["delayed_relevance_recall"]
    assert recall == {"ghost": True, "baseline": True}


def test_decision_map_and_failure_map():
    result = s4.run_condition("full", s4.preregistered_conditions()["full"], [s3.canonical_variants()[0]])
    decisions = s4._decision_map(result)
    assert decisions[("balanced", "goal_initial")] == "hold"
    assert s4._failure_map(result) == []
    broken = deepcopy(result)
    broken["trials"][0]["checkpoints"][0]["ghost_correct"] = False
    assert s4._failure_map(broken) == ["balanced:goal_initial"]


def test_attribution_no_change_and_change():
    full = s4.run_condition("full", s4.preregistered_conditions()["full"], [s3.canonical_variants()[0]])
    same = s4._attribution(full, deepcopy(full))
    assert same == {"score_delta_from_full": 0, "changed_decisions": [], "changed_decision_count": 0, "incorrect_checkpoints": [], "causally_effective_on_matrix": False}
    changed_result = deepcopy(full)
    row = changed_result["trials"][0]["checkpoints"][0]
    row["ghost"] = "retreat"
    row["ghost_correct"] = False
    changed_result["ghost_correct"] -= 1
    attr = s4._attribution(full, changed_result)
    assert attr["score_delta_from_full"] == -1
    assert attr["changed_decisions"] == ["balanced:goal_initial"]
    assert attr["incorrect_checkpoints"] == ["balanced:goal_initial"]
    assert attr["causally_effective_on_matrix"] is True


def test_stage3_anchor_detects_each_mismatch():
    full = s4.run_condition("full", s4.preregistered_conditions()["full"], [s3.canonical_variants()[0]])
    stage3 = s3.run_matrix([s3.canonical_variants()[0]])
    assert all(s4._stage3_anchor(stage3, full).values())
    bad = deepcopy(stage3); bad["ghost_correct"] -= 1
    assert not s4._stage3_anchor(bad, full)["score_match"]
    bad = deepcopy(stage3); bad["trials"][0]["checkpoints"][0]["ghost"] = "retreat"
    assert not s4._stage3_anchor(bad, full)["decision_match"]
    bad = deepcopy(stage3); bad["invariant_failures"] = ["x"]
    assert not s4._stage3_anchor(bad, full)["invariant_match"]


def _fake_result(correct=10, changed=False):
    checkpoint = {"checkpoint": "c", "ghost": "a" if not changed else "b", "ghost_correct": correct == 10}
    return {"ghost_correct": correct, "trials": [{"variant": "v", "checkpoints": [checkpoint]}]}


def _fake_conditions(effective=(), combined_effective=()):
    names = list(s4._PRE_REGISTERED)
    out = {}
    for name in names:
        changed = name in set(effective) | set(combined_effective)
        result = _fake_result(9 if changed else 10, changed)
        result["attribution"] = {"causally_effective_on_matrix": changed, "changed_decisions": ["v:c"] if changed else []}
        out[name] = result
    return out


def test_interpret_no_effect_category():
    data = s4._interpret(_fake_conditions())
    assert data["category"] == "no_ablation_effect_detected"
    assert data["effective_single_ablations"] == []
    assert "utility_only" in data["decision_equivalent_to_full"]


def test_interpret_single_effect_category():
    data = s4._interpret(_fake_conditions(effective=("no_goals",)))
    assert data["category"] == "single_channel_contribution_detected"
    assert data["effective_single_ablations"] == ["no_goals"]
    assert "no_values" in data["ineffective_single_ablations"]


def test_interpret_interaction_category():
    data = s4._interpret(_fake_conditions(combined_effective=("no_values_goals",)))
    assert data["category"] == "redundant_or_interacting_contribution_detected"
    assert data["interaction_flags"] == ["no_values_goals"]


def test_interpret_mixed_category():
    data = s4._interpret(_fake_conditions(effective=("no_beliefs",), combined_effective=("no_values_goals",)))
    assert data["category"] == "mixed_single_and_interaction_contribution"


def test_interpret_combined_or_minimal_category():
    data = _fake_conditions(combined_effective=("utility_only",))
    out = s4._interpret(data)
    assert out["category"] == "combined_only_or_minimal_path_effect_detected"


def test_run_ablation_matrix_rejects_stage3_anchor_drift(monkeypatch):
    real = s3.run_matrix()
    bad = deepcopy(real); bad["ghost_correct"] -= 1
    monkeypatch.setattr(s4.s3, "run_matrix", lambda: bad)
    with pytest.raises(RuntimeError, match="does not exactly reproduce"):
        s4.run_ablation_matrix()


def test_run_ablation_matrix_rejects_baseline_drift(monkeypatch):
    real_run = s4.run_condition
    real_stage3_run = s3.run_matrix
    def altered(name, condition, variants=None):
        result = real_run(name, condition, [s3.canonical_variants()[0]])
        if name == "no_values":
            result["baseline_correct"] -= 1
        return result
    monkeypatch.setattr(s4.s3, "run_matrix", lambda: real_stage3_run([s3.canonical_variants()[0]]))
    monkeypatch.setattr(s4, "run_condition", altered)
    with pytest.raises(RuntimeError, match="baseline changed"):
        s4.run_ablation_matrix()


def test_run_condition_trial_rejects_bad_variant():
    with pytest.raises(ValueError, match="invalid shape"):
        s4.run_condition_trial({}, s4.preregistered_conditions()["full"])


def test_finish_covers_missing_baseline_recall_branch(monkeypatch):
    class Baseline:
        def has_observation(self, *args):
            return False
        def apply_signal(self, *args, **kwargs):
            return None
        def apply_host_effects(self, effects):
            return effects
    class Agent:
        pass
    monkeypatch.setattr(s4.s3, "_fillers", lambda *args: None)
    monkeypatch.setattr(s4.s3, "ghost_has_observation", lambda *args: False)
    monkeypatch.setattr(s4.s3, "ghost_signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(s4, "apply_host_effects_to_ghost", lambda *args: None)
    monkeypatch.setattr(s4, "_choose", lambda *args: {"checkpoint": args[-2]})
    checkpoints = []
    recall = s4._finish(object(), Agent(), Agent(), Baseline(), [-0.5], checkpoints, s4.preregistered_conditions()["no_recall"])
    assert recall == {"ghost": False, "baseline": False}
    assert len(checkpoints) == 5
