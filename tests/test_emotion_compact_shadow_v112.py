from copy import deepcopy
import json

import pytest

import ghost
from ghost import GhostAPI
from ghost._emotion_compact import (
    EMOTION_COMPACT_SHADOW_SCHEMA_VERSION,
    compact_shadow_sizes,
    emotion_defaults_fingerprint,
    pack_emotion_snapshot,
    unpack_emotion_snapshot,
)
from ghost.emotions import (
    DEFAULT_EVENT_IMPULSES,
    EMOTION_SNAPSHOT_SCHEMA_VERSION,
    EmotionRuntime,
)


def _custom_runtime():
    runtime = EmotionRuntime(history_limit=12)
    runtime.configure_event_profile(
        "storm",
        {"fear": 0.62, "anger": 0.19, "hope": -0.17, "resolve": 0.44},
    )
    runtime.configure_event_profile("greet", deepcopy(DEFAULT_EVENT_IMPULSES["greet"]))
    runtime.register_agent(
        "mara",
        initial={"fear": 0.21, "anger": 0.17, "hope": 0.43, "resolve": 0.31},
        baseline={"fear": 0.08, "hope": 0.22, "resolve": 0.19},
        sensitivities={"fear": 1.4, "anger": 0.6, "resolve": 1.8},
        inertia={"fear": 0.61, "anger": 0.91, "resolve": 0.73},
        salience_bias={"fear": 1.3, "hope": 0.72, "resolve": 1.6},
        spotlight_switch_margin=0.09,
    )
    runtime.apply_event(
        "mara",
        "storm",
        intensity=0.71,
        source="weather",
        context_modifiers={"fear": 0.8, "resolve": 1.25},
    )
    runtime.apply_event(
        "mara",
        "help",
        intensity=0.55,
        impulse_overrides={"resolve": 0.25},
    )
    runtime.tick("mara", steps=4)
    runtime.apply_event("mara", "greet")
    return runtime


def _many_agents(count, history_limit=16):
    runtime = EmotionRuntime(history_limit=history_limit)
    runtime.configure_event_profile(
        "resolve_probe",
        {"fear": 0.11, "hope": 0.16, "resolve": 0.35},
    )
    events = (
        "greet",
        "pressure",
        "help",
        "threat",
        "cooperate",
        "betrayal",
        "apology",
        "resolve_probe",
    )
    for index in range(count):
        agent = f"agent_{index:04d}"
        custom = index % 4 == 0
        runtime.register_agent(
            agent,
            initial={
                "fear": ((index * 17) % 41) / 100.0,
                "anger": ((index * 11) % 37) / 100.0,
            },
            baseline={"fear": 0.07 + (index % 3) * 0.01} if custom else None,
            sensitivities={"fear": 1.2, "hope": 0.8} if custom else None,
            inertia={"fear": 0.67} if custom else None,
            salience_bias={"fear": 1.15} if custom else None,
        )
        for offset in range(history_limit + 4):
            runtime.apply_event(
                agent,
                events[(index + offset) % len(events)],
                intensity=0.55 + 0.05 * ((index + offset) % 5),
                source=f"src_{offset % 3}",
            )
        if index % 3 == 0:
            runtime.tick(agent, steps=1 + (index % 5))
    return runtime


def _continue(runtime):
    first = runtime.apply_event(
        "mara",
        "threat",
        intensity=0.63,
        source="continuation_source",
        context_modifiers={"fear": 0.72, "anger": 1.14},
    )
    second = runtime.tick("mara", steps=3)
    third = runtime.apply_event(
        "mara",
        "help",
        intensity=0.81,
        impulse_overrides={"joy": 0.31},
    )
    fourth = runtime.tick("mara", steps=2)
    return [first, second, third, fourth]


