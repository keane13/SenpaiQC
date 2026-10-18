"""Act slice: operator rework guide (default) and robot mode behind ROBOT_MODE.

Robot mode is a second look, not just sorting: the planner gets the expert's cards, presents
the part the way the cited card's inspection_view says, the reasoning model judges the closer
view, and a disagreement sends the part to the hold bin for a person instead of the planned bin.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from statistics import mean
from typing import Optional

from domain.models import Decision
from domain.policy import needs_confirm
from slices.inspect.service import image_size

SUPPORTED_LANGUAGES = ("en", "id", "th", "vi")


def guide(c, decision_id: str, language: str) -> dict:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"language must be one of {SUPPORTED_LANGUAGES}")
    doc = c.docs.get("decisions", decision_id)
    if doc is None:
        raise KeyError(decision_id)
    cache = doc.setdefault("guides", {})
    if language in cache:
        return cache[language]
    card = None
    for d in doc.get("defects", []):
        if d.get("card_id"):
            card = c.cards.get(d["card_id"])
            break
    if doc["decision"] == "pass":
        steps, model, cost = [], None, 0.0
    else:
        steps, usage = c.text.rework_steps(card, doc.get("rationale", ""), language)
        model, cost = usage.model, usage.cost_usd
    g = {
        "decision_id": decision_id, "language": language, "decision": doc["decision"],
        "card_id": card.card_id if card else None,
        "card_source": f"{card.source_video} @ {card.source_timestamp}" if card else None,
        "steps": steps, "model": model, "cost_usd": cost,
        "defects": doc.get("defects", []), "image_size": doc.get("image_size"),
    }
    cache[language] = g
    c.docs.put("decisions", decision_id, doc)
    return g


def run_robot(c, decision_id: str) -> dict:
    if not c.settings.robot_mode:
        raise PermissionError("robot mode is off (set ROBOT_MODE=true)")
    doc = c.docs.get("decisions", decision_id)
    if doc is None:
        raise KeyError(decision_id)
    image = c.blobs.load(doc["image_uri"])
    approved = c.cards.list(part_number=doc["part_number"], status="approved")
    # Cards for this part: the ones the model cited, plus the defect a person confirmed.
    cited = {d["card_id"] for d in doc.get("defects", []) if d.get("card_id")}
    confirmed = doc.get("confirmed_defect_name")
    focus = [x for x in approved if x.card_id in cited or x.defect_name == confirmed] or approved
    calls, usage = c.reasoning.plan_robot(image, "image/jpeg", decision_id, doc["decision"],
                                          doc.get("rationale", ""), focus)

    target = _target_box(doc)
    second: dict = {"status": "skipped", "reason": "no defect point to re-check (fast-path decision)"}         if target is None else {"status": "skipped", "reason": "planner did not present the part to the camera"}

    def look(angle: float) -> Optional[str]:
        nonlocal second
        if target is None:
            return None
        started = time.perf_counter()
        view, how = c.robot.second_look(image, target, angle)
        w, h = image_size(view)
        out = c.reasoning.inspect(view, "image/jpeg", w, h, doc["part_number"], approved)
        after = _after(out)
        agrees = after["decision"] == doc["decision"]
        view_uri = c.blobs.save(f"episodes/second-look/{decision_id}-{int(time.time())}.jpg", view, "image/jpeg")
        second = {
            "status": "done", "angle_deg": angle, "view": how, "view_uri": view_uri, "model": out.usage.model,
            "cards_used": [x.card_id for x in focus if x.inspection_view],
            "before": _before(doc), "after": after, "agrees": agrees,
            "rationale": out.rationale, "cost_usd": out.usage.cost_usd,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        return None if agrees else "hold"

    ep = c.robot.run(decision_id, calls, scrap_confirmed=bool(doc.get("confirmed")), on_present=look)
    rec = {
        "episode_id": ep.episode_id, "decision_id": decision_id, "uri": ep.uri, "simulator": ep.simulator,
        "planner": usage.model, "calls": [x.model_dump() for x in calls], "log": ep.steps,
        "blocked": ep.blocked, "cost_usd": usage.cost_usd, "latency_ms": usage.latency_ms,
        "second_look": second, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    c.docs.put("episodes", ep.episode_id, rec)
    if second["status"] == "done":
        doc["second_look"] = second | {"episode_id": ep.episode_id}
        if not second["agrees"]:
            doc["needs_human_confirm"] = True  # two looks disagree: a person decides
        c.docs.put("decisions", decision_id, doc)
    return rec


def _target_box(doc: dict) -> Optional[list[int]]:
    """Where to look closer: the first defect ER 2 boxed, or a box around its point."""
    for d in doc.get("defects", []):
        if len(d.get("box") or []) == 4:
            return d["box"]
    for d in doc.get("defects", []):
        if len(d.get("point") or []) == 2:
            w, h = doc.get("image_size") or [0, 0]
            r = max(4, min(w, h) // 20)
            x, y = d["point"]
            return [x - r, y - r, x + r, y + r]
    return None


def _before(doc: dict) -> dict:
    defects = doc.get("defects", [])
    return {
        "decision": doc["decision"], "confidence": doc.get("confidence"),
        "cited": sum(1 for d in defects if d.get("card_id")),
        "uncited": sum(1 for d in defects if not d.get("card_id")),
        "needs_human_confirm": bool(doc.get("needs_human_confirm")),
    }


def _after(out) -> dict:
    uncited = sum(1 for d in out.defects if d.card_id is None)
    decision = Decision(out.decision)
    if uncited and decision == Decision.pass_:
        decision = Decision.rework  # same rule as Inspect: an unknown defect never passes
    return {
        "decision": decision.value, "confidence": out.confidence,
        "cited": len(out.defects) - uncited, "uncited": uncited,
        "needs_human_confirm": needs_confirm(decision, uncited > 0, out.needs_human_confirm or not out.schema_valid),
    }


def second_look_stats(c) -> dict:
    """Before/after over every robot episode that took a second look."""
    looks = [e["second_look"] for e in c.docs.list("episodes", 1000)
             if (e.get("second_look") or {}).get("status") == "done"]
    if not looks:
        return {"n": 0}

    def rate(side: str, key: str) -> float:
        return round(sum(1 for x in looks if x[side][key]) / len(looks), 3)

    paired = [x for x in looks if x["before"]["confidence"] is not None and x["after"]["confidence"] is not None]
    return {
        "n": len(looks),
        "agreement_rate": round(sum(1 for x in looks if x["agrees"]) / len(looks), 3),
        "rerouted_to_hold": sum(1 for x in looks if not x["agrees"]),
        "needs_human_before": rate("before", "needs_human_confirm"),
        "needs_human_after": rate("after", "needs_human_confirm"),
        "uncited_before": sum(x["before"]["uncited"] for x in looks),
        "uncited_after": sum(x["after"]["uncited"] for x in looks),
        "confidence_pairs": len(paired),
        "confidence_before": round(mean(x["before"]["confidence"] for x in paired), 3) if paired else None,
        "confidence_after": round(mean(x["after"]["confidence"] for x in paired), 3) if paired else None,
        "mean_latency_ms": int(mean(x["latency_ms"] for x in looks)),
        "mean_cost_usd": round(mean(x["cost_usd"] for x in looks), 6),
    }


def episode_frames(c, episode_id: str) -> dict:
    import json

    rec = c.docs.get("episodes", episode_id)
    if rec is None:
        raise KeyError(episode_id)
    return json.loads(c.blobs.load(rec["uri"]))
