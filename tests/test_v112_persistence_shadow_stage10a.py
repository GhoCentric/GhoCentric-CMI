import builtins
from copy import deepcopy
import json

import pytest

from ghost import _persistence_codec as codec
from ghost import _persistence_shadow as shadow
from ghost_research import v112_persistence_shadow_stage10a as stage10a


def _observation(sequence=1, *, record_id=None, provenance=None):
    return {
        "id": record_id or f"epistemic_{sequence:06d}",
        "kind": "observation",
        "observation_kind": "saw",
        "observer": "npc_a",
        "provenance": provenance if provenance is not None else {
            "token": "marker",
            "flag": True,
            "count": 3,
            "score": 0.75,
            "note": None,
        },
        "reliability": 0.8,
        "sequence": sequence,
        "subject": "gate",
        "tick": 7,
        "visible_features": ["smoke", "guard"],
    }


def _belief(sequence=2, *, record_id=None):
    return {
        "id": record_id or f"epistemic_{sequence:06d}",
        "kind": "belief",
        "holder": "npc_a",
        "subject": "gate",
        "confidence": 0.6,
        "evidence_ids": [],
        "previous_belief_id": None,
        "sequence": sequence,
    }


def _snapshot(records=None):
    if records is None:
        records = [
            _observation(1),
            _belief(2),
            _observation(3, record_id="custom-observation", provenance={"source": "watchtower"}),
        ]
    return {
        "mode": "full",
        "api": {
            "schema_version": "test",
            "epistemic": {
                "schema_version": "test",
                "sequence": len(records),
                "records": deepcopy(records),
            },
        },
        "host": {"value": 4},
    }


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_primitive_tag_supports_all_json_primitive_categories():
    assert [codec._primitive_tag(value) for value in (True, None, 2, 2.5, "x")] == ["b", "n", "i", "f", "s"]


def test_primitive_tag_rejects_nonprimitive_values():
    with pytest.raises(TypeError, match="unsupported provenance"):
        codec._primitive_tag([])


def test_observation_codec_roundtrip_and_custom_id():
    encoder = codec.ObservationCodec()
    first = _observation(1)
    second = _observation(2, record_id="custom", provenance={"source": "x"})
    encoder.append(first)
    encoder.append(second)
    restored = codec.ObservationCodec(encoder.snapshot())
    assert restored.decode(0) == first and restored.decode(1) == second


def test_observation_codec_reuses_string_and_schema_ids():
    encoder = codec.ObservationCodec()
    encoder.append(_observation(1, provenance={"token": "same"}))
    before_strings = len(encoder.strings)
    before_schemas = len(encoder.schemas)
    encoder.append(_observation(2, provenance={"token": "same"}))
    assert len(encoder.strings) == before_strings and len(encoder.schemas) == before_schemas


@pytest.mark.parametrize("bad", [[], {"schema": "wrong"}])
def test_observation_codec_rejects_invalid_snapshot_container_or_schema(bad):
    with pytest.raises(ValueError):
        codec.ObservationCodec(bad)


def test_observation_codec_none_constructs_empty_encoder():
    encoder = codec.ObservationCodec(None)
    assert encoder.rows == [] and encoder.strings == [] and encoder.schemas == []


def test_observation_codec_accepts_legacy_schema_identifier():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1))
    packet = encoder.snapshot(); packet["schema"] = codec.LEGACY_OBSERVATION_CODEC_SCHEMA
    assert codec.ObservationCodec(packet).decode(0) == _observation(1)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.__setitem__("strings", "bad"),
        lambda p: p.__setitem__("strings", ["dup", "dup"]),
        lambda p: p.__setitem__("provenance_schemas", "bad"),
        lambda p: p.__setitem__("rows", "bad"),
    ],
)
def test_observation_codec_rejects_invalid_top_level_tables(mutate):
    packet = codec.ObservationCodec().snapshot(); mutate(packet)
    with pytest.raises(ValueError):
        codec.ObservationCodec(packet)


@pytest.mark.parametrize(
    "schema",
    [
        [],
        {"keys": []},
        {"keys": "bad", "types": ""},
        {"keys": [], "types": 1},
        {"keys": [0], "types": ""},
        {"keys": [9], "types": "s"},
    ],
)
def test_observation_codec_rejects_invalid_provenance_schema(schema):
    packet = codec.ObservationCodec().snapshot()
    packet["strings"] = ["key"]
    packet["provenance_schemas"] = [schema]
    with pytest.raises(ValueError):
        codec.ObservationCodec(packet)


