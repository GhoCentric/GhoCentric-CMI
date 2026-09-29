"""Private shadow codec for compact EmotionRuntime persistence research.

This module is intentionally not exported through ``ghost`` or ``GhostAPI``.
The existing EmotionRuntime snapshot remains authoritative.  The codec exists
only to test whether an exact, version-bound hot/cold representation can be
maintained alongside it without changing runtime behavior.
"""

from copy import deepcopy
import hashlib
import json

from .emotions import (
    DEFAULT_EMOTIONS,
    DEFAULT_EVENT_IMPULSES,
    DEFAULT_GENERIC_INERTIA,
    DEFAULT_INERTIA,
    DEFAULT_SPOTLIGHT_SWITCH_MARGIN,
    EMOTION_SNAPSHOT_SCHEMA_VERSION,
    EmotionRuntime,
)

EMOTION_COMPACT_SHADOW_SCHEMA_VERSION = "1"

_BUNDLE_KEYS = {
    "defaults_fingerprint",
    "history",
    "hot",
    "schema_version",
    "source_schema_version",
}
_HOT_KEYS = {
    "agents",
    "custom_profiles",
    "history_limit",
    "sequence",
}
_AGENT_HOT_KEYS = {
    "baseline_sparse",
    "inertia_sparse",
    "levels",
    "salience_bias_sparse",
    "sensitivities_sparse",
    "spotlight_emotion",
    "spotlight_switch_margin",
}


def _canonical_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def emotion_defaults_fingerprint():
    payload = {
        "default_emotions": list(DEFAULT_EMOTIONS),
        "default_event_impulses": DEFAULT_EVENT_IMPULSES,
        "default_generic_inertia": DEFAULT_GENERIC_INERTIA,
        "default_inertia": DEFAULT_INERTIA,
        "default_spotlight_switch_margin": DEFAULT_SPOTLIGHT_SWITCH_MARGIN,
        "emotion_snapshot_schema": EMOTION_SNAPSHOT_SCHEMA_VERSION,
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dict")
    return value


def _require_exact_keys(value, expected, label):
    value = _require_dict(value, label)
    keys = set(value)
    if keys != expected:
        raise ValueError(f"{label} has invalid keys")
    return value


def _default_inertia(emotion):
    return DEFAULT_INERTIA.get(emotion, DEFAULT_GENERIC_INERTIA)


def _default_profiles(history_limit):
    return EmotionRuntime(history_limit=history_limit).snapshot()["event_profiles"]


def _validated_current_snapshot(snapshot):
    snapshot = _require_dict(snapshot, "emotion snapshot")
    if snapshot.get("schema_version") != EMOTION_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            "compact emotion shadow accepts only current emotion snapshot schema "
            + repr(EMOTION_SNAPSHOT_SCHEMA_VERSION)
        )
    normalized = EmotionRuntime.from_snapshot(deepcopy(snapshot)).snapshot()
    if normalized != snapshot:
        raise ValueError("emotion snapshot must already be canonical")
    return normalized


def _sparse_map(mapping, default_for):
    return {
        name: value
        for name, value in mapping.items()
        if value != default_for(name)
    }


def pack_emotion_snapshot(snapshot):
    """Return an exact shadow bundle split into hot state and cold history."""

    snapshot = _validated_current_snapshot(snapshot)
    history_limit = snapshot["history_limit"]
    default_profiles = _default_profiles(history_limit)
    customized = set(snapshot["customized_profiles"])
    profiles = snapshot["event_profiles"]

    missing_defaults = set(default_profiles) - set(profiles)
    if missing_defaults:
        raise ValueError("emotion snapshot is missing current default profiles")

    for event, profile in profiles.items():
        if event not in customized and profile != default_profiles.get(event):
            raise ValueError(
                "non-customized event profile differs from current defaults: "
                + event
            )

    custom_profiles = {
        event: deepcopy(profiles[event])
        for event in sorted(customized)
    }

    hot_agents = {}
    history_agents = {}
    for agent, state in sorted(snapshot["agents"].items()):
        hot_agents[agent] = {
            "levels": deepcopy(state["levels"]),
            "baseline_sparse": _sparse_map(
                state["baseline"],
                lambda _name: 0.0,
            ),
            "sensitivities_sparse": _sparse_map(
                state["sensitivities"],
                lambda _name: 1.0,
            ),
            "inertia_sparse": _sparse_map(
                state["inertia"],
                _default_inertia,
            ),
            "salience_bias_sparse": _sparse_map(
                state["salience_bias"],
                lambda _name: 1.0,
            ),
            "spotlight_emotion": state["spotlight_emotion"],
            "spotlight_switch_margin": state["spotlight_switch_margin"],
        }
        if state["history"]:
            history_agents[agent] = deepcopy(state["history"])

    return {
        "schema_version": EMOTION_COMPACT_SHADOW_SCHEMA_VERSION,
        "source_schema_version": EMOTION_SNAPSHOT_SCHEMA_VERSION,
        "defaults_fingerprint": emotion_defaults_fingerprint(),
        "hot": {
            "history_limit": history_limit,
            "sequence": snapshot["sequence"],
            "custom_profiles": custom_profiles,
            "agents": hot_agents,
        },
        "history": history_agents,
    }


