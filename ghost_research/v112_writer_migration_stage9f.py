"""Research-only Stage-9F writer exclusion and interrupted-migration adjudication."""
from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
import errno
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from time import perf_counter_ns
from types import SimpleNamespace
from typing import Any

from ghost_research import v112_atomic_recovery_stage9e as s9e
from ghost_research import v112_restart_continue_stage9d as s9d
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.writer-migration.stage9f.v1"
VERDICT = "V112_WRITER_MIGRATION_STAGE9F_EXPERIMENT_VALID"
LOCK_FILE = ".stage9f-writer.lock"
LOCK_BUSY_EXIT_CODE = 78
MIGRATION_CRASH_EXIT_CODE = 79
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)
_MIGRATION_EXPECTATION = {
    "after_lock_acquired": "legacy",
    "after_source_validated": "legacy",
    "after_partial_slot_write": "legacy",
    "after_slot_fsync": "legacy",
    "after_slot_replace": "legacy",
    "after_slot_dir_fsync": "legacy",
    "after_head_fsync": "legacy",
    "after_head_replace": "new",
    "after_commit_dir_fsync": "new",
}
_TIMING_SAMPLES = 3


class WriterBusyError(RuntimeError):
    """Raised when another process already holds the Stage-9F writer lease."""


class MigrationCrash(RuntimeError):
    """Focused-test fault injection; the experiment uses actual child exit."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _template_packet(template: s6.StructuralContender) -> dict:
    packet = {
        "agent_ids": list(template.agent_ids),
        "source_ids": list(template.source_ids),
        "subject_ids": list(template.subject_ids),
    }
    for key, value in packet.items():
        if not value or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"restart template {key} must be non-empty strings")
    return packet


def _template_from_packet(packet: Any) -> SimpleNamespace:
    if not isinstance(packet, dict) or set(packet) != {"agent_ids", "source_ids", "subject_ids"}:
        raise ValueError("restart template packet has invalid shape")
    clean = {}
    for key in ("agent_ids", "source_ids", "subject_ids"):
        value = packet[key]
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"restart template {key} must be a non-empty string list")
        clean[key] = list(value)
    return SimpleNamespace(**clean)


def _trip_migration(point: str | None, wanted: str, mode: str) -> None:
    if point != wanted:
        return
    if mode == "raise":
        raise MigrationCrash(wanted)
    if mode == "exit":
        os._exit(MIGRATION_CRASH_EXIT_CODE)
    raise ValueError("migration crash mode must be 'raise' or 'exit'")


class WriterLease(AbstractContextManager):
    """Non-blocking local-process writer exclusion using advisory flock."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / LOCK_FILE
        self._handle = None

    def __enter__(self) -> "WriterLease":
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise WriterBusyError("Stage-9F writer lease is already held") from exc
            raise
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        return False


class LockedCheckpointStore(s9e.AtomicCheckpointStore):
    """Stage-9E store wrapped in single-host writer exclusion and strict bootstrap recovery."""

    def writer_lease(self) -> WriterLease:
        return WriterLease(self.directory)

    def write_locked(self, compact: dict, *, crash_at: str | None = None, crash_mode: str = "raise") -> int:
        with self.writer_lease():
            return super().write(compact, crash_at=crash_at, crash_mode=crash_mode)

    def recover_committed(self, template: s6.StructuralContender) -> dict:
        if not self.head_path.exists():
            raise ValueError("no committed checkpoint head")
        try:
            head = self._head()
        except ValueError:
            head = None
        return self._select_candidate(head, self._candidates(template))

    def migrate_stage9d(
        self,
        blob: bytes,
        template: s6.StructuralContender,
        *,
        crash_at: str | None = None,
        crash_mode: str = "raise",
    ) -> int:
        if crash_at is not None and crash_at not in _MIGRATION_EXPECTATION:
            raise ValueError("unknown Stage-9F migration crash point")
        with self.writer_lease():
            _trip_migration(crash_at, "after_lock_acquired", crash_mode)
            compact = s9d.decode_envelope(blob)
            s9d.restore_runtime(blob, template)
            _trip_migration(crash_at, "after_source_validated", crash_mode)
            if self.head_path.exists():
                existing = self.recover_committed(template)
                if existing["compact"] != compact:
                    raise ValueError("migration target already contains a different committed state")
                return existing["generation"]
            write_point = crash_at if crash_at in s9e._CRASH_EXPECTATION else None
            return super().write(compact, crash_at=write_point, crash_mode=crash_mode)


