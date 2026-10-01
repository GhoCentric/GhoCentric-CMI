from copy import deepcopy

AGENT_STORED_KEYS = (
    "release_rate",
    "switch_threshold",
    "current_leader",
    "activation",
)
DERIVED_PUBLIC_KEYS = ("agent",)


def derive_public_state(agent, stored):
    return {
        "agent": agent,
        "release_rate": stored["release_rate"],
        "activation": deepcopy(dict(sorted(stored["activation"].items()))),
        "current_leader": stored["current_leader"],
        "switch_threshold": stored["switch_threshold"],
    }


def bounded_positive_update(current, impulse):
    return current + impulse * (1.0 - current)


def recall_step(stored, dimension, strength):
    out = deepcopy(stored)
    before = out["activation"].get(dimension, 0.0)
    after = bounded_positive_update(before, strength)
    out["activation"][dimension] = after
    packet = {
        "cause": "memory_recall",
        "dimension": dimension,
        "retrieval_strength": strength,
        "activation_before": before,
        "activation_after": after,
    }
    return out, packet


def ingest_step(stored, transitions):
    out = deepcopy(stored)
    rows = []
    for dimension in sorted(transitions):
        transition = transitions[dimension]
        meaning = transition["level_after"]
        effective = transition["effective_impulse"]
        cause = abs(effective)
        before = out["activation"].get(dimension, 0.0)
        after = bounded_positive_update(before, cause)
        out["activation"][dimension] = after
        rows.append(
            {
                "cause": "interpretation_update",
                "dimension": dimension,
                "meaning": meaning,
                "effective_impulse": effective,
                "relevance_impulse": cause,
                "activation_before": before,
                "activation_after": after,
            }
        )
    return out, rows


def tick_step(stored, steps):
    out = deepcopy(stored)
    before = deepcopy(out["activation"])
    retention = (1.0 - out["release_rate"]) ** steps
    for dimension in sorted(out["activation"]):
        out["activation"][dimension] *= retention
    packet = {
        "cause": "time",
        "steps": steps,
        "activation_before": before,
        "activation_after": deepcopy(dict(sorted(out["activation"].items()))),
    }
    return out, packet


def raw_leader(values):
    if not values:
        return None, 0.0
    name = min(values, key=lambda key: (-values[key], key))
    value = values[name]
    return (None, 0.0) if value <= 0.0 else (name, value)


def pairwise_advantage(challenger, incumbent):
    total = challenger + incumbent
    if total <= 0.0:
        return 0.0
    return (challenger - incumbent) / total


def foreground_step(stored, tick, attended_salience):
    out = deepcopy(stored)
    values = dict(sorted(attended_salience.items()))
    raw, raw_value = raw_leader(values)
    previous = out["current_leader"]
    advantage = 0.0
    if raw is None:
        resolved = None
        reason = "zero_vector"
    elif previous is None or previous not in values:
        resolved = raw
        reason = "acquired"
    else:
        incumbent_value = values[previous]
        if incumbent_value <= 0.0:
            resolved = raw
            reason = "incumbent_inactive"
        elif raw == previous:
            resolved = previous
            reason = "leader_holds"
        else:
            advantage = pairwise_advantage(raw_value, incumbent_value)
            if advantage + 1e-12 >= out["switch_threshold"]:
                resolved = raw
                reason = "threshold_crossed"
            else:
                resolved = previous
                reason = "hysteresis_retained"
    out["current_leader"] = resolved
    packet = {
        "computed_at_tick": tick,
        "threshold": out["switch_threshold"],
        "previous_leader": previous,
        "raw_leader": raw,
        "raw_leader_salience": raw_value,
        "resolved_leader": resolved,
        "resolved_leader_salience": values.get(resolved, 0.0) if resolved else 0.0,
        "pairwise_advantage": advantage,
        "reason": reason,
        "attended_salience": deepcopy(values),
    }
    return out, packet
