from copy import deepcopy
import math

import pytest

from ghost.api import GhostAPI
from ghost_research.v112_action_policy_stage2 import (
    BASELINE_POLICY_ID,
    DEFAULT_POLICY_WEIGHTS,
    GHOST_POLICY_ID,
    POLICY_FEATURE_KEY,
    POLICY_PACKET_VERSION,
    apply_host_effects_to_baseline,
    apply_host_effects_to_ghost,
    baseline_policy_packet,
    flatten_ghost_state,
    ghost_policy_packet,
    max_score_delta,
    validate_baseline_state,
)


def candidate(candidate_id, *, utility, values=None, goals=None, capability=None, extra_features=None):
    features = {
        POLICY_FEATURE_KEY: {
            "utility": utility,
            "value_alignment": {} if values is None else values,
            "goal_support": {} if goals is None else goals,
        }
    }
    if extra_features:
        features.update(extra_features)
    return {
        "id": candidate_id,
        "capability": capability or candidate_id,
        "features": features,
    }


def setup_guard(api=None, agent_id="guard"):
    api = api or GhostAPI()
    guard = api.register_agent(
        agent_id,
        role="guard",
        values={"duty": 0.9, "survival": 0.4},
        goals={
            "hold_gate": {
                "status": "active",
                "priority": 0.9,
                "progress": 0.0,
                "value_weights": {"duty": 1.0},
            }
        },
        capabilities=["hold", "retreat", "wait"],
    )
    return api, guard


def decision_candidates():
    return [
        candidate(
            "hold",
            utility=0.1,
            values={"duty": 1.0, "survival": -0.2},
            goals={"hold_gate": 1.0},
        ),
        candidate(
            "retreat",
            utility=0.8,
            values={"duty": -0.5, "survival": 1.0},
            goals={"hold_gate": -0.5},
        ),
    ]


def set_decision_affordances(agent):
    return agent.set_affordances(decision_candidates(), context={"scene": "gate"})


def assert_packets_equivalent(ghost_packet, baseline_packet):
    assert ghost_packet["scores"] == baseline_packet["scores"]
    assert ghost_packet["weights"] == baseline_packet["weights"]
    assert ghost_packet["state"] == baseline_packet["state"]
    assert ghost_packet["goal_pressures"] == baseline_packet["goal_pressures"]
    assert ghost_packet["candidates"] == baseline_packet["candidates"]
    assert max_score_delta(ghost_packet, baseline_packet) == 0.0


def test_default_weights_are_explicit_and_stable():
    assert DEFAULT_POLICY_WEIGHTS == {"utility": 1.0, "values": 1.0, "goals": 1.0}


def test_flatten_ghost_state_is_minimal_copy():
    _, guard = setup_guard()
    flat = flatten_ghost_state(guard)
    assert flat == {
        "values": {"duty": 0.9, "survival": 0.4},
        "goals": {"hold_gate": {"status": "active", "priority": 0.9, "progress": 0.0}},
    }
    flat["values"]["duty"] = 0.0
    assert guard.values()["duty"] == 0.9


def test_baseline_state_requires_exact_top_level_shape():
    with pytest.raises(ValueError, match="exactly values and goals"):
        validate_baseline_state({"values": {}, "goals": {}, "extra": {}})
    with pytest.raises(ValueError, match="exactly values and goals"):
        validate_baseline_state([])


def test_baseline_state_requires_dict_channels():
    with pytest.raises(ValueError, match="values must be a dict"):
        validate_baseline_state({"values": [], "goals": {}})
    with pytest.raises(ValueError, match="goals must be a dict"):
        validate_baseline_state({"values": {}, "goals": []})


@pytest.mark.parametrize("bad", [True, "x", float("nan"), -0.1, 1.1])
def test_baseline_value_validation_rejects_non_unit_values(bad):
    with pytest.raises(ValueError):
        validate_baseline_state({"values": {"duty": bad}, "goals": {}})


