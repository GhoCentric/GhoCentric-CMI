"""v1.12-dev Stage-8 equal-storage blind-baseline adjudication.

Full Ghost and the compact baseline are frozen exactly as in Stage 7.  A third
contender adds a task-blind append-only observation archive whose *allocated*
byte budget is preregistered from Stage-7 Full-Ghost snapshot sizes.  Tasks are
revealed only after all contender state is frozen.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from ghost_research import v112_equal_budget_archive_stage8 as ar
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.equal-budget-adjudication.stage8.v1"
VERDICT = "V112_EQUAL_BUDGET_ADJUDICATION_STAGE8_EXPERIMENT_VALID"
_HISTORY_KINDS = frozenset({
    "early_marker_source",
    "relationship_event_count",
    "evidence_sources",
    "belief_revision_count",
    "counterfactual_without_source",
    "deeper_relationship",
    "novel_delegate_choice",
})
ArchiveResolver = Callable[[dict, dict], tuple[Any, int]]


def _rows(frozen: dict) -> list[dict]:
    return ar.records(frozen)


def _marker(frozen: dict, args: dict) -> tuple[Any, int]:
    rows = _rows(frozen)
    scanned = 0
    for row in reversed(rows):
        scanned += 1
        if row.get("token") == args["token"]:
            return row.get("source"), scanned
    return None, scanned


def _relationship_rows(frozen: dict, source: str) -> tuple[list[dict], int]:
    rows = _rows(frozen)
    selected = []
    for row in rows:
        if row.get("event") == "relationship_event" and row.get("source") == source:
            selected.append(row)
    return selected, len(rows)


def _relationship_count(frozen: dict, args: dict) -> tuple[Any, int]:
    selected, scanned = _relationship_rows(frozen, args["source"])
    return len(selected), scanned


def _evidence_rows(frozen: dict, subject: str) -> tuple[list[dict], int]:
    rows = _rows(frozen)
    selected = [row for row in rows if row.get("event") == "evidence_signal" and row.get("subject") == subject]
    return selected, len(rows)


def _sources(frozen: dict, args: dict) -> tuple[Any, int]:
    selected, scanned = _evidence_rows(frozen, args["subject"])
    return sorted({row["source"] for row in selected}), scanned


def _revisions(frozen: dict, args: dict) -> tuple[Any, int]:
    selected, scanned = _evidence_rows(frozen, args["subject"])
    return len(selected), scanned


_signal_dominant = s7._signal_dominant


def _counterfactual(frozen: dict, args: dict) -> tuple[Any, int]:
    selected, scanned = _evidence_rows(frozen, args["subject"])
    signals = [
        float(row["features"]["signal"])
        for row in selected
        if row["source"] != args["excluded_source"]
    ]
    return _signal_dominant(signals), scanned


def _counts(frozen: dict, sources: list[str]) -> tuple[dict[str, int], int]:
    rows = _rows(frozen)
    wanted = set(sources)
    counts = {source: 0 for source in sources}
    for row in rows:
        if row.get("event") == "relationship_event" and row.get("source") in wanted:
            counts[row["source"]] += 1
    return counts, len(rows)


def _deeper(frozen: dict, args: dict) -> tuple[Any, int]:
    sources = list(args["sources"])
    counts, scanned = _counts(frozen, sources)
    return sorted(sources, key=lambda source: (-counts[source], source))[0], scanned


def _delegate(frozen: dict, args: dict) -> tuple[Any, int]:
    sources = list(args["sources"])
    duty = float(frozen["compact"]["flat"]["decision_state"]["values"].get("duty", 0.0))
    if duty >= float(args["duty_threshold"]):
        counts, scanned = _counts(frozen, sources)
        return sorted(sources, key=lambda source: (-counts[source], source))[0], scanned
    relationships = frozen["compact"]["relationships"]
    answer = sorted(
        sources,
        key=lambda source: (-float(relationships.get(s6._pair_key(ex.AGENT, source), 0.0)), source),
    )[0]
    return answer, 0


_ARCHIVE: dict[str, ArchiveResolver] = {
    "early_marker_source": _marker,
    "relationship_event_count": _relationship_count,
    "evidence_sources": _sources,
    "belief_revision_count": _revisions,
    "counterfactual_without_source": _counterfactual,
    "deeper_relationship": _deeper,
    "novel_delegate_choice": _delegate,
}


def _archive_answer(frozen: dict, task: dict) -> dict:
    spec = s7._validated_task(task)
    compact = s7._answer(frozen["compact"], spec)
    if compact["status"] == "supported":
        return {"status": "supported", "answer": compact["answer"], "access": "compact_state", "records_examined": 0}
    if spec["kind"] not in _ARCHIVE:
        return {"status": "unsupported", "answer": None, "access": "unsupported", "records_examined": 0}
    answer, scanned = _ARCHIVE[spec["kind"]](frozen, spec["args"])
    return {
        "status": "supported" if answer is not None else "unsupported",
        "answer": answer,
        "access": "generic_archive_scan",
        "records_examined": scanned,
    }


def _score_archive(exposure: dict, tasks: list[dict]) -> dict:
    rows = []
    for raw in tasks:
        task = s7._validated_task(raw)
        expected = s7._ground_truth(exposure["host_ledger"], task)
        result = _archive_answer(exposure["archive_frozen"], task)
        rows.append({
            "task": task["id"],
            "kind": task["kind"],
            "expected": expected,
            "status": result["status"],
            "answer": result["answer"],
            "correct": result["status"] == "supported" and result["answer"] == expected,
            "access": result["access"],
            "records_examined": result["records_examined"],
        })
    return {
        "mode": "archive_baseline",
        "rows": rows,
        "supported": sum(row["status"] == "supported" for row in rows),
        "correct": sum(row["correct"] for row in rows),
        "unsupported": sum(row["status"] == "unsupported" for row in rows),
        "archive_scans": sum(row["access"] == "generic_archive_scan" for row in rows),
        "records_examined": sum(row["records_examined"] for row in rows),
    }


def _archive_exposure(raw_level: dict) -> dict:
    cfg = ex.level(raw_level)
    compact = ex.blind_exposure(cfg, "baseline")
    frozen = ar.freeze_archive(cfg["id"], compact["frozen"], compact["host_ledger"])
    return {
        "level": cfg,
        "frozen": compact["frozen"],
        "archive_frozen": frozen,
        "host_ledger": deepcopy(compact["host_ledger"]),
        "compact_snapshot_bytes": compact["snapshot_bytes"],
    }


def _level_result(raw_level: dict) -> dict:
    cfg = ex.level(raw_level)
    full_exposure = ex.blind_exposure(cfg, "full")
    compact_exposure = ex.blind_exposure(cfg, "baseline")
    archive_exposure = _archive_exposure(cfg)
    if not (full_exposure["host_ledger"] == compact_exposure["host_ledger"] == archive_exposure["host_ledger"]):
        raise RuntimeError("Stage-8 contenders did not receive identical blind exposure")
    tasks = s7.reveal_tasks()
    full = s7._score_tasks(full_exposure, tasks)
    compact = s7._score_tasks(compact_exposure, tasks)
    archive = _score_archive(archive_exposure, tasks)
    archive_frozen = archive_exposure["archive_frozen"]
    return {
        "level": cfg,
        "task_count": len(tasks),
        "full": full,
        "compact": compact,
        "archive": archive,
        "state": {
            "full_snapshot_bytes": full_exposure["snapshot_bytes"],
            "compact_snapshot_bytes": compact_exposure["snapshot_bytes"],
            "archive_allocated_budget_bytes": archive_frozen["allocated_budget_bytes"],
            "archive_used_bytes": archive_frozen["used_bytes"],
            "archive_headroom_bytes": archive_frozen["headroom_bytes"],
            "archive_record_count": len(ar.records(archive_frozen)),
            "archive_within_full_budget": archive_frozen["used_bytes"] <= archive_frozen["allocated_budget_bytes"],
        },
    }


def _comparative_outcome(totals: dict) -> str:
    full = totals["full"]["correct"]
    compact = totals["compact"]["correct"]
    archive = totals["archive"]["correct"]
    if full > archive:
        return "structured_state_advantage_beyond_equal_budget_archive"
    if archive > full:
        return "generic_archive_outperforms_full_ghost_on_revealed_tasks"
    if full == archive and full > compact:
        return "generic_archive_recovers_stage7_gap"
    return "three_way_parity_on_revealed_tasks"


def run_matrix(levels: list[dict] | None = None) -> dict:
    selected = ex.canonical_levels() if levels is None else [ex.level(item) for item in deepcopy(levels)]
    if not selected:
        raise ValueError("Stage-8 matrix requires at least one level")
    entries = [_level_result(item) for item in selected]
    tasks_per_level = entries[0]["task_count"]
    if any(entry["task_count"] != tasks_per_level for entry in entries):
        raise RuntimeError("Stage-8 task count changed between levels")
    totals = {
        mode: {
            "correct": sum(entry[mode]["correct"] for entry in entries),
            "supported": sum(entry[mode]["supported"] for entry in entries),
            "unsupported": sum(entry[mode]["unsupported"] for entry in entries),
        }
        for mode in ("full", "compact", "archive")
    }
    return {
        "levels": entries,
        "tasks_per_level": tasks_per_level,
        "scored_tasks_per_contender": tasks_per_level * len(entries),
        "totals": totals,
        "comparative_outcome": _comparative_outcome(totals),
        "same_external_exposure": True,
        "archive_budget_valid": all(entry["state"]["archive_within_full_budget"] for entry in entries),
        "archive_taskblind_storage": True,
        "posthoc_archive_reconstruction_read_only": True,
    }


def run_experiment() -> dict:
    matrix = run_matrix()
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "matrix": matrix,
        "constraints": {
            "state_frozen_before_task_reveal": True,
            "archive_schema_fixed_before_task_reveal": True,
            "archive_records_external_observations_verbatim": True,
            "archive_derived_state_before_reveal": False,
            "archive_budget_source": "frozen Stage-7 Full-Ghost snapshot sizes",
            "archive_padding": False,
            "posthoc_archive_queries_read_only": True,
            "compact_baseline_redesign": False,
            "ghost_redesign": False,
        },
        "claim_boundary": (
            "Stage 8 distinguishes information-retention budget from structured-state value on the frozen Stage-7 task battery. "
            "An equal-budget generic archive may scan and reconstruct from task-blind raw observations after reveal, but may not mutate frozen state or use task-specific pre-reveal fields. "
            "Parity with Ghost would show that generic retention is sufficient for this battery; a Ghost advantage would require further attribution before broader claims."
        ),
    }
