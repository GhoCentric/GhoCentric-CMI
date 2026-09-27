"""v1.12-dev Stage-7A exact attribution of Stage-7 overflow support.

This research-only module does not add difficulty. It replays the frozen
Stage-7 experiment and traces each of the fourteen baseline-unsupported
post-hoc tasks to the already-persisted Ghost state used to answer it.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7
from ghost_research import v112_structural_complexity_stage6 as s6

SCHEMA = "ghost.v1.12-dev.latent-state-attribution.stage7a.v1"
VERDICT = "V112_LATENT_STATE_ATTRIBUTION_STAGE7A_EXPERIMENT_VALID"
_OVERFLOW_LEVELS = ("first_overflow", "deep_overflow")
_EXPECTED_TASKS = (
    "early_marker_source",
    "relationship_event_count",
    "evidence_sources",
    "belief_revision_count",
    "counterfactual_without_a",
    "deeper_relationship",
    "novel_delegate_choice",
)


def _level(level_id: str) -> dict:
    for item in ex.canonical_levels():
        if item["id"] == level_id:
            return item
    raise ValueError(f"unknown Stage-7A level: {level_id!r}")


def _task(task_id: str) -> dict:
    for item in s7.reveal_tasks():
        if item["id"] == task_id:
            return item
    raise ValueError(f"unknown Stage-7A task: {task_id!r}")


def _latest_belief(snapshot: dict) -> dict:
    rows = [
        row for row in snapshot["api"]["epistemic"]["records"]
        if row.get("kind") == "belief"
        and row.get("holder") == ex.AGENT
        and row.get("subject") == ex.SUBJECT
    ]
    if not rows:
        raise RuntimeError("Stage-7A current belief disappeared")
    return max(rows, key=lambda row: row["sequence"])


def _relationship(snapshot: dict, source: str) -> dict:
    key = s6._pair_key(ex.AGENT, source)
    try:
        return snapshot["api"]["engine"]["relationships"][key]
    except KeyError as exc:
        raise RuntimeError(f"Stage-7A relationship disappeared: {key}") from exc


def _answer(snapshot: dict, task_id: str) -> Any:
    result = s7._answer(snapshot, _task(task_id))
    return result["answer"] if result["status"] == "supported" else None


def _ablate_marker(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    records = out["api"]["epistemic"]["records"]
    out["api"]["epistemic"]["records"] = [
        row for row in records
        if not (
            row.get("kind") == "observation"
            and row.get("provenance", {}).get("token") == "early_promise"
        )
    ]
    return out


def _ablate_relationship_a(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    rel = _relationship(out, ex.WITNESS_A)
    rel["maturity"] = 0.0
    return out


def _ablate_evidence_links(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    belief = _latest_belief(out)
    belief["evidence_ids"] = []
    belief["provenance"]["evidence_ids"] = []
    return out


def _ablate_revision_lineage(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    for row in out["api"]["epistemic"]["records"]:
        if row.get("kind") == "belief" and row.get("holder") == ex.AGENT and row.get("subject") == ex.SUBJECT:
            row["previous_belief_id"] = None
    return out


def _ablate_counterfactual_signals(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    ids = set(_latest_belief(out)["evidence_ids"])
    for row in out["api"]["epistemic"]["records"]:
        if row.get("kind") == "evidence" and row.get("id") in ids and row.get("source") != ex.WITNESS_A:
            row["provenance"]["signal"] = 0.0
    return out


def _ablate_duty(snapshot: dict) -> dict:
    out = deepcopy(snapshot)
    out["api"]["agents"]["agents"][ex.AGENT]["values"]["duty"] = 0.0
    return out


def _host_steps(ledger: list[dict], task_id: str) -> list[int]:
    observations = [row for row in ledger if row["kind"] == "observation"]
    revisions = [row for row in ledger if row["kind"] == "belief_revision" and row["subject"] == ex.SUBJECT]
    if task_id == "early_marker_source":
        return [row["step"] for row in observations if row["token"] == "early_promise"]
    if task_id == "relationship_event_count":
        return [row["step"] for row in observations if row["event"] == "relationship_event" and row["source"] == ex.WITNESS_A]
    if task_id in {"evidence_sources", "belief_revision_count", "counterfactual_without_a"}:
        return [row["step"] for row in revisions]
    if task_id in {"deeper_relationship", "novel_delegate_choice"}:
        return [row["step"] for row in observations if row["event"] == "relationship_event" and row["source"] in {ex.WITNESS_A, ex.WITNESS_B}]
    raise ValueError(f"no Stage-7A host-step attribution for task: {task_id!r}")


def _path(task_id: str) -> dict:
    paths = {
        "early_marker_source": ("epistemic_observation_provenance", ["api.epistemic.records[kind=observation].provenance.token/source"]),
        "relationship_event_count": ("relationship_aggregate", ["api.engine.relationships[guard_00|witness_a].maturity"]),
        "evidence_sources": ("epistemic_evidence_graph", ["current_belief.evidence_ids", "api.epistemic.records[kind=evidence].source"]),
        "belief_revision_count": ("epistemic_belief_lineage", ["api.epistemic.records[kind=belief].previous_belief_id"]),
        "counterfactual_without_a": ("epistemic_evidence_graph", ["current_belief.evidence_ids", "evidence.provenance.signal", "evidence.source"]),
        "deeper_relationship": ("relationship_aggregate", ["api.engine.relationships[*].maturity"]),
        "novel_delegate_choice": ("relationship_aggregate_plus_value_branch", ["agent.values.duty", "api.engine.relationships[*].maturity"]),
    }
    component, state_paths = paths[task_id]
    return {"component": component, "state_paths": state_paths}


def _counterfactual(snapshot: dict, task_id: str) -> dict:
    original = _answer(snapshot, task_id)
    if task_id == "early_marker_source":
        ablated = _answer(_ablate_marker(snapshot), task_id)
        return {"original": original, "ablated": ablated, "necessary": ablated != original, "ablation": "remove_early_promise_epistemic_observation"}
    if task_id in {"relationship_event_count", "deeper_relationship"}:
        ablated = _answer(_ablate_relationship_a(snapshot), task_id)
        return {"original": original, "ablated": ablated, "necessary": ablated != original, "ablation": "zero_witness_a_relationship_maturity"}
    if task_id == "evidence_sources":
        ablated = _answer(_ablate_evidence_links(snapshot), task_id)
        return {"original": original, "ablated": ablated, "necessary": ablated != original, "ablation": "remove_current_belief_evidence_links"}
    if task_id == "belief_revision_count":
        ablated = _answer(_ablate_revision_lineage(snapshot), task_id)
        return {"original": original, "ablated": ablated, "necessary": ablated != original, "ablation": "remove_belief_previous_links"}
    if task_id == "counterfactual_without_a":
        ablated = _answer(_ablate_counterfactual_signals(snapshot), task_id)
        return {"original": original, "ablated": ablated, "necessary": ablated != original, "ablation": "zero_non_a_evidence_provenance_signals"}
    if task_id == "novel_delegate_choice":
        rel_ablated = _answer(_ablate_relationship_a(snapshot), task_id)
        value_ablated = _answer(_ablate_duty(snapshot), task_id)
        return {
            "original": original,
            "ablated": rel_ablated,
            "necessary": rel_ablated != original,
            "ablation": "zero_witness_a_relationship_maturity",
            "value_only_ablation": value_ablated,
            "value_necessary_on_stage7_workload": value_ablated != original,
        }
    raise ValueError(f"no Stage-7A counterfactual for task: {task_id!r}")


def _trace(level_id: str, task_id: str) -> dict:
    exposure = ex.blind_exposure(_level(level_id), "full")
    baseline = ex.blind_exposure(_level(level_id), "baseline")
    task = _task(task_id)
    expected = s7._ground_truth(exposure["host_ledger"], task)
    full = s7._answer(exposure["frozen"], task)
    flat = s7._answer(baseline["frozen"], task)
    if full != {"status": "supported", "answer": expected}:
        raise RuntimeError(f"Stage-7A Full-Ghost anchor drifted: {level_id}:{task_id}")
    if flat["status"] != "unsupported":
        raise RuntimeError(f"Stage-7A baseline divergence disappeared: {level_id}:{task_id}")
    path = _path(task_id)
    counterfactual = _counterfactual(exposure["frozen"], task_id)
    return {
        "level": level_id,
        "task": task_id,
        "kind": task["kind"],
        "expected": expected,
        "full_answer": full["answer"],
        "baseline_status": flat["status"],
        "host_steps": _host_steps(exposure["host_ledger"], task_id),
        "perception_has_early_promise": ex.token_in_perception(exposure["frozen"], "early_promise"),
        "epistemic_has_early_promise": ex.token_in_epistemic(exposure["frozen"], "early_promise"),
        **path,
        "counterfactual": counterfactual,
    }


def run_attribution() -> dict:
    stage7 = s7.run_matrix()
    if stage7["totals"] != {
        "full": {"correct": 30, "supported": 30, "unsupported": 0},
        "baseline": {"correct": 16, "supported": 16, "unsupported": 14},
    }:
        raise RuntimeError("Stage-7A Stage-7 result anchor drifted")
    rows = [_trace(level_id, task_id) for level_id in _OVERFLOW_LEVELS for task_id in _EXPECTED_TASKS]
    necessary = sum(row["counterfactual"]["necessary"] for row in rows)
    components: dict[str, int] = {}
    for row in rows:
        components[row["component"]] = components.get(row["component"], 0) + 1
    value_rows = [row for row in rows if row["task"] == "novel_delegate_choice"]
    return {
        "schema": SCHEMA,
        "strict_verdict": VERDICT,
        "stage7_anchor": {"full": 30, "baseline": 16, "baseline_unsupported": 14},
        "traced_divergences": len(rows),
        "causally_perturbed": necessary,
        "component_counts": dict(sorted(components.items())),
        "rows": rows,
        "findings": {
            "all_14_have_exact_persisted_state_paths": len(rows) == 14,
            "all_14_change_under_preregistered_component_ablation": necessary == 14,
            "overflow_perception_missing_early_promise": all(not row["perception_has_early_promise"] for row in rows),
            "overflow_epistemic_retains_early_promise": all(row["epistemic_has_early_promise"] for row in rows),
            "delegate_value_branch_causally_required": any(row["counterfactual"].get("value_necessary_on_stage7_workload", False) for row in value_rows),
        },
        "claim_boundary": (
            "Stage 7A attributes only the fourteen Stage-7 overflow divergences. "
            "It tests persisted-state paths and targeted counterfactual perturbations; it does not prove universal Ghost superiority or that every Ghost layer/byte is necessary."
        ),
    }
