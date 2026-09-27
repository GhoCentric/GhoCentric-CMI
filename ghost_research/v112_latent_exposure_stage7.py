"""Blind-life exposure substrate for v1.12-dev Stage 7.

This module knows only how to deliver a deterministic life to the frozen
Stage-6 Full-Ghost and strong-baseline architectures.  It does not import or
reference the post-hoc task battery.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ghost.ids import normalize_id
from ghost_research import v112_continuity_stress_stage3 as s3
from ghost_research import v112_structural_complexity_stage6 as s6

AGENT = "guard_00"
SUBJECT = "visitor_00"
WITNESS_A = "witness_a"
WITNESS_B = "witness_b"
WITNESS_C = "witness_c"
_LEVEL_KEYS = frozenset({"id", "ambient_events"})


def level(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) != _LEVEL_KEYS:
        raise ValueError("latent-state level has invalid shape")
    return {
        "id": normalize_id(raw["id"], "latent-state level id"),
        "ambient_events": s6._positive_int(raw["ambient_events"], "ambient events", allow_zero=True),
    }


def canonical_levels() -> list[dict]:
    return [
        level({"id": "within_window", "ambient_events": 64}),
        level({"id": "first_overflow", "ambient_events": 128}),
        level({"id": "deep_overflow", "ambient_events": 224}),
    ]


def _record(ledger: list[dict], kind: str, **data: Any) -> dict:
    row = {"step": len(ledger) + 1, "kind": kind}
    row.update(deepcopy(data))
    ledger.append(row)
    return row


def _observe(contender: s6.StructuralContender, ledger: list[dict], life_id: str, event: str, *, source: str, subject: str, token: str, features: dict | None = None) -> None:
    event = normalize_id(event, "life event")
    source = normalize_id(source, "life source")
    subject = normalize_id(subject, "life subject")
    token = normalize_id(token, "life token")
    payload = deepcopy(features or {})
    row = _record(ledger, "observation", event=event, source=source, subject=subject, token=token, features=payload)
    if contender.mode == "full":
        contender.agents[AGENT].observe(event, kind="social", subject=subject, source=source, features={"token": token, **payload})
        contender.api.observe(
            observer=AGENT,
            kind="social",
            visible_features=[event, token],
            reliability=1.0,
            subject=subject,
            provenance={
                "stage7_life": life_id,
                "host_step": row["step"],
                "event": event,
                "source": source,
                "token": token,
                **payload,
            },
        )
        return
    contender.flat[AGENT].observe(
        event,
        subject,
        {"source": source, "token": token, "host_step": row["step"], **payload},
    )


def _relationship(contender: s6.StructuralContender, ledger: list[dict], life_id: str, source: str, event: str) -> None:
    _observe(
        contender,
        ledger,
        life_id,
        "relationship_event",
        source=source,
        subject=AGENT,
        token=f"rel_{source}_{len(ledger) + 1}",
        features={"relationship_event": event},
    )
    contender.relationship_event(AGENT, source, event)


def _evidence_adjustments(signal: float) -> tuple[dict, dict]:
    signed = s3._signed(signal, "stage7 evidence signal")
    strength = abs(signed)
    if signed > 0.0:
        return {"threat": {"hostile": strength}}, {"threat": {"benign": strength * 0.5}}
    if signed < 0.0:
        return {"threat": {"benign": strength}}, {"threat": {"hostile": strength * 0.5}}
    return {}, {}


def _evidence(contender: s6.StructuralContender, ledger: list[dict], life_id: str, source: str, signal: float, token: str) -> None:
    signed = s3._signed(signal, "stage7 evidence signal")
    _observe(
        contender,
        ledger,
        life_id,
        "evidence_signal",
        source=source,
        subject=SUBJECT,
        token=token,
        features={"signal": signed},
    )
    _record(ledger, "belief_revision", source=source, subject=SUBJECT, signal=signed, token=token)
    if contender.mode == "baseline":
        contender.flat[AGENT].apply_signal(SUBJECT, "threat", "hostile", "benign", signed)
        return
    supports, contradicts = _evidence_adjustments(signed)
    evidence = contender.api.add_evidence(
        evidence_type="stage7_signal",
        source=source,
        supports=supports,
        contradicts=contradicts,
        subject=SUBJECT,
        available_to=AGENT,
        provenance={"stage7_life": life_id, "token": token, "signal": signed},
    )
    current = contender.api.get_belief(AGENT, SUBJECT)
    if current is None:
        raise RuntimeError("Stage-7 Ghost belief seed disappeared")
    contender.api.evaluate_beliefs(
        holder=AGENT,
        subject=SUBJECT,
        evidence_ids=[evidence["id"]],
        previous_belief_id=current["id"],
        provenance={"stage7_life": life_id, "token": token},
    )


def _ambient(contender: s6.StructuralContender, ledger: list[dict], life_id: str, count: int) -> None:
    for index in range(count):
        _observe(
            contender,
            ledger,
            life_id,
            f"ambient_{index % 9}",
            source="world",
            subject=f"ambient_subject_{index % 11}",
            token=f"ambient_token_{index:03d}",
            features={"ordinal": index, "tone": f"tone_{index % 5}"},
        )


def _early_life(contender: s6.StructuralContender, ledger: list[dict], life_id: str) -> None:
    _observe(contender, ledger, life_id, "life_begin", source="world", subject=SUBJECT, token="life_begin")
    _observe(
        contender, ledger, life_id, "promise_made", source=WITNESS_A, subject=AGENT,
        token="early_promise", features={"promise": "return_help"},
    )
    for event in ("help", "help", "help", "help", "deceive"):
        _relationship(contender, ledger, life_id, WITNESS_A, event)
    for event in ("help", "deceive", "help"):
        _relationship(contender, ledger, life_id, WITNESS_B, event)
    _evidence(contender, ledger, life_id, WITNESS_A, 1.0, "evidence_a")
    _evidence(contender, ledger, life_id, WITNESS_B, 0.2, "evidence_b")
    _evidence(contender, ledger, life_id, WITNESS_C, -0.8, "evidence_c")


def _late_life(contender: s6.StructuralContender, ledger: list[dict], life_id: str) -> None:
    _evidence(contender, ledger, life_id, WITNESS_B, 0.1, "evidence_b_recent")
    _observe(
        contender, ledger, life_id, "late_warning", source=WITNESS_C, subject=SUBJECT,
        token="late_warning", features={"warning": "north_gate"},
    )
    _observe(contender, ledger, life_id, "life_end", source="world", subject=SUBJECT, token="life_end")


def _freeze(contender: s6.StructuralContender) -> dict:
    if contender.mode == "full":
        return {"mode": "full", "api": contender.api.snapshot()}
    return {
        "mode": "baseline",
        "api": contender.api.snapshot(),
        "flat": contender.flat[AGENT].snapshot(),
        "relationships": deepcopy(contender.relationships),
    }


def blind_exposure(raw_level: dict, mode: str) -> dict:
    cfg = level(raw_level)
    contender = s6.StructuralContender(mode, 3)
    ledger: list[dict] = []
    _early_life(contender, ledger, cfg["id"])
    _ambient(contender, ledger, cfg["id"], cfg["ambient_events"])
    _late_life(contender, ledger, cfg["id"])
    frozen = _freeze(contender)
    return {
        "level": cfg,
        "frozen": frozen,
        "host_ledger": ledger,
        "snapshot_bytes": s6._encode_bytes(frozen),
    }


def baseline_history_complete(frozen: dict) -> bool:
    flat = frozen["flat"]
    return flat["sequence"] == len(flat["observations"])


def ghost_epistemic_records(frozen: dict) -> list[dict]:
    return frozen["api"]["epistemic"]["records"]


def ghost_perception_history(frozen: dict) -> list[dict]:
    perception = frozen["api"].get("perception")
    if perception is None:
        return []
    observer = perception["observers"].get(AGENT)
    return [] if observer is None else observer["history"]


def token_in_perception(frozen: dict, token: str) -> bool:
    return any(row["features"].get("token") == token for row in ghost_perception_history(frozen))


def token_in_epistemic(frozen: dict, token: str) -> bool:
    return any(
        row.get("kind") == "observation" and row.get("provenance", {}).get("token") == token
        for row in ghost_epistemic_records(frozen)
    )


def baseline_observations(frozen: dict) -> list[dict]:
    return frozen["flat"]["observations"]
