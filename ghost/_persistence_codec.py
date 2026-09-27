"""Internal lossless compact snapshot codec for the guarded persistence candidate."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

OBSERVATION_CODEC_SCHEMA = "ghost.persistence.observation-codec.v1"
RECORDS_CODEC_SCHEMA = "ghost.persistence.epistemic-records.v1"
LEGACY_OBSERVATION_CODEC_SCHEMA = "ghost.stage9c.incremental-observation.v1"
LEGACY_RECORDS_CODEC_SCHEMA = "ghost.stage9c.incremental-epistemic-records.v1"

_OBSERVATION_FIELDS = {
    "id", "kind", "observation_kind", "observer", "provenance",
    "reliability", "sequence", "subject", "tick", "visible_features",
}


def _primitive_tag(value: Any) -> str:
    if isinstance(value, bool):
        return "b"
    if value is None:
        return "n"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "f"
    if isinstance(value, str):
        return "s"
    raise TypeError("unsupported provenance value type: " + type(value).__name__)


def _positive_sequence(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(label + " must be a positive integer")
    return value


def _record_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(label + " must be a non-empty string")
    return value


def _string_at(strings: List[str], index: Any, label: str) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(strings):
        raise ValueError(label + " references an invalid string")
    return strings[index]


def _schema_signature(strings: List[str], schema: Any) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    if not isinstance(schema, dict) or set(schema) != {"keys", "types"}:
        raise ValueError("observation provenance schema has invalid shape")
    keys = schema["keys"]
    types = schema["types"]
    if not isinstance(keys, list) or not isinstance(types, str) or len(keys) != len(types):
        raise ValueError("observation provenance schema is invalid")
    decoded = tuple(_string_at(strings, item, "provenance schema") for item in keys)
    if any(tag not in "bnifs" for tag in types):
        raise ValueError("observation provenance type tag is invalid")
    return decoded, tuple(types)


def _validate_snapshot_tables(snapshot: dict) -> Tuple[List[str], List[dict], List[list]]:
    allowed = {OBSERVATION_CODEC_SCHEMA, LEGACY_OBSERVATION_CODEC_SCHEMA}
    if snapshot.get("schema") not in allowed:
        raise ValueError("observation codec schema mismatch")
    if set(snapshot) != {"schema", "strings", "provenance_schemas", "rows"}:
        raise ValueError("observation codec snapshot has invalid shape")
    strings = snapshot["strings"]
    schemas = snapshot["provenance_schemas"]
    rows = snapshot["rows"]
    if not isinstance(strings, list) or any(not isinstance(value, str) for value in strings):
        raise ValueError("observation codec strings must be a string list")
    if len(set(strings)) != len(strings):
        raise ValueError("observation codec strings must be unique")
    if not isinstance(schemas, list) or not isinstance(rows, list):
        raise ValueError("observation codec tables must be lists")
    return strings, schemas, rows


class ObservationCodec:
    """Canonical observation table used only by persistence shadow mode."""

    def __init__(self, snapshot: Optional[dict] = None) -> None:
        self.strings: List[str] = []
        self._string_id: Dict[str, int] = {}
        self.schemas: List[dict] = []
        self._schema_id: Dict[Tuple[Tuple[str, ...], Tuple[str, ...]], int] = {}
        self.rows: List[list] = []
        if snapshot is not None:
            self._restore(snapshot)

    def _restore(self, snapshot: dict) -> None:
        if not isinstance(snapshot, dict):
            raise ValueError("observation codec snapshot must be a dict")
        strings, schemas, rows = _validate_snapshot_tables(snapshot)
        self.strings = deepcopy(strings)
        self._string_id = {value: index for index, value in enumerate(self.strings)}
        self.schemas = deepcopy(schemas)
        self.rows = deepcopy(rows)
        for index, schema in enumerate(self.schemas):
            signature = _schema_signature(self.strings, schema)
            if signature in self._schema_id:
                raise ValueError("duplicate observation provenance schema")
            self._schema_id[signature] = index
        for position in range(len(self.rows)):
            self.decode(position)

    def _sid(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("observation codec string value must be a string")
        found = self._string_id.get(value)
        if found is not None:
            return found
        found = len(self.strings)
        self.strings.append(value)
        self._string_id[value] = found
        return found

    def _schema(self, provenance: dict) -> Tuple[int, Tuple[str, ...], Tuple[str, ...]]:
        if not isinstance(provenance, dict):
            raise TypeError("observation provenance must be a dict")
        if any(not isinstance(key, str) for key in provenance):
            raise TypeError("observation provenance keys must be strings")
        keys = tuple(sorted(provenance))
        types = tuple(_primitive_tag(provenance[key]) for key in keys)
        signature = (keys, types)
        found = self._schema_id.get(signature)
        if found is None:
            found = len(self.schemas)
            self.schemas.append({"keys": [self._sid(key) for key in keys], "types": "".join(types)})
            self._schema_id[signature] = found
        return found, keys, types

    @staticmethod
    def _validate_record(record: Any) -> None:
        if not isinstance(record, dict) or set(record) != _OBSERVATION_FIELDS:
            raise ValueError("unexpected observation record schema")
        if record.get("kind") != "observation":
            raise ValueError("observation record kind mismatch")
        visible = record["visible_features"]
        if not isinstance(visible, list) or any(not isinstance(item, str) for item in visible):
            raise TypeError("visible_features must contain strings")
        _positive_sequence(record["sequence"], "observation sequence")
        _record_id(record["id"], "observation id")

    def append(self, record: dict) -> None:
        self._validate_record(record)
        schema_id, keys, types = self._schema(record["provenance"])
        provenance = [schema_id]
        for key, tag in zip(keys, types):
            value = record["provenance"][key]
            provenance.append(self._sid(value) if tag == "s" else value)
        sequence = record["sequence"]
        derived = record["id"] == "epistemic_%06d" % sequence
        self.rows.append([
            None if derived else self._sid(record["id"]),
            self._sid(record["observation_kind"]), self._sid(record["observer"]), provenance,
            record["reliability"], sequence, self._sid(record["subject"]), record["tick"],
            [self._sid(item) for item in record["visible_features"]],
        ])

    def _decode_provenance(self, row: list) -> dict:
        schema_index = row[3][0]
        if isinstance(schema_index, bool) or not isinstance(schema_index, int) or not (0 <= schema_index < len(self.schemas)):
            raise ValueError("observation row references invalid codec data")
        schema = self.schemas[schema_index]
        keys, types = _schema_signature(self.strings, schema)
        values = row[3][1:]
        if len(values) != len(keys):
            raise ValueError("observation provenance row has invalid width")
        provenance = {}
        for key, value, tag in zip(keys, values, types):
            decoded = _string_at(self.strings, value, "observation provenance") if tag == "s" else value
            if _primitive_tag(decoded) != tag:
                raise ValueError("observation provenance value does not match type tag")
            provenance[key] = decoded
        return provenance

    def decode(self, position: int) -> dict:
        try:
            row = self.rows[position]
        except (IndexError, TypeError) as exc:
            raise ValueError("observation row references invalid codec data") from exc
        if not isinstance(row, list) or len(row) != 9 or not isinstance(row[3], list) or not row[3]:
            raise ValueError("observation row has invalid shape")
        sequence = _positive_sequence(row[5], "observation row sequence")
        record_id = "epistemic_%06d" % sequence if row[0] is None else _string_at(self.strings, row[0], "observation id")
        visible = row[8]
        if not isinstance(visible, list):
            raise ValueError("observation visible feature row must be a list")
        return {
            "id": record_id,
            "kind": "observation",
            "observation_kind": _string_at(self.strings, row[1], "observation kind"),
            "observer": _string_at(self.strings, row[2], "observation observer"),
            "provenance": self._decode_provenance(row),
            "reliability": row[4],
            "sequence": sequence,
            "subject": _string_at(self.strings, row[6], "observation subject"),
            "tick": row[7],
            "visible_features": [_string_at(self.strings, item, "visible feature") for item in visible],
        }

    def snapshot(self) -> dict:
        return {
            "schema": OBSERVATION_CODEC_SCHEMA,
            "strings": deepcopy(self.strings),
            "provenance_schemas": deepcopy(self.schemas),
            "rows": deepcopy(self.rows),
        }


def _epistemic_records(snapshot: dict, *, compact: bool) -> Tuple[dict, Any]:
    try:
        epistemic = snapshot["api"]["epistemic"]
        key = "records_codec" if compact else "records"
        value = epistemic[key]
    except (KeyError, TypeError) as exc:
        label = "records_codec" if compact else "api.epistemic.records"
        raise ValueError("snapshot does not contain " + label) from exc
    return epistemic, value


def _ordered_identity(record: Any, seen_ids: set, last_sequence: int) -> Tuple[str, int]:
    if not isinstance(record, dict):
        raise ValueError("epistemic record must be a dict")
    record_id = _record_id(record.get("id"), "epistemic record id")
    if record_id in seen_ids:
        raise ValueError("epistemic record ids must be unique non-empty strings")
    sequence = _positive_sequence(record.get("sequence"), "epistemic record sequence")
    if sequence <= last_sequence:
        raise ValueError("epistemic records must be in increasing sequence order")
    return record_id, sequence


def compact_snapshot(full_snapshot: dict) -> dict:
    """Losslessly replace epistemic records with the candidate v1 codec."""
    if not isinstance(full_snapshot, dict):
        raise TypeError("full snapshot must be a dict")
    _, records = _epistemic_records(full_snapshot, compact=False)
    if not isinstance(records, list):
        raise ValueError("epistemic records must be a list")
    codec = ObservationCodec()
    other_records = []
    seen_ids = set()
    last_sequence = 0
    for record in records:
        record_id, sequence = _ordered_identity(record, seen_ids, last_sequence)
        seen_ids.add(record_id)
        last_sequence = sequence
        if record.get("kind") == "observation":
            codec.append(record)
        else:
            other_records.append(deepcopy(record))
    result = deepcopy(full_snapshot)
    epistemic = result["api"]["epistemic"]
    epistemic.pop("records")
    epistemic["records_codec"] = {
        "schema": RECORDS_CODEC_SCHEMA,
        "observation": codec.snapshot(),
        "other_records": other_records,
    }
    return result


def _decode_records(encoded: Any) -> List[dict]:
    if not isinstance(encoded, dict) or set(encoded) != {"schema", "observation", "other_records"}:
        raise ValueError("compact epistemic records codec has invalid shape")
    if encoded["schema"] not in {RECORDS_CODEC_SCHEMA, LEGACY_RECORDS_CODEC_SCHEMA}:
        raise ValueError("compact epistemic records schema mismatch")
    other_records = encoded["other_records"]
    if not isinstance(other_records, list) or any(not isinstance(row, dict) for row in other_records):
        raise ValueError("compact non-observation records must be a dict list")
    observation = ObservationCodec(encoded["observation"])
    records = [observation.decode(position) for position in range(len(observation.rows))]
    records.extend(deepcopy(other_records))
    try:
        records.sort(key=lambda row: row["sequence"])
    except (KeyError, TypeError) as exc:
        raise ValueError("compact record sequence is invalid") from exc
    return records


def _validate_expanded_order(records: List[dict]) -> None:
    seen_ids = set()
    last_sequence = 0
    for row in records:
        record_id, sequence = _ordered_identity(row, seen_ids, last_sequence)
        seen_ids.add(record_id)
        last_sequence = sequence


def expand_snapshot(compact: dict) -> dict:
    """Expand candidate v1 or the frozen Stage-9C legacy representation."""
    if not isinstance(compact, dict):
        raise TypeError("compact snapshot must be a dict")
    result = deepcopy(compact)
    epistemic, encoded = _epistemic_records(result, compact=True)
    epistemic.pop("records_codec")
    records = _decode_records(encoded)
    _validate_expanded_order(records)
    epistemic["records"] = records
    return result
