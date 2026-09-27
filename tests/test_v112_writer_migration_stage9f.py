from copy import deepcopy
import errno
import json
from pathlib import Path
import threading

import pytest

from ghost_research import v112_writer_migration_stage9f as s9f

LEVEL = {"id": "events_224", "ambient_events": 224}


@pytest.fixture(scope="module")
def pair():
    return s9f.s9e._checkpoint_pair(LEVEL)


def test_template_packet_roundtrip(pair):
    packet = s9f._template_packet(pair["template"])
    restored = s9f._template_from_packet(packet)
    assert restored.agent_ids == pair["template"].agent_ids
    assert restored.source_ids == pair["template"].source_ids
    assert restored.subject_ids == pair["template"].subject_ids


def test_template_packet_rejects_bad_template(pair):
    bad = s9f.SimpleNamespace(
        agent_ids=[], source_ids=list(pair["template"].source_ids), subject_ids=list(pair["template"].subject_ids)
    )
    with pytest.raises(ValueError, match="agent_ids"):
        s9f._template_packet(bad)
    bad.agent_ids = [""]
    with pytest.raises(ValueError, match="agent_ids"):
        s9f._template_packet(bad)


def test_template_from_packet_rejects_shape_and_values(pair):
    with pytest.raises(ValueError, match="invalid shape"):
        s9f._template_from_packet([])
    packet = s9f._template_packet(pair["template"])
    bad = deepcopy(packet); bad["source_ids"] = "nope"
    with pytest.raises(ValueError, match="source_ids"):
        s9f._template_from_packet(bad)
    bad = deepcopy(packet); bad["subject_ids"] = [""]
    with pytest.raises(ValueError, match="subject_ids"):
        s9f._template_from_packet(bad)


def test_trip_migration_paths(monkeypatch):
    s9f._trip_migration(None, "x", "raise")
    with pytest.raises(s9f.MigrationCrash, match="x"):
        s9f._trip_migration("x", "x", "raise")
    monkeypatch.setattr(s9f.os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit) as exc:
        s9f._trip_migration("x", "x", "exit")
    assert exc.value.code == s9f.MIGRATION_CRASH_EXIT_CODE
    with pytest.raises(ValueError, match="crash mode"):
        s9f._trip_migration("x", "x", "bad")


def test_writer_lease_acquire_release_and_empty_exit(tmp_path):
    lease = s9f.WriterLease(tmp_path / "lease")
    assert lease.__enter__() is lease
    assert lease.path.exists()
    assert lease.__exit__(None, None, None) is False
    assert lease.__exit__(None, None, None) is False


def test_writer_lease_rejects_competing_lock(tmp_path):
    directory = tmp_path / "busy"
    with s9f.WriterLease(directory):
        with pytest.raises(s9f.WriterBusyError, match="already held"):
            with s9f.WriterLease(directory):
                pass


def test_writer_lease_reraises_nonbusy_oserror(tmp_path, monkeypatch):
    original = s9f.fcntl.flock
    def broken(fd, flags):
        if flags & s9f.fcntl.LOCK_NB:
            raise OSError(errno.EIO, "io")
        return original(fd, flags)
    monkeypatch.setattr(s9f.fcntl, "flock", broken)
    with pytest.raises(OSError) as exc:
        with s9f.WriterLease(tmp_path / "io"):
            pass
    assert exc.value.errno == errno.EIO


def test_locked_write_and_recover_committed(tmp_path, pair):
    store = s9f.LockedCheckpointStore(tmp_path / "store")
    assert store.write_locked(pair["old_compact"]) == 1
    row = store.recover_committed(pair["template"])
    assert row["generation"] == 1
    assert s9f.ex._freeze(row["contender"]) == pair["old_frozen"]


def test_recover_committed_missing_head_rejects_orphan(tmp_path, pair):
    store = s9f.LockedCheckpointStore(tmp_path / "orphan")
    with pytest.raises(s9f.s9e.SimulatedCrash):
        s9f.s9e.AtomicCheckpointStore.write(
            store, pair["old_compact"], crash_at="after_slot_replace", crash_mode="raise"
        )
    assert not store.head_path.exists()
    with pytest.raises(ValueError, match="no committed checkpoint head"):
        store.recover_committed(pair["template"])


