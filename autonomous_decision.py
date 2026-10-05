"""Simple priority-ordered goal fallback for Midnight City.

The live server uses smart_autonomy.choose as the primary non-LLM path.
fallback_goal is a simpler last-resort alternative (and for unit tests).
need_pressure is re-exported from smart_autonomy (single definition).
"""
from __future__ import annotations

import random
from typing import Any

from smart_autonomy import need_pressure  # canonical definition

DEFAULT_PERSONALITY = {
    "sociability": 0.62,
    "discipline": 0.68,
    "impulsiveness": 0.28,
    "laziness": 0.32,
    "curiosity": 0.64,
    "risk_taking": 0.30,
    "routine_preference": 0.58,
    "social_energy": 0.60,
    "work_drive": 0.60,
    "spontaneity": 0.35,
}


def personality(c: dict) -> dict[str, float]:
    p = dict(DEFAULT_PERSONALITY)
    p.update(c.get("personality") or {})
    return {k: max(0.0, min(1.0, float(v))) for k, v in p.items()}


def fallback_goal(
    c: dict,
    obligations: list | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Priority-ordered goal when utility/LLM are unavailable.

    Order: urgent obligation → sleep → hunger → hygiene → stress/fun →
    social → work → curiosity → relax.
    """
    _ = rng  # reserved for stochastic ties; kept for API stability
    p = personality(c)
    n = need_pressure(c)
    obligations = obligations or []

    if any(o.get("urgent") for o in obligations):
        return {"goal": "attend_obligation", "duration_minutes": 240, "source": "fallback"}
    if n["sleep"] > 0.86 or n["energy_low"] > 0.92:
        return {"goal": "sleep", "duration_minutes": 450, "source": "fallback"}
    if n["hunger"] > 0.78:
        return {"goal": "eat", "duration_minutes": 35, "source": "fallback"}
    if n["hygiene"] > 0.75:
        return {"goal": "take_care_of_self", "duration_minutes": 40, "source": "fallback"}
    if n["stress"] > 0.70 or n["fun"] > 0.72:
        return {"goal": "recreation", "duration_minutes": 60, "source": "fallback"}
    if n["social"] > 0.72 and p["sociability"] > 0.5:
        return {"goal": "socialize", "duration_minutes": 60, "source": "fallback"}
    if p["work_drive"] > 0.72 and c.get("occupation"):
        return {"goal": "work", "duration_minutes": 120, "source": "fallback"}
    if p["curiosity"] > 0.7:
        return {"goal": "personal_goal", "duration_minutes": 90, "source": "fallback"}
    return {"goal": "relax", "duration_minutes": 60, "source": "fallback"}
