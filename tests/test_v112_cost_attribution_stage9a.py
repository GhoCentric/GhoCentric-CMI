from copy import deepcopy
import inspect

import pytest

from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7


def small_level():
    return {"id": "test_ambient", "ambient_events": 8}


def frozen_small():
    return ex.blind_exposure(small_level(), "full")["frozen"]


def test_schema_and_verdict():
    result = s9a.run_experiment(timing=False)
    assert result["schema"] == s9a.SCHEMA
    assert result["strict_verdict"] == s9a.VERDICT


def test_levels_are_frozen_attribution_scales():
    result = s9a.run_experiment(timing=False)
    assert [row["level"]["ambient_events"] for row in result["levels"]] == [224, 1024, 2048]


def test_index_rejects_non_full_state():
    with pytest.raises(ValueError, match="Full-Ghost"):
        s9a.FrozenGhostIndex({"mode": "baseline"})


def test_index_builder_has_no_task_registry_dependency():
    source = inspect.getsource(s9a.FrozenGhostIndex.__init__)
    assert "reveal_tasks" not in source
    assert "recent_marker_source" not in source
    assert "novel_delegate_choice" not in source


def test_pair_key_parses_and_rejects_bad_keys():
    assert s9a._pair_key("a|b") == ("a", "b")
    for bad in ["a", "|b", "a|"]:
        with pytest.raises(ValueError, match="invalid relationship"):
            s9a._pair_key(bad)



def test_index_ignores_observation_without_token():
    frozen = frozen_small()
    for row in frozen["api"]["epistemic"]["records"]:
        if row.get("kind") == "observation":
            row.get("provenance", {}).pop("token", None)
            break
    index = s9a.FrozenGhostIndex(frozen)
    assert index.record_position_by_id


def test_index_payload_is_json_safe_and_nonempty():
    index = s9a.FrozenGhostIndex(frozen_small())
    assert s9a._json_bytes(index.index_payload()) > 0
    assert index.record_position_by_id


def test_index_answer_matches_stage7_for_every_task():
    frozen = frozen_small()
    index = s9a.FrozenGhostIndex(frozen)
    for task in s7.reveal_tasks():
        assert index.answer(task) == s7._answer(frozen, task)["answer"]


def test_index_missing_marker_returns_none():
    index = s9a.FrozenGhostIndex(frozen_small())
    task = {"id": "x", "kind": "recent_marker_source", "args": {"token": "missing"}}
    assert index.answer(task) is None


def test_index_missing_belief_returns_none_and_empty_evidence():
    index = s9a.FrozenGhostIndex(frozen_small())
    assert index._belief(ex.AGENT, "missing") is None
    assert index._evidence("missing") == []
    task = {"id": "x", "kind": "current_belief_dominant", "args": {"subject": "missing"}}
    assert index.answer(task) is None


def test_index_relationship_reverse_lookup_and_missing():
    index = s9a.FrozenGhostIndex(frozen_small())
    key = next(iter(index.relationships))
    assert index._relationship(*key) == index._relationship(*reversed(key))
    with pytest.raises(KeyError):
        index._relationship("missing-a", "missing-b")


def test_index_low_duty_delegate_uses_trust_branch():
    index = s9a.FrozenGhostIndex(frozen_small())
    index.agent_values[ex.AGENT] = {"duty": 0.0}
    task = next(row for row in s7.reveal_tasks() if row["kind"] == "novel_delegate_choice")
    answer = index.answer(task)
    sources = task["args"]["sources"]
    expected = sorted(sources, key=lambda source: (-float(index._relationship(ex.AGENT, source)["trust"]), source))[0]
    assert answer == expected


def test_index_unhandled_kind_is_guarded(monkeypatch):
    index = s9a.FrozenGhostIndex(frozen_small())
    monkeypatch.setattr(s7, "_validated_task", lambda task: {"id": "x", "kind": "impossible", "args": {}})
    with pytest.raises(RuntimeError, match="unhandled"):
        index.answer({"ignored": True})