def test_recover_committed_corrupt_head_uses_stage9e_fallback(tmp_path, pair):
    store = s9f.LockedCheckpointStore(tmp_path / "corrupt-head")
    store.write_locked(pair["old_compact"])
    store.head_path.write_bytes(b"{")
    row = store.recover_committed(pair["template"])
    assert row["generation"] == 1


def test_migrate_rejects_unknown_crash_point(tmp_path, pair):
    store = s9f.LockedCheckpointStore(tmp_path / "unknown")
    blob = s9f.s9d.encode_envelope(pair["old_compact"])
    with pytest.raises(ValueError, match="unknown Stage-9F"):
        store.migrate_stage9d(blob, pair["template"], crash_at="nope")


def test_migrate_custom_raise_points(tmp_path, pair):
    blob = s9f.s9d.encode_envelope(pair["old_compact"])
    for point in ("after_lock_acquired", "after_source_validated"):
        store = s9f.LockedCheckpointStore(tmp_path / point)
        with pytest.raises(s9f.MigrationCrash, match=point):
            store.migrate_stage9d(blob, pair["template"], crash_at=point, crash_mode="raise")


def test_migrate_stage9e_raise_point_and_retry(tmp_path, pair):
    blob = s9f.s9d.encode_envelope(pair["old_compact"])
    store = s9f.LockedCheckpointStore(tmp_path / "write-crash")
    with pytest.raises(s9f.s9e.SimulatedCrash, match="after_slot_fsync"):
        store.migrate_stage9d(blob, pair["template"], crash_at="after_slot_fsync", crash_mode="raise")
    assert store.migrate_stage9d(blob, pair["template"]) == 1


def test_migrate_idempotent_and_conflict(tmp_path, pair):
    store = s9f.LockedCheckpointStore(tmp_path / "idem")
    old_blob = s9f.s9d.encode_envelope(pair["old_compact"])
    new_blob = s9f.s9d.encode_envelope(pair["new_compact"])
    assert store.migrate_stage9d(old_blob, pair["template"]) == 1
    assert store.migrate_stage9d(old_blob, pair["template"]) == 1
    with pytest.raises(ValueError, match="different committed state"):
        store.migrate_stage9d(new_blob, pair["template"])


def test_wait_for_path_success_and_timeout(tmp_path):
    ready = tmp_path / "ready"; ready.write_text("x")
    s9f._wait_for_path(ready, timeout_seconds=0.01)
    with pytest.raises(RuntimeError, match="timed out"):
        s9f._wait_for_path(tmp_path / "missing", timeout_seconds=0.0)


def test_child_hold_lock_returns_after_release(tmp_path):
    release = tmp_path / "release"
    ready = tmp_path / "ready"
    timer = threading.Timer(0.03, lambda: release.write_text("go"))
    timer.start()
    try:
        s9f._child_hold_lock(str(tmp_path / "store"), str(ready), str(release))
    finally:
        timer.join()
    assert ready.exists()


def test_child_migrate_unexpected_return_is_guarded(tmp_path, pair, monkeypatch):
    blob = s9f.s9d.encode_envelope(pair["old_compact"])
    envelope = tmp_path / "legacy"; envelope.write_bytes(blob)
    template = tmp_path / "template"; template.write_bytes(s9f._canonical_bytes(s9f._template_packet(pair["template"])))
    monkeypatch.setattr(s9f.LockedCheckpointStore, "migrate_stage9d", lambda self, *args, **kwargs: 1)
    with pytest.raises(RuntimeError, match="unexpectedly returned"):
        s9f._child_migrate(str(tmp_path / "store"), str(envelope), str(template), "after_head_replace")


def test_spawn_holder_actual_process_excludes_writer(tmp_path, pair):
    root = tmp_path / "holder"
    root.mkdir()
    ready = root / "ready"; release = root / "release"; store_dir = root / "store"
    proc = s9f._spawn_holder(store_dir, ready, release)
    try:
        s9f._wait_for_path(ready)
        with pytest.raises(s9f.WriterBusyError):
            s9f.LockedCheckpointStore(store_dir).write_locked(pair["old_compact"])
        release.write_text("go")
        assert proc.wait(timeout=5) == 0
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait(timeout=5)


