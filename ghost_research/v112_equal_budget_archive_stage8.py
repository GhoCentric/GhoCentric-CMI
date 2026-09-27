"""Task-blind equal-budget generic archive for v1.12-dev Stage 8.

The archive schema is fixed before post-hoc tasks are revealed.  It records
external observation rows verbatim and maintains no Ghost-style epistemic,
relationship, belief-lineage, or task-specific derived structures.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ghost.ids import normalize_id

SCHEMA = "ghost.v1.12-dev.equal-budget-archive.stage8.v1"
_BUDGETS = {
    "within_window": 76806,
    "first_overflow": 110461,
    "deep_overflow": 146792,
}
_LEVELS = frozenset(_BUDGETS)


def encode_bytes(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


def budget_for(level_id: str) -> int:
    key = normalize_id(level_id, "archive level id")
    if key not in _LEVELS:
        raise ValueError(f"unknown Stage-8 archive level: {key!r}")
    return _BUDGETS[key]


def _observation_rows(host_ledger: list[dict]) -> list[dict]:
    if not isinstance(host_ledger, list):
        raise ValueError("host ledger must be a list")
    rows = []
    previous = 0
    for raw in host_ledger:
        if not isinstance(raw, dict) or "step" not in raw or "kind" not in raw:
            raise ValueError("host ledger row has invalid shape")
        step = raw["step"]
        if isinstance(step, bool) or not isinstance(step, int) or step <= previous:
            raise ValueError("host ledger steps must be strictly increasing positive integers")
        previous = step
        if raw["kind"] == "observation":
            rows.append(deepcopy(raw))
    return rows


def freeze_archive(level_id: str, compact_frozen: dict, host_ledger: list[dict]) -> dict:
    """Freeze a generic append-only observation archive before task reveal."""
    level_key = normalize_id(level_id, "archive level id")
    budget = budget_for(level_key)
    if not isinstance(compact_frozen, dict) or compact_frozen.get("mode") != "baseline":
        raise ValueError("Stage-8 archive requires the frozen compact baseline state")
    archive = {
        "schema": SCHEMA,
        "level": level_key,
        "records": _observation_rows(host_ledger),
        "writer_policy": "append_external_observations_verbatim",
    }
    frozen = {
        "mode": "archive_baseline",
        "compact": deepcopy(compact_frozen),
        "archive": archive,
        "allocated_budget_bytes": budget,
    }
    used = encode_bytes(frozen)
    if used > budget:
        raise RuntimeError(f"generic archive exceeded preregistered Stage-7 Ghost byte budget: {used}>{budget}")
    frozen["used_bytes"] = used
    frozen["headroom_bytes"] = budget - used
    return frozen


def records(frozen: dict) -> list[dict]:
    if not isinstance(frozen, dict) or frozen.get("mode") != "archive_baseline":
        raise ValueError("not a Stage-8 archive-baseline snapshot")
    archive = frozen.get("archive")
    if not isinstance(archive, dict) or archive.get("schema") != SCHEMA:
        raise ValueError("Stage-8 archive schema mismatch")
    rows = archive.get("records")
    if not isinstance(rows, list):
        raise ValueError("Stage-8 archive records missing")
    return rows
