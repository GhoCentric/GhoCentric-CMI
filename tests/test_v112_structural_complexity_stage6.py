from copy import deepcopy
import math
import pytest

from ghost_research import v112_structural_complexity_stage6 as s6


def test_positive_int_and_level_validation():
    assert s6._positive_int(1, "x") == 1
    assert s6._positive_int(0, "x", allow_zero=True) == 0
    for bad in (True, 0, -1, 1.2):
        with pytest.raises(ValueError, match="positive integer"):
            s6._positive_int(bad, "x")
    with pytest.raises(ValueError, match="non-negative integer"):
        s6._positive_int(-1, "x", allow_zero=True)
    with pytest.raises(ValueError, match="invalid shape"):
        s6._level({"id": "x", "agents": 3})
    with pytest.raises(ValueError, match="at least three"):
        s6._level({"id": "x", "agents": 2, "pending": 0})
    with pytest.raises(ValueError, match="smaller than"):
        s6._level({"id": "x", "agents": 3, "pending": 3})


def test_canonical_levels_are_structural_not_duration_levels():
    levels = s6.canonical_levels()
    assert [(x["id"], x["agents"], x["pending"]) for x in levels] == [
        ("light_mesh", 3, 1), ("medium_mesh", 4, 2), ("heavy_mesh", 5, 3)
    ]
    assert all(set(x) == {"id", "agents", "pending"} for x in levels)


def test_ids_and_pair_key_and_sign_helpers():
    assert s6._ids("guard", 3) == ["guard_00", "guard_01", "guard_02"]
    assert s6._pair_key(" Guard ", " Source ") == "Guard|Source"
    assert s6._sign(0.2) == 1.0
    assert s6._sign(-0.2) == -1.0
    assert s6._sign(1e-14) == 0.0


def test_encode_bytes_is_canonical_and_rejects_nan():
    assert s6._encode_bytes({"b": 1, "a": 2}) == s6._encode_bytes({"a": 2, "b": 1})
    with pytest.raises(ValueError):
        s6._encode_bytes({"x": float("nan")})


def test_decision_state_and_beliefs_are_independent_copies():
    first = s6._decision_state()
    second = s6._decision_state()
    first["values"]["duty"] = 0.0
    assert second["values"]["duty"] == 0.9
    beliefs = s6._beliefs(["a", "b"])
    assert beliefs["a"]["threat"] == {"benign": 0.5, "hostile": 0.5}
    assert beliefs["a"] is not beliefs["b"]


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_contender_constructs_independent_mesh(mode):
    c = s6.StructuralContender(mode, 3)
    assert c.mode == mode
    assert c.agent_ids == ["guard_00", "guard_01", "guard_02"]
    assert len(c.subject_ids) == 6 and len(c.source_ids) == 3
    assert c.snapshot_bytes() > 0
    assert (c.custom_baseline_bytes() > 0) is (mode == "baseline")


def test_contender_rejects_bad_mode_and_small_mesh():
    with pytest.raises(ValueError, match="unsupported structural"):
        s6.StructuralContender("lean", 3)
    with pytest.raises(ValueError, match="at least three"):
        s6.StructuralContender("full", 2)


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_seeded_relationship_mesh_has_expected_signs(mode):
    c = s6.StructuralContender(mode, 3)
    for i, agent in enumerate(c.agent_ids):
        assert c.trust(agent, c.source_ids[i]) > 0.0
        assert c.trust(agent, c.source_ids[(i + 1) % 3]) > 0.0
        assert c.trust(agent, c.source_ids[(i - 1) % 3]) < 0.0


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_relationship_events_and_bad_event(mode):
    c = s6.StructuralContender(mode, 3)
    agent, source = c.agent_ids[0], c.source_ids[0]
    before = c.trust(agent, source)
    after = c.relationship_event(agent, source, "betrayal")
    assert after < before and after < 0.0
    with pytest.raises(ValueError, match="unsupported structural relationship"):
        c.relationship_event(agent, source, "greet")


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_direct_signal_moves_belief(mode):
    c = s6.StructuralContender(mode, 3)
    agent, subject = c.agent_ids[0], c.subject_ids[0]
    before = c.distribution(agent, subject)["hostile"]
    after = c.direct_signal(agent, subject, 1.0)["hostile"]
    assert after > before


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_source_claim_uses_relationship_sign(mode):
    c = s6.StructuralContender(mode, 3)
    agent = c.agent_ids[0]
    trusted, distrusted = c.source_ids[0], c.source_ids[-1]
    p1, p2 = c.subject_ids[0], c.subject_ids[1]
    t = c.source_claim(agent, trusted, p1, 1.0)
    d = c.source_claim(agent, distrusted, p2, 1.0)
    assert t["effective_signal"] == 1.0 and t["distribution"]["hostile"] > 0.5
    assert d["effective_signal"] == -1.0 and d["distribution"]["hostile"] < 0.5


