from copy import deepcopy
import json

import pytest

from ghost_research import v112_lean_adjudication_stage5 as s5


def test_constants_and_canonical_levels_are_stable():
    assert s5.SCHEMA.endswith("stage5.v1")
    assert s5.VERDICT == "V112_LEAN_ADJUDICATION_STAGE5_EXPERIMENT_VALID"
    assert [item["id"] for item in s5.canonical_levels()] == ["light", "medium", "heavy"]
    assert s5.FULL_WEIGHTS["values"] == 1.0 and s5.LEAN_WEIGHTS["values"] == 0.0


@pytest.mark.parametrize("value,allow_zero,expected", [(1, False, 1), (0, True, 0), (4, True, 4)])
def test_positive_int_accepts_valid_values(value, allow_zero, expected):
    assert s5._positive_int(value, "x", allow_zero=allow_zero) == expected


@pytest.mark.parametrize("value,allow_zero", [(True, False), (0, False), (-1, True), (1.2, False)])
def test_positive_int_rejects_invalid_values(value, allow_zero):
    with pytest.raises(ValueError, match="integer"):
        s5._positive_int(value, "x", allow_zero=allow_zero)


def test_level_validation_accepts_and_normalizes():
    raw = {"id": " Demo ", "subjects": 2, "fillers": 3, "restarts": 1, "hostile": 0.5, "contradiction": -0.5}
    assert s5._level(raw) == {"id": "Demo", "subjects": 2, "fillers": 3, "restarts": 1, "hostile": 0.5, "contradiction": -0.5}


@pytest.mark.parametrize(
    "raw,match",
    [
        (None, "invalid shape"),
        ({"id": "x"}, "invalid shape"),
        ({"id": "x", "subjects": 1, "fillers": 0, "restarts": 1, "hostile": 0.5, "contradiction": -0.5}, "cannot exceed"),
        ({"id": "x", "subjects": 1, "fillers": 1, "restarts": 0, "hostile": -0.5, "contradiction": -0.5}, "positive hostile"),
        ({"id": "x", "subjects": 1, "fillers": 1, "restarts": 0, "hostile": 0.5, "contradiction": 0.5}, "positive hostile"),
    ],
)
def test_level_validation_rejects_bad_shape_or_semantics(raw, match):
    with pytest.raises(ValueError, match=match):
        s5._level(raw)


def test_subject_ids_validate_count():
    assert s5._subject_ids(3) == ["visitor_00", "visitor_01", "visitor_02"]
    with pytest.raises(ValueError, match="positive integer"):
        s5._subject_ids(0)


def test_candidate_builders_bind_subject_and_values():
    threat = s5._threat_candidates("visitor_x")
    assert [row["id"] for row in threat] == ["admit", "challenge"]
    assert threat[0]["features"]["v112_stage3_belief"]["subject"] == "visitor_x"
    values = s5._value_candidates()
    assert [row["id"] for row in values] == ["avoid", "protect"]
    assert values[1]["features"]["v112_stage2_policy"]["value_alignment"] == {"compassion": 1.0}


def test_encode_bytes_is_canonical_and_rejects_nan():
    assert s5._encode_bytes({"b": 1, "a": 2}) == s5._encode_bytes({"a": 2, "b": 1})
    with pytest.raises(ValueError):
        s5._encode_bytes({"x": float("nan")})


@pytest.mark.parametrize("mode", ["full", "lean", "baseline"])
def test_contender_constructs_all_modes(mode):
    c = s5._Contender(mode, ["visitor_00", "visitor_01"])
    assert c.mode == mode
    assert c.subjects == ["visitor_00", "visitor_01"]
    assert c.snapshot_bytes() > 0


def test_contender_rejects_bad_mode_or_subjects():
    with pytest.raises(ValueError, match="unsupported contender mode"):
        s5._Contender("nope", ["visitor_00"])
    with pytest.raises(ValueError, match="requires subjects"):
        s5._Contender("full", [])
    with pytest.raises(ValueError, match="unique"):
        s5._Contender("full", ["visitor", " visitor "])


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_signal_and_distribution_move_toward_hostile(mode):
    c = s5._Contender(mode, ["visitor_00"])
    before = c.distribution("visitor_00")["hostile"]
    c.signal("visitor_00", 0.6)
    assert c.distribution("visitor_00")["hostile"] > before


@pytest.mark.parametrize("mode", ["full", "lean", "baseline"])
def test_hidden_fact_never_changes_decision_belief(mode):
    c = s5._Contender(mode, ["visitor_00"])
    c.signal("visitor_00", 0.5)
    assert c.hidden_fact("visitor_00", "probe") is True


