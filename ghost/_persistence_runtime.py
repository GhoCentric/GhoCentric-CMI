"""Internal opt-in bridge from GhostAPI.snapshot() to shadow persistence."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Union

from ._persistence_shadow import ShadowPersistenceCandidate

RUNTIME_WRAPPER_SCHEMA = "ghost.persistence.runtime-shadow.v1"
_HOOK_ATTR = "_persistence_shadow_runtime"
_EXPECTED_FAILURES = (OSError, TypeError, ValueError, KeyError, RuntimeError)


def _wrap_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        raise TypeError("GhostAPI snapshot must be a dict")
    return {"schema": RUNTIME_WRAPPER_SCHEMA, "api": deepcopy(snapshot)}


def _unwrap_snapshot(value: Any) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "api"}
        or value.get("schema") != RUNTIME_WRAPPER_SCHEMA
        or not isinstance(value.get("api"), dict)
    ):
        raise ValueError("runtime shadow wrapper is invalid")
    return deepcopy(value["api"])


def _validate_runtime_options(enabled, failure_threshold, verify_load) -> None:
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a bool")
    if (
        isinstance(failure_threshold, bool)
        or not isinstance(failure_threshold, int)
        or failure_threshold < 1
    ):
        raise ValueError("failure_threshold must be a positive integer")
    if not isinstance(verify_load, bool):
        raise TypeError("verify_load must be a bool")


class PersistenceShadowRuntime:
    """Non-authoritative snapshot observer with a local fail-open circuit breaker."""

    def __init__(
        self,
        directory: Union[str, Path],
        *,
        enabled: bool = True,
        failure_threshold: int = 1,
        verify_load: bool = True,
    ) -> None:
        _validate_runtime_options(enabled, failure_threshold, verify_load)
        self.store = ShadowPersistenceCandidate(directory, enabled=enabled)
        self.enabled = enabled
        self.failure_threshold = failure_threshold
        self.verify_load = verify_load
        self.attempts = 0
        self.successes = 0
        self.failures = 0
        self.consecutive_failures = 0
        self.skipped_disabled = 0
        self.skipped_circuit_open = 0
        self.circuit_open = False
        self.last_generation = None
        self.last_source = None
        self.last_reason = None

    def _record_failure(self, reason: str) -> None:
        self.failures += 1
        self.consecutive_failures += 1
        self.last_reason = str(reason)
        self.last_source = "baseline_or_unavailable"
        if self.consecutive_failures >= self.failure_threshold:
            self.circuit_open = True

    def _verify_write(self, snapshot: dict, result: dict) -> tuple[bool, str, str | None]:
        self.last_generation = result["generation"]
        if not result["candidate_usable"]:
            return False, "baseline_or_unavailable", result.get("reason") or "candidate_unusable"
        if not self.verify_load:
            return True, "candidate_unverified", None
        loaded = self.store.load()
        restored = _unwrap_snapshot(loaded["snapshot"])
        if restored != snapshot:
            return False, "baseline_or_unavailable", "verified_state_mismatch"
        if loaded["source"] != "candidate":
            reason = str(loaded.get("fallback_reason") or "unknown")
            return False, "baseline_or_unavailable", "verified_candidate_fallback:" + reason
        return True, "candidate", None

    def observe_snapshot(self, snapshot: dict) -> None:
        """Observe one real GhostAPI snapshot without ever changing its return value."""
        if not self.enabled:
            self.skipped_disabled += 1
            return
        if self.circuit_open:
            self.skipped_circuit_open += 1
            return
        self.attempts += 1
        try:
            result = self.store.write(_wrap_snapshot(snapshot))
            ok, source, reason = self._verify_write(snapshot, result)
        except _EXPECTED_FAILURES as exc:
            self._record_failure(type(exc).__name__ + ":" + str(exc))
            return
        if not ok:
            self._record_failure(reason or "candidate_unusable")
            return
        self.successes += 1
        self.consecutive_failures = 0
        self.last_source = source
        self.last_reason = None

    def load_verified_snapshot(self) -> dict:
        """Load the shadow packet and return its exact embedded GhostAPI snapshot."""
        loaded = self.store.load()
        snapshot = _unwrap_snapshot(loaded["snapshot"])
        if loaded["source"] != "candidate":
            raise RuntimeError(
                "verified shadow load fell back to baseline: "
                + str(loaded.get("fallback_reason") or "unknown")
            )
        return snapshot

    def reset_circuit(self) -> None:
        if not self.enabled:
            raise RuntimeError("cannot reset a disabled persistence shadow runtime")
        self.circuit_open = False
        self.consecutive_failures = 0
        self.last_reason = None

    def disable(self, *, rollback: bool = False) -> None:
        if not isinstance(rollback, bool):
            raise TypeError("rollback must be a bool")
        if rollback and self.store.enabled and self.store.directory.exists():
            self.store.rollback_shadow()
        self.enabled = False
        self.store.enabled = False
        self.circuit_open = False

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "circuit_open": self.circuit_open,
            "failure_threshold": self.failure_threshold,
            "verify_load": self.verify_load,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "skipped_disabled": self.skipped_disabled,
            "skipped_circuit_open": self.skipped_circuit_open,
            "last_generation": self.last_generation,
            "last_source": self.last_source,
            "last_reason": self.last_reason,
        }


def attach_persistence_shadow(
    api,
    directory: Union[str, Path],
    *,
    enabled: bool = True,
    failure_threshold: int = 1,
    verify_load: bool = True,
) -> PersistenceShadowRuntime:
    """Attach the internal observer to one GhostAPI instance only when enabled."""
    runtime = PersistenceShadowRuntime(
        directory,
        enabled=enabled,
        failure_threshold=failure_threshold,
        verify_load=verify_load,
    )
    if enabled:
        setattr(api, _HOOK_ATTR, runtime)
    else:
        api.__dict__.pop(_HOOK_ATTR, None)
    return runtime


def detach_persistence_shadow(api, *, rollback: bool = False):
    """Detach an attached observer; this is intentionally not a public GhostAPI method."""
    runtime = api.__dict__.pop(_HOOK_ATTR, None)
    if runtime is None:
        return None
    runtime.disable(rollback=rollback)
    return runtime.status()
