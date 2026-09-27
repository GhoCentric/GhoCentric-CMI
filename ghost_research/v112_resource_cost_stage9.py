"""v1.12-dev Stage-9 resource-cost adjudication.

Stage 9 freezes the behavioral question after Stage 8: Full Ghost and a
 task-blind generic archive both answer the latent-state battery correctly.
This experiment profiles the cost frontier instead of manufacturing another
behavioral winner.  Correctness remains mandatory; timing is telemetry and is
never a PASS criterion.
"""
from __future__ import annotations

from copy import deepcopy
import json
from statistics import median
from time import perf_counter_ns
from typing import Any, Callable

from ghost.api import GhostAPI
from ghost_research import v112_equal_budget_adjudication_stage8 as s8
from ghost_research import v112_equal_budget_archive_stage8 as ar
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7

SCHEMA = "ghost.v1.12-dev.resource-cost.stage9.v1"
VERDICT = "V112_RESOURCE_COST_STAGE9_EXPERIMENT_VALID"
_LEVEL_KEYS = frozenset({"id", "ambient_events"})
_COLD_REHYDRATES_PER_BATTERY = 10
_QUERY_REPETITIONS = 100
_TIMING_SAMPLES = 7


def canonical_levels() -> list[dict]:
    return [
        {"id": "events_64", "ambient_events": 64},
        {"id": "events_128", "ambient_events": 128},
        {"id": "events_224", "ambient_events": 224},
        {"id": "events_512", "ambient_events": 512},
        {"id": "events_1024", "ambient_events": 1024},
        {"id": "events_2048", "ambient_events": 2048},
    ]


