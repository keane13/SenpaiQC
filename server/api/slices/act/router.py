from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from auth import current_user
from guards import ai_quota
from container import get_container

from . import service

router = APIRouter(prefix="/act", tags=["act"])


@router.get("/guide/{decision_id}")
def guide(decision_id: str, lang: str = "en", user: str = Depends(ai_quota)):
    try:
        return service.guide(get_container(), decision_id, lang)
    except KeyError:
        raise HTTPException(404, "decision not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/robot/{decision_id}")
def robot(decision_id: str, user: str = Depends(ai_quota)):
    try:
        return service.run_robot(get_container(), decision_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except KeyError:
        raise HTTPException(404, "decision not found")


@router.get("/second-look/stats")
def second_look_stats(user: str = Depends(current_user)):
    return service.second_look_stats(get_container())


@router.get("/second-look/{episode_id}/image")
def second_look_image(episode_id: str, token: str = ""):
    # <img> tags cannot send headers, so the token comes as a query parameter (as for decision images).
    from auth import current_user as _check
    from config import get_settings

    _check(authorization=f"Bearer {token}", s=get_settings())
    c = get_container()
    rec = c.docs.get("episodes", episode_id)
    uri = ((rec or {}).get("second_look") or {}).get("view_uri")
    if not uri:
        raise HTTPException(404, "no second-look view for this episode")
    return Response(c.blobs.load(uri), media_type="image/jpeg")


@router.get("/episodes")
def episodes(user: str = Depends(current_user)):
    return get_container().docs.list("episodes", 50)


@router.get("/episodes/{episode_id}")
def episode(episode_id: str, user: str = Depends(current_user)):
    try:
        return service.episode_frames(get_container(), episode_id)
    except KeyError:
        raise HTTPException(404, "episode not found")
