"""Stage-9B storage/query experiment over the lossless compact epistemic codec."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ghost_research import v112_compact_epistemic_codec_stage9b as codec
from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_equal_budget_adjudication_stage8 as s8
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_resource_cost_stage9 as s9

SCHEMA = "ghost.v1.12-dev.compact-epistemic.stage9b.v1"
VERDICT = "V112_COMPACT_EPISTEMIC_STAGE9B_EXPERIMENT_VALID"
_TIMING_SAMPLES = 7
_QUERY_REPETITIONS = 100
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
)


def _compact_work(index: codec.CompactGhostIndex, tasks: list[dict]) -> dict:
    record_reads, relationship_reads = 5, 0
    for task in tasks:
        kind = task["kind"]
        if kind in {"evidence_sources", "counterfactual_without_source"}:
            belief = index._belief(ex.AGENT, task["args"]["subject"])
            record_reads += 1 + (0 if belief is None else len(belief["evidence_ids"]))
        if kind in {"current_trust_sign", "relationship_event_count"}:
            relationship_reads += 1
        if kind in {"deeper_relationship", "novel_delegate_choice"}:
            relationship_reads += len(task["args"]["sources"])
    entry_count = sum((
        len(index.latest_observation_position_by_token), len(index.other_record_position_by_id),
        len(index.latest_belief_position_by_holder_subject),
        len(index.revision_count_by_holder_subject), len(index.relationships),
    ))
    return {
        "indexed_record_reads_per_battery": record_reads,
        "indexed_relationship_reads_per_battery": relationship_reads,
        "index_entry_count": entry_count,
        "index_payload_bytes": codec.json_bytes(index.index_payload()),
    }


def _correctness(full: dict, archive: dict, compact: dict, tasks: list[dict]) -> dict:
    readers = {
        "current": s9.WarmGhostReader(full["frozen"]),
        "indexed": s9a.FrozenGhostIndex(full["frozen"]),
        "compact_indexed": codec.CompactGhostIndex(compact),
    }
    rows = []
    for task in tasks:
        expected = s7._ground_truth(full["host_ledger"], task)
        answers = {name: reader.answer(task) for name, reader in readers.items()}
        answers["archive"] = s8._archive_answer(archive["archive_frozen"], task)["answer"]
        rows.append({"task": task["id"], "expected": expected, **answers,
                     "all_correct": all(value == expected for value in answers.values())})
    return {"all_correct": all(row["all_correct"] for row in rows), "rows": rows}


def _timing(full: dict, archive: dict, compact: dict, tasks: list[dict], samples: int) -> dict:
    warm = s9.WarmGhostReader(full["frozen"])
    indexed = s9a.FrozenGhostIndex(full["frozen"])
    compact_indexed = codec.CompactGhostIndex(compact)
    med = s9._median_us
    return {
        "samples": samples,
        "compact_build_us": med(lambda: codec.compact_snapshot(full["frozen"]), samples),
        "compact_expand_us": med(lambda: codec.expand_snapshot(compact), samples),
        "current_index_build_us": med(lambda: s9a.FrozenGhostIndex(full["frozen"]), samples),
        "compact_index_build_us": med(lambda: codec.CompactGhostIndex(compact), samples),
        "current_battery_us": med(lambda: s9._query_battery_warm(warm, tasks), samples),
        "indexed_battery_us": med(lambda: s9a._battery_indexed(indexed, tasks), samples),
        "compact_indexed_battery_us": med(lambda: s9a._battery_indexed(compact_indexed, tasks), samples),
        "archive_battery_us": med(lambda: s9._query_battery_archive(archive["archive_frozen"], tasks), samples),
        "compact_indexed_100_batteries_us": med(
            lambda: s9a._battery_indexed(compact_indexed, tasks, _QUERY_REPETITIONS), samples
        ),
        "archive_100_batteries_us": med(
            lambda: s9._query_battery_archive(archive["archive_frozen"], tasks, _QUERY_REPETITIONS), samples
        ),
    }


def _storage(full: dict, archive: dict, compact: dict, current_index: Any, compact_index: Any) -> dict:
    observations = [
        row for row in full["frozen"]["api"]["epistemic"]["records"]
        if row.get("kind") == "observation"
    ]
    observation_codec = compact["api"]["epistemic"]["records_codec"]["observation"]
    current_bytes = codec.json_bytes(full["frozen"])
    compact_bytes = codec.json_bytes(compact)
    current_index_bytes = codec.json_bytes(current_index.index_payload())
    compact_index_bytes = codec.json_bytes(compact_index.index_payload())
    return {
        "current_snapshot_bytes": current_bytes,
        "compact_snapshot_bytes": compact_bytes,
        "archive_snapshot_bytes": archive["snapshot_bytes"],
        "current_index_payload_bytes": current_index_bytes,
        "compact_index_payload_bytes": compact_index_bytes,
        "current_plus_index_bytes": current_bytes + current_index_bytes,
        "compact_plus_index_bytes": compact_bytes + compact_index_bytes,
        "observation_attribution": codec.observation_diagnostics(observations, observation_codec),
    }


def _profile_level(level: dict, *, timing: bool, samples: int) -> dict:
    full = ex.blind_exposure(level, "full")
    archive = s9._archive_exposure(level)
    if full["host_ledger"] != archive["host_ledger"]:
        raise RuntimeError("Stage-9B contenders did not receive identical exposure")
    compact = codec.compact_snapshot(full["frozen"])
    if codec.expand_snapshot(compact) != full["frozen"]:
        raise RuntimeError("compact representation is not exact-roundtrip lossless")
    tasks = s7.reveal_tasks()
    current_index = s9a.FrozenGhostIndex(full["frozen"])
    compact_index = codec.CompactGhostIndex(compact)
    result = {
        "level": deepcopy(level),
        "lossless_full_snapshot_roundtrip": True,
        "correctness": _correctness(full, archive, compact, tasks),
        "storage": _storage(full, archive, compact, current_index, compact_index),
        "work": {
            "current": s9._ghost_work(full["frozen"], tasks),
            "indexed": s9a._indexed_work(current_index, tasks),
            "compact_indexed": _compact_work(compact_index, tasks),
            "archive_records_examined_per_battery": s9._correctness(full, archive, tasks)["archive_records_examined_per_battery"],
        },
        "timing": None,
    }
    if timing:
        result["timing"] = _timing(full, archive, compact, tasks, samples)
    return result


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    levels = [_profile_level(deepcopy(level), timing=timing, samples=timing_samples) for level in _LEVELS]
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "all_four_correct": all(row["correctness"]["all_correct"] for row in levels),
        "all_lossless_roundtrips": all(row["lossless_full_snapshot_roundtrip"] for row in levels),
        "constraints": {
            "stage9a_question_frozen": True,
            "production_ghost_modified": False,
            "compact_representation_is_lossless": True,
            "compact_index_built_without_tasks": True,
            "compact_representation_built_without_tasks": True,
            "research_only": True,
            "timing_is_telemetry_not_gate": True,
            "no_weighted_composite_score": True,
            "incremental_write_cost_not_tested": True,
        },
        "claim_boundary": (
            "Stage 9B tests whether the exact frozen Ghost snapshot can losslessly replace verbose epistemic observation records with a canonical task-blind representation and retain the Stage-9A indexed-query behavior. "
            "It does not establish a production storage format, incremental update cost, universal speed advantage, or permission to change Ghost semantics."
        ),
    }
