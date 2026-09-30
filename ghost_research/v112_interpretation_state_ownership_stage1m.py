from copy import deepcopy

LIVE_FIELDS = ("history_limit", "_sequence", "_agents")
SNAPSHOT_KEYS = ("schema_version", "history_limit", "sequence", "agents")
AGENT_STORED_KEYS = (
    "levels",
    "baseline",
    "thresholds",
    "sensitivities",
    "rules",
    "active",
    "history",
)
TRANSITION_CAUSAL_KEYS = (
    "levels",
    "thresholds",
    "sensitivities",
    "rules",
    "active",
)
DERIVED_STATE_KEYS = (
    "agent",
    "active_interpretations",
    "strongest_interpretation",
    "strongest_level",
)


def derive_state(agent, stored):
    packet = deepcopy(stored)
    active = [
        dimension
        for dimension in sorted(packet["active"])
        if packet["active"][dimension]
    ]
    strongest = None
    strongest_level = 0.0
    if packet["levels"]:
        strongest = min(
            packet["levels"],
            key=lambda name: (-packet["levels"][name], name),
        )
        strongest_level = packet["levels"][strongest]
        if strongest_level <= 0.0:
            strongest = None
    packet["agent"] = agent
    packet["active_interpretations"] = active
    packet["strongest_interpretation"] = strongest
    packet["strongest_level"] = strongest_level
    return packet


def transition_projection(stored):
    return {
        key: deepcopy(stored[key])
        for key in TRANSITION_CAUSAL_KEYS
    }


def transition_fingerprint(packet):
    state = packet["state"]
    return {
        "sequence": packet["sequence"],
        "contributions": deepcopy(packet["contributions"]),
        "transitions": deepcopy(packet["transitions"]),
        "levels": deepcopy(state["levels"]),
        "active": deepcopy(state["active"]),
        "active_interpretations": deepcopy(
            packet["active_interpretations"]
        ),
        "strongest_interpretation": packet["strongest_interpretation"],
        "strongest_level": packet["strongest_level"],
    }
