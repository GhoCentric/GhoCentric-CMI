from copy import deepcopy
import json

import pytest

from ghost_research import v112_incremental_compact_codec_stage9c as inc
from ghost_research import v112_incremental_compact_stage9c as s9c
from ghost_research import v112_restart_continue_stage9d as s9d
from ghost_research import v112_structural_complexity_stage6 as s6


def _live():
    return s9c.LiveExposure({"id": "events_224", "ambient_events": 224}).run()


def _template():
    return s6.StructuralContender("full", 3)


def test_envelope_roundtrip_is_canonical_and_exact():
    compact = _live()["compact"]
    blob = s9d.encode_envelope(compact)
    assert s9d.decode_envelope(blob) == compact
    assert blob == s9d._canonical_bytes(json.loads(blob))


def test_make_envelope_rejects_non_dict():
    with pytest.raises(TypeError, match="must be a dict"):
        s9d.make_envelope([])


@pytest.mark.parametrize("value", ["x", b"x"])
def test_decode_rejects_invalid_json(value):
    blob = value if isinstance(value, bytes) else value.encode()
    with pytest.raises(ValueError, match="canonical JSON"):
        s9d.decode_envelope(blob)


def test_decode_rejects_non_bytes():
    with pytest.raises(TypeError, match="must be bytes"):
        s9d.decode_envelope("x")


def test_decode_rejects_shape_schema_and_payload_type():
    with pytest.raises(ValueError, match="invalid shape"):
        s9d.decode_envelope(s9d._canonical_bytes({"schema": s9d.ENVELOPE_SCHEMA}))
    packet = s9d.make_envelope({})
    packet["schema"] = "wrong"
    with pytest.raises(ValueError, match="schema mismatch"):
        s9d.decode_envelope(s9d._canonical_bytes(packet))
    packet = {"schema": s9d.ENVELOPE_SCHEMA, "payload_sha256": "0" * 64, "compact": []}
    with pytest.raises(ValueError, match="payload must be a dict"):
        s9d.decode_envelope(s9d._canonical_bytes(packet))


@pytest.mark.parametrize("digest", ["0", "g" * 64])
def test_decode_rejects_bad_digest_text(digest):
    packet = {"schema": s9d.ENVELOPE_SCHEMA, "payload_sha256": digest, "compact": {}}
    with pytest.raises(ValueError, match="64 hex"):
        s9d.decode_envelope(s9d._canonical_bytes(packet))


def test_decode_rejects_integrity_mismatch():
    packet = s9d.make_envelope({"a": 1})
    packet["compact"]["a"] = 2
    with pytest.raises(ValueError, match="integrity mismatch"):
        s9d.decode_envelope(s9d._canonical_bytes(packet))


def test_restore_rejects_non_full_expanded_snapshot(monkeypatch):
    monkeypatch.setattr(inc.IncrementalCompactSidecar, "expand_full_snapshot", staticmethod(lambda compact: {"mode": "baseline", "api": {}}))
    with pytest.raises(ValueError, match="Full-Ghost"):
        s9d.restore_runtime(s9d.encode_envelope({}), _template())


def test_restore_runtime_exact_and_sidecar_query_ready():
    live = _live()
    contender, sidecar, compact = s9d.restore_runtime(s9d.encode_envelope(live["compact"]), _template())
    assert compact == live["compact"]
    assert contender.api.snapshot() == live["frozen"]["api"]
    assert sidecar.compact_full_snapshot(live["frozen"]) == live["compact"]


def test_restore_runtime_detects_record_count_mismatch(monkeypatch):
    live = _live()
    original = s9c.LiveExposureAnswer.sidecar
    def wrong(payload):
        side = original(payload)
        side.records_ingested += 1
        return side
    monkeypatch.setattr(s9c.LiveExposureAnswer, "sidecar", staticmethod(wrong))
    with pytest.raises(RuntimeError, match="record count mismatch"):
        s9d.restore_runtime(s9d.encode_envelope(live["compact"]), _template())


