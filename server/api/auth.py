"""Auth: a fixed demo token for judges locally, or Firebase ID tokens on GCP."""
from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Header, HTTPException

from config import Settings, get_settings


def current_user(authorization: str = Header(default=""), s: Settings = Depends(get_settings)) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "missing bearer token")
    if s.auth_mode == "demo":
        if not hmac.compare_digest(token.encode(), s.demo_token.encode()):
            raise HTTPException(401, "invalid demo token")
        return "demo-inspector"
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_firebase_token(token, grequests.Request(), audience=s.gcp_project)
    except Exception as exc:
        logging.getLogger(__name__).info("Firebase token rejected: %s", exc)
        raise HTTPException(401, "invalid or expired sign-in") from exc
    return claims.get("email") or claims["user_id"]