def test_observation_codec_rejects_duplicate_provenance_schema():
    packet = codec.ObservationCodec().snapshot()
    packet["strings"] = ["key"]
    packet["provenance_schemas"] = [{"keys": [0], "types": "s"}, {"keys": [0], "types": "s"}]
    with pytest.raises(ValueError, match="duplicate"):
        codec.ObservationCodec(packet)


@pytest.mark.parametrize(
    "record,exception",
    [
        ([], ValueError),
        ({"kind": "observation"}, ValueError),
        ({**_observation(1), "kind": "belief"}, ValueError),
        ({**_observation(1), "visible_features": "bad"}, TypeError),
        ({**_observation(1), "sequence": True}, ValueError),
        ({**_observation(1), "sequence": 0}, ValueError),
        ({**_observation(1), "id": ""}, ValueError),
        ({**_observation(1), "provenance": []}, TypeError),
        ({**_observation(1), "provenance": {1: "bad"}}, TypeError),
    ],
)
def test_observation_codec_append_rejects_invalid_records(record, exception):
    with pytest.raises(exception):
        codec.ObservationCodec().append(record)


@pytest.mark.parametrize(
    "row",
    [
        [],
        [None, 0, 0, [0], 0.8, 1, 0, 1, []],
    ],
)
def test_observation_codec_restore_rejects_bad_rows(row):
    encoder = codec.ObservationCodec(); encoder.append(_observation(1, provenance={"token": "x"}))
    packet = encoder.snapshot(); packet["rows"] = [row]
    with pytest.raises(ValueError):
        codec.ObservationCodec(packet)


def test_observation_codec_decode_rejects_bad_provenance_width():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1, provenance={"token": "x"}))
    encoder.rows[0][3].append(1)
    with pytest.raises(ValueError, match="width"):
        encoder.decode(0)


def test_observation_codec_decode_rejects_unknown_type_tag():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1, provenance={"token": "x"}))
    encoder.schemas[0]["types"] = "z"
    with pytest.raises(ValueError, match="type tag"):
        encoder.decode(0)


def test_observation_codec_decode_rejects_invalid_sequence():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1))
    encoder.rows[0][5] = 0
    with pytest.raises(ValueError, match="sequence"):
        encoder.decode(0)


def test_observation_codec_decode_wraps_bad_string_reference():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1))
    encoder.rows[0][1] = 999
    with pytest.raises(ValueError, match="invalid string"):
        encoder.decode(0)



def test_observation_codec_decode_rejects_invalid_schema_index():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1))
    encoder.rows[0][3][0] = 999
    with pytest.raises(ValueError, match="invalid codec"):
        encoder.decode(0)


def test_observation_codec_decode_rejects_provenance_type_mismatch():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1, provenance={"count": 3}))
    encoder.rows[0][3][1] = "wrong"
    with pytest.raises(ValueError, match="type tag"):
        encoder.decode(0)


def test_observation_codec_decode_rejects_out_of_range_position():
    encoder = codec.ObservationCodec()
    with pytest.raises(ValueError, match="invalid codec"):
        encoder.decode(0)


def test_observation_codec_decode_rejects_nonlist_visible_features_row():
    encoder = codec.ObservationCodec(); encoder.append(_observation(1))
    encoder.rows[0][8] = "bad"
    with pytest.raises(ValueError, match="visible feature row"):
        encoder.decode(0)

def test_compact_snapshot_roundtrips_exactly_and_preserves_input():
    full = _snapshot(); before = deepcopy(full)
    compact = codec.compact_snapshot(full)
    assert full == before and "records_codec" in compact["api"]["epistemic"] and codec.expand_snapshot(compact) == full


@pytest.mark.parametrize("bad", [None, [], {}])
def test_compact_snapshot_rejects_invalid_snapshot_shape(bad):
    expected = TypeError if bad is None or isinstance(bad, list) else ValueError
    with pytest.raises(expected):
        codec.compact_snapshot(bad)


def test_compact_snapshot_rejects_nonlist_records():
    full = _snapshot(); full["api"]["epistemic"]["records"] = "bad"
    with pytest.raises(ValueError, match="records must be a list"):
        codec.compact_snapshot(full)


