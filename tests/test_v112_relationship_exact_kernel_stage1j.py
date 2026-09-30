from copy import deepcopy

import pytest

from ghost_research.v112_relationship_exact_kernel_stage1j import (
    PARAM_NAMES,
    exact_step,
    resolve_exact_params,
)


def defaults():
    return {
        "apology_recovery_fraction": 0.25,
        "recent_event_decay": 0.8,
        "maturity_gain": 0.01,
        "maturity_cap": 0.75,
        "volatility": 1.0,
        "positive_volatility": 1.0,
        "negative_volatility": 1.0,
    }


def record(**updates):
    value = {
        "pos": 0.0,
        "neg": 0.0,
        "attachment": 0.0,
        "maturity": 0.0,
        "recent_event_magnitude": 0.0,
    }
    value.update(updates)
    return value


def test_resolve_exact_params_defaults_and_overrides():
    out = resolve_exact_params(
        {"maturity_cap": 0.4, "recent_event_decay": 0.5},
        defaults(),
    )
    assert set(out) == set(PARAM_NAMES)
    assert out["maturity_cap"] == 0.4
    assert out["recent_event_decay"] == 0.5
    assert out["maturity_gain"] == 0.01


def test_positive_exact_step_and_non_mutating():
    original = record(pos=0.1, attachment=0.2)
    frozen = deepcopy(original)
    state, meta = exact_step(
        original,
        defaults(),
        event="cooperate",
        intensity=0.5,
        spec={"trust": 0.08, "attachment": 0.02},
    )
    assert original == frozen
    assert state["pos"] == pytest.approx(0.14)
    assert state["attachment"] == pytest.approx(0.21)
    assert state["maturity"] == 0.01
    assert state["recent_event_magnitude"] == pytest.approx(0.008)
    assert meta["trust_delta"] == 0.04
    assert meta["channel"] == "pos"


def test_negative_exact_step():
    state, meta = exact_step(
        record(),
        defaults(),
        event="pressure",
        intensity=0.5,
        spec={"trust": -0.08},
    )
    assert state["neg"] == pytest.approx(0.04)
    assert meta["trust_delta"] == -0.04
    assert meta["channel"] == "neg"


def test_zero_exact_step_uses_spec_sign_for_channel():
    state, meta = exact_step(
        record(),
        defaults(),
        event="neutral",
        intensity=1.0,
        spec={"trust": 0.0},
    )
    assert state["pos"] == 0.0
    assert state["neg"] == 0.0
    assert meta["channel"] == "pos"


def test_apology_nonnegative_trust_is_zero_but_memory_uses_requested_delta():
    state, meta = exact_step(
        record(pos=0.3),
        defaults(),
        event="apology",
        intensity=1.0,
        spec={"trust": 0.05, "recovery_fraction": 0.25},
    )
    assert state["pos"] == 0.3
    assert meta["trust_delta"] == 0.0
    assert meta["requested_delta"] == 0.05
    assert state["recent_event_magnitude"] == pytest.approx(0.01)


def test_apology_negative_trust_uses_full_requested_delta_when_below_cap():
    state, meta = exact_step(
        record(neg=1.0),
        defaults(),
        event="apology",
        intensity=1.0,
        spec={"trust": 0.05, "recovery_fraction": 0.25},
    )
    assert state["pos"] == 0.05
    assert meta["trust_delta"] == 0.05


def test_apology_negative_trust_is_recovery_capped():
    state, meta = exact_step(
        record(neg=0.08),
        defaults(),
        event="apology",
        intensity=1.0,
        spec={"trust": 0.05, "recovery_fraction": 0.25},
    )
    assert state["pos"] == pytest.approx(0.02)
    assert meta["trust_delta"] == pytest.approx(0.02)
    assert state["recent_event_magnitude"] == pytest.approx(0.01)


def test_apology_uses_record_default_recovery_fraction_when_spec_omits_it():
    _, meta = exact_step(
        record(neg=0.08, apology_recovery_fraction=0.5),
        defaults(),
        event="apology",
        intensity=1.0,
        spec={"trust": 0.05},
    )
    assert meta["trust_delta"] == pytest.approx(0.04)


def test_extra_deltas_accumulate_and_scale():
    state, _ = exact_step(
        record(curiosity=0.3),
        defaults(),
        event="custom",
        intensity=0.25,
        spec={
            "trust": 0.2,
            "attachment": -0.4,
            "extra_deltas": {"curiosity": 0.8, "respect": -0.2},
        },
    )
    assert state["curiosity"] == pytest.approx(0.5)
    assert state["respect"] == pytest.approx(-0.05)
    assert state["attachment"] == pytest.approx(-0.1)


def test_zero_attachment_does_not_create_missing_attachment_field():
    state, _ = exact_step(
        {"pos": 0.0, "neg": 0.0},
        defaults(),
        event="neutral",
        intensity=1.0,
        spec={"trust": 0.0},
    )
    assert "attachment" not in state


def test_recent_decay_and_maturity_overrides():
    state, meta = exact_step(
        record(
            maturity=0.39,
            recent_event_magnitude=0.6,
            recent_event_decay=0.5,
            maturity_gain=0.02,
            maturity_cap=0.4,
            volatility=1.2,
            positive_volatility=1.1,
            negative_volatility=1.3,
        ),
        defaults(),
        event="deceive",
        intensity=1.0,
        spec={"trust": -0.15},
    )
    assert state["recent_event_magnitude"] == pytest.approx(0.375)
    assert state["maturity"] == 0.4
    assert meta["maturity"] == 0.39
    assert meta["maturity_modifier"] == pytest.approx(0.61)
    assert meta["volatility"] == 1.2
    assert meta["positive_volatility"] == 1.1
    assert meta["negative_volatility"] == 1.3


def test_maturity_modifier_clamps_at_zero():
    _, meta = exact_step(
        record(maturity=1.2),
        defaults(),
        event="neutral",
        intensity=0.0,
        spec={"trust": 0.0},
    )
    assert meta["maturity_modifier"] == 0.0


@pytest.mark.parametrize(
    ("trust", "expected"),
    [(0.1, "pos"), (-0.1, "neg"), (0.0, "pos")],
)
def test_zero_intensity_channel_follows_spec_sign(trust, expected):
    _, meta = exact_step(
        record(),
        defaults(),
        event="x",
        intensity=0.0,
        spec={"trust": trust},
    )
    assert meta["channel"] == expected