def test_shadow_module_is_private_and_fingerprint_is_stable():
    assert not hasattr(ghost, "pack_emotion_snapshot")
    assert not hasattr(GhostAPI, "pack_emotion_snapshot")
    first = emotion_defaults_fingerprint()
    second = emotion_defaults_fingerprint()
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    "runtime",
    [
        EmotionRuntime(),
        _custom_runtime(),
    ],
)
def test_exact_roundtrip_and_canonical_json(runtime):
    snapshot = runtime.snapshot()
    bundle = pack_emotion_snapshot(snapshot)
    restored = unpack_emotion_snapshot(bundle)

    assert restored == snapshot
    assert json.loads(json.dumps(bundle, sort_keys=True)) == bundle
    assert bundle["schema_version"] == EMOTION_COMPACT_SHADOW_SCHEMA_VERSION
    assert bundle["source_schema_version"] == EMOTION_SNAPSHOT_SCHEMA_VERSION


def test_exact_continuation_after_shadow_restore():
    runtime = _custom_runtime()
    snapshot = runtime.snapshot()
    restored = unpack_emotion_snapshot(pack_emotion_snapshot(snapshot))

    left = EmotionRuntime.from_snapshot(snapshot)
    right = EmotionRuntime.from_snapshot(restored)

    assert _continue(left) == _continue(right)
    assert left.snapshot() == right.snapshot()


def test_custom_profile_identity_survives_even_when_equal_to_default():
    runtime = EmotionRuntime()
    runtime.configure_event_profile("greet", deepcopy(DEFAULT_EVENT_IMPULSES["greet"]))
    snapshot = runtime.snapshot()

    restored = unpack_emotion_snapshot(pack_emotion_snapshot(snapshot))

    assert restored == snapshot
    assert restored["customized_profiles"] == ["greet"]


def test_bundle_and_restore_are_detached_from_inputs():
    runtime = _custom_runtime()
    snapshot = runtime.snapshot()
    original = deepcopy(snapshot)

    bundle = pack_emotion_snapshot(snapshot)
    snapshot["agents"]["mara"]["levels"]["fear"] = 0.999
    assert unpack_emotion_snapshot(bundle) == original

    restored = unpack_emotion_snapshot(bundle)
    restored["agents"]["mara"]["levels"]["fear"] = 0.001
    assert unpack_emotion_snapshot(bundle) == original


@pytest.mark.parametrize("count", [1, 10, 100])
def test_hot_shadow_is_smaller_and_full_roundtrip_scales(count):
    snapshot = _many_agents(count).snapshot()
    sizes = compact_shadow_sizes(snapshot)
    bundle = pack_emotion_snapshot(snapshot)

    assert unpack_emotion_snapshot(bundle) == snapshot
    assert sizes["hot_bytes"] < sizes["full_snapshot_bytes"]
    assert sizes["hot_over_full"] < 0.10
    assert sizes["bundle_bytes"] <= sizes["full_snapshot_bytes"]


def test_sparse_maps_omit_default_values():
    runtime = EmotionRuntime()
    runtime.register_agent("mara")
    bundle = pack_emotion_snapshot(runtime.snapshot())
    hot = bundle["hot"]["agents"]["mara"]

    assert hot["baseline_sparse"] == {}
    assert hot["sensitivities_sparse"] == {}
    assert hot["inertia_sparse"] == {}
    assert hot["salience_bias_sparse"] == {}


def test_pack_rejects_non_dict_old_schema_and_noncanonical_snapshot():
    with pytest.raises(ValueError, match="must be a dict"):
        pack_emotion_snapshot([])

    old = EmotionRuntime().snapshot()
    old["schema_version"] = "1.0"
    with pytest.raises(ValueError, match="only current"):
        pack_emotion_snapshot(old)

    noncanonical = EmotionRuntime().snapshot()
    noncanonical["customized_profiles"] = ["greet", "greet"]
    with pytest.raises(ValueError, match="canonical"):
        pack_emotion_snapshot(noncanonical)


