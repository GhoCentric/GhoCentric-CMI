from copy import deepcopy
import math

LIVE_FIELDS = ("history_limit", "_sequence", "_profiles", "_history")
SNAPSHOT_KEYS = ("schema_version", "history_limit", "sequence", "profiles", "history")
PROFILE_STORED_KEYS = ("motive_id", "baseline", "weights")
PROFILE_CAUSAL_KEYS = ("baseline", "weights")


def compact_profiles(profiles):
    return {
        agent: {
            motive_id: {
                "baseline": profile["baseline"],
                "weights": deepcopy(profile["weights"]),
            }
            for motive_id, profile in motives.items()
        }
        for agent, motives in profiles.items()
    }


def expand_profiles(compact):
    return {
        agent: {
            motive_id: {
                "motive_id": motive_id,
                "baseline": profile["baseline"],
                "weights": deepcopy(profile["weights"]),
            }
            for motive_id, profile in motives.items()
        }
        for agent, motives in compact.items()
    }


def evaluate_compact(agent, compact, packet, sequence):
    profiles = compact.get(agent, {})
    signals = packet["signals"]
    motives = {}

    for motive_id in sorted(profiles):
        profile = profiles[motive_id]
        contribution_terms = []
        support_terms = []
        opposition_terms = []
        missing = []
        contributions = []

        for signal_name, weight in profile["weights"].items():
            if signal_name in signals:
                signal_value = signals[signal_name]
            else:
                signal_value = 0.0
                missing.append(signal_name)
            contribution = signal_value * weight
            contribution_terms.append(contribution)
            if contribution >= 0.0:
                support_terms.append(contribution)
            else:
                opposition_terms.append(-contribution)
            contributions.append(
                {
                    "signal": signal_name,
                    "signal_value": signal_value,
                    "weight": weight,
                    "contribution": contribution,
                }
            )

        raw = math.fsum([profile["baseline"], *contribution_terms])
        score = min(1.0, max(0.0, raw))
        motives[motive_id] = {
            "motive_id": motive_id,
            "score": score,
            "raw_score": raw,
            "baseline": profile["baseline"],
            "support": math.fsum(support_terms),
            "opposition": math.fsum(opposition_terms),
            "missing_signals": missing,
            "contributions": contributions,
        }

    ranking = sorted(motives, key=lambda name: (-motives[name]["score"], name))
    return {
        "sequence": sequence,
        "agent": agent,
        "signal_packet_version": packet["packet_version"],
        "sources": deepcopy(packet["sources"]),
        "signals": deepcopy(signals),
        "motives": motives,
        "ranking": ranking,
        "dominant_motive": ranking[0] if ranking else None,
        "dominant_score": motives[ranking[0]]["score"] if ranking else None,
    }
