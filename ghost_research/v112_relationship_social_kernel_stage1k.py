def social_heat(diagnostics):
    heat = diagnostics.get("severity", 0.0)
    heat += {
        "relationship_broken": 0.30,
        "near_break": 0.20,
        "major_negative_shift": 0.15,
        "state_shift": 0.10,
    }.get(diagnostics.get("pressure"), 0.0)
    if diagnostics.get("direction") == "positive":
        heat *= 0.40
    return max(0.0, min(1.0, heat))


def observer_trust_delta(direction, heat, weight):
    if direction == "negative":
        return -0.20 * heat * weight
    if direction == "positive":
        return 0.05 * heat * weight
    return 0.0


def world_effects(heat):
    return {
        "pressure_delta": 0.20 * heat,
        "fear_delta": 0.08 * heat,
        "resentment_delta": 0.08 * heat,
        "order_delta": -0.04 * heat,
        "guard_suspicion_delta": 0.35 * heat,
    }


def social_delta_step(record, max_reservoir, trust_delta):
    updated = dict(record)
    before_trust = record.get("pos", 0.0) - record.get("neg", 0.0)

    if trust_delta > 0.0:
        updated["pos"] = min(
            max_reservoir,
            record.get("pos", 0.0) + trust_delta,
        )
    elif trust_delta < 0.0:
        updated["neg"] = min(
            max_reservoir,
            record.get("neg", 0.0) + abs(trust_delta),
        )

    after_trust = updated.get("pos", 0.0) - updated.get("neg", 0.0)
    return updated, {
        "before_trust": before_trust,
        "after_trust": after_trust,
        "trust_delta": trust_delta,
    }
