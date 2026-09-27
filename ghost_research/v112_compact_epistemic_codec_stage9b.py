"""Lossless research-only compact codec and task-blind index for Stage 9B."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any

from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_latent_exposure_stage7 as ex

_OBS_FIELDS = (
    "id", "kind", "observation_kind", "observer", "provenance",
    "reliability", "sequence", "subject", "tick", "visible_features",
)
_CONSTANT_FIELDS = ("observation_kind", "observer", "reliability", "tick")


def json_bytes(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


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
    raise TypeError(f"unsupported provenance value type: {type(value).__name__}")


def _validate_observations(observations: list[dict]) -> None:
    if not observations:
        raise ValueError("observation codec requires at least one observation")
    expected = tuple(sorted(_OBS_FIELDS))
    for row in observations:
        if tuple(sorted(row)) != expected or row.get("kind") != "observation":
            raise ValueError("unexpected epistemic observation schema")
        if not all(isinstance(value, str) for value in row["visible_features"]):
            raise TypeError("visible_features must contain strings")


def _ids_derivable(observations: list[dict]) -> bool:
    return all(row["id"] == f"epistemic_{int(row['sequence']):06d}" for row in observations)


def _collect_strings(observations: list[dict], derive_ids: bool) -> list[str]:
    values: set[str] = set()
    for row in observations:
        if not derive_ids:
            values.add(row["id"])
        values.update((row["observation_kind"], row["observer"], row["subject"]))
        for key, value in row["provenance"].items():
            values.add(key)
            if isinstance(value, str):
                values.add(value)
        values.update(row["visible_features"])
    return sorted(values)


def _constant_map(observations: list[dict], string_id: dict[str, int]) -> dict[str, Any]:
    constants: dict[str, Any] = {}
    for field in _CONSTANT_FIELDS:
        first = observations[0][field]
        if all(row[field] == first for row in observations):
            constants[field] = string_id[first] if isinstance(first, str) else first
    return constants


def _provenance_signature(record: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    keys = tuple(sorted(record["provenance"]))
    types = tuple(_primitive_tag(record["provenance"][key]) for key in keys)
    return keys, types


def _schema_tables(observations: list[dict], string_id: dict[str, int]) -> tuple[list[dict], dict]:
    signatures = sorted({_provenance_signature(row) for row in observations})
    schemas = [
        {"keys": [string_id[key] for key in keys], "types": "".join(types)}
        for keys, types in signatures
    ]
    return schemas, {signature: index for index, signature in enumerate(signatures)}


def _encode_provenance(record: dict, schema_id: dict, string_id: dict[str, int]) -> list:
    keys, types = _provenance_signature(record)
    encoded = [schema_id[(keys, types)]]
    for key, tag in zip(keys, types):
        value = record["provenance"][key]
        encoded.append(string_id[value] if tag == "s" else value)
    return encoded


def _encode_row(record: dict, *, derive_ids: bool, constants: dict, schema_id: dict,
                string_id: dict[str, int]) -> list:
    row: list[Any] = []
    if not derive_ids:
        row.append(string_id[record["id"]])
    for field in ("observation_kind", "observer"):
        if field not in constants:
            row.append(string_id[record[field]])
    row.append(_encode_provenance(record, schema_id, string_id))
    if "reliability" not in constants:
        row.append(record["reliability"])
    row.extend((record["sequence"], string_id[record["subject"]]))
    if "tick" not in constants:
        row.append(record["tick"])
    row.append([string_id[value] for value in record["visible_features"]])
    return row


def observation_codec(observations: list[dict]) -> dict:
    _validate_observations(observations)
    derive_ids = _ids_derivable(observations)
    strings = _collect_strings(observations, derive_ids)
    string_id = {value: index for index, value in enumerate(strings)}
    constants = _constant_map(observations, string_id)
    schemas, schema_id = _schema_tables(observations, string_id)
    rows = [
        _encode_row(row, derive_ids=derive_ids, constants=constants,
                    schema_id=schema_id, string_id=string_id)
        for row in observations
    ]
    return {
        "schema": "ghost.stage9b.observation-columnar.v1",
        "strings": strings,
        "provenance_schemas": schemas,
        "id_from_sequence": derive_ids,
        "constants": constants,
        "rows": rows,
    }


def _read_string_field(codec: dict, row: list, cursor: int, field: str) -> tuple[str, int]:
    if field in codec["constants"]:
        return codec["strings"][codec["constants"][field]], cursor
    return codec["strings"][row[cursor]], cursor + 1


def _decode_provenance(codec: dict, encoded: list) -> dict:
    schema = codec["provenance_schemas"][encoded[0]]
    keys = [codec["strings"][index] for index in schema["keys"]]
    result = {}
    for key, value, tag in zip(keys, encoded[1:], schema["types"]):
        result[key] = codec["strings"][value] if tag == "s" else value
    return result


def decode_observation(codec: dict, row: list) -> dict:
    cursor = 0
    record_id = None
    if not codec["id_from_sequence"]:
        record_id = codec["strings"][row[cursor]]
        cursor += 1
    observation_kind, cursor = _read_string_field(codec, row, cursor, "observation_kind")
    observer, cursor = _read_string_field(codec, row, cursor, "observer")
    provenance = _decode_provenance(codec, row[cursor])
    cursor += 1
    reliability = codec["constants"].get("reliability")
    if "reliability" not in codec["constants"]:
        reliability = row[cursor]
        cursor += 1
    sequence, subject_id = row[cursor], row[cursor + 1]
    cursor += 2
    tick = codec["constants"].get("tick")
    if "tick" not in codec["constants"]:
        tick = row[cursor]
        cursor += 1
    visible = [codec["strings"][index] for index in row[cursor]]
    cursor += 1
    if cursor != len(row):
        raise ValueError("observation row has trailing data")
    return {
        "id": f"epistemic_{int(sequence):06d}" if codec["id_from_sequence"] else record_id,
        "kind": "observation", "observation_kind": observation_kind, "observer": observer,
        "provenance": provenance, "reliability": reliability, "sequence": sequence,
        "subject": codec["strings"][subject_id], "tick": tick, "visible_features": visible,
    }


def compact_snapshot(frozen: dict) -> dict:
    if not isinstance(frozen, dict) or frozen.get("mode") != "full":
        raise ValueError("compact_snapshot requires a Full-Ghost frozen state")
    compact = deepcopy(frozen)
    epistemic = compact["api"]["epistemic"]
    records = epistemic.pop("records")
    if records != sorted(records, key=lambda row: row["sequence"]):
        raise ValueError("epistemic records are not sequence ordered")
    observations = [row for row in records if row.get("kind") == "observation"]
    epistemic["records_codec"] = {
        "schema": "ghost.stage9b.epistemic-records.v1",
        "observation": observation_codec(observations),
        "other_records": [row for row in records if row.get("kind") != "observation"],
    }
    return compact


def expand_snapshot(compact: dict) -> dict:
    restored = deepcopy(compact)
    epistemic = restored["api"]["epistemic"]
    encoded = epistemic.pop("records_codec")
    if encoded.get("schema") != "ghost.stage9b.epistemic-records.v1":
        raise ValueError("unsupported compact epistemic schema")
    codec = encoded["observation"]
    observations = [decode_observation(codec, row) for row in codec["rows"]]
    records = observations + deepcopy(encoded["other_records"])
    epistemic["records"] = sorted(records, key=lambda row: row["sequence"])
    return restored


def _observation_token_positions(observation_codec: dict) -> dict[str, int]:
    result: dict[str, int] = {}
    for pos, row in enumerate(observation_codec["rows"]):
        token = decode_observation(observation_codec, row)["provenance"].get("token")
        if token is not None:
            result[token] = pos
    return result


def _belief_positions(other_records: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    latest: dict[str, int] = {}
    revisions: Counter[str] = Counter()
    for pos, row in enumerate(other_records):
        if row.get("kind") != "belief":
            continue
        key = row["holder"] + "\x1f" + row["subject"]
        latest[key] = pos
        if row.get("previous_belief_id") is not None:
            revisions[key] += 1
    return latest, dict(revisions)


class CompactGhostIndex(s9a.FrozenGhostIndex):
    """Task-blind index over compact state; inherits the frozen query contract."""

    def __init__(self, compact: dict) -> None:
        if not isinstance(compact, dict) or compact.get("mode") != "full":
            raise ValueError("CompactGhostIndex requires a compact Full-Ghost state")
        api = compact["api"]
        encoded = api["epistemic"]["records_codec"]
        self.observation_codec = encoded["observation"]
        self.other_records = encoded["other_records"]
        self.latest_observation_position_by_token = _observation_token_positions(self.observation_codec)
        self.other_record_position_by_id = {row["id"]: pos for pos, row in enumerate(self.other_records)}
        latest, revisions = _belief_positions(self.other_records)
        self.latest_belief_position_by_holder_subject = latest
        self.revision_count_by_holder_subject = revisions
        self.relationships = {s9a._pair_key(key): value for key, value in api["engine"]["relationships"].items()}
        self.agent_values = {key: value.get("values", {}) for key, value in api["agents"]["agents"].items()}

    def index_payload(self) -> dict:
        return {
            "latest_observation_position_by_token": self.latest_observation_position_by_token,
            "other_record_position_by_id": self.other_record_position_by_id,
            "latest_belief_position_by_holder_subject": self.latest_belief_position_by_holder_subject,
            "revision_count_by_holder_subject": self.revision_count_by_holder_subject,
            "relationship_keys": sorted("\x1f".join(pair) for pair in self.relationships),
            "agent_value_keys": {key: sorted(value) for key, value in sorted(self.agent_values.items())},
        }

    def _belief(self, holder: str, subject: str) -> dict | None:
        pos = self.latest_belief_position_by_holder_subject.get(holder + "\x1f" + subject)
        return None if pos is None else self.other_records[pos]

    def _evidence(self, subject: str) -> list[dict]:
        belief = self._belief(ex.AGENT, subject)
        if belief is None:
            return []
        return [self.other_records[self.other_record_position_by_id[item]] for item in belief["evidence_ids"]]

    def _marker(self, args: dict) -> Any:
        pos = self.latest_observation_position_by_token.get(args["token"])
        if pos is None:
            return None
        row = self.observation_codec["rows"][pos]
        return decode_observation(self.observation_codec, row)["provenance"].get("source")


def _string_metrics(observations: list[dict]) -> dict:
    values: list[str] = []
    for row in observations:
        values.extend((row["id"], row["observation_kind"], row["observer"], row["subject"]))
        values.extend(value for value in row["provenance"].values() if isinstance(value, str))
        values.extend(row["visible_features"])
    unique = set(values)
    return {
        "string_value_occurrences": len(values),
        "unique_string_values": len(unique),
        "string_occurrence_json_bytes": sum(json_bytes(value) for value in values),
        "unique_string_value_json_bytes": sum(json_bytes(value) for value in unique),
    }


def observation_diagnostics(observations: list[dict], codec: dict) -> dict:
    constants = sorted(codec["constants"])
    original = json_bytes(observations)
    compact = json_bytes(codec)
    result = {
        "observation_count": len(observations),
        "original_observation_list_bytes": original,
        "compact_observation_codec_bytes": compact,
        "observation_bytes_saved": original - compact,
        "top_level_key_and_colon_bytes": sum(json_bytes(key) + 1 for row in observations for key in row),
        "provenance_key_and_colon_bytes": sum(
            json_bytes(key) + 1 for row in observations for key in row["provenance"]
        ),
        "constant_top_level_fields": constants,
        "constant_field_value_occurrence_bytes": sum(
            json_bytes(row[field]) for row in observations for field in constants
        ),
        "provenance_schema_count": len(codec["provenance_schemas"]),
        "codec_string_table_entries": len(codec["strings"]),
        "id_derived_from_sequence": codec["id_from_sequence"],
        "diagnostics_are_non_additive": True,
    }
    result.update(_string_metrics(observations))
    return result