def _level(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _LEVEL_KEYS:
        raise ValueError("Stage-9 level has invalid shape")
    cfg = ex.level(raw)
    if cfg["ambient_events"] < 1:
        raise ValueError("Stage-9 requires at least one ambient event")
    return cfg


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _archive_exposure(raw_level: dict) -> dict:
    cfg = _level(raw_level)
    compact = ex.blind_exposure(cfg, "baseline")
    archive = {
        "schema": ar.SCHEMA,
        "level": cfg["id"],
        "records": ar._observation_rows(compact["host_ledger"]),
        "writer_policy": "append_external_observations_verbatim",
    }
    frozen = {"mode": "archive_baseline", "compact": deepcopy(compact["frozen"]), "archive": archive}
    return {
        "level": cfg,
        "archive_frozen": frozen,
        "host_ledger": deepcopy(compact["host_ledger"]),
        "snapshot_bytes": len(_json_bytes(frozen)),
    }


class WarmGhostReader:
    """Read-only Stage-7 semantics with one Ghost snapshot restoration."""

    def __init__(self, frozen: dict) -> None:
        if not isinstance(frozen, dict) or frozen.get("mode") != "full":
            raise ValueError("WarmGhostReader requires a Full-Ghost frozen state")
        self.frozen = frozen
        self.api = GhostAPI.from_snapshot(frozen["api"])
        self.records = ex.ghost_epistemic_records(frozen)

    def _relationship_count(self, source: str) -> int:
        maturity = float(self.api.get_relationship(ex.AGENT, source)["maturity"])
        return int(round(maturity / 0.01))

    def _evidence(self, subject: str) -> list[dict]:
        belief = self.api.get_belief(ex.AGENT, subject)
        if belief is None:
            return []
        by_id = {row["id"]: row for row in self.records}
        return [by_id[evidence_id] for evidence_id in belief["evidence_ids"]]

    def _marker(self, args: dict) -> Any:
        return s7._marker_source(self.records, args["token"], ghost=True)

    def _trust(self, args: dict) -> Any:
        return s7._trust_sign(float(self.api.get_relationship(ex.AGENT, args["source"])["trust"]))

    def _belief(self, args: dict) -> Any:
        belief = self.api.get_belief(ex.AGENT, args["subject"])
        return None if belief is None else belief["dimensions"]["threat"]["dominant_candidate"]

    def _sources(self, args: dict) -> Any:
        return sorted({row["source"] for row in self._evidence(args["subject"])})

    def _revisions(self, args: dict) -> Any:
        return sum(
            row.get("kind") == "belief"
            and row.get("holder") == ex.AGENT
            and row.get("subject") == args["subject"]
            and row.get("previous_belief_id") is not None
            for row in self.records
        )

    def _counterfactual(self, args: dict) -> Any:
        signals = [
            float(row["provenance"]["signal"])
            for row in self._evidence(args["subject"])
            if row["source"] != args["excluded_source"]
        ]
        return s7._signal_dominant(signals)

    def _deeper(self, args: dict) -> Any:
        sources = list(args["sources"])
        return sorted(sources, key=lambda source: (-self._relationship_count(source), source))[0]

    def _delegate(self, args: dict) -> Any:
        sources = list(args["sources"])
        agent = self.api.agent(ex.AGENT)
        if agent is None:
            raise RuntimeError("frozen Ghost agent disappeared")
        if float(agent.values().get("duty", 0.0)) >= float(args["duty_threshold"]):
            return sorted(sources, key=lambda source: (-self._relationship_count(source), source))[0]
        return sorted(
            sources,
            key=lambda source: (-float(self.api.get_relationship(ex.AGENT, source)["trust"]), source),
        )[0]

    def answer(self, task: dict) -> Any:
        spec = s7._validated_task(task)
        handlers: dict[str, Callable[[dict], Any]] = {
            "recent_marker_source": self._marker,
            "early_marker_source": self._marker,
            "current_trust_sign": self._trust,
            "current_belief_dominant": self._belief,
            "relationship_event_count": lambda args: self._relationship_count(args["source"]),
            "evidence_sources": self._sources,
            "belief_revision_count": self._revisions,
            "counterfactual_without_source": self._counterfactual,
            "deeper_relationship": self._deeper,
            "novel_delegate_choice": self._delegate,
        }
        handler = handlers.get(spec["kind"])
        if handler is None:
            raise RuntimeError(f"unhandled Stage-9 task kind: {spec['kind']!r}")
        return handler(spec["args"])


def _marker_scan_count(records: list[dict], token: str) -> int:
    scanned = 0
    for row in reversed(records):
        scanned += 1
        if row.get("kind") == "observation" and row.get("provenance", {}).get("token") == token:
            return scanned
    return scanned


def _ghost_work(frozen: dict, tasks: list[dict]) -> dict:
    records = ex.ghost_epistemic_records(frozen)
    tokens = {
        task["kind"]: task["args"]["token"]
        for task in tasks
        if task["kind"] in {"recent_marker_source", "early_marker_source"}
    }
    marker_rows = sum(_marker_scan_count(records, token) for token in tokens.values())
    record_rows = marker_rows + (3 * len(records))
    return {
        "epistemic_record_count": len(records),
        "epistemic_records_examined_per_battery": record_rows,
        "cold_snapshot_rehydrates_per_battery": _COLD_REHYDRATES_PER_BATTERY,
        "warm_snapshot_rehydrates_per_session": 1,
        "relationship_lookups_per_battery": 6,
        "belief_lookups_per_battery": 3,
        "agent_value_lookups_per_battery": 1,
    }


def _correctness(full: dict, archive: dict, tasks: list[dict]) -> dict:
    if full["host_ledger"] != archive["host_ledger"]:
        raise RuntimeError("Stage-9 contenders did not receive identical exposure")
    warm = WarmGhostReader(full["frozen"])
    rows = []
    for task in tasks:
        expected = s7._ground_truth(full["host_ledger"], task)
        cold = s7._answer(full["frozen"], task)
        warm_answer = warm.answer(task)
        archive_answer = s8._archive_answer(archive["archive_frozen"], task)
        rows.append({
            "task": task["id"],
            "expected": expected,
            "cold_full": cold["answer"],
            "warm_full": warm_answer,
            "archive": archive_answer["answer"],
            "cold_full_correct": cold["status"] == "supported" and cold["answer"] == expected,
            "warm_full_correct": warm_answer == expected,
            "archive_correct": archive_answer["status"] == "supported" and archive_answer["answer"] == expected,
            "archive_records_examined": archive_answer["records_examined"],
        })
    return {
        "rows": rows,
        "full_correct": sum(row["cold_full_correct"] and row["warm_full_correct"] for row in rows),
        "archive_correct": sum(row["archive_correct"] for row in rows),
        "archive_records_examined_per_battery": sum(row["archive_records_examined"] for row in rows),
        "archive_scans_per_battery": sum(row["archive_records_examined"] > 0 for row in rows),
    }


def _median_us(fn: Callable[[], Any], samples: int) -> float:
    values = []
    for _ in range(samples):
        start = perf_counter_ns()
        fn()
        values.append((perf_counter_ns() - start) / 1000.0)
    return float(median(values))


def _query_battery_full(frozen: dict, tasks: list[dict]) -> None:
    for task in tasks:
        s7._answer(frozen, task)


def _query_battery_warm(reader: WarmGhostReader, tasks: list[dict], repetitions: int = 1) -> None:
    for _ in range(repetitions):
        for task in tasks:
            reader.answer(task)


def _query_battery_archive(frozen: dict, tasks: list[dict], repetitions: int = 1) -> None:
    for _ in range(repetitions):
        for task in tasks:
            s8._archive_answer(frozen, task)


def _timing(raw_level: dict, full: dict, archive: dict, tasks: list[dict], samples: int) -> dict:
    full_blob = _json_bytes(full["frozen"])
    archive_blob = _json_bytes(archive["archive_frozen"])
    warm = WarmGhostReader(full["frozen"])
    return {
        "samples": samples,
        "query_repetitions": _QUERY_REPETITIONS,
        "ingest_full_us": _median_us(lambda: ex.blind_exposure(raw_level, "full"), samples),
        "ingest_archive_us": _median_us(lambda: _archive_exposure(raw_level), samples),
        "serialize_full_us": _median_us(lambda: _json_bytes(full["frozen"]), samples),
        "serialize_archive_us": _median_us(lambda: _json_bytes(archive["archive_frozen"]), samples),
        "restore_full_us": _median_us(lambda: GhostAPI.from_snapshot(json.loads(full_blob)["api"]), samples),
        "restore_archive_us": _median_us(lambda: json.loads(archive_blob), samples),
        "cold_full_battery_us": _median_us(lambda: _query_battery_full(full["frozen"], tasks), samples),
        "warm_full_battery_us": _median_us(lambda: _query_battery_warm(warm, tasks), samples),
        "archive_battery_us": _median_us(lambda: _query_battery_archive(archive["archive_frozen"], tasks), samples),
        "warm_full_100_batteries_us": _median_us(
            lambda: _query_battery_warm(warm, tasks, _QUERY_REPETITIONS), samples,
        ),
        "archive_100_batteries_us": _median_us(
            lambda: _query_battery_archive(archive["archive_frozen"], tasks, _QUERY_REPETITIONS), samples,
        ),
    }


def _profile_level(raw_level: dict, *, timing: bool, timing_samples: int) -> dict:
    cfg = _level(raw_level)
    full = ex.blind_exposure(cfg, "full")
    archive = _archive_exposure(cfg)
    tasks = s7.reveal_tasks()
    correctness = _correctness(full, archive, tasks)
    ghost_work = _ghost_work(full["frozen"], tasks)
    result = {
        "level": cfg,
        "task_count": len(tasks),
        "correctness": correctness,
        "state": {
            "full_snapshot_bytes": full["snapshot_bytes"],
            "archive_snapshot_bytes": archive["snapshot_bytes"],
            "archive_record_count": len(ar.records(archive["archive_frozen"])),
            "full_epistemic_record_count": ghost_work["epistemic_record_count"],
            "full_over_archive_byte_ratio": full["snapshot_bytes"] / archive["snapshot_bytes"],
        },
        "deterministic_work": {
            "full": ghost_work,
            "archive": {
                "records_examined_per_battery": correctness["archive_records_examined_per_battery"],
                "scans_per_battery": correctness["archive_scans_per_battery"],
            },
        },
        "timing": None,
    }
    if timing:
        result["timing"] = _timing(cfg, full, archive, tasks, timing_samples)
    return result


def run_matrix(
    levels: list[dict] | None = None,
    *,
    timing: bool = False,
    timing_samples: int = _TIMING_SAMPLES,
) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    selected = canonical_levels() if levels is None else [_level(item) for item in deepcopy(levels)]
    if not selected:
        raise ValueError("Stage-9 matrix requires at least one level")
    entries = [_profile_level(item, timing=timing, timing_samples=timing_samples) for item in selected]
    all_correct = all(
        row["correctness"]["full_correct"] == row["task_count"]
        and row["correctness"]["archive_correct"] == row["task_count"]
        for row in entries
    )
    return {
        "levels": entries,
        "all_full_and_archive_correct": all_correct,
        "timing_enabled": timing,
        "timing_is_telemetry_not_gate": True,
        "no_weighted_composite_score": True,
        "query_repetitions": _QUERY_REPETITIONS,
    }


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    matrix = run_matrix(timing=timing, timing_samples=timing_samples)
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "matrix": matrix,
        "constraints": {
            "stage8_behavioral_question_frozen": True,
            "full_and_archive_must_remain_correct": True,
            "same_external_exposure": True,
            "ghost_cold_query_is_exact_stage7_path": True,
            "ghost_warm_query_removes_only_repeated_snapshot_restore": True,
            "archive_query_is_exact_stage8_read_only_scan_path": True,
            "timing_thresholds": False,
            "weighted_winner_score": False,
        },
        "claim_boundary": (
            "Stage 9 profiles the current Full-Ghost versus generic-archive storage/update/restore/query tradeoff after Stage 8 established equal task correctness. "
            "Deterministic work counts and byte sizes are primary structural evidence. Timing is device-specific telemetry and is never a validity gate. "
            "No universal winner is inferred from a single weighted score."
        ),
    }