def test_run_child_migration_actual_exit(tmp_path, pair):
    code = s9f._run_child_migration(
        tmp_path / "child", s9f.s9d.encode_envelope(pair["old_compact"]), pair["template"], "after_lock_acquired"
    )
    assert code == s9f.MIGRATION_CRASH_EXIT_CODE


def test_writer_exclusion_success(tmp_path, pair):
    row = s9f._writer_exclusion(pair, tmp_path / "writer")
    assert row["competing_writer_rejected"]
    assert row["serialized_generations"] == [1, 2]


def test_writer_exclusion_detects_unblocked_competitor(tmp_path, pair, monkeypatch):
    class Done:
        def poll(self): return 0
        def kill(self): raise AssertionError("kill")
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(s9f, "_spawn_holder", lambda *args: Done())
    monkeypatch.setattr(s9f, "_wait_for_path", lambda *args, **kwargs: None)
    monkeypatch.setattr(s9f.LockedCheckpointStore, "write_locked", lambda self, compact, **kwargs: 1)
    with pytest.raises(RuntimeError, match="not excluded"):
        s9f._writer_exclusion(pair, tmp_path / "unblocked")


def test_writer_exclusion_detects_bad_handoff(tmp_path, pair, monkeypatch):
    monkeypatch.setattr(s9f, "_spawn_holder", lambda *args: _FakeKilledHolder())
    monkeypatch.setattr(s9f, "_wait_for_path", lambda *args, **kwargs: None)
    calls = {"n": 0}
    original = s9f.LockedCheckpointStore.write_locked
    def write(self, compact, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise s9f.WriterBusyError("busy")
        return 9
    monkeypatch.setattr(s9f.LockedCheckpointStore, "write_locked", write)
    contender = object()
    monkeypatch.setattr(s9f.ex, "_freeze", lambda value: deepcopy(pair["new_frozen"]))
    monkeypatch.setattr(
        s9f.LockedCheckpointStore,
        "recover_committed",
        lambda self, template: {"generation": 9, "contender": contender},
    )
    with pytest.raises(RuntimeError, match="ordering/state"):
        s9f._writer_exclusion(pair, tmp_path / "handoff")
    monkeypatch.setattr(s9f.LockedCheckpointStore, "write_locked", original)


class _FakeKilledHolder:
    def __init__(self): self.dead = False
    def poll(self): return 0 if self.dead else None
    def kill(self): self.dead = True
    def wait(self, timeout=None): self.dead = True; return -9


def test_writer_exclusion_finally_kills_live_holder(tmp_path, pair, monkeypatch):
    holder = _FakeKilledHolder()
    monkeypatch.setattr(s9f, "_spawn_holder", lambda *args: holder)
    monkeypatch.setattr(s9f, "_wait_for_path", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("wait failed")))
    with pytest.raises(RuntimeError, match="wait failed"):
        s9f._writer_exclusion(pair, tmp_path / "finally")
    assert holder.dead


def test_writer_exclusion_detects_continuation_drift(tmp_path, pair, monkeypatch):
    original = s9f.s9e._continuation_equal
    monkeypatch.setattr(s9f.s9e, "_continuation_equal", lambda *args: False)
    with pytest.raises(RuntimeError, match="continuation parity"):
        s9f._writer_exclusion(pair, tmp_path / "continuation")
    monkeypatch.setattr(s9f.s9e, "_continuation_equal", original)


def test_migration_matrix_success(tmp_path, pair):
    rows = s9f._migration_matrix(pair, tmp_path / "matrix")
    assert set(rows) == set(s9f._MIGRATION_EXPECTATION)
    assert all(row["pass"] for row in rows.values())


def test_migration_matrix_rejects_wrong_exit_code(tmp_path, pair, monkeypatch):
    monkeypatch.setattr(s9f, "_run_child_migration", lambda *args, **kwargs: 1)
    with pytest.raises(RuntimeError, match="exited"):
        s9f._migration_matrix(pair, tmp_path / "wrong-code")


