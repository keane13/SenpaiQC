"""Request guardrails for a public demo URL.

- Per-user rate limit on endpoints that call Gemini (inspect, teach, guide, robot, root cause, ask).
- A daily cap on AI calls per instance, so a leaked token cannot run up the Gemini bill.
  With Cloud Run --max-instances N the worst case is N x AI_CALLS_PER_DAY calls a day.
In-memory on purpose: no extra infrastructure, and the cap resets with the instance.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from auth import current_user
from config import get_settings

_lock = threading.Lock()
_recent: dict[str, deque] = defaultdict(deque)
_day = {"date": "", "count": 0}


def _charge(user: str, units: int) -> str:
    """Per-user requests per minute, plus a daily budget in cost units per instance.
    One unit ~ one Gemini call (about $0.002-0.007); heavier endpoints cost more units."""
    s = get_settings()
    now = time.monotonic()
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        q = _recent[user]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= s.ai_calls_per_minute:
            raise HTTPException(429, f"Too many AI requests: limit {s.ai_calls_per_minute} per minute. Wait a moment and try again.")
        if _day["date"] != today:
            _day.update(date=today, count=0)
        if _day["count"] + units > s.ai_calls_per_day:
            raise HTTPException(429, "The daily AI budget for this demo is used up. Try again tomorrow.")
        q.append(now)
        _day["count"] += units
    return user


def ai_quota(user: str = Depends(current_user)) -> str:
    """One Gemini call: inspect escalation, rework steps, chat question."""
    return _charge(user, 1)


def ai_quota_video(user: str = Depends(current_user)) -> str:
    """Video understanding: long inputs, roughly ten calls' worth of tokens."""
    return _charge(user, 10)


def ai_quota_agent(user: str = Depends(current_user)) -> str:
    """Root-cause agent: about 20 model calls per investigation."""
    return _charge(user, 25)


def usage() -> dict:
    s = get_settings()
    return {"ai_units_today": _day["count"], "ai_units_per_day": s.ai_calls_per_day, "ai_calls_per_minute": s.ai_calls_per_minute}


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Image URLs carry the token as a query parameter; never leak it to other sites via Referer.
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}
