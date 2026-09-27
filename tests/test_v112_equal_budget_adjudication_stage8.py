from __future__ import annotations

from copy import deepcopy
import json

import pytest

from ghost_research import v112_equal_budget_archive_stage8 as ar
from ghost_research import v112_equal_budget_adjudication_stage8 as s8
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7


@pytest.mark.parametrize("level_id,budget", [
    ("within_window", 76806),
    ("first_overflow", 110461),
    ("deep_overflow", 146792),
])
def test_preregistered_budgets(level_id, budget):
    assert ar.budget_for(level_id) == budget


@pytest.mark.parametrize("bad", ["unknown", ""])
def test_unknown_budget_rejected(bad):
    with pytest.raises(ValueError):
        ar.budget_for(bad)


def test_encode_bytes_is_canonical_and_finite():
    assert ar.encode_bytes({"b": 1, "a": 2}) == len(b'{"a":2,"b":1}')
    with pytest.raises(ValueError):
        ar.encode_bytes({"x": float("nan")})


def test_observation_rows_require_list():
    with pytest.raises(ValueError):
        ar._observation_rows({})


def test_observation_rows_reject_bad_shape():
    with pytest.raises(ValueError):
        ar._observation_rows([{"step": 1}])


@pytest.mark.parametrize("rows", [
    [{"step": 0, "kind": "observation"}],
    [{"step": 1, "kind": "observation"}, {"step": 1, "kind": "observation"}],
])
def test_observation_rows_require_monotonic_positive_steps(rows):
    with pytest.raises(ValueError):
        ar._observation_rows(rows)


def test_observation_rows_store_only_external_observations():
    rows = [
        {"step": 1, "kind": "observation", "event": "x"},
        {"step": 2, "kind": "belief_revision", "signal": 1.0},
        {"step": 3, "kind": "observation", "event": "y"},
    ]
    out = ar._observation_rows(rows)
    assert [x["event"] for x in out] == ["x", "y"]
    rows[0]["event"] = "mutated"
    assert out[0]["event"] == "x"


def test_freeze_archive_requires_compact_baseline():
    with pytest.raises(ValueError):
        ar.freeze_archive("within_window", {"mode": "full"}, [])


def test_freeze_archive_is_task_blind_and_within_budget():
    exposure = ex.blind_exposure(ex.canonical_levels()[0], "baseline")
    frozen = ar.freeze_archive("within_window", exposure["frozen"], exposure["host_ledger"])
    assert frozen["archive"]["writer_policy"] == "append_external_observations_verbatim"
    assert frozen["used_bytes"] <= frozen["allocated_budget_bytes"]
    assert frozen["headroom_bytes"] == frozen["allocated_budget_bytes"] - frozen["used_bytes"]
    assert all(row["kind"] == "observation" for row in frozen["archive"]["records"])


def test_freeze_archive_does_not_alias_inputs():
    exposure = ex.blind_exposure(ex.canonical_levels()[0], "baseline")
    frozen = ar.freeze_archive("within_window", exposure["frozen"], exposure["host_ledger"])
    exposure["frozen"]["flat"]["sequence"] = -1
    exposure["host_ledger"][0]["kind"] = "mutated"
    assert frozen["compact"]["flat"]["sequence"] >= 0
    assert frozen["archive"]["records"][0]["kind"] == "observation"


def test_records_validation():
    with pytest.raises(ValueError):
        ar.records({})
    with pytest.raises(ValueError):
        ar.records({"mode": "archive_baseline", "archive": {"schema": "bad", "records": []}})
    with pytest.raises(ValueError):
        ar.records({"mode": "archive_baseline", "archive": {"schema": ar.SCHEMA, "records": "bad"}})


@pytest.fixture(scope="module")
def matrix():
    return s8.run_matrix()


@pytest.fixture(scope="module")
def experiment():
    return s8.run_experiment()


@pytest.mark.parametrize("level_id,full,compact,archive", [
    ("within_window", 10, 10, 10),
    ("first_overflow", 10, 3, 10),
    ("deep_overflow", 10, 3, 10),
])
def test_level_scores(matrix, level_id, full, compact, archive):
    row = next(x for x in matrix["levels"] if x["level"]["id"] == level_id)
    assert (row["full"]["correct"], row["compact"]["correct"], row["archive"]["correct"]) == (full, compact, archive)


