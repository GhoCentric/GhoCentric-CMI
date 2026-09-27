from copy import deepcopy
import inspect

import pytest

from ghost import GhostAPI
from ghost import _persistence_runtime as runtime
from ghost_research import v112_persistence_runtime_stage10b as s10b


class DummyAPI:
    pass


class FakeStore:
    def __init__(self, directory, *, write_result=None, loaded=None, error=None):
        self.directory = directory
        self.enabled = True
        self.write_result = write_result or {
            "attempted": True,
            "candidate_usable": True,
            "generation": 1,
            "reason": None,
        }
        self.loaded = loaded
        self.error = error
        self.write_calls = 0
        self.rollback_calls = 0

    def write(self, snapshot):
        self.write_calls += 1
        if self.error is not None:
            raise self.error
        return deepcopy(self.write_result)

    def load(self):
        if self.loaded is None:
            raise RuntimeError("fake load missing")
        return deepcopy(self.loaded)

    def rollback_shadow(self):
        self.rollback_calls += 1


def _api_snapshot():
    return GhostAPI().snapshot()


def _wrapped(snapshot=None):
    return runtime._wrap_snapshot(snapshot or _api_snapshot())


def _healthy_store(tmp_path, snapshot, *, source="candidate"):
    return FakeStore(
        tmp_path,
        loaded={
            "snapshot": _wrapped(snapshot),
            "source": source,
            "generation": 1,
            "fallback_reason": None if source == "candidate" else "forced",
        },
    )


def test_wrapper_roundtrip_is_copy_isolated():
    snapshot = _api_snapshot()
    wrapped = runtime._wrap_snapshot(snapshot)
    wrapped["api"]["extra"] = "local"
    assert "extra" not in snapshot
    restored = runtime._unwrap_snapshot(runtime._wrap_snapshot(snapshot))
    restored["extra"] = "copy"
    assert "extra" not in snapshot


def test_wrap_requires_dict():
    with pytest.raises(TypeError, match="snapshot"):
        runtime._wrap_snapshot([])


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"schema": "wrong", "api": {}},
        {"schema": runtime.RUNTIME_WRAPPER_SCHEMA, "api": []},
        {"schema": runtime.RUNTIME_WRAPPER_SCHEMA, "api": {}, "extra": 1},
    ],
)
def test_unwrap_rejects_invalid_wrapper(bad):
    with pytest.raises(ValueError, match="wrapper"):
        runtime._unwrap_snapshot(bad)


@pytest.mark.parametrize(
    "kwargs,exception",
    [
        ({"enabled": 1}, TypeError),
        ({"failure_threshold": True}, ValueError),
        ({"failure_threshold": 0}, ValueError),
        ({"failure_threshold": 1.5}, ValueError),
        ({"verify_load": 1}, TypeError),
    ],
)
def test_runtime_constructor_validation(tmp_path, kwargs, exception):
    with pytest.raises(exception):
        runtime.PersistenceShadowRuntime(tmp_path, **kwargs)


def test_observe_disabled_skips_without_attempt(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path, enabled=False)
    observer.observe_snapshot(_api_snapshot())
    assert observer.status()["skipped_disabled"] == 1
    assert observer.status()["attempts"] == 0


