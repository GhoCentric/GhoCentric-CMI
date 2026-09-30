import pytest

from ghost_research.v112_relationship_transition_kernel_stage1h import (
    classify_state,
    direction_label,
    pressure_label,
    transition_for_states,
    transition_metadata,
)


@pytest.mark.parametrize(
    ("trust", "expected"),
    [
        (-0.550001, "hostile"),
        (-0.55, "hostile"),
        (-0.549999, "neutral"),
        (0.079999, "neutral"),
        (0.08, "friendly"),
        (0.080001, "friendly"),
    ],
)
def test_classify_state_boundaries(trust, expected):
    assert classify_state(trust) == expected


@pytest.mark.parametrize(
    ("before", "after", "transition", "trigger"),
    [
        ("hostile", "hostile", None, None),
        ("neutral", "neutral", None, None),
        ("friendly", "friendly", None, None),
        ("neutral", "hostile", ("neutral", "hostile"), {"event": "relationship_broken"}),
        ("friendly", "hostile", ("friendly", "hostile"), {"event": "relationship_broken"}),
        ("hostile", "neutral", ("hostile", "neutral"), {"event": "deescalation"}),
        ("hostile", "friendly", ("hostile", "friendly"), {"event": "forgiveness"}),
        ("neutral", "friendly", ("neutral", "friendly"), {"event": "forgiveness"}),
        ("friendly", "neutral", ("friendly", "neutral"), {"event": "state_shift"}),
    ],
)
def test_transition_matrix(before, after, transition, trigger):
    assert transition_for_states(before, after) == (transition, trigger)


@pytest.mark.parametrize(
    ("trigger", "delta", "state", "trust", "expected"),
    [
        (None, 0.0, "neutral", -0.50, "near_break"),
        ({"event": "relationship_broken"}, 0.0, "hostile", -0.7, "relationship_broken"),
        ({"event": "deescalation"}, 0.0, "neutral", -0.2, "deescalating"),
        ({"event": "forgiveness"}, 0.0, "friendly", 0.2, "forgiveness"),
        ({"event": "state_shift"}, 0.0, "neutral", 0.0, "state_shift"),
        ({"event": "unknown"}, -0.50, "hostile", -1.0, "major_negative_shift"),
        (None, -0.20, "hostile", -1.0, "negative_shift"),
        (None, 0.20, "friendly", 0.4, "positive_shift"),
        (None, 0.005, "friendly", 0.1, "minor_positive_shift"),
        (None, -0.005, "neutral", 0.0, "minor_negative_shift"),
        (None, 0.0, "neutral", 0.0, "stable"),
    ],
)
def test_pressure_precedence(trigger, delta, state, trust, expected):
    assert pressure_label(trigger, delta, state, trust) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(1.0, "positive"), (-1.0, "negative"), (0.0, "stable")],
)
def test_direction(delta, expected):
    assert direction_label(delta) == expected


def test_transition_metadata_combines_classification_and_transition():
    assert transition_metadata("neutral", -0.55) == (
        "hostile",
        ("neutral", "hostile"),
        {"event": "relationship_broken"},
    )
    assert transition_metadata("hostile", -0.2) == (
        "neutral",
        ("hostile", "neutral"),
        {"event": "deescalation"},
    )
    assert transition_metadata("neutral", 0.08) == (
        "friendly",
        ("neutral", "friendly"),
        {"event": "forgiveness"},
    )
