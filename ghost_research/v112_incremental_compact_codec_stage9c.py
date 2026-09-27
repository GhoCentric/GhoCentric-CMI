"""Incremental compact epistemic codec + task-blind index for Stage 9C."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from time import perf_counter_ns
from typing import Any

from ghost_research import v112_compact_epistemic_codec_stage9b as s9bcodec
from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_latent_exposure_stage7 as ex

SCHEMA = "ghost.v1.12-dev.incremental-compact.stage9c.v1"
CODEC_SCHEMA = "ghost.stage9c.incremental-observation.v1"
SNAPSHOT_SCHEMA = "ghost.stage9c.incremental-epistemic-records.v1"

json_bytes = s9bcodec.json_bytes
_primitive_tag = s9bcodec._primitive_tag


class IncrementalObservationCodec:
    """Append-only canonical observation codec with stable insertion-order IDs."""

    def __init__(self, snapshot: dict | None = None) -> None:
        if snapshot is None:
            self.strings: list[str] = []
            self._string_id: dict[str, int] = {}
            self.schemas: list[dict] = []
            self._schema_id: dict[tuple[tuple[str, ...], tuple[str, ...]], int] = {}
            self.rows: list[list] = []
            return
        if snapshot.get("schema") != CODEC_SCHEMA:
            raise ValueError("incremental observation codec schema mismatch")
        self.strings = deepcopy(snapshot["strings"])
        self._string_id = {value: index for index, value in enumerate(self.strings)}
        self.schemas = deepcopy(snapshot["provenance_schemas"])
        self._schema_id = {}
        for index, schema in enumerate(self.schemas):
            keys = tuple(self.strings[item] for item in schema["keys"])
            self._schema_id[(keys, tuple(schema["types"]))] = index
        self.rows = deepcopy(snapshot["rows"])

    def _sid(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("incremental codec string value must be a string")
        found = self._string_id.get(value)
        if found is not None:
            return found
        found = len(self.strings)
        self.strings.append(value)
        self._string_id[value] = found
        return found

    def _schema(self, provenance: dict) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
        keys = tuple(sorted(provenance))
        types = tuple(_primitive_tag(provenance[key]) for key in keys)
        signature = (keys, types)
        found = self._schema_id.get(signature)
        if found is None:
            found = len(self.schemas)
            self.schemas.append({"keys": [self._sid(key) for key in keys], "types": "".join(types)})
            self._schema_id[signature] = found
        return found, keys, types

    def append(self, record: dict) -> int:
        required = {
            "id", "kind", "observation_kind", "observer", "provenance", "reliability",
            "sequence", "subject", "tick", "visible_features",
        }
        if set(record) != required or record.get("kind") != "observation":
            raise ValueError("unexpected incremental observation schema")
        if not all(isinstance(item, str) for item in record["visible_features"]):
            raise TypeError("visible_features must contain strings")
        schema_id, keys, types = self._schema(record["provenance"])
        provenance = [schema_id]
        for key, tag in zip(keys, types):
            value = record["provenance"][key]
            provenance.append(self._sid(value) if tag == "s" else value)
        derived_id = record["id"] == f"epistemic_{int(record['sequence']):06d}"
        self.rows.append([
            None if derived_id else self._sid(record["id"]),
            self._sid(record["observation_kind"]), self._sid(record["observer"]), provenance,
            record["reliability"], record["sequence"], self._sid(record["subject"]), record["tick"],
            [self._sid(item) for item in record["visible_features"]],
        ])
        return len(self.rows) - 1

    def decode(self, position: int) -> dict:
        row = self.rows[position]
        schema = self.schemas[row[3][0]]
        keys = [self.strings[item] for item in schema["keys"]]
        provenance = {}
        for key, value, tag in zip(keys, row[3][1:], schema["types"]):
            provenance[key] = self.strings[value] if tag == "s" else value
        sequence = row[5]
        return {
            "id": f"epistemic_{int(sequence):06d}" if row[0] is None else self.strings[row[0]],
            "kind": "observation", "observation_kind": self.strings[row[1]],
            "observer": self.strings[row[2]], "provenance": provenance,
            "reliability": row[4], "sequence": sequence, "subject": self.strings[row[6]],
            "tick": row[7], "visible_features": [self.strings[item] for item in row[8]],
        }

    def snapshot(self) -> dict:
        return {
            "schema": CODEC_SCHEMA, "strings": deepcopy(self.strings),
            "provenance_schemas": deepcopy(self.schemas), "rows": deepcopy(self.rows),
        }


class IncrementalCompactSidecar(s9a.FrozenGhostIndex):
    """Incrementally maintained compact epistemic store + task-blind indexes."""

    def __init__(self, snapshot: dict | None = None) -> None:
        if snapshot is None:
            self.observations = IncrementalObservationCodec()
            self.other_records: list[dict] = []
            self.other_record_position_by_id: dict[str, int] = {}
            self.latest_observation_position_by_token: dict[str, int] = {}
            self.latest_belief_position_by_holder_subject: dict[str, int] = {}
            self.revision_count_by_holder_subject: dict[str, int] = {}
            self.relationships: dict[tuple[str, str], dict] = {}
            self.agent_values: dict[str, dict] = {}
            self._seen_ids: set[str] = set()
            self._last_sequence = 0
            self.records_ingested = 0
            return
        if snapshot.get("schema") != SCHEMA:
            raise ValueError("incremental sidecar schema mismatch")
        self.observations = IncrementalObservationCodec(snapshot["observation_codec"])
        self.other_records = deepcopy(snapshot["other_records"])
        self.relationships = {
            tuple(key.split("\x1f", 1)): deepcopy(value) for key, value in snapshot["relationships"].items()
        }
        self.agent_values = deepcopy(snapshot["agent_values"])
        self._rebuild_indexes()
        self._last_sequence = int(snapshot["last_sequence"])
        self.records_ingested = int(snapshot["records_ingested"])

    def _rebuild_indexes(self) -> None:
        self._seen_ids = set()
        self.other_record_position_by_id = {}
        self.latest_observation_position_by_token = {}
        self.latest_belief_position_by_holder_subject = {}
        revisions: Counter[str] = Counter()
        for pos in range(len(self.observations.rows)):
            row = self.observations.decode(pos)
            self._seen_ids.add(row["id"])
            token = row.get("provenance", {}).get("token")
            if token is not None:
                self.latest_observation_position_by_token[token] = pos
        for pos, row in enumerate(self.other_records):
            self._seen_ids.add(row["id"])
            self.other_record_position_by_id[row["id"]] = pos
            if row.get("kind") == "belief":
                key = row["holder"] + "\x1f" + row["subject"]
                self.latest_belief_position_by_holder_subject[key] = pos
                if row.get("previous_belief_id") is not None:
                    revisions[key] += 1
        self.revision_count_by_holder_subject = dict(revisions)

    def _record_identity(self, record: dict) -> tuple[str, int]:
        record_id = record.get("id")
        sequence = record.get("sequence")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("epistemic record id missing")
        if record_id in self._seen_ids:
            raise ValueError("duplicate epistemic record id")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= self._last_sequence:
            raise ValueError("epistemic records must arrive in increasing sequence order")
        return record_id, sequence

    def _ingest_observation(self, record: dict) -> None:
        pos = self.observations.append(record)
        token = record.get("provenance", {}).get("token")
        if token is not None:
            self.latest_observation_position_by_token[token] = pos

    def _ingest_other(self, record_id: str, record: dict) -> None:
        pos = len(self.other_records)
        self.other_records.append(deepcopy(record))
        self.other_record_position_by_id[record_id] = pos
        if record.get("kind") != "belief":
            return
        key = record["holder"] + "\x1f" + record["subject"]
        self.latest_belief_position_by_holder_subject[key] = pos
        if record.get("previous_belief_id") is not None:
            self.revision_count_by_holder_subject[key] = self.revision_count_by_holder_subject.get(key, 0) + 1

    def ingest_record(self, record: dict) -> None:
        record_id, sequence = self._record_identity(record)
        self._seen_ids.add(record_id)
        self._last_sequence = sequence
        self.records_ingested += 1
        if record.get("kind") == "observation":
            self._ingest_observation(record)
            return
        self._ingest_other(record_id, record)

    def update_relationship(self, agent: str, source: str, value: dict) -> None:
        self.relationships[(agent, source)] = deepcopy(value)

    def set_agent_values(self, agent: str, values: dict) -> None:
        self.agent_values[agent] = deepcopy(values)

    def snapshot(self) -> dict:
        return {
            "schema": SCHEMA, "observation_codec": self.observations.snapshot(),
            "other_records": deepcopy(self.other_records),
            "relationships": {"\x1f".join(key): deepcopy(value) for key, value in sorted(self.relationships.items())},
            "agent_values": deepcopy(self.agent_values), "last_sequence": self._last_sequence,
            "records_ingested": self.records_ingested,
        }

    def compact_epistemic(self, full_epistemic: dict) -> dict:
        result = deepcopy(full_epistemic)
        result.pop("records")
        result["records_codec"] = {
            "schema": SNAPSHOT_SCHEMA, "observation": self.observations.snapshot(),
            "other_records": deepcopy(self.other_records),
        }
        return result

    def compact_full_snapshot(self, frozen: dict) -> dict:
        result = deepcopy(frozen)
        result["api"]["epistemic"] = self.compact_epistemic(frozen["api"]["epistemic"])
        return result

    @staticmethod
    def expand_full_snapshot(compact: dict) -> dict:
        result = deepcopy(compact)
        epistemic = result["api"]["epistemic"]
        encoded = epistemic.pop("records_codec")
        if encoded.get("schema") != SNAPSHOT_SCHEMA:
            raise ValueError("incremental compact snapshot schema mismatch")
        obs = IncrementalObservationCodec(encoded["observation"])
        records = [obs.decode(pos) for pos in range(len(obs.rows))] + deepcopy(encoded["other_records"])
        epistemic["records"] = sorted(records, key=lambda row: row["sequence"])
        return result

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
        return None if pos is None else self.observations.decode(pos)["provenance"].get("source")
