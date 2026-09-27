"""Research-only Stage-9E atomic checkpoint/crash-recovery adjudication."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter_ns
from typing import Any

from ghost_research import v112_incremental_compact_codec_stage9c as inc
from ghost_research import v112_incremental_compact_stage9c as s9c
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_restart_continue_stage9d as s9d
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.atomic-recovery.stage9e.v1"
SLOT_SCHEMA = "ghost.stage9e.atomic-slot.v1"
HEAD_SCHEMA = "ghost.stage9e.atomic-head.v1"
VERDICT = "V112_ATOMIC_RECOVERY_STAGE9E_EXPERIMENT_VALID"
CRASH_EXIT_CODE = 77
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)
_CRASH_EXPECTATION = {
    "after_partial_slot_write": "old",
    "after_slot_fsync": "old",
    "after_slot_replace": "old",
    "after_slot_dir_fsync": "old",
    "after_head_fsync": "old",
    "after_head_replace": "new",
    "after_commit_dir_fsync": "new",
}
_TIMING_SAMPLES = 3


class SimulatedCrash(RuntimeError):
    """Fault-injection marker used by focused tests; experiment uses os._exit."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid checkpoint JSON: {path.name}") from exc


def _digest_text(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("checkpoint digest must be 64 hex characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("checkpoint digest must be 64 hex characters") from exc
    return value.lower()


def _fsync_dir(directory: Path) -> None:
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _trip(point: str | None, wanted: str, mode: str) -> None:
    if point != wanted:
        return
    if mode == "raise":
        raise SimulatedCrash(wanted)
    if mode == "exit":
        os._exit(CRASH_EXIT_CODE)
    raise ValueError("crash mode must be 'raise' or 'exit'")


class AtomicCheckpointStore:
    """Two-slot research store with an atomically replaced committed-head pointer."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.head_path = self.directory / "head.json"

    def _slot_path(self, slot: str) -> Path:
        if slot not in {"a", "b"}:
            raise ValueError("checkpoint slot must be 'a' or 'b'")
        return self.directory / f"slot_{slot}.json"

    def _head(self) -> dict | None:
        if not self.head_path.exists():
            return None
        packet = _json_file(self.head_path)
        if not isinstance(packet, dict) or set(packet) != {"schema", "active_slot", "generation", "slot_sha256"}:
            raise ValueError("atomic checkpoint head has invalid shape")
        if packet["schema"] != HEAD_SCHEMA or packet["active_slot"] not in {"a", "b"}:
            raise ValueError("atomic checkpoint head schema/slot mismatch")
        generation = packet["generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("atomic checkpoint generation must be a positive integer")
        return {
            "schema": HEAD_SCHEMA,
            "active_slot": packet["active_slot"],
            "generation": generation,
            "slot_sha256": _digest_text(packet["slot_sha256"]),
        }

    @staticmethod
    def _slot_bytes(compact: dict, generation: int) -> bytes:
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("atomic checkpoint generation must be a positive integer")
        envelope = s9d.encode_envelope(compact)
        packet = {
            "schema": SLOT_SCHEMA,
            "generation": generation,
            "envelope_sha256": _sha(envelope),
            "envelope_b64": base64.b64encode(envelope).decode("ascii"),
        }
        return _canonical_bytes(packet)

    @staticmethod
    def _decode_slot_bytes(data: bytes) -> tuple[int, bytes, dict]:
        try:
            packet = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("atomic checkpoint slot is not valid JSON") from exc
        if not isinstance(packet, dict) or set(packet) != {"schema", "generation", "envelope_sha256", "envelope_b64"}:
            raise ValueError("atomic checkpoint slot has invalid shape")
        if packet["schema"] != SLOT_SCHEMA:
            raise ValueError("atomic checkpoint slot schema mismatch")
        generation = packet["generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("atomic checkpoint slot generation must be positive")
        try:
            envelope = base64.b64decode(packet["envelope_b64"], validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("atomic checkpoint slot envelope is not valid base64") from exc
        if _sha(envelope) != _digest_text(packet["envelope_sha256"]):
            raise ValueError("atomic checkpoint slot envelope integrity mismatch")
        compact = s9d.decode_envelope(envelope)
        return generation, envelope, compact

    def _validated_slot(self, slot: str, template: s6.StructuralContender) -> dict:
        path = self._slot_path(slot)
        data = path.read_bytes()
        generation, envelope, compact = self._decode_slot_bytes(data)
        contender, sidecar, restored = s9d.restore_runtime(envelope, template)
        if restored != compact:
            raise RuntimeError("atomic checkpoint restore changed compact payload")
        return {
            "slot": slot,
            "generation": generation,
            "slot_sha256": _sha(data),
            "contender": contender,
            "sidecar": sidecar,
            "compact": compact,
        }

    def _write_slot(self, target: str, compact: dict, generation: int, crash_at: str | None, crash_mode: str) -> bytes:
        slot_path = self._slot_path(target)
        slot_tmp = slot_path.with_suffix(".json.tmp")
        slot_data = self._slot_bytes(compact, generation)
        with slot_tmp.open("wb") as handle:
            if crash_at == "after_partial_slot_write":
                handle.write(slot_data[: max(1, len(slot_data) // 2)])
                handle.flush()
                _trip(crash_at, "after_partial_slot_write", crash_mode)
            handle.write(slot_data)
            handle.flush()
            os.fsync(handle.fileno())
        _trip(crash_at, "after_slot_fsync", crash_mode)
        os.replace(slot_tmp, slot_path)
        _trip(crash_at, "after_slot_replace", crash_mode)
        _fsync_dir(self.directory)
        _trip(crash_at, "after_slot_dir_fsync", crash_mode)
        return slot_data

    def _commit_head(self, target: str, generation: int, slot_data: bytes, crash_at: str | None, crash_mode: str) -> None:
        packet = {"schema": HEAD_SCHEMA, "active_slot": target, "generation": generation, "slot_sha256": _sha(slot_data)}
        head_tmp = self.head_path.with_suffix(".json.tmp")
        with head_tmp.open("wb") as handle:
            handle.write(_canonical_bytes(packet))
            handle.flush()
            os.fsync(handle.fileno())
        _trip(crash_at, "after_head_fsync", crash_mode)
        os.replace(head_tmp, self.head_path)
        _trip(crash_at, "after_head_replace", crash_mode)
        _fsync_dir(self.directory)
        _trip(crash_at, "after_commit_dir_fsync", crash_mode)

    def write(self, compact: dict, *, crash_at: str | None = None, crash_mode: str = "raise") -> int:
        if crash_at is not None and crash_at not in _CRASH_EXPECTATION:
            raise ValueError("unknown Stage-9E crash point")
        head = self._head()
        active = None if head is None else head["active_slot"]
        generation = 1 if head is None else head["generation"] + 1
        target = "a" if active != "a" else "b"
        slot_data = self._write_slot(target, compact, generation, crash_at, crash_mode)
        self._commit_head(target, generation, slot_data, crash_at, crash_mode)
        return generation

    def _candidates(self, template: s6.StructuralContender) -> list[dict]:
        candidates = []
        for slot in ("a", "b"):
            try:
                candidates.append(self._validated_slot(slot, template))
            except (FileNotFoundError, OSError, TypeError, ValueError, RuntimeError):
                continue
        return candidates

    @staticmethod
    def _select_candidate(head: dict | None, candidates: list[dict]) -> dict:
        if not candidates:
            raise ValueError("no recoverable atomic checkpoint generation")
        if head is None:
            return max(candidates, key=lambda row: row["generation"])
        active = [row for row in candidates if row["slot"] == head["active_slot"]]
        if active and active[0]["generation"] == head["generation"] and active[0]["slot_sha256"] == head["slot_sha256"]:
            return active[0]
        eligible = [row for row in candidates if row["generation"] < head["generation"]]
        if not eligible:
            raise ValueError("committed checkpoint is invalid and no prior generation survives")
        return max(eligible, key=lambda row: row["generation"])

    def recover(self, template: s6.StructuralContender) -> dict:
        try:
            head = self._head()
        except ValueError:
            head = None
        return self._select_candidate(head, self._candidates(template))

    def import_stage9d(self, blob: bytes, template: s6.StructuralContender) -> int:
        compact = s9d.decode_envelope(blob)
        s9d.restore_runtime(blob, template)
        return self.write(compact)


def _checkpoint_pair(level: dict) -> dict:
    runner = s9c.LiveExposure(level)
    old = runner.run(restart_points=set())
    old_compact = deepcopy(old["compact"])
    old_frozen = deepcopy(old["frozen"])
    for index in range(12):
        runner.observe(
            f"stage9e_post_checkpoint_{index % 3}",
            source="world",
            subject=ex.SUBJECT,
            token=f"stage9e_post_{index:02d}",
            features={"ordinal": index},
        )
    runner.evidence(ex.WITNESS_B, 0.15, "stage9e_post_evidence")
    runner.relationship(ex.WITNESS_C, "help")
    new_frozen = ex._freeze(runner.contender)
    new_compact = runner.sidecar.compact_full_snapshot(new_frozen)
    if inc.IncrementalCompactSidecar.expand_full_snapshot(old_compact) != old_frozen:
        raise RuntimeError("Stage-9E old checkpoint failed exact compact reconstruction")
    if inc.IncrementalCompactSidecar.expand_full_snapshot(new_compact) != new_frozen:
        raise RuntimeError("Stage-9E new checkpoint failed exact compact reconstruction")
    return {
        "template": runner.contender,
        "old_frozen": old_frozen,
        "old_compact": old_compact,
        "new_frozen": new_frozen,
        "new_compact": new_compact,
        "new_ledger": deepcopy(runner.ledger),
    }


def _continuation_equal(restored: s6.StructuralContender, expected_frozen: dict, template: s6.StructuralContender) -> bool:
    shadow = s9d._restore_contender(expected_frozen, template)
    left: list[dict] = []
    right: list[dict] = []
    args = ("stage9e_post_recovery",)
    kwargs = {"source": "world", "subject": ex.SUBJECT, "token": "stage9e_post_recovery", "features": {"probe": 1}}
    ex._observe(restored, left, "stage9e_recovery", *args, **kwargs)
    ex._observe(shadow, right, "stage9e_recovery", *args, **kwargs)
    return left == right and restored._fingerprint() == shadow._fingerprint() and ex._freeze(restored) == ex._freeze(shadow)


def _child_write(store_dir: str, compact_path: str, crash_point: str) -> None:
    compact = json.loads(Path(compact_path).read_text(encoding="utf-8"))
    AtomicCheckpointStore(store_dir).write(compact, crash_at=crash_point, crash_mode="exit")
    raise RuntimeError("fault-injection child unexpectedly returned")


def _run_child_crash(store_dir: Path, compact: dict, crash_point: str) -> int:
    compact_path = store_dir / "candidate_compact.json"
    compact_path.write_bytes(_canonical_bytes(compact))
    code = (
        "from ghost_research.v112_atomic_recovery_stage9e import _child_write; "
        "import sys; _child_write(sys.argv[1], sys.argv[2], sys.argv[3])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(store_dir), str(compact_path), crash_point],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode


def _query_correct(compact: dict, ledger: list[dict]) -> bool:
    sidecar = s9c.LiveExposureAnswer.sidecar({"compact": compact})
    return all(sidecar.answer(task) == s7._ground_truth(ledger, task) for task in s7.reveal_tasks())


def _migration_check(pair: dict, root: Path) -> dict:
    template = pair["template"]
    legacy_blob = s9d.encode_envelope(pair["old_compact"])
    store = AtomicCheckpointStore(root / "migration")
    generation = store.import_stage9d(legacy_blob, template)
    migrated = store.recover(template)
    if generation != 1 or ex._freeze(migrated["contender"]) != pair["old_frozen"]:
        raise RuntimeError("Stage-9E Stage-9D migration changed exact Ghost state")
    if not _continuation_equal(migrated["contender"], pair["old_frozen"], template):
        raise RuntimeError("Stage-9E migrated runtime failed continuation parity")
    return {"stage9d_raw_envelope_imported": True, "exact_state": True, "continuation_equal": True}


def _crash_matrix(pair: dict, root: Path) -> dict:
    results = {}
    for point, expected in _CRASH_EXPECTATION.items():
        store = AtomicCheckpointStore(root / f"crash_{point}")
        store.write(pair["old_compact"])
        if _run_child_crash(store.directory, pair["new_compact"], point) != CRASH_EXIT_CODE:
            raise RuntimeError(f"Stage-9E child crash point {point} did not terminate as injected")
        recovered = store.recover(pair["template"])
        expected_frozen = pair[f"{expected}_frozen"]
        if ex._freeze(recovered["contender"]) != expected_frozen:
            raise RuntimeError(f"Stage-9E crash recovery selected wrong generation at {point}")
        if not _continuation_equal(recovered["contender"], expected_frozen, pair["template"]):
            raise RuntimeError(f"Stage-9E post-crash continuation drifted at {point}")
        results[point] = {"expected": expected, "recovered_generation": recovered["generation"], "pass": True}
    return results


def _active_slot_fallback(pair: dict, root: Path) -> bool:
    store = AtomicCheckpointStore(root / "fallback_active_slot")
    store.write(pair["old_compact"]); store.write(pair["new_compact"])
    head = store._head()
    if head is None:
        raise RuntimeError("Stage-9E committed head unexpectedly missing")
    store._slot_path(head["active_slot"]).write_bytes(b"corrupt")
    recovered = store.recover(pair["template"])
    if ex._freeze(recovered["contender"]) != pair["old_frozen"]:
        raise RuntimeError("Stage-9E corrupted committed slot did not fall back to prior generation")
    return True


def _corrupt_head_fallback(pair: dict, root: Path) -> bool:
    store = AtomicCheckpointStore(root / "fallback_head")
    store.write(pair["old_compact"]); store.write(pair["new_compact"])
    store.head_path.write_bytes(b"corrupt")
    recovered = store.recover(pair["template"])
    if ex._freeze(recovered["contender"]) != pair["new_frozen"]:
        raise RuntimeError("Stage-9E corrupted head did not recover highest valid slot")
    return True


def _dual_slot_fail_closed(pair: dict, root: Path) -> bool:
    store = AtomicCheckpointStore(root / "fail_closed")
    store.write(pair["old_compact"]); store.write(pair["new_compact"])
    store._slot_path("a").write_bytes(b"corrupt-a"); store._slot_path("b").write_bytes(b"corrupt-b")
    try:
        store.recover(pair["template"])
    except ValueError:
        return True
    raise RuntimeError("Stage-9E unrecoverable dual-slot corruption did not fail closed")


def _unknown_schema_rejected(pair: dict, root: Path) -> bool:
    packet = json.loads(s9d.encode_envelope(pair["old_compact"]).decode("utf-8"))
    packet["schema"] = "ghost.stage9d.compact-restart-envelope.v999"
    try:
        AtomicCheckpointStore(root / "future_schema").import_stage9d(_canonical_bytes(packet), pair["template"])
    except ValueError:
        return True
    raise RuntimeError("Stage-9E accepted an unknown predecessor envelope schema")


def _timing_probe(pair: dict, root: Path, samples: int) -> dict:
    writes = []; recovers = []
    for index in range(samples):
        store = AtomicCheckpointStore(root / f"timing_{index}")
        start = perf_counter_ns(); store.write(pair["new_compact"]); writes.append((perf_counter_ns() - start) / 1000.0)
        start = perf_counter_ns(); store.recover(pair["template"]); recovers.append((perf_counter_ns() - start) / 1000.0)
    return {"samples": samples, "atomic_write_median_us": s9d._median(writes), "recover_median_us": s9d._median(recovers)}


def _profile_level(level: dict, root: Path, *, timing: bool, samples: int) -> dict:
    pair = _checkpoint_pair(level)
    migration = _migration_check(pair, root)
    crashes = _crash_matrix(pair, root)
    corruption = {
        "active_slot_fallback": _active_slot_fallback(pair, root),
        "corrupt_head_highest_valid": _corrupt_head_fallback(pair, root),
        "dual_slot_corruption_fails_closed": _dual_slot_fail_closed(pair, root),
        "unknown_predecessor_schema_rejected": _unknown_schema_rejected(pair, root),
    }
    slot_bytes = AtomicCheckpointStore._slot_bytes(pair["new_compact"], 2)
    return {
        "level": deepcopy(level), "migration": migration, "crash_recovery": crashes,
        "all_process_crash_cases_pass": all(row["pass"] for row in crashes.values()),
        "corruption_recovery": corruption,
        "query_correct_after_new_checkpoint": _query_correct(pair["new_compact"], pair["new_ledger"]),
        "storage": {
            "full_snapshot_bytes": inc.json_bytes(pair["new_frozen"]),
            "compact_bytes": inc.json_bytes(pair["new_compact"]),
            "slot_packet_bytes": len(slot_bytes),
        },
        "timing": _timing_probe(pair, root, samples) if timing else None,
    }

def _aggregate(levels: list[dict]) -> dict:
    return {
        "all_stage9d_migrations_exact": all(
            row["migration"]["exact_state"] and row["migration"]["continuation_equal"] for row in levels
        ),
        "all_process_crash_cases_pass": all(row["all_process_crash_cases_pass"] for row in levels),
        "all_corruption_recovery_cases_pass": all(all(row["corruption_recovery"].values()) for row in levels),
        "all_queries_correct": all(row["query_correct_after_new_checkpoint"] for row in levels),
    }


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    with tempfile.TemporaryDirectory(prefix="ghost_stage9e_") as tmp:
        root = Path(tmp)
        levels = [_profile_level(deepcopy(level), root / level["id"], timing=timing, samples=timing_samples) for level in _LEVELS]
    result = {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "constraints": {
            "production_ghost_modified": False,
            "research_only": True,
            "actual_process_exit_fault_injection": True,
            "fsync_and_atomic_replace_exercised": True,
            "power_loss_durability_not_proven": True,
            "single_writer_only": True,
            "concurrent_writer_safety_not_tested": True,
            "backward_migration_from_stage9d_tested": True,
            "forward_unknown_schema_compatibility_not_claimed": True,
            "checksum_is_integrity_not_authentication": True,
            "timing_is_telemetry_not_gate": True,
            "no_weighted_composite_score": True,
        },
        "claim_boundary": (
            "Stage 9E tests a research-only two-slot checkpoint protocol around the Stage-9D compact envelope. It uses actual child-process termination at seven write boundaries, requires recovery to the last committed generation before head replacement and the new generation after it, validates exact Ghost state and post-recovery continuation, exercises fsync plus atomic replace, falls back from one corrupted committed slot or corrupted head, and imports the exact Stage-9D envelope format without semantic drift. It does not prove sudden-power-loss durability on every filesystem, multi-process/concurrent-writer safety, authenticated tamper resistance, or forward compatibility with unknown future schemas."
        ),
    }
    result.update(_aggregate(levels))
    return result
