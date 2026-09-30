from copy import deepcopy

from ghost_research.v112_epistemic_state_ownership_stage1l import (
    LIVE_FIELDS,
    PERSISTED_FIELDS,
    authoritative_projection,
    ownership_summary,
    rebuild_indexes,
)


def _records():
    return [
        {
            "id": "epistemic_000001",
            "kind": "fact",
            "sequence": 1,
            "tick": 0,
            "fact_id": "f",
            "source": "world",
            "subject": "door",
            "predicate": "state",
            "object": "closed",
            "attributes": {},
        },
        {
            "id": "epistemic_000002",
            "kind": "belief",
            "sequence": 2,
            "tick": 0,
            "holder": "guard",
            "subject": "visitor",
        },
        {
            "id": "epistemic_000003",
            "kind": "fact",
            "sequence": 3,
            "tick": 1,
            "fact_id": "f",
            "source": "world",
            "subject": "door",
            "predicate": "state",
            "object": "open",
            "attributes": {},
        },
        {
            "id": "epistemic_000004",
            "kind": "belief",
            "sequence": 4,
            "tick": 1,
            "holder": "guard",
            "subject": "visitor",
        },
        {
            "id": "epistemic_000005",
            "kind": "observation",
            "sequence": 5,
            "tick": 1,
        },
    ]


def test_field_contract_constants():
    assert LIVE_FIELDS == (
        "_tick",
        "_sequence",
        "_records",
        "_by_id",
        "_facts",
        "_beliefs",
        "_latest",
    )
    assert PERSISTED_FIELDS == ("tick", "sequence", "records")


def test_authoritative_projection_is_exact_and_isolated():
    snapshot = {
        "schema_version": "1.0",
        "tick": 1,
        "sequence": 5,
        "records": _records(),
    }
    frozen = deepcopy(snapshot)
    projected = authoritative_projection(snapshot)
    assert projected == snapshot
    projected["records"][0]["fact_id"] = "tampered"
    assert snapshot == frozen


def test_rebuild_indexes_empty():
    assert rebuild_indexes([]) == {
        "by_id": {},
        "facts": {},
        "beliefs": {},
        "latest": {},
    }


def test_rebuild_indexes_exact():
    rows = _records()
    indexes = rebuild_indexes(rows)
    assert set(indexes["by_id"]) == {row["id"] for row in rows}
    assert indexes["facts"]["f"]["object"] == "open"
    assert set(indexes["beliefs"]) == {
        "epistemic_000002",
        "epistemic_000004",
    }
    assert indexes["latest"][("guard", "visitor")] == "epistemic_000004"


def test_rebuild_indexes_is_input_isolated():
    rows = _records()
    frozen = deepcopy(rows)
    indexes = rebuild_indexes(rows)
    indexes["by_id"]["epistemic_000001"]["fact_id"] = "changed"
    indexes["facts"]["f"]["object"] = "changed"
    assert rows == frozen


def test_ownership_summary():
    snapshot = {
        "schema_version": "1.0",
        "tick": 1,
        "sequence": 5,
        "records": _records(),
    }
    assert ownership_summary(snapshot) == {
        "persisted_runtime_fields": ["tick", "sequence", "records"],
        "derived_index_names": ["by_id", "facts", "beliefs", "latest"],
        "record_count": 5,
        "fact_index_count": 1,
        "belief_index_count": 2,
        "latest_belief_count": 1,
    }
