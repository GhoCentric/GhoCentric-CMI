"""Live incremental compact-state adjudication for Stage 9C."""
from __future__ import annotations

from copy import deepcopy
from time import perf_counter_ns
from typing import Any

from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_incremental_compact_codec_stage9c as inc
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_resource_cost_stage9 as s9
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = inc.SCHEMA
VERDICT = "V112_INCREMENTAL_COMPACT_STAGE9C_EXPERIMENT_VALID"
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)
_TIMING_SAMPLES = 5
_QUERY_REPETITIONS = 100

class LiveExposure:
    """Replays the frozen Stage-7 life while incrementally maintaining the sidecar."""

    def __init__(self, raw_level: dict) -> None:
        self.level = ex.level(raw_level)
        self.contender = s6.StructuralContender("full", 3)
        self.ledger: list[dict] = []
        self.sidecar = inc.IncrementalCompactSidecar()
        self._cursor = 0
        self.sidecar_update_ns = 0
        self.ghost_update_ns = 0
        self.archive_append_ns = 0
        self.archive_rows: list[dict] = []
        self._sync_records()
        for source in self.contender.source_ids:
            self.sidecar.update_relationship(ex.AGENT, source, self.contender.api.get_relationship(ex.AGENT, source))
        self.sidecar.set_agent_values(ex.AGENT, self.contender.agents[ex.AGENT].values())

    def _sync_records(self) -> None:
        records = self.contender.api.epistemic._records  # research-only append cursor over authoritative runtime
        start = perf_counter_ns()
        for record in records[self._cursor:]:
            self.sidecar.ingest_record(record)
        self._cursor = len(records)
        self.sidecar_update_ns += perf_counter_ns() - start

    def _sync_archive(self, before: int) -> None:
        start = perf_counter_ns()
        for row in self.ledger[before:]:
            if row["kind"] == "observation":
                self.archive_rows.append(deepcopy(row))
        self.archive_append_ns += perf_counter_ns() - start

    def _run(self, fn, *args, relationship_source: str | None = None, **kwargs) -> None:
        before = len(self.ledger)
        start = perf_counter_ns()
        fn(self.contender, self.ledger, self.level["id"], *args, **kwargs)
        self.ghost_update_ns += perf_counter_ns() - start
        self._sync_records()
        self._sync_archive(before)
        if relationship_source is not None:
            self.sidecar.update_relationship(
                ex.AGENT, relationship_source,
                self.contender.api.get_relationship(ex.AGENT, relationship_source),
            )

    def observe(self, event: str, *, source: str, subject: str, token: str, features: dict | None = None) -> None:
        self._run(ex._observe, event, source=source, subject=subject, token=token, features=features)

    def relationship(self, source: str, event: str) -> None:
        self._run(ex._relationship, source, event, relationship_source=source)

    def evidence(self, source: str, signal: float, token: str) -> None:
        self._run(ex._evidence, source, signal, token)

    def restart_sidecar(self) -> None:
        self.sidecar = inc.IncrementalCompactSidecar(self.sidecar.snapshot())

    def run(self, *, restart_points: set[int] | None = None) -> dict:
        restart_points = set(restart_points or ())
        self.observe("life_begin", source="world", subject=ex.SUBJECT, token="life_begin")
        self.observe("promise_made", source=ex.WITNESS_A, subject=ex.AGENT, token="early_promise", features={"promise": "return_help"})
        for event in ("help", "help", "help", "help", "deceive"):
            self.relationship(ex.WITNESS_A, event)
        for event in ("help", "deceive", "help"):
            self.relationship(ex.WITNESS_B, event)
        self.evidence(ex.WITNESS_A, 1.0, "evidence_a")
        self.evidence(ex.WITNESS_B, 0.2, "evidence_b")
        self.evidence(ex.WITNESS_C, -0.8, "evidence_c")
        for index in range(self.level["ambient_events"]):
            self.observe(
                f"ambient_{index % 9}", source="world", subject=f"ambient_subject_{index % 11}",
                token=f"ambient_token_{index:03d}", features={"ordinal": index, "tone": f"tone_{index % 5}"},
            )
            if index in restart_points:
                self.restart_sidecar()
        self.evidence(ex.WITNESS_B, 0.1, "evidence_b_recent")
        self.observe("late_warning", source=ex.WITNESS_C, subject=ex.SUBJECT, token="late_warning", features={"warning": "north_gate"})
        self.observe("life_end", source="world", subject=ex.SUBJECT, token="life_end")
        frozen = ex._freeze(self.contender)
        compact = self.sidecar.compact_full_snapshot(frozen)
        return {
            "level": deepcopy(self.level), "frozen": frozen, "compact": compact,
            "host_ledger": deepcopy(self.ledger), "archive_rows": deepcopy(self.archive_rows),
            "timing_ns": {
                "ghost_updates": self.ghost_update_ns, "sidecar_updates": self.sidecar_update_ns,
                "archive_appends": self.archive_append_ns,
            },
        }


def _median_us(fn, samples: int) -> float:
    return s9._median_us(fn, samples)


def _answers(live: dict, tasks: list[dict]) -> list[dict]:
    return [
        {
            "task": task["id"],
            "expected": s7._ground_truth(live["host_ledger"], task),
            "incremental": LiveExposureAnswer.answer(live, task),
        }
        for task in tasks
    ]


