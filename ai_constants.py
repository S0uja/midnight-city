"""Shared AI constants for Midnight City character autonomy.

Single source of truth for romantic progression thresholds, map zones,
and location travel costs. Import from here instead of duplicating numbers
across interaction_engine, social_context, and the server.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Romantic ladder thresholds (friendship / trust / attraction minimums)
# Used by interaction_engine availability, social_context scoring boosts,
# willingness checks, and player_interaction gates.
# ---------------------------------------------------------------------------
ROMANTIC_THRESHOLDS = {
    "flirt": {"friendship": 35, "trust": 30, "attraction": 10},
    "romantic_conversation": {"friendship": 40, "trust": 30, "attraction": 18},
    "date": {"friendship": 45, "trust": 35, "attraction": 24},
    "hug": {"friendship": 40, "trust": 30, "attraction": 18},
    "kiss": {"friendship": 50, "trust": 45, "attraction": 35},
    "intimacy": {"friendship": 60, "trust": 55, "attraction": 42},
    "move_in_together": {"friendship": 75, "trust": 70, "attraction": 65},
}

# Soft utility boosts applied once the character *meets* the threshold above.
# Keeps romantic actions competitive against repetitive eat/walk loops.
ROMANTIC_SCORE_BOOST = {
    "flirt": 0.65,
    "romantic_conversation": 0.65,
    "date": 0.70,
    "hug": 0.45,
    "kiss": 0.70,
    "intimacy": 0.55,
    "move_in_together": 0.22,
}

# Slightly softer boosts used only in the place-context layer.
ROMANTIC_CONTEXT_BOOST = {
    "flirt": 0.60,
    "romantic_conversation": 0.60,
    "date": 0.65,
    "hug": 0.40,
    "kiss": 0.65,
    "intimacy": 0.50,
    "move_in_together": 0.28,
}

COUPLE_STATUSES = frozenset({"boyfriend", "girlfriend"})

# ---------------------------------------------------------------------------
# World locations ↔ approximate map coordinates (map-v5 semantic zones)
# Coordinates must be unique so nearest-zone selection is unambiguous.
# ---------------------------------------------------------------------------
LOCATION_ZONES = {
    "Apartments": (16.0, 24.0),
    "College": (49.0, 17.0),
    "Rooftop": (52.0, 43.0),
    "Park": (27.0, 39.0),
    "Studio": (72.0, 55.0),
    "Cafe": (57.0, 58.0),
    "Downtown": (51.0, 48.0),
    "Night Club": (75.0, 45.0),
    "Beach": (14.0, 85.0),
    "Clinic": (8.0, 57.0),
    "Gym": (18.0, 69.0),
    "Waterfront": (49.0, 82.0),
    "Port": (86.0, 79.0),
    "Rail Station": (65.0, 39.0),
}

# Relative travel cost seeds (minutes between locations).
TRAVEL_BASE = {
    "Apartments": 0, "Cafe": 8, "Studio": 12, "College": 10,
    "Night Club": 10, "Rooftop": 8, "Beach": 9, "Park": 7,
    "Downtown": 8, "Clinic": 10, "Gym": 9, "Waterfront": 9,
    "Port": 12, "Rail Station": 8,
}

DATE_LOCATIONS = ("Cafe", "Park", "Rooftop", "Beach")

HOME = "Apartments"
SOCIAL_LOCATIONS = frozenset({"Cafe", "Night Club", "Rooftop", "Downtown", "Beach", "Park"})

VALID_GOALS = frozenset({
    "sleep", "get_ready", "take_care_of_self", "eat", "attend_obligation",
    "work", "study", "relax", "socialize", "recreation", "buy_essentials",
    "personal_goal", "wander", "wait",
})


def meets_romantic(kind: str, friendship: float, trust: float, attraction: float) -> bool:
    """Return True if relationship stats clear the threshold for this interaction."""
    t = ROMANTIC_THRESHOLDS.get(kind)
    if not t:
        return True
    return (
        friendship >= t["friendship"]
        and trust >= t["trust"]
        and attraction >= t["attraction"]
    )


def nearest_location(x: float, y: float) -> str:
    """Map a 2D player position to the closest named location."""
    best_name = "Apartments"
    best_dist = float("inf")
    for name, (zx, zy) in LOCATION_ZONES.items():
        d = (zx - x) ** 2 + (zy - y) ** 2
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


def travel_minutes(a: str, b: str) -> int:
    if a == b:
        return 0
    return max(3, min(30, abs(TRAVEL_BASE.get(a, 8) - TRAVEL_BASE.get(b, 8)) + 4))