def test_observe_open_circuit_skips_without_attempt(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.circuit_open = True
    observer.observe_snapshot(_api_snapshot())
    assert observer.status()["skipped_circuit_open"] == 1
    assert observer.status()["attempts"] == 0


def test_observe_success_verified_candidate(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = _healthy_store(tmp_path, snapshot)
    observer.observe_snapshot(snapshot)
    health = observer.status()
    assert health["attempts"] == 1 and health["successes"] == 1
    assert health["last_generation"] == 1 and health["last_source"] == "candidate"
    assert health["last_reason"] is None and health["circuit_open"] is False


def test_observe_success_without_verified_load(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path, verify_load=False)
    observer.store = FakeStore(tmp_path)
    observer.observe_snapshot(snapshot)
    assert observer.status()["last_source"] == "candidate_unverified"
    assert observer.status()["successes"] == 1


def test_candidate_unusable_records_failure_below_threshold(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path, failure_threshold=2)
    observer.store = FakeStore(
        tmp_path,
        write_result={
            "attempted": True,
            "candidate_usable": False,
            "generation": 3,
            "reason": "forced-unusable",
        },
    )
    observer.observe_snapshot(_api_snapshot())
    health = observer.status()
    assert health["failures"] == 1 and health["circuit_open"] is False
    assert health["last_generation"] == 3 and health["last_reason"] == "forced-unusable"


def test_candidate_unusable_without_reason_uses_default_and_opens_circuit(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = FakeStore(
        tmp_path,
        write_result={
            "attempted": True,
            "candidate_usable": False,
            "generation": 1,
            "reason": None,
        },
    )
    observer.observe_snapshot(_api_snapshot())
    assert observer.status()["last_reason"] == "candidate_unusable"
    assert observer.status()["circuit_open"] is True


def test_verified_state_mismatch_opens_circuit(tmp_path):
    snapshot = _api_snapshot()
    altered = deepcopy(snapshot); altered["ghost_version"] = "drift"
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = _healthy_store(tmp_path, altered)
    observer.observe_snapshot(snapshot)
    assert observer.status()["last_reason"] == "verified_state_mismatch"
    assert observer.status()["circuit_open"] is True


def test_verified_candidate_fallback_opens_circuit(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = _healthy_store(tmp_path, snapshot, source="baseline")
    observer.observe_snapshot(snapshot)
    assert observer.status()["last_reason"] == "verified_candidate_fallback:forced"


def test_verified_candidate_fallback_without_reason_uses_unknown(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    store = _healthy_store(tmp_path, snapshot, source="baseline")
    store.loaded["fallback_reason"] = None
    observer.store = store
    observer.observe_snapshot(snapshot)
    assert observer.status()["last_reason"] == "verified_candidate_fallback:unknown"


@pytest.mark.parametrize(
    "error",
    [OSError("disk"), TypeError("type"), ValueError("value"), KeyError("key"), RuntimeError("runtime")],
)
def test_expected_store_failures_fail_open_and_record_type(tmp_path, error):
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = FakeStore(tmp_path, error=error)
    observer.observe_snapshot(_api_snapshot())
    health = observer.status()
    assert health["failures"] == 1 and health["circuit_open"] is True
    assert health["last_reason"].startswith(type(error).__name__ + ":")


def test_success_resets_consecutive_failure_state(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path, failure_threshold=3)
    observer._record_failure("first")
    observer.store = _healthy_store(tmp_path, snapshot)
    observer.observe_snapshot(snapshot)
    health = observer.status()
    assert health["consecutive_failures"] == 0 and health["last_reason"] is None
    assert health["failures"] == 1 and health["successes"] == 1


def test_load_verified_snapshot_returns_api_snapshot(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = _healthy_store(tmp_path, snapshot)
    assert observer.load_verified_snapshot() == snapshot


def test_load_verified_snapshot_rejects_fallback(tmp_path):
    snapshot = _api_snapshot()
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    observer.store = _healthy_store(tmp_path, snapshot, source="baseline")
    with pytest.raises(RuntimeError, match="fell back"):
        observer.load_verified_snapshot()


def test_reset_circuit_requires_enabled_runtime(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path, enabled=False)
    with pytest.raises(RuntimeError, match="disabled"):
        observer.reset_circuit()


def test_reset_circuit_clears_only_live_failure_state(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path, failure_threshold=1)
    observer._record_failure("forced")
    observer.reset_circuit()
    health = observer.status()
    assert health["circuit_open"] is False and health["consecutive_failures"] == 0
    assert health["last_reason"] is None and health["failures"] == 1


def test_disable_validates_rollback_flag(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    with pytest.raises(TypeError, match="rollback"):
        observer.disable(rollback=1)


def test_disable_without_existing_directory_is_inert(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path / "missing")
    observer.disable(rollback=True)
    assert observer.enabled is False and observer.store.enabled is False
    assert observer.circuit_open is False


def test_disable_with_rollback_calls_store(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    fake = FakeStore(tmp_path)
    observer.store = fake
    observer.disable(rollback=True)
    assert fake.rollback_calls == 1 and fake.enabled is False


def test_disable_without_rollback_does_not_call_store(tmp_path):
    observer = runtime.PersistenceShadowRuntime(tmp_path)
    fake = FakeStore(tmp_path)
    observer.store = fake
    observer.disable(rollback=False)
    assert fake.rollback_calls == 0 and fake.enabled is False


def test_attach_enabled_sets_private_hook_and_detach_disables(tmp_path):
    api = DummyAPI()
    observer = runtime.attach_persistence_shadow(api, tmp_path, enabled=True)
    assert api.__dict__[runtime._HOOK_ATTR] is observer
    status = runtime.detach_persistence_shadow(api)
    assert status["enabled"] is False and runtime._HOOK_ATTR not in api.__dict__


def test_attach_disabled_removes_existing_hook(tmp_path):
    api = DummyAPI(); api.__dict__[runtime._HOOK_ATTR] = object()
    observer = runtime.attach_persistence_shadow(api, tmp_path, enabled=False)
    assert runtime._HOOK_ATTR not in api.__dict__ and observer.enabled is False


def test_detach_missing_hook_returns_none():
    assert runtime.detach_persistence_shadow(DummyAPI()) is None


def test_detach_can_request_rollback(tmp_path):
    api = DummyAPI(); observer = runtime.attach_persistence_shadow(api, tmp_path)
    fake = FakeStore(tmp_path); tmp_path.mkdir(exist_ok=True); observer.store = fake
    status = runtime.detach_persistence_shadow(api, rollback=True)
    assert fake.rollback_calls == 1 and status["enabled"] is False


def test_real_ghostapi_snapshot_hook_writes_exact_shadow(tmp_path):
    api = GhostAPI()
    observer = runtime.attach_persistence_shadow(api, tmp_path)
    snapshot = api.snapshot()
    assert observer.load_verified_snapshot() == snapshot
    assert observer.status()["successes"] == 1


def test_real_ghostapi_disabled_attach_changes_no_signature_or_snapshot(tmp_path):
    baseline = GhostAPI(); candidate = GhostAPI()
    before = baseline.snapshot()
    observer = runtime.attach_persistence_shadow(candidate, tmp_path, enabled=False)
    after = candidate.snapshot()
    assert before == after and observer.status()["attempts"] == 0
    assert inspect.signature(GhostAPI.__init__) == inspect.signature(type(baseline).__init__)


def test_from_snapshot_does_not_inherit_private_runtime_configuration(tmp_path):
    api = GhostAPI(); runtime.attach_persistence_shadow(api, tmp_path)
    snapshot = api.snapshot()
    restored = GhostAPI.from_snapshot(snapshot)
    assert runtime._HOOK_ATTR not in restored.__dict__ and restored.snapshot() == snapshot


def test_stage10b_mutation_helper_is_deterministic():
    left = GhostAPI(); right = GhostAPI()
    assert s10b._mutate(left) == s10b._mutate(right)
    assert left.snapshot() == right.snapshot()


def test_stage10b_circuit_probe_detects_fail_open(tmp_path):
    assert s10b._circuit_probe({"id": "events_224", "ambient_events": 224}, tmp_path) is True


def test_stage10b_profile_rejects_snapshot_drift(tmp_path, monkeypatch):
    class DriftAPI:
        def __init__(self, value): self.value = value
        def snapshot(self): return {"value": self.value}
    values = iter([DriftAPI(1), DriftAPI(1), DriftAPI(2), DriftAPI(3)])
    monkeypatch.setattr(s10b, "_api_from_level", lambda level: next(values))
    monkeypatch.setattr(s10b, "attach_persistence_shadow", lambda *args, **kwargs: runtime.PersistenceShadowRuntime(tmp_path, enabled=False))
    with pytest.raises(RuntimeError, match="snapshot output"):
        s10b._profile_level({"id": "x", "ambient_events": 1}, tmp_path)


def test_stage10b_profile_rejects_continuation_return_drift(tmp_path, monkeypatch):
    original_mutate = s10b._mutate
    calls = {"count": 0}
    def drift(api):
        calls["count"] += 1
        result = original_mutate(api)
        if calls["count"] == 2:
            result = deepcopy(result); result["drift"] = True
        return result
    monkeypatch.setattr(s10b, "_mutate", drift)
    with pytest.raises(RuntimeError, match="return packet"):
        s10b._profile_level({"id": "events_224", "ambient_events": 224}, tmp_path)


def test_stage10b_gates_identify_false_rows():
    row = {
        "disabled_attach_is_inert": True,
        "enabled_snapshot_output_exact": True,
        "verified_shadow_restore_exact": True,
        "continuation_exact": True,
        "configuration_not_serialized": True,
        "health_is_nominal": True,
        "circuit_breaker_fail_open": True,
    }
    assert all(s10b._gates([row]).values())
    bad = deepcopy(row); bad["continuation_exact"] = False
    assert s10b._gates([bad])["continuation_parity"] is False


def test_stage10b_full_experiment_passes_all_gates():
    result = s10b.run_experiment()
    assert result["strict_verdict"] == s10b.VERDICT
    assert result["all_gates_pass"] is True
    assert len(result["levels"]) == 4
    assert all(result["gates"].values())
