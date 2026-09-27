from copy import deepcopy
import json
from pathlib import Path

import pytest

from ghost_research import v112_atomic_recovery_stage9e as s9e


LEVEL = {"id": "events_224", "ambient_events": 224}


@pytest.fixture(scope="module")
def pair():
    return s9e._checkpoint_pair(LEVEL)


@pytest.fixture
def store(tmp_path):
    return s9e.AtomicCheckpointStore(tmp_path / "store")


def test_canonical_and_sha_are_deterministic():
    left = s9e._canonical_bytes({"b": 2, "a": 1})
    right = s9e._canonical_bytes({"a": 1, "b": 2})
    assert left == right and s9e._sha(left) == s9e._sha(right)


def test_json_file_valid_and_invalid(tmp_path):
    good = tmp_path / "good.json"; good.write_text('{"a":1}', encoding="utf-8")
    bad = tmp_path / "bad.json"; bad.write_bytes(b"{")
    assert s9e._json_file(good) == {"a": 1}
    with pytest.raises(ValueError, match="invalid checkpoint JSON"):
        s9e._json_file(bad)
    with pytest.raises(ValueError, match="invalid checkpoint JSON"):
        s9e._json_file(tmp_path / "missing.json")


@pytest.mark.parametrize("bad", [None, "x", "g" * 64])
def test_digest_text_rejects_invalid_values(bad):
    with pytest.raises(ValueError, match="64 hex"):
        s9e._digest_text(bad)


def test_digest_text_normalizes_case():
    assert s9e._digest_text("A" * 64) == "a" * 64


def test_fsync_dir_executes(tmp_path):
    s9e._fsync_dir(tmp_path)
    assert tmp_path.is_dir()


def test_trip_mismatch_returns_and_raise_mode_raises():
    assert s9e._trip(None, "x", "raise") is None
    with pytest.raises(s9e.SimulatedCrash, match="x"):
        s9e._trip("x", "x", "raise")


def test_trip_exit_path_and_bad_mode(monkeypatch):
    class ExitProbe(RuntimeError):
        pass
    monkeypatch.setattr(s9e.os, "_exit", lambda code: (_ for _ in ()).throw(ExitProbe(code)))
    with pytest.raises(ExitProbe, match=str(s9e.CRASH_EXIT_CODE)):
        s9e._trip("x", "x", "exit")
    with pytest.raises(ValueError, match="crash mode"):
        s9e._trip("x", "x", "bad")


def test_slot_path_validation(store):
    assert store._slot_path("a").name == "slot_a.json"
    with pytest.raises(ValueError, match="slot must"):
        store._slot_path("c")


def test_head_none_then_valid(store, pair):
    assert store._head() is None
    assert store.write(pair["old_compact"]) == 1
    head = store._head()
    assert head is not None and head["active_slot"] == "a" and head["generation"] == 1


def _write_head(path: Path, packet):
    path.write_text(json.dumps(packet), encoding="utf-8")


def test_head_rejects_shape_schema_generation_and_digest(store):
    _write_head(store.head_path, [])
    with pytest.raises(ValueError, match="invalid shape"):
        store._head()
    base = {"schema": s9e.HEAD_SCHEMA, "active_slot": "a", "generation": 1, "slot_sha256": "0" * 64}
    wrong = deepcopy(base); wrong["schema"] = "wrong"; _write_head(store.head_path, wrong)
    with pytest.raises(ValueError, match="schema/slot"):
        store._head()
    wrong = deepcopy(base); wrong["active_slot"] = "c"; _write_head(store.head_path, wrong)
    with pytest.raises(ValueError, match="schema/slot"):
        store._head()
    wrong = deepcopy(base); wrong["generation"] = True; _write_head(store.head_path, wrong)
    with pytest.raises(ValueError, match="positive integer"):
        store._head()
    wrong = deepcopy(base); wrong["slot_sha256"] = "bad"; _write_head(store.head_path, wrong)
    with pytest.raises(ValueError, match="64 hex"):
        store._head()


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5])
def test_slot_bytes_rejects_bad_generation(pair, bad):
    with pytest.raises(ValueError, match="positive integer"):
        s9e.AtomicCheckpointStore._slot_bytes(pair["old_compact"], bad)