def test_migration_matrix_detects_source_mutation(tmp_path, pair, monkeypatch):
    def mutate(root, blob, template, point):
        root.mkdir(parents=True, exist_ok=True)
        (root / "legacy.stage9d").write_bytes(b"mutated")
        return s9f.MIGRATION_CRASH_EXIT_CODE
    monkeypatch.setattr(s9f, "_run_child_migration", mutate)
    monkeypatch.setitem(s9f._MIGRATION_EXPECTATION, "after_lock_acquired", "legacy")
    saved = dict(s9f._MIGRATION_EXPECTATION)
    try:
        for key in list(s9f._MIGRATION_EXPECTATION):
            if key != "after_lock_acquired": del s9f._MIGRATION_EXPECTATION[key]
        with pytest.raises(RuntimeError, match="mutated"):
            s9f._migration_matrix(pair, tmp_path / "mutated")
    finally:
        s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION.update(saved)


def test_migration_matrix_detects_orphan_promotion(tmp_path, pair, monkeypatch):
    point = "after_lock_acquired"
    saved = dict(s9f._MIGRATION_EXPECTATION)
    s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION[point] = "legacy"
    def fake_run(root, blob, template, crash_point):
        root.mkdir(parents=True, exist_ok=True); (root / "legacy.stage9d").write_bytes(blob)
        return s9f.MIGRATION_CRASH_EXIT_CODE
    monkeypatch.setattr(s9f, "_run_child_migration", fake_run)
    monkeypatch.setattr(s9f.LockedCheckpointStore, "recover_committed", lambda self, template: {"generation": 1})
    try:
        with pytest.raises(RuntimeError, match="promoted"):
            s9f._migration_matrix(pair, tmp_path / "promote")
    finally:
        s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION.update(saved)


def test_migration_matrix_detects_committed_drift(tmp_path, pair, monkeypatch):
    point = "after_head_replace"
    saved = dict(s9f._MIGRATION_EXPECTATION)
    s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION[point] = "new"
    def fake_run(root, blob, template, crash_point):
        root.mkdir(parents=True, exist_ok=True); (root / "legacy.stage9d").write_bytes(blob)
        store = s9f.LockedCheckpointStore(root / "store"); store.write_locked(pair["old_compact"])
        return s9f.s9e.CRASH_EXIT_CODE
    monkeypatch.setattr(s9f, "_run_child_migration", fake_run)
    drift_pair = dict(pair)
    drift_pair["old_frozen"] = {"drift": True}
    try:
        with pytest.raises(RuntimeError, match="drifted"):
            s9f._migration_matrix(drift_pair, tmp_path / "committed-drift")
    finally:
        s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION.update(saved)


def test_migration_matrix_detects_retry_or_state_failure(tmp_path, pair, monkeypatch):
    point = "after_lock_acquired"
    saved = dict(s9f._MIGRATION_EXPECTATION)
    s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION[point] = "legacy"
    def fake_run(root, blob, template, crash_point):
        root.mkdir(parents=True, exist_ok=True); (root / "legacy.stage9d").write_bytes(blob)
        return s9f.MIGRATION_CRASH_EXIT_CODE
    monkeypatch.setattr(s9f, "_run_child_migration", fake_run)
    monkeypatch.setattr(s9f.LockedCheckpointStore, "migrate_stage9d", lambda self, blob, template, **kwargs: 2)
    calls = {"n": 0}
    contender = object()
    monkeypatch.setattr(s9f.ex, "_freeze", lambda value: deepcopy(pair["old_frozen"]))
    def recover(self, template):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("no committed checkpoint head")
        return {"generation": 2, "contender": contender}
    monkeypatch.setattr(s9f.LockedCheckpointStore, "recover_committed", recover)
    try:
        with pytest.raises(RuntimeError, match="retry/idempotency"):
            s9f._migration_matrix(pair, tmp_path / "retry-fail")
    finally:
        s9f._MIGRATION_EXPECTATION.clear(); s9f._MIGRATION_EXPECTATION.update(saved)


def test_migration_matrix_detects_continuation_failure(tmp_path, pair, monkeypatch):
    original = s9f.s9e._continuation_equal
    monkeypatch.setattr(s9f.s9e, "_continuation_equal", lambda *args: False)
    try:
        with pytest.raises(RuntimeError, match="continuation drifted"):
            s9f._migration_matrix(pair, tmp_path / "cont-fail")
    finally:
        s9f.s9e._continuation_equal = original


def test_migration_conflict_success(tmp_path, pair):
    assert s9f._migration_conflict(pair, tmp_path)


