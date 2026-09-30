from copy import deepcopy

from ghost_research.v112_interpretation_state_ownership_stage1m import (
    AGENT_STORED_KEYS,
    DERIVED_STATE_KEYS,
    LIVE_FIELDS,
    SNAPSHOT_KEYS,
    TRANSITION_CAUSAL_KEYS,
    derive_state,
    transition_fingerprint,
    transition_projection,
)


def _stored(levels=None, active=None):
    levels = {} if levels is None else levels
    active = {} if active is None else active
    return {
        "levels": deepcopy(levels),
        "baseline": {name: 0.0 for name in levels},
        "thresholds": {
            name: {"enter": 0.65, "exit": 0.5}
            for name in levels
        },
        "sensitivities": {name: 1.0 for name in levels},
        "rules": {},
        "active": deepcopy(active),
        "history": [],
    }


def test_contract_constants():
    assert LIVE_FIELDS == ("history_limit", "_sequence", "_agents")
    assert SNAPSHOT_KEYS == (
        "schema_version",
        "history_limit",
        "sequence",
        "agents",
    )
    assert len(AGENT_STORED_KEYS) == 7
    assert len(TRANSITION_CAUSAL_KEYS) == 5
    assert len(DERIVED_STATE_KEYS) == 4


def test_derive_empty_state():
    packet = derive_state("npc", _stored())
    assert packet["agent"] == "npc"
    assert packet["active_interpretations"] == []
    assert packet["strongest_interpretation"] is None
    assert packet["strongest_level"] == 0.0


def test_derive_zero_level_state():
    packet = derive_state("npc", _stored({"threat": 0.0}, {"threat": False}))
    assert packet["strongest_interpretation"] is None
    assert packet["strongest_level"] == 0.0


def test_derive_active_and_tie_break():
    packet = derive_state(
        "npc",
        _stored(
            {"threat": 0.7, "betrayal": 0.7, "respect": 0.2},
            {"threat": True, "betrayal": True, "respect": False},
        ),
    )
    assert packet["active_interpretations"] == ["betrayal", "threat"]
    assert packet["strongest_interpretation"] == "betrayal"
    assert packet["strongest_level"] == 0.7


def test_derive_state_is_input_isolated():
    stored = _stored({"threat": 0.7}, {"threat": True})
    frozen = deepcopy(stored)
    packet = derive_state("npc", stored)
    packet["levels"]["threat"] = 0.0
    assert stored == frozen


def test_transition_projection_is_exact_subset_and_isolated():
    stored = _stored({"threat": 0.7}, {"threat": True})
    projected = transition_projection(stored)
    assert tuple(projected) == TRANSITION_CAUSAL_KEYS
    projected["levels"]["threat"] = 0.0
    assert stored["levels"]["threat"] == 0.7


def test_transition_fingerprint():
    packet = {
        "sequence": 4,
        "contributions": [{"contribution": 0.2}],
        "transitions": {"threat": {"transition": "entered"}},
        "state": {
            "levels": {"threat": 0.7},
            "active": {"threat": True},
        },
        "active_interpretations": ["threat"],
        "strongest_interpretation": "threat",
        "strongest_level": 0.7,
    }
    frozen = deepcopy(packet)
    result = transition_fingerprint(packet)
    assert result["sequence"] == 4
    assert result["levels"] == {"threat": 0.7}
    result["contributions"][0]["contribution"] = 9.0
    assert packet == frozen
