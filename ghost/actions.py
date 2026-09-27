"""Deterministic engine-neutral action handshake for Ghost v1.12 development.

Stage 1 deliberately separates *action protocol* from *action policy*.
The host supplies the current legal affordances. A policy supplies one finite score
per candidate. Ghost deterministically chooses exactly one candidate, persists that
decision, and waits for the host to report the execution outcome.

This runtime does not discover legal actions, execute behavior, infer success,
change game-world state, or invent candidate scores. Keeping those concerns out of
the protocol gives later Ghost-state policies and simpler baselines one identical
execution/result substrate for fair experiments.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .ids import normalize_id

ACTION_SNAPSHOT_SCHEMA_VERSION = "1.0"
DEFAULT_ACTION_HISTORY_LIMIT = 128
ACTION_FINAL_STATUSES = frozenset({"succeeded", "failed", "interrupted", "cancelled"})

_SNAPSHOT_KEYS = {"schema_version", "history_limit", "sequence", "agents"}
_AGENT_KEYS = {"pending", "history"}
_DECISION_KEYS = {
    "decision_id", "sequence", "agent", "affordance_sequence", "candidate_id",
    "capability", "score", "scores", "policy_id", "context",
}
_RESULT_KEYS = {"resolution_sequence", "decision", "status", "outcome"}
_AFFORDANCE_KEYS = {"sequence", "agent", "candidates", "context"}
_CANDIDATE_KEYS = {"id", "capability", "features"}


def _positive_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{label} must be a finite number")
    return out


def _json_copy(value: Any, label: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must contain only finite numbers")
        return value
    if isinstance(value, list):
        return [_json_copy(item, f"{label}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ValueError(f"{label} keys must be strings")
            key = raw_key.strip()
            if not key:
                raise ValueError(f"{label} keys must be non-empty strings")
            if key in out:
                raise ValueError(f"{label} contains duplicate normalized key: {key!r}")
            out[key] = _json_copy(item, f"{label}.{key}")
        return {key: out[key] for key in sorted(out)}
    raise ValueError(f"{label} must be strict JSON-safe data")


def _metadata(value, label: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dict or None")
    return _json_copy(value, label)


def _final_status(value, label: str = "action status") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    status = value.strip().lower()
    if status not in ACTION_FINAL_STATUSES:
        raise ValueError(
            f"unsupported {label}: {value!r}; expected one of {sorted(ACTION_FINAL_STATUSES)}"
        )
    return status


def _affordance_view(record, agent: str) -> tuple[int, list[tuple[str, str]]]:
    if not isinstance(record, dict) or set(record) != _AFFORDANCE_KEYS:
        raise ValueError("action affordance record has invalid keys")
    sequence = _positive_int(record["sequence"], "action affordance sequence")
    if normalize_id(record["agent"], "action affordance agent") != agent:
        raise ValueError("action affordance record belongs to a different agent")
    raw_candidates = record["candidates"]
    if not isinstance(raw_candidates, list):
        raise ValueError("action affordance candidates must be a list")
    if not raw_candidates:
        raise ValueError("cannot choose an action from an empty affordance set")
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict) or set(raw) != _CANDIDATE_KEYS:
            raise ValueError(f"action affordance candidate[{index}] has invalid keys")
        candidate_id = normalize_id(raw["id"], f"action affordance candidate[{index}] id")
        capability = normalize_id(raw["capability"], f"action affordance candidate[{index}] capability")
        if candidate_id in seen:
            raise ValueError(f"action affordance candidates contain duplicate id: {candidate_id!r}")
        seen.add(candidate_id)
        candidates.append((candidate_id, capability))
    return sequence, candidates


def _scores(value, candidate_ids: set[str]) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("action scores must be a dict")
    out: dict[str, float] = {}
    for raw_key, raw_score in value.items():
        key = normalize_id(raw_key, "action score candidate id")
        if key in out:
            raise ValueError(f"action scores contain duplicate normalized candidate id: {key!r}")
        out[key] = _finite(raw_score, f"action score {key}")
    missing = candidate_ids - set(out)
    extra = set(out) - candidate_ids
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(sorted(missing)))
        if extra:
            detail.append("extra=" + ",".join(sorted(extra)))
        raise ValueError("action scores must cover current candidates exactly (" + "; ".join(detail) + ")")
    return {key: out[key] for key in sorted(out)}


def _validate_decision(raw, agent: str, sequence: int, label: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != _DECISION_KEYS:
        raise ValueError(f"{label} has invalid keys")
    decision_sequence = _positive_int(raw["sequence"], f"{label}.sequence")
    if decision_sequence > sequence:
        raise ValueError(f"{label}.sequence exceeds snapshot sequence")
    decision_id = normalize_id(raw["decision_id"], f"{label}.decision_id")
    if decision_id != f"action_decision_{decision_sequence}":
        raise ValueError(f"{label}.decision_id is inconsistent with sequence")
    if normalize_id(raw["agent"], f"{label}.agent") != agent:
        raise ValueError(f"{label}.agent does not match owner")
    affordance_sequence = _positive_int(raw["affordance_sequence"], f"{label}.affordance_sequence")
    candidate_id = normalize_id(raw["candidate_id"], f"{label}.candidate_id")
    capability = normalize_id(raw["capability"], f"{label}.capability")
    score = _finite(raw["score"], f"{label}.score")
    score_table = raw["scores"]
    if not isinstance(score_table, dict) or not score_table:
        raise ValueError(f"{label}.scores must be a non-empty dict")
    validated_scores: dict[str, float] = {}
    for raw_key, raw_score in score_table.items():
        key = normalize_id(raw_key, f"{label}.scores candidate id")
        if key in validated_scores:
            raise ValueError(f"{label}.scores contain duplicate normalized candidate id")
        validated_scores[key] = _finite(raw_score, f"{label}.scores.{key}")
    if candidate_id not in validated_scores or validated_scores[candidate_id] != score:
        raise ValueError(f"{label} selected score is inconsistent with score table")
    expected = min(validated_scores, key=lambda item: (-validated_scores[item], item))
    if candidate_id != expected:
        raise ValueError(f"{label} selected candidate is inconsistent with deterministic ranking")
    return {
        "decision_id": decision_id,
        "sequence": decision_sequence,
        "agent": agent,
        "affordance_sequence": affordance_sequence,
        "candidate_id": candidate_id,
        "capability": capability,
        "score": score,
        "scores": {key: validated_scores[key] for key in sorted(validated_scores)},
        "policy_id": normalize_id(raw["policy_id"], f"{label}.policy_id"),
        "context": _metadata(raw["context"], f"{label}.context"),
    }


def _validate_result(raw, agent: str, sequence: int, label: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != _RESULT_KEYS:
        raise ValueError(f"{label} has invalid keys")
    resolution_sequence = _positive_int(raw["resolution_sequence"], f"{label}.resolution_sequence")
    if resolution_sequence > sequence:
        raise ValueError(f"{label}.resolution_sequence exceeds snapshot sequence")
    decision = _validate_decision(raw["decision"], agent, sequence, f"{label}.decision")
    if resolution_sequence <= decision["sequence"]:
        raise ValueError(f"{label}.resolution_sequence must follow decision sequence")
    return {
        "resolution_sequence": resolution_sequence,
        "decision": decision,
        "status": _final_status(raw["status"], f"{label}.status"),
        "outcome": _metadata(raw["outcome"], f"{label}.outcome"),
    }



def _restore_agent_state(
    raw_state, *, agent: str, sequence: int, history_limit: int, seen_sequences: set[int]
) -> tuple[dict, int]:
    if not isinstance(raw_state, dict) or set(raw_state) != _AGENT_KEYS:
        raise ValueError(f"action snapshot state for {agent!r} has invalid keys")
    pending = raw_state["pending"]
    max_sequence = 0
    if pending is not None:
        pending = _validate_decision(
            pending, agent, sequence, f"action snapshot {agent}.pending"
        )
        if pending["sequence"] in seen_sequences:
            raise ValueError("action snapshot contains duplicate global sequence")
        seen_sequences.add(pending["sequence"])
        max_sequence = pending["sequence"]
    raw_history = raw_state["history"]
    if not isinstance(raw_history, list):
        raise ValueError(f"action snapshot history for {agent!r} must be a list")
    if len(raw_history) > history_limit:
        raise ValueError(f"action snapshot history for {agent!r} exceeds history_limit")
    history: list[dict] = []
    previous_resolution = 0
    for index, raw_result in enumerate(raw_history):
        result = _validate_result(
            raw_result, agent, sequence, f"action snapshot {agent}.history[{index}]"
        )
        if result["resolution_sequence"] <= previous_resolution:
            raise ValueError(f"action snapshot history for {agent!r} must be ordered")
        previous_resolution = result["resolution_sequence"]
        for item_sequence in (result["decision"]["sequence"], result["resolution_sequence"]):
            if item_sequence in seen_sequences:
                raise ValueError("action snapshot contains duplicate global sequence")
            seen_sequences.add(item_sequence)
            max_sequence = max(max_sequence, item_sequence)
        history.append(result)
    if pending is None and not history:
        raise ValueError(f"action snapshot state for {agent!r} must not be empty")
    return {"pending": pending, "history": history}, max_sequence

class ActionRuntime:
    """Persistent deterministic action selection/result protocol."""

    def __init__(self, history_limit: int = DEFAULT_ACTION_HISTORY_LIMIT) -> None:
        self.history_limit = _positive_int(history_limit, "action history_limit")
        self._sequence = 0
        self._agents: dict[str, dict] = {}

    def has_state(self) -> bool:
        return bool(self._agents)

    def agent_ids(self) -> list[str]:
        return sorted(self._agents)

    def pending(self, agent) -> dict | None:
        agent = normalize_id(agent, "action agent")
        state = self._agents.get(agent)
        return None if state is None or state["pending"] is None else deepcopy(state["pending"])

    def history(self, agent, *, limit: int | None = None) -> list[dict]:
        agent = normalize_id(agent, "action agent")
        records = self._agents.get(agent, {}).get("history", [])
        if limit is None:
            return deepcopy(records)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("action history limit must be a non-negative integer or None")
        if limit == 0:
            return []
        return deepcopy(records[-limit:])

    def current(self, agent) -> dict | None:
        agent = normalize_id(agent, "action agent")
        state = self._agents.get(agent)
        if state is None:
            return None
        return {
            "pending": deepcopy(state["pending"]),
            "last_result": deepcopy(state["history"][-1]) if state["history"] else None,
        }

    def choose(self, agent, affordance_record: dict, scores: dict, *, policy_id="host", context=None) -> dict:
        agent = normalize_id(agent, "action agent")
        state = self._agents.get(agent)
        if state is not None and state["pending"] is not None:
            raise ValueError("agent already has an unresolved action decision")
        affordance_sequence, candidates = _affordance_view(affordance_record, agent)
        score_table = _scores(scores, {item[0] for item in candidates})
        chosen_id = min(score_table, key=lambda item: (-score_table[item], item))
        chosen_capability = next(capability for candidate, capability in candidates if candidate == chosen_id)
        self._sequence += 1
        decision = {
            "decision_id": f"action_decision_{self._sequence}",
            "sequence": self._sequence,
            "agent": agent,
            "affordance_sequence": affordance_sequence,
            "candidate_id": chosen_id,
            "capability": chosen_capability,
            "score": score_table[chosen_id],
            "scores": score_table,
            "policy_id": normalize_id(policy_id, "action policy id"),
            "context": _metadata(context, "action decision context"),
        }
        if state is None:
            state = {"pending": None, "history": []}
            self._agents[agent] = state
        state["pending"] = deepcopy(decision)
        return deepcopy(decision)

    def resolve(self, agent, decision_id, status, *, outcome=None) -> dict:
        agent = normalize_id(agent, "action agent")
        state = self._agents.get(agent)
        if state is None or state["pending"] is None:
            raise ValueError("agent has no unresolved action decision")
        actual_id = normalize_id(decision_id, "action decision id")
        expected_id = state["pending"]["decision_id"]
        if actual_id != expected_id:
            raise ValueError(f"action decision id does not match pending decision: {actual_id!r} != {expected_id!r}")
        self._sequence += 1
        result = {
            "resolution_sequence": self._sequence,
            "decision": deepcopy(state["pending"]),
            "status": _final_status(status),
            "outcome": _metadata(outcome, "action outcome"),
        }
        state["pending"] = None
        state["history"].append(deepcopy(result))
        if len(state["history"]) > self.history_limit:
            del state["history"][: len(state["history"]) - self.history_limit]
        return deepcopy(result)

    def snapshot(self) -> dict:
        return {
            "schema_version": ACTION_SNAPSHOT_SCHEMA_VERSION,
            "history_limit": self.history_limit,
            "sequence": self._sequence,
            "agents": deepcopy({agent: self._agents[agent] for agent in sorted(self._agents)}),
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "ActionRuntime":
        if not isinstance(snapshot, dict):
            raise ValueError("action snapshot must be a dict")
        unknown = set(snapshot) - _SNAPSHOT_KEYS
        if unknown:
            raise ValueError("action snapshot has unsupported keys: " + ", ".join(sorted(unknown)))
        missing = _SNAPSHOT_KEYS - set(snapshot)
        if missing:
            raise ValueError("action snapshot is missing required keys: " + ", ".join(sorted(missing)))
        if snapshot["schema_version"] != ACTION_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"unsupported action snapshot schema version: {snapshot['schema_version']!r}")
        history_limit = _positive_int(snapshot["history_limit"], "action snapshot history_limit")
        sequence = _non_negative_int(snapshot["sequence"], "action snapshot sequence")
        raw_agents = snapshot["agents"]
        if not isinstance(raw_agents, dict):
            raise ValueError("action snapshot agents must be a dict")
        runtime = cls(history_limit=history_limit)
        agents: dict[str, dict] = {}
        seen_agents: set[str] = set()
        seen_sequences: set[int] = set()
        max_sequence = 0
        for raw_agent, raw_state in raw_agents.items():
            agent = normalize_id(raw_agent, "action snapshot agent")
            if agent in seen_agents:
                raise ValueError(f"action snapshot contains duplicate normalized agent: {agent!r}")
            seen_agents.add(agent)
            restored_state, state_max = _restore_agent_state(
                raw_state,
                agent=agent,
                sequence=sequence,
                history_limit=history_limit,
                seen_sequences=seen_sequences,
            )
            agents[agent] = restored_state
            max_sequence = max(max_sequence, state_max)
        if seen_sequences and max_sequence != sequence:
            raise ValueError("latest action event sequence must equal action snapshot sequence")
        if not seen_sequences and sequence != 0:
            raise ValueError("empty action snapshot requires sequence 0")
        runtime._sequence = sequence
        runtime._agents = {agent: agents[agent] for agent in sorted(agents)}
        return runtime
