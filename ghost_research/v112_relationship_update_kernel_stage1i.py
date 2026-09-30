PARAM_NAMES = (
    "pos_gain", "neg_gain", "pos_decay", "neg_decay", "positive_reservoir_cap",
    "betrayal_shock_maturity_threshold", "betrayal_shock_positive_threshold",
    "betrayal_stability_breach_fraction", "stability_shock_maturity_threshold",
    "stability_shock_positive_threshold", "high_severity_threshold",
    "high_severity_shock_bonus", "severe_negative_maturity_floor",
    "relative_shock_ratio", "relative_shock_bonus", "recent_event_decay",
    "volatility", "positive_volatility", "negative_volatility",
    "maturity_gain", "maturity_cap",
)


def resolve_params(record, defaults):
    return {name: record.get(name, defaults[name]) for name in PARAM_NAMES}


def event_step(
    record, defaults, *, event, channel, base_amount, intensity, attachment_delta=0.0
):
    p = resolve_params(record, defaults)
    max_reservoir = defaults["max_reservoir"]
    pos, neg = record.get("pos", 0.0), record.get("neg", 0.0)
    maturity = record.get("maturity", 0.0)
    recent = record.get("recent_event_magnitude", 0.0)
    amount = base_amount * intensity
    maturity_modifier = max(0.0, 1.0 - maturity)
    event_maturity_modifier = maturity_modifier
    shock_multiplier = 1.0
    high_severity_shock = relative_shock = shock_applied = False
    stability_breach = 0.0

    if channel == "pos":
        cap = min(p["positive_reservoir_cap"], max_reservoir)
        resistance = 1.0 / (1.0 + (neg * 0.35))
        saturation = max(0.0, 1.0 - (pos / cap))
        gain = amount * p["pos_gain"]
        gain *= p["volatility"]
        gain *= p["positive_volatility"]
        gain *= maturity_modifier
        gain *= resistance
        gain *= saturation
        effective_gain = gain
        pos = min(cap, pos + gain)
    elif channel == "neg":
        saturation = max(0.0, 1.0 - (neg / max_reservoir))
        shock_eligible = (
            maturity >= p["stability_shock_maturity_threshold"]
            and pos >= p["stability_shock_positive_threshold"]
        )
        if shock_eligible:
            if amount >= p["high_severity_threshold"]:
                high_severity_shock = True
                shock_multiplier += p["high_severity_shock_bonus"]
                event_maturity_modifier = max(
                    maturity_modifier, p["severe_negative_maturity_floor"]
                )
            if recent > 0.0 and amount >= recent * p["relative_shock_ratio"]:
                relative_shock = True
                shock_multiplier += p["relative_shock_bonus"]
        gain = amount * p["neg_gain"]
        gain *= p["volatility"]
        gain *= p["negative_volatility"]
        gain *= event_maturity_modifier
        gain *= saturation
        gain *= shock_multiplier
        if (
            event == "betrayal"
            and maturity >= p["betrayal_shock_maturity_threshold"]
            and pos >= p["betrayal_shock_positive_threshold"]
        ):
            stability_breach = pos * p["betrayal_stability_breach_fraction"]
            shock_applied = True
        effective_gain = gain + stability_breach
        neg = min(max_reservoir, neg + gain + stability_breach)
    else:
        raise ValueError(f"unsupported channel: {channel!r}")

    recent_decay = p["recent_event_decay"]
    state = {
        "pos": pos, "neg": neg,
        "attachment": record.get("attachment", 0.0) + attachment_delta,
        "maturity": min(p["maturity_cap"], maturity + p["maturity_gain"]),
        "recent_event_magnitude": recent * recent_decay + amount * (1.0 - recent_decay),
    }
    metadata = {
        "amount": amount, "effective_gain": effective_gain,
        "maturity_modifier": maturity_modifier,
        "event_maturity_modifier": event_maturity_modifier,
        "shock_applied": shock_applied, "stability_breach": stability_breach,
        "high_severity_shock": high_severity_shock,
        "relative_shock": relative_shock, "shock_multiplier": shock_multiplier,
        "recent_event_magnitude": recent,
    }
    return state, metadata


def tick_step(record, defaults):
    p = resolve_params(record, defaults)
    return {
        "pos": record.get("pos", 0.0) * p["pos_decay"],
        "neg": record.get("neg", 0.0) * p["neg_decay"],
        "attachment": record.get("attachment", 0.0),
        "maturity": record.get("maturity", 0.0),
        "recent_event_magnitude": record.get("recent_event_magnitude", 0.0),
    }