def test_baseline_goal_requires_required_fields_and_valid_status():
    with pytest.raises(ValueError, match="missing required keys"):
        validate_baseline_state({"values": {}, "goals": {"g": {"status": "active"}}})
    with pytest.raises(ValueError, match="unsupported"):
        validate_baseline_state({
            "values": {},
            "goals": {"g": {"status": "unknown", "priority": 0.5, "progress": 0.5}},
        })


def test_baseline_goal_requires_string_status():
    with pytest.raises(ValueError, match="must be a string"):
        validate_baseline_state({
            "values": {},
            "goals": {"g": {"status": 3, "priority": 0.5, "progress": 0.5}},
        })


def test_information_equivalent_ghost_and_flat_baseline_are_exactly_equal():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    baseline = flatten_ghost_state(guard)
    gp = ghost_policy_packet(guard, affordances)
    bp = baseline_policy_packet(baseline, affordances)
    assert gp["policy_id"] == GHOST_POLICY_ID
    assert bp["policy_id"] == BASELINE_POLICY_ID
    assert gp["packet_version"] == POLICY_PACKET_VERSION
    assert_packets_equivalent(gp, bp)


def test_initial_equivalent_state_selects_hold_in_identical_action_runtime():
    ghost_api, ghost_guard = setup_guard(agent_id="ghost_guard")
    baseline_api, baseline_guard = setup_guard(agent_id="baseline_guard")
    baseline_state = flatten_ghost_state(baseline_guard)
    ghost_aff = set_decision_affordances(ghost_guard)
    baseline_aff = set_decision_affordances(baseline_guard)
    gp = ghost_policy_packet(ghost_guard, ghost_aff)
    bp = baseline_policy_packet(baseline_state, baseline_aff)
    assert_packets_equivalent(gp, bp)
    gd = ghost_guard.choose_action(gp["scores"], policy_id=gp["policy_id"])
    bd = baseline_guard.choose_action(bp["scores"], policy_id=bp["policy_id"])
    assert gd["candidate_id"] == bd["candidate_id"] == "hold"
    assert ghost_api.actions.pending("ghost_guard")["candidate_id"] == "hold"
    assert baseline_api.actions.pending("baseline_guard")["candidate_id"] == "hold"


def test_closed_loop_host_effect_changes_next_decision_for_both_representations():
    _, ghost_guard = setup_guard(agent_id="ghost_guard")
    _, baseline_guard = setup_guard(agent_id="baseline_guard")
    baseline_state = flatten_ghost_state(baseline_guard)
    ghost_aff = set_decision_affordances(ghost_guard)
    baseline_aff = set_decision_affordances(baseline_guard)
    gp1 = ghost_policy_packet(ghost_guard, ghost_aff)
    bp1 = baseline_policy_packet(baseline_state, baseline_aff)
    gd1 = ghost_guard.choose_action(gp1["scores"], policy_id=gp1["policy_id"])
    bd1 = baseline_guard.choose_action(bp1["scores"], policy_id=bp1["policy_id"])
    assert gd1["candidate_id"] == bd1["candidate_id"] == "hold"

    effects = {"goal_progress": {"hold_gate": 1.0}}
    gr = ghost_guard.resolve_action(gd1["decision_id"], "succeeded", outcome={"effects": effects})
    br = baseline_guard.resolve_action(bd1["decision_id"], "succeeded", outcome={"effects": effects})
    ghost_state2 = apply_host_effects_to_ghost(ghost_guard, gr["outcome"]["effects"])
    baseline_state2 = apply_host_effects_to_baseline(baseline_state, br["outcome"]["effects"])
    assert ghost_state2 == baseline_state2

    ghost_aff2 = set_decision_affordances(ghost_guard)
    baseline_aff2 = set_decision_affordances(baseline_guard)
    gp2 = ghost_policy_packet(ghost_guard, ghost_aff2)
    bp2 = baseline_policy_packet(baseline_state2, baseline_aff2)
    assert_packets_equivalent(gp2, bp2)
    gd2 = ghost_guard.choose_action(gp2["scores"], policy_id=gp2["policy_id"])
    bd2 = baseline_guard.choose_action(bp2["scores"], policy_id=bp2["policy_id"])
    assert gd2["candidate_id"] == bd2["candidate_id"] == "retreat"
    assert gp1["scores"] != gp2["scores"]