def test_pack_rejects_missing_or_unmarked_changed_default_profiles():
    missing = EmotionRuntime().snapshot()
    del missing["event_profiles"]["greet"]
    with pytest.raises(ValueError, match="missing current default profiles"):
        pack_emotion_snapshot(missing)

    changed = EmotionRuntime().snapshot()
    changed["event_profiles"]["greet"]["fear"] = -0.01
    with pytest.raises(ValueError, match="non-customized"):
        pack_emotion_snapshot(changed)


def _valid_bundle():
    return pack_emotion_snapshot(_custom_runtime().snapshot())


def test_unpack_rejects_non_dict_and_invalid_bundle_keys():
    with pytest.raises(ValueError, match="must be a dict"):
        unpack_emotion_snapshot([])

    bundle = _valid_bundle()
    bundle["extra"] = 1
    with pytest.raises(ValueError, match="invalid keys"):
        unpack_emotion_snapshot(bundle)


def test_unpack_rejects_schema_source_and_fingerprint_drift():
    bundle = _valid_bundle()
    bundle["schema_version"] = "999"
    with pytest.raises(ValueError, match="unsupported emotion compact shadow schema"):
        unpack_emotion_snapshot(bundle)

    bundle = _valid_bundle()
    bundle["source_schema_version"] = "999"
    with pytest.raises(ValueError, match="unsupported emotion compact source schema"):
        unpack_emotion_snapshot(bundle)

    bundle = _valid_bundle()
    bundle["defaults_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="defaults fingerprint mismatch"):
        unpack_emotion_snapshot(bundle)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda b: b.__setitem__("hot", []), "must be a dict"),
        (lambda b: b["hot"].__setitem__("extra", 1), "invalid keys"),
        (lambda b: b.__setitem__("history", []), "must be a dict"),
        (lambda b: b["hot"].__setitem__("custom_profiles", []), "must be a dict"),
        (lambda b: b["hot"].__setitem__("agents", []), "must be a dict"),
        (
            lambda b: b["hot"]["agents"].__setitem__("mara", []),
            "must be a dict",
        ),
        (
            lambda b: b["hot"]["agents"]["mara"].__setitem__("extra", 1),
            "invalid keys",
        ),
        (
            lambda b: b["hot"]["agents"]["mara"].__setitem__("levels", []),
            "must be a dict",
        ),
        (
            lambda b: b["hot"]["agents"]["mara"].__setitem__(
                "baseline_sparse",
                [],
            ),
            "must be a dict",
        ),
        (
            lambda b: b["hot"]["agents"]["mara"]["baseline_sparse"].__setitem__(
                "unknown_channel",
                0.2,
            ),
            "unknown emotion channels",
        ),
        (
            lambda b: b["history"].__setitem__("unknown_agent", []),
            "unknown agents",
        ),
    ],
)
def test_unpack_rejects_malformed_shadow_shapes(mutator, message):
    bundle = _valid_bundle()
    mutator(bundle)
    with pytest.raises(ValueError, match=message):
        unpack_emotion_snapshot(bundle)


def test_unpack_uses_existing_emotion_validation_for_values_and_history():
    bundle = _valid_bundle()
    bundle["hot"]["agents"]["mara"]["levels"]["fear"] = 2.0
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        unpack_emotion_snapshot(bundle)

    bundle = _valid_bundle()
    bundle["history"]["mara"] = ["not-a-record"]
    with pytest.raises(ValueError, match=r"history\[0\] must be a dict"):
        unpack_emotion_snapshot(bundle)


def test_empty_history_and_profile_only_state_roundtrip():
    runtime = EmotionRuntime(history_limit=5)
    runtime.configure_event_profile("quiet_signal", {"fear": -0.1})
    snapshot = runtime.snapshot()
    bundle = pack_emotion_snapshot(snapshot)

    assert bundle["history"] == {}
    assert unpack_emotion_snapshot(bundle) == snapshot
