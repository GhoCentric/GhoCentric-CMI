"""Research-only Stage-9D compact restart-and-continue adjudication."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from time import perf_counter_ns
from typing import Any

from ghost_research import v112_cost_attribution_stage9a as s9a
from ghost_research import v112_incremental_compact_codec_stage9c as inc
from ghost_research import v112_incremental_compact_stage9c as s9c
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.restart-continue.stage9d.v1"
ENVELOPE_SCHEMA = "ghost.stage9d.compact-restart-envelope.v1"
VERDICT = "V112_RESTART_CONTINUE_STAGE9D_EXPERIMENT_VALID"
_LEVELS = (
    {"id": "events_224", "ambient_events": 224},
    {"id": "events_1024", "ambient_events": 1024},
    {"id": "events_2048", "ambient_events": 2048},
    {"id": "events_4096", "ambient_events": 4096},
)
_TIMING_SAMPLES = 5


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _payload_digest(compact: dict) -> str:
    return hashlib.sha256(_canonical_bytes(compact)).hexdigest()


def make_envelope(compact: dict) -> dict:
    if not isinstance(compact, dict):
        raise TypeError("compact restart payload must be a dict")
    payload = deepcopy(compact)
    return {"schema": ENVELOPE_SCHEMA, "payload_sha256": _payload_digest(payload), "compact": payload}


def encode_envelope(compact: dict) -> bytes:
    return _canonical_bytes(make_envelope(compact))


def _validate_digest_text(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("compact restart digest must be 64 hex characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("compact restart digest must be 64 hex characters") from exc
    return value.lower()


def decode_envelope(blob: bytes | bytearray) -> dict:
    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("compact restart envelope must be bytes")
    try:
        packet = json.loads(bytes(blob).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("compact restart envelope is not valid canonical JSON") from exc
    if not isinstance(packet, dict) or set(packet) != {"schema", "payload_sha256", "compact"}:
        raise ValueError("compact restart envelope has invalid shape")
    if packet["schema"] != ENVELOPE_SCHEMA:
        raise ValueError("compact restart envelope schema mismatch")
    expected = _validate_digest_text(packet["payload_sha256"])
    compact = packet["compact"]
    if not isinstance(compact, dict):
        raise ValueError("compact restart envelope payload must be a dict")
    if _payload_digest(compact) != expected:
        raise ValueError("compact restart envelope integrity mismatch")
    return deepcopy(compact)


def _restore_contender(frozen: dict, template: s6.StructuralContender) -> s6.StructuralContender:
    from ghost.api import GhostAPI

    if not isinstance(frozen, dict) or frozen.get("mode") != "full" or not isinstance(frozen.get("api"), dict):
        raise ValueError("expanded compact restart snapshot must be Full-Ghost state")
    restored = s6.StructuralContender.__new__(s6.StructuralContender)
    restored.mode = "full"
    restored.agent_ids = list(template.agent_ids)
    restored.source_ids = list(template.source_ids)
    restored.subject_ids = list(template.subject_ids)
    restored.api = GhostAPI.from_snapshot(deepcopy(frozen["api"]))
    restored.agents = {logical: restored.api.agent(logical) for logical in restored.agent_ids}
    if any(agent is None for agent in restored.agents.values()):
        raise RuntimeError("compact restart lost a registered structural agent")
    restored.flat = {}
    restored.relationships = {}
    return restored


def restore_runtime(blob: bytes, template: s6.StructuralContender) -> tuple[s6.StructuralContender, inc.IncrementalCompactSidecar, dict]:
    compact = decode_envelope(blob)
    full = inc.IncrementalCompactSidecar.expand_full_snapshot(compact)
    contender = _restore_contender(full, template)
    sidecar = s9c.LiveExposureAnswer.sidecar({"compact": compact})
    if sidecar.records_ingested != len(contender.api.epistemic._records):
        raise RuntimeError("compact restart sidecar/runtime record count mismatch")
    if sidecar.compact_full_snapshot(ex._freeze(contender)) != compact:
        raise RuntimeError("compact restart reconstruction drifted from persisted packet")
    return contender, sidecar, compact


class FullRestartExposure(s9c.LiveExposure):
    """Runs one branch through compact full restarts against an uninterrupted shadow."""

    def __init__(self, raw_level: dict) -> None:
        super().__init__(raw_level)
        self.shadow = s6.StructuralContender("full", 3)
        self.shadow_ledger: list[dict] = []
        self.step_fingerprint_checks = 0
        self.restart_parity_checks = 0
        self.full_restart_ns: list[int] = []
        self.restart_packet_bytes: list[int] = []
        if ex._freeze(self.contender) != ex._freeze(self.shadow):
            raise RuntimeError("restart experiment initial branches are not identical")

    def _run(self, fn, *args, relationship_source: str | None = None, **kwargs) -> None:
        super()._run(fn, *args, relationship_source=relationship_source, **kwargs)
        fn(self.shadow, self.shadow_ledger, self.level["id"], *args, **kwargs)
        if self.ledger[-1] != self.shadow_ledger[-1]:
            raise RuntimeError("restart continuation host ledger drifted")
        if self.contender._fingerprint() != self.shadow._fingerprint():
            raise RuntimeError("restart continuation decision-relevant state drifted")
        self.step_fingerprint_checks += 1

    def restart_sidecar(self) -> None:
        before = ex._freeze(self.contender)
        if before != ex._freeze(self.shadow):
            raise RuntimeError("restart boundary reached with pre-existing branch drift")
        compact = self.sidecar.compact_full_snapshot(before)
        blob = encode_envelope(compact)
        start = perf_counter_ns()
        contender, sidecar, restored_compact = restore_runtime(blob, self.contender)
        elapsed = perf_counter_ns() - start
        self.contender = contender
        self.sidecar = sidecar
        self._cursor = len(self.contender.api.epistemic._records)
        if restored_compact != compact or ex._freeze(self.contender) != before:
            raise RuntimeError("compact full restart changed exact Ghost state")
        if ex._freeze(self.contender) != ex._freeze(self.shadow):
            raise RuntimeError("compact full restart diverged from uninterrupted shadow")
        self.restart_parity_checks += 1
        self.full_restart_ns.append(elapsed)
        self.restart_packet_bytes.append(len(blob))

    def run(self, *, restart_points: set[int] | None = None) -> dict:
        result = super().run(restart_points=restart_points)
        shadow_frozen = ex._freeze(self.shadow)
        if result["host_ledger"] != self.shadow_ledger or result["frozen"] != shadow_frozen:
            raise RuntimeError("restart continuation final state drifted from uninterrupted shadow")
        result["restart_diagnostics"] = {
            "step_fingerprint_checks": self.step_fingerprint_checks,
            "restart_parity_checks": self.restart_parity_checks,
            "restart_packet_bytes": list(self.restart_packet_bytes),
            "full_restart_us": [value / 1000.0 for value in self.full_restart_ns],
        }
        return result


def _restart_points(ambient_events: int) -> set[int]:
    return {ambient_events // 4, ambient_events // 2, (3 * ambient_events) // 4}


def _answers(live: dict, sidecar: inc.IncrementalCompactSidecar) -> list[dict]:
    return [
        {
            "task": task["id"],
            "expected": s7._ground_truth(live["host_ledger"], task),
            "actual": sidecar.answer(task),
        }
        for task in s7.reveal_tasks()
    ]


def _corruption_probes(compact: dict) -> dict[str, bytes]:
    clean = make_envelope(compact)
    wrong_schema = deepcopy(clean)
    wrong_schema["schema"] = "wrong"
    stale_digest = deepcopy(clean)
    stale_digest["compact"]["api"]["epistemic"]["sequence"] += 1
    bad_digest = deepcopy(clean)
    bad_digest["payload_sha256"] = "g" * 64
    codec_corrupt = deepcopy(compact)
    codec_corrupt["api"]["epistemic"]["records_codec"]["schema"] = "wrong"
    ghost_schema_corrupt = deepcopy(compact)
    ghost_schema_corrupt["api"]["schema_version"] = "wrong"
    return {
        "wrong_envelope_schema": _canonical_bytes(wrong_schema),
        "stale_payload_digest": _canonical_bytes(stale_digest),
        "invalid_digest_encoding": _canonical_bytes(bad_digest),
        "truncated_json": encode_envelope(compact)[:-1],
        "rehashed_codec_schema": encode_envelope(codec_corrupt),
        "rehashed_ghost_schema": encode_envelope(ghost_schema_corrupt),
    }


def _corruption_battery(compact: dict, template: s6.StructuralContender) -> dict[str, bool]:
    results = {}
    for name, blob in _corruption_probes(compact).items():
        try:
            restore_runtime(blob, template)
        except (TypeError, ValueError):
            results[name] = True
        else:
            results[name] = False
    return results


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _profile_result(live: dict, restarts: set[int], *, timing: bool, samples: int) -> dict:
    sidecar = s9c.LiveExposureAnswer.sidecar(live)
    answers = _answers(live, sidecar)
    diag = live["restart_diagnostics"]
    result = {
        "level": deepcopy(live["level"]),
        "all_correct": all(row["actual"] == row["expected"] for row in answers),
        "exact_stage7_reference": True,
        "exact_final_roundtrip": True,
        "answers": answers,
        "restart": {
            "requested_points": sorted(restarts), "full_restarts": len(diag["full_restart_us"]),
            "restart_parity_checks": diag["restart_parity_checks"],
            "step_fingerprint_checks": diag["step_fingerprint_checks"],
            "packet_bytes": diag["restart_packet_bytes"],
        },
        "storage": {
            "current_snapshot_bytes": inc.json_bytes(live["frozen"]),
            "compact_snapshot_bytes": inc.json_bytes(live["compact"]),
            "final_restart_envelope_bytes": len(encode_envelope(live["compact"])),
        },
        "timing": None,
    }
    if timing:
        restart_us = diag["full_restart_us"]
        result["timing"] = {
            "samples": samples, "observed_restart_median_us": _median(restart_us),
            "observed_restart_max_us": max(restart_us),
            "post_restart_query_battery_us": s9c._median_us(lambda: s9a._battery_indexed(sidecar, s7.reveal_tasks()), samples),
        }
    return result


def _profile_level(level: dict, *, timing: bool, samples: int) -> dict:
    restarts = _restart_points(level["ambient_events"])
    live = FullRestartExposure(level).run(restart_points=restarts)
    reference = ex.blind_exposure(level, "full")
    if live["host_ledger"] != reference["host_ledger"] or live["frozen"] != reference["frozen"]:
        raise RuntimeError("Stage-9D restart branch drifted from exact frozen Stage-7 reference")
    if inc.IncrementalCompactSidecar.expand_full_snapshot(live["compact"]) != live["frozen"]:
        raise RuntimeError("Stage-9D final compact snapshot failed exact reconstruction")
    return _profile_result(live, restarts, timing=timing, samples=samples)


def run_experiment(*, timing: bool = True, timing_samples: int = _TIMING_SAMPLES) -> dict:
    if isinstance(timing_samples, bool) or not isinstance(timing_samples, int) or timing_samples < 1:
        raise ValueError("timing_samples must be a positive integer")
    levels = [_profile_level(deepcopy(level), timing=timing, samples=timing_samples) for level in _LEVELS]
    probe_runner = FullRestartExposure(_LEVELS[0])
    probe_live = probe_runner.run(restart_points={_LEVELS[0]["ambient_events"] // 2})
    corruption = _corruption_battery(probe_live["compact"], probe_runner.contender)
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "levels": levels,
        "all_correct": all(row["all_correct"] for row in levels),
        "all_exact_stage7_references": all(row["exact_stage7_reference"] for row in levels),
        "all_exact_final_roundtrips": all(row["exact_final_roundtrip"] for row in levels),
        "corruption_rejection": corruption,
        "all_guarded_corruptions_rejected": all(corruption.values()),
        "constraints": {
            "production_ghost_modified": False,
            "research_only": True,
            "compact_packet_is_only_ghost_restart_payload": True,
            "full_ghost_restart_and_continue_tested": True,
            "uninterrupted_shadow_compared": True,
            "checksum_is_integrity_not_authentication": True,
            "record_deletion_not_supported_by_current_public_epistemic_contract": True,
            "timing_is_telemetry_not_gate": True,
            "no_weighted_composite_score": True,
        },
        "claim_boundary": (
            "Stage 9D tests whether the Stage-9C compact representation can cross a serialized restart boundary, restore the real GhostAPI runtime, rebuild the task-blind sidecar, and continue the same life without decision-relevant or final-state drift versus an uninterrupted shadow and the frozen Stage-7 reference. The SHA-256 envelope detects accidental payload corruption and malformed rehashed schemas, but it is not authentication against an attacker who can rewrite both payload and digest. This remains research-only and does not replace Ghost production persistence."
        ),
    }