@pytest.mark.parametrize("level_id,used,budget,records", [
    ("within_window", 29548, 76806, 80),
    ("first_overflow", 48822, 110461, 144),
    ("deep_overflow", 65608, 146792, 240),
])
def test_archive_budget_telemetry(matrix, level_id, used, budget, records):
    row = next(x for x in matrix["levels"] if x["level"]["id"] == level_id)
    state = row["state"]
    assert state["archive_used_bytes"] == used
    assert state["archive_allocated_budget_bytes"] == budget
    assert state["archive_record_count"] == records
    assert state["archive_within_full_budget"] is True


@pytest.mark.parametrize("level_id,scans,examined", [
    ("within_window", 0, 0),
    ("first_overflow", 7, 1007),
    ("deep_overflow", 7, 1679),
])
def test_archive_reconstruction_telemetry(matrix, level_id, scans, examined):
    row = next(x for x in matrix["levels"] if x["level"]["id"] == level_id)
    assert row["archive"]["archive_scans"] == scans
    assert row["archive"]["records_examined"] == examined


def test_stage7_anchor_is_preserved(matrix):
    assert matrix["totals"]["full"] == {"correct": 30, "supported": 30, "unsupported": 0}
    assert matrix["totals"]["compact"] == {"correct": 16, "supported": 16, "unsupported": 14}


def test_archive_recovers_all_stage7_tasks(matrix):
    assert matrix["totals"]["archive"] == {"correct": 30, "supported": 30, "unsupported": 0}
    assert matrix["comparative_outcome"] == "generic_archive_recovers_stage7_gap"


def test_archive_storage_constraints(matrix):
    assert matrix["archive_budget_valid"] is True
    assert matrix["archive_taskblind_storage"] is True
    assert matrix["posthoc_archive_reconstruction_read_only"] is True
    assert matrix["same_external_exposure"] is True


def test_empty_matrix_rejected():
    with pytest.raises(ValueError):
        s8.run_matrix([])


def test_archive_answer_uses_compact_state_when_available():
    exposure = s8._archive_exposure(ex.canonical_levels()[0])
    task = next(x for x in s7.reveal_tasks() if x["id"] == "recent_marker_source")
    out = s8._archive_answer(exposure["archive_frozen"], task)
    assert out == {"status": "supported", "answer": "witness_c", "access": "compact_state", "records_examined": 0}


@pytest.mark.parametrize("task_id,expected", [
    ("early_marker_source", "witness_a"),
    ("relationship_event_count", 5),
    ("evidence_sources", ["witness_a", "witness_b", "witness_c"]),
    ("belief_revision_count", 4),
    ("counterfactual_without_a", "benign"),
    ("deeper_relationship", "witness_a"),
    ("novel_delegate_choice", "witness_a"),
])
def test_archive_recovers_overflow_history_tasks(task_id, expected):
    exposure = s8._archive_exposure(ex.canonical_levels()[2])
    task = next(x for x in s7.reveal_tasks() if x["id"] == task_id)
    out = s8._archive_answer(exposure["archive_frozen"], task)
    assert out["status"] == "supported"
    assert out["answer"] == expected
    assert out["access"] == "generic_archive_scan"
    assert out["records_examined"] > 0


def test_archive_answer_can_report_unsupported_for_unmapped_kind(monkeypatch):
    exposure = s8._archive_exposure(ex.canonical_levels()[2])
    task = next(x for x in s7.reveal_tasks() if x["id"] == "early_marker_source")
    monkeypatch.delitem(s8._ARCHIVE, "early_marker_source")
    out = s8._archive_answer(exposure["archive_frozen"], task)
    assert out["status"] == "unsupported"
    assert out["access"] == "unsupported"


@pytest.mark.parametrize("signals,expected", [
    ([1.0], "hostile"),
    ([-1.0], "benign"),
    ([1.0, -1.0], "tie"),
])
def test_signal_dominant(signals, expected):
    assert s8._signal_dominant(signals) == expected