@pytest.mark.parametrize("mode,expected_effect", [("full", True), ("baseline", True), ("lean", False)])
def test_delayed_badge_effect_uses_recall_only_for_full_and_baseline(mode, expected_effect):
    c = s5._Contender(mode, ["visitor_00"])
    c.signal("visitor_00", 0.65)
    before = c.distribution("visitor_00")["hostile"]
    c.observe_badge("visitor_00")
    assert c.delayed_badge_effect("visitor_00") is True
    after = c.distribution("visitor_00")["hostile"]
    assert (after < before) is expected_effect


def test_delayed_badge_effect_no_memory_is_noop():
    c = s5._Contender("full", ["visitor_00"])
    before = c.distribution("visitor_00")
    assert c.delayed_badge_effect("visitor_00") is False
    assert c.distribution("visitor_00") == before


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_apply_effects_changes_goal_state(mode):
    c = s5._Contender(mode, ["visitor_00"])
    c.apply_effects({"goal_progress": {"hold_gate": 0.75}})
    if mode == "baseline":
        assert c.baseline.decision_state["goals"]["hold_gate"]["progress"] == 0.75
    else:
        assert c.agent.goal("hold_gate")["progress"] == 0.75


@pytest.mark.parametrize("mode", ["full", "lean", "baseline"])
def test_choose_resolves_and_returns_scores(mode):
    c = s5._Contender(mode, ["visitor_00"])
    result = c.choose(s5._value_candidates(), "value")
    assert result["decision"] in {"avoid", "protect"}
    assert set(result["scores"]) == {"avoid", "protect"}
    assert c.agent.pending_action() is None


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_filler_and_restart_preserve_state(mode):
    c = s5._Contender(mode, ["visitor_00"])
    c.signal("visitor_00", 0.55)
    c.observe_badge("visitor_00")
    c.filler(0, 4)
    before = c._decision_fingerprint()
    c.restart()
    assert c._decision_fingerprint() == before


def test_filler_accepts_zero_and_rejects_bad_values():
    c = s5._Contender("full", ["visitor_00"])
    c.filler(0, 0)
    assert c.agent.observation_history() == []
    with pytest.raises(ValueError, match="integer"):
        c.filler(-1, 1)
    with pytest.raises(ValueError, match="integer"):
        c.filler(0, -1)


def test_restart_detects_missing_registered_agent(monkeypatch):
    c = s5._Contender("full", ["visitor_00"])
    from ghost.api import GhostAPI
    original = GhostAPI.agent
    monkeypatch.setattr(GhostAPI, "agent", lambda self, agent_id: None)
    with pytest.raises(RuntimeError, match="lost registered agent"):
        c.restart()
    monkeypatch.setattr(GhostAPI, "agent", original)


def test_restart_detects_state_drift(monkeypatch):
    c = s5._Contender("baseline", ["visitor_00"])
    original = c._decision_fingerprint
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        data = original()
        if calls["n"] > 1:
            data = deepcopy(data)
            data["decision"]["values"]["duty"] = 0.0
        return data
    monkeypatch.setattr(c, "_decision_fingerprint", fake)
    with pytest.raises(RuntimeError, match="changed decision-relevant state"):
        c.restart()


def test_score_row_marks_correctness():
    c = s5._Contender("full", ["visitor_00"])
    row = s5._score_row(c, s5._value_candidates(), "value", "protect", "values")
    assert row["correct"] is True and row["requirement"] == "values"


def test_run_fillers_segments_and_restarts(monkeypatch):
    c = s5._Contender("full", ["visitor_00"])
    restarts = {"n": 0}
    original = c.restart
    def counted():
        restarts["n"] += 1
        original()
    monkeypatch.setattr(c, "restart", counted)
    s5._run_fillers(c, 5, 2)
    assert restarts["n"] == 2
    assert len(c.agent.observation_history()) == 5
    with pytest.raises(ValueError, match="cannot exceed"):
        s5._run_fillers(c, 1, 2)


@pytest.mark.parametrize("mode,expected", [("full", 11), ("baseline", 11), ("lean", 9)])
def test_light_level_expected_scores(mode, expected):
    result = s5.run_level(s5.canonical_levels()[0], mode)
    assert result["correct"] == expected
    assert result["checkpoint_count"] == 11
    assert result["hidden_information_boundary"] is True


def test_decision_map_extracts_checkpoint_decisions():
    result = s5.run_level(s5.canonical_levels()[0], "full")
    mapping = s5._decision_map(result)
    assert mapping["goal_initial"] == "hold"
    assert mapping["value_preference"] == "protect"


def test_scale_matrix_rejects_empty_levels():
    with pytest.raises(ValueError, match="at least one level"):
        s5.run_scale_matrix([])