def test_restore_runtime_detects_reconstruction_drift(monkeypatch):
    live = _live()
    monkeypatch.setattr(inc.IncrementalCompactSidecar, "compact_full_snapshot", lambda self, frozen: {"drift": True})
    with pytest.raises(RuntimeError, match="reconstruction drifted"):
        s9d.restore_runtime(s9d.encode_envelope(live["compact"]), _template())


def test_restore_contender_detects_missing_agent(monkeypatch):
    live = _live()
    class FakeAPI:
        epistemic = type("E", (), {"_records": []})()
        def agent(self, logical):
            return None
    from ghost import api as api_module
    monkeypatch.setattr(api_module.GhostAPI, "from_snapshot", classmethod(lambda cls, snapshot: FakeAPI()))
    with pytest.raises(RuntimeError, match="lost a registered"):
        s9d._restore_contender(live["frozen"], _template())


def test_full_restart_exposure_exact_continuation():
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    result = runner.run(restart_points={56, 112, 168})
    diag = result["restart_diagnostics"]
    assert diag["restart_parity_checks"] == 3
    assert len(diag["full_restart_us"]) == 3
    assert len(diag["restart_packet_bytes"]) == 3
    assert diag["step_fingerprint_checks"] > 224


def test_full_restart_initial_drift_is_rejected(monkeypatch):
    original = s9d.ex._freeze
    calls = {"n": 0}
    def drift(contender):
        calls["n"] += 1
        value = original(contender)
        if calls["n"] == 2:
            value = deepcopy(value); value["drift"] = True
        return value
    monkeypatch.setattr(s9d.ex, "_freeze", drift)
    with pytest.raises(RuntimeError, match="initial branches"):
        s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})