def _expand_sparse(names, sparse, default_for, label):
    sparse = _require_dict(sparse, label)
    extra = set(sparse) - set(names)
    if extra:
        raise ValueError(f"{label} contains unknown emotion channels")
    return {
        name: sparse.get(name, default_for(name))
        for name in names
    }


def unpack_emotion_snapshot(bundle):
    """Reconstruct the authoritative current EmotionRuntime snapshot exactly."""

    bundle = _require_exact_keys(bundle, _BUNDLE_KEYS, "emotion compact bundle")
    if bundle["schema_version"] != EMOTION_COMPACT_SHADOW_SCHEMA_VERSION:
        raise ValueError("unsupported emotion compact shadow schema")
    if bundle["source_schema_version"] != EMOTION_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported emotion compact source schema")
    if bundle["defaults_fingerprint"] != emotion_defaults_fingerprint():
        raise ValueError("emotion compact defaults fingerprint mismatch")

    hot = _require_exact_keys(bundle["hot"], _HOT_KEYS, "emotion compact hot state")
    history = _require_dict(bundle["history"], "emotion compact history")
    custom_profiles = _require_dict(
        hot["custom_profiles"],
        "emotion compact custom profiles",
    )
    agents_hot = _require_dict(hot["agents"], "emotion compact agents")

    default_profiles = _default_profiles(hot["history_limit"])
    profiles = deepcopy(default_profiles)
    for event, profile in custom_profiles.items():
        profiles[event] = deepcopy(profile)

    unknown_history_agents = set(history) - set(agents_hot)
    if unknown_history_agents:
        raise ValueError("emotion compact history contains unknown agents")

    agents = {}
    for agent, raw_hot in sorted(agents_hot.items()):
        raw_hot = _require_exact_keys(
            raw_hot,
            _AGENT_HOT_KEYS,
            f"emotion compact agent {agent}",
        )
        levels = _require_dict(
            raw_hot["levels"],
            f"emotion compact agent {agent} levels",
        )
        names = sorted(levels)
        agents[agent] = {
            "levels": deepcopy(levels),
            "baseline": _expand_sparse(
                names,
                raw_hot["baseline_sparse"],
                lambda _name: 0.0,
                f"emotion compact agent {agent} baseline",
            ),
            "sensitivities": _expand_sparse(
                names,
                raw_hot["sensitivities_sparse"],
                lambda _name: 1.0,
                f"emotion compact agent {agent} sensitivities",
            ),
            "inertia": _expand_sparse(
                names,
                raw_hot["inertia_sparse"],
                _default_inertia,
                f"emotion compact agent {agent} inertia",
            ),
            "salience_bias": _expand_sparse(
                names,
                raw_hot["salience_bias_sparse"],
                lambda _name: 1.0,
                f"emotion compact agent {agent} salience bias",
            ),
            "spotlight_emotion": raw_hot["spotlight_emotion"],
            "spotlight_switch_margin": raw_hot["spotlight_switch_margin"],
            "history": deepcopy(history.get(agent, [])),
        }

    candidate = {
        "schema_version": EMOTION_SNAPSHOT_SCHEMA_VERSION,
        "history_limit": hot["history_limit"],
        "sequence": hot["sequence"],
        "event_profiles": profiles,
        "customized_profiles": sorted(custom_profiles),
        "agents": agents,
    }
    return EmotionRuntime.from_snapshot(candidate).snapshot()


def compact_shadow_sizes(snapshot):
    """Return canonical byte telemetry without changing the authoritative format."""

    bundle = pack_emotion_snapshot(snapshot)
    full_bytes = len(_canonical_bytes(snapshot))
    hot_bytes = len(_canonical_bytes(bundle["hot"]))
    history_bytes = len(_canonical_bytes(bundle["history"]))
    bundle_bytes = len(_canonical_bytes(bundle))
    return {
        "full_snapshot_bytes": full_bytes,
        "hot_bytes": hot_bytes,
        "history_bytes": history_bytes,
        "bundle_bytes": bundle_bytes,
        "hot_over_full": hot_bytes / full_bytes,
        "bundle_over_full": bundle_bytes / full_bytes,
    }
