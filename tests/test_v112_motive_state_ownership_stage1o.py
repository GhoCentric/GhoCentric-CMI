from copy import deepcopy

from ghost_research.v112_motive_state_ownership_stage1o import (
    LIVE_FIELDS,
    PROFILE_CAUSAL_KEYS,
    PROFILE_STORED_KEYS,
    SNAPSHOT_KEYS,
    compact_profiles,
    evaluate_compact,
    expand_profiles,
)


def packet(agent="npc", signals=None):
    return {
        "packet_version": "1.0",
        "agent": agent,
        "signals": {} if signals is None else deepcopy(signals),
        "sources": {
            "traits": {"count": 0},
            "values": {"count": 0},
            "goals": {"count": 0},
            "persistent_salience": {
                "present": False,
                "count": 0,
                "source_count": 0,
            },
            "attention": {
                "present": False,
                "count": 0,
                "attended_count": 0,
                "revision": None,
            },
        },
    }


def profiles():
    return {
        "npc": {
            "protect": {
                "motive_id": "protect",
                "baseline": 0.1,
                "weights": {"x": 0.5, "missing": 0.2},
            },
            "withdraw": {
                "motive_id": "withdraw",
                "baseline": 0.4,
                "weights": {"x": -0.5},
            },
        }
    }


def test_contract_constants():
    assert LIVE_FIELDS == ("history_limit", "_sequence", "_profiles", "_history")
    assert SNAPSHOT_KEYS == (
        "schema_version",
        "history_limit",
        "sequence",
        "profiles",
        "history",
    )
    assert PROFILE_STORED_KEYS == ("motive_id", "baseline", "weights")
    assert PROFILE_CAUSAL_KEYS == ("baseline", "weights")


def test_compact_expand_exact():
    full = profiles()
    assert expand_profiles(compact_profiles(full)) == full


def test_compact_profiles_isolated():
    full = profiles()
    frozen = deepcopy(full)
    compact = compact_profiles(full)
    compact["npc"]["protect"]["weights"]["x"] = 0.9
    assert full == frozen


def test_expand_profiles_isolated():
    compact = compact_profiles(profiles())
    frozen = deepcopy(compact)
    expanded = expand_profiles(compact)
    expanded["npc"]["protect"]["weights"]["x"] = 0.9
    assert compact == frozen


def test_evaluate_empty_profiles():
    result = evaluate_compact("npc", {}, packet(), 4)
    assert result["sequence"] == 4
    assert result["motives"] == {}
    assert result["ranking"] == []
    assert result["dominant_motive"] is None
    assert result["dominant_score"] is None


def test_evaluate_scores_missing_ranking_and_opposition():
    compact = compact_profiles(profiles())
    result = evaluate_compact("npc", compact, packet(signals={"x": 0.8}), 7)
    assert result["ranking"] == ["protect", "withdraw"]
    assert result["dominant_motive"] == "protect"
    assert result["motives"]["protect"]["score"] == 0.5
    assert result["motives"]["protect"]["missing_signals"] == ["missing"]
    assert result["motives"]["withdraw"]["opposition"] == 0.4


def test_evaluate_clamps_and_isolates_packet():
    full = {
        "npc": {
            "high": {
                "motive_id": "high",
                "baseline": 0.9,
                "weights": {"x": 1.0},
            },
            "low": {
                "motive_id": "low",
                "baseline": 0.1,
                "weights": {"x": -1.0},
            },
        }
    }
    compact = compact_profiles(full)
    source = packet(signals={"x": 1.0})
    frozen = deepcopy(source)
    result = evaluate_compact("npc", compact, source, 3)
    assert result["motives"]["high"]["score"] == 1.0
    assert result["motives"]["low"]["score"] == 0.0
    result["sources"]["traits"]["count"] = 9
    assert source == frozen
