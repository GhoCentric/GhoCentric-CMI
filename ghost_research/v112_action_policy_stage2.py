"""Stage-2 causal action-policy probe for Ghost v1.12 development.

This module is deliberately *research-only*.  It does not add a public Ghost API
and it is not packaged by the project's ``ghost.*`` setuptools include rule.

The experiment holds the scoring formula and Stage-1 action protocol constant
while changing only the representation supplying persistent state:

* ``ghost_policy_packet`` reads values/goals from a bound ``GhostAgent``.
* ``baseline_policy_packet`` reads the same information from a compact plain
  dictionary with no Ghost runtime semantics.

That design lets parity, causal mutation, persistence, and ablation be tested
without claiming that Ghost is behaviorally superior.  Stage 2 asks whether the
closed loop is wired causally and explainably.  Long-horizon superiority is a
later experiment.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from ghost.ids import normalize_id

POLICY_PACKET_VERSION = "1.0"
POLICY_FEATURE_KEY = "v112_stage2_policy"
GHOST_POLICY_ID = "ghost_state_v112_stage2"
BASELINE_POLICY_ID = "flat_state_v112_stage2"

_POLICY_FEATURE_KEYS = {"utility", "value_alignment", "goal_support"}
_WEIGHT_KEYS = {"utility", "values", "goals"}
_EFFECT_KEYS = {"values", "goal_progress", "goal_priority"}
_BASELINE_KEYS = {"values", "goals"}
_BASELINE_GOAL_KEYS = {"status", "priority", "progress"}
_ACTIVE_GOAL_STATUSES = frozenset({"active", "blocked"})
_GOAL_STATUSES = frozenset({"inactive", "active", "blocked", "satisfied", "abandoned"})

DEFAULT_POLICY_WEIGHTS = {"utility": 1.0, "values": 1.0, "goals": 1.0}


def _finite(value: Any, label: str) -> float:
    numeric_type = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not numeric_type:
        raise ValueError(f"{label} must be a finite number")
    out = float(value)
    if math.isnan(out) or math.isinf(out):
        raise ValueError(f"{label} must be a finite number")
    return out


def _unit(value: Any, label: str) -> float:
    out = _finite(value, label)
    if not 0.0 <= out <= 1.0:
        raise ValueError(f"{label} must be in [0, 1]")
    return out


def _signed_unit(value: Any, label: str) -> float:
    out = _finite(value, label)
    if not -1.0 <= out <= 1.0:
        raise ValueError(f"{label} must be in [-1, 1]")
    return out


def _normalized_channel_map(value: Any, label: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dict or None")
    out: dict[str, float] = {}
    for raw_key, raw_value in value.items():
        key = normalize_id(raw_key, f"{label} key")
        if key in out:
            raise ValueError(f"{label} contains duplicate normalized key: {key!r}")
        out[key] = _signed_unit(raw_value, f"{label}.{key}")
    return {key: out[key] for key in sorted(out)}


def _weights(value: dict | None) -> dict[str, float]:
    if value is None:
        return dict(DEFAULT_POLICY_WEIGHTS)
    if not isinstance(value, dict) or set(value) != _WEIGHT_KEYS:
        raise ValueError("policy weights must contain exactly utility, values, and goals")
    out = {key: _finite(value[key], f"policy weight {key}") for key in sorted(_WEIGHT_KEYS)}
    if any(item < 0.0 for item in out.values()):
        raise ValueError("policy weights must be non-negative")
    return out


def _goal_status(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    status = value.strip().lower()
    if status not in _GOAL_STATUSES:
        raise ValueError(f"unsupported {label}: {value!r}")
    return status


def _minimal_goal(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a dict")
    missing = _BASELINE_GOAL_KEYS - set(raw)
    if missing:
        raise ValueError(f"{label} is missing required keys: " + ", ".join(sorted(missing)))
    return {
        "status": _goal_status(raw["status"], f"{label}.status"),
        "priority": _unit(raw["priority"], f"{label}.priority"),
        "progress": _unit(raw["progress"], f"{label}.progress"),
    }


def _minimal_state(values: Any, goals: Any, label: str) -> dict[str, dict]:
    if not isinstance(values, dict):
        raise ValueError(f"{label}.values must be a dict")
    if not isinstance(goals, dict):
        raise ValueError(f"{label}.goals must be a dict")
    normalized_values: dict[str, float] = {}
    for raw_key, raw_value in values.items():
        key = normalize_id(raw_key, f"{label}.values key")
        if key in normalized_values:
            raise ValueError(f"{label}.values contains duplicate normalized key: {key!r}")
        normalized_values[key] = _unit(raw_value, f"{label}.values.{key}")
    normalized_goals: dict[str, dict] = {}
    for raw_key, raw_goal in goals.items():
        key = normalize_id(raw_key, f"{label}.goals key")
        if key in normalized_goals:
            raise ValueError(f"{label}.goals contains duplicate normalized key: {key!r}")
        normalized_goals[key] = _minimal_goal(raw_goal, f"{label}.goals.{key}")
    return {
        "values": {key: normalized_values[key] for key in sorted(normalized_values)},
        "goals": {key: normalized_goals[key] for key in sorted(normalized_goals)},
    }


def flatten_ghost_state(agent) -> dict[str, dict]:
    """Copy only the value/goal information intentionally visible to Stage 2."""
    return _minimal_state(agent.values(), agent.goals(), "ghost state")


def validate_baseline_state(state: Any) -> dict[str, dict]:
    if not isinstance(state, dict) or set(state) != _BASELINE_KEYS:
        raise ValueError("baseline state must contain exactly values and goals")
    return _minimal_state(state["values"], state["goals"], "baseline state")


def _goal_pressure(goal: dict[str, Any]) -> float:
    if goal["status"] not in _ACTIVE_GOAL_STATUSES:
        return 0.0
    return goal["priority"] * (1.0 - goal["progress"])


def _mean_component(mapping: dict[str, float], state: dict[str, float]) -> float:
    if not mapping:
        return 0.0
    return sum(state.get(key, 0.0) * weight for key, weight in mapping.items()) / len(mapping)


def _candidate_policy_features(candidate: Any, index: int) -> tuple[str, dict[str, Any]]:
    if not isinstance(candidate, dict):
        raise ValueError(f"affordance candidate[{index}] must be a dict")
    candidate_id = normalize_id(candidate.get("id"), f"affordance candidate[{index}] id")
    features = candidate.get("features")
    if not isinstance(features, dict):
        raise ValueError(f"affordance candidate[{index}] features must be a dict")
    policy = features.get(POLICY_FEATURE_KEY)
    if not isinstance(policy, dict) or set(policy) != _POLICY_FEATURE_KEYS:
        raise ValueError(
            f"affordance candidate[{index}] {POLICY_FEATURE_KEY} must contain exactly "
            "utility, value_alignment, and goal_support"
        )
    return candidate_id, {
        "utility": _signed_unit(policy["utility"], f"candidate {candidate_id} utility"),
        "value_alignment": _normalized_channel_map(
            policy["value_alignment"], f"candidate {candidate_id} value_alignment"
        ),
        "goal_support": _normalized_channel_map(
            policy["goal_support"], f"candidate {candidate_id} goal_support"
        ),
    }


def _affordance_policy_features(affordance_record: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(affordance_record, dict):
        raise ValueError("affordance record must be a dict")
    candidates = affordance_record.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("affordance record must contain a non-empty candidates list")
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_id, features = _candidate_policy_features(candidate, index)
        if candidate_id in seen:
            raise ValueError(f"affordance record contains duplicate candidate id: {candidate_id!r}")
        seen.add(candidate_id)
        out.append((candidate_id, features))
    return out


def _evaluate(state: dict[str, dict], affordance_record: dict, *, weights: dict | None) -> dict:
    config = _weights(weights)
    goal_pressures = {
        goal_id: _goal_pressure(goal)
        for goal_id, goal in state["goals"].items()
    }
    candidates: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for candidate_id, features in _affordance_policy_features(affordance_record):
        value_component = _mean_component(features["value_alignment"], state["values"])
        goal_component = _mean_component(features["goal_support"], goal_pressures)
        components = {
            "utility": config["utility"] * features["utility"],
            "values": config["values"] * value_component,
            "goals": config["goals"] * goal_component,
        }
        score = math.fsum(components.values())
        candidates[candidate_id] = {
            "raw": deepcopy(features),
            "components": components,
            "score": score,
        }
        scores[candidate_id] = score
    return {
        "packet_version": POLICY_PACKET_VERSION,
        "weights": config,
        "state": deepcopy(state),
        "goal_pressures": goal_pressures,
        "candidates": {key: candidates[key] for key in sorted(candidates)},
        "scores": {key: scores[key] for key in sorted(scores)},
    }


def ghost_policy_packet(agent, affordance_record: dict, *, weights: dict | None = None) -> dict:
    packet = _evaluate(flatten_ghost_state(agent), affordance_record, weights=weights)
    packet["policy_id"] = GHOST_POLICY_ID
    return packet


def baseline_policy_packet(state: dict, affordance_record: dict, *, weights: dict | None = None) -> dict:
    packet = _evaluate(validate_baseline_state(state), affordance_record, weights=weights)
    packet["policy_id"] = BASELINE_POLICY_ID
    return packet


def _effects(value: Any) -> dict[str, dict[str, float]]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("host effects must be a dict or None")
    unknown = set(value) - _EFFECT_KEYS
    if unknown:
        raise ValueError("host effects contain unsupported keys: " + ", ".join(sorted(unknown)))
    out: dict[str, dict[str, float]] = {"values": {}, "goal_progress": {}, "goal_priority": {}}
    for channel in out:
        raw = value.get(channel, {})
        if not isinstance(raw, dict):
            raise ValueError(f"host effects {channel} must be a dict")
        normalized: dict[str, float] = {}
        for raw_key, raw_value in raw.items():
            key = normalize_id(raw_key, f"host effects {channel} key")
            if key in normalized:
                raise ValueError(f"host effects {channel} contains duplicate normalized key: {key!r}")
            normalized[key] = _unit(raw_value, f"host effects {channel}.{key}")
        out[channel] = {key: normalized[key] for key in sorted(normalized)}
    return out


def apply_host_effects_to_ghost(agent, effects: dict | None) -> dict[str, dict]:
    """Apply explicit host-authoritative effects; infer nothing from action status."""
    normalized = _effects(effects)
    goals = agent.goals()
    for goal_id in set(normalized["goal_progress"]) | set(normalized["goal_priority"]):
        if goal_id not in goals:
            raise ValueError(f"host effect references unknown Ghost goal: {goal_id}")
    for value_id, weight in normalized["values"].items():
        agent.set_value(value_id, weight)
    for goal_id, progress in normalized["goal_progress"].items():
        agent.set_goal_progress(goal_id, progress)
    for goal_id, priority in normalized["goal_priority"].items():
        agent.set_goal_priority(goal_id, priority)
    return flatten_ghost_state(agent)


def apply_host_effects_to_baseline(state: dict, effects: dict | None) -> dict[str, dict]:
    normalized_state = validate_baseline_state(state)
    normalized = _effects(effects)
    for goal_id in set(normalized["goal_progress"]) | set(normalized["goal_priority"]):
        if goal_id not in normalized_state["goals"]:
            raise ValueError(f"host effect references unknown baseline goal: {goal_id}")
    normalized_state["values"].update(normalized["values"])
    for goal_id, progress in normalized["goal_progress"].items():
        normalized_state["goals"][goal_id]["progress"] = progress
    for goal_id, priority in normalized["goal_priority"].items():
        normalized_state["goals"][goal_id]["priority"] = priority
    return validate_baseline_state(normalized_state)


def max_score_delta(left: dict, right: dict) -> float:
    left_scores = left.get("scores") if isinstance(left, dict) else None
    right_scores = right.get("scores") if isinstance(right, dict) else None
    if not isinstance(left_scores, dict) or not isinstance(right_scores, dict):
        raise ValueError("policy packets must contain score dictionaries")
    if set(left_scores) != set(right_scores):
        raise ValueError("policy packets score different candidate sets")
    if not left_scores:
        return 0.0
    return max(abs(_finite(left_scores[key], f"left score {key}") - _finite(right_scores[key], f"right score {key}")) for key in left_scores)