@pytest.mark.parametrize(
    "records,match",
    [
        (["bad"], "record must be a dict"),
        ([_observation(1), _belief(2, record_id="epistemic_000001")], "ids must be unique"),
        ([_observation(2), _belief(1)], "in increasing sequence"),
    ],
)
def test_compact_snapshot_rejects_bad_record_identity_or_order(records, match):
    with pytest.raises(ValueError, match=match):
        codec.compact_snapshot(_snapshot(records))


def test_expand_snapshot_accepts_legacy_schema_ids():
    full = _snapshot(); compact = codec.compact_snapshot(full)
    encoded = compact["api"]["epistemic"]["records_codec"]
    encoded["schema"] = codec.LEGACY_RECORDS_CODEC_SCHEMA
    encoded["observation"]["schema"] = codec.LEGACY_OBSERVATION_CODEC_SCHEMA
    assert codec.expand_snapshot(compact) == full


@pytest.mark.parametrize("bad", [None, [], {}])
def test_expand_snapshot_rejects_invalid_compact_shape(bad):
    expected = TypeError if bad is None or isinstance(bad, list) else ValueError
    with pytest.raises(expected):
        codec.expand_snapshot(bad)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda e: e.update(extra=True), "invalid shape"),
        (lambda e: e.__setitem__("schema", "wrong"), "schema mismatch"),
        (lambda e: e.__setitem__("other_records", "bad"), "dict list"),
        (lambda e: e.__setitem__("other_records", ["bad"]), "dict list"),
    ],
)
def test_expand_snapshot_rejects_invalid_records_codec(mutate, match):
    compact = codec.compact_snapshot(_snapshot()); encoded = compact["api"]["epistemic"]["records_codec"]; mutate(encoded)
    with pytest.raises(ValueError, match=match):
        codec.expand_snapshot(compact)


def test_expand_snapshot_rejects_bad_other_record_sequence():
    compact = codec.compact_snapshot(_snapshot())
    compact["api"]["epistemic"]["records_codec"]["other_records"][0]["sequence"] = "bad"
    with pytest.raises(ValueError):
        codec.expand_snapshot(compact)


def test_expand_snapshot_rejects_duplicate_ids_after_decode():
    compact = codec.compact_snapshot(_snapshot())
    compact["api"]["epistemic"]["records_codec"]["other_records"][0]["id"] = "epistemic_000001"
    with pytest.raises(ValueError, match="ids must be unique"):
        codec.expand_snapshot(compact)


def test_shadow_constructor_requires_bool_enabled(tmp_path):
    with pytest.raises(TypeError, match="enabled"):
        shadow.ShadowPersistenceCandidate(tmp_path, enabled=1)


def test_shadow_disabled_is_completely_inert(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path / "disabled")
    result = store.write(_snapshot())
    assert result["attempted"] is False and not store.directory.exists()


@pytest.mark.parametrize("method", ["load", "rollback_shadow"])
def test_shadow_disabled_read_or_rollback_is_rejected(tmp_path, method):
    store = shadow.ShadowPersistenceCandidate(tmp_path / "disabled")
    with pytest.raises(RuntimeError, match="disabled"):
        getattr(store, method)()


def test_shadow_write_load_and_generation_progression(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path / "live", enabled=True)
    first = _snapshot(); second = _snapshot([_observation(1), _belief(2), _observation(3)])
    one = store.write(first); two = store.write(second); loaded = store.load()
    assert one["generation"] == 1 and two["generation"] == 2 and loaded["source"] == "candidate" and loaded["snapshot"] == second


def test_shadow_baseline_packet_requires_dict():
    with pytest.raises(TypeError, match="snapshot"):
        shadow.ShadowPersistenceCandidate._baseline_packet([], 1)


def test_shadow_candidate_packet_validates_baseline_digest():
    with pytest.raises(ValueError, match="64 hex"):
        shadow.ShadowPersistenceCandidate._candidate_packet({}, 1, "bad")


