from copy import deepcopy
import pytest

from ghost.api import GhostAPI


def setup_agent():
    api = GhostAPI()
    agent = api.register_agent("npc", capabilities=["talk", "move"])
    return api, agent


def test_closed_action_handshake_through_bound_agent():
    api, agent = setup_agent()
    aff = agent.set_affordances([
        {"id":"confront", "capability":"talk", "features":{}},
        {"id":"leave", "capability":"move", "features":{}},
    ], context={"scene":"market"})
    decision = agent.choose_action(
        {"leave":0.1, "confront":0.9}, policy_id="stage1_policy", context={"reason":"test"}
    )
    assert decision["affordance_sequence"] == aff["sequence"]
    assert decision["candidate_id"] == "confront"
    assert agent.pending_action() == decision
    assert "actions" not in agent.state()["layers"]
    with pytest.raises(ValueError, match="cannot replace affordances"):
        agent.set_affordances(["move"])
    with pytest.raises(ValueError, match="cannot replace affordances"):
        agent.clear_affordances()
    result = agent.resolve_action(decision["decision_id"], "interrupted", outcome={"cause":"guard"})
    assert result["status"] == "interrupted"
    assert agent.pending_action() is None
    assert agent.action_history() == [result]
    agent.clear_affordances()


def test_choose_requires_current_affordances_and_registered_agent():
    api, agent = setup_agent()
    with pytest.raises(ValueError, match="current affordance"):
        agent.choose_action({})
    from ghost.agent import GhostAgent
    ghost = GhostAgent(api, "missing")
    with pytest.raises(ValueError, match="registered"):
        ghost.choose_action({})


def test_api_snapshot_roundtrip_pending_and_resolved_actions():
    api, agent = setup_agent()
    agent.set_affordances([{"id":"confront","capability":"talk","features":{}}])
    d = agent.choose_action({"confront": 1})
    pending_snapshot = api.snapshot()
    restored = GhostAPI.from_snapshot(pending_snapshot)
    assert restored.agent("npc").pending_action() == d
    restored.agent("npc").resolve_action(d["decision_id"], "succeeded", outcome={"ok":True})
    resolved_snapshot = restored.snapshot()
    roundtrip = GhostAPI.from_snapshot(resolved_snapshot)
    assert roundtrip.agent("npc").pending_action() is None
    assert roundtrip.agent("npc").action_history()[0]["status"] == "succeeded"


def test_v111_snapshot_without_actions_remains_compatible():
    api, agent = setup_agent()
    agent.set_affordances([{"id":"confront","capability":"talk","features":{}}])
    snap = api.snapshot()
    snap.pop("actions", None)
    restored = GhostAPI.from_snapshot(snap)
    assert restored.actions.has_state() is False
    assert restored.agent("npc").pending_action() is None


def test_snapshot_rejects_action_owner_without_registered_agent():
    api, agent = setup_agent()
    agent.set_affordances([{"id":"confront","capability":"talk","features":{}}])
    agent.choose_action({"confront":1})
    snap = api.snapshot()
    snap["actions"]["agents"]["orphan"] = snap["actions"]["agents"].pop("npc")
    snap["actions"]["agents"]["orphan"]["pending"]["agent"] = "orphan"
    with pytest.raises(ValueError, match="action agent must reference a registered agent"):
        GhostAPI.from_snapshot(snap)


def test_snapshot_rejects_stale_pending_affordance_and_candidate():
    api, agent = setup_agent()
    agent.set_affordances([{"id":"confront","capability":"talk","features":{}}])
    agent.choose_action({"confront":1})
    snap = api.snapshot()
    bad = deepcopy(snap)
    bad["actions"]["agents"]["npc"]["pending"]["affordance_sequence"] += 1
    with pytest.raises(ValueError, match="current affordance set"):
        GhostAPI.from_snapshot(bad)
    bad = deepcopy(snap)
    bad["affordances"]["history"]["npc"][-1]["candidates"][0]["id"] = "other"
    with pytest.raises(ValueError, match="current affordance candidate"):
        GhostAPI.from_snapshot(bad)


def test_restore_snapshot_rebinds_actions_runtime():
    api, agent = setup_agent()
    agent.set_affordances([{"id":"confront","capability":"talk","features":{}}])
    d=agent.choose_action({"confront":1})
    snap=api.snapshot()
    other=GhostAPI()
    restored=other.restore_snapshot(snap)
    assert restored["actions"]["agents"]["npc"]["pending"]["decision_id"] == d["decision_id"]
    assert other.agent("npc").pending_action()["decision_id"] == d["decision_id"]
