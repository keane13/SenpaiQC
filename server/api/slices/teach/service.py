"""Teach slice: expert video -> draft Defect Knowledge Cards -> human approval."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone

from domain.models import CardStatus, DefectKnowledgeCard


UPLOAD_PREFIX = "teach/uploads/"
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/3gpp", "video/x-msvideo", "video/mpeg", "video/x-matroska"}


def _safe_name(filename: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename or "clip.mp4").strip("-.")
    return (name or "clip.mp4")[-80:]


def draft_from_video(c, video: bytes, mime_type: str, filename: str, part_number: str) -> dict:
    path = f"teach/{datetime.now(timezone.utc):%Y%m%d}/{uuid.uuid4().hex[:8]}-{_safe_name(filename)}"
    uri = c.blobs.save(path, video, mime_type)
    cards, usage = c.text.draft_cards(video, mime_type, part_number, uri)
    return _save_drafts(c, cards, usage, uri)


def upload_url(c, filename: str, content_type: str, size: int) -> dict:
    """Large videos: a signed URL straight to Cloud Storage (bypasses Cloud Run's 32 MiB cap)."""
    s = c.settings
    if content_type not in VIDEO_TYPES:
        raise ValueError("Use an MP4, MOV, WEBM or 3GP video.")
    limit = s.max_video_upload_mb * 1024 * 1024
    if size > limit:
        raise ValueError(f"Video is {size / 2**20:.0f} MB; the limit is {s.max_video_upload_mb} MB. Trim it to the part where the expert explains defects.")
    path = f"{UPLOAD_PREFIX}{datetime.now(timezone.utc):%Y%m%d}/{uuid.uuid4().hex}-{_safe_name(filename)}"
    try:
        signed = c.blobs.upload_url(path, content_type, limit)
    except Exception as exc:  # e.g. the service account may not sign URLs
        logging.getLogger(__name__).error("signed upload URL failed: %s", exc)
        raise ValueError(f"Large-video upload is not available on this server right now. Use a video under "
                         f"{s.max_video_mb} MB (about 1 minute at 720p), or ask the admin to check the deploy.") from exc
    if signed is None:  # local backend: no cap, upload through the API
        return {"mode": "direct", "max_mb": s.max_video_upload_mb}
    return {"mode": "signed", **signed, "max_mb": s.max_video_upload_mb}


def draft_from_upload(c, uri: str, mime_type: str, part_number: str) -> dict:
    """Draft cards from a video the browser uploaded to Cloud Storage with a signed URL."""
    if uri.startswith("gs://"):
        bucket, _, path = uri[5:].partition("/")
        if bucket != c.settings.gcs_bucket:
            raise ValueError("Unknown upload. Request a new upload link and try again.")
    else:
        path = uri.removeprefix("local://")
    if ".." in path or not path.startswith(UPLOAD_PREFIX):
        raise ValueError("Unknown upload. Request a new upload link and try again.")
    if mime_type not in VIDEO_TYPES:
        raise ValueError("Use an MP4, MOV, WEBM or 3GP video.")
    size = c.blobs.size(uri)
    if size is None:
        raise ValueError("The upload did not arrive. Check your connection and try again.")
    if size > c.settings.max_video_upload_mb * 1024 * 1024:
        raise ValueError(f"Video larger than {c.settings.max_video_upload_mb} MB.")
    if getattr(c.text, "reads_gcs", False) and uri.startswith("gs://"):
        cards, usage = c.text.draft_cards(None, mime_type, part_number, uri)
        return _save_drafts(c, cards, usage, uri)
    fd, tmp = tempfile.mkstemp(suffix=Path(path).suffix or ".mp4")
    os.close(fd)
    try:
        c.blobs.download_to_file(uri, tmp)
        cards, usage = c.text.draft_cards(Path(tmp), mime_type, part_number, uri)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return _save_drafts(c, cards, usage, uri)


def _save_drafts(c, cards, usage, uri: str) -> dict:
    saved = []
    for card in cards:
        existing = c.cards.get(card.card_id)
        if existing is not None:
            # Never overwrite an expert-approved card with a new draft: version it instead.
            n = 2
            while c.cards.get(f"{card.card_id.rsplit('-v', 1)[0]}-v{n}"):
                n += 1
            card.card_id = f"{card.card_id.rsplit('-v', 1)[0]}-v{n}"
        c.cards.put(card)
        saved.append(card)
    return {
        "source_video": uri,
        "cards": [x.model_dump(mode="json") for x in saved],
        "model": usage.model, "latency_ms": usage.latency_ms, "cost_usd": usage.cost_usd,
        "schema_valid": bool(saved) or usage.model.startswith("offline"),
    }


def update_card(c, card_id: str, patch: dict) -> DefectKnowledgeCard:
    card = c.cards.get(card_id)
    if card is None:
        raise KeyError(card_id)
    # Editing an approved card sends it back to draft: the expert must re-approve.
    patch = {k: v for k, v in patch.items() if k not in {"card_id", "status", "approved_by"}}
    updated = DefectKnowledgeCard(**(card.model_dump() | patch | {"status": CardStatus.draft, "approved_by": None}))
    c.cards.put(updated)
    return updated


def approve_card(c, card_id: str, approver: str) -> DefectKnowledgeCard:
    card = c.cards.get(card_id)
    if card is None:
        raise KeyError(card_id)
    if not card.accept_limit or not card.rework_action or card.defect_name == "fill_in":
        raise ValueError("card needs a defect_name, accept_limit and rework_action before approval")
    card.status = CardStatus.approved
    card.approved_by = approver
    c.cards.put(card)
    return card