def test_shadow_manifest_packet_validates_reason_type():
    with pytest.raises(TypeError, match="reason"):
        shadow.ShadowPersistenceCandidate._manifest_packet(1, False, 3)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.__setitem__("schema", "wrong"),
        lambda p: p.__setitem__("format_version", 999),
        lambda p: p.__setitem__("generation", True),
        lambda p: p.__setitem__("generation", 0),
        lambda p: p.__setitem__("snapshot", []),
        lambda p: p.__setitem__("snapshot_sha256", "bad"),
        lambda p: p["snapshot"].__setitem__("drift", True),
    ],
)
def test_shadow_decode_baseline_rejects_invalid_packet(mutate):
    packet = shadow.ShadowPersistenceCandidate._baseline_packet(_snapshot(), 1); mutate(packet)
    with pytest.raises(ValueError):
        shadow.ShadowPersistenceCandidate._decode_baseline(packet)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.__setitem__("schema", "wrong"),
        lambda p: p.__setitem__("format_version", "bad"),
        lambda p: p.__setitem__("format_version", 999),
        lambda p: p.__setitem__("generation", 2),
        lambda p: p.__setitem__("baseline_sha256", "bad"),
        lambda p: p.__setitem__("baseline_sha256", "0" * 64),
        lambda p: p.__setitem__("compact", []),
        lambda p: p.__setitem__("compact_sha256", "bad"),
        lambda p: p["compact"].__setitem__("drift", True),
    ],
)
def test_shadow_decode_candidate_rejects_invalid_packet(mutate):
    baseline = shadow.ShadowPersistenceCandidate._baseline_packet(_snapshot(), 1)
    compact = codec.compact_snapshot(_snapshot())
    packet = shadow.ShadowPersistenceCandidate._candidate_packet(compact, 1, baseline["snapshot_sha256"]); mutate(packet)
    with pytest.raises(ValueError):
        shadow.ShadowPersistenceCandidate._decode_candidate(packet, 1, baseline["snapshot_sha256"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.__setitem__("schema", "wrong"),
        lambda p: p.__setitem__("format_version", 999),
        lambda p: p.__setitem__("generation", 2),
        lambda p: p.__setitem__("candidate_usable", 1),
        lambda p: p.__setitem__("reason", 1),
    ],
)
def test_shadow_decode_manifest_rejects_invalid_packet(mutate):
    packet = shadow.ShadowPersistenceCandidate._manifest_packet(1, True, None); mutate(packet)
    with pytest.raises(ValueError):
        shadow.ShadowPersistenceCandidate._decode_manifest(packet, 1)


def test_shadow_candidate_corruption_falls_back_to_baseline(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); store.write(full)
    store.candidate_path.write_bytes(b"{")
    loaded = store.load()
    assert loaded["source"] == "baseline" and loaded["snapshot"] == full


def test_shadow_missing_manifest_falls_back_to_baseline(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); store.write(full); store.manifest_path.unlink()
    assert store.load()["source"] == "baseline"


def test_shadow_manifest_can_mark_candidate_unusable(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); store.write(full)
    packet = shadow.ShadowPersistenceCandidate._manifest_packet(1, False, "probe"); _write_json(store.manifest_path, packet)
    loaded = store.load()
    assert loaded["source"] == "baseline" and loaded["fallback_reason"] == "probe"


def test_shadow_candidate_state_mismatch_falls_back(tmp_path, monkeypatch):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); store.write(full)
    monkeypatch.setattr(shadow, "expand_snapshot", lambda compact: {"different": True})
    assert store.load()["fallback_reason"] == "candidate_state_mismatch"


def test_shadow_candidate_encode_failure_preserves_written_baseline(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); bad = _snapshot(); bad["api"]["epistemic"]["records"][0]["provenance"] = {"bad": []}
    result = store.write(bad); loaded = store.load()
    assert result["candidate_usable"] is False and loaded["snapshot"] == bad and loaded["source"] == "baseline"


def test_shadow_manifest_write_failure_does_not_invalidate_baseline(tmp_path, monkeypatch):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); real = shadow._atomic_write
    def fail_manifest(path, data):
        if path == store.manifest_path:
            raise OSError("probe")
        return real(path, data)
    monkeypatch.setattr(shadow, "_atomic_write", fail_manifest)
    result = store.write(full)
    assert result["candidate_usable"] is False and store.baseline_path.exists()


def test_shadow_rollback_removes_only_shadow_files(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); store.write(full); store.rollback_shadow()
    loaded = store.load()
    assert store.baseline_path.exists() and not store.candidate_path.exists() and not store.manifest_path.exists() and loaded["snapshot"] == full


