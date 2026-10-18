from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from auth import current_user
from guards import ai_quota
from container import get_container
from domain.models import LineContext

from . import service

router = APIRouter(tags=["inspect"])
MAX_IMAGE = 15 * 1024 * 1024


@router.post("/inspect")
async def inspect(
    image: UploadFile = File(...),
    part_number: str = Form("IMP-200"),
    line_id: str = Form("L1"), shift: str = Form("A"), machine_id: str = Form("MC-01"),
    mould_id: str = Form("MD-01"), material_lot: str = Form("LOT-0001"),
    force_path: Optional[str] = Form(None),
    user: str = Depends(ai_quota),
):
    data = await image.read()
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "image larger than 15 MB")
    ctx = LineContext(line_id=line_id, shift=shift, machine_id=machine_id, mould_id=mould_id, material_lot=material_lot)
    try:
        r = service.inspect(get_container(), data, image.content_type or "image/jpeg", part_number, ctx, force_path)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return r.model_dump(mode="json", by_alias=True)


@router.get("/decisions")
def list_decisions(pending: bool = False, limit: int = 100, user: str = Depends(current_user)):
    docs = sorted(get_container().docs.list("decisions", 5000), key=lambda d: d.get("created_at", ""), reverse=True)[:limit]
    if pending:
        docs = [d for d in docs if d.get("needs_human_confirm") and not d.get("confirmed")]
    return docs


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str, user: str = Depends(current_user)):
    d = get_container().docs.get("decisions", decision_id)
    if d is None:
        raise HTTPException(404, "decision not found")
    return d


class Confirm(BaseModel):
    decision: Optional[str] = None  # override: pass | rework | scrap
    defect_name: Optional[str] = None


@router.post("/decisions/{decision_id}/confirm")
def confirm(decision_id: str, body: Confirm, user: str = Depends(current_user)):
    try:
        return service.confirm(get_container(), decision_id, user, body.decision, body.defect_name)
    except KeyError:
        raise HTTPException(404, "decision not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/decisions/{decision_id}/image")
def decision_image(decision_id: str, token: str = ""):
    # <img> tags cannot send headers, so the token comes as a query parameter here.
    from auth import current_user as _check
    from config import get_settings

    _check(authorization=f"Bearer {token}", s=get_settings())
    c = get_container()
    d = c.docs.get("decisions", decision_id)
    if d is None:
        raise HTTPException(404, "decision not found")
    return Response(c.blobs.load(d["image_uri"]), media_type="image/jpeg")


SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"


@router.get("/samples")
def list_samples(user: str = Depends(current_user)):
    """Sample part photos for people without a part at hand (judges, training)."""
    if not SAMPLES.exists():
        return []
    meta = json.loads((SAMPLES / "samples.json").read_text()) if (SAMPLES / "samples.json").exists() else {}
    return [{"name": p.name, **meta.get(p.name, {})} for p in sorted(SAMPLES.glob("*.jp*g"))]


@router.get("/samples/{name}")
def sample_image(name: str):
    p = (SAMPLES / name).resolve()
    if SAMPLES.resolve() not in p.parents or not p.is_file() or p.suffix.lower() not in {".jpg", ".jpeg"}:
        raise HTTPException(404, "sample not found")
    return Response(p.read_bytes(), media_type="image/jpeg")
