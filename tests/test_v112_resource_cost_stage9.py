from copy import deepcopy

import pytest

from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_resource_cost_stage9 as s9


def small_level():
    return {"id": "test_ambient", "ambient_events": 8}


def test_schema_and_verdict():
    result = s9.run_experiment(timing=False)
    assert result["schema"] == s9.SCHEMA
    assert result["strict_verdict"] == s9.VERDICT


def test_canonical_levels_are_structural_scale_curve():
    levels = s9.canonical_levels()
    assert [row["ambient_events"] for row in levels] == [64, 128, 224, 512, 1024, 2048]
    assert len({row["id"] for row in levels}) == 6


@pytest.mark.parametrize("bad", [None, [], {"id": "x"}, {"id": "x", "ambient_events": 1, "extra": 2}])
def test_level_rejects_bad_shape(bad):
    with pytest.raises(ValueError, match="invalid shape"):
        s9._level(bad)


@pytest.mark.parametrize("bad,pattern", [(0, "at least one"), (-1, "non-negative")])
def test_level_requires_positive_ambient_events(bad, pattern):
    with pytest.raises(ValueError, match=pattern):
        s9._level({"id": "x", "ambient_events": bad})


def test_archive_exposure_is_task_blind_and_json_sized():
    exposure = s9._archive_exposure(small_level())
    assert exposure["archive_frozen"]["archive"]["writer_policy"] == "append_external_observations_verbatim"
    assert exposure["snapshot_bytes"] == len(s9._json_bytes(exposure["archive_frozen"]))


def test_archive_exposure_does_not_alias_host_ledger():
    exposure = s9._archive_exposure(small_level())
    before = deepcopy(exposure["archive_frozen"])
    exposure["host_ledger"][0]["kind"] = "mutated"
    assert exposure["archive_frozen"] == before


def test_warm_reader_rejects_non_full_state():
    with pytest.raises(ValueError, match="Full-Ghost"):
        s9.WarmGhostReader({"mode": "baseline"})


def test_warm_reader_matches_exact_stage7_full_answers():
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    reader = s9.WarmGhostReader(exposure["frozen"])
    for task in s7.reveal_tasks():
        assert reader.answer(task) == s7._answer(exposure["frozen"], task)["answer"]



def test_warm_reader_handles_missing_belief(monkeypatch):
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    reader = s9.WarmGhostReader(exposure["frozen"])
    monkeypatch.setattr(reader.api, "get_belief", lambda *args, **kwargs: None)
    assert reader._evidence("missing") == []
    task = {"id": "current_belief_dominant", "kind": "current_belief_dominant", "args": {"subject": ex.SUBJECT}}
    assert reader.answer(task) is None


def test_warm_reader_delegate_missing_agent_is_guarded(monkeypatch):
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    reader = s9.WarmGhostReader(exposure["frozen"])
    monkeypatch.setattr(reader.api, "agent", lambda *args, **kwargs: None)
    task = next(row for row in s7.reveal_tasks() if row["kind"] == "novel_delegate_choice")
    with pytest.raises(RuntimeError, match="disappeared"):
        reader.answer(task)


def test_warm_reader_delegate_low_duty_uses_trust_branch(monkeypatch):
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    reader = s9.WarmGhostReader(exposure["frozen"])

    class DummyAgent:
        def values(self):
            return {"duty": 0.0}

    monkeypatch.setattr(reader.api, "agent", lambda *args, **kwargs: DummyAgent())
    monkeypatch.setattr(
        reader.api,
        "get_relationship",
        lambda agent, source: {"trust": 0.5 if source == ex.WITNESS_B else 0.1, "maturity": 0.0},
    )
    task = next(row for row in s7.reveal_tasks() if row["kind"] == "novel_delegate_choice")
    assert reader.answer(task) == ex.WITNESS_B

def test_warm_reader_unhandled_kind_is_guarded(monkeypatch):
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    reader = s9.WarmGhostReader(exposure["frozen"])
    monkeypatch.setattr(s7, "_validated_task", lambda task: {"id": "x", "kind": "impossible", "args": {}})
    with pytest.raises(RuntimeError, match="unhandled"):
        reader.answer({"ignored": True})


def test_marker_scan_count_finds_from_tail_and_missing():
    rows = [
        {"kind": "observation", "provenance": {"token": "a"}},
        {"kind": "belief"},
        {"kind": "observation", "provenance": {"token": "b"}},
    ]
    assert s9._marker_scan_count(rows, "b") == 1
    assert s9._marker_scan_count(rows, "a") == 3
    assert s9._marker_scan_count(rows, "missing") == 3


def test_ghost_work_has_expected_fixed_lookup_contract():
    from ghost_research import v112_latent_exposure_stage7 as ex

    exposure = ex.blind_exposure(small_level(), "full")
    work = s9._ghost_work(exposure["frozen"], s7.reveal_tasks())
    assert work["cold_snapshot_rehydrates_per_battery"] == 10
    assert work["warm_snapshot_rehydrates_per_session"] == 1
    assert work["relationship_lookups_per_battery"] == 6
    assert work["belief_lookups_per_battery"] == 3
    assert work["agent_value_lookups_per_battery"] == 1
    assert work["epistemic_records_examined_per_battery"] >= work["epistemic_record_count"] * 3


