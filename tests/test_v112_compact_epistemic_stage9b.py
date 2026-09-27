from __future__ import annotations

from copy import deepcopy
import json

import pytest

from ghost_research import v112_compact_epistemic_codec_stage9b as codec
from ghost_research import v112_compact_epistemic_stage9b as stage9b
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_resource_cost_stage9 as s9


@pytest.fixture(scope="module")
def full224() -> dict:
    return ex.blind_exposure({"id": "events_224", "ambient_events": 224}, "full")


@pytest.fixture(scope="module")
def compact224(full224: dict) -> dict:
    return codec.compact_snapshot(full224["frozen"])


def _observation(**overrides) -> dict:
    row = {
        "id": "epistemic_000001",
        "kind": "observation",
        "observation_kind": "social",
        "observer": "guard_00",
        "provenance": {"token": "alpha", "source": "world", "host_step": 1},
        "reliability": 1.0,
        "sequence": 1,
        "subject": "visitor_00",
        "tick": 0,
        "visible_features": ["alpha", "alpha"],
    }
    row.update(overrides)
    return row


def test_json_bytes_is_canonical() -> None:
    assert codec.json_bytes({"b": 2, "a": 1}) == len(b'{"a":1,"b":2}')


@pytest.mark.parametrize(
    ("value", "tag"),
    [(True, "b"), (None, "n"), (2, "i"), (2.5, "f"), ("x", "s")],
)
def test_primitive_tags(value, tag) -> None:
    assert codec._primitive_tag(value) == tag


def test_primitive_tag_rejects_nested_value() -> None:
    with pytest.raises(TypeError, match="unsupported provenance"):
        codec._primitive_tag({"nested": True})


def test_codec_rejects_empty_observations() -> None:
    with pytest.raises(ValueError, match="at least one"):
        codec.observation_codec([])


def test_codec_rejects_wrong_schema() -> None:
    row = _observation()
    row.pop("observer")
    with pytest.raises(ValueError, match="unexpected"):
        codec.observation_codec([row])


def test_codec_rejects_non_observation_kind() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        codec.observation_codec([_observation(kind="belief")])


def test_codec_rejects_non_string_visible_feature() -> None:
    with pytest.raises(TypeError, match="visible_features"):
        codec.observation_codec([_observation(visible_features=["alpha", 3])])


def test_codec_handles_non_derived_ids_and_variable_fields() -> None:
    first = _observation(id="custom-a", reliability=0.8, tick=1)
    second = _observation(
        id="custom-b", sequence=2, observation_kind="visual", observer="guard_01",
        reliability=0.9, tick=2, subject="visitor_01",
        provenance={"token": "beta", "source": "witness", "host_step": 2, "flag": True,
                    "missing": None, "weight": 0.5},
        visible_features=["beta", "detail"],
    )
    packed = codec.observation_codec([first, second])
    assert packed["id_from_sequence"] is False
    assert packed["constants"] == {}
    assert [codec.decode_observation(packed, row) for row in packed["rows"]] == [first, second]


def test_codec_derives_ids_and_constants() -> None:
    rows = [_observation(), _observation(id="epistemic_000002", sequence=2, subject="visitor_01")]
    packed = codec.observation_codec(rows)
    assert packed["id_from_sequence"] is True
    assert set(packed["constants"]) == {"observation_kind", "observer", "reliability", "tick"}
    assert [codec.decode_observation(packed, row) for row in packed["rows"]] == rows


def test_decode_rejects_trailing_row_data() -> None:
    packed = codec.observation_codec([_observation()])
    bad = deepcopy(packed["rows"][0]) + ["extra"]
    with pytest.raises(ValueError, match="trailing data"):
        codec.decode_observation(packed, bad)


def test_compact_snapshot_rejects_wrong_mode() -> None:
    with pytest.raises(ValueError, match="Full-Ghost"):
        codec.compact_snapshot({"mode": "compact"})


def test_compact_snapshot_rejects_unsorted_records(full224: dict) -> None:
    frozen = deepcopy(full224["frozen"])
    frozen["api"]["epistemic"]["records"][:2] = reversed(frozen["api"]["epistemic"]["records"][:2])
    with pytest.raises(ValueError, match="sequence ordered"):
        codec.compact_snapshot(frozen)


def test_full_snapshot_roundtrip_is_exact(full224: dict, compact224: dict) -> None:
    assert codec.expand_snapshot(compact224) == full224["frozen"]


def test_expand_rejects_unknown_codec(compact224: dict) -> None:
    compact = deepcopy(compact224)
    compact["api"]["epistemic"]["records_codec"]["schema"] = "unknown"
    with pytest.raises(ValueError, match="unsupported compact"):
        codec.expand_snapshot(compact)


def test_compact_index_rejects_wrong_mode() -> None:
    with pytest.raises(ValueError, match="compact Full-Ghost"):
        codec.CompactGhostIndex({"mode": "wrong"})


def test_compact_index_preserves_stage7_answers(full224: dict, compact224: dict) -> None:
    reader = codec.CompactGhostIndex(compact224)
    for task in s7.reveal_tasks():
        assert reader.answer(task) == s7._ground_truth(full224["host_ledger"], task)


