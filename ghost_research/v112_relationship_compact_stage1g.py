from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA = "ghocentric.cmi.relationship-compact.stage1g.v1"


def encode_relationships(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(records, dict):
        raise TypeError("relationship records must be a dict")
    for pair, record in records.items():
        if not isinstance(pair, str) or not isinstance(record, dict):
            raise TypeError("relationship records must map string pair ids to dicts")
        if not all(isinstance(field, str) for field in record):
            raise TypeError("relationship record field names must be strings")

    fields = sorted({field for record in records.values() for field in record})
    shared: dict[str, Any] = {}
    varying: list[str] = []

    for field in fields:
        present = [field in record for record in records.values()]
        if records and all(present):
            first = next(iter(records.values()))[field]
            if all(record[field] == first for record in records.values()):
                shared[field] = deepcopy(first)
                continue
        varying.append(field)

    rows: list[list[Any]] = []
    for pair, record in records.items():
        mask = 0
        values: list[Any] = []
        for index, field in enumerate(varying):
            if field in record:
                mask |= 1 << index
                values.append(deepcopy(record[field]))
        rows.append([pair, mask, values])

    return {
        "schema": SCHEMA,
        "fields": fields,
        "shared": shared,
        "varying": varying,
        "rows": rows,
        "record_count": len(records),
    }


def install_relationships_in_place(
    target: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(target, dict) or not isinstance(records, dict):
        raise TypeError("relationship restore target and records must be dicts")
    replacement = deepcopy(records)
    target.clear()
    target.update(replacement)
    return target


def decode_relationships(compact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(compact, dict):
        raise TypeError("compact relationship state must be a dict")
    required = {"schema", "fields", "shared", "varying", "rows", "record_count"}
    if set(compact) != required:
        raise ValueError("compact relationship state keys are invalid")
    if compact["schema"] != SCHEMA:
        raise ValueError("compact relationship schema is unsupported")

    fields = compact["fields"]
    shared = compact["shared"]
    varying = compact["varying"]
    rows = compact["rows"]
    record_count = compact["record_count"]

    if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
        raise TypeError("compact fields must be a list of strings")
    if fields != sorted(set(fields)):
        raise ValueError("compact fields must be unique and sorted")
    if not isinstance(shared, dict) or not isinstance(varying, list):
        raise TypeError("compact shared/varying containers are invalid")
    if not all(isinstance(x, str) for x in varying) or varying != sorted(set(varying)):
        raise ValueError("compact varying fields must be unique and sorted")
    if set(shared) & set(varying):
        raise ValueError("shared and varying fields overlap")
    if set(shared) | set(varying) != set(fields):
        raise ValueError("shared/varying fields do not cover the field set")
    if not isinstance(rows, list) or type(record_count) is not int or record_count < 0:
        raise TypeError("compact rows/record_count are invalid")
    if record_count != len(rows):
        raise ValueError("compact record_count does not match rows")

    decoded: dict[str, dict[str, Any]] = {}
    valid_mask = (1 << len(varying)) - 1
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("compact row must be [pair, mask, values]")
        pair, mask, values = row
        if not isinstance(pair, str) or pair in decoded:
            raise ValueError("compact pair id is invalid or duplicated")
        if type(mask) is not int or mask < 0 or mask & ~valid_mask:
            raise ValueError("compact presence mask is invalid")
        if not isinstance(values, list):
            raise TypeError("compact row values must be a list")

        record = deepcopy(shared)
        value_index = 0
        for index, field in enumerate(varying):
            if mask & (1 << index):
                if value_index >= len(values):
                    raise ValueError("compact row is missing encoded values")
                record[field] = deepcopy(values[value_index])
                value_index += 1
        if value_index != len(values):
            raise ValueError("compact row contains extra encoded values")
        decoded[pair] = record

    return decoded