def test_comparative_outcome_branches():
    assert s8._comparative_outcome({"full": {"correct": 3}, "compact": {"correct": 1}, "archive": {"correct": 2}}) == "structured_state_advantage_beyond_equal_budget_archive"
    assert s8._comparative_outcome({"full": {"correct": 2}, "compact": {"correct": 1}, "archive": {"correct": 3}}) == "generic_archive_outperforms_full_ghost_on_revealed_tasks"
    assert s8._comparative_outcome({"full": {"correct": 3}, "compact": {"correct": 1}, "archive": {"correct": 3}}) == "generic_archive_recovers_stage7_gap"
    assert s8._comparative_outcome({"full": {"correct": 3}, "compact": {"correct": 3}, "archive": {"correct": 3}}) == "three_way_parity_on_revealed_tasks"


def test_experiment_contract(experiment):
    assert experiment["schema"] == s8.SCHEMA
    assert experiment["strict_verdict"] == s8.VERDICT
    assert experiment["constraints"]["archive_schema_fixed_before_task_reveal"] is True
    assert experiment["constraints"]["archive_records_external_observations_verbatim"] is True
    assert experiment["constraints"]["archive_derived_state_before_reveal"] is False
    assert experiment["constraints"]["archive_padding"] is False
    assert "generic retention is sufficient" in experiment["claim_boundary"]


def test_matrix_is_deterministic(matrix):
    assert s8.run_matrix() == matrix


def test_archive_snapshot_is_json_safe():
    exposure = s8._archive_exposure(ex.canonical_levels()[1])
    json.dumps(exposure["archive_frozen"], allow_nan=False, sort_keys=True)


def test_posthoc_queries_do_not_mutate_frozen_archive():
    exposure = s8._archive_exposure(ex.canonical_levels()[2])
    before = deepcopy(exposure["archive_frozen"])
    for task in s7.reveal_tasks():
        s8._archive_answer(exposure["archive_frozen"], task)
    assert exposure["archive_frozen"] == before


def test_marker_missing_returns_none():
    exposure = s8._archive_exposure(ex.canonical_levels()[0])
    answer, scanned = s8._marker(exposure["archive_frozen"], {"token": "not_present"})
    assert answer is None
    assert scanned == exposure["archive_frozen"]["archive"]["records"].__len__()


def test_delegate_low_duty_uses_compact_relationships():
    exposure = s8._archive_exposure(ex.canonical_levels()[2])
    frozen = deepcopy(exposure["archive_frozen"])
    frozen["compact"]["flat"]["decision_state"]["values"]["duty"] = 0.0
    answer, scanned = s8._delegate(frozen, {"sources": [ex.WITNESS_A, ex.WITNESS_B], "duty_threshold": 0.8})
    assert answer in {ex.WITNESS_A, ex.WITNESS_B}
    assert scanned == 0


def test_archive_budget_overflow_fails(monkeypatch):
    exposure = ex.blind_exposure(ex.canonical_levels()[0], "baseline")
    monkeypatch.setitem(ar._BUDGETS, "within_window", 1)
    with pytest.raises(RuntimeError, match="exceeded preregistered"):
        ar.freeze_archive("within_window", exposure["frozen"], exposure["host_ledger"])


def test_level_result_rejects_exposure_mismatch(monkeypatch):
    original = s8._archive_exposure
    def broken(level):
        out = original(level)
        out["host_ledger"] = deepcopy(out["host_ledger"])
        out["host_ledger"][0]["event"] = "drift"
        return out
    monkeypatch.setattr(s8, "_archive_exposure", broken)
    with pytest.raises(RuntimeError, match="identical blind exposure"):
        s8._level_result(ex.canonical_levels()[0])


def test_matrix_rejects_task_count_drift(monkeypatch):
    calls = {"n": 0}
    def fake(item):
        calls["n"] += 1
        count = 10 if calls["n"] == 1 else 9
        block = {"correct": count, "supported": count, "unsupported": 0}
        return {
            "level": item,
            "task_count": count,
            "full": deepcopy(block),
            "compact": deepcopy(block),
            "archive": deepcopy(block),
            "state": {"archive_within_full_budget": True},
        }
    monkeypatch.setattr(s8, "_level_result", fake)
    with pytest.raises(RuntimeError, match="task count changed"):
        s8.run_matrix(ex.canonical_levels()[:2])
