from __future__ import annotations

from copy import deepcopy
import math
import pytest

from ghost.actions import ActionRuntime


def affordance(agent="npc", sequence=1, candidates=None):
    if candidates is None:
        candidates = [
            {"id": "confront", "capability": "talk", "features": {}},
            {"id": "leave", "capability": "move", "features": {"distance": 2}},
        ]
    return {"sequence": sequence, "agent": agent, "candidates": candidates, "context": {}}


def test_choose_is_deterministic_and_ties_break_by_candidate_id():
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"leave": 0.5, "confront": 0.5}, policy_id="baseline", context={"x": 1})
    assert d["candidate_id"] == "confront"
    assert d["capability"] == "talk"
    assert d["scores"] == {"confront": 0.5, "leave": 0.5}
    assert d["policy_id"] == "baseline"
    assert d["context"] == {"x": 1}
    assert r.pending("npc") == d
    assert r.agent_ids() == ["npc"]
    assert r.has_state() is True
    assert r.current("npc") == {"pending": d, "last_result": None}


def test_resolve_records_host_result_and_clears_pending():
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"confront": 1, "leave": -1})
    out = {"witnessed": True, "detail": ["guard", 2]}
    result = r.resolve("npc", d["decision_id"], " SUCCEEDED ", outcome=out)
    assert result["status"] == "succeeded"
    assert result["outcome"] == {"detail": ["guard", 2], "witnessed": True}
    assert r.pending("npc") is None
    assert r.history("npc") == [result]
    assert r.current("npc") == {"pending": None, "last_result": result}
    out["witnessed"] = False
    assert r.history("npc")[0]["outcome"]["witnessed"] is True


def test_history_limit_and_limit_reads():
    r = ActionRuntime(history_limit=2)
    for i in range(3):
        d = r.choose("npc", affordance(sequence=i + 1), {"confront": i, "leave": -1})
        r.resolve("npc", d["decision_id"], "failed")
    assert len(r.history("npc")) == 2
    assert len(r.history("npc", limit=1)) == 1
    assert r.history("npc", limit=0) == []
    assert r.history("missing") == []
    assert r.current("missing") is None


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "2"])
def test_bad_history_limit_rejected(bad):
    with pytest.raises(ValueError):
        ActionRuntime(bad)


@pytest.mark.parametrize("bad", [True, -1, 1.2, "1"])
def test_bad_history_read_limit_rejected(bad):
    with pytest.raises(ValueError):
        ActionRuntime().history("npc", limit=bad)


def test_double_choose_wrong_resolve_and_missing_resolve_rejected():
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    with pytest.raises(ValueError, match="unresolved"):
        r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    with pytest.raises(ValueError, match="does not match"):
        r.resolve("npc", "action_decision_999", "failed")
    r.resolve("npc", d["decision_id"], "cancelled")
    with pytest.raises(ValueError, match="no unresolved"):
        r.resolve("npc", d["decision_id"], "failed")


@pytest.mark.parametrize("status", ["succeeded", "failed", "interrupted", "cancelled"])
def test_all_final_statuses(status):
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    assert r.resolve("npc", d["decision_id"], status)["status"] == status


@pytest.mark.parametrize("bad", [None, 1, "pending", "unknown"])
def test_bad_final_status_rejected_without_consuming_pending(bad):
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    with pytest.raises(ValueError):
        r.resolve("npc", d["decision_id"], bad)
    assert r.pending("npc") == d


@pytest.mark.parametrize("scores", [None, [], {"confront": 1}, {"confront": 1, "leave": 0, "extra": 2}])
def test_score_table_shape_rejected(scores):
    r = ActionRuntime()
    with pytest.raises(ValueError):
        r.choose("npc", affordance(), scores)


@pytest.mark.parametrize("bad", [True, float("inf"), float("nan"), "1"])
def test_non_finite_or_non_numeric_score_rejected(bad):
    with pytest.raises(ValueError):
        ActionRuntime().choose("npc", affordance(), {"confront": bad, "leave": 0})


def test_duplicate_normalized_score_id_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ActionRuntime().choose("npc", affordance(), {"confront": 1, " confront ": 0, "leave": 0})


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        {"sequence": 1, "agent": "npc", "candidates": [], "context": {}, "extra": 1},
    ],
)
def test_bad_affordance_record_rejected(record):
    with pytest.raises(ValueError):
        ActionRuntime().choose("npc", record, {})


