from copy import deepcopy
import json

import pytest

from ghost_research.v112_relationship_compact_stage1g import (
    SCHEMA,
    decode_relationships,
    encode_relationships,
    install_relationships_in_place,
)


def _records():
    return {
        "a|b": {"trust": 0.25, "state": "neutral", "gain": 0.1, "extra": 7},
        "c|d": {"trust": -0.5, "state": "hostile", "gain": 0.1},
    }


def test_empty_roundtrip_is_exact_and_json_safe():
    compact = encode_relationships({})
    assert compact == {
        "schema": SCHEMA,
        "fields": [],
        "shared": {},
        "varying": [],
        "rows": [],
        "record_count": 0,
    }
    assert decode_relationships(compact) == {}
    json.dumps(compact, allow_nan=False)


def test_multi_record_roundtrip_extracts_shared_values():
    records = _records()
    compact = encode_relationships(records)
    assert compact["shared"] == {"gain": 0.1}
    assert compact["varying"] == ["extra", "state", "trust"]
    assert decode_relationships(compact) == records


def test_encoding_is_deterministic_for_same_order_and_preserves_pair_order():
    records = _records()
    first = encode_relationships(records)
    second = encode_relationships(deepcopy(records))
    assert first == second
    assert [row[0] for row in first["rows"]] == list(records)
    assert list(decode_relationships(first)) == list(records)

    reversed_records = dict(reversed(list(records.items())))
    reversed_compact = encode_relationships(reversed_records)
    assert [row[0] for row in reversed_compact["rows"]] == list(reversed_records)
    assert list(decode_relationships(reversed_compact)) == list(reversed_records)


def test_encode_and_decode_are_deep_copy_isolated():
    records = _records()
    frozen = deepcopy(records)
    compact = encode_relationships(records)
    records["a|b"]["trust"] = 999
    assert decode_relationships(compact) == frozen

    decoded = decode_relationships(compact)
    decoded["a|b"]["trust"] = -999
    assert decode_relationships(compact) == frozen


def test_in_place_restore_preserves_container_identity_and_copy_isolation():
    target = {"old": {"trust": 1}}
    target_id = id(target)
    records = _records()

    returned = install_relationships_in_place(target, records)

    assert returned is target
    assert id(target) == target_id
    assert target == records

    records["a|b"]["trust"] = 999
    assert target["a|b"]["trust"] == 0.25


@pytest.mark.parametrize("target, records", [([], {}), ({}, [])])
def test_in_place_restore_rejects_non_dict_inputs(target, records):
    with pytest.raises(TypeError, match="restore target"):
        install_relationships_in_place(target, records)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"a|b": 1},
        {1: {}},
    ],
)
def test_encode_rejects_invalid_record_containers(bad):
    with pytest.raises(TypeError):
        encode_relationships(bad)


def test_encode_rejects_non_string_record_field_names():
    with pytest.raises(TypeError, match="field names"):
        encode_relationships({"a|b": {1: "bad"}})


def _compact():
    return encode_relationships(_records())


def test_decode_rejects_non_dict_and_wrong_top_level_keys():
    with pytest.raises(TypeError):
        decode_relationships([])
    bad = _compact()
    bad["extra"] = True
    with pytest.raises(ValueError, match="keys"):
        decode_relationships(bad)


def test_decode_rejects_schema_drift():
    bad = _compact()
    bad["schema"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        decode_relationships(bad)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("fields", "bad", TypeError),
        ("fields", ["trust", 1], TypeError),
        ("shared", [], TypeError),
        ("varying", "bad", TypeError),
        ("rows", {}, TypeError),
        ("record_count", -1, TypeError),
    ],
)
def test_decode_rejects_container_shape_errors(field, value, error):
    bad = _compact()
    bad[field] = value
    with pytest.raises(error):
        decode_relationships(bad)


def test_decode_rejects_unsorted_or_duplicate_fields():
    bad = _compact()
    bad["fields"] = list(reversed(bad["fields"]))
    with pytest.raises(ValueError, match="fields"):
        decode_relationships(bad)

    bad = _compact()
    bad["varying"] = bad["varying"] + [bad["varying"][0]]
    with pytest.raises(ValueError, match="varying"):
        decode_relationships(bad)


def test_decode_rejects_shared_varying_overlap_and_incomplete_cover():
    bad = _compact()
    bad["shared"][bad["varying"][0]] = 1
    with pytest.raises(ValueError, match="overlap"):
        decode_relationships(bad)

    bad = _compact()
    bad["varying"] = bad["varying"][:-1]
    with pytest.raises(ValueError, match="cover"):
        decode_relationships(bad)


def test_decode_rejects_record_count_drift():
    bad = _compact()
    bad["record_count"] += 1
    with pytest.raises(ValueError, match="record_count"):
        decode_relationships(bad)

    bad = _compact()
    bad["record_count"] = True
    with pytest.raises(TypeError, match="record_count"):
        decode_relationships(bad)


@pytest.mark.parametrize(
    "row",
    [
        ["a|b", 1],
        "bad",
    ],
)
def test_decode_rejects_bad_row_shape(row):
    bad = _compact()
    bad["rows"][0] = row
    with pytest.raises(ValueError, match="row"):
        decode_relationships(bad)


def test_decode_rejects_duplicate_or_non_string_pair_ids():
    bad = _compact()
    bad["rows"][1][0] = bad["rows"][0][0]
    with pytest.raises(ValueError, match="pair"):
        decode_relationships(bad)

    bad = _compact()
    bad["rows"][0][0] = 1
    with pytest.raises(ValueError, match="pair"):
        decode_relationships(bad)


def test_decode_rejects_invalid_presence_masks():
    bad = _compact()
    bad["rows"][0][1] = -1
    with pytest.raises(ValueError, match="mask"):
        decode_relationships(bad)

    bad = _compact()
    bad["rows"][0][1] = True
    with pytest.raises(ValueError, match="mask"):
        decode_relationships(bad)

    bad = _compact()
    bad["rows"][0][1] = 1 << len(bad["varying"])
    with pytest.raises(ValueError, match="mask"):
        decode_relationships(bad)


def test_decode_rejects_non_list_row_values():
    bad = _compact()
    bad["rows"][0][2] = {}
    with pytest.raises(TypeError, match="values"):
        decode_relationships(bad)


def test_decode_rejects_missing_or_extra_encoded_values():
    bad = _compact()
    bad["rows"][0][2] = []
    with pytest.raises(ValueError, match="missing"):
        decode_relationships(bad)

    bad = _compact()
    bad["rows"][0][2].append("extra")
    with pytest.raises(ValueError, match="extra"):
        decode_relationships(bad)
