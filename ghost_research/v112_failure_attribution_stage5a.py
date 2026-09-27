"""Research-only Stage-5A attribution of the six Lean-Ghost divergences.

Stage 5 showed exactly six Lean-vs-Full decision divergences: one values
checkpoint and one delayed-recall checkpoint at each scale level.  Stage 5A
freezes that matrix, replays those exact checkpoints, and performs orthogonal
counterfactual restoration: restore values only, restore recall only, or both.
No production ``ghost.*`` code is modified.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research import v112_lean_adjudication_stage5 as s5
from ghost_research.v112_action_policy_stage2 import apply_host_effects_to_ghost

SCHEMA = "ghost.v1.12-dev.failure-attribution.stage5a.v1"
VERDICT = "V112_FAILURE_ATTRIBUTION_STAGE5A_EXPERIMENT_VALID"

_CONDITIONS = {
    "full": ({"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}, True),
    "lean": ({"utility": 1.0, "values": 0.0, "goals": 1.0, "beliefs": 1.0}, False),
    "restore_values": ({"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}, False),
    "restore_recall": ({"utility": 1.0, "values": 0.0, "goals": 1.0, "beliefs": 1.0}, True),
}
_EXPECTED_FAILURES = {
    (level, checkpoint): requirement
    for level in ("light", "medium", "heavy")
    for checkpoint, requirement in (("value_preference", "values"), ("delayed_badge", "recall"))
}


def _condition(name: str) -> dict:
    if not isinstance(name, str) or name not in _CONDITIONS:
        raise ValueError(f"unknown Stage-5A condition: {name!r}")
    weights, recall = _CONDITIONS[name]
    return {"name": name, "weights": s3._weights(deepcopy(weights)), "recall_enabled": recall}


def _row_map(level_result: dict) -> dict[str, dict]:
    if not isinstance(level_result, dict) or not isinstance(level_result.get("rows"), list):
        raise ValueError("level result must contain rows")
    rows = level_result["rows"]
    mapping = {row["checkpoint"]: row for row in rows}
    if len(mapping) != len(rows):
        raise ValueError("level result contains duplicate checkpoints")
    return mapping


def _decision_margin(scores: dict[str, float], chosen: str, alternate: str) -> float:
    if set(scores) != {chosen, alternate}:
        raise ValueError("score map does not match the two compared candidates")
    return scores[chosen] - scores[alternate]


class _CounterfactualGhost(s5._Contender):
    def __init__(self, subjects: list[str], condition: str) -> None:
        super().__init__("full", subjects)
        cfg = _condition(condition)
        self.condition_name = cfg["name"]
        self.weights = cfg["weights"]
        self.recall_enabled = cfg["recall_enabled"]

    def choose(self, candidates: list[dict], checkpoint: str) -> dict:
        affordance = self.agent.set_affordances(candidates, context={"checkpoint": checkpoint, "mode": self.condition_name})
        packet = s3.ghost_policy(self.api, "guard", self.agent, affordance, weights=self.weights)
        decision = self.agent.choose_action(packet["scores"], policy_id=f"stage5a_{self.condition_name}")
        self.agent.resolve_action(decision["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
        return {"decision": decision["candidate_id"], "scores": packet["scores"]}

    def delayed_badge_effect(self, subject: str) -> bool:
        remembered = self.has_badge(subject)
        if remembered and self.recall_enabled:
            self.signal(subject, -1.0)
        return remembered


def _run_level_condition(level: dict, condition: str) -> dict:
    cfg = s5._level(level)
    subjects = s5._subject_ids(cfg["subjects"])
    contender = _CounterfactualGhost(subjects, condition)
    rows = [
        s5._score_row(contender, s3._goal_candidates(), "goal_initial", "hold", "goals"),
        s5._score_row(contender, s5._value_candidates(), "value_preference", "protect", "values"),
    ]
    for index, subject in enumerate(subjects[:-1]):
        contender.signal(subject, cfg["hostile"])
        rows.append(s5._score_row(contender, s5._threat_candidates(subject), f"subject_{index}_hostile", "challenge", "beliefs"))
        contender.hidden_fact(subject, cfg["id"])
        rows.append(s5._score_row(contender, s5._threat_candidates(subject), f"subject_{index}_hidden", "challenge", "information_boundary"))
        contender.signal(subject, cfg["contradiction"])
        rows.append(s5._score_row(contender, s5._threat_candidates(subject), f"subject_{index}_revised", "admit", "belief_revision"))
    memory_subject = subjects[-1]
    contender.signal(memory_subject, cfg["hostile"])
    rows.append(s5._score_row(contender, s5._threat_candidates(memory_subject), "memory_hostile", "challenge", "beliefs"))
    contender.observe_badge(memory_subject)
    s5._run_fillers(contender, cfg["fillers"], cfg["restarts"])
    before = contender.distribution(memory_subject)
    remembered = contender.delayed_badge_effect(memory_subject)
    after = contender.distribution(memory_subject)
    rows.append(s5._score_row(contender, s5._threat_candidates(memory_subject), "delayed_badge", "admit", "recall"))
    contender.signal(memory_subject, cfg["contradiction"])
    rows.append(s5._score_row(contender, s5._threat_candidates(memory_subject), "memory_revised", "admit", "belief_revision"))
    contender.apply_effects({"goal_progress": {"hold_gate": 0.75}, "goal_priority": {"protect_civilian": 1.0}})
    rows.append(s5._score_row(contender, s3._conflict_candidates(), "conflict_shift", "assist", "goals"))
    contender.apply_effects({"goal_progress": {"hold_gate": 1.0}})
    rows.append(s5._score_row(contender, s3._goal_candidates(), "goal_complete", "retreat", "goals"))
    s5._run_fillers(contender, max(1, cfg["fillers"] // 4), min(cfg["restarts"], max(1, cfg["fillers"] // 4)))
    rows.append(s5._score_row(contender, s3._goal_candidates(), "recurrence", "retreat", "goals"))
    return {
        "level": cfg["id"], "condition": condition, "rows": rows,
        "correct": sum(row["correct"] for row in rows),
        "badge_remembered": remembered,
        "belief_before_recall": before, "belief_after_recall": after,
    }


def _condition_matrix() -> dict[str, dict[str, dict]]:
    return {
        condition: {level["id"]: _run_level_condition(level, condition) for level in s5.canonical_levels()}
        for condition in _CONDITIONS
    }


def _frozen_stage5_rows() -> dict[str, dict[str, dict[str, dict]]]:
    scale = s5.run_scale_matrix()
    return {
        entry["level"]: {
            mode: _row_map(entry["competitors"][mode])
            for mode in ("full", "lean", "baseline")
        }
        for entry in scale["levels"]
    }


def _attribution_row(level: str, checkpoint: str, requirement: str, frozen: dict, matrix: dict) -> dict:
    original = frozen[level]
    full = original["full"][checkpoint]
    lean = original["lean"][checkpoint]
    baseline = original["baseline"][checkpoint]
    restored_values = _row_map(matrix["restore_values"][level])[checkpoint]
    restored_recall = _row_map(matrix["restore_recall"][level])[checkpoint]
    if requirement == "values":
        chosen, alternate = "protect", "avoid"
        isolated = restored_values["decision"] == chosen and restored_recall["decision"] == lean["decision"]
        mechanism = "value_score_removed_to_zero_tie"
    elif requirement == "recall":
        chosen, alternate = "admit", "challenge"
        isolated = restored_recall["decision"] == chosen and restored_values["decision"] == lean["decision"]
        mechanism = "remembered_observation_not_reapplied_as_belief_evidence"
    else:
        raise ValueError(f"unsupported requirement: {requirement!r}")
    return {
        "level": level, "checkpoint": checkpoint, "requirement": requirement,
        "expected": full["expected"], "full_decision": full["decision"], "lean_decision": lean["decision"],
        "baseline_decision": baseline["decision"], "full_scores": full["scores"], "lean_scores": lean["scores"],
        "baseline_scores": baseline["scores"],
        "full_margin": _decision_margin(full["scores"], chosen, alternate),
        "lean_margin": _decision_margin(lean["scores"], lean["decision"], chosen),
        "restore_values_decision": restored_values["decision"], "restore_recall_decision": restored_recall["decision"],
        "isolated_counterfactual": isolated, "mechanism": mechanism,
    }


def _validate_replay(frozen: dict, matrix: dict) -> None:
    for level in frozen:
        for condition in ("full", "lean"):
            original = frozen[level][condition]
            replay = _row_map(matrix[condition][level])
            left = {k: (v["decision"], v["scores"]) for k, v in original.items()}
            right = {k: (v["decision"], v["scores"]) for k, v in replay.items()}
            if left != right:
                raise RuntimeError(f"Stage-5A {condition} replay drifted at {level}")


def _collect_divergences(frozen: dict, matrix: dict) -> list[dict]:
    rows = []
    observed = set()
    for level, modes in frozen.items():
        for checkpoint, full_row in modes["full"].items():
            lean_row = modes["lean"][checkpoint]
            if full_row["decision"] == lean_row["decision"]:
                continue
            key = (level, checkpoint)
            requirement = _EXPECTED_FAILURES.get(key)
            if requirement is None:
                raise RuntimeError(f"unexpected Lean divergence: {level}:{checkpoint}")
            observed.add(key)
            rows.append(_attribution_row(level, checkpoint, requirement, frozen, matrix))
    missing = sorted(set(_EXPECTED_FAILURES) - observed)
    if missing:
        raise RuntimeError(f"expected Lean divergences missing: {missing!r}")
    return rows


def _validate_isolation(divergences: list[dict]) -> None:
    for row in divergences:
        if not row["isolated_counterfactual"]:
            raise RuntimeError(f"counterfactual isolation failed: {row['level']}:{row['checkpoint']}")


def _memory_trace(matrix: dict, levels: list[str]) -> dict:
    return {
        level: {
            condition: {
                "remembered": matrix[condition][level]["badge_remembered"],
                "before": matrix[condition][level]["belief_before_recall"],
                "after": matrix[condition][level]["belief_after_recall"],
            }
            for condition in _CONDITIONS
        }
        for level in levels
    }


def run_attribution() -> dict:
    frozen = _frozen_stage5_rows()
    matrix = _condition_matrix()
    _validate_replay(frozen, matrix)
    divergences = _collect_divergences(frozen, matrix)
    _validate_isolation(divergences)
    return {
        "schema": SCHEMA, "strict_verdict": VERDICT,
        "stage5_totals": {"full": 57, "lean": 51, "baseline": 57},
        "divergence_count": len(divergences), "divergences": divergences,
        "counterfactual_totals": {
            condition: sum(matrix[condition][level]["correct"] for level in matrix[condition])
            for condition in _CONDITIONS
        },
        "memory_trace": _memory_trace(matrix, list(frozen)),
        "summary": {
            "values_failures": sum(row["requirement"] == "values" for row in divergences),
            "recall_failures": sum(row["requirement"] == "recall" for row in divergences),
            "unexplained_failures": sum(not row["isolated_counterfactual"] for row in divergences),
        },
        "claim_boundary": (
            "Stage 5A attributes only the six pre-existing Lean-vs-Full divergences on the frozen Stage-5 matrix. "
            "Orthogonal restoration identifies decision-path necessity on these checkpoints; it does not establish general Ghost superiority, production necessity, or a universal cognitive interpretation."
        ),
    }