def test_affordance_agent_empty_and_candidate_validation():
    r = ActionRuntime()
    with pytest.raises(ValueError, match="different agent"):
        r.choose("npc", affordance(agent="other"), {"confront": 1, "leave": 0})
    with pytest.raises(ValueError, match="empty"):
        r.choose("npc", affordance(candidates=[]), {})
    bad = affordance(candidates="no")
    with pytest.raises(ValueError, match="must be a list"):
        r.choose("npc", bad, {})
    bad = affordance(candidates=[{"id": "x", "capability": "talk"}])
    with pytest.raises(ValueError, match="invalid keys"):
        r.choose("npc", bad, {"x": 1})
    bad = affordance(candidates=[
        {"id": "x", "capability": "talk", "features": {}},
        {"id": " x ", "capability": "move", "features": {}},
    ])
    with pytest.raises(ValueError, match="duplicate"):
        r.choose("npc", bad, {"x": 1})


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_affordance_sequence_must_be_positive_int(bad):
    with pytest.raises(ValueError):
        ActionRuntime().choose("npc", affordance(sequence=bad), {"confront": 1, "leave": 0})


def test_metadata_and_policy_validation_and_mutation_resistance():
    r = ActionRuntime()
    context = {"b": [1, {"x": True}], "a": 2.5}
    d = r.choose("npc", affordance(), {"confront": 2, "leave": 1}, context=context)
    context["b"][1]["x"] = False
    assert d["context"]["b"][1]["x"] is True
    with pytest.raises(ValueError):
        ActionRuntime().choose("npc", affordance(), {"confront": 1, "leave": 0}, policy_id=" ")
    for bad_context in ([], {1: "x"}, {"": 1}, {"x": float("inf")}, {"x": object()}):
        with pytest.raises(ValueError):
            ActionRuntime().choose("other", affordance(agent="other"), {"confront": 1, "leave": 0}, context=bad_context)


def test_outcome_validation():
    r = ActionRuntime()
    for bad in ([], {1: "x"}, {"": 1}, {"x": math.nan}, {"x": object()}):
        d = r.choose("npc", affordance(), {"confront": 1, "leave": 0})
        with pytest.raises(ValueError):
            r.resolve("npc", d["decision_id"], "failed", outcome=bad)
        assert r.pending("npc") == d
        r.resolve("npc", d["decision_id"], "failed")


def build_snapshot_with_history_and_pending():
    r = ActionRuntime(history_limit=3)
    d1 = r.choose("a", affordance(agent="a", sequence=1), {"confront": 1, "leave": 0}, policy_id="p")
    r.resolve("a", d1["decision_id"], "failed", outcome={"why": "blocked"})
    d2 = r.choose("b", affordance(agent="b", sequence=2), {"confront": 0, "leave": 1}, policy_id="p")
    return r, d2


def test_snapshot_roundtrip_and_deepcopy():
    r, pending = build_snapshot_with_history_and_pending()
    snap = r.snapshot()
    restored = ActionRuntime.from_snapshot(snap)
    assert restored.snapshot() == snap
    assert restored.pending("b") == pending
    snap["agents"]["a"]["history"][0]["outcome"]["why"] = "mutated"
    assert restored.history("a")[0]["outcome"]["why"] == "blocked"


@pytest.mark.parametrize("bad", [None, [], "x"])
def test_snapshot_type_rejected(bad):
    with pytest.raises(ValueError):
        ActionRuntime.from_snapshot(bad)