def test_storage_attribution_maps_snapshot_and_epistemic_kinds():
    frozen = frozen_small()
    result = s9a._storage_attribution(frozen)
    assert result["full_snapshot_bytes"] == s9a._json_bytes(frozen)
    assert set(result["api_component_value_bytes"]) >= {"engine", "epistemic", "perception", "agents"}
    assert result["epistemic_record_counts"]["observation"] > 0
    assert 0.0 < result["epistemic_fraction_of_snapshot"] < 1.0


def test_indexed_work_is_smaller_than_current_epistemic_scan_on_small_case():
    frozen = frozen_small()
    tasks = s7.reveal_tasks()
    index = s9a.FrozenGhostIndex(frozen)
    indexed = s9a._indexed_work(index, tasks)
    from ghost_research import v112_resource_cost_stage9 as s9
    current = s9._ghost_work(frozen, tasks)
    assert indexed["indexed_record_reads_per_battery"] < current["epistemic_records_examined_per_battery"]
    assert indexed["index_payload_bytes"] > 0


def test_battery_helpers_do_not_mutate_state():
    from ghost_research import v112_resource_cost_stage9 as s9
    frozen = frozen_small()
    archive = s9._archive_exposure(small_level())["archive_frozen"]
    frozen_before, archive_before = deepcopy(frozen), deepcopy(archive)
    tasks = s7.reveal_tasks()
    s9._query_battery_warm(s9.WarmGhostReader(frozen), tasks, 2)
    s9a._battery_indexed(s9a.FrozenGhostIndex(frozen), tasks, 2)
    s9._query_battery_archive(archive, tasks, 2)
    assert frozen == frozen_before
    assert archive == archive_before



def test_task_timing_returns_every_task_id():
    index = s9a.FrozenGhostIndex(frozen_small())
    tasks = s7.reveal_tasks()
    result = s9a._task_timing(index, tasks, 1)
    assert set(result) == {task["id"] for task in tasks}
    assert all(value >= 0.0 for value in result.values())



def test_profile_rejects_mismatched_exposure(monkeypatch):
    from ghost_research import v112_resource_cost_stage9 as s9

    original = s9._archive_exposure
    def altered(level):
        value = original(level)
        value["host_ledger"][0]["kind"] = "different"
        return value
    monkeypatch.setattr(s9, "_archive_exposure", altered)
    with pytest.raises(RuntimeError, match="identical exposure"):
        s9a._profile_level(small_level(), timing=False, samples=1)


def test_profile_without_timing_preserves_three_way_correctness():
    row = s9a._profile_level(small_level(), timing=False, samples=1)
    assert row["correctness"]["all_correct"] is True
    assert len(row["correctness"]["rows"]) == 10
    assert row["timing"] is None


def test_profile_with_timing_populates_attribution_lanes():
    row = s9a._profile_level(small_level(), timing=True, samples=1)
    timing = row["timing"]
    assert set(timing) == {
        "samples", "index_build_us", "current_battery_us", "indexed_battery_us", "archive_battery_us",
        "current_100_batteries_us", "indexed_100_batteries_us", "archive_100_batteries_us",
        "current_task_us", "indexed_task_us",
    }
    assert timing["samples"] == 1


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "7"])
def test_run_experiment_rejects_invalid_timing_samples(bad):
    with pytest.raises(ValueError, match="positive integer"):
        s9a.run_experiment(timing_samples=bad)


def test_run_experiment_claim_boundary_and_constraints():
    result = s9a.run_experiment(timing=False)
    assert result["all_three_correct"] is True
    constraints = result["constraints"]
    assert constraints["stage9_behavioral_question_frozen"] is True
    assert constraints["production_ghost_modified"] is False
    assert constraints["index_built_without_tasks"] is True
    assert constraints["index_is_research_only"] is True
    assert constraints["timing_is_telemetry_not_gate"] is True
    assert constraints["no_weighted_composite_score"] is True
    assert "does not establish a production optimization" in result["claim_boundary"]
