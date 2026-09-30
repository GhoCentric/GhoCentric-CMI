from copy import deepcopy

import pytest

from ghost_research.v112_attention_state_ownership_stage1n import (
    AGENT_STORED_KEYS,
    DERIVED_STATE_KEYS,
    LIVE_FIELDS,
    SNAPSHOT_KEYS,
    TRANSITION_CAUSAL_KEYS,
    attention_gain,
    derive_state,
    flow_depth,
    transition_projection,
)


def config(**updates):
    value = {
        "entry_threshold": 0.72,
        "exit_threshold": 0.44,
        "build_rate": 0.26,
        "release_rate": 0.48,
        "interrupt_threshold": 0.72,
        "interrupt_release": 0.82,
        "max_suppression": 0.96,
    }
    value.update(updates)
    return value


def stored(**updates):
    value = {
        "flow_pressure": 0.0,
        "flow_active": False,
        "config": config(),
        "history": [],
    }
    value.update(updates)
    return value


def test_contract_constants():
    assert LIVE_FIELDS == ("history_limit", "_sequence", "_agents")
    assert SNAPSHOT_KEYS == ("schema_version", "history_limit", "sequence", "agents")
    assert AGENT_STORED_KEYS == (
        "flow_pressure",
        "flow_active",
        "config",
        "history",
    )
    assert TRANSITION_CAUSAL_KEYS == (
        "flow_pressure",
        "flow_active",
        "config",
    )
    assert DERIVED_STATE_KEYS == ("agent", "flow_depth", "attention_gain")


def test_flow_depth_inactive_and_entry_one():
    assert flow_depth(False, 0.9, config()) == 0.0
    assert flow_depth(True, 1.0, config(entry_threshold=1.0)) == 1.0


def test_flow_depth_regular_and_clamped():
    assert flow_depth(True, 0.86, config()) == pytest.approx(0.5)
    assert flow_depth(True, 0.2, config()) == 0.0
    assert flow_depth(True, 1.0, config()) == 1.0


def test_attention_gain_breakthrough_or_inactive():
    assert attention_gain(True, 0.9, config(), True) == 1.0
    assert attention_gain(False, 0.9, config(), False) == 1.0


def test_attention_gain_active():
    assert attention_gain(True, 0.72, config()) == pytest.approx(0.664)
    assert attention_gain(True, 1.0, config()) == pytest.approx(0.04)


def test_derive_state_exact_and_isolated():
    source = stored(flow_pressure=0.86, flow_active=True)
    frozen = deepcopy(source)
    packet = derive_state("npc", source)
    assert packet["agent"] == "npc"
    assert packet["flow_depth"] == pytest.approx(0.5)
    assert packet["attention_gain"] == pytest.approx(0.352)
    packet["config"]["build_rate"] = 0.9
    assert source == frozen


def test_transition_projection_exact_subset_and_isolated():
    source = stored(flow_pressure=0.6, flow_active=True)
    projected = transition_projection(source)
    assert tuple(projected) == TRANSITION_CAUSAL_KEYS
    projected["config"]["build_rate"] = 0.9
    assert source["config"]["build_rate"] == 0.26
