"""Internal opt-in shadow persistence candidate; never authoritative by default."""
from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional, Union

from ._persistence_codec import compact_snapshot, expand_snapshot

BASELINE_SCHEMA = "ghost.persistence.shadow-baseline.v1"
CANDIDATE_SCHEMA = "ghost.persistence.shadow-compact.v1"
MANIFEST_SCHEMA = "ghost.persistence.shadow-manifest.v1"
FORMAT_VERSION = 1
_SUPPORTED_CANDIDATE_VERSIONS = {FORMAT_VERSION}


class ShadowWriterBusyError(RuntimeError):
    """Raised when another process holds the local shadow-writer lease."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(label + " must be 64 hex characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(label + " must be 64 hex characters") from exc
    return value.lower()


def _json_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError("persistence file is unreadable: " + path.name) from exc


def _json_object(path: Path) -> dict:
    try:
        value = json.loads(_json_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("persistence file is not valid JSON: " + path.name) from exc
    if not isinstance(value, dict):
        raise ValueError("persistence file must contain a JSON object: " + path.name)
    return value


def _fsync_dir(directory: Path) -> None:
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class _WriterLease(AbstractContextManager):
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / ".shadow-writer.lock"
        self._handle = None

    def __enter__(self) -> "_WriterLease":
        try:
            import fcntl
        except ImportError as exc:
            raise RuntimeError("shadow persistence requires advisory flock support when enabled") from exc
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise ShadowWriterBusyError("shadow persistence writer lease is already held") from exc
            raise
        self._handle = (handle, fcntl)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        held = self._handle
        self._handle = None
        if held is not None:
            handle, fcntl = held
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        return False


class ShadowPersistenceCandidate:
    """Dual-write full baseline + compact candidate with exact fallback semantics."""

    def __init__(self, directory: Union[str, Path], *, enabled: bool = False) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        self.directory = Path(directory)
        self.enabled = enabled
        self.baseline_path = self.directory / "baseline.json"
        self.candidate_path = self.directory / "candidate.json"
        self.manifest_path = self.directory / "manifest.json"

    def _lease(self) -> _WriterLease:
        return _WriterLease(self.directory)

    @staticmethod
    def _baseline_packet(snapshot: dict, generation: int) -> dict:
        if not isinstance(snapshot, dict):
            raise TypeError("snapshot must be a dict")
        payload = deepcopy(snapshot)
        digest = _sha(_canonical_bytes(payload))
        return {
            "schema": BASELINE_SCHEMA,
            "format_version": FORMAT_VERSION,
            "generation": generation,
            "snapshot_sha256": digest,
            "snapshot": payload,
        }

    @staticmethod
    def _candidate_packet(compact: dict, generation: int, baseline_sha256: str) -> dict:
        payload = deepcopy(compact)
        return {
            "schema": CANDIDATE_SCHEMA,
            "format_version": FORMAT_VERSION,
            "generation": generation,
            "baseline_sha256": _digest(baseline_sha256, "baseline digest"),
            "compact_sha256": _sha(_canonical_bytes(payload)),
            "compact": payload,
        }

    @staticmethod
    def _manifest_packet(generation: int, candidate_usable: bool, reason: Optional[str]) -> dict:
        if reason is not None and not isinstance(reason, str):
            raise TypeError("manifest reason must be a string or None")
        return {
            "schema": MANIFEST_SCHEMA,
            "format_version": FORMAT_VERSION,
            "generation": generation,
            "candidate_usable": candidate_usable,
            "reason": reason,
        }

    @staticmethod
    def _decode_baseline(packet: dict) -> tuple:
        expected = {"schema", "format_version", "generation", "snapshot_sha256", "snapshot"}
        if set(packet) != expected or packet.get("schema") != BASELINE_SCHEMA:
            raise ValueError("baseline packet shape/schema mismatch")
        if packet["format_version"] != FORMAT_VERSION:
            raise ValueError("baseline format version is unsupported")
        generation = packet["generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("baseline generation must be positive")
        snapshot = packet["snapshot"]
        if not isinstance(snapshot, dict):
            raise ValueError("baseline snapshot must be a dict")
        expected_digest = _digest(packet["snapshot_sha256"], "baseline digest")
        actual_digest = _sha(_canonical_bytes(snapshot))
        if actual_digest != expected_digest:
            raise ValueError("baseline snapshot integrity mismatch")
        return generation, expected_digest, deepcopy(snapshot)

    @staticmethod
    def _decode_candidate(packet: dict, generation: int, baseline_sha256: str) -> dict:
        expected = {
            "schema", "format_version", "generation", "baseline_sha256", "compact_sha256", "compact"
        }
        if set(packet) != expected or packet.get("schema") != CANDIDATE_SCHEMA:
            raise ValueError("candidate packet shape/schema mismatch")
        version = packet["format_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("candidate format version must be an integer")
        if version not in _SUPPORTED_CANDIDATE_VERSIONS:
            raise ValueError("candidate format version is unsupported")
        if packet["generation"] != generation:
            raise ValueError("candidate generation does not match baseline")
        if _digest(packet["baseline_sha256"], "candidate baseline digest") != baseline_sha256:
            raise ValueError("candidate baseline digest does not match baseline")
        compact = packet["compact"]
        if not isinstance(compact, dict):
            raise ValueError("candidate compact payload must be a dict")
        expected_digest = _digest(packet["compact_sha256"], "candidate compact digest")
        if _sha(_canonical_bytes(compact)) != expected_digest:
            raise ValueError("candidate compact integrity mismatch")
        return deepcopy(compact)

    @staticmethod
    def _decode_manifest(packet: dict, generation: int) -> tuple:
        expected = {"schema", "format_version", "generation", "candidate_usable", "reason"}
        if set(packet) != expected or packet.get("schema") != MANIFEST_SCHEMA:
            raise ValueError("shadow manifest shape/schema mismatch")
        if packet["format_version"] != FORMAT_VERSION:
            raise ValueError("shadow manifest format version is unsupported")
        if packet["generation"] != generation:
            raise ValueError("shadow manifest generation does not match baseline")
        if not isinstance(packet["candidate_usable"], bool):
            raise ValueError("shadow manifest candidate_usable must be bool")
        reason = packet["reason"]
        if reason is not None and not isinstance(reason, str):
            raise ValueError("shadow manifest reason must be string or null")
        return packet["candidate_usable"], reason

    def _next_generation(self) -> int:
        if not self.baseline_path.exists():
            return 1
        packet = _json_object(self.baseline_path)
        generation, _, _ = self._decode_baseline(packet)
        return generation + 1

    def _write_manifest_best_effort(self, generation: int, usable: bool, reason: Optional[str]) -> bool:
        packet = self._manifest_packet(generation, usable, reason)
        try:
            _atomic_write(self.manifest_path, _canonical_bytes(packet))
        except OSError:
            return False
        return True

    def _persist_candidate(self, snapshot: dict, generation: int, baseline_sha: str) -> Optional[str]:
        try:
            compact = compact_snapshot(snapshot)
            if expand_snapshot(compact) != snapshot:
                raise RuntimeError("candidate compact roundtrip drifted")
            packet = self._candidate_packet(compact, generation, baseline_sha)
            _atomic_write(self.candidate_path, _canonical_bytes(packet))
            verified = self._decode_candidate(_json_object(self.candidate_path), generation, baseline_sha)
            if expand_snapshot(verified) != snapshot:
                raise RuntimeError("persisted candidate roundtrip drifted")
        except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
            return type(exc).__name__ + ":" + str(exc)
        return None

    def write(self, snapshot: dict) -> dict:
        if not self.enabled:
            return {"attempted": False, "candidate_usable": False, "generation": None, "reason": "disabled"}
        with self._lease():
            generation = self._next_generation()
            baseline_packet = self._baseline_packet(snapshot, generation)
            _atomic_write(self.baseline_path, _canonical_bytes(baseline_packet))
            reason = self._persist_candidate(snapshot, generation, baseline_packet["snapshot_sha256"])
            if reason is not None:
                self._write_manifest_best_effort(generation, False, reason)
                return {"attempted": True, "candidate_usable": False, "generation": generation, "reason": reason}
            if not self._write_manifest_best_effort(generation, True, None):
                return {"attempted": True, "candidate_usable": False, "generation": generation, "reason": "manifest_write_failed"}
            return {"attempted": True, "candidate_usable": True, "generation": generation, "reason": None}

    def _baseline(self) -> tuple:
        return self._decode_baseline(_json_object(self.baseline_path))

    @staticmethod
    def _fallback(snapshot: dict, generation: int, reason: str) -> dict:
        return {
            "snapshot": deepcopy(snapshot),
            "source": "baseline",
            "generation": generation,
            "fallback_reason": reason,
        }

    def load(self) -> dict:
        if not self.enabled:
            raise RuntimeError("shadow persistence is disabled")
        generation, baseline_sha, baseline = self._baseline()
        try:
            manifest = _json_object(self.manifest_path)
            usable, reason = self._decode_manifest(manifest, generation)
            if not usable:
                return self._fallback(baseline, generation, reason or "candidate_marked_unusable")
            candidate = self._decode_candidate(_json_object(self.candidate_path), generation, baseline_sha)
            expanded = expand_snapshot(candidate)
            if expanded != baseline:
                return self._fallback(baseline, generation, "candidate_state_mismatch")
        except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
            return self._fallback(baseline, generation, type(exc).__name__ + ":" + str(exc))
        return {
            "snapshot": expanded,
            "source": "candidate",
            "generation": generation,
            "fallback_reason": None,
        }

    def rollback_shadow(self) -> None:
        if not self.enabled:
            raise RuntimeError("shadow persistence is disabled")
        with self._lease():
            for path in (self.candidate_path, self.manifest_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            _fsync_dir(self.directory)
