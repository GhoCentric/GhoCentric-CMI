from copy import deepcopy

import pytest

from ghost_research.v112_relationship_social_kernel_stage1k import (
    observer_trust_delta,
    social_delta_step,
    social_heat,
    world_effects,
)


@pytest.mark.parametrize(
    ("pressure", "expected"),
    [
        (None, 0.5),
        ("relationship_broken", 0.8),
        ("near_break", 0.7),
        ("major_negative_shift", 0.65),
        ("state_shift", 0.6),
        ("minor_negative_shift", 0.5),
    ],
)
def test_social_heat_pressure_adjustments(pressure, expected):
    assert social_heat(
        {"severity": 0.5, "pressure": pressure, "direction": "negative"}
    ) == pytest.approx(expected)


def test_social_heat_positive_direction_scales_after_pressure():
    assert social_heat(
        {
            "severity": 0.5,
            "pressure": "relationship_broken",
            "direction": "positive",
        }
    ) == pytest.approx(0.32)


@pytest.mark.parametrize(
    ("severity", "pressure", "expected"),
    [
        (0.95, "relationship_broken", 1.0),
        (1.0, None, 1.0),
        (0.0, None, 0.0),
    ],
)
def test_social_heat_clamps(severity, pressure, expected):
    assert social_heat(
        {"severity": severity, "pressure": pressure, "direction": "negative"}
    ) == pytest.approx(expected)


def test_social_heat_missing_fields_defaults_to_zero():
    assert social_heat({}) == 0.0


@pytest.mark.parametrize(
    ("direction", "heat", "weight", "expected"),
    [
        ("negative", 0.8, 1.0, -0.16),
        ("negative", 0.8, 0.25, -0.04),
        ("positive", 0.8, 1.0, 0.04),
        ("positive", 0.8, 0.25, 0.01),
        ("stable", 0.8, 1.0, 0.0),
        ("negative", 0.0, 1.0, 0.0),
    ],
)
def test_observer_trust_delta(direction, heat, weight, expected):
    assert observer_trust_delta(direction, heat, weight) == pytest.approx(expected)


def test_world_effects_exact():
    assert world_effects(0.5) == {
        "pressure_delta": 0.1,
        "fear_delta": 0.04,
        "resentment_delta": 0.04,
        "order_delta": -0.02,
        "guard_suspicion_delta": 0.175,
    }


def record(**updates):
    value = {
        "pos": 0.0,
        "neg": 0.0,
        "attachment": 0.0,
        "maturity": 0.4,
        "recent_event_magnitude": 0.3,
    }
    value.update(updates)
    return value


def test_positive_social_delta_and_input_isolation():
    original = record(pos=0.2)
    frozen = deepcopy(original)
    state, meta = social_delta_step(original, 5.0, 0.4)
    assert original == frozen
    assert state["pos"] == pytest.approx(0.6)
    assert state["neg"] == 0.0
    assert meta["before_trust"] == pytest.approx(0.2)
    assert meta["after_trust"] == pytest.approx(0.6)
    assert meta["trust_delta"] == pytest.approx(0.4)


def test_negative_social_delta():
    state, meta = social_delta_step(record(neg=0.1), 5.0, -0.4)
    assert state["neg"] == pytest.approx(0.5)
    assert meta["before_trust"] == pytest.approx(-0.1)
    assert meta["after_trust"] == pytest.approx(-0.5)


def test_zero_social_delta_does_not_create_reservoir_fields():
    state, meta = social_delta_step({"attachment": 0.2}, 5.0, 0.0)
    assert "pos" not in state
    assert "neg" not in state
    assert meta["before_trust"] == 0.0
    assert meta["after_trust"] == 0.0


@pytest.mark.parametrize(
    ("record_value", "delta", "field"),
    [
        ({"pos": 4.95, "neg": 0.0}, 0.20, "pos"),
        ({"pos": 0.0, "neg": 4.95}, -0.20, "neg"),
    ],
)
def test_social_delta_reservoir_cap(record_value, delta, field):
    state, _ = social_delta_step(record_value, 5.0, delta)
    assert state[field] == 5.0


def test_social_delta_preserves_unrelated_fields():
    state, _ = social_delta_step(
        record(custom=0.7, diagnostics={"x": 1}),
        5.0,
        -0.1,
    )
    assert state["custom"] == 0.7
    assert state["diagnostics"] == {"x": 1}
    assert state["maturity"] == 0.4
    assert state["recent_event_magnitude"] == 0.3