def test_goal_progress_mutation_changes_only_goal_components():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    before = ghost_policy_packet(guard, affordances)
    guard.set_goal_progress("hold_gate", 1.0)
    after = ghost_policy_packet(guard, affordances)
    for candidate_id in before["candidates"]:
        b = before["candidates"][candidate_id]["components"]
        a = after["candidates"][candidate_id]["components"]
        assert a["utility"] == b["utility"]
        assert a["values"] == b["values"]
        assert a["goals"] != b["goals"]


def test_reverting_relevant_state_restores_exact_scores():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    before = ghost_policy_packet(guard, affordances)
    guard.set_goal_progress("hold_gate", 1.0)
    changed = ghost_policy_packet(guard, affordances)
    guard.set_goal_progress("hold_gate", 0.0)
    restored = ghost_policy_packet(guard, affordances)
    assert changed["scores"] != before["scores"]
    assert restored["scores"] == before["scores"]


def test_irrelevant_value_perturbation_does_not_change_scores():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    before = ghost_policy_packet(guard, affordances)
    guard.set_value("tradition", 0.99)
    after = ghost_policy_packet(guard, affordances)
    assert before["scores"] == after["scores"]
    assert before["candidates"] == after["candidates"]


def test_irrelevant_candidate_feature_is_ignored():
    _, guard = setup_guard()
    a = candidate("hold", utility=0.2, values={"duty": 1.0}, goals={}, extra_features={"animation": "brace"})
    guard.set_affordances([a])
    p = ghost_policy_packet(guard, guard.affordances())
    assert list(p["scores"]) == ["hold"]


def test_inactive_satisfied_and_abandoned_goals_have_zero_pressure():
    for status in ("inactive", "satisfied", "abandoned"):
        api = GhostAPI()
        guard = api.register_agent(
            "g", values={}, goals={"goal": {"status": status, "priority": 1.0, "progress": 0.0}}, capabilities=["wait"]
        )
        guard.set_affordances([candidate("wait", utility=0.0, goals={"goal": 1.0})])
        p = ghost_policy_packet(guard, guard.affordances())
        assert p["goal_pressures"]["goal"] == 0.0
        assert p["scores"]["wait"] == 0.0


def test_blocked_goal_retains_pressure():
    api = GhostAPI()
    guard = api.register_agent(
        "g", values={}, goals={"goal": {"status": "blocked", "priority": 0.8, "progress": 0.25}}, capabilities=["wait"]
    )
    guard.set_affordances([candidate("wait", utility=0.0, goals={"goal": 1.0})])
    p = ghost_policy_packet(guard, guard.affordances())
    assert p["goal_pressures"]["goal"] == pytest.approx(0.6)


def test_missing_referenced_value_or_goal_contributes_zero():
    api = GhostAPI()
    guard = api.register_agent("g", values={}, goals={}, capabilities=["wait"])
    guard.set_affordances([candidate("wait", utility=0.2, values={"missing": 1.0}, goals={"missing": 1.0})])
    p = ghost_policy_packet(guard, guard.affordances())
    assert p["candidates"]["wait"]["components"] == {"utility": 0.2, "values": 0.0, "goals": 0.0}


def test_empty_value_and_goal_maps_are_valid():
    api = GhostAPI()
    guard = api.register_agent("g", values={}, goals={}, capabilities=["wait"])
    guard.set_affordances([candidate("wait", utility=-0.2)])
    p = ghost_policy_packet(guard, guard.affordances())
    assert p["scores"] == {"wait": -0.2}


