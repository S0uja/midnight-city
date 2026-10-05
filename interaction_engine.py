"""Contextual social interaction engine for Midnight City.

Deterministic, fast layer: Brain chooses whether to socialize; this layer
chooses who/how, checks the other NPC's willingness, and applies relationship
outcomes. Romantic thresholds come from ai_constants (single source of truth).
"""
from __future__ import annotations

from ai_constants import (
    COUPLE_STATUSES,
    ROMANTIC_SCORE_BOOST,
    ROMANTIC_THRESHOLDS,
    meets_romantic,
)

INTERACTIONS = {
    "greet": {"minutes": 5, "min_friendship": 0, "social": 0.08, "friendship": 0.8, "trust": 0.15, "annoyance": -0.1},
    "small_talk": {"minutes": 15, "min_friendship": 0, "social": 0.18, "friendship": 1.4, "trust": 0.25, "annoyance": -0.15},
    "joke": {"minutes": 10, "min_friendship": 10, "social": 0.20, "friendship": 1.8, "trust": 0.10, "annoyance": -0.35},
    "ask_about_day": {"minutes": 12, "min_friendship": 0, "social": 0.16, "friendship": 1.2, "trust": 0.5, "annoyance": -0.2},
    "ask_advice": {"minutes": 15, "min_friendship": 20, "social": 0.20, "friendship": 1.0, "trust": 1.0, "respect": 0.8, "annoyance": -0.1},
    "offer_help": {"minutes": 20, "min_friendship": 20, "social": 0.22, "friendship": 2.0, "trust": 1.8, "respect": 1.2, "annoyance": -0.3},
    "eat_together": {"minutes": 30, "min_friendship": 35, "social": 0.32, "friendship": 2.4, "trust": 0.8, "annoyance": -0.2},
    "walk_together": {"minutes": 30, "min_friendship": 35, "social": 0.30, "friendship": 2.2, "trust": 0.5, "annoyance": -0.2},
    "invite_home": {"minutes": 10, "min_friendship": 50, "social": 0.26, "friendship": 2.0, "trust": 1.2, "annoyance": -0.1},
    "flirt": {"minutes": 10, "min_friendship": 35, "social": 0.28, "friendship": 1.2, "trust": 0.2, "attraction": 3.5, "annoyance": -0.1},
    "romantic_conversation": {"minutes": 25, "min_friendship": 40, "social": 0.30, "friendship": 2.0, "trust": 2.2, "attraction": 4.0, "annoyance": -0.1},
    "date": {"minutes": 90, "min_friendship": 45, "social": 0.42, "friendship": 4.0, "trust": 3.0, "attraction": 7.0, "annoyance": -0.3},
    "hug": {"minutes": 5, "min_friendship": 40, "social": 0.34, "friendship": 1.5, "trust": 2.0, "attraction": 3.0, "annoyance": -0.3},
    "kiss": {"minutes": 5, "min_friendship": 50, "social": 0.40, "friendship": 1.5, "trust": 2.5, "attraction": 8.0, "annoyance": -0.2},
    "intimacy": {"minutes": 60, "min_friendship": 60, "social": 0.46, "friendship": 2.0, "trust": 4.0, "attraction": 6.0, "annoyance": -0.5},
    "move_in_together": {"minutes": 15, "min_friendship": 75, "social": 0.38, "friendship": 3.0, "trust": 4.0, "attraction": 2.0, "annoyance": -0.2},
    "compliment": {"minutes": 5, "min_friendship": 10, "social": 0.18, "friendship": 1.3, "trust": 0.2, "attraction": 0.7, "respect": 0.4, "annoyance": -0.2},
    "gossip": {"minutes": 15, "min_friendship": 45, "social": 0.22, "friendship": 1.0, "trust": -0.5, "annoyance": -0.1},
    "argue": {"minutes": 15, "min_friendship": 0, "social": 0.12, "friendship": -2.5, "trust": -2.0, "annoyance": 2.2, "respect": -0.5},
    "serious_argument": {"minutes": 25, "min_friendship": 0, "social": 0.08, "friendship": -5.0, "trust": -4.5, "annoyance": 6.0, "respect": -1.5},
    "apologize": {"minutes": 10, "min_friendship": 0, "social": 0.15, "friendship": 2.0, "trust": 2.5, "annoyance": -3.0},
    "make_up": {"minutes": 15, "min_friendship": 20, "social": 0.20, "friendship": 2.8, "trust": 2.0, "annoyance": -3.5},
    "study_together": {"minutes": 45, "min_friendship": 15, "social": 0.22, "friendship": 1.8, "trust": 0.8, "respect": 0.8, "annoyance": -0.1},
    "watch_together": {"minutes": 45, "min_friendship": 25, "social": 0.24, "friendship": 2.0, "trust": 0.7, "annoyance": -0.1},
}

ROMANTIC_KINDS = frozenset(ROMANTIC_THRESHOLDS.keys())


def relationship(a, bid):
    return (a.get("relationships") or {}).get(bid) or {
        "friendship": 50, "trust": 50, "attraction": 10, "annoyance": 0, "respect": 50
    }


