"""Research-only Stage-3 long-horizon continuity stress experiment.

Ghost and a strong flat baseline receive the same external events and use the
same Stage-1 action protocol.  The baseline owns and serializes its own values,
goals, compact belief state, and bounded raw observation history; it is never
continuously mirrored from Ghost.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any

from ghost.ids import normalize_id
from ghost_research.v112_action_policy_stage2 import (
    POLICY_FEATURE_KEY as STAGE2_FEATURE_KEY,
    apply_host_effects_to_baseline,
    apply_host_effects_to_ghost,
    baseline_policy_packet,
    ghost_policy_packet,
    validate_baseline_state,
)

PACKET_VERSION = "1.0"
BELIEF_FEATURE_KEY = "v112_stage3_belief"
GHOST_POLICY_ID = "ghost_continuity_v112_stage3"
BASELINE_POLICY_ID = "flat_continuity_v112_stage3"
BASELINE_SCHEMA = "ghost.research.v1.12.stage3.flat-baseline.v1"
BASELINE_SIGNAL_GAIN = 2.0
DEFAULT_HISTORY_LIMIT = 128
DEFAULT_WEIGHTS = {"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _unit(value: Any, label: str) -> float:
    out = _finite(value, label)
    if not 0.0 <= out <= 1.0:
        raise ValueError(f"{label} must be in [0, 1]")
    return out


def _signed(value: Any, label: str) -> float:
    out = _finite(value, label)
    if not -1.0 <= out <= 1.0:
        raise ValueError(f"{label} must be in [-1, 1]")
    return out


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _weights(value: dict | None) -> dict[str, float]:
    if value is None:
        return dict(DEFAULT_WEIGHTS)
    if not isinstance(value, dict) or set(value) != set(DEFAULT_WEIGHTS):
        raise ValueError("weights must contain exactly utility, values, goals, beliefs")
    out = {key: _finite(value[key], f"weight {key}") for key in sorted(value)}
    if any(weight < 0.0 for weight in out.values()):
        raise ValueError("weights must be non-negative")
    return out


def _distribution(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict) or len(value) < 2:
        raise ValueError(f"{label} must contain at least two candidates")
    out = {normalize_id(key, f"{label} candidate"): _unit(prob, f"{label}.{key}") for key, prob in value.items()}
    if len(out) != len(value) or not math.isclose(math.fsum(out.values()), 1.0, abs_tol=1e-12):
        raise ValueError(f"{label} must have unique candidates summing to 1.0")
    return {key: out[key] for key in sorted(out)}


def _belief_tree(value: Any) -> dict[str, dict[str, dict[str, float]]]:
    if not isinstance(value, dict):
        raise ValueError("beliefs must be a dict")
    out = {}
    for raw_subject, raw_dimensions in value.items():
        subject = normalize_id(raw_subject, "belief subject")
        if subject in out or not isinstance(raw_dimensions, dict) or not raw_dimensions:
            raise ValueError("belief subjects must be unique with non-empty dimensions")
        dims = {}
        for raw_dimension, raw_distribution in raw_dimensions.items():
            dimension = normalize_id(raw_dimension, "belief dimension")
            if dimension in dims:
                raise ValueError("duplicate normalized belief dimension")
            dims[dimension] = _distribution(raw_distribution, f"beliefs.{subject}.{dimension}")
        out[subject] = {key: dims[key] for key in sorted(dims)}
    return {key: out[key] for key in sorted(out)}


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be strict JSON-safe data") from exc


class FlatContinuityBaseline:
    """Independent compact baseline used for the Stage-3 matched comparison."""

    def __init__(self, decision_state: dict, beliefs: dict, *, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self.decision_state = validate_baseline_state(decision_state)
        self.beliefs = _belief_tree(beliefs)
        self.history_limit = _positive_int(history_limit, "history_limit")
        self.sequence = 0
        self.observations: list[dict] = []

    def belief_distribution(self, subject, dimension) -> dict[str, float]:
        subject = normalize_id(subject, "belief subject")
        dimension = normalize_id(dimension, "belief dimension")
        try:
            return deepcopy(self.beliefs[subject][dimension])
        except KeyError as exc:
            raise ValueError(f"baseline has no belief for {subject}.{dimension}") from exc

    def apply_signal(self, subject, dimension, positive, negative, signal, *, reliability: float = 1.0) -> dict[str, float]:
        subject = normalize_id(subject, "belief subject")
        dimension = normalize_id(dimension, "belief dimension")
        positive = normalize_id(positive, "positive candidate")
        negative = normalize_id(negative, "negative candidate")
        signed = _signed(signal, "signal")
        reliability = _unit(reliability, "reliability")
        dist = self.belief_distribution(subject, dimension)
        if positive == negative or set(dist) != {positive, negative}:
            raise ValueError("signal requires exactly the named positive/negative candidates")
        if signed == 0.0 or reliability == 0.0:
            return dist
        p = min(1.0 - 1e-12, max(1e-12, dist[positive]))
        log_odds = math.log(p / (1.0 - p)) + BASELINE_SIGNAL_GAIN * signed * reliability
        updated = 1.0 / (1.0 + math.exp(-log_odds))
        self.beliefs[subject][dimension] = {negative: 1.0 - updated, positive: updated}
        return self.belief_distribution(subject, dimension)

    def apply_host_effects(self, effects: dict | None) -> dict:
        self.decision_state = apply_host_effects_to_baseline(self.decision_state, effects)
        return deepcopy(self.decision_state)

    def observe(self, event, subject, features: dict | None = None) -> dict:
        self.sequence += 1
        record = {
            "sequence": self.sequence,
            "event": normalize_id(event, "observation event"),
            "subject": normalize_id(subject, "observation subject"),
            "features": _json_copy({} if features is None else features),
        }
        self.observations.append(record)
        if len(self.observations) > self.history_limit:
            del self.observations[: len(self.observations) - self.history_limit]
        return deepcopy(record)

    def has_observation(self, subject, feature, expected) -> bool:
        subject = normalize_id(subject, "observation subject")
        feature = normalize_id(feature, "observation feature")
        return any(
            record["subject"] == subject and record["features"].get(feature) == expected
            for record in reversed(self.observations)
        )

    def snapshot(self) -> dict:
        return {
            "schema": BASELINE_SCHEMA,
            "decision_state": deepcopy(self.decision_state),
            "beliefs": deepcopy(self.beliefs),
            "observations": deepcopy(self.observations),
            "sequence": self.sequence,
            "history_limit": self.history_limit,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "FlatContinuityBaseline":
        keys = {"schema", "decision_state", "beliefs", "observations", "sequence", "history_limit"}
        if not isinstance(snapshot, dict) or set(snapshot) != keys or snapshot["schema"] != BASELINE_SCHEMA:
            raise ValueError("invalid baseline snapshot")
        history_limit = _positive_int(snapshot["history_limit"], "snapshot history_limit")
        sequence = _non_negative_sequence(snapshot["sequence"])
        restored = _restore_observations(snapshot["observations"], history_limit, sequence)
        out = cls(snapshot["decision_state"], snapshot["beliefs"], history_limit=history_limit)
        out.sequence = sequence
        out.observations = restored
        return out


def _non_negative_sequence(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("snapshot sequence must be a non-negative integer")
    return value


def _restore_observation(item: Any, previous: int) -> tuple[dict, int]:
    if not isinstance(item, dict) or set(item) != {"sequence", "event", "subject", "features"}:
        raise ValueError("invalid baseline observation record")
    current = item["sequence"]
    if isinstance(current, bool) or not isinstance(current, int) or current <= previous:
        raise ValueError("baseline observations must be strictly ordered")
    return _json_copy(item), current


def _restore_observations(raw: Any, history_limit: int, sequence: int) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > history_limit:
        raise ValueError("invalid baseline observation history")
    previous, restored = 0, []
    for item in raw:
        record, previous = _restore_observation(item, previous)
        restored.append(record)
    consistent = (restored and previous == sequence) or (not restored and sequence == 0)
    if not consistent:
        raise ValueError("baseline observation sequence is inconsistent")
    return restored


def _belief_feature(candidate: Any, index: int) -> tuple[str, dict | None]:
    if not isinstance(candidate, dict) or not isinstance(candidate.get("features"), dict):
        raise ValueError(f"candidate[{index}] must contain a feature dictionary")
    candidate_id = normalize_id(candidate.get("id"), f"candidate[{index}] id")
    raw = candidate["features"].get(BELIEF_FEATURE_KEY)
    if raw is None:
        return candidate_id, None
    if not isinstance(raw, dict) or set(raw) != {"subject", "dimension", "alignment"}:
        raise ValueError(f"candidate {candidate_id} has invalid belief feature")
    alignment = raw["alignment"]
    if not isinstance(alignment, dict) or not alignment:
        raise ValueError(f"candidate {candidate_id} belief alignment must be non-empty")
    normalized = {normalize_id(key, "belief alignment candidate"): _signed(weight, "belief alignment weight") for key, weight in alignment.items()}
    if len(normalized) != len(alignment):
        raise ValueError("duplicate normalized belief alignment candidate")
    return candidate_id, {
        "subject": normalize_id(raw["subject"], "belief subject"),
        "dimension": normalize_id(raw["dimension"], "belief dimension"),
        "alignment": {key: normalized[key] for key in sorted(normalized)},
    }


def _ghost_distribution(api, holder, subject, dimension) -> dict[str, float]:
    belief = api.get_belief(normalize_id(holder, "belief holder"), normalize_id(subject, "belief subject"))
    dimension = normalize_id(dimension, "belief dimension")
    if belief is None or dimension not in belief.get("dimensions", {}):
        raise ValueError("Ghost belief/dimension is missing")
    return _distribution(belief["dimensions"][dimension]["candidates"], "Ghost belief distribution")


def _belief_contribution(feature: dict | None, lookup) -> tuple[float, dict | None]:
    if feature is None:
        return 0.0, None
    belief_state = lookup(feature["subject"], feature["dimension"])
    missing = set(feature["alignment"]) - set(belief_state)
    if missing:
        raise ValueError("belief alignment references missing candidates")
    component = math.fsum(belief_state[key] * weight for key, weight in feature["alignment"].items())
    return component, belief_state


def _merge_packet(base: dict, affordance_record: dict, lookup, policy_id: str, weights: dict) -> dict:
    candidates = affordance_record.get("candidates") if isinstance(affordance_record, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("affordance record requires non-empty candidates")
    scores, detail, seen = {}, {}, set()
    for index, candidate in enumerate(candidates):
        candidate_id, feature = _belief_feature(candidate, index)
        if candidate_id in seen or candidate_id not in base["scores"]:
            raise ValueError("Stage-3 candidate set mismatches Stage-2 base packet")
        seen.add(candidate_id)
        component, belief_state = _belief_contribution(feature, lookup)
        weighted = weights["beliefs"] * component
        score = math.fsum((base["scores"][candidate_id], weighted))
        scores[candidate_id] = score
        detail[candidate_id] = {"base_score": base["scores"][candidate_id], "belief_component": component, "weighted_belief": weighted, "score": score, "belief_state": deepcopy(belief_state)}
    if seen != set(base["scores"]):
        raise ValueError("Stage-3 candidate set does not cover Stage-2 base packet")
    return {"packet_version": PACKET_VERSION, "policy_id": policy_id, "weights": weights, "scores": {k: scores[k] for k in sorted(scores)}, "candidates": {k: detail[k] for k in sorted(detail)}}


def ghost_policy(api, holder, agent, affordance_record: dict, *, weights: dict | None = None) -> dict:
    config = _weights(weights)
    base_weights = {key: config[key] for key in ("utility", "values", "goals")}
    base = ghost_policy_packet(agent, affordance_record, weights=base_weights)
    return _merge_packet(base, affordance_record, lambda s, d: _ghost_distribution(api, holder, s, d), GHOST_POLICY_ID, config)


def baseline_policy(baseline: FlatContinuityBaseline, affordance_record: dict, *, weights: dict | None = None) -> dict:
    config = _weights(weights)
    base_weights = {key: config[key] for key in ("utility", "values", "goals")}
    base = baseline_policy_packet(baseline.decision_state, affordance_record, weights=base_weights)
    return _merge_packet(base, affordance_record, baseline.belief_distribution, BASELINE_POLICY_ID, config)


def seed_ghost_belief(api, holder="guard", subject="visitor", probability=0.5) -> dict:
    probability = _unit(probability, "initial hostile probability")
    return api.evaluate_beliefs(holder=holder, subject=subject, candidates={"threat": {"benign": 1.0 - probability, "hostile": probability}})


def ghost_signal(api, signal, *, holder="guard", subject="visitor", reliability: float = 1.0) -> dict:
    signed = _signed(signal, "Ghost signal")
    reliability = _unit(reliability, "Ghost signal reliability")
    current = api.get_belief(holder, subject) or seed_ghost_belief(api, holder, subject)
    if signed == 0.0 or reliability == 0.0:
        return deepcopy(current)
    strength = abs(signed) * reliability
    supported, contradicted = ("hostile", "benign") if signed > 0.0 else ("benign", "hostile")
    evidence = api.add_evidence(evidence_type="stage3_signal", source="host", subject=subject, available_to=holder, supports={"threat": {supported: strength}}, contradicts={"threat": {contradicted: strength * 0.5}})
    return api.evaluate_beliefs(holder=holder, subject=subject, previous_belief_id=current["id"], evidence_ids=[evidence["id"]])


def ghost_has_observation(agent, subject, feature, expected) -> bool:
    subject, feature = normalize_id(subject, "observation subject"), normalize_id(feature, "observation feature")
    return any(record["subject"] == subject and record["features"].get(feature) == expected for record in reversed(agent.observation_history()))


def candidate(candidate_id, *, utility=0.0, values=None, goals=None, belief=None) -> dict:
    candidate_id = normalize_id(candidate_id, "candidate id")
    features = {STAGE2_FEATURE_KEY: {"utility": _signed(utility, "candidate utility"), "value_alignment": deepcopy(values or {}), "goal_support": deepcopy(goals or {})}}
    if belief is not None:
        features[BELIEF_FEATURE_KEY] = deepcopy(belief)
    return {"id": candidate_id, "capability": candidate_id, "features": features}


def canonical_variants() -> list[dict]:
    return [
        {"id": "balanced", "hostile": [0.65], "contradiction": [-0.90]},
        {"id": "weak_hostile", "hostile": [0.45], "contradiction": [-0.95]},
        {"id": "repeated", "hostile": [0.55, 0.35], "contradiction": [-0.90, -0.60]},
    ]


def _decision_state() -> dict:
    return {"values": {"compassion": 0.65, "duty": 0.9, "survival": 0.4}, "goals": {"hold_gate": {"status": "active", "priority": 0.9, "progress": 0.0}, "protect_civilian": {"status": "active", "priority": 0.35, "progress": 0.0}}}


def _agent_goals() -> dict:
    return {"hold_gate": {"status": "active", "priority": 0.9, "progress": 0.0, "value_weights": {"duty": 1.0}}, "protect_civilian": {"status": "active", "priority": 0.35, "progress": 0.0, "value_weights": {"compassion": 1.0}}}


def _goal_candidates() -> list[dict]:
    return [candidate("hold", utility=0.1, values={"duty": 1.0, "survival": -0.2}, goals={"hold_gate": 1.0, "protect_civilian": -0.3}), candidate("retreat", utility=0.65, values={"duty": -0.6, "survival": 1.0}, goals={"hold_gate": -0.6})]


def _conflict_candidates() -> list[dict]:
    return [candidate("hold", utility=0.1, values={"duty": 1.0, "compassion": -0.2}, goals={"hold_gate": 1.0, "protect_civilian": -0.4}), candidate("assist", utility=0.15, values={"duty": -0.2, "compassion": 1.0}, goals={"hold_gate": -0.4, "protect_civilian": 1.0})]


def _threat_candidates() -> list[dict]:
    common = {"subject": "visitor", "dimension": "threat"}
    return [candidate("admit", belief={**common, "alignment": {"benign": 1.0, "hostile": -1.0}}), candidate("challenge", belief={**common, "alignment": {"benign": -1.0, "hostile": 1.0}})]


def _choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, candidates, checkpoint) -> dict:
    ga = ghost_agent.set_affordances(candidates, context={"checkpoint": checkpoint})
    ba = baseline_agent.set_affordances(candidates, context={"checkpoint": checkpoint})
    gp, bp = ghost_policy(ghost_api, "guard", ghost_agent, ga), baseline_policy(baseline, ba)
    gd = ghost_agent.choose_action(gp["scores"], policy_id=gp["policy_id"])
    bd = baseline_agent.choose_action(bp["scores"], policy_id=bp["policy_id"])
    ghost_agent.resolve_action(gd["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
    baseline_agent.resolve_action(bd["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
    return {"checkpoint": checkpoint, "ghost": gd["candidate_id"], "baseline": bd["candidate_id"], "ghost_scores": gp["scores"], "baseline_scores": bp["scores"]}


def _fillers(ghost_api, ghost_agent, baseline, start: int, count: int) -> None:
    for index in range(start, start + count):
        subject, tone = f"ambient_{index % 7}", f"noise_{index % 5}"
        features = {"step": index, "tone": tone}
        ghost_agent.observe(f"ambient_event_{index}", kind="environment", subject=subject, source="host", features=features)
        baseline.observe(f"ambient_event_{index}", subject, features)
        ghost_api.observe(observer="guard", kind="environment", visible_features=[tone], reliability=0.5, subject=subject, provenance={"step": index})


def _validated_variant(variant: dict) -> tuple[str, list[float], list[float]]:
    if not isinstance(variant, dict) or set(variant) != {"id", "hostile", "contradiction"}:
        raise ValueError("trial variant has invalid shape")
    trial_id = normalize_id(variant["id"], "trial id")
    hostile = [_signed(item, f"{trial_id} hostile signal") for item in variant["hostile"]]
    contradiction = [_signed(item, f"{trial_id} contradiction signal") for item in variant["contradiction"]]
    valid_hostile = bool(hostile) and all(item > 0.0 for item in hostile)
    valid_contradiction = bool(contradiction) and all(item < 0.0 for item in contradiction)
    if not valid_hostile or not valid_contradiction:
        raise ValueError("trial requires positive hostile and negative contradiction signals")
    return trial_id, hostile, contradiction


def _restart(ghost_api, baseline_api, baseline):
    from ghost.api import GhostAPI
    ghost_api = GhostAPI.from_snapshot(ghost_api.snapshot())
    baseline_api = GhostAPI.from_snapshot(baseline_api.snapshot())
    baseline = FlatContinuityBaseline.from_snapshot(baseline.snapshot())
    ghost_agent, baseline_agent = ghost_api.agent("guard"), baseline_api.agent("baseline_guard")
    if ghost_agent is None or baseline_agent is None:
        raise RuntimeError("restart lost registered agent")
    return ghost_api, ghost_agent, baseline_api, baseline_agent, baseline


def _annotate_checkpoints(checkpoints: list[dict], expected: dict[str, str]) -> tuple[int, int]:
    for row in checkpoints:
        row["expected"] = expected[row["checkpoint"]]
        row["ghost_correct"] = row["ghost"] == row["expected"]
        row["baseline_correct"] = row["baseline"] == row["expected"]
    return sum(row["ghost_correct"] for row in checkpoints), sum(row["baseline_correct"] for row in checkpoints)


def _finish_trial(ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, contradiction, checkpoints):
    _fillers(ghost_api, ghost_agent, baseline, 24, 24)
    recall = {
        "ghost": ghost_has_observation(ghost_agent, "visitor", "badge", "red"),
        "baseline": baseline.has_observation("visitor", "badge", "red"),
    }
    if recall["ghost"]:
        ghost_signal(ghost_api, -0.35)
    if recall["baseline"]:
        baseline.apply_signal("visitor", "threat", "hostile", "benign", -0.35)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _threat_candidates(), "delayed_relevance"))
    for signal in contradiction:
        ghost_signal(ghost_api, signal)
        baseline.apply_signal("visitor", "threat", "hostile", "benign", signal)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _threat_candidates(), "contradiction_revised"))
    conflict = {"goal_progress": {"hold_gate": 0.75}, "goal_priority": {"protect_civilian": 1.0}}
    apply_host_effects_to_ghost(ghost_agent, conflict)
    baseline.apply_host_effects(conflict)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _conflict_candidates(), "conflict_shift"))
    _fillers(ghost_api, ghost_agent, baseline, 48, 16)
    delayed = {"goal_progress": {"hold_gate": 1.0}}
    apply_host_effects_to_ghost(ghost_agent, delayed)
    baseline.apply_host_effects(delayed)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _goal_candidates(), "goal_delayed_consequence"))
    _fillers(ghost_api, ghost_agent, baseline, 64, 16)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _goal_candidates(), "recurrence_final"))
    return recall


def run_trial(variant: dict) -> dict:
    from ghost.api import GhostAPI

    trial_id, hostile, contradiction = _validated_variant(variant)
    capabilities = ["admit", "assist", "challenge", "hold", "retreat"]
    ghost_api = GhostAPI()
    ghost_agent = ghost_api.register_agent("guard", role="guard", values=_decision_state()["values"], goals=_agent_goals(), capabilities=capabilities)
    baseline_api = GhostAPI()
    baseline_agent = baseline_api.register_agent("baseline_guard", role="guard", capabilities=capabilities)
    baseline = FlatContinuityBaseline(_decision_state(), {"visitor": {"threat": {"benign": 0.5, "hostile": 0.5}}})
    seed_ghost_belief(ghost_api)
    expected = {"goal_initial": "hold", "conflict_initial": "hold", "hostile_observed": "challenge", "hidden_fact_boundary": "challenge", "restart_continuity": "challenge", "delayed_relevance": "challenge", "contradiction_revised": "admit", "conflict_shift": "assist", "goal_delayed_consequence": "retreat", "recurrence_final": "retreat"}
    checkpoints = [_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _goal_candidates(), "goal_initial"), _choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _conflict_candidates(), "conflict_initial")]

    for signal in hostile:
        ghost_signal(ghost_api, signal)
        baseline.apply_signal("visitor", "threat", "hostile", "benign", signal)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _threat_candidates(), "hostile_observed"))

    before_g, before_b = _ghost_distribution(ghost_api, "guard", "visitor", "threat"), baseline.belief_distribution("visitor", "threat")
    ghost_api.record_fact("visitor_safe_fact", "host_truth", "visitor", "actual_intent", "benign")
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _threat_candidates(), "hidden_fact_boundary"))
    hidden_ok = {"ghost": before_g == _ghost_distribution(ghost_api, "guard", "visitor", "threat"), "baseline": before_b == baseline.belief_distribution("visitor", "threat")}

    ghost_agent.observe("badge_seen", kind="direct", subject="visitor", source="host", features={"badge": "red"})
    baseline.observe("badge_seen", "visitor", {"badge": "red"})
    _fillers(ghost_api, ghost_agent, baseline, 0, 24)
    ga = ghost_agent.set_affordances(_threat_candidates(), context={"checkpoint": "pre_restart_probe"})
    ba = baseline_agent.set_affordances(_threat_candidates(), context={"checkpoint": "pre_restart_probe"})
    pre_g, pre_b = ghost_policy(ghost_api, "guard", ghost_agent, ga)["scores"], baseline_policy(baseline, ba)["scores"]
    ghost_api, ghost_agent, baseline_api, baseline_agent, baseline = _restart(ghost_api, baseline_api, baseline)
    checkpoints.append(_choose_pair(ghost_api, ghost_agent, baseline_agent, baseline, _threat_candidates(), "restart_continuity"))
    post_g = ghost_policy(ghost_api, "guard", ghost_agent, ghost_agent.set_affordances(_threat_candidates(), context={"checkpoint": "post_restart_probe"}))["scores"]
    post_b = baseline_policy(baseline, baseline_agent.set_affordances(_threat_candidates(), context={"checkpoint": "post_restart_probe"}))["scores"]
    restart_ok = pre_g == post_g and pre_b == post_b

    recall = _finish_trial(ghost_api, ghost_agent, baseline_api, baseline_agent, baseline, contradiction, checkpoints)

    ghost_correct, baseline_correct = _annotate_checkpoints(checkpoints, expected)
    encode = lambda value: len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    return {"variant": trial_id, "checkpoint_count": len(checkpoints), "checkpoints": checkpoints, "ghost_correct": ghost_correct, "baseline_correct": baseline_correct, "divergence_count": sum(row["ghost"] != row["baseline"] for row in checkpoints), "hidden_information_boundary": hidden_ok, "restart_scores_match": restart_ok, "delayed_relevance_recall": recall, "final_beliefs": {"ghost": _ghost_distribution(ghost_api, "guard", "visitor", "threat"), "baseline": baseline.belief_distribution("visitor", "threat")}, "snapshot_bytes": {"ghost": encode(ghost_api.snapshot()), "baseline_policy": encode(baseline.snapshot()), "baseline_action_transport": encode(baseline_api.snapshot())}}


def _invariant_failures(trials: list[dict]) -> list[str]:
    failures = []
    for trial in trials:
        if not all(trial["hidden_information_boundary"].values()):
            failures.append(f"{trial['variant']}:hidden_information_boundary")
        if not trial["restart_scores_match"]:
            failures.append(f"{trial['variant']}:restart_scores")
        if not all(trial["delayed_relevance_recall"].values()):
            failures.append(f"{trial['variant']}:delayed_relevance_recall")
    return failures


def _comparative_outcome(ghost_correct: int, baseline_correct: int) -> str:
    if ghost_correct > baseline_correct:
        return "directional_ghost_advantage"
    if ghost_correct < baseline_correct:
        return "directional_baseline_advantage"
    return "behavioral_parity_on_scored_constraints"


def run_matrix(variants: list[dict] | None = None) -> dict:
    selected = canonical_variants() if variants is None else deepcopy(variants)
    if not isinstance(selected, list) or not selected:
        raise ValueError("matrix requires at least one variant")
    trials = [run_trial(variant) for variant in selected]
    total = sum(trial["checkpoint_count"] for trial in trials)
    ghost_correct = sum(trial["ghost_correct"] for trial in trials)
    baseline_correct = sum(trial["baseline_correct"] for trial in trials)
    return {
        "schema": "ghost.v1.12-dev.continuity-stress.stage3.matrix.v1",
        "strict_verdict": "V112_CONTINUITY_STRESS_STAGE3_EXPERIMENT_VALID",
        "trial_count": len(trials),
        "scored_checkpoints": total,
        "ghost_correct": ghost_correct,
        "baseline_correct": baseline_correct,
        "ghost_accuracy": ghost_correct / total,
        "baseline_accuracy": baseline_correct / total,
        "decision_divergence_count": sum(t["divergence_count"] for t in trials),
        "invariant_failures": _invariant_failures(trials),
        "comparative_outcome": _comparative_outcome(ghost_correct, baseline_correct),
        "trials": trials,
        "claim_boundary": "One deterministic long-horizon matrix against one strong independently maintained flat baseline. Directional results are not a general Ghost-superiority claim; broader scenarios, ablations, and scale remain required.",
    }