def test_custom_weights_are_applied_by_channel():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances, weights={"utility": 2.0, "values": 0.0, "goals": 0.0})
    assert p["scores"] == {"hold": 0.2, "retreat": 1.6}


def test_state_ablation_collapses_exactly_to_immediate_utility():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances, weights={"utility": 1.0, "values": 0.0, "goals": 0.0})
    assert p["scores"] == {"hold": 0.1, "retreat": 0.8}


def test_overwhelming_immediate_utility_can_dominate_ghost_state():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances, weights={"utility": 10.0, "values": 1.0, "goals": 1.0})
    d = guard.choose_action(p["scores"], policy_id=p["policy_id"])
    assert d["candidate_id"] == "retreat"


def test_zero_all_channel_weights_produces_deterministic_tie():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances, weights={"utility": 0.0, "values": 0.0, "goals": 0.0})
    assert p["scores"] == {"hold": 0.0, "retreat": 0.0}
    assert guard.choose_action(p["scores"], policy_id=p["policy_id"])["candidate_id"] == "hold"


def test_policy_weights_reject_wrong_shape_negative_and_nonfinite():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    for weights in (
        {},
        {"utility": 1.0, "values": 1.0, "goals": 1.0, "x": 1.0},
        {"utility": -1.0, "values": 1.0, "goals": 1.0},
        {"utility": math.inf, "values": 1.0, "goals": 1.0},
        {"utility": True, "values": 1.0, "goals": 1.0},
    ):
        with pytest.raises(ValueError):
            ghost_policy_packet(guard, affordances, weights=weights)


def test_affordance_record_validation_rejects_missing_empty_or_nondict_candidates():
    state = {"values": {}, "goals": {}}
    for record in (None, {}, {"candidates": []}, {"candidates": "x"}):
        with pytest.raises(ValueError):
            baseline_policy_packet(state, record)


def test_candidate_validation_rejects_bad_shapes():
    state = {"values": {}, "goals": {}}
    bad_records = [
        {"candidates": ["wait"]},
        {"candidates": [{"id": "wait", "features": []}]},
        {"candidates": [{"id": "wait", "features": {}}]},
        {"candidates": [{"id": "wait", "features": {POLICY_FEATURE_KEY: []}}]},
        {"candidates": [{"id": "wait", "features": {POLICY_FEATURE_KEY: {"utility": 0.0, "value_alignment": {}}}}]},
    ]
    for record in bad_records:
        with pytest.raises(ValueError):
            baseline_policy_packet(state, record)


def test_candidate_validation_rejects_bad_channel_map_and_signed_values():
    state = {"values": {}, "goals": {}}
    bad = [
        candidate("wait", utility=True),
        candidate("wait", utility=1.1),
        candidate("wait", utility=0.0, values=[]),
        candidate("wait", utility=0.0, goals=[]),
        candidate("wait", utility=0.0, values={"duty": 1.1}),
    ]
    for c in bad:
        with pytest.raises(ValueError):
            baseline_policy_packet(state, {"candidates": [c]})


def test_candidate_duplicate_ids_are_rejected_even_without_affordance_runtime():
    c = candidate("wait", utility=0.0)
    with pytest.raises(ValueError, match="duplicate candidate id"):
        baseline_policy_packet({"values": {}, "goals": {}}, {"candidates": [c, deepcopy(c)]})


def test_host_effects_apply_identically_to_ghost_and_flat_baseline():
    _, guard = setup_guard()
    baseline = flatten_ghost_state(guard)
    effects = {
        "values": {"duty": 0.7, "compassion": 0.6},
        "goal_progress": {"hold_gate": 0.5},
        "goal_priority": {"hold_gate": 0.4},
    }
    gs = apply_host_effects_to_ghost(guard, effects)
    bs = apply_host_effects_to_baseline(baseline, effects)
    assert gs == bs


