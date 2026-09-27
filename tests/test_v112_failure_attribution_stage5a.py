from copy import deepcopy

import pytest

from ghost_research import v112_failure_attribution_stage5a as a


@pytest.fixture(scope="module")
def matrix():
    return a._condition_matrix()


@pytest.fixture(scope="module")
def frozen():
    return a._frozen_stage5_rows()


@pytest.fixture(scope="module")
def result():
    return a.run_attribution()


def _freeze_helpers(monkeypatch, frozen, matrix):
    monkeypatch.setattr(a, "_frozen_stage5_rows", lambda: deepcopy(frozen))
    monkeypatch.setattr(a, "_condition_matrix", lambda: deepcopy(matrix))


def test_constants_are_stable():
    assert a.SCHEMA.endswith("stage5a.v1")
    assert a.VERDICT == "V112_FAILURE_ATTRIBUTION_STAGE5A_EXPERIMENT_VALID"
    assert len(a._EXPECTED_FAILURES) == 6


@pytest.mark.parametrize("name", ["full", "lean", "restore_values", "restore_recall"])
def test_condition_accepts_all_preregistered_names(name):
    cfg = a._condition(name)
    assert cfg["name"] == name
    assert set(cfg["weights"]) == {"utility", "values", "goals", "beliefs"}


@pytest.mark.parametrize("name", ["", "nope", None])
def test_condition_rejects_unknown_names(name):
    with pytest.raises(ValueError, match="unknown Stage-5A condition"):
        a._condition(name)


def test_row_map_validates_shape_and_duplicates():
    with pytest.raises(ValueError, match="contain rows"):
        a._row_map(None)
    with pytest.raises(ValueError, match="duplicate"):
        a._row_map({"rows": [{"checkpoint": "x"}, {"checkpoint": "x"}]})
    assert set(a._row_map({"rows": [{"checkpoint": "x"}]})) == {"x"}


def test_decision_margin_requires_exact_pair():
    assert a._decision_margin({"a": 2.0, "b": 0.5}, "a", "b") == 1.5
    with pytest.raises(ValueError, match="two compared"):
        a._decision_margin({"a": 1.0, "b": 0.0, "c": 2.0}, "a", "b")


@pytest.mark.parametrize("condition,expected", [("full", "protect"), ("lean", "avoid"), ("restore_values", "protect"), ("restore_recall", "avoid")])
def test_value_checkpoint_orthogonal_restoration(matrix, condition, expected):
    row = a._row_map(matrix[condition]["light"])["value_preference"]
    assert row["decision"] == expected


@pytest.mark.parametrize("condition,expected", [("full", "admit"), ("lean", "challenge"), ("restore_values", "challenge"), ("restore_recall", "admit")])
def test_recall_checkpoint_orthogonal_restoration(matrix, condition, expected):
    row = a._row_map(matrix[condition]["light"])["delayed_badge"]
    assert row["decision"] == expected


@pytest.mark.parametrize("condition", ["full", "lean", "restore_values", "restore_recall"])
def test_badge_is_remembered_in_every_condition(matrix, condition):
    assert matrix[condition]["light"]["badge_remembered"] is True


def test_recall_enabled_changes_belief_while_disabled_does_not(matrix):
    full = matrix["full"]["light"]
    lean = matrix["lean"]["light"]
    assert full["belief_after_recall"] != full["belief_before_recall"]
    assert lean["belief_after_recall"] == lean["belief_before_recall"]


def test_condition_matrix_has_all_levels_and_conditions(matrix):
    assert set(matrix) == {"full", "lean", "restore_values", "restore_recall"}
    assert all(set(levels) == {"light", "medium", "heavy"} for levels in matrix.values())


def test_frozen_stage5_rows_has_three_modes(frozen):
    assert set(frozen) == {"light", "medium", "heavy"}
    assert all(set(modes) == {"full", "lean", "baseline"} for modes in frozen.values())


@pytest.mark.parametrize("requirement", ["values", "recall"])
def test_attribution_row_accepts_supported_requirements(frozen, matrix, requirement):
    checkpoint = "value_preference" if requirement == "values" else "delayed_badge"
    row = a._attribution_row("light", checkpoint, requirement, frozen, matrix)
    assert row["requirement"] == requirement and row["isolated_counterfactual"] is True