def test_shadow_nested_writer_lease_is_rejected(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True)
    with store._lease():
        with pytest.raises(shadow.ShadowWriterBusyError):
            with store._lease():
                assert False


def test_shadow_writer_lease_reports_missing_flock_support(tmp_path, monkeypatch):
    real_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("probe")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="flock support"):
        with shadow._WriterLease(tmp_path):
            assert False



def test_observation_codec_sid_rejects_non_string():
    with pytest.raises(TypeError, match="string value"):
        codec.ObservationCodec()._sid(1)


def test_expand_snapshot_rejects_nonpositive_sorted_sequence():
    compact = codec.compact_snapshot(_snapshot())
    compact["api"]["epistemic"]["records_codec"]["other_records"][0]["sequence"] = 0
    with pytest.raises(ValueError, match="positive integer"):
        codec.expand_snapshot(compact)


def test_shadow_digest_rejects_nonhex_64_character_text():
    with pytest.raises(ValueError, match="64 hex"):
        shadow._digest("g" * 64, "probe")


def test_shadow_json_object_rejects_non_object(tmp_path):
    path = tmp_path / "list.json"; path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        shadow._json_object(path)


def test_shadow_writer_lease_propagates_unexpected_flock_error(tmp_path, monkeypatch):
    import fcntl
    def fail(*args):
        raise OSError(5, "probe")
    monkeypatch.setattr(fcntl, "flock", fail)
    lease = shadow._WriterLease(tmp_path)
    with pytest.raises(OSError):
        lease.__enter__()


def test_shadow_writer_lease_exit_without_enter_is_safe(tmp_path):
    lease = shadow._WriterLease(tmp_path)
    assert lease.__exit__(None, None, None) is False


def test_shadow_write_detects_pre_persist_roundtrip_drift(tmp_path, monkeypatch):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot()
    monkeypatch.setattr(shadow, "expand_snapshot", lambda compact: {"drift": True})
    result = store.write(full)
    assert result["candidate_usable"] is False and "roundtrip drifted" in result["reason"]


def test_shadow_write_detects_post_persist_roundtrip_drift(tmp_path, monkeypatch):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); full = _snapshot(); real = codec.expand_snapshot
    calls = {"n": 0}
    def drift_second(compact):
        calls["n"] += 1
        return real(compact) if calls["n"] == 1 else {"drift": True}
    monkeypatch.setattr(shadow, "expand_snapshot", drift_second)
    result = store.write(full)
    assert result["candidate_usable"] is False and "persisted candidate" in result["reason"]


def test_shadow_rollback_is_idempotent(tmp_path):
    store = shadow.ShadowPersistenceCandidate(tmp_path, enabled=True); store.write(_snapshot()); store.rollback_shadow(); store.rollback_shadow()
    assert store.baseline_path.exists()

def test_stage10a_normalizes_only_legacy_codec_schema_names():
    full = _snapshot(); compact = codec.compact_snapshot(full)
    legacy = deepcopy(compact)
    legacy["api"]["epistemic"]["records_codec"]["schema"] = codec.LEGACY_RECORDS_CODEC_SCHEMA
    legacy["api"]["epistemic"]["records_codec"]["observation"]["schema"] = codec.LEGACY_OBSERVATION_CODEC_SCHEMA
    assert stage10a._normalize_legacy(legacy) == compact


def test_stage10a_bad_candidate_probe_requires_observation():
    with pytest.raises(RuntimeError, match="requires at least one observation"):
        stage10a._bad_candidate_snapshot(_snapshot([_belief(1)]))


def test_stage10a_rewrite_json_applies_transform(tmp_path):
    path = tmp_path / "x.json"; _write_json(path, {"a": 1})
    stage10a._rewrite_json(path, lambda packet: packet.__setitem__("a", 2))
    assert json.loads(path.read_text()) == {"a": 2}



def test_stage10a_profile_rejects_production_codec_roundtrip_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(stage10a, "expand_snapshot", lambda compact: {"drift": True})
    with pytest.raises(RuntimeError, match="production codec"):
        stage10a._profile_level({"id": "probe", "ambient_events": 1}, tmp_path)

def test_stage10a_experiment_passes_all_preregistered_gates():
    result = stage10a.run_experiment()
    assert result["strict_verdict"] == stage10a.VERDICT and result["all_gates_pass"] and all(result["gates"].values())
