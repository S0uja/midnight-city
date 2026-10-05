"""Body / Executive layer — DEPRECATED thin wrapper.

Planning is owned by midnight_city_server_local.build_plan(), which also
handles social_interaction pairing, date travel, and joint activities.
This module is kept only so older imports do not crash; new code must not
call ExecutivePlanner.

Prefer: server build_plan + ai_constants (HOME, SOCIAL_LOCATIONS, travel_minutes).
"""
from __future__ import annotations

import warnings

from ai_constants import HOME, SOCIAL_LOCATIONS  # noqa: F401 — re-export for compatibility

warnings.warn(
    "executive.ExecutivePlanner is deprecated; use midnight_city_server_local.build_plan",
    DeprecationWarning,
    stacklevel=2,
)


class ExecutivePlanner:
    """Legacy stub. Raises if used so silent dual-path planning cannot return."""

    def __init__(self, character: dict, sim_minutes: int):
        raise RuntimeError(
            "ExecutivePlanner is deprecated. Use midnight_city_server_local.build_plan() "
            "which owns goal→action expansion including social/date logic."
        )

    def make_plan(self, goal: str, requested_duration: int = 60):
        raise RuntimeError("ExecutivePlanner.make_plan is disabled")