def test_none_host_effects_are_a_noop_copy():
    _, guard = setup_guard()
    baseline = flatten_ghost_state(guard)
    before = deepcopy(baseline)
    after = apply_host_effects_to_baseline(baseline, None)
    assert after == before
    assert after is not baseline


def test_host_effect_validation_rejects_bad_shapes_and_unknown_channels():
    _, guard = setup_guard()
    baseline = flatten_ghost_state(guard)
    for effects in ([], {"unknown": {}}, {"values": []}, {"goal_progress": []}, {"goal_priority": []}):
        with pytest.raises(ValueError):
            apply_host_effects_to_baseline(baseline, effects)


@pytest.mark.parametrize("effects", [
    {"values": {"duty": -0.1}},
    {"values": {"duty": float("nan")}},
    {"goal_progress": {"hold_gate": 1.1}},
    {"goal_priority": {"hold_gate": True}},
])
def test_host_effect_numeric_validation(effects):
    _, guard = setup_guard()
    with pytest.raises(ValueError):
        apply_host_effects_to_ghost(guard, effects)


def test_host_effect_rejects_unknown_goal_for_both_representations():
    _, guard = setup_guard()
    baseline = flatten_ghost_state(guard)
    effects = {"goal_progress": {"missing": 0.2}}
    with pytest.raises(ValueError, match="unknown Ghost goal"):
        apply_host_effects_to_ghost(guard, effects)
    with pytest.raises(ValueError, match="unknown baseline goal"):
        apply_host_effects_to_baseline(baseline, effects)


def test_snapshot_restore_preserves_post_consequence_policy_and_action_history():
    api, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances)
    d = guard.choose_action(p["scores"], policy_id=p["policy_id"])
    effects = {"goal_progress": {"hold_gate": 1.0}}
    r = guard.resolve_action(d["decision_id"], "succeeded", outcome={"effects": effects})
    apply_host_effects_to_ghost(guard, r["outcome"]["effects"])
    before_history = guard.action_history()
    restored = GhostAPI.from_snapshot(api.snapshot())
    restored_guard = restored.agent("guard")
    assert restored_guard is not None
    assert restored_guard.action_history() == before_history
    affordances2 = set_decision_affordances(restored_guard)
    p2 = ghost_policy_packet(restored_guard, affordances2)
    assert restored_guard.choose_action(p2["scores"], policy_id=p2["policy_id"])["candidate_id"] == "retreat"


def test_snapshot_before_outcome_preserves_pending_decision_and_blocks_affordance_change():
    api, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    p = ghost_policy_packet(guard, affordances)
    d = guard.choose_action(p["scores"], policy_id=p["policy_id"])
    restored = GhostAPI.from_snapshot(api.snapshot())
    rg = restored.agent("guard")
    assert rg.pending_action()["decision_id"] == d["decision_id"]
    with pytest.raises(ValueError, match="pending"):
        set_decision_affordances(rg)


def test_candidate_order_does_not_change_score_table_or_choice():
    api1, g1 = setup_guard(agent_id="a")
    api2, g2 = setup_guard(agent_id="b")
    cands = decision_candidates()
    a1 = g1.set_affordances(cands)
    a2 = g2.set_affordances(list(reversed(cands)))
    p1 = ghost_policy_packet(g1, a1)
    p2 = ghost_policy_packet(g2, a2)
    assert p1["scores"] == p2["scores"]
    assert g1.choose_action(p1["scores"], policy_id=p1["policy_id"])["candidate_id"] == "hold"
    assert g2.choose_action(p2["scores"], policy_id=p2["policy_id"])["candidate_id"] == "hold"
    assert api1.actions.current("a") is not None
    assert api2.actions.current("b") is not None


def test_baseline_state_input_is_not_mutated_by_scoring_or_effect_application():
    state = {
        "values": {"duty": 0.9},
        "goals": {"hold_gate": {"status": "active", "priority": 0.9, "progress": 0.0}},
    }
    original = deepcopy(state)
    record = {"candidates": [candidate("wait", utility=0.0, values={"duty": 1.0}, goals={"hold_gate": 1.0})]}
    baseline_policy_packet(state, record)
    updated = apply_host_effects_to_baseline(state, {"goal_progress": {"hold_gate": 1.0}})
    assert state == original
    assert updated != original


