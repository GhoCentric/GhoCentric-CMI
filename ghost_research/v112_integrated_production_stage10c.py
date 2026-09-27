"""Stage-10C integrated production-shaped persistence adjudication."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter_ns
import tracemalloc

from ghost import GhostAPI
from ghost._persistence_codec import compact_snapshot
from ghost._persistence_runtime import (
    _unwrap_snapshot,
    _wrap_snapshot,
    attach_persistence_shadow,
    detach_persistence_shadow,
)
from ghost._persistence_shadow import ShadowPersistenceCandidate, _canonical_bytes
from ghost_research import v112_atomic_recovery_stage9e as s9e

SCHEMA = "ghost.v1.12-dev.integrated-production.stage10c.v1"
VERDICT = "V112_INTEGRATED_PRODUCTION_STAGE10C_EXPERIMENT_VALID"
CRASH_EXIT_CODE = 83
_LONG_STEPS = 4
_TIMING_SAMPLES = 3
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)
_SNAPSHOT_CACHE = {}


def _snapshot_from_level(level: dict) -> dict:
    key = (level["id"], level["ambient_events"])
    if key not in _SNAPSHOT_CACHE:
        pair = s9e._checkpoint_pair(level)
        _SNAPSHOT_CACHE[key] = deepcopy(pair["new_frozen"]["api"])
    return deepcopy(_SNAPSHOT_CACHE[key])


def _api_from_level(level: dict) -> GhostAPI:
    return GhostAPI.from_snapshot(_snapshot_from_level(level))


def _mutate(api: GhostAPI, index: int) -> dict:
    event_type = "help" if index % 2 == 0 else "betrayal"
    intensity = (0.25, 0.5, 0.75, 1.0)[index % 4]
    return api.apply_event(
        "stage10c_player",
        "stage10c_npc_%d" % (index % 3),
        {"type": event_type, "intensity": intensity},
    )


def _median_us(fn, samples: int = _TIMING_SAMPLES) -> float:
    values = []
    for _ in range(samples):
        start = perf_counter_ns()
        fn()
        values.append((perf_counter_ns() - start) / 1000.0)
    return float(statistics.median(values))


def _long_steps(live: GhostAPI, control: GhostAPI, runtime) -> list:
    rows = []
    for index in range(_LONG_STEPS):
        live_result = _mutate(live, index)
        control_result = _mutate(control, index)
        live_snapshot = live.snapshot()
        control_snapshot = control.snapshot()
        rows.append({
            "return_exact": live_result == control_result,
            "snapshot_exact": live_snapshot == control_snapshot,
            "generation": runtime.status()["last_generation"],
        })
    return rows


def _continuation(live: GhostAPI, control: GhostAPI, runtime) -> dict:
    shadow = runtime.load_verified_snapshot()
    restored = GhostAPI.from_snapshot(deepcopy(shadow))
    restore_exact = shadow == control.snapshot() == restored.snapshot()
    live_result = _mutate(live, 100)
    control_result = _mutate(control, 100)
    restored_result = _mutate(restored, 100)
    live_final = live.snapshot()
    control_final = control.snapshot()
    restored_final = restored.snapshot()
    return {
        "verified_restore_exact": restore_exact,
        "continuation_return_exact": live_result == control_result == restored_result,
        "continuation_snapshot_exact": live_final == control_final == restored_final,
    }


def _long_run_probe(level: dict, root: Path) -> dict:
    live, control = _api_from_level(level), _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=2, verify_load=True)
    rows = _long_steps(live, control, runtime)
    continuation = _continuation(live, control, runtime)
    health = runtime.status()
    return {
        "steps": rows,
        "generation_sequence": [row["generation"] for row in rows],
        "all_step_returns_exact": all(row["return_exact"] for row in rows),
        "all_step_snapshots_exact": all(row["snapshot_exact"] for row in rows),
        **continuation,
        "health": health,
        "health_nominal": (
            health["attempts"] == _LONG_STEPS + 1
            and health["successes"] == _LONG_STEPS + 1
            and health["failures"] == 0
            and health["circuit_open"] is False
            and health["last_source"] == "candidate"
        ),
    }


def _start_lock_holder(root: Path):
    code = (
        "from ghost._persistence_shadow import ShadowPersistenceCandidate\n"
        "from pathlib import Path\n"
        "import sys,time\n"
        "store=ShadowPersistenceCandidate(Path(sys.argv[1]), enabled=True)\n"
        "with store._lease():\n"
        " print('READY', flush=True)\n"
        " time.sleep(5)\n"
    )
    engine = Path(__file__).resolve().parents[1]
    return subprocess.Popen(
        [sys.executable, "-c", code, str(root)],
        cwd=str(engine), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _writer_contention_probe(level: dict, root: Path) -> dict:
    live, control = _api_from_level(level), _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=1, verify_load=True)
    with _start_lock_holder(root) as holder:
        ready = holder.stdout.readline().strip()
        contended, expected = live.snapshot(), control.snapshot()
        failed = runtime.status()
        holder.terminate()
        holder.wait(timeout=5)
    runtime.reset_circuit()
    recovered, expected_recovered = live.snapshot(), control.snapshot()
    health = runtime.status()
    return {
        "holder_ready": ready == "READY",
        "contended_snapshot_exact": contended == expected,
        "failure_opened_circuit": (
            failed["attempts"] == 1 and failed["failures"] == 1 and failed["circuit_open"] is True
        ),
        "post_death_snapshot_exact": recovered == expected_recovered,
        "post_death_write_recovered": (
            health["attempts"] == 2 and health["successes"] == 1 and health["failures"] == 1
            and health["circuit_open"] is False and health["last_generation"] == 1
        ),
    }


def _candidate_corruption_probe(level: dict, root: Path) -> dict:
    live, control = _api_from_level(level), _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=2, verify_load=True)
    first, expected_first = live.snapshot(), control.snapshot()
    runtime.store.candidate_path.write_bytes(b"{broken")
    fallback = runtime.store.load()
    second, expected_second = live.snapshot(), control.snapshot()
    repaired = runtime.store.load()
    return {
        "first_exact": first == expected_first,
        "fallback_source": fallback["source"],
        "fallback_exact": _unwrap_snapshot(fallback["snapshot"]) == first,
        "second_exact": second == expected_second,
        "repaired_source": repaired["source"],
        "repaired_exact": _unwrap_snapshot(repaired["snapshot"]) == second,
        "generation": repaired["generation"],
    }


def _candidate_version_probe(level: dict, root: Path) -> dict:
    live, control = _api_from_level(level), _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=2, verify_load=True)
    first, expected_first = live.snapshot(), control.snapshot()
    packet = json.loads(runtime.store.candidate_path.read_text(encoding="utf-8"))
    packet["format_version"] = 999
    runtime.store.candidate_path.write_bytes(_canonical_bytes(packet))
    fallback = runtime.store.load()
    second, expected_second = live.snapshot(), control.snapshot()
    repaired = runtime.store.load()
    return {
        "first_exact": first == expected_first,
        "fallback_source": fallback["source"],
        "fallback_exact": _unwrap_snapshot(fallback["snapshot"]) == first,
        "second_exact": second == expected_second,
        "repaired_source": repaired["source"],
        "repaired_exact": _unwrap_snapshot(repaired["snapshot"]) == second,
        "generation": repaired["generation"],
    }


def _rollback_probe(level: dict, root: Path) -> dict:
    live, control = _api_from_level(level), _api_from_level(level)
    runtime = attach_persistence_shadow(live, root, failure_threshold=2, verify_load=True)
    first, expected_first = live.snapshot(), control.snapshot()
    detached = detach_persistence_shadow(live, rollback=True)
    baseline = ShadowPersistenceCandidate(root, enabled=True).load()
    after, expected_after = live.snapshot(), control.snapshot()
    return {
        "first_exact": first == expected_first,
        "detached_disabled": detached["enabled"] is False,
        "candidate_removed": not runtime.store.candidate_path.exists(),
        "manifest_removed": not runtime.store.manifest_path.exists(),
        "baseline_preserved": runtime.store.baseline_path.is_file(),
        "baseline_source": baseline["source"],
        "baseline_exact": _unwrap_snapshot(baseline["snapshot"]) == first,
        "post_detach_exact": after == expected_after,
        "hook_removed": "_persistence_shadow_runtime" not in live.__dict__,
    }


_CRASH_CODE = r'''
import json,os,sys
from ghost import GhostAPI
import ghost._persistence_shadow as shadow
from ghost._persistence_runtime import attach_persistence_shadow
with open(sys.argv[1], encoding="utf-8") as handle:
    base=json.load(handle)
root=sys.argv[2]
target=int(sys.argv[3])
api=GhostAPI.from_snapshot(base)
api.apply_event("stage10c_crash","stage10c_npc",{"type":"help","intensity":0.625})
attach_persistence_shadow(api,root,failure_threshold=2,verify_load=True)
real=shadow._atomic_write
calls={"n":0}
def crashing_write(path,data):
    calls["n"]+=1
    real(path,data)
    if calls["n"]==target:
        os._exit(83)
shadow._atomic_write=crashing_write
api.snapshot()
os._exit(91)
'''


def _crash_expected(base_snapshot: dict) -> dict:
    api = GhostAPI.from_snapshot(deepcopy(base_snapshot))
    api.apply_event(
        "stage10c_crash", "stage10c_npc", {"type": "help", "intensity": 0.625}
    )
    return api.snapshot()


def _run_crash_child(input_path: Path, root: Path, atomic_call: int):
    engine = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, "-c", _CRASH_CODE, str(input_path), str(root), str(atomic_call)],
        cwd=str(engine), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _crash_case(level: dict, root: Path, atomic_call: int) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    base_api = _api_from_level(level)
    runtime = attach_persistence_shadow(base_api, root, failure_threshold=2, verify_load=True)
    base_snapshot = base_api.snapshot()
    detach_persistence_shadow(base_api)
    expected_snapshot = _crash_expected(base_snapshot)
    input_path = root.parent / (root.name + "_input.json")
    input_path.write_text(json.dumps(base_snapshot, sort_keys=True), encoding="utf-8")
    proc = _run_crash_child(input_path, root, atomic_call)
    loaded = ShadowPersistenceCandidate(root, enabled=True).load()
    expected_source = {1: "baseline", 2: "baseline", 3: "candidate"}[atomic_call]
    return {
        "atomic_call": atomic_call,
        "returncode": proc.returncode,
        "expected_exit": proc.returncode == CRASH_EXIT_CODE,
        "source": loaded["source"],
        "source_exact": loaded["source"] == expected_source,
        "generation": loaded["generation"],
        "state_exact": _unwrap_snapshot(loaded["snapshot"]) == expected_snapshot,
        "initial_generation": runtime.status()["last_generation"],
    }


def _crash_matrix(level: dict, root: Path) -> list:
    return [_crash_case(level, root / ("atomic_%d" % call), call) for call in (1, 2, 3)]


def _peak_compact_bytes(snapshot: dict) -> int:
    tracemalloc.start()
    compact_snapshot(_wrap_snapshot(snapshot))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return int(peak)


def _cost_profile(level: dict, root: Path) -> dict:
    control = _api_from_level(level)
    snapshot = control.snapshot()
    wrapped = _wrap_snapshot(snapshot)
    store = ShadowPersistenceCandidate(root / "store", enabled=True)
    verified_api, unverified_api = _api_from_level(level), _api_from_level(level)
    attach_persistence_shadow(verified_api, root / "verified", verify_load=True)
    attach_persistence_shadow(unverified_api, root / "unverified", verify_load=False)
    control_us = _median_us(control.snapshot)
    verified_us = _median_us(verified_api.snapshot)
    unverified_us = _median_us(unverified_api.snapshot)
    return {
        "samples": _TIMING_SAMPLES,
        "control_snapshot_us": control_us,
        "compact_cpu_us": _median_us(lambda: compact_snapshot(wrapped)),
        "shadow_write_us": _median_us(lambda: store.write(wrapped)),
        "shadow_load_us": _median_us(store.load),
        "integrated_verified_us": verified_us,
        "integrated_unverified_us": unverified_us,
        "verified_over_control_ratio": verified_us / control_us,
        "unverified_over_control_ratio": unverified_us / control_us,
        "compact_peak_python_alloc_bytes": _peak_compact_bytes(snapshot),
        "full_wrapper_bytes": len(_canonical_bytes(wrapped)),
        "baseline_file_bytes": store.baseline_path.stat().st_size,
        "candidate_file_bytes": store.candidate_path.stat().st_size,
        "manifest_file_bytes": store.manifest_path.stat().st_size,
    }


def _profile_level(level: dict, root: Path) -> dict:
    return {
        "level": deepcopy(level),
        "long_run": _long_run_probe(level, root / "long_run"),
        "writer_contention": _writer_contention_probe(level, root / "writer_contention"),
        "candidate_corruption": _candidate_corruption_probe(level, root / "corruption"),
        "candidate_version": _candidate_version_probe(level, root / "version"),
        "rollback": _rollback_probe(level, root / "rollback"),
        "crash_matrix": _crash_matrix(level, root / "crash"),
        "cost": _cost_profile(level, root / "cost"),
    }


def _gate_long_run(levels: list) -> tuple:
    returns = all(row["long_run"]["all_step_returns_exact"] for row in levels)
    snapshots = all(row["long_run"]["all_step_snapshots_exact"] for row in levels)
    continuation = all(
        row["long_run"]["verified_restore_exact"]
        and row["long_run"]["continuation_return_exact"]
        and row["long_run"]["continuation_snapshot_exact"]
        and row["long_run"]["health_nominal"]
        for row in levels
    )
    return returns, snapshots, continuation


def _gate_contention(levels: list) -> bool:
    return all(all(row["writer_contention"].values()) for row in levels)


def _gate_repair(levels: list, key: str) -> bool:
    return all(
        row[key]["first_exact"]
        and row[key]["fallback_source"] == "baseline"
        and row[key]["fallback_exact"]
        and row[key]["second_exact"]
        and row[key]["repaired_source"] == "candidate"
        and row[key]["repaired_exact"]
        and row[key]["generation"] == 2
        for row in levels
    )


def _gate_rollback(levels: list) -> bool:
    return all(
        row["rollback"]["first_exact"]
        and row["rollback"]["detached_disabled"]
        and row["rollback"]["candidate_removed"]
        and row["rollback"]["manifest_removed"]
        and row["rollback"]["baseline_preserved"]
        and row["rollback"]["baseline_source"] == "baseline"
        and row["rollback"]["baseline_exact"]
        and row["rollback"]["post_detach_exact"]
        and row["rollback"]["hook_removed"]
        for row in levels
    )


def _gate_crash(levels: list) -> bool:
    return all(
        all(
            case["expected_exit"] and case["source_exact"] and case["generation"] == 2
            and case["state_exact"] and case["initial_generation"] == 1
            for case in row["crash_matrix"]
        )
        for row in levels
    )


def _gate_telemetry(levels: list) -> bool:
    keys = (
        "control_snapshot_us", "compact_cpu_us", "shadow_write_us", "shadow_load_us",
        "integrated_verified_us", "integrated_unverified_us", "verified_over_control_ratio",
        "unverified_over_control_ratio", "compact_peak_python_alloc_bytes", "full_wrapper_bytes",
        "baseline_file_bytes", "candidate_file_bytes", "manifest_file_bytes",
    )
    return all(all(row["cost"][key] > 0 for key in keys) for row in levels)


def _gates(levels: list) -> dict:
    returns, snapshots, continuation = _gate_long_run(levels)
    return {
        "long_run_return_parity": returns,
        "long_run_snapshot_parity": snapshots,
        "verified_restore_continuation": continuation,
        "writer_contention_fail_open_recovery": _gate_contention(levels),
        "candidate_corruption_fallback_repair": _gate_repair(levels, "candidate_corruption"),
        "candidate_version_fallback_repair": _gate_repair(levels, "candidate_version"),
        "rollback_preserves_baseline_authority": _gate_rollback(levels),
        "production_atomic_crash_recovery": _gate_crash(levels),
        "performance_telemetry_complete": _gate_telemetry(levels),
    }


def _constraints() -> dict:
    return {
        "production_files_modified_by_stage10c": False,
        "real_ghostapi_hook_exercised": True,
        "production_shadow_store_exercised": True,
        "cross_process_writer_contention_exercised": True,
        "actual_process_exit_after_atomic_commits_exercised": True,
        "candidate_remains_non_authoritative": True,
        "candidate_remains_private_opt_in": True,
        "enabled_observer_is_synchronous": True,
        "timing_and_python_allocation_are_telemetry_not_gates": True,
        "no_public_persistence_api_claim": True,
        "no_release_latency_slo_claim": True,
        "no_sudden_hardware_power_loss_claim": True,
        "no_distributed_locking_claim": True,
    }


def run_experiment() -> dict:
    with tempfile.TemporaryDirectory(prefix="ghost-stage10c-") as temporary:
        root = Path(temporary)
        levels = [_profile_level(deepcopy(level), root / level["id"]) for level in _LEVELS]
    gates = _gates(levels)
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "constraints": _constraints(),
        "claim_boundary": (
            "Stage 10C adjudicates the Stage-10A/10B production-shaped persistence candidate as it exists in ghost/*: repeated real GhostAPI mutation/snapshot observation, verified restore and continuation, cross-process writer contention, candidate corruption/version fallback and repair, rollback to baseline authority, and actual child-process exit immediately after each production atomic file commit. It also attributes synchronous enabled-path cost and Python allocation telemetry. Passing Stage 10C supports advancing the still-private, explicit-opt-in candidate to a repository push/release-hygiene gate; it does not justify making candidate persistence authoritative or public, and it does not establish an acceptable product latency SLO, sudden hardware power-loss durability, or distributed locking."
        ),
    }
