"""Persistent event-driven cognitive state for Midnight City.

The brain is shared at the model level, but cognitive queues/contexts are
independent per NPC. Meaningful events enqueue a wake-up instead of being
silently dropped while another NPC is thinking.
"""
from __future__ import annotations
import copy
import threading
from collections import deque

IMPORTANT_EVENTS = {
    "goal_completed", "new_obligation", "obligation_imminent", "plan_interrupted",
    "major_state_change", "player_pen", "relationship_change", "significant_event",
}


class PersistentBrainRuntime:
    def __init__(self, on_rethink=None):
        self.on_rethink = on_rethink
        self.lock = threading.RLock()
        self.contexts = {}
        self.pending = {}          # character_id -> deque[requests]
        self.pending_limit = 24
        self.running = False
        self.thread = None
        self.last_event = {}
        self.last_obs = {}

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.thread = threading.Thread(target=self._loop, name="MidnightBrain", daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False

    def reset(self):
        with self.lock:
            self.contexts.clear()
            self.pending.clear()
            self.last_event.clear()
            self.last_obs.clear()

    def _loop(self):
        while True:
            with self.lock:
                if not self.running:
                    return
                item = None
                for cid in sorted(self.pending):
                    q = self.pending.get(cid)
                    if q:
                        item = q.popleft()
                        if not q:
                            self.pending.pop(cid, None)
                        break
            if item and self.on_rethink:
                try:
                    self.on_rethink(item)
                except Exception:
                    pass
            threading.Event().wait(.05)

    def observe(self, world, emit_events=True):
        now = int(world.get("sim_minutes", 0))
        chars = world.get("characters", {}) or {}
        plans = world.get("goals", {}) or {}
        with self.lock:
            for cid, c in chars.items():
                ctx = self.contexts.setdefault(cid, {"events": deque(maxlen=24), "world": {}})
                old = self.last_obs.get(cid, {})
                loc = c.get("location")
                oldloc = old.get("location")
                nearby = {
                    oid for oid, o in chars.items()
                    if oid != cid and o.get("location") == loc
                }
                oldnear = set(old.get("nearby", ()))
                if oldloc is not None and loc != oldloc:
                    self._event(cid, now, "major_state_change", f"moved to {loc}", False)
                # First observation after startup/reset establishes a baseline only.
                if oldloc is not None and emit_events:
                    for oid in nearby - oldnear:
                        self._event(cid, now, "person_entered_same_location", f"{oid} entered {loc}", False)
                    for oid in oldnear - nearby:
                        self._event(cid, now, "person_left_same_location", f"{oid} left {loc}", False)
                ctx["world"] = {
                    "sim_minutes": now,
                    "day": int(world.get("day", 1)),
                    "time": world.get("time"),
                    "location": loc,
                    "nearby_characters": [
                        {"id": oid, "name": chars[oid].get("name", oid), "action": chars[oid].get("action")}
                        for oid in sorted(nearby)
                    ],
                    "character_state": {
                        k: c.get(k) for k in (
                            "action", "mood", "energy", "stress", "curiosity", "social_need",
                            "hunger", "sleepiness", "hygiene", "fun", "comfort",
                        )
                    },
                    "active_goal": copy.deepcopy(plans.get(cid)),
                }
                self.last_obs[cid] = {"location": loc, "nearby": tuple(sorted(nearby))}

    def _event(self, cid, now, kind, detail, wake=True):
        ctx = self.contexts.setdefault(cid, {"events": deque(maxlen=24), "world": {}})
        e = {"sim_minutes": int(now), "event": kind, "detail": detail}
        ctx["events"].append(e)
        if wake and kind in IMPORTANT_EVENTS:
            marker = (int(now), kind, str(detail))
            if self.last_event.get(cid) == marker:
                return
            self.last_event[cid] = marker
            q = self.pending.setdefault(cid, deque(maxlen=self.pending_limit))
            q.append({
                "character_id": cid,
                "sim_minutes": int(now),
                "reason": f"{kind}: {detail}",
                "event": kind,
            })

    def note_event(self, cid, sim_minutes, kind, detail):
        with self.lock:
            self._event(cid, int(sim_minutes), kind, detail, True)

    def mark_goal_completed(self, cid, sim_minutes):
        self.note_event(cid, sim_minutes, "goal_completed", "high-level goal completed")

    def context_for(self, cid):
        with self.lock:
            x = copy.deepcopy(self.contexts.get(cid, {}))
            if x and "events" in x:
                x["events"] = list(x["events"])[-12:]
            return x

    def all_contexts(self):
        with self.lock:
            ids = list(self.contexts)
        return {cid: self.context_for(cid) for cid in ids}

    def pending_counts(self):
        with self.lock:
            return {cid: len(q) for cid, q in self.pending.items() if q}