def _wait_for_path(path: Path, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for child marker: {path.name}")
        time.sleep(0.01)


def _child_hold_lock(store_dir: str, ready_path: str, release_path: str) -> None:
    ready = Path(ready_path)
    release = Path(release_path)
    with WriterLease(store_dir):
        ready.write_text("locked\n", encoding="utf-8")
        while not release.exists():
            time.sleep(0.01)


def _child_migrate(store_dir: str, envelope_path: str, template_path: str, crash_point: str) -> None:
    blob = Path(envelope_path).read_bytes()
    template = _template_from_packet(json.loads(Path(template_path).read_text(encoding="utf-8")))
    LockedCheckpointStore(store_dir).migrate_stage9d(blob, template, crash_at=crash_point, crash_mode="exit")
    raise RuntimeError("migration fault-injection child unexpectedly returned")


def _spawn_holder(store_dir: Path, ready: Path, release: Path) -> subprocess.Popen:
    code = (
        "from ghost_research.v112_writer_migration_stage9f import _child_hold_lock; "
        "import sys; _child_hold_lock(sys.argv[1], sys.argv[2], sys.argv[3])"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code, str(store_dir), str(ready), str(release)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_child_migration(root: Path, blob: bytes, template: s6.StructuralContender, crash_point: str) -> int:
    root.mkdir(parents=True, exist_ok=True)
    envelope_path = root / "legacy.stage9d"
    template_path = root / "template.json"
    envelope_path.write_bytes(blob)
    template_path.write_bytes(_canonical_bytes(_template_packet(template)))
    code = (
        "from ghost_research.v112_writer_migration_stage9f import _child_migrate; "
        "import sys; _child_migrate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(root / "store"), str(envelope_path), str(template_path), crash_point],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode


def _stop_child(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)


def _validate_writer_handoff(first: int, second: int, recovered: dict, pair: dict) -> None:
    exact = ex._freeze(recovered["contender"]) == pair["new_frozen"]
    if first != 1 or second != 2 or not exact:
        raise RuntimeError("Stage-9F writer handoff changed checkpoint ordering/state")
    if not s9e._continuation_equal(recovered["contender"], pair["new_frozen"], pair["template"]):
        raise RuntimeError("Stage-9F writer handoff failed continuation parity")


def _writer_exclusion(pair: dict, root: Path) -> dict:
    store_dir = root / "store"
    ready = root / "holder.ready"
    release = root / "holder.release"
    root.mkdir(parents=True, exist_ok=True)
    holder = _spawn_holder(store_dir, ready, release)
    try:
        _wait_for_path(ready)
        try:
            LockedCheckpointStore(store_dir).write_locked(pair["old_compact"])
        except WriterBusyError:
            pass
        else:
            raise RuntimeError("Stage-9F competing writer was not excluded")
        _stop_child(holder)
    finally:
        _stop_child(holder)
    store = LockedCheckpointStore(store_dir)
    first = store.write_locked(pair["old_compact"])
    second = store.write_locked(pair["new_compact"])
    recovered = store.recover_committed(pair["template"])
    _validate_writer_handoff(first, second, recovered, pair)
    return {
        "competing_writer_rejected": True,
        "process_death_released_lock": True,
        "serialized_generations": [first, second],
        "exact_final_state": True,
        "continuation_equal": True,
    }


def _expected_migration_exit(point: str) -> int:
    if point in {"after_lock_acquired", "after_source_validated"}:
        return MIGRATION_CRASH_EXIT_CODE
    return s9e.CRASH_EXIT_CODE


def _verify_pre_retry_state(store: LockedCheckpointStore, pair: dict, point: str, expected: str) -> None:
    if expected == "legacy":
        try:
            store.recover_committed(pair["template"])
        except ValueError:
            return
        raise RuntimeError(f"Stage-9F promoted an uncommitted bootstrap generation at {point}")
    recovered = store.recover_committed(pair["template"])
    if ex._freeze(recovered["contender"]) != pair["old_frozen"]:
        raise RuntimeError(f"Stage-9F committed interrupted migration drifted at {point}")


def _verify_migration_final(store: LockedCheckpointStore, pair: dict, point: str, generation: int) -> None:
    final = store.recover_committed(pair["template"])
    exact = ex._freeze(final["contender"]) == pair["old_frozen"]
    if generation != 1 or final["generation"] != 1 or not exact:
        raise RuntimeError(f"Stage-9F migration retry/idempotency failed at {point}")
    if not s9e._continuation_equal(final["contender"], pair["old_frozen"], pair["template"]):
        raise RuntimeError(f"Stage-9F migration continuation drifted at {point}")


def _migration_case(pair: dict, root: Path, point: str, expected: str, blob: bytes) -> dict:
    code = _run_child_migration(root, blob, pair["template"], point)
    expected_code = _expected_migration_exit(point)
    if code != expected_code:
        raise RuntimeError(f"Stage-9F migration child {point} exited {code}, expected {expected_code}")
    if (root / "legacy.stage9d").read_bytes() != blob:
        raise RuntimeError("Stage-9F interrupted migration mutated its Stage-9D source")
    store = LockedCheckpointStore(root / "store")
    with store.writer_lease():
        pass
    _verify_pre_retry_state(store, pair, point, expected)
    generation = store.migrate_stage9d(blob, pair["template"] )
    _verify_migration_final(store, pair, point, generation)
    return {"expected": expected, "source_preserved": True, "retry_generation": generation, "pass": True}


def _migration_matrix(pair: dict, root: Path) -> dict:
    blob = s9d.encode_envelope(pair["old_compact"])
    return {
        point: _migration_case(pair, root / point, point, expected, blob)
        for point, expected in _MIGRATION_EXPECTATION.items()
    }

def _migration_conflict(pair: dict, root: Path) -> bool:
    store = LockedCheckpointStore(root / "conflict")
    old_blob = s9d.encode_envelope(pair["old_compact"])
    new_blob = s9d.encode_envelope(pair["new_compact"])
    store.migrate_stage9d(old_blob, pair["template"])
    try:
        store.migrate_stage9d(new_blob, pair["template"])
    except ValueError:
        recovered = store.recover_committed(pair["template"])
        if recovered["generation"] == 1 and ex._freeze(recovered["contender"]) == pair["old_frozen"]:
            return True
    raise RuntimeError("Stage-9F conflicting migration did not fail closed without changing committed state")


def _timing_probe(pair: dict, root: Path, samples: int) -> dict:
    writes = []
    migrations = []
    blob = s9d.encode_envelope(pair["old_compact"])
    for index in range(samples):
        store = LockedCheckpointStore(root / f"write_{index}")
        start = perf_counter_ns()
        store.write_locked(pair["new_compact"])
        writes.append((perf_counter_ns() - start) / 1000.0)
        migration = LockedCheckpointStore(root / f"migration_{index}")
        start = perf_counter_ns()
        migration.migrate_stage9d(blob, pair["template"])
        migrations.append((perf_counter_ns() - start) / 1000.0)
    return {
        "samples": samples,
        "locked_write_median_us": s9d._median(writes),
        "fresh_migration_median_us": s9d._median(migrations),
    }


def _profile_level(level: dict, root: Path, *, timing: bool, samples: int) -> dict:
    pair = s9e._checkpoint_pair(level)
    writer = _writer_exclusion(pair, root / "writer")
    migrations = _migration_matrix(pair, root / "migration")
    conflict = _migration_conflict(pair, root)
    return {
        "level": deepcopy(level),
        "writer_exclusion": writer,
        "migration_crashes": migrations,
        "all_migration_crash_cases_pass": all(row["pass"] for row in migrations.values()),
        "migration_conflict_fails_closed": conflict,
        "query_correct_after_target_state": s9e._query_correct(pair["new_compact"], pair["new_ledger"]),
        "timing": _timing_probe(pair, root / "timing", samples) if timing else None,
    }


def _aggregate(levels: list[dict]) -> dict:
    return {
        "all_writer_exclusion_cases_pass": all(
            row["writer_exclusion"]["competing_writer_rejected"]
            and row["writer_exclusion"]["process_death_released_lock"]
            and row["writer_exclusion"]["exact_final_state"]
            and row["writer_exclusion"]["continuation_equal"]
            for row in levels
        ),
        "all_interrupted_migrations_pass": all(row["all_migration_crash_cases_pass"] for row in levels),
        "all_migration_conflicts_fail_closed": all(row["migration_conflict_fails_closed"] for row in levels),
        "all_queries_correct": all(row["query_correct_after_target_state"] for row in levels),
    }


CLAIM_BOUNDARY = (
    "Stage 9F tests research-only single-host writer exclusion using advisory flock and interrupted "
    "Stage-9D-to-Stage-9E migration. It requires a competing process to be rejected while a writer lease "
    "is held, verifies the OS releases that lease after process death, preserves exact generation order, "
    "state, and continuation after handoff, injects actual process exits at nine migration boundaries, "
    "refuses to treat a valid orphan slot without a committed head as a successful bootstrap migration, "
    "retries interrupted migration idempotently, preserves the predecessor envelope, and rejects a conflicting "
    "migration without changing committed state. It does not prove distributed or multi-host locking, "
    "NFS/remote-filesystem flock semantics, sudden-power-loss durability, starvation/fairness guarantees, "
    "authenticated tamper resistance, or production readiness."
)


def _constraints() -> dict:
    return {
        "production_ghost_modified": False, "research_only": True,
        "actual_cross_process_flock_exercised": True, "writer_lock_is_single_host_advisory": True,
        "multi_host_locking_not_proven": True, "lock_release_after_process_death_tested": True,
        "actual_process_exit_during_migration": True, "missing_bootstrap_head_never_promotes_orphan_slot": True,
        "migration_retry_is_idempotent": True, "conflicting_migration_fails_closed": True,
        "stage9d_source_preserved_during_interruption": True, "sudden_power_loss_durability_not_proven": True,
        "timing_is_telemetry_not_gate": True, "no_weighted_composite_score": True,
    }


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    with tempfile.TemporaryDirectory(prefix="ghost_stage9f_") as tmp:
        root = Path(tmp)
        levels = [
            _profile_level(deepcopy(level), root / level["id"], timing=timing, samples=timing_samples)
            for level in _LEVELS
        ]
    result = {"schema": SCHEMA, "strict_verdict": VERDICT, "levels": levels,
              "constraints": _constraints(), "claim_boundary": CLAIM_BOUNDARY}
    result.update(_aggregate(levels))
    return result
