"""v1.12-dev Stage-9A cost attribution and research-only indexed-view probe.

Stage 9 established equal correctness while Full Ghost used fewer logical record
reads but more wall-clock time and storage than the generic archive.  Stage 9A
attributes that cost without changing production Ghost.  A task-blind index is
built only from the already-frozen Ghost snapshot and is used as a diagnostic,
not as a production recommendation.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any, Callable

from ghost_research import v112_equal_budget_adjudication_stage8 as s8
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_resource_cost_stage9 as s9

SCHEMA = "ghost.v1.12-dev.cost-attribution.stage9a.v1"
VERDICT = "V112_COST_ATTRIBUTION_STAGE9A_EXPERIMENT_VALID"
_TIMING_SAMPLES = 7
_QUERY_REPETITIONS = 100
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
)


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


def _pair_key(raw: str) -> tuple[str, str]:
    parts = raw.split("|", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("invalid relationship snapshot key")
    return parts[0], parts[1]


class FrozenGhostIndex:
    """Generic indexes over one frozen snapshot; construction receives no tasks."""

    def __init__(self, frozen: dict) -> None:
        if not isinstance(frozen, dict) or frozen.get("mode") != "full":
            raise ValueError("FrozenGhostIndex requires a Full-Ghost frozen state")
        api = frozen["api"]
        self.records = api["epistemic"]["records"]
        self.record_position_by_id: dict[str, int] = {}
        self.latest_observation_position_by_token: dict[str, int] = {}
        self.latest_belief_position_by_holder_subject: dict[str, int] = {}
        revisions: Counter[str] = Counter()
        for pos, row in enumerate(self.records):
            self.record_position_by_id[row["id"]] = pos
            kind = row.get("kind")
            if kind == "observation":
                token = row.get("provenance", {}).get("token")
                if token is not None:
                    self.latest_observation_position_by_token[token] = pos
            elif kind == "belief":
                key = row["holder"] + "\x1f" + row["subject"]
                self.latest_belief_position_by_holder_subject[key] = pos
                if row.get("previous_belief_id") is not None:
                    revisions[key] += 1
        self.revision_count_by_holder_subject = dict(revisions)
        self.relationships = {
            _pair_key(key): value for key, value in api["engine"]["relationships"].items()
        }
        self.agent_values = {
            agent_id: state.get("values", {}) for agent_id, state in api["agents"]["agents"].items()
        }

    def index_payload(self) -> dict:
        return {
            "record_position_by_id": self.record_position_by_id,
            "latest_observation_position_by_token": self.latest_observation_position_by_token,
            "latest_belief_position_by_holder_subject": self.latest_belief_position_by_holder_subject,
            "revision_count_by_holder_subject": self.revision_count_by_holder_subject,
            "relationship_keys": sorted("\x1f".join(pair) for pair in self.relationships),
            "agent_value_keys": {key: sorted(value) for key, value in sorted(self.agent_values.items())},
        }

    def _belief(self, holder: str, subject: str) -> dict | None:
        pos = self.latest_belief_position_by_holder_subject.get(holder + "\x1f" + subject)
        return None if pos is None else self.records[pos]

    def _relationship(self, agent: str, source: str) -> dict:
        value = self.relationships.get((agent, source))
        if value is None:
            value = self.relationships.get((source, agent))
        if value is None:
            raise KeyError((agent, source))
        return value

    def _relationship_count(self, source: str) -> int:
        return int(round(float(self._relationship(ex.AGENT, source)["maturity"]) / 0.01))

    def _evidence(self, subject: str) -> list[dict]:
        belief = self._belief(ex.AGENT, subject)
        if belief is None:
            return []
        return [self.records[self.record_position_by_id[item]] for item in belief["evidence_ids"]]

    def _marker(self, args: dict) -> Any:
        pos = self.latest_observation_position_by_token.get(args["token"])
        return None if pos is None else self.records[pos].get("provenance", {}).get("source")

    def _trust(self, args: dict) -> Any:
        return s7._trust_sign(float(self._relationship(ex.AGENT, args["source"])["trust"]))

    def _belief_answer(self, args: dict) -> Any:
        belief = self._belief(ex.AGENT, args["subject"])
        return None if belief is None else belief["dimensions"]["threat"]["dominant_candidate"]

    def _sources(self, args: dict) -> Any:
        return sorted({row["source"] for row in self._evidence(args["subject"])})

    def _revisions(self, args: dict) -> Any:
        return self.revision_count_by_holder_subject.get(ex.AGENT + "\x1f" + args["subject"], 0)

    def _counterfactual(self, args: dict) -> Any:
        signals = [
            float(row["provenance"]["signal"])
            for row in self._evidence(args["subject"])
            if row["source"] != args["excluded_source"]
        ]
        return s7._signal_dominant(signals)

    def _deeper(self, args: dict) -> Any:
        sources = list(args["sources"])
        return sorted(sources, key=lambda source: (-self._relationship_count(source), source))[0]

    def _delegate(self, args: dict) -> Any:
        sources = list(args["sources"])
        duty = float(self.agent_values.get(ex.AGENT, {}).get("duty", 0.0))
        if duty >= float(args["duty_threshold"]):
            return sorted(sources, key=lambda source: (-self._relationship_count(source), source))[0]
        return sorted(
            sources,
            key=lambda source: (-float(self._relationship(ex.AGENT, source)["trust"]), source),
        )[0]

    def answer(self, task: dict) -> Any:
        spec = s7._validated_task(task)
        handlers: dict[str, Callable[[dict], Any]] = {
            "recent_marker_source": self._marker,
            "early_marker_source": self._marker,
            "current_trust_sign": self._trust,
            "current_belief_dominant": self._belief_answer,
            "relationship_event_count": lambda args: self._relationship_count(args["source"]),
            "evidence_sources": self._sources,
            "belief_revision_count": self._revisions,
            "counterfactual_without_source": self._counterfactual,
            "deeper_relationship": self._deeper,
            "novel_delegate_choice": self._delegate,
        }
        handler = handlers.get(spec["kind"])
        if handler is None:
            raise RuntimeError(f"unhandled Stage-9A task kind: {spec['kind']!r}")
        return handler(spec["args"])


def _storage_attribution(frozen: dict) -> dict:
    api = frozen["api"]
    records = api["epistemic"]["records"]
    kinds = Counter(row.get("kind", "<missing>") for row in records)
    kind_bytes = {
        kind: sum(_json_bytes(row) for row in records if row.get("kind", "<missing>") == kind)
        for kind in sorted(kinds)
    }
    components = {key: _json_bytes(value) for key, value in api.items()}
    return {
        "full_snapshot_bytes": _json_bytes(frozen),
        "api_component_value_bytes": components,
        "epistemic_record_counts": dict(sorted(kinds.items())),
        "epistemic_record_value_bytes": kind_bytes,
        "epistemic_fraction_of_snapshot": components["epistemic"] / _json_bytes(frozen),
    }


def _indexed_work(index: FrozenGhostIndex, tasks: list[dict]) -> dict:
    evidence_reads = 0
    relationship_reads = 0
    for task in tasks:
        kind = task["kind"]
        if kind in {"evidence_sources", "counterfactual_without_source"}:
            belief = index._belief(ex.AGENT, task["args"]["subject"])
            evidence_reads += 1 + (0 if belief is None else len(belief["evidence_ids"]))
        if kind in {"current_trust_sign", "relationship_event_count"}:
            relationship_reads += 1
        elif kind in {"deeper_relationship", "novel_delegate_choice"}:
            relationship_reads += len(task["args"]["sources"])
    direct = 2 + 1 + 1 + 1
    return {
        "indexed_record_reads_per_battery": direct + evidence_reads,
        "indexed_relationship_reads_per_battery": relationship_reads,
        "index_entry_count": (
            len(index.record_position_by_id)
            + len(index.latest_observation_position_by_token)
            + len(index.latest_belief_position_by_holder_subject)
            + len(index.revision_count_by_holder_subject)
            + len(index.relationships)
        ),
        "index_payload_bytes": _json_bytes(index.index_payload()),
    }


def _battery_indexed(reader: FrozenGhostIndex, tasks: list[dict], repetitions: int = 1) -> None:
    for _ in range(repetitions):
        for task in tasks:
            reader.answer(task)


def _task_timing(reader: Any, tasks: list[dict], samples: int) -> dict[str, float]:
    return {task["id"]: s9._median_us(lambda task=task: reader.answer(task), samples) for task in tasks}


def _correctness_rows(full: dict, archive: dict, current: Any, indexed: Any, tasks: list[dict]) -> list[dict]:
    rows = []
    for task in tasks:
        expected = s7._ground_truth(full["host_ledger"], task)
        archive_answer = s8._archive_answer(archive["archive_frozen"], task)["answer"]
        current_answer = current.answer(task)
        indexed_answer = indexed.answer(task)
        rows.append({
            "task": task["id"], "expected": expected, "current": current_answer,
            "indexed": indexed_answer, "archive": archive_answer,
            "all_correct": current_answer == indexed_answer == archive_answer == expected,
        })
    return rows


def _timing_profile(full: dict, archive: dict, current: Any, indexed: Any, tasks: list[dict], samples: int) -> dict:
    return {
        "samples": samples,
        "index_build_us": s9._median_us(lambda: FrozenGhostIndex(full["frozen"]), samples),
        "current_battery_us": s9._median_us(lambda: s9._query_battery_warm(current, tasks), samples),
        "indexed_battery_us": s9._median_us(lambda: _battery_indexed(indexed, tasks), samples),
        "archive_battery_us": s9._median_us(lambda: s9._query_battery_archive(archive["archive_frozen"], tasks), samples),
        "current_100_batteries_us": s9._median_us(lambda: s9._query_battery_warm(current, tasks, _QUERY_REPETITIONS), samples),
        "indexed_100_batteries_us": s9._median_us(lambda: _battery_indexed(indexed, tasks, _QUERY_REPETITIONS), samples),
        "archive_100_batteries_us": s9._median_us(lambda: s9._query_battery_archive(archive["archive_frozen"], tasks, _QUERY_REPETITIONS), samples),
        "current_task_us": _task_timing(current, tasks, samples),
        "indexed_task_us": _task_timing(indexed, tasks, samples),
    }


def _profile_level(level: dict, *, timing: bool, samples: int) -> dict:
    full = ex.blind_exposure(level, "full")
    archive = s9._archive_exposure(level)
    if full["host_ledger"] != archive["host_ledger"]:
        raise RuntimeError("Stage-9A contenders did not receive identical exposure")
    tasks = s7.reveal_tasks()
    current = s9.WarmGhostReader(full["frozen"])
    indexed = FrozenGhostIndex(full["frozen"])
    rows = _correctness_rows(full, archive, current, indexed, tasks)
    work = {
        "current": s9._ghost_work(full["frozen"], tasks),
        "indexed": _indexed_work(indexed, tasks),
        "archive_records_examined_per_battery": s9._correctness(full, archive, tasks)["archive_records_examined_per_battery"],
    }
    result = {
        "level": deepcopy(level),
        "correctness": {"all_correct": all(row["all_correct"] for row in rows), "rows": rows},
        "storage": _storage_attribution(full["frozen"]),
        "archive_snapshot_bytes": archive["snapshot_bytes"],
        "work": work,
        "timing": None,
    }
    if timing:
        result["timing"] = _timing_profile(full, archive, current, indexed, tasks, samples)
    return result


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    levels = [_profile_level(deepcopy(level), timing=timing, samples=timing_samples) for level in _LEVELS]
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "all_three_correct": all(row["correctness"]["all_correct"] for row in levels),
        "constraints": {
            "stage9_behavioral_question_frozen": True,
            "production_ghost_modified": False,
            "index_built_without_tasks": True,
            "index_is_research_only": True,
            "timing_is_telemetry_not_gate": True,
            "no_weighted_composite_score": True,
        },
        "claim_boundary": (
            "Stage 9A attributes current frozen-state cost and tests whether a generic research-only index over existing snapshot fields can reduce read work while preserving the exact Stage-7 answers. "
            "It does not establish a production optimization, a universal performance winner, or permission to change Ghost semantics."
        ),
    }
