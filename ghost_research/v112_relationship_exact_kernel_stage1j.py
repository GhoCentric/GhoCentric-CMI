PARAM_NAMES = (
    "apology_recovery_fraction",
    "recent_event_decay",
    "maturity_gain",
    "maturity_cap",
    "volatility",
    "positive_volatility",
    "negative_volatility",
)


def resolve_exact_params(record, defaults):
    return {name: record.get(name, defaults[name]) for name in PARAM_NAMES}


def exact_step(record, defaults, *, event, intensity, spec):
    p = resolve_exact_params(record, defaults)
    updated = dict(record)
    before_trust = record.get("pos", 0.0) - record.get("neg", 0.0)
    requested_delta = spec["trust"] * intensity

    if event == "apology":
        if before_trust >= 0.0:
            trust_delta = 0.0
        else:
            trust_delta = min(
                requested_delta,
                -before_trust * spec.get(
                    "recovery_fraction",
                    p["apology_recovery_fraction"],
                ),
            )
    else:
        trust_delta = requested_delta

    if trust_delta > 0.0:
        updated["pos"] = record.get("pos", 0.0) + trust_delta
        channel = "pos"
    elif trust_delta < 0.0:
        updated["neg"] = record.get("neg", 0.0) + abs(trust_delta)
        channel = "neg"
    else:
        channel = "pos" if spec["trust"] >= 0.0 else "neg"

    attachment_delta = spec.get("attachment", 0.0) * intensity
    if attachment_delta != 0.0:
        updated["attachment"] = record.get("attachment", 0.0) + attachment_delta

    for key, value in spec.get("extra_deltas", {}).items():
        updated[key] = record.get(key, 0.0) + value * intensity

    maturity = record.get("maturity", 0.0)
    recent = record.get("recent_event_magnitude", 0.0)
    updated["recent_event_magnitude"] = (
        recent * p["recent_event_decay"]
        + abs(requested_delta) * (1.0 - p["recent_event_decay"])
    )
    updated["maturity"] = min(
        p["maturity_cap"],
        maturity + p["maturity_gain"],
    )
    after_trust = updated.get("pos", 0.0) - updated.get("neg", 0.0)
    metadata = {
        "requested_delta": requested_delta,
        "trust_delta": trust_delta,
        "channel": channel,
        "base_amount": abs(spec["trust"]),
        "before_trust": before_trust,
        "after_trust": after_trust,
        "maturity": maturity,
        "maturity_modifier": max(0.0, 1.0 - maturity),
        "volatility": p["volatility"],
        "positive_volatility": p["positive_volatility"],
        "negative_volatility": p["negative_volatility"],
        "recent_event_magnitude": recent,
    }
    return updated, metadata
