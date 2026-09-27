import math
from copy import deepcopy

import pytest

from ghost.api import GhostAPI
import ghost_research.v112_continuity_stress_stage3 as s3


def base_state():
    return {
        "values": {"duty": 0.8},
        "goals": {"g": {"status": "active", "priority": 0.7, "progress": 0.2}},
    }


def base_beliefs():
    return {"visitor": {"threat": {"benign": 0.5, "hostile": 0.5}}}


def make_baseline(**kwargs):
    return s3.FlatContinuityBaseline(base_state(), base_beliefs(), **kwargs)


def make_ghost():
    api = GhostAPI()
    agent = api.register_agent(
        "guard",
        values={"duty": 0.8},
        goals={"g": {"status": "active", "priority": 0.7, "progress": 0.2}},
        capabilities=["admit", "challenge", "wait"],
    )
    s3.seed_ghost_belief(api)
    return api, agent


def threat_candidates():
    common = {"subject": "visitor", "dimension": "threat"}
    return [
        s3.candidate("admit", belief={**common, "alignment": {"benign": 1.0, "hostile": -1.0}}),
        s3.candidate("challenge", belief={**common, "alignment": {"benign": -1.0, "hostile": 1.0}}),
    ]


def test_constants_are_stable():
    assert s3.DEFAULT_WEIGHTS == {"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}
    assert s3.BASELINE_SIGNAL_GAIN == 2.0
    assert len(s3.canonical_variants()) == 3


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf")])
def test_finite_rejects_bad_numbers(value):
    with pytest.raises(ValueError, match="finite"):
        s3._finite(value, "x")


def test_unit_and_signed_validation():
    assert s3._unit(0.25, "x") == 0.25
    assert s3._signed(-0.5, "x") == -0.5
    with pytest.raises(ValueError, match="\[0, 1\]"):
        s3._unit(1.1, "x")
    with pytest.raises(ValueError, match="\[-1, 1\]"):
        s3._signed(-1.1, "x")


@pytest.mark.parametrize("value", [True, 0, -1, 1.5])
def test_positive_int_validation(value):
    with pytest.raises(ValueError, match="positive integer"):
        s3._positive_int(value, "n")
    assert s3._positive_int(2, "n") == 2


def test_weights_default_custom_and_validation():
    assert s3._weights(None) == s3.DEFAULT_WEIGHTS
    custom = {"utility": 2, "values": 0, "goals": 1, "beliefs": 3}
    assert s3._weights(custom) == {"beliefs": 3.0, "goals": 1.0, "utility": 2.0, "values": 0.0}
    with pytest.raises(ValueError, match="exactly"):
        s3._weights({})
    with pytest.raises(ValueError, match="non-negative"):
        s3._weights({"utility": -1, "values": 0, "goals": 0, "beliefs": 0})


def test_distribution_and_belief_tree_validation():
    assert s3._distribution({"b": 0.25, "a": 0.75}, "d") == {"a": 0.75, "b": 0.25}
    for bad in (None, {"a": 1.0}, {"a": 0.2, "b": 0.2}):
        with pytest.raises(ValueError):
            s3._distribution(bad, "d")
    with pytest.raises(ValueError, match="unique"):
        s3._distribution({" a ": 0.5, "a": 0.5}, "d")
    assert s3._belief_tree(base_beliefs()) == base_beliefs()
    with pytest.raises(ValueError, match="dict"):
        s3._belief_tree([])
    with pytest.raises(ValueError, match="non-empty"):
        s3._belief_tree({"visitor": {}})
    with pytest.raises(ValueError, match="duplicate"):
        s3._belief_tree({"visitor": {" a ": {"x": 0.5, "y": 0.5}, "a": {"x": 0.5, "y": 0.5}}})


def test_json_copy_is_strict():
    value = {"x": [1, 2.5, True, None]}
    assert s3._json_copy(value) == value
    with pytest.raises(ValueError, match="JSON-safe"):
        s3._json_copy({"x": float("nan")})
    with pytest.raises(ValueError, match="JSON-safe"):
        s3._json_copy({"x": {1, 2}})


def test_flat_baseline_belief_access_is_copy_and_missing_rejected():
    b = make_baseline()
    d = b.belief_distribution("visitor", "threat")
    d["hostile"] = 1.0
    assert b.belief_distribution("visitor", "threat")["hostile"] == 0.5
    with pytest.raises(ValueError, match="no belief"):
        b.belief_distribution("missing", "threat")


def test_flat_baseline_signal_positive_negative_and_noop():
    b = make_baseline()
    assert b.apply_signal("visitor", "threat", "hostile", "benign", 0.0) == {"benign": 0.5, "hostile": 0.5}
    assert b.apply_signal("visitor", "threat", "hostile", "benign", 0.7)["hostile"] > 0.5
    assert b.apply_signal("visitor", "threat", "hostile", "benign", -0.9)["hostile"] < 0.5
    before = b.belief_distribution("visitor", "threat")
    assert b.apply_signal("visitor", "threat", "hostile", "benign", 1.0, reliability=0.0) == before


def test_flat_baseline_signal_rejects_wrong_candidates():
    b = make_baseline()
    with pytest.raises(ValueError, match="exactly"):
        b.apply_signal("visitor", "threat", "hostile", "hostile", 0.5)
    with pytest.raises(ValueError, match="exactly"):
        b.apply_signal("visitor", "threat", "other", "benign", 0.5)


def test_flat_baseline_host_effects_update_own_state():
    b = make_baseline()
    out = b.apply_host_effects({"goal_progress": {"g": 0.9}})
    assert out["goals"]["g"]["progress"] == 0.9
    assert b.decision_state["goals"]["g"]["progress"] == 0.9


def test_flat_baseline_observation_history_trims_and_queries():
    b = make_baseline(history_limit=2)
    b.observe("e1", "visitor", {"badge": "red"})
    b.observe("e2", "other", {"x": 1})
    b.observe("e3", "visitor", {"badge": "blue"})
    assert [x["event"] for x in b.observations] == ["e2", "e3"]
    assert not b.has_observation("visitor", "badge", "red")
    assert b.has_observation("visitor", "badge", "blue")
    assert b.observe("e4", "visitor")["features"] == {}


def test_flat_baseline_snapshot_roundtrip():
    b = make_baseline()
    b.observe("e1", "visitor", {"badge": "red"})
    b.apply_signal("visitor", "threat", "hostile", "benign", 0.4)
    restored = s3.FlatContinuityBaseline.from_snapshot(b.snapshot())
    assert restored.snapshot() == b.snapshot()


def test_flat_baseline_snapshot_validation():
    good = make_baseline().snapshot()
    cases = []
    x = dict(good); x["schema"] = "bad"; cases.append(x)
    x = dict(good); x["sequence"] = True; cases.append(x)
    x = dict(good); x["observations"] = "bad"; cases.append(x)
    x = dict(good); x["history_limit"] = 0; cases.append(x)
    x = dict(good); x["extra"] = 1; cases.append(x)
    for case in cases:
        with pytest.raises(ValueError):
            s3.FlatContinuityBaseline.from_snapshot(case)


def test_snapshot_observation_record_order_and_sequence_validation():
    b = make_baseline(history_limit=3)
    b.observe("e1", "visitor", {})
    b.observe("e2", "visitor", {})
    good = b.snapshot()
    x = deepcopy(good := good)
    x["observations"][0]["bad"] = 1
    with pytest.raises(ValueError, match="record"):
        s3.FlatContinuityBaseline.from_snapshot(x)
    x = deepcopy(good); x["observations"][1]["sequence"] = 1
    with pytest.raises(ValueError, match="ordered"):
        s3.FlatContinuityBaseline.from_snapshot(x)
    x = deepcopy(good); x["sequence"] = 3
    with pytest.raises(ValueError, match="inconsistent"):
        s3.FlatContinuityBaseline.from_snapshot(x)
    x = make_baseline().snapshot(); x["sequence"] = 1
    with pytest.raises(ValueError, match="inconsistent"):
        s3.FlatContinuityBaseline.from_snapshot(x)
    x = deepcopy(good); x["history_limit"] = 1
    with pytest.raises(ValueError, match="history"):
        s3.FlatContinuityBaseline.from_snapshot(x)


def test_belief_feature_none_valid_and_invalid_shapes():
    c = s3.candidate("wait")
    assert s3._belief_feature(c, 0) == ("wait", None)
    with pytest.raises(ValueError, match="feature dictionary"):
        s3._belief_feature("bad", 0)
    c = {"id": "wait", "features": {s3.BELIEF_FEATURE_KEY: []}}
    with pytest.raises(ValueError, match="invalid belief"):
        s3._belief_feature(c, 0)
    c = {"id": "wait", "features": {s3.BELIEF_FEATURE_KEY: {"subject": "s", "dimension": "d", "alignment": {}}}}
    with pytest.raises(ValueError, match="non-empty"):
        s3._belief_feature(c, 0)


def test_belief_feature_normalizes_and_rejects_duplicate_alignment():
    c = s3.candidate("wait", belief={"subject": " S ", "dimension": " D ", "alignment": {"a": 1.0, "b": -1.0}})
    _, feature = s3._belief_feature(c, 0)
    assert feature == {"subject": "S", "dimension": "D", "alignment": {"a": 1.0, "b": -1.0}}
    c["features"][s3.BELIEF_FEATURE_KEY]["alignment"] = {" a ": 0.5, "a": 0.5}
    with pytest.raises(ValueError, match="duplicate"):
        s3._belief_feature(c, 0)


def test_ghost_distribution_valid_and_missing():
    api, _ = make_ghost()
    assert s3._ghost_distribution(api, "guard", "visitor", "threat") == {"benign": 0.5, "hostile": 0.5}
    with pytest.raises(ValueError, match="missing"):
        s3._ghost_distribution(api, "guard", "missing", "threat")
    with pytest.raises(ValueError, match="missing"):
        s3._ghost_distribution(api, "guard", "visitor", "missing")


def test_stage3_policy_packets_use_same_base_and_belief_feature():
    api, agent = make_ghost()
    baseline = make_baseline()
    candidates = threat_candidates()
    gp = s3.ghost_policy(api, "guard", agent, agent.set_affordances(candidates))
    transport = GhostAPI().register_agent("b", capabilities=["admit", "challenge"])
    bp = s3.baseline_policy(baseline, transport.set_affordances(candidates))
    assert gp["policy_id"] == s3.GHOST_POLICY_ID
    assert bp["policy_id"] == s3.BASELINE_POLICY_ID
    assert gp["packet_version"] == bp["packet_version"] == s3.PACKET_VERSION
    assert gp["scores"] == bp["scores"] == {"admit": 0.0, "challenge": 0.0}


def test_merge_packet_rejects_invalid_affordance_and_candidate_mismatch():
    base = {"scores": {"a": 0.0}}
    w = s3._weights(None)
    with pytest.raises(ValueError, match="non-empty"):
        s3._merge_packet(base, {}, lambda *_: {}, "p", w)
    rec = {"candidates": [s3.candidate("b")]}
    with pytest.raises(ValueError, match="mismatches"):
        s3._merge_packet(base, rec, lambda *_: {}, "p", w)
    rec = {"candidates": [s3.candidate("a"), s3.candidate("a")]}
    base2 = {"scores": {"a": 0.0}}
    with pytest.raises(ValueError, match="mismatches"):
        s3._merge_packet(base2, rec, lambda *_: {}, "p", w)


def test_merge_packet_requires_alignment_candidates_and_full_coverage():
    belief = {"subject": "visitor", "dimension": "threat", "alignment": {"missing": 1.0}}
    rec = {"candidates": [s3.candidate("a", belief=belief)]}
    with pytest.raises(ValueError, match="missing"):
        s3._merge_packet({"scores": {"a": 0.0}}, rec, lambda *_: {"hostile": 1.0}, "p", s3._weights(None))
    rec = {"candidates": [s3.candidate("a")]}
    with pytest.raises(ValueError, match="cover"):
        s3._merge_packet({"scores": {"a": 0.0, "b": 0.0}}, rec, lambda *_: {}, "p", s3._weights(None))


def test_custom_policy_weights_and_belief_ablation():
    api, agent = make_ghost()
    cands = threat_candidates()
    aff = agent.set_affordances(cands)
    s3.ghost_signal(api, 0.8)
    full = s3.ghost_policy(api, "guard", agent, aff)
    ablated = s3.ghost_policy(api, "guard", agent, aff, weights={"utility": 1, "values": 1, "goals": 1, "beliefs": 0})
    assert full["scores"]["challenge"] > full["scores"]["admit"]
    assert ablated["scores"] == {"admit": 0.0, "challenge": 0.0}


def test_seed_and_ghost_signal_positive_negative_and_noop():
    api = GhostAPI()
    b = s3.seed_ghost_belief(api, probability=0.4)
    assert b["dimensions"]["threat"]["candidates"]["hostile"] == 0.4
    with pytest.raises(ValueError):
        s3.seed_ghost_belief(api, probability=1.2)
    api = GhostAPI()
    assert s3.ghost_signal(api, 0.0)["dimensions"]["threat"]["candidates"]["hostile"] == 0.5
    assert s3.ghost_signal(api, 0.7)["dimensions"]["threat"]["candidates"]["hostile"] > 0.5
    assert s3.ghost_signal(api, -0.9)["dimensions"]["threat"]["candidates"]["hostile"] < 0.5
    before = api.get_belief("guard", "visitor")
    assert s3.ghost_signal(api, 1.0, reliability=0.0) == before


def test_ghost_has_observation_true_and_false():
    api = GhostAPI(); agent = api.register_agent("guard", capabilities=["wait"])
    agent.observe("badge_seen", kind="direct", subject="visitor", features={"badge": "red"})
    assert s3.ghost_has_observation(agent, "visitor", "badge", "red")
    assert not s3.ghost_has_observation(agent, "visitor", "badge", "blue")


def test_candidate_builder_with_and_without_belief():
    plain = s3.candidate("wait", utility=0.2, values={"duty": 1.0}, goals={"g": 0.5})
    assert s3.BELIEF_FEATURE_KEY not in plain["features"]
    enriched = s3.candidate("wait", belief={"subject": "s", "dimension": "d", "alignment": {"a": 1.0}})
    assert s3.BELIEF_FEATURE_KEY in enriched["features"]
    with pytest.raises(ValueError):
        s3.candidate("wait", utility=1.2)


def test_trial_variant_validation():
    with pytest.raises(ValueError, match="shape"):
        s3.run_trial({})
    with pytest.raises(ValueError, match="positive hostile"):
        s3.run_trial({"id": "x", "hostile": [], "contradiction": [-0.5]})
    with pytest.raises(ValueError, match="positive hostile"):
        s3.run_trial({"id": "x", "hostile": [-0.2], "contradiction": [-0.5]})
    with pytest.raises(ValueError, match="positive hostile"):
        s3.run_trial({"id": "x", "hostile": [0.2], "contradiction": [0.5]})


@pytest.mark.parametrize("variant", s3.canonical_variants())
def test_each_canonical_long_horizon_trial_is_deterministic_and_scored(variant):
    first = s3.run_trial(variant)
    second = s3.run_trial(variant)
    assert first == second
    assert first["checkpoint_count"] == 10
    assert 0 <= first["ghost_correct"] <= 10
    assert 0 <= first["baseline_correct"] <= 10
    assert 0 <= first["divergence_count"] <= 10
    assert set(first["hidden_information_boundary"]) == {"ghost", "baseline"}
    assert isinstance(first["restart_scores_match"], bool)
    assert set(first["delayed_relevance_recall"]) == {"ghost", "baseline"}
    assert all(value > 0 for value in first["snapshot_bytes"].values())


def test_run_trial_can_record_failed_recall_without_crashing(monkeypatch):
    monkeypatch.setattr(s3, "ghost_has_observation", lambda *args: False)
    monkeypatch.setattr(s3.FlatContinuityBaseline, "has_observation", lambda *args: False)
    result = s3.run_trial(s3.canonical_variants()[0])
    assert result["delayed_relevance_recall"] == {"ghost": False, "baseline": False}


def test_run_trial_detects_restart_agent_loss(monkeypatch):
    original = GhostAPI.from_snapshot
    calls = {"n": 0}

    def broken(snapshot):
        calls["n"] += 1
        if calls["n"] == 1:
            return GhostAPI()
        return original(snapshot)

    monkeypatch.setattr(GhostAPI, "from_snapshot", staticmethod(broken))
    with pytest.raises(RuntimeError, match="lost registered agent"):
        s3.run_trial(s3.canonical_variants()[0])


def fake_trial(ghost_correct, baseline_correct, *, hidden=True, restart=True, recall=True):
    return {
        "variant": "fake",
        "checkpoint_count": 10,
        "ghost_correct": ghost_correct,
        "baseline_correct": baseline_correct,
        "divergence_count": abs(ghost_correct - baseline_correct),
        "hidden_information_boundary": {"ghost": hidden, "baseline": hidden},
        "restart_scores_match": restart,
        "delayed_relevance_recall": {"ghost": recall, "baseline": recall},
    }


def test_matrix_real_result_is_deterministic_without_preordaining_winner():
    first = s3.run_matrix()
    second = s3.run_matrix()
    assert first == second
    assert first["trial_count"] == 3
    assert first["scored_checkpoints"] == 30
    assert 0 <= first["ghost_correct"] <= 30
    assert 0 <= first["baseline_correct"] <= 30
    assert 0 <= first["decision_divergence_count"] <= 30
    expected = s3._comparative_outcome(first["ghost_correct"], first["baseline_correct"])
    assert first["comparative_outcome"] == expected


def test_matrix_requires_nonempty_list():
    for bad in ([], {}, None):
        if bad is None:
            continue
        with pytest.raises(ValueError, match="at least one"):
            s3.run_matrix(bad)


def test_matrix_comparative_outcome_branches(monkeypatch):
    monkeypatch.setattr(s3, "run_trial", lambda _: fake_trial(9, 8))
    assert s3.run_matrix([{"x": 1}])["comparative_outcome"] == "directional_ghost_advantage"
    monkeypatch.setattr(s3, "run_trial", lambda _: fake_trial(7, 9))
    assert s3.run_matrix([{"x": 1}])["comparative_outcome"] == "directional_baseline_advantage"
    monkeypatch.setattr(s3, "run_trial", lambda _: fake_trial(8, 8))
    assert s3.run_matrix([{"x": 1}])["comparative_outcome"] == "behavioral_parity_on_scored_constraints"


def test_matrix_records_invariant_failures(monkeypatch):
    monkeypatch.setattr(s3, "run_trial", lambda _: fake_trial(8, 8, hidden=False, restart=False, recall=False))
    result = s3.run_matrix([{"x": 1}])
    assert result["invariant_failures"] == [
        "fake:hidden_information_boundary",
        "fake:restart_scores",
        "fake:delayed_relevance_recall",
    ]