def test_snapshot_top_level_shape_and_schema_validation():
    base = ActionRuntime().snapshot()
    bad = deepcopy(base); bad["extra"] = 1
    with pytest.raises(ValueError, match="unsupported keys"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(base); del bad["agents"]
    with pytest.raises(ValueError, match="missing required"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(base); bad["schema_version"] = "9"
    with pytest.raises(ValueError, match="unsupported action snapshot"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(base); bad["agents"] = []
    with pytest.raises(ValueError, match="agents must be a dict"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(base); bad["sequence"] = 1
    with pytest.raises(ValueError, match="empty action snapshot"):
        ActionRuntime.from_snapshot(bad)


def test_snapshot_agent_state_validation():
    base, _ = build_snapshot_with_history_and_pending(); snap = base.snapshot()
    bad = deepcopy(snap); bad["agents"][" a "] = bad["agents"].pop("a")
    # normalized key itself is fine when unique
    assert ActionRuntime.from_snapshot(bad).agent_ids() == ["a", "b"]
    bad = deepcopy(snap); bad["agents"][" a "] = deepcopy(bad["agents"]["a"])
    with pytest.raises(ValueError, match="duplicate normalized agent"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(snap); bad["agents"]["a"] = []
    with pytest.raises(ValueError, match="invalid keys"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(snap); bad["agents"]["a"]["history"] = "x"
    with pytest.raises(ValueError, match="must be a list"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(snap); bad["history_limit"] = 0
    with pytest.raises(ValueError):
        ActionRuntime.from_snapshot(bad)
    bad = {"schema_version":"1.0","history_limit":1,"sequence":0,"agents":{"a":{"pending":None,"history":[]}}}
    with pytest.raises(ValueError, match="must not be empty"):
        ActionRuntime.from_snapshot(bad)


def test_snapshot_history_limit_and_order_validation():
    r = ActionRuntime(history_limit=2)
    for i in range(2):
        d = r.choose("a", affordance(agent="a", sequence=i+1), {"confront": 1, "leave": 0})
        r.resolve("a", d["decision_id"], "failed")
    snap = r.snapshot()
    bad = deepcopy(snap); bad["history_limit"] = 1
    with pytest.raises(ValueError, match="exceeds history_limit"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(snap); bad["agents"]["a"]["history"].reverse()
    with pytest.raises(ValueError, match="must be ordered"):
        ActionRuntime.from_snapshot(bad)


def test_snapshot_decision_and_result_validation_branches():
    r, _ = build_snapshot_with_history_and_pending(); snap = r.snapshot()
    cases = []
    def case(edit):
        bad=deepcopy(snap); edit(bad); cases.append(bad)
    case(lambda x: x["agents"]["b"].__setitem__("pending", []))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("sequence", x["sequence"]+1))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("decision_id", "wrong"))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("agent", "other"))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("affordance_sequence", 0))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("score", float("inf")))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("scores", {}))
    case(lambda x: x["agents"]["b"]["pending"]["scores"].__setitem__("leave", -2))
    case(lambda x: x["agents"]["b"]["pending"].__setitem__("candidate_id", "confront"))
    case(lambda x: x["agents"]["a"]["history"][0].__setitem__("resolution_sequence", x["sequence"]+1))
    case(lambda x: x["agents"]["a"]["history"][0].__setitem__("resolution_sequence", 1))
    case(lambda x: x["agents"]["a"]["history"][0].__setitem__("status", "pending"))
    for bad in cases:
        with pytest.raises(ValueError):
            ActionRuntime.from_snapshot(bad)


def test_snapshot_duplicate_global_sequence_and_max_sequence_validation():
    r, _ = build_snapshot_with_history_and_pending(); snap = r.snapshot()
    bad = deepcopy(snap)
    bad["agents"]["b"]["pending"]["sequence"] = bad["agents"]["a"]["history"][0]["decision"]["sequence"]
    bad["agents"]["b"]["pending"]["decision_id"] = "action_decision_1"
    with pytest.raises(ValueError, match="duplicate global sequence"):
        ActionRuntime.from_snapshot(bad)
    bad = deepcopy(snap); bad["sequence"] += 1
    with pytest.raises(ValueError, match="latest action event sequence"):
        ActionRuntime.from_snapshot(bad)

def test_snapshot_negative_sequence_rejected():
    snap = ActionRuntime().snapshot()
    snap["sequence"] = -1
    with pytest.raises(ValueError):
        ActionRuntime.from_snapshot(snap)


def test_metadata_duplicate_normalized_key_rejected():
    with pytest.raises(ValueError, match="duplicate normalized key"):
        ActionRuntime().choose(
            "npc",
            affordance(),
            {"confront": 1, "leave": 0},
            context={"x": 1, " x ": 2},
        )


def test_snapshot_duplicate_normalized_score_key_rejected():
    r = ActionRuntime()
    r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    snap = r.snapshot()
    pending = snap["agents"]["npc"]["pending"]
    pending["scores"][" confront "] = pending["scores"]["confront"]
    with pytest.raises(ValueError, match="duplicate normalized candidate"):
        ActionRuntime.from_snapshot(snap)


def test_snapshot_rejects_choice_that_is_not_highest_ranked():
    r = ActionRuntime()
    r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    snap = r.snapshot()
    pending = snap["agents"]["npc"]["pending"]
    pending["scores"]["leave"] = 2.0
    with pytest.raises(ValueError, match="deterministic ranking"):
        ActionRuntime.from_snapshot(snap)


def test_snapshot_rejects_invalid_history_result_keys():
    r = ActionRuntime()
    d = r.choose("npc", affordance(), {"confront": 1, "leave": 0})
    r.resolve("npc", d["decision_id"], "failed")
    snap = r.snapshot()
    snap["agents"]["npc"]["history"][0]["extra"] = 1
    with pytest.raises(ValueError, match="invalid keys"):
        ActionRuntime.from_snapshot(snap)


def test_snapshot_rejects_duplicate_global_sequence_across_history_agents():
    r = ActionRuntime()
    da = r.choose("a", affordance(agent="a", sequence=1), {"confront": 1, "leave": 0})
    r.resolve("a", da["decision_id"], "failed")
    db = r.choose("b", affordance(agent="b", sequence=2), {"confront": 1, "leave": 0})
    r.resolve("b", db["decision_id"], "failed")
    snap = r.snapshot()
    # Make b's decision/reply reuse a's 1/2 while remaining internally valid.
    bres = snap["agents"]["b"]["history"][0]
    bres["decision"]["sequence"] = 1
    bres["decision"]["decision_id"] = "action_decision_1"
    bres["resolution_sequence"] = 2
    with pytest.raises(ValueError, match="duplicate global sequence"):
        ActionRuntime.from_snapshot(snap)
