"""Smart autonomy layer inspired by modern life-sim autonomy systems.
No LLM calls here. This layer provides fast, deterministic candidate scoring,
context (time/place/occasion), soft needs, memories, routines and reflection.
"""
from __future__ import annotations
from typing import Any

GOALS = {
    "sleep","get_ready","take_care_of_self","eat","attend_obligation","work",
    "study","relax","socialize","recreation","buy_essentials","personal_goal",
    "wander","wait",
}

def clamp(x,a=0.0,b=1.0): return max(a,min(b,float(x)))

def norm(v): return clamp(float(v)/100.0)

def need_pressure(c):
    return {
        "hunger": norm(c.get("hunger",0)),
        "sleep": norm(c.get("sleepiness",0)),
        "hygiene": norm(100-float(c.get("hygiene",100))),
        "social": norm(c.get("social_need",0)),
        "fun": norm(100-float(c.get("fun",100))),
        "stress": norm(c.get("stress",0)),
        "energy_low": norm(100-float(c.get("energy",100))),
        "comfort_low": norm(100-float(c.get("comfort",100))),
    }

def context(c, sim_minutes, obligations=None, nearby=None):
    m=int(sim_minutes)%1440; hour=m/60
    day=(int(sim_minutes)//1440)%7
    p=c.get("personality") or {}
    n=need_pressure(c)
    return {
        "hour":hour,"day":day,
        "part_of_day":"night" if hour>=22 or hour<6 else "morning" if hour<11 else "afternoon" if hour<17 else "evening",
        "weekday":day<5,
        "obligations":obligations or [],
        "nearby_count":len(nearby or []),
        "alone":not bool(nearby),
        "personality":p,"needs":n,
    }

def relationship_bonus(c, nearby=None):
    rels=c.get("relationships") or {}
    bonus={g:0.0 for g in GOALS}
    for person in nearby or []:
        rid=person.get("id") or person.get("character_id")
        r=rels.get(rid,{}) if isinstance(rels,dict) else {}
        trust=float(r.get("trust",50))/100.0; friendship=float(r.get("friendship",50))/100.0
        annoyance=float(r.get("annoyance",0))/100.0
        bonus["socialize"] += .18*friendship + .10*trust - .12*annoyance
        if friendship>.65: bonus["recreation"] += .04
    return bonus

def memory_bonus(c, recent_goals=None):
    memories=c.get("memory_items") or c.get("episodic_memory") or []
    text=" ".join(str(x) for x in memories[-12:]).lower()
    b={g:0.0 for g in GOALS}
    if any(x in text for x in ("enjoyed", "liked", "fun")): b["recreation"]+=.04
    if any(x in text for x in ("productive", "finished", "progress")): b["personal_goal"]+=.05; b["work"]+=.03
    if any(x in text for x in ("lonely", "missed", "alone")): b["socialize"]+=.07
    if any(x in text for x in ("stress", "stressed", "exhausted")): b["relax"]+=.06
    return b

def score_candidates(c, sim_minutes, obligations=None, nearby=None, recent_goals=None, smart_schedule=None):
    """Utility-style autonomy: score possible high-level intentions.
    Needs are soft signals. Time/place/occasion/personality modify utility.
    """
    ctx=context(c,sim_minutes,obligations,nearby); n=ctx["needs"]; p=ctx["personality"]
    hour=ctx["hour"]; weekday=ctx["weekday"]; day=ctx["day"]
    scores={g:0.02 for g in GOALS}
    reasons={g:[] for g in GOALS}
    if nearby:
        for person in nearby:
            r=(c.get("relationships") or {}).get(person.get("id"), {})
            f=float(r.get("friendship",50)); trust=float(r.get("trust",50)); annoyance=float(r.get("annoyance",0))
            if f >= 35 and annoyance < 70:
                social_opportunity=.14 + max(0.0, f-50)/400 + max(0.0, trust-50)/600
                if ctx["hour"] >= 18: social_opportunity += .05
                scores["socialize"] += social_opportunity
                reasons["socialize"].append(f"nearby {person.get('name','NPC')} opportunity")
    rel_bonus=relationship_bonus(c, nearby)
    mem_bonus=memory_bonus(c, recent_goals)
    for g,v in rel_bonus.items():
        if v: reasons[g].append("relationship context")
        scores[g]+=v
    for g,v in mem_bonus.items():
        if v: reasons[g].append("memory context")
        scores[g]+=v

    def add(g,v,why):
        scores[g]+=float(v); reasons[g].append(why)

    if n["sleep"]>.35 or n["energy_low"]>.45:
        add("sleep", .25*n["sleep"]+.22*n["energy_low"], "sleep pressure")
    if hour>=22 or hour<6:
        add("sleep", .42, "night")
    # Morning preparation is a bounded routine, not an all-morning activity.
    # Once the normal window has passed, it should not keep winning over work/study.
    if 6<=hour<9.25 and weekday:
        add("get_ready", .25, "morning routine")
    if n["hunger"]>.35:
        add("eat", .30*n["hunger"], "hunger")
    if n["hygiene"]>.35:
        add("take_care_of_self", .22*n["hygiene"], "hygiene")
    if n["social"]>.30:
        add("socialize", .20*n["social"]*float(p.get("sociability",.5)), "social need")
    if n["fun"]>.30 or n["stress"]>.35:
        add("recreation", .22*max(n["fun"],n["stress"]), "fun/stress")
    interests=(c.get('preferences') or {}).get('interests') or []
    if interests:
        add('recreation', min(.10, .02*len(interests)), 'personal interests')
    if n["stress"]>.45:
        add("relax", .18*n["stress"], "stress recovery")
    # Work is schedule/occupation driven, not an always-on need. This is a
    # key part of life-sim autonomy: a student should not spontaneously work
    # every time the Brain wakes up.
    occupation=str(c.get("occupation","")).lower()
    work_window = (10 <= hour < 17 and weekday and ("developer" in occupation or "software" in occupation))
    freelance_window = (17 <= hour < 22 and weekday and "freelance" in occupation and day in (0,2,4))
    if work_window or freelance_window:
        add("work", .20*float(p.get("work_drive",.5)), "work schedule")
    elif "student" in occupation and weekday and 9 <= hour < 17:
        # Keep academic work as study rather than generic employment.
        add("study", .10*float(p.get("discipline",.5)), "student schedule")
    if float(p.get("curiosity",.5))>.6:
        add("personal_goal", .12*float(p.get("curiosity",.5)), "curiosity")
        add("wander", .08*float(p.get("curiosity",.5)), "curiosity")
    if weekday:
        add("study", .06, "weekday")
    if ctx["alone"] and n["social"]<.35:
        add("relax", .04, "quiet")
    if hour>=17 and hour<23:
        add("recreation", .08, "evening")
        add("personal_goal", .04 * float(p.get("curiosity",.5)), "evening project")
    if hour>=18 and n["social"]>.2:
        add("socialize", .06, "evening social window")

    # Obligations dominate ordinary utility, but are still represented as context.
    for o in obligations or []:
        if o.get("urgent"):
            add("attend_obligation", .90, "scheduled obligation")
            break

    # Soft schedule from last night's reflection.
    for item in smart_schedule or []:
        if item.get("goal") not in scores: continue
        # Smart Schedule is weekly. Missing `days` keeps backward compatibility
        # with old saves and means every weekday unless explicitly overridden.
        item_days=item.get("days")
        if item_days is not None:
            try:
                if day not in {int(x) for x in item_days}:
                    continue
            except Exception:
                continue
        elif not weekday:
            continue
        start=float(item.get("start",0)); end=float(item.get("end",24))
        if start <= hour < end:
            if item["goal"] == "sleep" and hour < 22 and n["sleep"] < .90 and n["energy_low"] < .85:
                continue
            add(item["goal"], .32, "smart schedule")

    # Personality/context modifiers.
    if float(p.get("routine_preference",.5))>.65 and weekday:
        add("get_ready", .04, "routine preference")
        add("study", .04, "routine preference")
    if float(p.get("spontaneity",.5))>.65:
        add("wander", .07, "spontaneity")
    if float(p.get("risk_taking",.5))>.6:
        add("wander", .05, "risk tolerance")
        add("socialize", .025, "risk tolerance")
    if float(p.get("impulsiveness",.5))>.65 and hour>=17:
        add("recreation", .05, "impulse")
        add("wander", .04, "impulse")
    if float(p.get("laziness",.5))>.65:
        add("relax", .06, "laziness")
    if float(p.get("discipline",.5))>.75:
        add("work", .05, "discipline")

    # Strong anti-loop memory: Smart Zoi-style autonomy should not repeatedly
    # choose the same leisure/need just because its generic utility remains high.
    # Only hard physiological pressure is allowed to overcome this cooldown.
    recent=(recent_goals or [])[-6:]
    counts={g:recent.count(g) for g in set(recent)}
    # Preparation is a daily routine, not a repeatable idle goal.
    if 'get_ready' in counts:
        scores['get_ready'] -= .80
        reasons['get_ready'].append('already prepared recently')
    for g,count in counts.items():
        if g in scores:
            scores[g] -= .14 * min(count,3)
    if recent:
        scores[recent[-1]] -= .12
    # Recent recreation/social actions get a longer cooldown unless their need
    # has become genuinely high again.
    if recent and recent[-1] == 'recreation' and n['fun'] < .65 and n['stress'] < .65:
        scores['recreation'] -= .28
    if recent and recent[-1] == 'socialize' and n['social'] < .65:
        scores['socialize'] -= .22
    if recent and recent[-1] == 'eat' and n['hunger'] < .55:
        scores['eat'] -= .20
    if recent and recent[-1] == 'sleep' and n['sleep'] < .70 and hour < 22:
        scores['sleep'] -= .30
    if recent and recent[-1] in ("relax","recreation","wait"):
        scores["personal_goal"]+=.05

    # Never allow a negative score.
    scores={k:max(0.0,v) for k,v in scores.items()}
    ranked=sorted(scores,key=scores.get,reverse=True)
    return [{"goal":g,"score":round(scores[g],4),"reasons":reasons[g][:4]} for g in ranked]

def choose(c, sim_minutes, obligations=None, nearby=None, recent_goals=None, smart_schedule=None):
    ranked=score_candidates(c,sim_minutes,obligations,nearby,recent_goals,smart_schedule)
    top=ranked[0]
    duration={
        "sleep":420,"get_ready":45,"eat":30,"take_care_of_self":30,
        "attend_obligation":120,"work":120,"study":90,"relax":60,
        "socialize":60,"recreation":60,"buy_essentials":45,
        "personal_goal":90,"wander":60,"wait":20,
    }.get(top["goal"],60)
    return {"goal":top["goal"],"duration_minutes":duration,"utility":top["score"],
            "reasons":top["reasons"],"source":"utility"}

def make_inner_thought(c, goal, sim_minutes, reason=None):
    n=need_pressure(c); name=c.get("name","NPC"); p=c.get("personality") or {}
    mood="calm" if float(c.get("stress",0))<35 else "tense" if float(c.get("stress",0))>65 else "okay"
    phrases={
      "sleep":"I am tired enough that sleep is starting to matter.",
      "eat":"I should get something to eat before I get too hungry.",
      "attend_obligation":"I have somewhere I need to be, so I should keep my schedule.",
      "work":"I want to make some progress on my work.",
      "study":"I should put some time into studying.",
      "socialize":"It would be nice to spend some time around someone.",
      "recreation":"I could use something enjoyable to reset my mood.",
      "relax":"I need a quieter moment.",
      "personal_goal":"I want to make progress on something that matters to me.",
      "wander":"I feel like getting out and seeing something different.",
      "get_ready":"I should get ready properly before the day gets going.",
      "take_care_of_self":"I should take care of myself.",
      "buy_essentials":"I should take care of a practical errand.",
      "wait":"Nothing urgent is pulling me away right now.",
    }
    return f"{name}: {phrases.get(goal,'I am deciding what matters next')} (feeling {mood})."

def reflect_day(c, events):
    """Build a compact day reflection plus learned signals."""
    name=c.get("name","NPC"); notable=[]; seen=set(); completed=[]
    for e in reversed(events[-120:]):
        if e.get("kind") not in ("body_action","goal_completed","social","thought"): continue
        text=e.get("action_text") or e.get("text")
        if text and text not in seen:
            seen.add(text); notable.append(text)
        if e.get("kind")=="goal_completed" and e.get("action"):
            completed.append(e.get("action"))
        if len(notable)>=8: break
    notable=list(reversed(notable))
    if not notable: return {"text":f"{name} had a quiet day and kept to a familiar routine.","lessons":[],"preferences":{}}
    lessons=[]; prefs={}
    joined=" ".join(notable).lower()
    if any(x in joined for x in ("gaming","watching tv","recreating")): lessons.append("leisure helped recover mood")
    if any(x in joined for x in ("working","studying","attending college")): lessons.append("productive time was part of the day")
    if any(x in joined for x in ("socializing",)): lessons.append("social contact mattered")
    if len(completed)>=4: lessons.append("the day was structured and active")
    if "gaming" in joined: prefs["recreation_action"]="gaming"
    elif "watching tv" in joined: prefs["recreation_action"]="watch_tv"
    text=f"{name} reflected on the day: " + "; ".join(notable[:8]) + "."
    if lessons: text += " Learned: " + "; ".join(lessons) + "."
    return {"text":text,"lessons":lessons,"preferences":prefs}

def schedule_from_reflection(c, sim_minutes, reflection):
    p=c.get("personality") or {}; occ=str(c.get("occupation","" )).lower(); weekdays=[0,1,2,3,4]
    diary=reflection.get("text","") if isinstance(reflection,dict) else str(reflection)
    out=[{"goal":"get_ready","start":7,"end":9.15,"days":weekdays,"reason":"morning routine"},{"goal":"eat","start":8,"end":10,"days":weekdays,"reason":"breakfast"}]
    if "evening student" in occ: out.append({"goal":"study","start":21,"end":22,"days":weekdays,"reason":"evening review"})
    elif "student" in occ: out.append({"goal":"study","start":16,"end":18,"days":weekdays,"reason":"study/review"})
    elif "developer" in occ or "software" in occ: out.append({"goal":"work","start":10,"end":17,"days":weekdays,"reason":"work routine"})
    if "freelance" in occ: out.append({"goal":"work","start":17,"end":20,"days":[0,2,4],"reason":"freelance project"})
    if float(p.get("sociability",.5))>.6: out.append({"goal":"socialize","start":18,"end":21,"days":weekdays,"reason":"social preference"})
    out.append({"goal":"recreation","start":18,"end":22,"days":weekdays,"reason":"evening recovery"})
    if "productive" in diary.lower() and float(p.get("discipline",.5))>.65: out.append({"goal":"personal_goal","start":20,"end":21.5,"days":[0,1,2,3,4],"reason":"follow-through from reflection"})
    return out