def test_policy_packet_is_detached_from_agent_state_and_affordance_input():
    _, guard = setup_guard()
    affordances = set_decision_affordances(guard)
    packet = ghost_policy_packet(guard, affordances)
    packet["state"]["values"]["duty"] = 0.0
    packet["candidates"]["hold"]["raw"]["utility"] = -1.0
    assert guard.values()["duty"] == 0.9
    assert guard.affordances()["candidates"][0]["features"][POLICY_FEATURE_KEY]["utility"] == 0.1


def test_max_score_delta_detects_difference_and_validates_packet_shapes():
    left = {"scores": {"a": 1.0, "b": 2.0}}
    right = {"scores": {"a": 1.25, "b": 1.5}}
    assert max_score_delta(left, right) == 0.5
    assert max_score_delta({"scores": {}}, {"scores": {}}) == 0.0
    with pytest.raises(ValueError, match="score dictionaries"):
        max_score_delta({}, right)
    with pytest.raises(ValueError, match="different candidate sets"):
        max_score_delta(left, {"scores": {"a": 1.0}})
    with pytest.raises(ValueError):
        max_score_delta({"scores": {"a": True}}, {"scores": {"a": 1.0}})


def test_policy_output_scores_are_finite_across_extreme_valid_inputs():
    api = GhostAPI()
    guard = api.register_agent(
        "g",
        values={"v": 1.0},
        goals={"goal": {"status": "active", "priority": 1.0, "progress": 0.0}},
        capabilities=["pos", "neg"],
    )
    guard.set_affordances([
        candidate("pos", utility=1.0, values={"v": 1.0}, goals={"goal": 1.0}),
        candidate("neg", utility=-1.0, values={"v": -1.0}, goals={"goal": -1.0}),
    ])
    p = ghost_policy_packet(guard, guard.affordances(), weights={"utility": 1e100, "values": 1e100, "goals": 1e100})
    assert all(math.isfinite(x) for x in p["scores"].values())
    assert p["scores"]["pos"] > p["scores"]["neg"]

def test_none_alignment_maps_normalize_to_empty():
    state = {"values": {}, "goals": {}}
    record = {"candidates": [{
        "id": "wait", "capability": "wait",
        "features": {POLICY_FEATURE_KEY: {"utility": 0.0, "value_alignment": None, "goal_support": None}},
    }]}
    p = baseline_policy_packet(state, record)
    assert p["scores"] == {"wait": 0.0}


def test_normalized_duplicate_keys_are_rejected_across_channels():
    with pytest.raises(ValueError, match="duplicate normalized key"):
        baseline_policy_packet(
            {"values": {}, "goals": {}},
            {"candidates": [candidate("wait", utility=0.0, values={" duty ": 1.0, "duty": 1.0})]},
        )
    with pytest.raises(ValueError, match="duplicate normalized key"):
        validate_baseline_state({"values": {" duty ": 0.5, "duty": 0.5}, "goals": {}})
    with pytest.raises(ValueError, match="duplicate normalized key"):
        validate_baseline_state({
            "values": {},
            "goals": {
                " goal ": {"status": "active", "priority": 0.5, "progress": 0.0},
                "goal": {"status": "active", "priority": 0.5, "progress": 0.0},
            },
        })
    _, guard = setup_guard()
    with pytest.raises(ValueError, match="duplicate normalized key"):
        apply_host_effects_to_ghost(guard, {"values": {" duty ": 0.5, "duty": 0.5}})


def test_baseline_goal_record_must_be_dict():
    with pytest.raises(ValueError, match="must be a dict"):
        validate_baseline_state({"values": {}, "goals": {"g": []}})