def test_slot_codec_roundtrip(pair):
    data = s9e.AtomicCheckpointStore._slot_bytes(pair["old_compact"], 3)
    generation, envelope, compact = s9e.AtomicCheckpointStore._decode_slot_bytes(data)
    assert generation == 3 and compact == pair["old_compact"] and envelope == s9e.s9d.encode_envelope(pair["old_compact"])


def _slot_packet(pair):
    return json.loads(s9e.AtomicCheckpointStore._slot_bytes(pair["old_compact"], 1).decode())


def test_decode_slot_rejects_json_shape_schema_generation_base64_digest(pair):
    with pytest.raises(ValueError, match="not valid JSON"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(b"{")
    with pytest.raises(ValueError, match="invalid shape"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(b"[]")
    packet = _slot_packet(pair); packet["schema"] = "wrong"
    with pytest.raises(ValueError, match="schema mismatch"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(s9e._canonical_bytes(packet))
    packet = _slot_packet(pair); packet["generation"] = False
    with pytest.raises(ValueError, match="generation must be positive"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(s9e._canonical_bytes(packet))
    packet = _slot_packet(pair); packet["envelope_b64"] = "***"
    with pytest.raises(ValueError, match="valid base64"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(s9e._canonical_bytes(packet))
    packet = _slot_packet(pair); packet["envelope_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="integrity mismatch"):
        s9e.AtomicCheckpointStore._decode_slot_bytes(s9e._canonical_bytes(packet))


def test_decode_slot_delegates_envelope_validation(pair):
    packet = _slot_packet(pair)
    envelope = b"{}"
    packet["envelope_b64"] = s9e.base64.b64encode(envelope).decode("ascii")
    packet["envelope_sha256"] = s9e._sha(envelope)
    with pytest.raises(ValueError):
        s9e.AtomicCheckpointStore._decode_slot_bytes(s9e._canonical_bytes(packet))


def test_validated_slot_and_restore_drift_detection(store, pair, monkeypatch):
    store.write(pair["old_compact"])
    row = store._validated_slot("a", pair["template"])
    assert row["generation"] == 1 and row["compact"] == pair["old_compact"]
    original = s9e.s9d.restore_runtime
    def drift(blob, template):
        contender, sidecar, compact = original(blob, template)
        return contender, sidecar, {"drift": compact}
    monkeypatch.setattr(s9e.s9d, "restore_runtime", drift)
    with pytest.raises(RuntimeError, match="changed compact"):
        store._validated_slot("a", pair["template"])


def test_write_rejects_unknown_crash_point(store, pair):
    with pytest.raises(ValueError, match="unknown Stage-9E crash point"):
        store.write(pair["old_compact"], crash_at="nope")


@pytest.mark.parametrize("point", list(s9e._CRASH_EXPECTATION))
def test_write_raise_fault_injection_hits_every_boundary(tmp_path, pair, point):
    store = s9e.AtomicCheckpointStore(tmp_path / point)
    store.write(pair["old_compact"])
    with pytest.raises(s9e.SimulatedCrash, match=point):
        store.write(pair["new_compact"], crash_at=point, crash_mode="raise")


def test_write_toggles_slots_and_generations(store, pair):
    assert store.write(pair["old_compact"]) == 1
    assert store.write(pair["new_compact"]) == 2
    head = store._head()
    assert head is not None and head["active_slot"] == "b" and head["generation"] == 2


def test_write_rejects_invalid_crash_mode_when_reached(store, pair):
    store.write(pair["old_compact"])
    with pytest.raises(ValueError, match="crash mode"):
        store.write(pair["new_compact"], crash_at="after_slot_fsync", crash_mode="bad")


def test_recover_empty_store_fails(store, pair):
    with pytest.raises(ValueError, match="no recoverable"):
        store.recover(pair["template"])


def test_recover_active_and_corrupt_active_fallback(tmp_path, pair):
    store = s9e.AtomicCheckpointStore(tmp_path / "recover")
    store.write(pair["old_compact"]); store.write(pair["new_compact"])
    current = store.recover(pair["template"])
    assert current["generation"] == 2 and s9e.ex._freeze(current["contender"]) == pair["new_frozen"]
    head = store._head(); assert head is not None
    store._slot_path(head["active_slot"]).write_bytes(b"corrupt")
    prior = store.recover(pair["template"])
    assert prior["generation"] == 1 and s9e.ex._freeze(prior["contender"]) == pair["old_frozen"]


def test_recover_corrupt_head_selects_highest_valid(tmp_path, pair):
    store = s9e.AtomicCheckpointStore(tmp_path / "head")
    store.write(pair["old_compact"]); store.write(pair["new_compact"])
    store.head_path.write_bytes(b"{")
    row = store.recover(pair["template"])
    assert row["generation"] == 2


def test_recover_valid_head_with_no_eligible_prior_fails(tmp_path, pair):
    store = s9e.AtomicCheckpointStore(tmp_path / "no-prior")
    store.write(pair["old_compact"])
    head = store._head(); assert head is not None
    fake = deepcopy(head); fake["active_slot"] = "b"; fake["slot_sha256"] = "0" * 64
    store.head_path.write_bytes(s9e._canonical_bytes(fake))
    with pytest.raises(ValueError, match="no prior generation"):
        store.recover(pair["template"])


def test_recover_skips_runtime_invalid_candidate(tmp_path, pair, monkeypatch):
    store = s9e.AtomicCheckpointStore(tmp_path / "skip")
    store.write(pair["old_compact"])
    monkeypatch.setattr(store, "_validated_slot", lambda slot, template: (_ for _ in ()).throw(RuntimeError("bad")))
    with pytest.raises(ValueError, match="no recoverable"):
        store.recover(pair["template"])


def test_import_stage9d_exact(store, pair):
    generation = store.import_stage9d(s9e.s9d.encode_envelope(pair["old_compact"]), pair["template"])
    row = store.recover(pair["template"])
    assert generation == 1 and s9e.ex._freeze(row["contender"]) == pair["old_frozen"]


def test_checkpoint_pair_exact(pair):
    assert pair["old_frozen"] != pair["new_frozen"]
    assert s9e.inc.IncrementalCompactSidecar.expand_full_snapshot(pair["new_compact"]) == pair["new_frozen"]


def test_checkpoint_pair_detects_old_and_new_roundtrip_drift(monkeypatch):
    original = s9e.inc.IncrementalCompactSidecar.expand_full_snapshot
    monkeypatch.setattr(s9e.inc.IncrementalCompactSidecar, "expand_full_snapshot", staticmethod(lambda compact: {"drift": True}))
    with pytest.raises(RuntimeError, match="old checkpoint"):
        s9e._checkpoint_pair(LEVEL)
    calls = {"n": 0}
    def drift_second(compact):
        calls["n"] += 1
        value = original(compact)
        return {"drift": True} if calls["n"] == 2 else value
    monkeypatch.setattr(s9e.inc.IncrementalCompactSidecar, "expand_full_snapshot", staticmethod(drift_second))
    with pytest.raises(RuntimeError, match="new checkpoint"):
        s9e._checkpoint_pair(LEVEL)


def test_continuation_equal_true(pair):
    restored = s9e.s9d._restore_contender(pair["old_frozen"], pair["template"])
    assert s9e._continuation_equal(restored, pair["old_frozen"], pair["template"])


def test_continuation_equal_false_paths(pair, monkeypatch):
    restored = s9e.s9d._restore_contender(pair["old_frozen"], pair["template"])
    original_observe = s9e.ex._observe
    calls = {"n": 0}
    def ledger_drift(*args, **kwargs):
        original_observe(*args, **kwargs); calls["n"] += 1
        if calls["n"] == 2:
            args[1][-1]["drift"] = True
    monkeypatch.setattr(s9e.ex, "_observe", ledger_drift)
    assert not s9e._continuation_equal(restored, pair["old_frozen"], pair["template"])


def test_continuation_equal_fingerprint_false(pair, monkeypatch):
    restored = s9e.s9d._restore_contender(pair["old_frozen"], pair["template"])
    original = restored._fingerprint
    monkeypatch.setattr(restored, "_fingerprint", lambda: {"drift": original()})
    assert not s9e._continuation_equal(restored, pair["old_frozen"], pair["template"])


def test_continuation_equal_freeze_false(pair, monkeypatch):
    restored = s9e.s9d._restore_contender(pair["old_frozen"], pair["template"])
    original_freeze = s9e.ex._freeze
    calls = {"n": 0}
    def drift_second(contender):
        calls["n"] += 1
        value = original_freeze(contender)
        if calls["n"] == 2:
            value = deepcopy(value); value["drift"] = True
        return value
    monkeypatch.setattr(s9e.ex, "_freeze", drift_second)
    assert not s9e._continuation_equal(restored, pair["old_frozen"], pair["template"])


def test_child_write_unexpected_return_is_guarded(tmp_path, pair, monkeypatch):
    path = tmp_path / "compact.json"; path.write_bytes(s9e._canonical_bytes(pair["old_compact"]))
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "write", lambda self, compact, **kwargs: 1)
    with pytest.raises(RuntimeError, match="unexpectedly returned"):
        s9e._child_write(str(tmp_path / "child"), str(path), "after_slot_fsync")


def test_actual_child_process_exit_fault(tmp_path, pair):
    store = s9e.AtomicCheckpointStore(tmp_path / "child-real")
    store.write(pair["old_compact"])
    code = s9e._run_child_crash(store.directory, pair["new_compact"], "after_slot_replace")
    assert code == s9e.CRASH_EXIT_CODE and store.recover(pair["template"])["generation"] == 1


def test_query_correct_true_and_false(pair, monkeypatch):
    assert s9e._query_correct(pair["new_compact"], pair["new_ledger"])
    monkeypatch.setattr(s9e.s7, "_ground_truth", lambda ledger, task: object())
    assert not s9e._query_correct(pair["new_compact"], pair["new_ledger"])


def test_profile_level_full_integration_without_timing(tmp_path):
    row = s9e._profile_level(LEVEL, tmp_path / "profile", timing=False, samples=1)
    assert row["all_process_crash_cases_pass"]
    assert all(row["corruption_recovery"].values())
    assert row["migration"]["continuation_equal"] and row["query_correct_after_new_checkpoint"]
    assert row["timing"] is None


def test_profile_level_timing_branch(tmp_path):
    row = s9e._profile_level(LEVEL, tmp_path / "timing", timing=True, samples=1)
    assert row["timing"]["samples"] == 1
    assert row["timing"]["atomic_write_median_us"] >= 0 and row["timing"]["recover_median_us"] >= 0


def _fake_pair(pair):
    return {
        "template": pair["template"], "old_frozen": pair["old_frozen"], "old_compact": pair["old_compact"],
        "new_frozen": pair["new_frozen"], "new_compact": pair["new_compact"], "new_ledger": pair["new_ledger"],
    }


def test_migration_check_rejects_state_and_continuation(tmp_path, pair, monkeypatch):
    original_recover = s9e.AtomicCheckpointStore.recover
    def wrong_state(self, template):
        row = original_recover(self, template)
        row["contender"].api.apply_world_effects({"pressure_delta": 0.01})
        return row
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", wrong_state)
    with pytest.raises(RuntimeError, match="migration changed"):
        s9e._migration_check(_fake_pair(pair), tmp_path / "a")
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", original_recover)
    monkeypatch.setattr(s9e, "_continuation_equal", lambda *args: False)
    with pytest.raises(RuntimeError, match="migrated runtime"):
        s9e._migration_check(_fake_pair(pair), tmp_path / "b")


def test_crash_matrix_rejects_child_exit_wrong_state_and_continuation(tmp_path, pair, monkeypatch):
    fake = _fake_pair(pair)
    monkeypatch.setattr(s9e, "_CRASH_EXPECTATION", {"after_slot_replace": "old"})
    monkeypatch.setattr(s9e, "_run_child_crash", lambda *args: 0)
    with pytest.raises(RuntimeError, match="did not terminate"):
        s9e._crash_matrix(fake, tmp_path / "exit")

    monkeypatch.setattr(s9e, "_run_child_crash", lambda *args: s9e.CRASH_EXIT_CODE)
    original_recover = s9e.AtomicCheckpointStore.recover
    def wrong_recover(self, template):
        row = original_recover(self, template)
        row["contender"].api.apply_world_effects({"pressure_delta": 0.01})
        return row
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", wrong_recover)
    with pytest.raises(RuntimeError, match="wrong generation"):
        s9e._crash_matrix(fake, tmp_path / "wrong")

    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", original_recover)
    monkeypatch.setattr(s9e, "_continuation_equal", lambda *args: False)
    with pytest.raises(RuntimeError, match="post-crash continuation"):
        s9e._crash_matrix(fake, tmp_path / "continue")


def test_active_slot_fallback_error_paths(tmp_path, pair, monkeypatch):
    fake = _fake_pair(pair)
    original_head = s9e.AtomicCheckpointStore._head
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "_head", lambda self: None)
    with pytest.raises(RuntimeError, match="head unexpectedly missing"):
        s9e._active_slot_fallback(fake, tmp_path / "missing")
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "_head", original_head)
    original_recover = s9e.AtomicCheckpointStore.recover
    def drift(self, template):
        row = original_recover(self, template)
        row["contender"].api.apply_world_effects({"pressure_delta": 0.01})
        return row
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", drift)
    with pytest.raises(RuntimeError, match="fall back"):
        s9e._active_slot_fallback(fake, tmp_path / "drift")


def test_corrupt_head_fallback_error(tmp_path, pair, monkeypatch):
    original = s9e.AtomicCheckpointStore.recover
    def drift(self, template):
        row = original(self, template)
        row["contender"].api.apply_world_effects({"pressure_delta": 0.01})
        return row
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", drift)
    with pytest.raises(RuntimeError, match="highest valid"):
        s9e._corrupt_head_fallback(_fake_pair(pair), tmp_path / "head")


def test_dual_slot_fail_closed_error(tmp_path, pair, monkeypatch):
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "recover", lambda self, template: {"contender": template})
    with pytest.raises(RuntimeError, match="did not fail closed"):
        s9e._dual_slot_fail_closed(_fake_pair(pair), tmp_path / "dual")


def test_unknown_schema_rejected_error(tmp_path, pair, monkeypatch):
    original = s9e.AtomicCheckpointStore.import_stage9d
    def accept(self, blob, template):
        try:
            return original(self, blob, template)
        except ValueError:
            return 1
    monkeypatch.setattr(s9e.AtomicCheckpointStore, "import_stage9d", accept)
    with pytest.raises(RuntimeError, match="unknown predecessor"):
        s9e._unknown_schema_rejected(_fake_pair(pair), tmp_path / "future")


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5])
def test_run_experiment_rejects_bad_samples(bad):
    with pytest.raises(ValueError, match="positive integer"):
        s9e.run_experiment(timing_samples=bad)


