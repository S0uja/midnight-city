"""Social Context Engine for Midnight City.

Fast deterministic layer: discovers social opportunities, filters interactions
by place/state/history, prevents double-booking and lets the target counter-offer.
Romantic thresholds come from ai_constants.
"""
from __future__ import annotations

from ai_constants import (
    ROMANTIC_CONTEXT_BOOST,
    ROMANTIC_THRESHOLDS,
    meets_romantic,
)

PLACE_RULES = {
    "College": {
        "study_together": 1.0, "ask_advice": 0.9, "small_talk": 0.85, "joke": 0.7,
        "flirt": 0.35, "eat_together": 0.3,
    },
    "Cafe": {
        "argue": 0.45, "serious_argument": 0.18, "eat_together": 1.0, "small_talk": 0.95,
        "ask_about_day": 0.9, "joke": 0.8, "flirt": 0.55, "walk_together": 0.25,
        "date": 0.95, "romantic_conversation": 0.7, "compliment": 0.7, "move_in_together": 0.55,
    },
    "Apartments": {
        "argue": 0.55, "serious_argument": 0.25, "small_talk": 0.9, "eat_together": 0.95,
        "watch_together": 0.8, "invite_home": 1.0, "flirt": 0.7, "ask_about_day": 0.85,
        "romantic_conversation": 0.9, "hug": 0.95, "kiss": 0.95, "intimacy": 1.0,
        "move_in_together": 0.95,
    },
    "Park": {
        "argue": 0.25, "serious_argument": 0.10, "walk_together": 1.0, "small_talk": 0.9,
        "joke": 0.85, "flirt": 0.65, "eat_together": 0.25, "date": 0.95,
        "romantic_conversation": 0.75, "hug": 0.65, "kiss": 0.45, "move_in_together": 0.45,
    },
    "Rooftop": {
        "small_talk": 0.9, "walk_together": 0.7, "flirt": 0.65, "joke": 0.85, "date": 0.8,
        "romantic_conversation": 0.8, "hug": 0.7, "kiss": 0.55, "move_in_together": 0.45,
    },
    "Beach": {
        "walk_together": 1.0, "small_talk": 0.9, "flirt": 0.7, "eat_together": 0.35,
        "date": 0.95, "romantic_conversation": 0.8, "hug": 0.75, "kiss": 0.55,
        "move_in_together": 0.45,
    },
    "Studio": {"offer_help": 1.0, "ask_advice": 0.9, "small_talk": 0.65, "joke": 0.45},
    "Downtown": {
        "argue": 0.35, "serious_argument": 0.12, "small_talk": 0.8, "walk_together": 0.85,
        "eat_together": 0.5, "joke": 0.7,
    },
    "Night Club": {
        "small_talk": 1.0, "joke": 0.9, "flirt": 0.9, "walk_together": 0.45, "date": 0.75,
        "romantic_conversation": 0.75, "hug": 0.6, "kiss": 0.5, "move_in_together": 0.35,
    },
}

COOLDOWNS = {
    "greet": 30, "small_talk": 60, "joke": 90, "ask_about_day": 120,
    "eat_together": 120, "walk_together": 150, "flirt": 180, "compliment": 120,
    "romantic_conversation": 240, "date": 720, "hug": 240, "kiss": 480,
    "intimacy": 1440, "move_in_together": 10080,
    "gossip": 240, "invite_home": 360, "argue": 180, "serious_argument": 360,
    "apologize": 180, "make_up": 180,
}

ROMANTIC_KINDS = frozenset(ROMANTIC_THRESHOLDS.keys())


def pair_key(a, b):
    return "::".join(sorted((str(a), str(b))))


def active_lock(state, a, b):
    locks = state.get("social_locks", {})
    return locks.get(pair_key(a, b))


def set_lock(state, a, b, interaction, until):
    state.setdefault("social_locks", {})[pair_key(a, b)] = {
        "initiator": a, "target": b, "interaction": interaction, "until": int(until),
    }


def clear_expired(state, now):
    locks = state.setdefault("social_locks", {})
    for k, v in list(locks.items()):
        if int(v.get("until", 0)) <= int(now):
            locks.pop(k, None)


def recent_time(actor, target_id, kind):
    for item in reversed(actor.get("social_history", []) or []):
        if item.get("target_id") == target_id and item.get("type") == kind:
            return int(item.get("time", -10**9))
    return -10**9


def contextual_options(actor, target, base_options, location, now):
    if (
        location == "Apartments"
        and actor.get("home")
        and target.get("home")
        and actor.get("home") != target.get("home")
    ):
        return []

    rules = PLACE_RULES.get(location, {})
    rel = (actor.get("relationships") or {}).get(target.get("id"), {})
    f = float(rel.get("friendship", 50))
    trust = float(rel.get("trust", 50))
    attraction = float(rel.get("attraction", 10))
    annoyance = float(rel.get("annoyance", 0))
    social = float(actor.get("social_need", 0))
    stress = float(actor.get("stress", 0))
    energy = float(actor.get("energy", 100))
    conflict_until = int((actor.get("conflict_cooldowns") or {}).get(target.get("id"), 0))
    in_conflict = now < conflict_until
    out = []

    for opt in base_options:
        kind = opt["type"]
        if in_conflict and kind not in {"apologize", "make_up"}:
            continue
        place = rules.get(kind, 0.5)
        last = recent_time(actor, target.get("id"), kind)
        cooldown = COOLDOWNS.get(kind, 90)
        if now - last < cooldown and social < 75:
            continue

        score = float(opt.get("score", 0.1)) * (0.55 + 0.45 * place)
        if kind in ROMANTIC_KINDS:
            score += max(0.0, attraction - 20) / 300.0
            if meets_romantic(kind, f, trust, attraction):
                score += ROMANTIC_CONTEXT_BOOST.get(kind, 0.0)
            if kind == "date" and f >= 55 and trust >= 45:
                score += 0.12
            if kind == "kiss" and attraction >= 60 and trust >= 60:
                score += 0.18
            if kind == "intimacy" and attraction >= 75 and trust >= 70 and location == "Apartments":
                score += 0.25
            if (
                kind == "move_in_together"
                and meets_romantic(kind, f, trust, attraction)
                and actor.get("home") != target.get("home")
            ):
                score += ROMANTIC_CONTEXT_BOOST.get(kind, 0.0)

        if kind in {"argue", "apologize", "make_up"}:
            score += max(0.0, annoyance - 15) / 90.0
        if kind == "eat_together" and float(actor.get("hunger", 0)) > 45:
            score += 0.18
        if kind == "walk_together" and energy > 45 and stress < 70:
            score += 0.08
        if kind in {"small_talk", "ask_about_day", "joke"} and social > 50:
            score += 0.08

        romantic_ready = any(
            meets_romantic(k, f, trust, attraction)
            for k in ("flirt", "romantic_conversation", "date", "hug", "kiss", "intimacy")
        )
        if romantic_ready and kind in {"eat_together", "walk_together"}:
            score -= 0.18

        out.append({
            **opt,
            "score": round(score, 4),
            "context": location,
            "cooldown_minutes": cooldown,
        })

    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def choose_counter_offer(target, actor, requested, alternatives):
    if not alternatives:
        return None
    for opt in alternatives:
        if opt["type"] != requested and opt["type"] in {
            "small_talk", "ask_about_day", "walk_together", "eat_together", "joke", "compliment",
        }:
            return opt["type"]
    return alternatives[0]["type"] if alternatives[0]["type"] != requested else None