def available_interactions(actor, target, hour: float):
    r = relationship(actor, target.get("id"))
    f = float(r.get("friendship", 50))
    trust = float(r.get("trust", 50))
    attraction = float(r.get("attraction", 10))
    annoyance = float(r.get("annoyance", 0))
    relationship_status = str(r.get("status", "")).lower()
    is_couple = relationship_status in COUPLE_STATUSES
    out = []

    for kind, meta in INTERACTIONS.items():
        if f < meta.get("min_friendship", 0):
            continue
        family_role = str(r.get("family_role") or "").strip().lower()
        if family_role and kind in {"flirt", "romantic_conversation", "date", "hug", "kiss", "intimacy"}:
            continue
        if kind in ROMANTIC_KINDS and not meets_romantic(kind, f, trust, attraction):
            continue
        if kind == "move_in_together" and actor.get("home") == target.get("home"):
            continue
        if kind in {"make_up", "apologize"} and annoyance < 8:
            continue
        if kind == "gossip" and trust < 35:
            continue
        if kind == "argue" and annoyance < 12 and f > 35:
            continue
        if kind == "serious_argument" and (annoyance < 35 or trust > 55):
            continue

        score = float(meta.get("social", 0.1))
        score += max(0.0, f - 40) / 250.0
        score += max(0.0, trust - 50) / 500.0
        if kind in ROMANTIC_KINDS:
            score += max(0.0, attraction - 20) / 400.0
            score += ROMANTIC_SCORE_BOOST.get(kind, 0.0)
        if kind == "intimacy" and is_couple:
            score += 0.30
        score += max(0.0, annoyance - 15) / 70.0 if kind in {"argue", "serious_argument", "apologize", "make_up"} else 0.0
        if kind == "serious_argument" and annoyance >= 40 and trust < 45:
            score += 0.16
        if hour >= 18 and kind in {"eat_together", "walk_together", "small_talk", "joke"}:
            score += 0.06
        if float(actor.get("social_need", 0)) > 55:
            score += 0.08
        out.append({"type": kind, "score": round(score, 4), "minutes": meta["minutes"]})

    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def choose_interaction(actor, target, hour: float):
    options = available_interactions(actor, target, hour)
    if not options:
        return None
    recent = actor.get("recent_interaction_types") or []
    for option in options:
        if option["type"] not in recent[:2] or float(actor.get("social_need", 0)) > 65:
            return option
    return options[0]


def willingness(target, actor, interaction_type, hour: float):
    r = relationship(target, actor.get("id"))
    f = float(r.get("friendship", 50))
    trust = float(r.get("trust", 50))
    annoyance = float(r.get("annoyance", 0))
    attraction = float(r.get("attraction", 10))
    score = 0.55 + (f - 50) / 180.0 + (trust - 50) / 300.0 - annoyance / 90.0

    if float(target.get("stress", 0)) > 70:
        score -= 0.18
    if float(target.get("energy", 100)) < 20:
        score -= 0.18
    if float(target.get("sleepiness", 0)) > 80:
        score -= 0.20

    if interaction_type in ROMANTIC_KINDS:
        th = ROMANTIC_THRESHOLDS[interaction_type]
        if attraction < th["attraction"] or f < th["friendship"] or trust < th["trust"]:
            score -= 0.12 + 0.08 * max(
                0.0,
                (th["attraction"] - attraction) / max(1.0, th["attraction"]),
            )
        if interaction_type == "intimacy" and str(r.get("status", "")).lower() in COUPLE_STATUSES:
            score += 0.22

    if interaction_type == "argue" and annoyance < 15:
        score -= 0.20
    if interaction_type == "serious_argument" and (annoyance < 35 or trust > 55):
        score -= 0.35
    if interaction_type in {"apologize", "make_up"} and annoyance >= 20:
        score += 0.20
    if 18 <= hour < 23:
        score += 0.04
    if interaction_type in ROMANTIC_KINDS and 18 <= hour < 24:
        score += 0.06
    return max(0.03, min(0.97, score))


def label(kind, actor_name, target_name):
    labels = {
        "greet": f"Greeting {target_name}",
        "small_talk": f"Having small talk with {target_name}",
        "joke": f"Joking with {target_name}",
        "ask_about_day": f"Asking {target_name} about their day",
        "ask_advice": f"Asking {target_name} for advice",
        "offer_help": f"Offering help to {target_name}",
        "eat_together": f"Eating together with {target_name}",
        "walk_together": f"Walking with {target_name}",
        "invite_home": f"Inviting {target_name} home",
        "flirt": f"Flirting with {target_name}",
        "romantic_conversation": f"Having a romantic conversation with {target_name}",
        "date": f"Going on a date with {target_name}",
        "hug": f"Hugging {target_name}",
        "kiss": f"Kissing {target_name}",
        "intimacy": f"Being intimate with {target_name}",
        "move_in_together": f"Discussing living together with {target_name}",
        "compliment": f"Complimenting {target_name}",
        "gossip": f"Gossiping with {target_name}",
        "argue": f"Arguing with {target_name}",
        "serious_argument": f"Having a serious argument with {target_name}",
        "apologize": f"Apologizing to {target_name}",
        "make_up": f"Making up with {target_name}",
        "study_together": f"Studying with {target_name}",
        "watch_together": f"Watching together with {target_name}",
    }
    return labels.get(kind, f"Interacting with {target_name}")
