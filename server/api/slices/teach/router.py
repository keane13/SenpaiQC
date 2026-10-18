from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from auth import current_user
from config import get_settings
from container import get_container
from guards import ai_quota_video

from . import service

router = APIRouter(prefix="/teach", tags=["teach"])


@router.post("/videos")
async def upload_video(part_number: str = Form(...), video: UploadFile = File(...), user: str = Depends(ai_quota_video)):
    s = get_settings()
    # Through the API only on Cloud Run's 32 MiB cap; locally there is no proxy limit.
    limit = s.max_video_mb if s.backend == "gcp" else s.max_video_upload_mb
    data = await video.read(limit * 1024 * 1024 + 1)
    if len(data) > limit * 1024 * 1024:
        raise HTTPException(413, f"Video larger than {limit} MB for direct upload. The app uploads larger videos straight to Cloud Storage; refresh and try again.")
    if not (video.content_type or "").startswith("video/"):
        raise HTTPException(415, "expected a video file")
    return service.draft_from_video(get_container(), data, video.content_type, video.filename or "clip.mp4", part_number)


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size: int


@router.post("/upload-url")
def upload_url(body: UploadRequest, user: str = Depends(current_user)):
    try:
        return service.upload_url(get_container(), body.filename, body.content_type, body.size)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class FromUpload(BaseModel):
    uri: str
    content_type: str
    part_number: str


@router.post("/videos/from-upload")
def video_from_upload(body: FromUpload, user: str = Depends(ai_quota_video)):
    try:
        return service.draft_from_upload(get_container(), body.uri, body.content_type, body.part_number)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/cards")
def list_cards(part_number: Optional[str] = None, status: Optional[str] = None, user: str = Depends(current_user)):
    return [c.model_dump(mode="json") for c in get_container().cards.list(part_number, status)]


class CardPatch(BaseModel):
    defect_name: Optional[str] = None
    visual_cues: Optional[list[str]] = None
    typical_location: Optional[str] = None
    inspection_view: Optional[str] = None
    accept_limit: Optional[str] = None
    severity: Optional[str] = None
    rework_action: Optional[str] = None


@router.put("/cards/{card_id}")
def edit_card(card_id: str, patch: CardPatch, user: str = Depends(current_user)):
    try:
        return service.update_card(get_container(), card_id, patch.model_dump(exclude_none=True)).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "card not found")


@router.post("/cards/{card_id}/approve")
def approve(card_id: str, user: str = Depends(current_user)):
    try:
        return service.approve_card(get_container(), card_id, user).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "card not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
