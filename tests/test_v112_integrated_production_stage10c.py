from copy import deepcopy

import pytest

from ghost_research import v112_integrated_production_stage10c as s10c


@pytest.fixture(scope="module")
def result():
    original = s10c._LEVELS
    s10c._LEVELS = ({"id": "events_224", "ambient_events": 224},)
    try:
        return s10c.run_experiment()
    finally:
        s10c._LEVELS = original


def test_stage10c_verdict_and_aggregate_gate(result):
    assert result["strict_verdict"] == s10c.VERDICT
    assert result["all_gates_pass"] is True
    assert all(result["gates"].values())


def test_stage10c_long_run_and_restore_are_exact(result):
    for row in result["levels"]:
        live = row["long_run"]
        assert live["generation_sequence"] == [1, 2, 3, 4]
        assert live["all_step_returns_exact"] is True
        assert live["all_step_snapshots_exact"] is True
        assert live["verified_restore_exact"] is True
        assert live["continuation_return_exact"] is True
        assert live["continuation_snapshot_exact"] is True
        assert live["health_nominal"] is True


def test_stage10c_writer_contention_fails_open_and_recovers(result):
    for row in result["levels"]:
        probe = row["writer_contention"]
        assert probe["holder_ready"] is True
        assert probe["contended_snapshot_exact"] is True
        assert probe["failure_opened_circuit"] is True
        assert probe["post_death_snapshot_exact"] is True
        assert probe["post_death_write_recovered"] is True


def test_stage10c_corruption_and_version_fallback_repair(result):
    for row in result["levels"]:
        for key in ("candidate_corruption", "candidate_version"):
            probe = row[key]
            assert probe["first_exact"] is True
            assert probe["fallback_source"] == "baseline"
            assert probe["fallback_exact"] is True
            assert probe["second_exact"] is True
            assert probe["repaired_source"] == "candidate"
            assert probe["repaired_exact"] is True
            assert probe["generation"] == 2


def test_stage10c_rollback_preserves_baseline_authority(result):
    for row in result["levels"]:
        probe = row["rollback"]
        assert probe["first_exact"] is True
        assert probe["detached_disabled"] is True
        assert probe["candidate_removed"] is True
        assert probe["manifest_removed"] is True
        assert probe["baseline_preserved"] is True
        assert probe["baseline_source"] == "baseline"
        assert probe["baseline_exact"] is True
        assert probe["post_detach_exact"] is True
        assert probe["hook_removed"] is True


def test_stage10c_actual_process_exit_boundaries_recover_exactly(result):
    for row in result["levels"]:
        assert [case["atomic_call"] for case in row["crash_matrix"]] == [1, 2, 3]
        assert [case["source"] for case in row["crash_matrix"]] == [
            "baseline", "baseline", "candidate"
        ]
        for case in row["crash_matrix"]:
            assert case["returncode"] == s10c.CRASH_EXIT_CODE
            assert case["expected_exit"] is True
            assert case["source_exact"] is True
            assert case["generation"] == 2
            assert case["state_exact"] is True
            assert case["initial_generation"] == 1


def test_stage10c_cost_attribution_is_complete_and_nonzero(result):
    for row in result["levels"]:
        cost = row["cost"]
        assert cost["samples"] == s10c._TIMING_SAMPLES
        for key, value in cost.items():
            if key != "samples":
                assert value > 0


def test_stage10c_constraints_keep_candidate_private_non_authoritative(result):
    constraints = result["constraints"]
    assert constraints["production_files_modified_by_stage10c"] is False
    for key, value in constraints.items():
        if key != "production_files_modified_by_stage10c":
            assert value is True


def test_stage10c_gate_reducer_detects_a_false_level(result):
    rows = deepcopy(result["levels"])
    rows[0]["long_run"]["all_step_returns_exact"] = False
    gates = s10c._gates(rows)
    assert gates["long_run_return_parity"] is False
    assert all(value for key, value in gates.items() if key != "long_run_return_parity")
