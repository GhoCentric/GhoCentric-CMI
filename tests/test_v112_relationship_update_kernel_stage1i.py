from copy import deepcopy

import pytest

from ghost_research.v112_relationship_update_kernel_stage1i import (
    PARAM_NAMES,
    event_step,
    resolve_params,
    tick_step,
)


def defaults():
    return {
        "pos_gain": 0.85,
        "neg_gain": 1.1,
        "pos_decay": 0.97,
        "neg_decay": 0.975,
        "max_reservoir": 5.0,
        "positive_reservoir_cap": 3.25,
        "betrayal_shock_maturity_threshold": 0.5,
        "betrayal_shock_positive_threshold": 1.0,
        "betrayal_stability_breach_fraction": 0.9,
        "stability_shock_maturity_threshold": 0.5,
        "stability_shock_positive_threshold": 1.0,
        "high_severity_threshold": 0.5,
        "high_severity_shock_bonus": 0.25,
        "severe_negative_maturity_floor": 0.45,
        "relative_shock_ratio": 2.5,
        "relative_shock_bonus": 0.2,
        "recent_event_decay": 0.8,
        "volatility": 1.0,
        "positive_volatility": 1.0,
        "negative_volatility": 1.0,
        "maturity_gain": 0.01,
        "maturity_cap": 0.75,
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


def test_resolve_params_uses_defaults_and_record_overrides():
    d = defaults()
    r = {"pos_gain": 2.0, "maturity_cap": 0.4}
    out = resolve_params(r, d)
    assert set(out) == set(PARAM_NAMES)
    assert out["pos_gain"] == 2.0
    assert out["maturity_cap"] == 0.4
    assert out["neg_gain"] == d["neg_gain"]


def test_positive_step_exact_and_non_mutating():
    d = defaults()
    r = record(neg=1.0, attachment=0.25)
    frozen = deepcopy(r)
    state, meta = event_step(
        r,
        d,
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=0.5,
        attachment_delta=0.025,
    )
    expected_gain = 0.06 * 0.85 * (1.0 / 1.35)
    assert r == frozen
    assert state == {
        "pos": expected_gain,
        "neg": 1.0,
        "attachment": 0.275,
        "maturity": 0.01,
        "recent_event_magnitude": 0.011999999999999997,
    }
    assert meta["amount"] == 0.06
    assert meta["effective_gain"] == expected_gain
    assert meta["shock_multiplier"] == 1.0
    assert meta["shock_applied"] is False


def test_sparse_record_uses_parameter_defaults():
    state, _ = event_step(
        {},
        defaults(),
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=1.0,
    )
    assert state["pos"] == 0.102
    assert state["attachment"] == 0.0
    assert state["maturity"] == 0.01


def test_record_parameter_override_changes_positive_gain():
    r = record(pos_gain=1.7)
    state, _ = event_step(
        r,
        defaults(),
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=1.0,
    )
    assert state["pos"] == 0.204


def test_positive_saturation_and_cap():
    r = record(pos=3.25)
    state, meta = event_step(
        r,
        defaults(),
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=1.0,
    )
    assert state["pos"] == 3.25
    assert meta["effective_gain"] == 0.0


def test_negative_step_without_shock():
    r = record()
    state, meta = event_step(
        r,
        defaults(),
        event="insult",
        channel="neg",
        base_amount=0.15,
        intensity=1.0,
    )
    assert state["neg"] == 0.165
    assert meta["effective_gain"] == 0.165
    assert meta["high_severity_shock"] is False
    assert meta["relative_shock"] is False


@pytest.mark.parametrize(
    ("maturity", "pos", "eligible"),
    [
        (0.499999, 1.0, False),
        (0.5, 0.999999, False),
        (0.5, 1.0, True),
    ],
)
def test_shock_eligibility_thresholds(maturity, pos, eligible):
    r = record(pos=pos, maturity=maturity)
    _, meta = event_step(
        r,
        defaults(),
        event="betrayal",
        channel="neg",
        base_amount=0.7,
        intensity=1.0,
    )
    assert meta["high_severity_shock"] is eligible


def test_eligible_but_below_high_and_relative_thresholds():
    r = record(pos=1.0, maturity=0.5, recent_event_magnitude=1.0)
    _, meta = event_step(
        r,
        defaults(),
        event="attack",
        channel="neg",
        base_amount=0.35,
        intensity=1.0,
    )
    assert meta["high_severity_shock"] is False
    assert meta["relative_shock"] is False
    assert meta["shock_multiplier"] == 1.0


def test_high_severity_threshold_is_inclusive():
    r = record(pos=1.0, maturity=0.5)
    _, meta = event_step(
        r,
        defaults(),
        event="custom",
        channel="neg",
        base_amount=0.5,
        intensity=1.0,
    )
    assert meta["high_severity_shock"] is True
    assert meta["shock_multiplier"] == 1.25


def test_high_severity_uses_maturity_floor():
    r = record(pos=1.0, maturity=0.9)
    _, meta = event_step(
        r,
        defaults(),
        event="custom",
        channel="neg",
        base_amount=0.5,
        intensity=1.0,
    )
    assert meta["maturity_modifier"] == pytest.approx(0.1)
    assert meta["event_maturity_modifier"] == 0.45


def test_relative_shock_threshold_is_inclusive():
    r = record(pos=1.0, maturity=0.5, recent_event_magnitude=0.2)
    _, meta = event_step(
        r,
        defaults(),
        event="custom",
        channel="neg",
        base_amount=0.5,
        intensity=1.0,
    )
    assert meta["relative_shock"] is True
    assert meta["shock_multiplier"] == 1.45


def test_relative_shock_requires_positive_recent_memory():
    r = record(pos=1.0, maturity=0.5, recent_event_magnitude=0.0)
    _, meta = event_step(
        r,
        defaults(),
        event="custom",
        channel="neg",
        base_amount=0.5,
        intensity=1.0,
    )
    assert meta["relative_shock"] is False


def test_betrayal_breach_is_exact_and_sets_shock_applied():
    r = record(pos=1.0, maturity=0.5)
    state, meta = event_step(
        r,
        defaults(),
        event="betrayal",
        channel="neg",
        base_amount=0.7,
        intensity=1.0,
    )
    assert meta["stability_breach"] == 0.9
    assert meta["shock_applied"] is True
    assert meta["effective_gain"] > 0.9
    assert state["neg"] == meta["effective_gain"]


@pytest.mark.parametrize(
    ("event", "maturity", "pos"),
    [
        ("attack", 0.5, 1.0),
        ("betrayal", 0.499999, 1.0),
        ("betrayal", 0.5, 0.999999),
    ],
)
def test_breach_requires_betrayal_and_both_thresholds(event, maturity, pos):
    _, meta = event_step(
        record(pos=pos, maturity=maturity),
        defaults(),
        event=event,
        channel="neg",
        base_amount=0.7,
        intensity=1.0,
    )
    assert meta["stability_breach"] == 0.0
    assert meta["shock_applied"] is False


def test_negative_cap_is_enforced():
    r = record(neg=5.0)
    state, _ = event_step(
        r,
        defaults(),
        event="betrayal",
        channel="neg",
        base_amount=0.7,
        intensity=1.0,
    )
    assert state["neg"] == 5.0


def test_zero_maturity_modifier_zeroes_ordinary_gain():
    r = record(maturity=1.0)
    state, meta = event_step(
        r,
        defaults(),
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=1.0,
    )
    assert state["pos"] == 0.0
    assert meta["effective_gain"] == 0.0


def test_maturity_cap_is_enforced():
    r = record(maturity=0.749)
    state, _ = event_step(
        r,
        defaults(),
        event="help",
        channel="pos",
        base_amount=0.12,
        intensity=0.0,
    )
    assert state["maturity"] == 0.75


def test_attachment_delta_is_applied_without_mutating_input():
    r = record(attachment=-0.3)
    frozen = deepcopy(r)
    state, _ = event_step(
        r,
        defaults(),
        event="betrayal",
        channel="neg",
        base_amount=0.7,
        intensity=0.25,
        attachment_delta=-0.125,
    )
    assert r == frozen
    assert state["attachment"] == -0.425


def test_invalid_channel_rejected():
    with pytest.raises(ValueError, match="unsupported channel"):
        event_step(
            record(),
            defaults(),
            event="x",
            channel="bad",
            base_amount=1.0,
            intensity=1.0,
        )


def test_tick_sparse_defaults_and_latent_state_preservation():
    state = tick_step(
        record(
            pos=2.0,
            neg=3.0,
            attachment=4.0,
            maturity=0.5,
            recent_event_magnitude=0.7,
        ),
        defaults(),
    )
    assert state == {
        "pos": 1.94,
        "neg": 2.925,
        "attachment": 4.0,
        "maturity": 0.5,
        "recent_event_magnitude": 0.7,
    }


def test_tick_uses_per_record_decay_overrides():
    state = tick_step(
        record(pos=2.0, neg=3.0, pos_decay=0.5, neg_decay=0.25),
        defaults(),
    )
    assert state["pos"] == 1.0
    assert state["neg"] == 0.75