def test_correctness_rejects_mismatched_exposure():
    from ghost_research import v112_latent_exposure_stage7 as ex

    full = ex.blind_exposure(small_level(), "full")
    archive = s9._archive_exposure(small_level())
    archive["host_ledger"][0]["kind"] = "different"
    with pytest.raises(RuntimeError, match="identical exposure"):
        s9._correctness(full, archive, s7.reveal_tasks())


def test_correctness_full_warm_and_archive_all_match():
    from ghost_research import v112_latent_exposure_stage7 as ex

    full = ex.blind_exposure(small_level(), "full")
    archive = s9._archive_exposure(small_level())
    result = s9._correctness(full, archive, s7.reveal_tasks())
    assert result["full_correct"] == 10
    assert result["archive_correct"] == 10
    assert len(result["rows"]) == 10


def test_median_us_executes_requested_samples():
    calls = []
    value = s9._median_us(lambda: calls.append(1), 3)
    assert len(calls) == 3
    assert value >= 0.0


def test_query_helpers_are_read_only():
    from ghost_research import v112_latent_exposure_stage7 as ex

    full = ex.blind_exposure(small_level(), "full")["frozen"]
    archive = s9._archive_exposure(small_level())["archive_frozen"]
    full_before, archive_before = deepcopy(full), deepcopy(archive)
    tasks = s7.reveal_tasks()
    s9._query_battery_full(full, tasks)
    reader = s9.WarmGhostReader(full)
    s9._query_battery_warm(reader, tasks, 2)
    s9._query_battery_archive(archive, tasks, 2)
    assert full == full_before
    assert archive == archive_before


def test_timing_returns_all_resource_lanes():
    from ghost_research import v112_latent_exposure_stage7 as ex

    full = ex.blind_exposure(small_level(), "full")
    archive = s9._archive_exposure(small_level())
    timing = s9._timing(small_level(), full, archive, s7.reveal_tasks(), 1)
    expected = {
        "samples", "query_repetitions", "ingest_full_us", "ingest_archive_us",
        "serialize_full_us", "serialize_archive_us", "restore_full_us", "restore_archive_us",
        "cold_full_battery_us", "warm_full_battery_us", "archive_battery_us",
        "warm_full_100_batteries_us", "archive_100_batteries_us",
    }
    assert set(timing) == expected
    assert all(timing[key] >= 0.0 for key in expected - {"samples", "query_repetitions"})


def test_profile_without_timing_has_cost_and_correctness():
    row = s9._profile_level(small_level(), timing=False, timing_samples=1)
    assert row["correctness"]["full_correct"] == 10
    assert row["correctness"]["archive_correct"] == 10
    assert row["state"]["full_snapshot_bytes"] > 0
    assert row["state"]["archive_snapshot_bytes"] > 0
    assert row["timing"] is None


def test_profile_with_timing_populates_telemetry():
    row = s9._profile_level(small_level(), timing=True, timing_samples=1)
    assert row["timing"]["samples"] == 1
    assert row["timing"]["query_repetitions"] == 100


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "7"])
def test_run_matrix_rejects_invalid_timing_samples(bad):
    with pytest.raises(ValueError, match="positive integer"):
        s9.run_matrix([small_level()], timing_samples=bad)


def test_run_matrix_rejects_empty_level_set():
    with pytest.raises(ValueError, match="at least one"):
        s9.run_matrix([])


def test_run_matrix_custom_level_is_correct_and_no_weighted_score():
    matrix = s9.run_matrix([small_level()], timing=False)
    assert matrix["all_full_and_archive_correct"] is True
    assert matrix["timing_enabled"] is False
    assert matrix["timing_is_telemetry_not_gate"] is True
    assert matrix["no_weighted_composite_score"] is True
    assert matrix["query_repetitions"] == 100


def test_run_matrix_timing_lane_is_optional():
    matrix = s9.run_matrix([small_level()], timing=True, timing_samples=1)
    assert matrix["timing_enabled"] is True
    assert matrix["levels"][0]["timing"] is not None


def test_run_experiment_constraints_preserve_claim_boundary():
    result = s9.run_experiment(timing=False)
    constraints = result["constraints"]
    assert constraints["stage8_behavioral_question_frozen"] is True
    assert constraints["full_and_archive_must_remain_correct"] is True
    assert constraints["ghost_cold_query_is_exact_stage7_path"] is True
    assert constraints["ghost_warm_query_removes_only_repeated_snapshot_restore"] is True
    assert constraints["archive_query_is_exact_stage8_read_only_scan_path"] is True
    assert constraints["timing_thresholds"] is False
    assert constraints["weighted_winner_score"] is False
    assert "device-specific telemetry" in result["claim_boundary"]
