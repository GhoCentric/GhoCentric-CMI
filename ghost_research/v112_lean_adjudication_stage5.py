"""Research-only Stage-5 lean-policy adjudication and adversarial scaling.

Stage 5 positively constructs a lean Ghost action policy using only immediate
utility, persistent goals, and persistent beliefs.  It then compares that
policy with full Ghost and the unchanged strong flat baseline.  Stage-3 is
replayed unchanged before a broader pre-registered scale matrix is run.

The experiment does not edit production ``ghost.*`` code.  A policy channel
that matters here has earned a requirement-sensitive decision contribution,
not a general claim of Ghost superiority or production necessity.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ghost.ids import normalize_id
from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research import v112_ablation_stage4 as s4
from ghost_research.v112_action_policy_stage2 import apply_host_effects_to_ghost

SCHEMA = "ghost.v1.12-dev.lean-adjudication.stage5.v1"
VERDICT = "V112_LEAN_ADJUDICATION_STAGE5_EXPERIMENT_VALID"
FULL_WEIGHTS = {"utility": 1.0, "values": 1.0, "goals": 1.0, "beliefs": 1.0}
LEAN_WEIGHTS = {"utility": 1.0, "values": 0.0, "goals": 1.0, "beliefs": 1.0}
_HISTORY_LIMIT = 128
_LEVEL_KEYS = frozenset({"id", "subjects", "fillers", "restarts", "hostile", "contradiction"})
_MODES = frozenset({"full", "lean", "baseline"})


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        word = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{label} must be a {word} integer")
    return value


def _level(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _LEVEL_KEYS:
        raise ValueError("scale level has invalid shape")
    level_id = normalize_id(raw["id"], "scale level id")
    subjects = _positive_int(raw["subjects"], "scale level subjects")
    fillers = _positive_int(raw["fillers"], "scale level fillers", allow_zero=True)
    restarts = _positive_int(raw["restarts"], "scale level restarts", allow_zero=True)
    if restarts > fillers:
        raise ValueError("scale level restarts cannot exceed fillers")
    hostile = s3._signed(raw["hostile"], "scale level hostile signal")
    contradiction = s3._signed(raw["contradiction"], "scale level contradiction signal")
    if hostile <= 0.0 or contradiction >= 0.0:
        raise ValueError("scale level requires positive hostile and negative contradiction signals")
    return {
        "id": level_id, "subjects": subjects, "fillers": fillers,
        "restarts": restarts, "hostile": hostile, "contradiction": contradiction,
    }


def canonical_levels() -> list[dict]:
    return [
        _level({"id": "light", "subjects": 2, "fillers": 16, "restarts": 0, "hostile": 0.45, "contradiction": -0.90}),
        _level({"id": "medium", "subjects": 4, "fillers": 64, "restarts": 1, "hostile": 0.55, "contradiction": -0.90}),
        _level({"id": "heavy", "subjects": 8, "fillers": 120, "restarts": 3, "hostile": 0.65, "contradiction": -0.95}),
    ]


def _subject_ids(count: int) -> list[str]:
    count = _positive_int(count, "subject count")
    return [f"visitor_{index:02d}" for index in range(count)]


def _threat_candidates(subject: str) -> list[dict]:
    subject = normalize_id(subject, "threat subject")
    common = {"subject": subject, "dimension": "threat"}
    return [
        s3.candidate("admit", belief={**common, "alignment": {"benign": 1.0, "hostile": -1.0}}),
        s3.candidate("challenge", belief={**common, "alignment": {"benign": -1.0, "hostile": 1.0}}),
    ]


def _value_candidates() -> list[dict]:
    return [
        s3.candidate("avoid", values={"compassion": -1.0}),
        s3.candidate("protect", values={"compassion": 1.0}),
    ]


def _encode_bytes(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


class _Contender:
    def __init__(self, mode: str, subjects: list[str]) -> None:
        from ghost.api import GhostAPI

        if mode not in _MODES:
            raise ValueError(f"unsupported contender mode: {mode!r}")
        if not isinstance(subjects, list) or not subjects:
            raise ValueError("contender requires subjects")
        self.mode = mode
        self.subjects = [normalize_id(item, "contender subject") for item in subjects]
        if len(set(self.subjects)) != len(self.subjects):
            raise ValueError("contender subjects must be unique")
        capabilities = ["admit", "assist", "avoid", "challenge", "hold", "protect", "retreat"]
        if mode == "baseline":
            self.api = GhostAPI()
            self.agent = self.api.register_agent("baseline_guard", role="guard", capabilities=capabilities)
            beliefs = {subject: {"threat": {"benign": 0.5, "hostile": 0.5}} for subject in self.subjects}
            self.baseline = s3.FlatContinuityBaseline(s3._decision_state(), beliefs, history_limit=_HISTORY_LIMIT)
        else:
            self.api = GhostAPI()
            self.agent = self.api.register_agent(
                "guard", role="guard", values=s3._decision_state()["values"], goals=s3._agent_goals(), capabilities=capabilities,
            )
            self.baseline = None
            for subject in self.subjects:
                s3.seed_ghost_belief(self.api, subject=subject)

    def _holder(self) -> str:
        return "baseline_guard" if self.mode == "baseline" else "guard"

    def distribution(self, subject: str) -> dict[str, float]:
        subject = normalize_id(subject, "distribution subject")
        if self.mode == "baseline":
            return self.baseline.belief_distribution(subject, "threat")
        return s3._ghost_distribution(self.api, "guard", subject, "threat")

    def signal(self, subject: str, value: float) -> None:
        subject = normalize_id(subject, "signal subject")
        if self.mode == "baseline":
            self.baseline.apply_signal(subject, "threat", "hostile", "benign", value)
        else:
            s3.ghost_signal(self.api, value, subject=subject)

    def hidden_fact(self, subject: str, token: str) -> bool:
        subject = normalize_id(subject, "hidden fact subject")
        before = self.distribution(subject)
        if self.mode != "baseline":
            self.api.record_fact(f"hidden_{token}_{subject}", "host_truth", subject, "actual_intent", "benign")
        return before == self.distribution(subject)

    def observe_badge(self, subject: str) -> None:
        subject = normalize_id(subject, "badge subject")
        if self.mode == "baseline":
            self.baseline.observe("badge_seen", subject, {"badge": "red"})
        else:
            self.agent.observe("badge_seen", kind="direct", subject=subject, source="host", features={"badge": "red"})

    def has_badge(self, subject: str) -> bool:
        subject = normalize_id(subject, "badge subject")
        if self.mode == "baseline":
            return self.baseline.has_observation(subject, "badge", "red")
        return s3.ghost_has_observation(self.agent, subject, "badge", "red")

    def apply_effects(self, effects: dict) -> None:
        if self.mode == "baseline":
            self.baseline.apply_host_effects(effects)
        else:
            apply_host_effects_to_ghost(self.agent, effects)

    def choose(self, candidates: list[dict], checkpoint: str) -> dict:
        affordance = self.agent.set_affordances(candidates, context={"checkpoint": checkpoint, "mode": self.mode})
        if self.mode == "baseline":
            packet = s3.baseline_policy(self.baseline, affordance)
        else:
            weights = FULL_WEIGHTS if self.mode == "full" else LEAN_WEIGHTS
            packet = s3.ghost_policy(self.api, "guard", self.agent, affordance, weights=weights)
        decision = self.agent.choose_action(packet["scores"], policy_id=f"stage5_{self.mode}")
        self.agent.resolve_action(decision["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
        return {"decision": decision["candidate_id"], "scores": packet["scores"]}

    def delayed_badge_effect(self, subject: str) -> bool:
        remembered = self.has_badge(subject)
        if remembered and self.mode != "lean":
            self.signal(subject, -1.0)
        return remembered

    def filler(self, start: int, count: int) -> None:
        start = _positive_int(start, "filler start", allow_zero=True)
        count = _positive_int(count, "filler count", allow_zero=True)
        for index in range(start, start + count):
            subject, tone = f"ambient_{index % 11}", f"noise_{index % 7}"
            features = {"step": index, "tone": tone}
            if self.mode == "baseline":
                self.baseline.observe(f"ambient_event_{index}", subject, features)
            else:
                self.agent.observe(f"ambient_event_{index}", kind="environment", subject=subject, source="host", features=features)
                self.api.observe(observer="guard", kind="environment", visible_features=[tone], reliability=0.5, subject=subject, provenance={"step": index})

    def restart(self) -> None:
        from ghost.api import GhostAPI

        before = self._decision_fingerprint()
        self.api = GhostAPI.from_snapshot(self.api.snapshot())
        self.agent = self.api.agent(self._holder())
        if self.agent is None:
            raise RuntimeError("contender restart lost registered agent")
        if self.mode == "baseline":
            self.baseline = s3.FlatContinuityBaseline.from_snapshot(self.baseline.snapshot())
        if before != self._decision_fingerprint():
            raise RuntimeError("contender restart changed decision-relevant state")

    def _decision_fingerprint(self) -> dict:
        if self.mode == "baseline":
            return {
                "decision": deepcopy(self.baseline.decision_state),
                "beliefs": deepcopy(self.baseline.beliefs),
                "observations": deepcopy(self.baseline.observations),
            }
        return {
            "values": self.agent.values(), "goals": self.agent.goals(),
            "beliefs": {subject: self.distribution(subject) for subject in self.subjects},
            "observations": self.agent.observation_history(),
        }

    def snapshot_bytes(self) -> int:
        if self.mode == "baseline":
            return _encode_bytes(self.api.snapshot()) + _encode_bytes(self.baseline.snapshot())
        return _encode_bytes(self.api.snapshot())


def _score_row(contender: _Contender, candidates: list[dict], checkpoint: str, expected: str, requirement: str) -> dict:
    result = contender.choose(candidates, checkpoint)
    return {
        "checkpoint": checkpoint, "expected": expected, "requirement": requirement,
        "decision": result["decision"], "correct": result["decision"] == expected,
        "scores": result["scores"],
    }


def _run_fillers(contender: _Contender, count: int, restarts: int) -> None:
    count = _positive_int(count, "filler count", allow_zero=True)
    restarts = _positive_int(restarts, "restart count", allow_zero=True)
    if restarts > count:
        raise ValueError("restart count cannot exceed filler count")
    segments = restarts + 1
    base, extra = divmod(count, segments)
    cursor = 0
    for segment in range(segments):
        chunk = base + (1 if segment < extra else 0)
        contender.filler(cursor, chunk)
        cursor += chunk
        if segment < restarts:
            contender.restart()


def run_level(level: dict, mode: str) -> dict:
    cfg = _level(level)
    subjects = _subject_ids(cfg["subjects"])
    contender = _Contender(mode, subjects)
    rows = [
        _score_row(contender, s3._goal_candidates(), "goal_initial", "hold", "goals"),
        _score_row(contender, _value_candidates(), "value_preference", "protect", "values"),
    ]
    hidden_ok = []
    for index, subject in enumerate(subjects[:-1]):
        contender.signal(subject, cfg["hostile"])
        rows.append(_score_row(contender, _threat_candidates(subject), f"subject_{index}_hostile", "challenge", "beliefs"))
        hidden_ok.append(contender.hidden_fact(subject, cfg["id"]))
        rows.append(_score_row(contender, _threat_candidates(subject), f"subject_{index}_hidden", "challenge", "information_boundary"))
        contender.signal(subject, cfg["contradiction"])
        rows.append(_score_row(contender, _threat_candidates(subject), f"subject_{index}_revised", "admit", "belief_revision"))
    memory_subject = subjects[-1]
    contender.signal(memory_subject, cfg["hostile"])
    rows.append(_score_row(contender, _threat_candidates(memory_subject), "memory_hostile", "challenge", "beliefs"))
    contender.observe_badge(memory_subject)
    _run_fillers(contender, cfg["fillers"], cfg["restarts"])
    remembered = contender.delayed_badge_effect(memory_subject)
    rows.append(_score_row(contender, _threat_candidates(memory_subject), "delayed_badge", "admit", "recall"))
    contender.signal(memory_subject, cfg["contradiction"])
    rows.append(_score_row(contender, _threat_candidates(memory_subject), "memory_revised", "admit", "belief_revision"))
    contender.apply_effects({"goal_progress": {"hold_gate": 0.75}, "goal_priority": {"protect_civilian": 1.0}})
    rows.append(_score_row(contender, s3._conflict_candidates(), "conflict_shift", "assist", "goals"))
    contender.apply_effects({"goal_progress": {"hold_gate": 1.0}})
    rows.append(_score_row(contender, s3._goal_candidates(), "goal_complete", "retreat", "goals"))
    _run_fillers(contender, max(1, cfg["fillers"] // 4), min(cfg["restarts"], max(1, cfg["fillers"] // 4)))
    rows.append(_score_row(contender, s3._goal_candidates(), "recurrence", "retreat", "goals"))
    correct = sum(row["correct"] for row in rows)
    return {
        "level": cfg["id"], "mode": mode, "checkpoint_count": len(rows), "correct": correct,
        "accuracy": correct / len(rows), "rows": rows, "first_failure": next((row["checkpoint"] for row in rows if not row["correct"]), None),
        "hidden_information_boundary": all(hidden_ok), "badge_remembered": remembered,
        "snapshot_bytes": contender.snapshot_bytes(),
    }


def _decision_map(level_result: dict) -> dict[str, str]:
    return {row["checkpoint"]: row["decision"] for row in level_result["rows"]}


def _level_entry(level: dict) -> dict:
    competitors = {mode: run_level(level, mode) for mode in ("full", "lean", "baseline")}
    if len({result["checkpoint_count"] for result in competitors.values()}) != 1:
        raise RuntimeError("contenders did not receive the same checkpoint count")
    return {"level": level["id"], "config": level, "competitors": competitors}


def _first_failure(level_results: list[dict], mode: str) -> str | None:
    return next(
        (entry["level"] for entry in level_results if entry["competitors"][mode]["first_failure"] is not None),
        None,
    )


def _divergence_count(level_results: list[dict], left: str, right: str) -> int:
    total = 0
    for entry in level_results:
        left_map = _decision_map(entry["competitors"][left])
        right_map = _decision_map(entry["competitors"][right])
        total += sum(decision != right_map[key] for key, decision in left_map.items())
    return total


def run_scale_matrix(levels: list[dict] | None = None) -> dict:
    selected = canonical_levels() if levels is None else [_level(item) for item in deepcopy(levels)]
    if not selected:
        raise ValueError("scale matrix requires at least one level")
    level_results = [_level_entry(level) for level in selected]
    modes = ("full", "lean", "baseline")
    totals = {mode: sum(entry["competitors"][mode]["correct"] for entry in level_results) for mode in modes}
    checkpoints = sum(entry["competitors"]["full"]["checkpoint_count"] for entry in level_results)
    failures = {mode: _first_failure(level_results, mode) for mode in modes}
    divergences = {
        "full_vs_baseline": _divergence_count(level_results, "full", "baseline"),
        "lean_vs_full": _divergence_count(level_results, "lean", "full"),
    }
    return {
        "levels": level_results, "scored_checkpoints_per_contender": checkpoints,
        "totals": totals, "first_failure_level": failures, "decision_divergences": divergences,
        "full_vs_baseline_outcome": s3._comparative_outcome(totals["full"], totals["baseline"]),
    }


def run_frozen_replay() -> dict:
    stage3 = s3.run_matrix()
    full = s4.run_condition("full", s4.preregistered_conditions()["full"])
    lean = s4.run_condition("lean", {"weights": LEAN_WEIGHTS, "recall_enabled": False})
    if full["ghost_correct"] != stage3["ghost_correct"] or full["baseline_correct"] != stage3["baseline_correct"]:
        raise RuntimeError("Stage-5 full replay no longer matches frozen Stage-3 scores")
    return {
        "stage3_scores": {"ghost": stage3["ghost_correct"], "baseline": stage3["baseline_correct"]},
        "full_scores": {"ghost": full["ghost_correct"], "baseline": full["baseline_correct"]},
        "lean_scores": {"ghost": lean["ghost_correct"], "baseline": lean["baseline_correct"]},
        "full_decision_match": s4._decision_map(full) == s4._decision_map(s4.run_condition("full_repeat", s4.preregistered_conditions()["full"])),
        "lean_decision_match_to_full": s4._decision_map(lean) == s4._decision_map(full),
        "lean_frozen_equivalent": lean["ghost_correct"] == full["ghost_correct"] and s4._decision_map(lean) == s4._decision_map(full),
    }


def run_capacity_probe(fill_counts: list[int] | None = None) -> dict:
    counts = [120, 127, 128, 129] if fill_counts is None else deepcopy(fill_counts)
    if not isinstance(counts, list) or not counts:
        raise ValueError("capacity probe requires filler counts")
    normalized = [_positive_int(item, "capacity filler count", allow_zero=True) for item in counts]
    if len(set(normalized)) != len(normalized):
        raise ValueError("capacity filler counts must be unique")
    rows = []
    for count in normalized:
        retained = {}
        for mode in ("full", "baseline"):
            contender = _Contender(mode, ["visitor_00"])
            contender.observe_badge("visitor_00")
            contender.filler(0, count)
            contender.restart()
            retained[mode] = contender.has_badge("visitor_00")
        rows.append({"fillers": count, "retained": retained, "agreement": retained["full"] == retained["baseline"]})
    return {"history_limit": _HISTORY_LIMIT, "rows": rows, "all_agree": all(row["agreement"] for row in rows)}


def _requirements_from_scale(scale: dict) -> dict:
    losses = {"values": 0, "recall": 0, "other": 0}
    for entry in scale["levels"]:
        for row in entry["competitors"]["lean"]["rows"]:
            if row["correct"]:
                continue
            bucket = row["requirement"] if row["requirement"] in {"values", "recall"} else "other"
            losses[bucket] += 1
    return losses


def run_adjudication() -> dict:
    frozen = run_frozen_replay()
    scale = run_scale_matrix()
    capacity = run_capacity_probe()
    requirement_losses = _requirements_from_scale(scale)
    return {
        "schema": SCHEMA, "strict_verdict": VERDICT,
        "frozen_replay": frozen, "scale_matrix": scale, "capacity_probe": capacity,
        "lean_requirement_losses": requirement_losses,
        "interpretation": {
            "lean_frozen_equivalent": frozen["lean_frozen_equivalent"],
            "lean_scaled_equivalent": scale["totals"]["lean"] == scale["totals"]["full"] and scale["decision_divergences"]["lean_vs_full"] == 0,
            "full_vs_baseline_outcome": scale["full_vs_baseline_outcome"],
            "values_requirement_sensitive": requirement_losses["values"] > 0,
            "recall_requirement_sensitive": requirement_losses["recall"] > 0,
        },
        "claim_boundary": (
            "Stage 5 tests one positive lean policy construction, one unchanged strong flat baseline, and a pre-registered scale matrix. "
            "A channel that prevents a scored failure is requirement-sensitive on this matrix only. Full-vs-baseline results remain directional evidence, not a general Ghost-superiority claim. "
            "Lean Ghost still stores the full Ghost runtime state; this experiment adjudicates decision-path simplification, not production package deletion or memory savings."
        ),
    }