def _storage(live: dict, sidecar: inc.IncrementalCompactSidecar, archive: dict) -> dict:
    compact_bytes = inc.json_bytes(live["compact"])
    index_bytes = inc.json_bytes(sidecar.index_payload())
    return {
        "current_snapshot_bytes": inc.json_bytes(live["frozen"]),
        "incremental_compact_snapshot_bytes": compact_bytes,
        "incremental_index_payload_bytes": index_bytes,
        "incremental_compact_plus_index_bytes": compact_bytes + index_bytes,
        "archive_snapshot_bytes": archive["snapshot_bytes"],
    }


def _write_work(sidecar: inc.IncrementalCompactSidecar, restarts: set[int]) -> dict:
    return {
        "records_ingested": sidecar.records_ingested,
        "observation_rows": len(sidecar.observations.rows),
        "other_records": len(sidecar.other_records),
        "sidecar_restarts": len(restarts),
        "no_full_rebuilds": True,
    }


def _timing(live: dict, sidecar: inc.IncrementalCompactSidecar, archive: dict, tasks: list[dict], samples: int) -> dict:
    return {
        "samples": samples,
        "incremental_query_battery_us": _median_us(lambda: s9a._battery_indexed(sidecar, tasks), samples),
        "incremental_100_batteries_us": _median_us(lambda: s9a._battery_indexed(sidecar, tasks, _QUERY_REPETITIONS), samples),
        "archive_query_battery_us": _median_us(lambda: s9._query_battery_archive(archive["archive_frozen"], tasks), samples),
        "sidecar_restart_us": _median_us(lambda: inc.IncrementalCompactSidecar(sidecar.snapshot()), samples),
        "expand_us": _median_us(lambda: inc.IncrementalCompactSidecar.expand_full_snapshot(live["compact"]), samples),
        "ghost_update_us_total": live["timing_ns"]["ghost_updates"] / 1000.0,
        "sidecar_update_us_total": live["timing_ns"]["sidecar_updates"] / 1000.0,
        "archive_append_us_total": live["timing_ns"]["archive_appends"] / 1000.0,
    }


def _profile_level(level: dict, *, timing: bool, samples: int) -> dict:
    restarts = {level["ambient_events"] // 3, (2 * level["ambient_events"]) // 3}
    live = LiveExposure(level).run(restart_points=restarts)
    reference = ex.blind_exposure(level, "full")
    if live["host_ledger"] != reference["host_ledger"] or live["frozen"] != reference["frozen"]:
        raise RuntimeError("incremental live exposure drifted from frozen Stage-7 reference")
    if inc.IncrementalCompactSidecar.expand_full_snapshot(live["compact"]) != live["frozen"]:
        raise RuntimeError("incremental compact state failed exact full-snapshot reconstruction")
    tasks = s7.reveal_tasks()
    sidecar = LiveExposureAnswer.sidecar(live)
    archive = s9._archive_exposure(level)
    answers = _answers(live, tasks)
    result = {
        "level": deepcopy(level), "exact_reference_match": True, "exact_roundtrip": True,
        "all_correct": all(row["incremental"] == row["expected"] for row in answers),
        "answers": answers, "storage": _storage(live, sidecar, archive),
        "write_work": _write_work(sidecar, restarts), "timing": None,
    }
    if timing:
        result["timing"] = _timing(live, sidecar, archive, tasks, samples)
    return result


class LiveExposureAnswer:
    """Small helper that reconstructs only the sidecar runtime, never full history."""

    @staticmethod
    def sidecar(live: dict) -> inc.IncrementalCompactSidecar:
        compact = live["compact"]
        epi = compact["api"]["epistemic"]["records_codec"]
        snapshot = {
            "schema": SCHEMA,
            "observation_codec": deepcopy(epi["observation"]),
            "other_records": deepcopy(epi["other_records"]),
            "relationships": {
                "\x1f".join(s9a._pair_key(key)): deepcopy(value)
                for key, value in compact["api"]["engine"]["relationships"].items()
            },
            "agent_values": {
                key: deepcopy(value.get("values", {}))
                for key, value in compact["api"]["agents"]["agents"].items()
            },
            "last_sequence": compact["api"]["epistemic"]["sequence"],
            "records_ingested": len(epi["observation"]["rows"]) + len(epi["other_records"]),
        }
        return inc.IncrementalCompactSidecar(snapshot)

    @staticmethod
    def answer(live: dict, task: dict) -> Any:
        return LiveExposureAnswer.sidecar(live).answer(task)


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    levels = [_profile_level(deepcopy(level), timing=timing, samples=timing_samples) for level in _LEVELS]
    return {
        "schema": SCHEMA, "strict_verdict": VERDICT, "levels": levels,
        "all_correct": all(row["all_correct"] for row in levels),
        "all_exact_reference_matches": all(row["exact_reference_match"] for row in levels),
        "all_exact_roundtrips": all(row["exact_roundtrip"] for row in levels),
        "constraints": {
            "production_ghost_modified": False, "research_only": True,
            "writer_never_receives_task_registry": True, "no_periodic_full_rebuilds": True,
            "sidecar_restart_tested": True, "full_ghost_restart_continuation_not_tested": True,
            "record_deletion_not_supported_by_current_public_epistemic_contract": True,
            "timing_is_telemetry_not_gate": True, "no_weighted_composite_score": True,
        },
        "claim_boundary": (
            "Stage 9C tests live incremental maintenance of the compact epistemic observation representation and task-blind query indexes alongside the unchanged Full-Ghost runtime. It requires exact final parity with the frozen Stage-7 reference, exact compact roundtrip, and sidecar restart continuity. It does not yet replace Ghost's in-memory epistemic runtime, test full Ghost restart-and-continue, or establish production readiness."
        ),
    }