def test_run_detects_ledger_drift(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.ex._observe
    def drift(contender, ledger, life_id, *args, **kwargs):
        original(contender, ledger, life_id, *args, **kwargs)
        if contender is runner.shadow:
            ledger[-1]["drift"] = True
    with pytest.raises(RuntimeError, match="host ledger drifted"):
        runner._run(drift, "x", source="world", subject="visitor_00", token="x")


def test_run_detects_fingerprint_drift(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = runner.shadow._fingerprint
    monkeypatch.setattr(runner.shadow, "_fingerprint", lambda: {"drift": original()})
    with pytest.raises(RuntimeError, match="decision-relevant"):
        runner._run(s9d.ex._observe, "x", source="world", subject="visitor_00", token="x")


def test_restart_rejects_preexisting_branch_drift(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.ex._freeze
    def drift(contender):
        value = original(contender)
        if contender is runner.shadow:
            value = deepcopy(value); value["drift"] = True
        return value
    monkeypatch.setattr(s9d.ex, "_freeze", drift)
    with pytest.raises(RuntimeError, match="pre-existing"):
        runner.restart_sidecar()


def test_restart_rejects_restored_compact_drift(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.restore_runtime
    def drift(blob, template):
        contender, sidecar, compact = original(blob, template)
        return contender, sidecar, {"drift": compact}
    monkeypatch.setattr(s9d, "restore_runtime", drift)
    with pytest.raises(RuntimeError, match="changed exact Ghost state"):
        runner.restart_sidecar()


def test_restart_detects_shadow_divergence_after_restore(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.restore_runtime
    def drift(blob, template):
        contender, sidecar, compact = original(blob, template)
        contender.api.apply_world_effects({"pressure_delta": 0.01})
        return contender, sidecar, compact
    monkeypatch.setattr(s9d, "restore_runtime", drift)
    with pytest.raises(RuntimeError, match="changed exact Ghost state"):
        runner.restart_sidecar()


def test_final_shadow_drift_is_rejected(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.ex._freeze
    calls = {"after": False}
    def drift(contender):
        value = original(contender)
        if calls["after"] and contender is runner.shadow:
            value = deepcopy(value); value["drift"] = True
        return value
    monkeypatch.setattr(s9d.ex, "_freeze", drift)
    original_parent_run = s9c.LiveExposure.run
    def parent_run(self, **kwargs):
        value = original_parent_run(self, **kwargs)
        calls["after"] = True
        return value
    monkeypatch.setattr(s9c.LiveExposure, "run", parent_run)
    with pytest.raises(RuntimeError, match="final state drifted"):
        runner.run(restart_points=set())


def test_restart_points_are_three_distinct_quartiles():
    assert s9d._restart_points(224) == {56, 112, 168}


def test_median_odd_and_even():
    assert s9d._median([3.0, 1.0, 2.0]) == 2.0
    assert s9d._median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_corruption_battery_rejects_all_guarded_cases():
    live = _live()
    result = s9d._corruption_battery(live["compact"], _template())
    assert set(result) == {
        "wrong_envelope_schema", "stale_payload_digest", "invalid_digest_encoding",
        "truncated_json", "rehashed_codec_schema", "rehashed_ghost_schema",
    }
    assert all(result.values())


def test_profile_level_without_timing():
    row = s9d._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)
    assert row["all_correct"] and row["exact_stage7_reference"] and row["exact_final_roundtrip"]
    assert row["restart"]["full_restarts"] == 3
    assert row["timing"] is None


def test_profile_level_with_timing():
    row = s9d._profile_level({"id": "events_224", "ambient_events": 224}, timing=True, samples=1)
    assert row["timing"]["samples"] == 1
    assert row["timing"]["observed_restart_median_us"] >= 0
    assert row["timing"]["post_restart_query_battery_us"] >= 0


def test_profile_detects_stage7_reference_drift(monkeypatch):
    original = s9d.ex.blind_exposure
    def drift(level, mode):
        value = original(level, mode)
        value["host_ledger"] = value["host_ledger"] + [{"drift": True}]
        return value
    monkeypatch.setattr(s9d.ex, "blind_exposure", drift)
    with pytest.raises(RuntimeError, match="Stage-7 reference"):
        s9d._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)


def test_profile_detects_roundtrip_drift(monkeypatch):
    original = inc.IncrementalCompactSidecar.expand_full_snapshot
    calls = {"n": 0}

    def drift_only_final_check(compact):
        calls["n"] += 1
        restored = original(compact)
        if calls["n"] == 4:
            return {"drift": True}
        return restored

    monkeypatch.setattr(
        inc.IncrementalCompactSidecar,
        "expand_full_snapshot",
        staticmethod(drift_only_final_check),
    )
    with pytest.raises(RuntimeError, match="final compact"):
        s9d._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)
    assert calls["n"] == 4


@pytest.mark.parametrize("bad", [True, 0, 1.5])
def test_run_rejects_bad_samples(bad):
    with pytest.raises(ValueError, match="positive integer"):
        s9d.run_experiment(timing_samples=bad)


def test_canonical_level_matrix():
    assert [row["ambient_events"] for row in s9d._LEVELS] == [224, 1024, 2048, 4096]


def test_run_structural_determinism(monkeypatch):
    monkeypatch.setattr(s9d, "_LEVELS", ({"id": "events_224", "ambient_events": 224},))
    left = s9d.run_experiment(timing=False, timing_samples=1)
    right = s9d.run_experiment(timing=False, timing_samples=1)
    assert left == right
    assert left["all_correct"] and left["all_exact_stage7_references"] and left["all_exact_final_roundtrips"]
    assert left["all_guarded_corruptions_rejected"]
    assert left["constraints"]["checksum_is_integrity_not_authentication"] is True


def test_restart_detects_shadow_only_divergence_after_restore(monkeypatch):
    runner = s9d.FullRestartExposure({"id": "events_224", "ambient_events": 224})
    original = s9d.ex._freeze
    shadow_calls = {"n": 0}
    def drift(contender):
        value = original(contender)
        if contender is runner.shadow:
            shadow_calls["n"] += 1
            if shadow_calls["n"] == 2:
                value = deepcopy(value); value["drift"] = True
        return value
    monkeypatch.setattr(s9d.ex, "_freeze", drift)
    with pytest.raises(RuntimeError, match="uninterrupted shadow"):
        runner.restart_sidecar()


def test_corruption_battery_records_unrejected_probe(monkeypatch):
    live = _live()
    monkeypatch.setattr(s9d, "restore_runtime", lambda blob, template: (template, None, {}))
    result = s9d._corruption_battery(live["compact"], _template())
    assert result and not any(result.values())