def test_migration_conflict_guard_when_conflict_not_rejected(tmp_path, pair, monkeypatch):
    store_states = {}
    original = s9f.LockedCheckpointStore.migrate_stage9d
    def accept(self, blob, template, **kwargs):
        key = str(self.directory); store_states[key] = store_states.get(key, 0) + 1; return store_states[key]
    monkeypatch.setattr(s9f.LockedCheckpointStore, "migrate_stage9d", accept)
    with pytest.raises(RuntimeError, match="did not fail closed"):
        s9f._migration_conflict(pair, tmp_path / "accept")
    monkeypatch.setattr(s9f.LockedCheckpointStore, "migrate_stage9d", original)


def test_migration_conflict_guard_when_state_changes(tmp_path, pair, monkeypatch):
    original_recover = s9f.LockedCheckpointStore.recover_committed
    calls = {"n": 0}
    def recover(self, template):
        calls["n"] += 1
        row = original_recover(self, template)
        if calls["n"] >= 1:
            row = dict(row); row["generation"] = 99
        return row
    monkeypatch.setattr(s9f.LockedCheckpointStore, "recover_committed", recover)
    with pytest.raises(RuntimeError, match="did not fail closed"):
        s9f._migration_conflict(pair, tmp_path / "changed")


def test_timing_probe_shape(tmp_path, pair):
    row = s9f._timing_probe(pair, tmp_path, 1)
    assert row["samples"] == 1 and row["locked_write_median_us"] >= 0 and row["fresh_migration_median_us"] >= 0


def test_profile_level_without_timing(tmp_path):
    row = s9f._profile_level(LEVEL, tmp_path / "profile", timing=False, samples=1)
    assert row["all_migration_crash_cases_pass"]
    assert row["migration_conflict_fails_closed"]
    assert row["query_correct_after_target_state"]
    assert row["timing"] is None


def test_profile_level_with_timing_stubbed(tmp_path, pair, monkeypatch):
    monkeypatch.setattr(s9f.s9e, "_checkpoint_pair", lambda level: pair)
    monkeypatch.setattr(s9f, "_writer_exclusion", lambda *args: {
        "competing_writer_rejected": True, "process_death_released_lock": True,
        "exact_final_state": True, "continuation_equal": True,
    })
    monkeypatch.setattr(s9f, "_migration_matrix", lambda *args: {"x": {"pass": True}})
    monkeypatch.setattr(s9f, "_migration_conflict", lambda *args: True)
    monkeypatch.setattr(s9f.s9e, "_query_correct", lambda *args: True)
    monkeypatch.setattr(s9f, "_timing_probe", lambda *args: {"samples": 1})
    row = s9f._profile_level(LEVEL, tmp_path, timing=True, samples=1)
    assert row["timing"] == {"samples": 1}


def test_aggregate_true_and_false():
    good = {
        "writer_exclusion": {"competing_writer_rejected": True, "process_death_released_lock": True, "exact_final_state": True, "continuation_equal": True},
        "all_migration_crash_cases_pass": True,
        "migration_conflict_fails_closed": True,
        "query_correct_after_target_state": True,
    }
    assert all(s9f._aggregate([good]).values())
    bad = deepcopy(good); bad["writer_exclusion"]["continuation_equal"] = False
    bad["all_migration_crash_cases_pass"] = False; bad["migration_conflict_fails_closed"] = False; bad["query_correct_after_target_state"] = False
    assert not any(s9f._aggregate([bad]).values())


def test_run_experiment_rejects_bad_timing_samples():
    for value in (True, 0, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            s9f.run_experiment(timing=False, timing_samples=value)


def test_run_experiment_result_shape(monkeypatch):
    row = {
        "writer_exclusion": {"competing_writer_rejected": True, "process_death_released_lock": True, "exact_final_state": True, "continuation_equal": True},
        "all_migration_crash_cases_pass": True,
        "migration_conflict_fails_closed": True,
        "query_correct_after_target_state": True,
    }
    monkeypatch.setattr(s9f, "_profile_level", lambda *args, **kwargs: deepcopy(row))
    result = s9f.run_experiment(timing=False, timing_samples=1)
    assert result["strict_verdict"] == s9f.VERDICT
    assert len(result["levels"]) == 4
    assert result["all_writer_exclusion_cases_pass"]
    assert result["constraints"]["multi_host_locking_not_proven"]
