from copy import deepcopy

from ghost_research.v112_continuity_state_ownership_stage1p import (
    AGENT_STORED_KEYS,
    DERIVED_PUBLIC_KEYS,
    bounded_positive_update,
    derive_public_state,
    foreground_step,
    ingest_step,
    pairwise_advantage,
    raw_leader,
    recall_step,
    tick_step,
)


def state(**updates):
    value = {
        "release_rate": 0.1,
        "switch_threshold": 0.25,
        "current_leader": None,
        "activation": {},
    }
    value.update(updates)
    return value


def test_contract_constants():
    assert AGENT_STORED_KEYS == (
        "release_rate",
        "switch_threshold",
        "current_leader",
        "activation",
    )
    assert DERIVED_PUBLIC_KEYS == ("agent",)


def test_derive_public_state_sorted_and_isolated():
    source = state(activation={"z": 0.2, "a": 0.4})
    frozen = deepcopy(source)
    packet = derive_public_state("npc", source)
    assert list(packet["activation"]) == ["a", "z"]
    packet["activation"]["a"] = 0.0
    assert source == frozen


def test_bounded_positive_update():
    assert bounded_positive_update(0.25, 0.4) == 0.55


def test_recall_step_new_dimension_and_isolated():
    source = state()
    updated, packet = recall_step(source, "threat", 0.5)
    assert updated["activation"]["threat"] == 0.5
    assert packet["activation_before"] == 0.0
    assert source["activation"] == {}


def test_ingest_step_sorted_and_negative_impulse():
    source = state()
    updated, rows = ingest_step(
        source,
        {
            "threat": {"level_after": 0.8, "effective_impulse": -0.4},
            "respect": {"level_after": 0.6, "effective_impulse": 0.2},
        },
    )
    assert [row["dimension"] for row in rows] == ["respect", "threat"]
    assert updated["activation"]["threat"] == 0.4
    assert rows[1]["relevance_impulse"] == 0.4


def test_tick_step():
    updated, packet = tick_step(
        state(release_rate=0.2, activation={"x": 0.5}),
        2,
    )
    assert abs(updated["activation"]["x"] - 0.32) < 1e-15
    assert packet["activation_before"] == {"x": 0.5}


def test_raw_leader_empty_zero_and_tie():
    assert raw_leader({}) == (None, 0.0)
    assert raw_leader({"b": 0.0, "a": 0.0}) == (None, 0.0)
    assert raw_leader({"b": 0.5, "a": 0.5}) == ("a", 0.5)


def test_pairwise_advantage_zero_and_regular():
    assert pairwise_advantage(0.0, 0.0) == 0.0
    assert abs(pairwise_advantage(0.6, 0.4) - 0.2) < 1e-15


def test_foreground_zero_acquire_and_hold():
    source = state()
    updated, packet = foreground_step(source, 1, {})
    assert updated["current_leader"] is None
    assert packet["reason"] == "zero_vector"

    updated, packet = foreground_step(source, 2, {"b": 0.4, "a": 0.6})
    assert updated["current_leader"] == "a"
    assert packet["reason"] == "acquired"

    held, packet = foreground_step(updated, 3, {"a": 0.7, "b": 0.3})
    assert held["current_leader"] == "a"
    assert packet["reason"] == "leader_holds"


def test_foreground_inactive_threshold_and_hysteresis():
    inactive = state(current_leader="a", switch_threshold=0.25)
    switched, packet = foreground_step(inactive, 1, {"a": 0.0, "b": 0.4})
    assert switched["current_leader"] == "b"
    assert packet["reason"] == "incumbent_inactive"

    crossed, packet = foreground_step(
        state(current_leader="a", switch_threshold=0.1),
        2,
        {"a": 0.4, "b": 0.6},
    )
    assert crossed["current_leader"] == "b"
    assert packet["reason"] == "threshold_crossed"

    retained, packet = foreground_step(
        state(current_leader="a", switch_threshold=0.3),
        3,
        {"a": 0.4, "b": 0.6},
    )
    assert retained["current_leader"] == "a"
    assert packet["reason"] == "hysteresis_retained"