def test_compact_index_missing_belief_and_marker(compact224: dict) -> None:
    reader = codec.CompactGhostIndex(compact224)
    assert reader._belief("nobody", "nothing") is None
    assert reader._evidence("nothing") == []
    assert reader._marker({"token": "not-present"}) is None


def test_index_payload_is_json_safe(compact224: dict) -> None:
    payload = codec.CompactGhostIndex(compact224).index_payload()
    assert json.loads(json.dumps(payload)) == payload


def test_observation_diagnostics_expose_nonadditive_attribution(full224: dict, compact224: dict) -> None:
    observations = [r for r in full224["frozen"]["api"]["epistemic"]["records"] if r["kind"] == "observation"]
    packed = compact224["api"]["epistemic"]["records_codec"]["observation"]
    result = codec.observation_diagnostics(observations, packed)
    assert result["diagnostics_are_non_additive"] is True
    assert result["observation_bytes_saved"] > 0
    assert result["compact_observation_codec_bytes"] < result["original_observation_list_bytes"]
    assert result["provenance_schema_count"] == 6


def test_compact_work_matches_indexed_logical_reads(compact224: dict) -> None:
    work = stage9b._compact_work(codec.CompactGhostIndex(compact224), s7.reveal_tasks())
    assert work["indexed_record_reads_per_battery"] == 15
    assert work["indexed_relationship_reads_per_battery"] > 0
    assert work["index_payload_bytes"] > 0


def test_correctness_four_way(full224: dict, compact224: dict) -> None:
    archive = s9._archive_exposure({"id": "events_224", "ambient_events": 224})
    result = stage9b._correctness(full224, archive, compact224, s7.reveal_tasks())
    assert result["all_correct"] is True
    assert len(result["rows"]) == 10


def test_storage_reports_compact_and_archive(full224: dict, compact224: dict) -> None:
    archive = s9._archive_exposure({"id": "events_224", "ambient_events": 224})
    current_index = stage9b.s9a.FrozenGhostIndex(full224["frozen"])
    compact_index = codec.CompactGhostIndex(compact224)
    result = stage9b._storage(full224, archive, compact224, current_index, compact_index)
    assert result["compact_snapshot_bytes"] < result["current_snapshot_bytes"]
    assert result["compact_plus_index_bytes"] > result["compact_snapshot_bytes"]


def test_timing_probe_has_all_paths(full224: dict, compact224: dict) -> None:
    archive = s9._archive_exposure({"id": "events_224", "ambient_events": 224})
    result = stage9b._timing(full224, archive, compact224, s7.reveal_tasks(), 1)
    assert result["samples"] == 1
    assert result["compact_build_us"] >= 0.0
    assert result["compact_indexed_battery_us"] >= 0.0
    assert result["archive_100_batteries_us"] >= 0.0


def test_profile_level_without_timing() -> None:
    result = stage9b._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)
    assert result["lossless_full_snapshot_roundtrip"] is True
    assert result["correctness"]["all_correct"] is True
    assert result["timing"] is None


def test_profile_level_with_timing() -> None:
    result = stage9b._profile_level({"id": "events_224", "ambient_events": 224}, timing=True, samples=1)
    assert result["timing"]["samples"] == 1


def test_profile_rejects_mismatched_host_ledgers(monkeypatch) -> None:
    original = stage9b.s9._archive_exposure
    def altered(level):
        value = original(level)
        value["host_ledger"] = value["host_ledger"] + [{"forced": "mismatch"}]
        return value
    monkeypatch.setattr(stage9b.s9, "_archive_exposure", altered)
    with pytest.raises(RuntimeError, match="identical exposure"):
        stage9b._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)


def test_profile_rejects_roundtrip_drift(monkeypatch) -> None:
    monkeypatch.setattr(stage9b.codec, "expand_snapshot", lambda compact: {"drift": True})
    with pytest.raises(RuntimeError, match="exact-roundtrip"):
        stage9b._profile_level({"id": "events_224", "ambient_events": 224}, timing=False, samples=1)


@pytest.mark.parametrize("bad", [True, 0, 1.5])
def test_run_experiment_rejects_bad_timing_samples(bad) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        stage9b.run_experiment(timing_samples=bad)


def test_run_experiment_deterministic_structural_result() -> None:
    left = stage9b.run_experiment(timing=False)
    right = stage9b.run_experiment(timing=False)
    assert left == right
    assert left["strict_verdict"] == stage9b.VERDICT
    assert left["all_four_correct"] is True
    assert left["all_lossless_roundtrips"] is True
    assert [row["level"]["ambient_events"] for row in left["levels"]] == [224, 1024, 2048]


def test_claim_boundary_keeps_incremental_cost_open() -> None:
    result = stage9b.run_experiment(timing=False, timing_samples=1)
    assert result["constraints"]["incremental_write_cost_not_tested"] is True
    assert result["constraints"]["compact_index_built_without_tasks"] is True
    assert result["constraints"]["research_only"] is True

def test_observation_token_index_skips_rows_without_token() -> None:
    packed = codec.observation_codec([_observation(provenance={"source": "world", "host_step": 1})])
    assert codec._observation_token_positions(packed) == {}