def test_source_claim_neutral_relationship_is_noop():
    c = s6.StructuralContender("baseline", 3)
    agent, subject = c.agent_ids[0], c.subject_ids[0]
    c.relationships[s6._pair_key(agent, "neutral_source")] = 0.0
    before = c.distribution(agent, subject)
    row = c.source_claim(agent, "neutral_source", subject, 1.0)
    assert row["effective_signal"] == 0.0
    assert row["distribution"] == before


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_hidden_fact_respects_information_boundary(mode):
    c = s6.StructuralContender(mode, 3)
    assert c.hidden_fact(c.agent_ids[0], c.subject_ids[0], "secret") is True


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_badge_memory_and_delayed_effect(mode):
    c = s6.StructuralContender(mode, 3)
    agent, subject = c.agent_ids[0], c.subject_ids[3]
    assert c.has_badge(agent, subject) is False
    assert c.delayed_badge_effect(agent, subject) is False
    c.direct_signal(agent, subject, 1.0)
    before = c.distribution(agent, subject)["hostile"]
    c.observe_badge(agent, subject)
    assert c.has_badge(agent, subject) is True
    assert c.delayed_badge_effect(agent, subject) is True
    assert c.distribution(agent, subject)["hostile"] < before


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_apply_effects_changes_goal_state(mode):
    c = s6.StructuralContender(mode, 3)
    agent = c.agent_ids[0]
    c.apply_effects(agent, {"goal_progress": {"hold_gate": 0.75}})
    if mode == "full":
        assert c.agents[agent].goal("hold_gate")["progress"] == 0.75
    else:
        assert c.flat[agent].decision_state["goals"]["hold_gate"]["progress"] == 0.75


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_choose_resolves_action(mode):
    c = s6.StructuralContender(mode, 3)
    agent = c.agent_ids[0]
    result = c.choose(agent, s6.s5._value_candidates(), "value")
    assert result["decision"] == "protect"
    assert c.agents[agent].pending_action() is None


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_pending_action_roundtrip_and_resolution(mode):
    c = s6.StructuralContender(mode, 3)
    agent = c.agent_ids[0]
    started = c.begin_pending(agent, s6.s3._goal_candidates(), "pending")
    assert started["decision"] == "hold"
    assert c.pending_map() == {agent: "hold"}
    c.restart()
    assert c.pending_map() == {agent: "hold"}
    result = c.resolve_pending(agent, "interrupted")
    assert result["status"] == "interrupted" and c.pending_map() == {}
    with pytest.raises(ValueError, match="no pending"):
        c.resolve_pending(agent)


def test_restart_detects_missing_agent(monkeypatch):
    c = s6.StructuralContender("full", 3)
    from ghost.api import GhostAPI
    original = GhostAPI.agent
    monkeypatch.setattr(GhostAPI, "agent", lambda self, agent_id: None)
    with pytest.raises(RuntimeError, match="lost registered"):
        c.restart()
    monkeypatch.setattr(GhostAPI, "agent", original)


def test_restart_detects_state_drift(monkeypatch):
    c = s6.StructuralContender("baseline", 3)
    original = c._fingerprint
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        out = original()
        if calls["n"] > 1:
            out = deepcopy(out)
            out["relationships"][next(iter(out["relationships"]))] = 0.123456
        return out
    monkeypatch.setattr(c, "_fingerprint", fake)
    with pytest.raises(RuntimeError, match="changed decision-relevant"):
        c.restart()


@pytest.mark.parametrize("mode", ["full", "baseline"])
def test_light_level_structural_invariants(mode):
    out = s6._run_level(s6.canonical_levels()[0], mode)
    assert out["checkpoint_count"] == 37
    assert out["hidden_information_boundary"] is True
    assert out["all_badges_remembered"] is True
    assert out["pending_restart_ok"] is True
    assert out["structure"] == {"agents": 3, "sources": 3, "subjects": 6, "relationship_edges_seeded": 9, "overlapping_pending": 1}


def test_decision_map_extracts_all_checkpoint_choices():
    out = s6._run_level(s6.canonical_levels()[0], "full")
    mapping = s6._decision_map(out)
    assert len(mapping) == out["checkpoint_count"]
    assert mapping["guard_00:goal_initial"] == "hold"


@pytest.mark.parametrize(
    "full,baseline,expected",
    [(2, 1, "directional_ghost_advantage"), (1, 2, "directional_baseline_advantage"), (1, 1, "behavioral_parity_on_scored_constraints")],
)
def test_comparative_outcome(full, baseline, expected):
    assert s6._comparative_outcome(full, baseline) == expected


def test_matrix_rejects_empty_levels():
    with pytest.raises(ValueError, match="at least one level"):
        s6.run_matrix([])


def test_matrix_detects_checkpoint_count_mismatch(monkeypatch):
    original = s6._run_level
    def fake(level, mode):
        out = original(level, mode)
        if mode == "baseline":
            out["checkpoint_count"] += 1
        return out
    monkeypatch.setattr(s6, "_run_level", fake)
    with pytest.raises(RuntimeError, match="different checkpoint counts"):
        s6.run_matrix([s6.canonical_levels()[0]])


def test_structural_matrix_is_deterministic_and_reports_structure():
    first = s6.run_matrix()
    second = s6.run_matrix()
    assert first == second
    assert first["scored_checkpoints_per_contender"] == 150
    assert len(first["levels"]) == 3
    assert all(first["invariants"].values())
    assert first["decision_divergences"] >= 0
    assert first["totals"]["full"] <= 150 and first["totals"]["baseline"] <= 150
    assert [x["full"]["structure"]["agents"] for x in first["levels"]] == [3, 4, 5]


def test_experiment_claim_boundary_and_validity_marker():
    out = s6.run_experiment()
    assert out["schema"] == s6.SCHEMA
    assert out["strict_verdict"] == s6.VERDICT
    assert out["interpretation"]["duration_only_scaling"] is False
    assert out["interpretation"]["baseline_rewritten_for_ghost"] is False
    assert "general Ghost superiority" in out["claim_boundary"]
