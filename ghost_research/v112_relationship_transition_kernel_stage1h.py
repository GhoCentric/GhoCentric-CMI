_TRIGGER_PRESSURE = {
    "relationship_broken": "relationship_broken",
    "deescalation": "deescalating",
    "forgiveness": "forgiveness",
    "state_shift": "state_shift",
}


def classify_state(trust: float) -> str:
    if trust <= -0.55:
        return "hostile"
    if trust >= 0.08:
        return "friendly"
    return "neutral"


def transition_for_states(before: str, after: str):
    if before == after:
        return None, None
    if after == "hostile":
        event = "relationship_broken"
    elif before == "hostile" and after == "neutral":
        event = "deescalation"
    elif before in ("hostile", "neutral") and after == "friendly":
        event = "forgiveness"
    else:
        event = "state_shift"
    return (before, after), {"event": event}


def transition_metadata(before_state: str, after_trust: float):
    after_state = classify_state(after_trust)
    transition, trigger = transition_for_states(before_state, after_state)
    return after_state, transition, trigger


def pressure_label(trigger, delta: float, after_state: str, after_trust: float) -> str:
    if after_state == "neutral" and -0.55 < after_trust <= -0.45:
        return "near_break"
    event = trigger.get("event") if trigger else None
    if event in _TRIGGER_PRESSURE:
        return _TRIGGER_PRESSURE[event]
    if delta <= -0.50:
        return "major_negative_shift"
    if delta <= -0.20:
        return "negative_shift"
    if delta >= 0.20:
        return "positive_shift"
    if delta >= 0.005:
        return "minor_positive_shift"
    if delta <= -0.005:
        return "minor_negative_shift"
    return "stable"


def direction_label(delta: float) -> str:
    if delta > 0.0:
        return "positive"
    if delta < 0.0:
        return "negative"
    return "stable"
