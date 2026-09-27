"""v1.12-dev Stage-7 latent-state utility / post-hoc capability discovery.

State is frozen before the task battery is revealed.  Post-hoc resolvers may
read already-persisted state but may not replay events, add fields, revise a
schema, or synchronize the baseline from Ghost.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from ghost.api import GhostAPI
from ghost.ids import normalize_id
from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.latent-state-utility.stage7.v1"
VERDICT = "V112_LATENT_STATE_UTILITY_STAGE7_EXPERIMENT_VALID"
_TASK_KEYS = frozenset({"id", "kind", "args"})
_HISTORY_KINDS = frozenset({
    "early_marker_source",
    "relationship_event_count",
    "evidence_sources",
    "belief_revision_count",
    "counterfactual_without_source",
    "deeper_relationship",
    "novel_delegate_choice",
})
_SUPPORTED_KINDS = _HISTORY_KINDS | {
    "recent_marker_source",
    "current_trust_sign",
    "current_belief_dominant",
}
Resolver = Callable[[dict, dict], Any]
TruthResolver = Callable[[list[dict], dict], Any]


def _task(task_id: str, kind: str, **args: Any) -> dict:
    return {
        "id": normalize_id(task_id, "post-hoc task id"),
        "kind": normalize_id(kind, "post-hoc task kind"),
        "args": deepcopy(args),
    }


def reveal_tasks() -> list[dict]:
    return [
        _task("recent_marker_source", "recent_marker_source", token="late_warning"),
        _task("current_trust_sign", "current_trust_sign", source=ex.WITNESS_A),
        _task("current_belief_dominant", "current_belief_dominant", subject=ex.SUBJECT),
        _task("early_marker_source", "early_marker_source", token="early_promise"),
        _task("relationship_event_count", "relationship_event_count", source=ex.WITNESS_A),
        _task("evidence_sources", "evidence_sources", subject=ex.SUBJECT),
        _task("belief_revision_count", "belief_revision_count", subject=ex.SUBJECT),
        _task(
            "counterfactual_without_a",
            "counterfactual_without_source",
            subject=ex.SUBJECT,
            excluded_source=ex.WITNESS_A,
        ),
        _task("deeper_relationship", "deeper_relationship", sources=[ex.WITNESS_A, ex.WITNESS_B]),
        _task(
            "novel_delegate_choice",
            "novel_delegate_choice",
            sources=[ex.WITNESS_A, ex.WITNESS_B],
            duty_threshold=0.8,
        ),
    ]


def _validated_task(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _TASK_KEYS:
        raise ValueError("post-hoc task has invalid shape")
    task_id = normalize_id(raw["id"], "post-hoc task id")
    kind = normalize_id(raw["kind"], "post-hoc task kind")
    if kind not in _SUPPORTED_KINDS:
        raise ValueError(f"unsupported post-hoc task kind: {kind!r}")
    if not isinstance(raw["args"], dict):
        raise ValueError("post-hoc task args must be a dict")
    return {"id": task_id, "kind": kind, "args": deepcopy(raw["args"])}


def _marker_source(records: list[dict], token: str, *, ghost: bool) -> str | None:
    for row in reversed(records):
        if ghost:
            if row.get("kind") == "observation" and row.get("provenance", {}).get("token") == token:
                return row["provenance"].get("source")
        elif row["features"].get("token") == token:
            return row["features"].get("source")
    return None


def _signal_dominant(signals: list[float]) -> str:
    total = sum(signals)
    if total > 1e-12:
        return "hostile"
    if total < -1e-12:
        return "benign"
    return "tie"


def _trust_sign(value: float) -> str:
    if value > 1e-12:
        return "positive"
    if value < -1e-12:
        return "negative"
    return "neutral"


def _full_api(frozen: dict) -> GhostAPI:
    return GhostAPI.from_snapshot(frozen["api"])


def _full_relationship_count(frozen: dict, source: str) -> int:
    maturity = float(_full_api(frozen).get_relationship(ex.AGENT, source)["maturity"])
    return int(round(maturity / 0.01))


def _full_evidence(frozen: dict, subject: str) -> list[dict]:
    api = _full_api(frozen)
    belief = api.get_belief(ex.AGENT, subject)
    if belief is None:
        return []
    by_id = {row["id"]: row for row in ex.ghost_epistemic_records(frozen)}
    return [by_id[evidence_id] for evidence_id in belief["evidence_ids"]]


def _baseline_relationship_count(frozen: dict, source: str) -> int | None:
    if not ex.baseline_history_complete(frozen):
        return None
    return sum(
        row["event"] == "relationship_event" and row["features"].get("source") == source
        for row in ex.baseline_observations(frozen)
    )


def _baseline_evidence(frozen: dict, subject: str) -> list[dict] | None:
    if not ex.baseline_history_complete(frozen):
        return None
    return [
        row for row in ex.baseline_observations(frozen)
        if row["event"] == "evidence_signal" and row["subject"] == subject
    ]


def _full_marker(frozen: dict, args: dict) -> Any:
    return _marker_source(ex.ghost_epistemic_records(frozen), args["token"], ghost=True)


def _baseline_marker(frozen: dict, args: dict) -> Any:
    return _marker_source(ex.baseline_observations(frozen), args["token"], ghost=False)


def _full_trust(frozen: dict, args: dict) -> Any:
    return _trust_sign(float(_full_api(frozen).get_relationship(ex.AGENT, args["source"])["trust"]))


def _baseline_trust(frozen: dict, args: dict) -> Any:
    key = s6._pair_key(ex.AGENT, args["source"])
    return _trust_sign(float(frozen["relationships"].get(key, 0.0)))


def _full_belief(frozen: dict, args: dict) -> Any:
    belief = _full_api(frozen).get_belief(ex.AGENT, args["subject"])
    return None if belief is None else belief["dimensions"]["threat"]["dominant_candidate"]


def _baseline_belief(frozen: dict, args: dict) -> Any:
    dist = frozen["flat"]["beliefs"][args["subject"]]["threat"]
    return sorted(dist.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _full_rel_count(frozen: dict, args: dict) -> Any:
    return _full_relationship_count(frozen, args["source"])


def _baseline_rel_count(frozen: dict, args: dict) -> Any:
    return _baseline_relationship_count(frozen, args["source"])


def _full_sources(frozen: dict, args: dict) -> Any:
    return sorted({row["source"] for row in _full_evidence(frozen, args["subject"])})


def _baseline_sources(frozen: dict, args: dict) -> Any:
    rows = _baseline_evidence(frozen, args["subject"])
    return None if rows is None else sorted({row["features"]["source"] for row in rows})


def _full_revisions(frozen: dict, args: dict) -> Any:
    return sum(
        row.get("kind") == "belief"
        and row.get("holder") == ex.AGENT
        and row.get("subject") == args["subject"]
        and row.get("previous_belief_id") is not None
        for row in ex.ghost_epistemic_records(frozen)
    )


def _baseline_revisions(frozen: dict, args: dict) -> Any:
    rows = _baseline_evidence(frozen, args["subject"])
    return None if rows is None else len(rows)


def _full_counterfactual(frozen: dict, args: dict) -> Any:
    signals = [
        float(row["provenance"]["signal"])
        for row in _full_evidence(frozen, args["subject"])
        if row["source"] != args["excluded_source"]
    ]
    return _signal_dominant(signals)


def _baseline_counterfactual(frozen: dict, args: dict) -> Any:
    rows = _baseline_evidence(frozen, args["subject"])
    if rows is None:
        return None
    signals = [
        float(row["features"]["signal"])
        for row in rows
        if row["features"]["source"] != args["excluded_source"]
    ]
    return _signal_dominant(signals)


def _full_deeper(frozen: dict, args: dict) -> Any:
    sources = list(args["sources"])
    return sorted(sources, key=lambda source: (-_full_relationship_count(frozen, source), source))[0]


def _baseline_counts(frozen: dict, sources: list[str]) -> dict[str, int] | None:
    counts = {source: _baseline_relationship_count(frozen, source) for source in sources}
    return None if any(value is None for value in counts.values()) else counts


def _baseline_deeper(frozen: dict, args: dict) -> Any:
    sources = list(args["sources"])
    counts = _baseline_counts(frozen, sources)
    return None if counts is None else sorted(sources, key=lambda source: (-counts[source], source))[0]


def _full_delegate(frozen: dict, args: dict) -> Any:
    api = _full_api(frozen)
    agent = api.agent(ex.AGENT)
    if agent is None:
        raise RuntimeError("frozen Ghost agent disappeared")
    sources = list(args["sources"])
    if float(agent.values().get("duty", 0.0)) >= float(args["duty_threshold"]):
        return sorted(sources, key=lambda source: (-_full_relationship_count(frozen, source), source))[0]
    return sorted(sources, key=lambda source: (-float(api.get_relationship(ex.AGENT, source)["trust"]), source))[0]


def _baseline_delegate(frozen: dict, args: dict) -> Any:
    sources = list(args["sources"])
    duty = float(frozen["flat"]["decision_state"]["values"].get("duty", 0.0))
    if duty >= float(args["duty_threshold"]):
        counts = _baseline_counts(frozen, sources)
        return None if counts is None else sorted(sources, key=lambda source: (-counts[source], source))[0]
    return sorted(
        sources,
        key=lambda source: (-float(frozen["relationships"].get(s6._pair_key(ex.AGENT, source), 0.0)), source),
    )[0]


_FULL: dict[str, Resolver] = {
    "recent_marker_source": _full_marker,
    "early_marker_source": _full_marker,
    "current_trust_sign": _full_trust,
    "current_belief_dominant": _full_belief,
    "relationship_event_count": _full_rel_count,
    "evidence_sources": _full_sources,
    "belief_revision_count": _full_revisions,
    "counterfactual_without_source": _full_counterfactual,
    "deeper_relationship": _full_deeper,
    "novel_delegate_choice": _full_delegate,
}
_BASELINE: dict[str, Resolver] = {
    "recent_marker_source": _baseline_marker,
    "early_marker_source": _baseline_marker,
    "current_trust_sign": _baseline_trust,
    "current_belief_dominant": _baseline_belief,
    "relationship_event_count": _baseline_rel_count,
    "evidence_sources": _baseline_sources,
    "belief_revision_count": _baseline_revisions,
    "counterfactual_without_source": _baseline_counterfactual,
    "deeper_relationship": _baseline_deeper,
    "novel_delegate_choice": _baseline_delegate,
}


def _answer(frozen: dict, task: dict) -> dict:
    spec = _validated_task(task)
    handlers = _FULL if frozen["mode"] == "full" else _BASELINE
    answer = handlers[spec["kind"]](frozen, spec["args"])
    return {"status": "supported" if answer is not None else "unsupported", "answer": answer}


def _truth_observations(ledger: list[dict]) -> list[dict]:
    return [row for row in ledger if row["kind"] == "observation"]


def _truth_revisions(ledger: list[dict]) -> list[dict]:
    return [row for row in ledger if row["kind"] == "belief_revision" and row["subject"] == ex.SUBJECT]


def _truth_marker(ledger: list[dict], args: dict) -> Any:
    return next(row["source"] for row in reversed(_truth_observations(ledger)) if row["token"] == args["token"])


def _truth_trust(ledger: list[dict], args: dict) -> Any:
    deltas = {"help": 0.20, "deceive": -0.15, "betrayal": -0.80}
    score = sum(
        deltas[row["features"]["relationship_event"]]
        for row in _truth_observations(ledger)
        if row["event"] == "relationship_event" and row["source"] == args["source"]
    )
    return _trust_sign(score)


def _truth_belief(ledger: list[dict], args: dict) -> Any:
    del args
    return _signal_dominant([float(row["signal"]) for row in _truth_revisions(ledger)])


def _truth_rel_count(ledger: list[dict], args: dict) -> Any:
    return sum(
        row["event"] == "relationship_event" and row["source"] == args["source"]
        for row in _truth_observations(ledger)
    )


def _truth_sources(ledger: list[dict], args: dict) -> Any:
    del args
    return sorted({row["source"] for row in _truth_revisions(ledger)})


def _truth_revision_count(ledger: list[dict], args: dict) -> Any:
    del args
    return len(_truth_revisions(ledger))


def _truth_counterfactual(ledger: list[dict], args: dict) -> Any:
    return _signal_dominant([
        float(row["signal"])
        for row in _truth_revisions(ledger)
        if row["source"] != args["excluded_source"]
    ])


def _truth_counts(ledger: list[dict], sources: list[str]) -> dict[str, int]:
    observations = _truth_observations(ledger)
    return {
        source: sum(row["event"] == "relationship_event" and row["source"] == source for row in observations)
        for source in sources
    }


def _truth_deeper(ledger: list[dict], args: dict) -> Any:
    sources = list(args["sources"])
    counts = _truth_counts(ledger, sources)
    return sorted(sources, key=lambda source: (-counts[source], source))[0]


def _truth_delegate(ledger: list[dict], args: dict) -> Any:
    sources = list(args["sources"])
    if s3._decision_state()["values"]["duty"] >= float(args["duty_threshold"]):
        counts = _truth_counts(ledger, sources)
        return sorted(sources, key=lambda source: (-counts[source], source))[0]
    deltas = {"help": 0.20, "deceive": -0.15, "betrayal": -0.80}
    observations = _truth_observations(ledger)
    trusts = {
        source: sum(
            deltas[row["features"]["relationship_event"]]
            for row in observations
            if row["event"] == "relationship_event" and row["source"] == source
        )
        for source in sources
    }
    return sorted(trusts, key=lambda source: (-trusts[source], source))[0]


_TRUTH: dict[str, TruthResolver] = {
    "recent_marker_source": _truth_marker,
    "early_marker_source": _truth_marker,
    "current_trust_sign": _truth_trust,
    "current_belief_dominant": _truth_belief,
    "relationship_event_count": _truth_rel_count,
    "evidence_sources": _truth_sources,
    "belief_revision_count": _truth_revision_count,
    "counterfactual_without_source": _truth_counterfactual,
    "deeper_relationship": _truth_deeper,
    "novel_delegate_choice": _truth_delegate,
}


def _ground_truth(ledger: list[dict], task: dict) -> Any:
    spec = _validated_task(task)
    return _TRUTH[spec["kind"]](ledger, spec["args"])


def _score_tasks(exposure: dict, tasks: list[dict]) -> dict:
    rows = []
    for raw in tasks:
        task = _validated_task(raw)
        expected = _ground_truth(exposure["host_ledger"], task)
        result = _answer(exposure["frozen"], task)
        rows.append({
            "task": task["id"],
            "kind": task["kind"],
            "expected": expected,
            "status": result["status"],
            "answer": result["answer"],
            "correct": result["status"] == "supported" and result["answer"] == expected,
            "history_dependent": task["kind"] in _HISTORY_KINDS,
        })
    return {
        "mode": exposure["frozen"]["mode"],
        "rows": rows,
        "supported": sum(row["status"] == "supported" for row in rows),
        "correct": sum(row["correct"] for row in rows),
        "unsupported": sum(row["status"] == "unsupported" for row in rows),
    }


def _level_result(raw_level: dict) -> dict:
    cfg = ex.level(raw_level)
    full_exposure = ex.blind_exposure(cfg, "full")
    baseline_exposure = ex.blind_exposure(cfg, "baseline")
    tasks = reveal_tasks()
    full = _score_tasks(full_exposure, tasks)
    baseline = _score_tasks(baseline_exposure, tasks)
    full_frozen, baseline_frozen = full_exposure["frozen"], baseline_exposure["frozen"]
    return {
        "level": cfg,
        "task_count": len(tasks),
        "full": full,
        "baseline": baseline,
        "result_divergences": sum(
            left["answer"] != right["answer"] or left["status"] != right["status"]
            for left, right in zip(full["rows"], baseline["rows"])
        ),
        "state": {
            "ghost_perception_history_complete": ex.token_in_perception(full_frozen, "life_begin"),
            "ghost_epistemic_ledger_complete": ex.token_in_epistemic(full_frozen, "life_begin") and ex.token_in_epistemic(full_frozen, "life_end"),
            "baseline_observation_history_complete": ex.baseline_history_complete(baseline_frozen),
            "full_snapshot_bytes": full_exposure["snapshot_bytes"],
            "baseline_snapshot_bytes": baseline_exposure["snapshot_bytes"],
            "same_external_exposure": full_exposure["host_ledger"] == baseline_exposure["host_ledger"],
        },
    }


def _outcome(full_correct: int, baseline_correct: int) -> str:
    if full_correct > baseline_correct:
        return "directional_ghost_latent_state_advantage"
    if baseline_correct > full_correct:
        return "directional_baseline_latent_state_advantage"
    return "latent_state_parity_on_revealed_tasks"


def _overflow_recovery(entries: list[dict]) -> bool:
    for entry in entries:
        state = entry["state"]
        if state["ghost_perception_history_complete"]:
            return False
        if not state["ghost_epistemic_ledger_complete"]:
            return False
        if state["baseline_observation_history_complete"]:
            return False
    return True


def run_matrix(levels: list[dict] | None = None) -> dict:
    selected = ex.canonical_levels() if levels is None else [ex.level(item) for item in deepcopy(levels)]
    if not selected:
        raise ValueError("latent-state matrix requires at least one level")
    entries = [_level_result(item) for item in selected]
    tasks_per_level = entries[0]["task_count"]
    if any(entry["task_count"] != tasks_per_level for entry in entries):
        raise RuntimeError("Stage-7 task count changed between levels")
    totals = {
        mode: {
            "correct": sum(entry[mode]["correct"] for entry in entries),
            "supported": sum(entry[mode]["supported"] for entry in entries),
            "unsupported": sum(entry[mode]["unsupported"] for entry in entries),
        }
        for mode in ("full", "baseline")
    }
    return {
        "levels": entries,
        "tasks_per_level": tasks_per_level,
        "scored_tasks_per_contender": tasks_per_level * len(entries),
        "totals": totals,
        "comparative_outcome": _outcome(totals["full"]["correct"], totals["baseline"]["correct"]),
        "control_level_parity": entries[0]["full"]["correct"] == entries[0]["baseline"]["correct"] == tasks_per_level,
        "overflow_cross_layer_recovery": _overflow_recovery(entries[1:]),
        "same_external_exposure": all(entry["state"]["same_external_exposure"] for entry in entries),
    }


def run_experiment() -> dict:
    matrix = run_matrix()
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "matrix": matrix,
        "constraints": {
            "state_frozen_before_task_reveal": True,
            "history_replay": False,
            "schema_changes_after_reveal": False,
            "baseline_state_redesign": False,
            "ghost_state_redesign": False,
            "posthoc_queries_read_only": True,
        },
        "claim_boundary": (
            "Stage 7 measures latent option value on one pre-registered blind-exposure battery. "
            "A Ghost advantage here means its already-existing persisted state answered more newly revealed tasks after history overflow without replay or schema redesign. "
            "It does not establish general intelligence, realism, consciousness, universal game superiority, or that every extra Ghost byte is necessary."
        ),
    }