def test_run_experiment_structure(monkeypatch):
    row = {
        "migration": {"exact_state": True, "continuation_equal": True},
        "all_process_crash_cases_pass": True,
        "corruption_recovery": {"x": True},
        "query_correct_after_new_checkpoint": True,
    }
    monkeypatch.setattr(s9e, "_LEVELS", ({"id": "x", "ambient_events": 1},))
    monkeypatch.setattr(s9e, "_profile_level", lambda *args, **kwargs: deepcopy(row))
    result = s9e.run_experiment(timing=False, timing_samples=1)
    assert result["strict_verdict"] == s9e.VERDICT
    assert result["all_stage9d_migrations_exact"] and result["all_process_crash_cases_pass"]
    assert result["all_corruption_recovery_cases_pass"] and result["all_queries_correct"]
    assert result["constraints"]["power_loss_durability_not_proven"] is True


def test_run_experiment_false_aggregate_paths(monkeypatch):
    row = {
        "migration": {"exact_state": False, "continuation_equal": True},
        "all_process_crash_cases_pass": False,
        "corruption_recovery": {"x": False},
        "query_correct_after_new_checkpoint": False,
    }
    monkeypatch.setattr(s9e, "_LEVELS", ({"id": "x", "ambient_events": 1},))
    monkeypatch.setattr(s9e, "_profile_level", lambda *args, **kwargs: deepcopy(row))
    result = s9e.run_experiment(timing=False, timing_samples=1)
    assert not result["all_stage9d_migrations_exact"] and not result["all_process_crash_cases_pass"]
    assert not result["all_corruption_recovery_cases_pass"] and not result["all_queries_correct"]


def test_crash_matrix_is_frozen():
    assert s9e._CRASH_EXPECTATION == {
        "after_partial_slot_write": "old", "after_slot_fsync": "old", "after_slot_replace": "old",
        "after_slot_dir_fsync": "old", "after_head_fsync": "old", "after_head_replace": "new",
        "after_commit_dir_fsync": "new",
    }
