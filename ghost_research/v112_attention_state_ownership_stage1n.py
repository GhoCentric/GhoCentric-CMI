from copy import deepcopy

LIVE_FIELDS = ("history_limit", "_sequence", "_agents")
SNAPSHOT_KEYS = ("schema_version", "history_limit", "sequence", "agents")
AGENT_STORED_KEYS = ("flow_pressure", "flow_active", "config", "history")
TRANSITION_CAUSAL_KEYS = ("flow_pressure", "flow_active", "config")
DERIVED_STATE_KEYS = ("agent", "flow_depth", "attention_gain")


def flow_depth(active, pressure, config):
    if not active:
        return 0.0
    entry = config["entry_threshold"]
    if entry >= 1.0:
        return 1.0
    return min(1.0, max(0.0, (pressure - entry) / (1.0 - entry)))


def attention_gain(active, pressure, config, breakthrough=False):
    if breakthrough or not active:
        return 1.0
    depth = flow_depth(True, pressure, config)
    suppression = config["max_suppression"] * (0.35 + 0.65 * depth)
    return max(0.0, 1.0 - suppression)


def derive_state(agent, stored):
    packet = deepcopy(stored)
    packet["agent"] = agent
    packet["flow_depth"] = flow_depth(
        bool(packet["flow_active"]),
        packet["flow_pressure"],
        packet["config"],
    )
    packet["attention_gain"] = attention_gain(
        bool(packet["flow_active"]),
        packet["flow_pressure"],
        packet["config"],
        False,
    )
    return packet


def transition_projection(stored):
    return {
        key: deepcopy(stored[key])
        for key in TRANSITION_CAUSAL_KEYS
    }
