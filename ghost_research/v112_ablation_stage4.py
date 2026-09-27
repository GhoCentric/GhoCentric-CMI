"""Research-only Stage-4 causal ablation and failure-attribution experiment.

Stage 4 freezes the Stage-3 event/checkpoint matrix and selectively removes
Ghost policy contributions.  The strong flat baseline remains unchanged.
Ablations disable decision contribution, not storage, so the experiment can
attribute behavioral changes without editing production ``ghost.*`` code.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research.v112_action_policy_stage2 import apply_host_effects_to_ghost

SCHEMA = "ghost.v1.12-dev.ablation.stage4.matrix.v1"
VERDICT = "V112_ABLATION_STAGE4_EXPERIMENT_VALID"

_CONDITION_KEYS = frozenset({"weights", "recall_enabled"})
_WEIGHT_KEYS = frozenset({"utility", "values", "goals", "beliefs"})

_PRE_REGISTERED = {
    "full": ({"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}, True),
    "no_values": ({"utility": 1.0, "values": 0.0, "goals": 1.0, "beliefs": 1.0}, True),
    "no_goals": ({"utility": 1.0, "values": 1.0, "goals": 0.0, "beliefs": 1.0}, True),
    "no_beliefs": ({"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 0.0}, True),
    "no_recall": ({"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}, False),
    "no_values_goals": ({"utility": 1.0, "values": 0.0, "goals": 0.0, "beliefs": 1.0}, True),
    "no_values_beliefs": ({"utility": 1.0, "values": 0.0, "goals": 1.0, "beliefs": 0.0}, True),
    "no_goals_beliefs": ({"utility": 1.0, "values": 1.0, "goals": 0.0, "beliefs": 0.0}, True),
    "utility_only": ({"utility": 1.0, "values": 0.0, "goals": 0.0, "beliefs": 0.0}, False),
}

_EXPECTED = {
    "goal_initial": "hold",
    "conflict_initial": "hold",
    "hostile_observed": "challenge",
    "hidden_fact_boundary": "challenge",
    "restart_continuity": "challenge",
    "delayed_relevance": "challenge",
    "contradiction_revised": "admit",
    "conflict_shift": "assist",
    "goal_delayed_consequence": "retreat",
    "recurrence_final": "retreat",
}


def _condition(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _CONDITION_KEYS:
        raise ValueError("condition must contain exactly weights and recall_enabled")
    weights = raw["weights"]
    if not isinstance(weights, dict) or set(weights) != _WEIGHT_KEYS:
        raise ValueError("condition weights must contain utility, values, goals, beliefs")
    normalized = s3._weights(weights)
    recall = raw["recall_enabled"]
    if not isinstance(recall, bool):
        raise ValueError("condition recall_enabled must be bool")
    return {"weights": normalized, "recall_enabled": recall}


def preregistered_conditions() -> dict[str, dict]:
    return {
        name: _condition({"weights": deepcopy(weights), "recall_enabled": recall})
        for name, (weights, recall) in _PRE_REGISTERED.items()
    }


def _choose(ghost_api, ghost_agent, baseline_agent, baseline, candidates, checkpoint: str, condition: dict) -> dict:
    ghost_aff = ghost_agent.set_affordances(candidates, context={"checkpoint": checkpoint})
    baseline_aff = baseline_agent.set_affordances(candidates, context={"checkpoint": checkpoint})
    ghost_packet = s3.ghost_policy(ghost_api, "guard", ghost_agent, ghost_aff, weights=condition["weights"])
    baseline_packet = s3.baseline_policy(baseline, baseline_aff)
    ghost_decision = ghost_agent.choose_action(ghost_packet["scores"], policy_id=ghost_packet["policy_id"])
    baseline_decision = baseline_agent.choose_action(baseline_packet["scores"], policy_id=baseline_packet["policy_id"])
    ghost_agent.resolve_action(ghost_decision["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
    baseline_agent.resolve_action(baseline_decision["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
    return {
        "checkpoint": checkpoint,
        "ghost": ghost_decision["candidate_id"],
        "baseline": baseline_decision["candidate_id"],
        "ghost_scores": ghost_packet["scores"],
        "baseline_scores": baseline_packet["scores"],
    }


def _finish(ghost_api, ghost_agent, baseline_agent, baseline, contradiction, checkpoints, condition) -> dict:
    s3._fillers(ghost_api, ghost_agent, baseline, 24, 24)
    recall = {
        "ghost": s3.ghost_has_observation(ghost_agent, "visitor", "badge", "red"),
        "baseline": baseline.has_observation("visitor", "badge", "red"),
    }
    if condition["recall_enabled"] and recall["ghost"]:
        s3.ghost_signal(ghost_api, -0.35)
    if recall["baseline"]:
        baseline.apply_signal("visitor", "threat", "hostile", "benign", -0.35)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._threat_candidates(), "delayed_relevance", condition))
    for signal in contradiction:
        s3.ghost_signal(ghost_api, signal)
        baseline.apply_signal("visitor", "threat", "hostile", "benign", signal)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._threat_candidates(), "contradiction_revised", condition))
    conflict = {"goal_progress": {"hold_gate": 0.75}, "goal_priority": {"protect_civilian": 1.0}}
    apply_host_effects_to_ghost(ghost_agent, conflict)
    baseline.apply_host_effects(conflict)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._conflict_candidates(), "conflict_shift", condition))
    s3._fillers(ghost_api, ghost_agent, baseline, 48, 16)
    delayed = {"goal_progress": {"hold_gate": 1.0}}
    apply_host_effects_to_ghost(ghost_agent, delayed)
    baseline.apply_host_effects(delayed)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._goal_candidates(), "goal_delayed_consequence", condition))
    s3._fillers(ghost_api, ghost_agent, baseline, 64, 16)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._goal_candidates(), "recurrence_final", condition))
    return recall


def _setup_trial():
    from ghost.api import GhostAPI

    capabilities = ["admit", "assist", "challenge", "hold", "retreat"]
    ghost_api = GhostAPI()
    ghost_agent = ghost_api.register_agent(
        "guard", role="guard", values=s3._decision_state()["values"], goals=s3._agent_goals(), capabilities=capabilities
    )
    baseline_api = GhostAPI()
    baseline_agent = baseline_api.register_agent("baseline_guard", role="guard", capabilities=capabilities)
    baseline = s3.FlatContinuityBaseline(
        s3._decision_state(), {"visitor": {"threat": {"benign": 0.5, "hostile": 0.5}}}
    )
    s3.seed_ghost_belief(ghost_api)
    return ghost_api, ghost_agent, baseline_api, baseline_agent, baseline


def _hostile_and_hidden(ghost_api, ghost_agent, baseline_agent, baseline, hostile, checkpoints, cfg):
    for signal in hostile:
        s3.ghost_signal(ghost_api, signal)
        baseline.apply_signal("visitor", "threat", "hostile", "benign", signal)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._threat_candidates(), "hostile_observed", cfg))
    before_g = s3._ghost_distribution(ghost_api, "guard", "visitor", "threat")
    before_b = baseline.belief_distribution("visitor", "threat")
    ghost_api.record_fact("visitor_safe_fact", "host_truth", "visitor", "actual_intent", "benign")
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._threat_candidates(), "hidden_fact_boundary", cfg))
    return {
        "ghost": before_g == s3._ghost_distribution(ghost_api, "guard", "visitor", "threat"),
        "baseline": before_b == baseline.belief_distribution("visitor", "threat"),
    }


def _restart_probe(ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, checkpoints, cfg):
    ghost_agent.observe("badge_seen", kind="direct", subject="visitor", source="host", features={"badge": "red"})
    baseline.observe("badge_seen", "visitor", {"badge": "red"})
    s3._fillers(ghost_api, ghost_agent, baseline, 0, 24)
    ghost_aff = ghost_agent.set_affordances(s3._threat_candidates(), context={"checkpoint": "pre_restart_probe"})
    baseline_aff = baseline_agent.set_affordances(s3._threat_candidates(), context={"checkpoint": "pre_restart_probe"})
    pre_g = s3.ghost_policy(ghost_api, "guard", ghost_agent, ghost_aff, weights=cfg["weights"])["scores"]
    pre_b = s3.baseline_policy(baseline, baseline_aff)["scores"]
    ghost_api, ghost_agent, baseline_api, baseline_agent, baseline = s3._restart(ghost_api, baseline_api, baseline)
    checkpoints.append(_choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._threat_candidates(), "restart_continuity", cfg))
    post_g = s3.ghost_policy(
        ghost_api, "guard", ghost_agent,
        ghost_agent.set_affordances(s3._threat_candidates(), context={"checkpoint": "post_restart_probe"}),
        weights=cfg["weights"],
    )["scores"]
    post_b = s3.baseline_policy(
        baseline, baseline_agent.set_affordances(s3._threat_candidates(), context={"checkpoint": "post_restart_probe"})
    )["scores"]
    return ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, pre_g == post_g and pre_b == post_b


def run_condition_trial(variant: dict, condition: dict) -> dict:
    cfg = _condition(condition)
    trial_id, hostile, contradiction = s3._validated_variant(variant)
    ghost_api, ghost_agent, baseline_api, baseline_agent, baseline = _setup_trial()
    checkpoints = [
        _choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._goal_candidates(), "goal_initial", cfg),
        _choose(ghost_api, ghost_agent, baseline_agent, baseline, s3._conflict_candidates(), "conflict_initial", cfg),
    ]
    hidden_ok = _hostile_and_hidden(ghost_api, ghost_agent, baseline_agent, baseline, hostile, checkpoints, cfg)
    ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, restart_ok = _restart_probe(
        ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, checkpoints, cfg
    )
    recall = _finish(ghost_api, ghost_agent, baseline_agent, baseline, contradiction, checkpoints, cfg)
    ghost_correct, baseline_correct = s3._annotate_checkpoints(checkpoints, _EXPECTED)
    return {
        "variant": trial_id, "checkpoint_count": len(checkpoints), "checkpoints": checkpoints,
        "ghost_correct": ghost_correct, "baseline_correct": baseline_correct,
        "divergence_count": sum(row["ghost"] != row["baseline"] for row in checkpoints),
        "hidden_information_boundary": hidden_ok, "restart_scores_match": restart_ok,
        "delayed_relevance_recall": recall,
    }


def run_condition(name: str, condition: dict, variants: list[dict] | None = None) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("condition name must be non-empty")
    selected = s3.canonical_variants() if variants is None else deepcopy(variants)
    if not isinstance(selected, list) or not selected:
        raise ValueError("condition run requires at least one variant")
    cfg = _condition(condition)
    trials = [run_condition_trial(variant, cfg) for variant in selected]
    total = sum(t["checkpoint_count"] for t in trials)
    ghost_correct = sum(t["ghost_correct"] for t in trials)
    baseline_correct = sum(t["baseline_correct"] for t in trials)
    return {
        "condition": name.strip(),
        "config": cfg,
        "trial_count": len(trials),
        "scored_checkpoints": total,
        "ghost_correct": ghost_correct,
        "baseline_correct": baseline_correct,
        "ghost_accuracy": ghost_correct / total,
        "baseline_accuracy": baseline_correct / total,
        "decision_divergence_count": sum(t["divergence_count"] for t in trials),
        "invariant_failures": s3._invariant_failures(trials),
        "trials": trials,
    }


def _decision_map(condition_result: dict) -> dict[tuple[str, str], str]:
    return {
        (trial["variant"], row["checkpoint"]): row["ghost"]
        for trial in condition_result["trials"]
        for row in trial["checkpoints"]
    }


def _failure_map(condition_result: dict) -> list[str]:
    return sorted(
        f"{trial['variant']}:{row['checkpoint']}"
        for trial in condition_result["trials"]
        for row in trial["checkpoints"]
        if not row["ghost_correct"]
    )


def _attribution(full: dict, result: dict) -> dict:
    full_map, current_map = _decision_map(full), _decision_map(result)
    changed = sorted(f"{variant}:{checkpoint}" for (variant, checkpoint), decision in current_map.items() if decision != full_map[(variant, checkpoint)])
    return {
        "score_delta_from_full": result["ghost_correct"] - full["ghost_correct"],
        "changed_decisions": changed,
        "changed_decision_count": len(changed),
        "incorrect_checkpoints": _failure_map(result),
        "causally_effective_on_matrix": bool(changed),
    }


def _stage3_anchor(stage3: dict, full: dict) -> dict:
    stage3_decisions = {
        (trial["variant"], row["checkpoint"]): row["ghost"]
        for trial in stage3["trials"]
        for row in trial["checkpoints"]
    }
    full_decisions = _decision_map(full)
    return {
        "score_match": (stage3["ghost_correct"], stage3["baseline_correct"]) == (full["ghost_correct"], full["baseline_correct"]),
        "decision_match": stage3_decisions == full_decisions,
        "invariant_match": stage3["invariant_failures"] == full["invariant_failures"],
    }


def _interpret(conditions: dict[str, dict]) -> dict:
    singles = ["no_values", "no_goals", "no_beliefs", "no_recall"]
    effective_singles = [name for name in singles if conditions[name]["attribution"]["causally_effective_on_matrix"]]
    ineffective_singles = [name for name in singles if name not in effective_singles]
    full_score = conditions["full"]["ghost_correct"]
    equivalent = [
        name
        for name, result in conditions.items()
        if result["ghost_correct"] == full_score and not result["attribution"]["changed_decisions"]
    ]
    interactions = []
    pairs = {
        "no_values_goals": ("no_values", "no_goals"),
        "no_values_beliefs": ("no_values", "no_beliefs"),
        "no_goals_beliefs": ("no_goals", "no_beliefs"),
    }
    for combined, parts in pairs.items():
        combined_effect = conditions[combined]["attribution"]["causally_effective_on_matrix"]
        parts_effect = any(conditions[part]["attribution"]["causally_effective_on_matrix"] for part in parts)
        if combined_effect and not parts_effect:
            interactions.append(combined)
    if effective_singles and interactions:
        category = "mixed_single_and_interaction_contribution"
    elif effective_singles:
        category = "single_channel_contribution_detected"
    elif interactions:
        category = "redundant_or_interacting_contribution_detected"
    elif len(equivalent) == len(conditions):
        category = "no_ablation_effect_detected"
    else:
        category = "combined_only_or_minimal_path_effect_detected"
    return {
        "category": category,
        "effective_single_ablations": effective_singles,
        "ineffective_single_ablations": ineffective_singles,
        "decision_equivalent_to_full": sorted(equivalent),
        "interaction_flags": sorted(interactions),
    }


def run_ablation_matrix() -> dict:
    stage3 = s3.run_matrix()
    configs = preregistered_conditions()
    ordered = list(_PRE_REGISTERED)
    results = {name: run_condition(name, configs[name]) for name in ordered}
    full = results["full"]
    anchor = _stage3_anchor(stage3, full)
    if not all(anchor.values()):
        raise RuntimeError("Stage-4 full condition does not exactly reproduce Stage-3 behavior")
    baseline_scores = {(result["baseline_correct"], result["scored_checkpoints"]) for result in results.values()}
    if baseline_scores != {(stage3["baseline_correct"], stage3["scored_checkpoints"])}:
        raise RuntimeError("baseline changed across Ghost ablation conditions")
    for result in results.values():
        result["attribution"] = _attribution(full, result)
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "stage3_anchor": anchor,
        "stage3_comparative_outcome": stage3["comparative_outcome"],
        "scored_checkpoints_per_condition": full["scored_checkpoints"],
        "conditions": results,
        "interpretation": _interpret(results),
        "claim_boundary": (
            "Stage 4 attributes decision-path contribution on the frozen Stage-3 matrix only. "
            "A disabled weight removes a channel from action scoring but does not delete its stored subsystem state. "
            "Results do not establish general Ghost superiority or production value."
        ),
    }
