from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from auth import current_user
from config import Settings, get_settings
from container import get_container
from guards import ai_quota

from . import service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/status")
def status(user: str = Depends(current_user)):
    return service.status(get_container())


@router.post("/test")
def send_test(user: str = Depends(ai_quota)):  # rate-limited like an AI call, so it cannot spam a chat
    c = get_container()
    if not c.channels.names():
        raise HTTPException(409, "No alert channel is configured on the server.")
    alert = service.sample_alert(user)
    if c.notifier is not None:
        c.notifier.publish(alert)
        return {"queued": True, "via": c.notifier.name}
    try:
        return {"sent": service.deliver(c, alert), "via": "inline"}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


def _verify_push(authorization: str, s: Settings) -> None:
    """Only Pub/Sub, signing as our own service account, may call the push endpoint."""
    if not (s.alert_push_audience and s.alert_push_sa):
        raise HTTPException(404)
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix("Bearer ").strip(), google_requests.Request(), audience=s.alert_push_audience)
    except Exception:
        raise HTTPException(401, "invalid push token")
    if claims.get("email") != s.alert_push_sa or not claims.get("email_verified"):
        raise HTTPException(403, "push token from an unexpected account")


@router.post("/push", include_in_schema=False)
async def push(request: Request, authorization: str = Header(default=""), s: Settings = Depends(get_settings)):
    _verify_push(authorization, s)
    try:
        envelope = await request.json()
        alert = json.loads(base64.b64decode(envelope["message"]["data"]))
    except Exception:
        return Response(status_code=204)  # malformed message: ack it, a retry would not fix it
    try:
        sent = service.deliver(get_container(), alert)
    except RuntimeError as exc:
        log.warning("%s; Pub/Sub will retry", exc)
        raise HTTPException(502, "delivery failed")
    log.info("alert %s delivered to %s", alert.get("kind"), sent or "no channel")
    return Response(status_code=204)
