"""Stage-10A guarded production-shadow persistence candidate adjudication."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from time import perf_counter_ns
from typing import Any

from ghost._persistence_codec import (
    OBSERVATION_CODEC_SCHEMA,
    RECORDS_CODEC_SCHEMA,
    compact_snapshot,
    expand_snapshot,
)
from ghost._persistence_shadow import ShadowPersistenceCandidate
from ghost_research import v112_atomic_recovery_stage9e as s9e

SCHEMA = "ghost.v1.12-dev.persistence-shadow.stage10a.v1"
VERDICT = "V112_PERSISTENCE_SHADOW_STAGE10A_EXPERIMENT_VALID"
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize_legacy(compact: dict) -> dict:
    result = deepcopy(compact)
    encoded = result["api"]["epistemic"]["records_codec"]
    encoded["schema"] = RECORDS_CODEC_SCHEMA
    encoded["observation"]["schema"] = OBSERVATION_CODEC_SCHEMA
    return result


def _rewrite_json(path: Path, transform) -> None:
    packet = json.loads(path.read_text(encoding="utf-8"))
    transform(packet)
    path.write_bytes(_canonical_bytes(packet))


def _bad_candidate_snapshot(full: dict) -> dict:
    bad = deepcopy(full)
    for record in bad["api"]["epistemic"]["records"]:
        if record.get("kind") == "observation":
            record["provenance"] = {"unsupported": ["still-json-safe"]}
            return bad
    raise RuntimeError("Stage-10A probe requires at least one observation")


def _probe_default(root: Path, full: dict) -> bool:
    disabled = ShadowPersistenceCandidate(root)
    result = disabled.write(full)
    return result["attempted"] is False and not root.exists()


def _probe_live(root: Path, old_full: dict, new_full: dict) -> dict:
    store = ShadowPersistenceCandidate(root, enabled=True)
    start = perf_counter_ns()
    first = store.write(old_full)
    second = store.write(new_full)
    write_us = (perf_counter_ns() - start) / 1000.0
    start = perf_counter_ns()
    loaded = store.load()
    load_us = (perf_counter_ns() - start) / 1000.0
    exact = first["candidate_usable"] and second["candidate_usable"]
    exact = exact and second["generation"] == 2 and loaded["source"] == "candidate"
    exact = exact and loaded["snapshot"] == new_full
    return {"exact": exact, "write_us": write_us, "load_us": load_us}


def _probe_version(root: Path, full: dict) -> bool:
    store = ShadowPersistenceCandidate(root, enabled=True)
    store.write(full)
    _rewrite_json(store.candidate_path, lambda packet: packet.__setitem__("format_version", 999))
    loaded = store.load()
    return loaded["source"] == "baseline" and loaded["snapshot"] == full


def _probe_corruption(root: Path, full: dict) -> bool:
    store = ShadowPersistenceCandidate(root, enabled=True)
    store.write(full)
    store.candidate_path.write_bytes(store.candidate_path.read_bytes()[:-1])
    loaded = store.load()
    return loaded["source"] == "baseline" and loaded["snapshot"] == full


def _probe_candidate_failure(root: Path, full: dict) -> bool:
    store = ShadowPersistenceCandidate(root, enabled=True)
    bad = _bad_candidate_snapshot(full)
    result = store.write(bad)
    loaded = store.load()
    return not result["candidate_usable"] and loaded["source"] == "baseline" and loaded["snapshot"] == bad


def _probe_rollback(root: Path, full: dict) -> bool:
    store = ShadowPersistenceCandidate(root, enabled=True)
    store.write(full)
    store.rollback_shadow()
    loaded = store.load()
    return (
        loaded["source"] == "baseline" and loaded["snapshot"] == full
        and store.baseline_path.exists() and not store.candidate_path.exists()
    )


def _profile_level(level: dict, root: Path) -> dict:
    pair = s9e._checkpoint_pair(level)
    old_full, new_full, legacy = pair["old_frozen"], pair["new_frozen"], pair["new_compact"]
    compact = compact_snapshot(new_full)
    research_equal = compact == _normalize_legacy(legacy)
    if expand_snapshot(compact) != new_full:
        raise RuntimeError("Stage-10A production codec failed exact full-snapshot roundtrip")
    live = _probe_live(root / "live", old_full, new_full)
    return {
        "level": deepcopy(level),
        "default_inert": _probe_default(root / "disabled", old_full),
        "exact_research_representation": research_equal,
        "exact_compact_roundtrip": True,
        "shadow_dual_write_exact": live["exact"],
        "unsupported_version_falls_back": _probe_version(root / "version", new_full),
        "corrupt_candidate_falls_back": _probe_corruption(root / "corrupt", new_full),
        "candidate_failure_preserves_baseline": _probe_candidate_failure(root / "failure", new_full),
        "rollback_preserves_baseline": _probe_rollback(root / "rollback", new_full),
        "storage": {"full_json_bytes": len(_canonical_bytes(new_full)), "compact_json_bytes": len(_canonical_bytes(compact))},
        "timing": {"two_shadow_writes_us": live["write_us"], "verified_shadow_load_us": live["load_us"]},
    }


def _gates(levels: list) -> dict:
    return {
        "default_inert": all(row["default_inert"] for row in levels),
        "research_representation_parity": all(row["exact_research_representation"] for row in levels),
        "compact_roundtrip": all(row["exact_compact_roundtrip"] for row in levels),
        "shadow_dual_write": all(row["shadow_dual_write_exact"] for row in levels),
        "version_fallback": all(row["unsupported_version_falls_back"] for row in levels),
        "corruption_fallback": all(row["corrupt_candidate_falls_back"] for row in levels),
        "candidate_failure_fallback": all(row["candidate_failure_preserves_baseline"] for row in levels),
        "rollback": all(row["rollback_preserves_baseline"] for row in levels),
    }


def run_experiment() -> dict:
    with tempfile.TemporaryDirectory(prefix="ghost-stage10a-") as temporary:
        root = Path(temporary)
        levels = [_profile_level(deepcopy(level), root / level["id"]) for level in _LEVELS]
    gates = _gates(levels)
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "constraints": {
            "production_candidate_added": True,
            "existing_production_files_modified": False,
            "public_api_modified": False,
            "default_path_is_inert": True,
            "candidate_is_never_required_for_baseline_load": True,
            "production_modules_import_ghost_research": False,
            "single_host_advisory_lock_only": True,
            "distributed_locking_not_claimed": True,
            "power_loss_durability_not_claimed": True,
            "timing_is_telemetry_not_gate": True,
        },
        "claim_boundary": (
            "Stage 10A ports the lossless compact representation into internal production-package code and tests an explicit opt-in shadow store. The canonical full snapshot remains the baseline authority. Candidate corruption, unsupported candidate versions, candidate encode/write failure, or explicit rollback must fall back to the exact baseline state. This does not activate persistence through GhostAPI, replace host persistence, establish distributed locking, or prove sudden-power-loss durability."
        ),
    }
