"""Alerts slice: tell the QC team when a spike opens an investigation.

scan() publishes one alert per new investigation. On Google Cloud it goes to a Pub/Sub topic and
comes back through a push subscription to /api/alerts/push, so a slow or failing chat service
never blocks the scan and Pub/Sub retries the delivery. Locally it is delivered inline.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def spike_alert(inv: dict) -> dict:
    return {
        "kind": "spike",
        "investigation_id": inv["id"],
        "part_number": inv.get("part_number", ""),
        "defect_name": inv["defect_name"],
        "shift_key": inv["shift_key"],
        "rate": inv["rate"],
        "ucl": inv["ucl"],
        "center": inv["center"],
    }


def sample_alert(user: str) -> dict:
    return {"kind": "test", "requested_by": user}


def render(alert: dict, app_url: str = "") -> str:
    link = f"{app_url.rstrip('/')}/#analytics" if app_url else ""
    if alert.get("kind") == "spike":
        lines = [
            f"SenpaiQC alert: {alert['defect_name']} spike on {alert['part_number']}",
            f"Shift {alert['shift_key']}: {alert['rate']:.1%} defective "
            f"(limit {alert['ucl']:.1%}, normal {alert['center']:.1%}).",
            f"Investigation {alert['investigation_id']} is open. Run Find root cause to draft the 8D.",
        ]
    else:
        lines = [f"SenpaiQC test alert from {alert.get('requested_by', 'a user')}: alerts reach this chat."]
    return "\n".join(lines + ([link] if link else []))


def notify(c, alert: dict) -> None:
    """Never lets an alert problem break the caller (the scan still opens the investigation)."""
    try:
        if c.notifier is not None:
            c.notifier.publish(alert)
        else:
            deliver(c, alert)
    except Exception as exc:
        log.warning("alert %s not sent: %s", alert.get("kind"), exc)


def deliver(c, alert: dict) -> list[str]:
    return c.channels.deliver(render(alert, c.settings.app_url))


def status(c) -> dict:
    return {"channels": c.channels.names(), "via": c.notifier.name if c.notifier else "inline"}
