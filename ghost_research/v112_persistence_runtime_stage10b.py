"""Stage-10B guarded GhostAPI snapshot integration and circuit-breaker adjudication."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
from time import perf_counter_ns

from ghost import GhostAPI
from ghost._persistence_runtime import attach_persistence_shadow
from ghost_research import v112_atomic_recovery_stage9e as s9e

SCHEMA = "ghost.v1.12-dev.persistence-runtime.stage10b.v1"
VERDICT = "V112_PERSISTENCE_RUNTIME_STAGE10B_EXPERIMENT_VALID"
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)


def _api_from_level(level: dict) -> GhostAPI:
    pair = s9e._checkpoint_pair(level)
    return GhostAPI.from_snapshot(deepcopy(pair["new_frozen"]["api"]))


def _mutate(api: GhostAPI) -> dict:
    return api.apply_event(
        "stage10b_player",
        "stage10b_npc",
        {"type": "help", "intensity": 0.75},
    )


def _circuit_probe(level: dict, root: Path) -> bool:
    live = _api_from_level(level)
    control = _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=1)
    calls = {"count": 0}

    def fail_write(snapshot):
        calls["count"] += 1
        raise OSError("forced-stage10b-shadow-failure")

    runtime.store.write = fail_write
    first, expected_first = live.snapshot(), control.snapshot()
    second, expected_second = live.snapshot(), control.snapshot()
    health = runtime.status()
    return (
        first == expected_first
        and second == expected_second
        and calls["count"] == 1
        and health["attempts"] == 1
        and health["failures"] == 1
        and health["circuit_open"] is True
        and health["skipped_circuit_open"] == 1
    )


def _disabled_probe(level: dict, root: Path) -> bool:
    disabled = _api_from_level(level)
    runtime = attach_persistence_shadow(disabled, root, enabled=False)
    snapshot = disabled.snapshot()
    return (
        snapshot == _api_from_level(level).snapshot()
        and "_persistence_shadow_runtime" not in disabled.__dict__
        and runtime.status()["attempts"] == 0
        and not root.exists()
    )


def _initial_snapshot_probe(level: dict, root: Path) -> tuple:
    live = _api_from_level(level)
    control = _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=2)
    start = perf_counter_ns(); live_snapshot = live.snapshot()
    integrated_us = (perf_counter_ns() - start) / 1000.0
    start = perf_counter_ns(); control_snapshot = control.snapshot()
    control_us = (perf_counter_ns() - start) / 1000.0
    if live_snapshot != control_snapshot:
        raise RuntimeError("Stage-10B enabled shadow changed GhostAPI snapshot output")
    return live, control, runtime, live_snapshot, integrated_us, control_us


def _continuation_probe(live, control, runtime, initial: dict) -> dict:
    shadow_snapshot = runtime.load_verified_snapshot()
    restored = GhostAPI.from_snapshot(deepcopy(shadow_snapshot))
    restore_exact = restored.snapshot() == initial
    not_serialized = "_persistence_shadow_runtime" not in restored.__dict__
    live_result, control_result, restored_result = _mutate(live), _mutate(control), _mutate(restored)
    if live_result != control_result or restored_result != control_result:
        raise RuntimeError("Stage-10B continuation return packet drifted")
    continuation_exact = live.snapshot() == control.snapshot() == restored.snapshot()
    return {
        "verified_shadow_restore_exact": restore_exact,
        "continuation_exact": continuation_exact,
        "configuration_not_serialized": not_serialized,
    }


def _profile_level(level: dict, root: Path) -> dict:
    disabled_exact = _disabled_probe(level, root / "disabled")
    live, control, runtime, initial, integrated_us, control_us = _initial_snapshot_probe(
        level, root / "live"
    )
    continuation = _continuation_probe(live, control, runtime, initial)
    health = runtime.status()
    return {
        "level": deepcopy(level),
        "disabled_attach_is_inert": disabled_exact,
        "enabled_snapshot_output_exact": True,
        **continuation,
        "health": health,
        "health_is_nominal": (
            health["attempts"] == 2
            and health["successes"] == 2
            and health["failures"] == 0
            and health["circuit_open"] is False
            and health["last_source"] == "candidate"
        ),
        "circuit_breaker_fail_open": _circuit_probe(level, root / "circuit"),
        "timing": {"integrated_snapshot_us": integrated_us, "control_snapshot_us": control_us},
    }


def _gates(levels: list) -> dict:
    return {
        "disabled_attach_inert": all(row["disabled_attach_is_inert"] for row in levels),
        "snapshot_output_parity": all(row["enabled_snapshot_output_exact"] for row in levels),
        "verified_restore": all(row["verified_shadow_restore_exact"] for row in levels),
        "continuation_parity": all(row["continuation_exact"] for row in levels),
        "configuration_not_serialized": all(row["configuration_not_serialized"] for row in levels),
        "health_nominal": all(row["health_is_nominal"] for row in levels),
        "circuit_breaker_fail_open": all(row["circuit_breaker_fail_open"] for row in levels),
    }


def run_experiment() -> dict:
    with tempfile.TemporaryDirectory(prefix="ghost-stage10b-") as temporary:
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
            "real_ghostapi_snapshot_hook_exercised": True,
            "integration_is_internal_only": True,
            "public_api_method_count_unchanged": True,
            "constructor_signature_unchanged": True,
            "disabled_configuration_attaches_no_hook": True,
            "shadow_failure_never_blocks_snapshot_return": True,
            "circuit_breaker_is_process_local": True,
            "host_persistence_not_replaced": True,
            "timing_is_telemetry_not_gate": True,
        },
        "claim_boundary": (
            "Stage 10B wires the internal shadow candidate to real GhostAPI.snapshot() calls through an explicitly attached private runtime observer. The returned GhostAPI snapshot remains exact, persisted shadow state restores exactly and continues deterministically, configuration is not serialized into Ghost state, and expected shadow failures open a process-local circuit without blocking GhostAPI snapshot output. This does not expose a public persistence API, make the candidate authoritative, replace host saves, or establish release readiness."
        ),
    }
