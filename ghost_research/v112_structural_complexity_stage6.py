"""Research-only Stage-6 structural-complexity stress experiment.

Stage 6 freezes the Full-Ghost decision path and the strong flat baseline from
Stage 5A, then increases *structure* rather than simple event-stream length.
Each level adds simultaneously active agents, subjects, sources, relationship
edges, agent-specific beliefs, and overlapping unresolved actions.

The baseline owns its own decision state, beliefs, observation history, source
trust, snapshots, and action-runtime agents.  It is never mirrored from Ghost.
Comparative scores are evidence, not pass/fail criteria.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ghost.ids import normalize_id
from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research import v112_lean_adjudication_stage5 as s5
from ghost_research.v112_action_policy_stage2 import apply_host_effects_to_ghost

SCHEMA = "ghost.v1.12-dev.structural-complexity.stage6.v1"
VERDICT = "V112_STRUCTURAL_COMPLEXITY_STAGE6_EXPERIMENT_VALID"
_MODES = frozenset({"full", "baseline"})
_LEVEL_KEYS = frozenset({"id", "agents", "pending"})
_RELATIONSHIP_DELTAS = {"help": 0.20, "deceive": -0.15, "betrayal": -0.80}
_CAPABILITIES = ["admit", "assist", "avoid", "challenge", "hold", "protect", "retreat"]


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        word = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{label} must be a {word} integer")
    return value


def _level(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _LEVEL_KEYS:
        raise ValueError("structural level has invalid shape")
    level_id = normalize_id(raw["id"], "structural level id")
    agents = _positive_int(raw["agents"], "structural agents")
    pending = _positive_int(raw["pending"], "structural pending", allow_zero=True)
    if agents < 3:
        raise ValueError("structural level requires at least three agents")
    if pending >= agents:
        raise ValueError("structural pending must be smaller than agent count")
    return {"id": level_id, "agents": agents, "pending": pending}


def canonical_levels() -> list[dict]:
    return [
        _level({"id": "light_mesh", "agents": 3, "pending": 1}),
        _level({"id": "medium_mesh", "agents": 4, "pending": 2}),
        _level({"id": "heavy_mesh", "agents": 5, "pending": 3}),
    ]


def _ids(prefix: str, count: int) -> list[str]:
    count = _positive_int(count, f"{prefix} count")
    return [f"{prefix}_{index:02d}" for index in range(count)]


def _pair_key(agent_id: str, source_id: str) -> str:
    return normalize_id(agent_id, "relationship agent") + "|" + normalize_id(source_id, "relationship source")


def _sign(value: float) -> float:
    return 1.0 if value > 1e-12 else (-1.0 if value < -1e-12 else 0.0)


def _encode_bytes(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


def _decision_state() -> dict:
    return deepcopy(s3._decision_state())


def _beliefs(subjects: list[str]) -> dict:
    return {subject: {"threat": {"benign": 0.5, "hostile": 0.5}} for subject in subjects}


class StructuralContender:
    """Independent multi-agent contender for Stage 6."""

    def __init__(self, mode: str, agent_count: int) -> None:
        from ghost.api import GhostAPI

        if mode not in _MODES:
            raise ValueError(f"unsupported structural contender mode: {mode!r}")
        agent_count = _positive_int(agent_count, "structural contender agent_count")
        if agent_count < 3:
            raise ValueError("structural contender requires at least three agents")
        self.mode = mode
        self.agent_ids = _ids("guard", agent_count)
        self.source_ids = _ids("source", agent_count)
        self.subject_ids = _ids("visitor", agent_count * 2)
        self.api = GhostAPI()
        self.agents: dict[str, Any] = {}
        self.flat: dict[str, s3.FlatContinuityBaseline] = {}
        self.relationships: dict[str, float] = {}
        for logical in self.agent_ids:
            runtime_id = self._runtime_id(logical)
            values = _decision_state()["values"] if mode == "full" else None
            goals = s3._agent_goals() if mode == "full" else None
            self.agents[logical] = self.api.register_agent(
                runtime_id, role="guard", values=values, goals=goals, capabilities=_CAPABILITIES,
            )
            if mode == "baseline":
                self.flat[logical] = s3.FlatContinuityBaseline(_decision_state(), _beliefs(self.subject_ids))
            else:
                for subject in self.subject_ids:
                    s3.seed_ghost_belief(self.api, holder=logical, subject=subject)
        self._seed_relationship_mesh()

    def _runtime_id(self, logical: str) -> str:
        logical = normalize_id(logical, "logical agent")
        return logical if self.mode == "full" else f"baseline_{logical}"

    def _seed_relationship_mesh(self) -> None:
        count = len(self.agent_ids)
        for index, agent_id in enumerate(self.agent_ids):
            trusted = (self.source_ids[index], self.source_ids[(index + 1) % count])
            distrusted = self.source_ids[(index - 1) % count]
            for source_id in trusted:
                self.relationship_event(agent_id, source_id, "help")
                self.relationship_event(agent_id, source_id, "help")
            self.relationship_event(agent_id, distrusted, "deceive")
            self.relationship_event(agent_id, distrusted, "deceive")

    def trust(self, agent_id: str, source_id: str) -> float:
        agent_id = normalize_id(agent_id, "trust agent")
        source_id = normalize_id(source_id, "trust source")
        if self.mode == "full":
            return float(self.api.get_relationship(agent_id, source_id)["trust"])
        return self.relationships.get(_pair_key(agent_id, source_id), 0.0)

    def relationship_event(self, agent_id: str, source_id: str, event: str) -> float:
        agent_id = normalize_id(agent_id, "relationship agent")
        source_id = normalize_id(source_id, "relationship source")
        event = normalize_id(event, "relationship event")
        if event not in _RELATIONSHIP_DELTAS:
            raise ValueError(f"unsupported structural relationship event: {event!r}")
        if self.mode == "full":
            self.api.apply_event(source_id, agent_id, {"type": event, "intensity": 1.0})
        else:
            key = _pair_key(agent_id, source_id)
            self.relationships[key] = max(-1.0, min(1.0, self.relationships.get(key, 0.0) + _RELATIONSHIP_DELTAS[event]))
        return self.trust(agent_id, source_id)

    def distribution(self, agent_id: str, subject: str) -> dict[str, float]:
        agent_id = normalize_id(agent_id, "distribution agent")
        subject = normalize_id(subject, "distribution subject")
        if self.mode == "full":
            return s3._ghost_distribution(self.api, agent_id, subject, "threat")
        return self.flat[agent_id].belief_distribution(subject, "threat")

    def direct_signal(self, agent_id: str, subject: str, signal: float) -> dict[str, float]:
        agent_id = normalize_id(agent_id, "signal agent")
        subject = normalize_id(subject, "signal subject")
        signed = s3._signed(signal, "direct signal")
        if self.mode == "full":
            s3.ghost_signal(self.api, signed, holder=agent_id, subject=subject)
        else:
            self.flat[agent_id].apply_signal(subject, "threat", "hostile", "benign", signed)
        return self.distribution(agent_id, subject)

    def source_claim(self, agent_id: str, source_id: str, subject: str, signal: float) -> dict:
        trust = self.trust(agent_id, source_id)
        raw = s3._signed(signal, "source claim")
        effective = raw * _sign(trust)
        if effective != 0.0:
            self.direct_signal(agent_id, subject, effective)
        return {"trust": trust, "raw_signal": raw, "effective_signal": effective, "distribution": self.distribution(agent_id, subject)}

    def hidden_fact(self, agent_id: str, subject: str, token: str) -> bool:
        agent_id = normalize_id(agent_id, "hidden fact agent")
        subject = normalize_id(subject, "hidden fact subject")
        token = normalize_id(token, "hidden fact token")
        before = self.distribution(agent_id, subject)
        if self.mode == "full":
            self.api.record_fact(f"hidden_{token}_{agent_id}_{subject}", "host_truth", subject, "actual_intent", "benign")
        return before == self.distribution(agent_id, subject)

    def observe_badge(self, agent_id: str, subject: str) -> None:
        agent_id = normalize_id(agent_id, "badge agent")
        subject = normalize_id(subject, "badge subject")
        if self.mode == "full":
            self.agents[agent_id].observe("badge_seen", kind="direct", subject=subject, source="host", features={"badge": "red"})
        else:
            self.flat[agent_id].observe("badge_seen", subject, {"badge": "red"})

    def has_badge(self, agent_id: str, subject: str) -> bool:
        agent_id = normalize_id(agent_id, "badge agent")
        subject = normalize_id(subject, "badge subject")
        if self.mode == "full":
            return s3.ghost_has_observation(self.agents[agent_id], subject, "badge", "red")
        return self.flat[agent_id].has_observation(subject, "badge", "red")

    def delayed_badge_effect(self, agent_id: str, subject: str) -> bool:
        remembered = self.has_badge(agent_id, subject)
        if remembered:
            self.direct_signal(agent_id, subject, -1.0)
        return remembered

    def apply_effects(self, agent_id: str, effects: dict) -> None:
        agent_id = normalize_id(agent_id, "effects agent")
        if self.mode == "full":
            apply_host_effects_to_ghost(self.agents[agent_id], effects)
        else:
            self.flat[agent_id].apply_host_effects(effects)

    def _packet(self, agent_id: str, candidates: list[dict], checkpoint: str) -> tuple[Any, dict]:
        agent_id = normalize_id(agent_id, "decision agent")
        agent = self.agents[agent_id]
        affordance = agent.set_affordances(candidates, context={"checkpoint": checkpoint, "mode": self.mode, "logical_agent": agent_id})
        if self.mode == "full":
            packet = s3.ghost_policy(self.api, agent_id, agent, affordance)
        else:
            packet = s3.baseline_policy(self.flat[agent_id], affordance)
        return agent, packet

    def choose(self, agent_id: str, candidates: list[dict], checkpoint: str) -> dict:
        agent, packet = self._packet(agent_id, candidates, checkpoint)
        decision = agent.choose_action(packet["scores"], policy_id=f"stage6_{self.mode}")
        agent.resolve_action(decision["decision_id"], "succeeded", outcome={"checkpoint": checkpoint})
        return {"decision": decision["candidate_id"], "scores": packet["scores"]}

    def begin_pending(self, agent_id: str, candidates: list[dict], checkpoint: str) -> dict:
        agent, packet = self._packet(agent_id, candidates, checkpoint)
        decision = agent.choose_action(packet["scores"], policy_id=f"stage6_pending_{self.mode}")
        return {"decision": decision["candidate_id"], "scores": packet["scores"], "pending": deepcopy(decision)}

    def resolve_pending(self, agent_id: str, status: str = "succeeded") -> dict:
        agent_id = normalize_id(agent_id, "pending agent")
        pending = self.agents[agent_id].pending_action()
        if pending is None:
            raise ValueError("agent has no pending action")
        return self.agents[agent_id].resolve_action(pending["decision_id"], status, outcome={"stage6": True})

    def pending_map(self) -> dict[str, str]:
        out = {}
        for agent_id in self.agent_ids:
            pending = self.agents[agent_id].pending_action()
            if pending is not None:
                out[agent_id] = pending["candidate_id"]
        return out

    def _fingerprint(self) -> dict:
        if self.mode == "full":
            state = {
                "beliefs": {agent: {subject: self.distribution(agent, subject) for subject in self.subject_ids} for agent in self.agent_ids},
                "relationships": {_pair_key(agent, source): self.trust(agent, source) for agent in self.agent_ids for source in self.source_ids},
                "goals": {agent: self.agents[agent].goals() for agent in self.agent_ids},
                "values": {agent: self.agents[agent].values() for agent in self.agent_ids},
                "observations": {agent: self.agents[agent].observation_history() for agent in self.agent_ids},
            }
        else:
            state = {
                "flat": {agent: self.flat[agent].snapshot() for agent in self.agent_ids},
                "relationships": deepcopy(self.relationships),
            }
        state["pending"] = self.pending_map()
        return state

    def restart(self) -> None:
        from ghost.api import GhostAPI

        before = self._fingerprint()
        self.api = GhostAPI.from_snapshot(self.api.snapshot())
        self.agents = {logical: self.api.agent(self._runtime_id(logical)) for logical in self.agent_ids}
        if any(agent is None for agent in self.agents.values()):
            raise RuntimeError("structural restart lost registered agent")
        if self.mode == "baseline":
            snapshots = {agent: self.flat[agent].snapshot() for agent in self.agent_ids}
            self.flat = {agent: s3.FlatContinuityBaseline.from_snapshot(snapshots[agent]) for agent in self.agent_ids}
            self.relationships = deepcopy(self.relationships)
        if before != self._fingerprint():
            raise RuntimeError("structural restart changed decision-relevant state")

    def snapshot_bytes(self) -> int:
        if self.mode == "full":
            return _encode_bytes(self.api.snapshot())
        return _encode_bytes(self.api.snapshot()) + _encode_bytes({"flat": {a: self.flat[a].snapshot() for a in self.agent_ids}, "relationships": self.relationships})

    def custom_baseline_bytes(self) -> int:
        if self.mode != "baseline":
            return 0
        return _encode_bytes({"flat": {a: self.flat[a].snapshot() for a in self.agent_ids}, "relationships": self.relationships})


def _score(contender: StructuralContender, rows: list[dict], agent_id: str, candidates: list[dict], checkpoint: str, expected: str, requirement: str) -> None:
    result = contender.choose(agent_id, candidates, checkpoint)
    rows.append({
        "agent": agent_id, "checkpoint": checkpoint, "expected": expected, "requirement": requirement,
        "decision": result["decision"], "correct": result["decision"] == expected, "scores": result["scores"],
    })


def _score_pending(contender: StructuralContender, rows: list[dict], agent_id: str, checkpoint: str) -> None:
    result = contender.begin_pending(agent_id, s3._goal_candidates(), checkpoint)
    rows.append({
        "agent": agent_id, "checkpoint": checkpoint, "expected": "hold", "requirement": "overlapping_pending",
        "decision": result["decision"], "correct": result["decision"] == "hold", "scores": result["scores"],
    })


def _initial_decisions(contender: StructuralContender, rows: list[dict]) -> None:
    for index, agent_id in enumerate(contender.agent_ids):
        _score(contender, rows, agent_id, s3._goal_candidates(), f"{agent_id}:goal_initial", "hold", "goals")
        _score(contender, rows, agent_id, s5._value_candidates(), f"{agent_id}:value_preference", "protect", "values")
        primary = contender.subject_ids[index]
        source = contender.source_ids[index]
        contender.source_claim(agent_id, source, primary, 1.0)
        _score(contender, rows, agent_id, s5._threat_candidates(primary), f"{agent_id}:trusted_primary", "challenge", "relationship_weighted_belief")


def _relay_decisions(contender: StructuralContender, rows: list[dict], hidden_checks: list[bool]) -> None:
    count = len(contender.agent_ids)
    for index, source in enumerate(contender.source_ids):
        receiver = contender.agent_ids[(index + 1) % count]
        primary = contender.subject_ids[index]
        contender.source_claim(receiver, source, primary, 1.0)
        _score(contender, rows, receiver, s5._threat_candidates(primary), f"{receiver}:distrusted_relay_{index}", "admit", "agent_specific_relationship")
        hidden_checks.append(contender.hidden_fact(receiver, primary, f"relay_{index}"))
        _score(contender, rows, receiver, s5._threat_candidates(primary), f"{receiver}:hidden_relay_{index}", "admit", "information_boundary")


def _begin_pending(contender: StructuralContender, rows: list[dict], pending_count: int) -> tuple[list[str], dict[str, str]]:
    pending_agents = contender.agent_ids[:pending_count]
    for agent_id in pending_agents:
        _score_pending(contender, rows, agent_id, f"{agent_id}:pending_hold")
    return pending_agents, contender.pending_map()


def _prepare_secondary_state(contender: StructuralContender, hidden_checks: list[bool]) -> None:
    count = len(contender.agent_ids)
    for index, agent_id in enumerate(contender.agent_ids):
        secondary = contender.subject_ids[count + index]
        own_source = contender.source_ids[index]
        contender.observe_badge(agent_id, secondary)
        contender.relationship_event(agent_id, own_source, "betrayal")
        contender.source_claim(agent_id, own_source, secondary, 1.0)
        hidden_checks.append(contender.hidden_fact(agent_id, secondary, f"secondary_{index}"))


def _restart_with_pending(contender: StructuralContender, before: dict[str, str], pending_count: int) -> bool:
    contender.restart()
    after = contender.pending_map()
    return before == after and len(after) == pending_count


def _resolve_pending_effects(contender: StructuralContender, pending_agents: list[str]) -> None:
    for agent_id in pending_agents:
        contender.resolve_pending(agent_id, "succeeded")
        contender.apply_effects(agent_id, {"goal_progress": {"hold_gate": 0.75}, "goal_priority": {"protect_civilian": 1.0}})


def _secondary_decisions(contender: StructuralContender, rows: list[dict], memory_checks: list[bool], pending_agents: list[str]) -> None:
    count = len(contender.agent_ids)
    pending = set(pending_agents)
    for index, agent_id in enumerate(contender.agent_ids):
        secondary = contender.subject_ids[count + index]
        _score(contender, rows, agent_id, s5._threat_candidates(secondary), f"{agent_id}:post_betrayal", "admit", "relationship_reversal")
        _score(contender, rows, agent_id, s5._threat_candidates(secondary), f"{agent_id}:hidden_secondary", "admit", "information_boundary")
        confirming = contender.source_ids[(index + 1) % count]
        contender.source_claim(agent_id, confirming, secondary, 1.0)
        contender.source_claim(agent_id, confirming, secondary, 1.0)
        _score(contender, rows, agent_id, s5._threat_candidates(secondary), f"{agent_id}:multi_source_confirmed", "challenge", "multi_source_belief")
        memory_checks.append(contender.delayed_badge_effect(agent_id, secondary))
        _score(contender, rows, agent_id, s5._threat_candidates(secondary), f"{agent_id}:delayed_badge", "admit", "recall")
        contender.direct_signal(agent_id, secondary, 1.0)
        _score(contender, rows, agent_id, s5._threat_candidates(secondary), f"{agent_id}:recurrence_hostile", "challenge", "history_dependent_recurrence")
        expected_conflict = "assist" if agent_id in pending else "hold"
        _score(contender, rows, agent_id, s3._conflict_candidates(), f"{agent_id}:goal_shift", expected_conflict, "overlapping_consequence")
        contender.apply_effects(agent_id, {"goal_progress": {"hold_gate": 1.0}})
        _score(contender, rows, agent_id, s3._goal_candidates(), f"{agent_id}:goal_complete", "retreat", "goals")


def _run_level(level: dict, mode: str) -> dict:
    cfg = _level(level)
    contender = StructuralContender(mode, cfg["agents"])
    rows: list[dict] = []
    hidden_checks: list[bool] = []
    memory_checks: list[bool] = []
    _initial_decisions(contender, rows)
    _relay_decisions(contender, rows, hidden_checks)
    pending_agents, pending_before = _begin_pending(contender, rows, cfg["pending"])
    _prepare_secondary_state(contender, hidden_checks)
    pending_restart_ok = _restart_with_pending(contender, pending_before, cfg["pending"])
    pending_after = contender.pending_map()
    _resolve_pending_effects(contender, pending_agents)
    _secondary_decisions(contender, rows, memory_checks, pending_agents)
    correct = sum(row["correct"] for row in rows)
    count = cfg["agents"]
    return {
        "level": cfg["id"], "mode": mode, "config": cfg, "checkpoint_count": len(rows), "correct": correct,
        "accuracy": correct / len(rows), "rows": rows, "first_failure": next((row["checkpoint"] for row in rows if not row["correct"]), None),
        "hidden_information_boundary": all(hidden_checks), "all_badges_remembered": all(memory_checks),
        "pending_restart_ok": pending_restart_ok, "pending_before_restart": pending_before, "pending_after_restart": pending_after,
        "snapshot_bytes": contender.snapshot_bytes(), "custom_baseline_bytes": contender.custom_baseline_bytes(),
        "structure": {"agents": count, "sources": count, "subjects": count * 2, "relationship_edges_seeded": count * 3, "overlapping_pending": cfg["pending"]},
    }


def _decision_map(result: dict) -> dict[str, str]:
    return {row["checkpoint"]: row["decision"] for row in result["rows"]}


def _comparative_outcome(full: int, baseline: int) -> str:
    if full > baseline:
        return "directional_ghost_advantage"
    if baseline > full:
        return "directional_baseline_advantage"
    return "behavioral_parity_on_scored_constraints"


def _level_entry(level: dict) -> dict:
    full = _run_level(level, "full")
    baseline = _run_level(level, "baseline")
    if full["checkpoint_count"] != baseline["checkpoint_count"]:
        raise RuntimeError("structural contenders received different checkpoint counts")
    return {"level": level["id"], "config": level, "full": full, "baseline": baseline}


def _first_failure(entries: list[dict], mode: str) -> str | None:
    return next((entry["level"] for entry in entries if entry[mode]["first_failure"] is not None), None)


def _divergences(entries: list[dict]) -> int:
    total = 0
    for entry in entries:
        baseline = _decision_map(entry["baseline"])
        total += sum(decision != baseline[key] for key, decision in _decision_map(entry["full"]).items())
    return total


def _invariants(entries: list[dict]) -> dict[str, bool]:
    modes = ("full", "baseline")
    return {
        "hidden_information": all(entry[mode]["hidden_information_boundary"] for entry in entries for mode in modes),
        "badge_recall": all(entry[mode]["all_badges_remembered"] for entry in entries for mode in modes),
        "pending_restart": all(entry[mode]["pending_restart_ok"] for entry in entries for mode in modes),
    }


def run_matrix(levels: list[dict] | None = None) -> dict:
    selected = canonical_levels() if levels is None else [_level(item) for item in deepcopy(levels)]
    if not selected:
        raise ValueError("structural matrix requires at least one level")
    entries = [_level_entry(level) for level in selected]
    totals = {mode: sum(entry[mode]["correct"] for entry in entries) for mode in ("full", "baseline")}
    checkpoints = sum(entry["full"]["checkpoint_count"] for entry in entries)
    return {
        "levels": entries, "scored_checkpoints_per_contender": checkpoints, "totals": totals,
        "decision_divergences": _divergences(entries),
        "first_failure_level": {mode: _first_failure(entries, mode) for mode in ("full", "baseline")},
        "comparative_outcome": _comparative_outcome(totals["full"], totals["baseline"]), "invariants": _invariants(entries),
    }


def run_experiment() -> dict:
    matrix = run_matrix()
    return {
        "schema": SCHEMA, "strict_verdict": VERDICT, "matrix": matrix,
        "interpretation": {
            "comparative_outcome": matrix["comparative_outcome"],
            "structural_invariants_pass": all(matrix["invariants"].values()),
            "baseline_rewritten_for_ghost": False,
            "duration_only_scaling": False,
        },
        "claim_boundary": (
            "Stage 6 increases simultaneous structural state: agents, sources, subjects, relationship edges, agent-specific beliefs, and overlapping unresolved actions. "
            "It does not claim realism, intelligence, uniqueness, or general Ghost superiority. A score difference is directional evidence on this pre-registered matrix only; parity remains a valid result."
        ),
    }