def test_scale_matrix_records_three_way_adjudication():
    result = s5.run_scale_matrix()
    assert result["scored_checkpoints_per_contender"] == 57
    assert result["totals"] == {"full": 57, "lean": 51, "baseline": 57}
    assert result["first_failure_level"] == {"full": None, "lean": "light", "baseline": None}
    assert result["decision_divergences"] == {"full_vs_baseline": 0, "lean_vs_full": 6}
    assert result["full_vs_baseline_outcome"] == "behavioral_parity_on_scored_constraints"


def test_scale_matrix_detects_checkpoint_count_mismatch(monkeypatch):
    original = s5.run_level
    def fake(level, mode):
        out = original(level, mode)
        if mode == "lean":
            out["checkpoint_count"] += 1
        return out
    monkeypatch.setattr(s5, "run_level", fake)
    with pytest.raises(RuntimeError, match="same checkpoint count"):
        s5.run_scale_matrix([s5.canonical_levels()[0]])


def test_frozen_replay_confirms_positive_lean_construction():
    result = s5.run_frozen_replay()
    assert result["stage3_scores"] == {"ghost": 30, "baseline": 30}
    assert result["lean_frozen_equivalent"] is True
    assert result["lean_decision_match_to_full"] is True


def test_frozen_replay_rejects_broken_full_anchor(monkeypatch):
    original = s5.s4.run_condition
    def fake(name, condition, variants=None):
        out = original(name, condition, variants)
        if name == "full":
            out = deepcopy(out)
            out["ghost_correct"] -= 1
        return out
    monkeypatch.setattr(s5.s4, "run_condition", fake)
    with pytest.raises(RuntimeError, match="no longer matches"):
        s5.run_frozen_replay()


def test_capacity_probe_boundary_and_agreement():
    result = s5.run_capacity_probe()
    assert [(row["fillers"], row["retained"]) for row in result["rows"]] == [
        (120, {"full": True, "baseline": True}),
        (127, {"full": True, "baseline": True}),
        (128, {"full": False, "baseline": False}),
        (129, {"full": False, "baseline": False}),
    ]
    assert result["all_agree"] is True


def test_capacity_probe_validates_input():
    with pytest.raises(ValueError, match="requires filler counts"):
        s5.run_capacity_probe([])
    with pytest.raises(ValueError, match="unique"):
        s5.run_capacity_probe([1, 1])


def test_requirements_from_scale_attributes_lean_losses():
    scale = s5.run_scale_matrix([s5.canonical_levels()[0]])
    assert s5._requirements_from_scale(scale) == {"values": 1, "recall": 1, "other": 0}


def test_requirements_from_scale_tracks_other_failures():
    scale = s5.run_scale_matrix([s5.canonical_levels()[0]])
    row = scale["levels"][0]["competitors"]["lean"]["rows"][0]
    row["correct"] = False
    row["requirement"] = "goals"
    assert s5._requirements_from_scale(scale)["other"] == 1


def test_full_adjudication_is_deterministic_and_scientifically_bounded():
    first = s5.run_adjudication()
    second = s5.run_adjudication()
    assert first == second
    assert first["strict_verdict"] == s5.VERDICT
    assert first["lean_requirement_losses"] == {"values": 3, "recall": 3, "other": 0}
    assert first["interpretation"] == {
        "lean_frozen_equivalent": True,
        "lean_scaled_equivalent": False,
        "full_vs_baseline_outcome": "behavioral_parity_on_scored_constraints",
        "values_requirement_sensitive": True,
        "recall_requirement_sensitive": True,
    }
    assert "not a general Ghost-superiority claim" in first["claim_boundary"]
    assert "not production package deletion" in first["claim_boundary"]


def test_adjudication_interpretation_handles_no_requirement_losses(monkeypatch):
    fake_scale = {
        "totals": {"full": 1, "lean": 1, "baseline": 0},
        "decision_divergences": {"lean_vs_full": 0},
        "full_vs_baseline_outcome": "directional_ghost_advantage",
        "levels": [],
    }
    monkeypatch.setattr(s5, "run_frozen_replay", lambda: {"lean_frozen_equivalent": False})
    monkeypatch.setattr(s5, "run_scale_matrix", lambda: fake_scale)
    monkeypatch.setattr(s5, "run_capacity_probe", lambda: {"all_agree": False})
    monkeypatch.setattr(s5, "_requirements_from_scale", lambda scale: {"values": 0, "recall": 0, "other": 0})
    out = s5.run_adjudication()
    assert out["interpretation"] == {
        "lean_frozen_equivalent": False,
        "lean_scaled_equivalent": True,
        "full_vs_baseline_outcome": "directional_ghost_advantage",
        "values_requirement_sensitive": False,
        "recall_requirement_sensitive": False,
    }