def test_attribution_row_rejects_unsupported_requirement(frozen, matrix):
    with pytest.raises(ValueError, match="unsupported requirement"):
        a._attribution_row("light", "value_preference", "other", frozen, matrix)


def test_full_attribution_exactly_explains_all_six_divergences(result):
    assert result["stage5_totals"] == {"full": 57, "lean": 51, "baseline": 57}
    assert result["divergence_count"] == 6
    assert result["summary"] == {"values_failures": 3, "recall_failures": 3, "unexplained_failures": 0}
    assert result["counterfactual_totals"] == {"full": 57, "lean": 51, "restore_values": 54, "restore_recall": 54}


def test_value_failures_are_exact_ties_without_value_signal(result):
    rows = [r for r in result["divergences"] if r["requirement"] == "values"]
    assert len(rows) == 3
    assert all(r["checkpoint"] == "value_preference" for r in rows)
    assert all(r["full_scores"] == {"avoid": -0.65, "protect": 0.65} for r in rows)
    assert all(r["lean_scores"] == {"avoid": 0.0, "protect": 0.0} for r in rows)
    assert all(r["lean_decision"] == "avoid" and r["restore_values_decision"] == "protect" for r in rows)


def test_recall_failures_remember_badge_but_do_not_reapply_evidence(result):
    rows = [r for r in result["divergences"] if r["requirement"] == "recall"]
    assert len(rows) == 3
    assert all(r["checkpoint"] == "delayed_badge" for r in rows)
    assert all(r["lean_decision"] == "challenge" and r["restore_recall_decision"] == "admit" for r in rows)
    for level in ("light", "medium", "heavy"):
        assert result["memory_trace"][level]["lean"]["remembered"] is True
        assert result["memory_trace"][level]["lean"]["before"] == result["memory_trace"][level]["lean"]["after"]
        assert result["memory_trace"][level]["restore_recall"]["before"] != result["memory_trace"][level]["restore_recall"]["after"]


def test_full_and_baseline_choose_expected_action_at_all_six_failures(result):
    assert all(r["full_decision"] == r["expected"] == r["baseline_decision"] for r in result["divergences"])


def test_claim_boundary_remains_narrow(result):
    assert "does not establish general Ghost superiority" in result["claim_boundary"]
    assert "six pre-existing" in result["claim_boundary"]


def test_replayer_rejects_full_or_lean_drift(monkeypatch, frozen, matrix):
    broken = deepcopy(matrix)
    row = a._row_map(broken["lean"]["light"])["goal_initial"]
    row["decision"] = "retreat"
    _freeze_helpers(monkeypatch, frozen, broken)
    with pytest.raises(RuntimeError, match="replay drifted"):
        a.run_attribution()


def test_replayer_rejects_unexpected_divergence(monkeypatch, frozen, matrix):
    _freeze_helpers(monkeypatch, frozen, matrix)
    expected = deepcopy(a._EXPECTED_FAILURES)
    expected.pop(("light", "value_preference"))
    monkeypatch.setattr(a, "_EXPECTED_FAILURES", expected)
    with pytest.raises(RuntimeError, match="unexpected Lean divergence"):
        a.run_attribution()


def test_replayer_rejects_missing_expected_divergence(monkeypatch, frozen, matrix):
    _freeze_helpers(monkeypatch, frozen, matrix)
    expected = deepcopy(a._EXPECTED_FAILURES)
    expected[("light", "goal_initial")] = "goals"
    monkeypatch.setattr(a, "_EXPECTED_FAILURES", expected)
    with pytest.raises(RuntimeError, match="divergences missing"):
        a.run_attribution()


def test_replayer_rejects_failed_counterfactual_isolation(monkeypatch, frozen, matrix):
    _freeze_helpers(monkeypatch, frozen, matrix)
    original = a._attribution_row
    def fake(*args, **kwargs):
        row = original(*args, **kwargs)
        row["isolated_counterfactual"] = False
        return row
    monkeypatch.setattr(a, "_attribution_row", fake)
    with pytest.raises(RuntimeError, match="counterfactual isolation failed"):
        a.run_attribution()
