"""SenpaiQC API (FastAPI on Cloud Run)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import REPO_ROOT, get_settings
from container import get_container
from guards import SECURITY_HEADERS, usage
from slices.act.router import router as act_router
from slices.ask.router import router as ask_router
from slices.inspect.router import router as inspect_router
from slices.learn.router import router as learn_router
from slices.teach.router import router as teach_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app):
    get_settings().check_deploy_secrets()
    get_container()  # load YOLO weights and clients at cold start, not on the first request
    yield


app = FastAPI(title="SenpaiQC API", version="0.1.0", lifespan=lifespan)
if get_settings().cors_origins:  # only needed when the web app is hosted elsewhere (Firebase option)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
        allow_methods=["*"], allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response
for r in (teach_router, inspect_router, act_router, learn_router, ask_router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "mode": get_container().mode(), "policy": get_container().policy.__dict__, "limits": usage()}


# Single-service deploy: the same Cloud Run service also serves the built web app.
WEB_DIST = REPO_ROOT / "client" / "dist"
if WEB_DIST.exists():

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (WEB_DIST / path).resolve()
        if path and f.is_file() and WEB_DIST.resolve() in f.parents and f.name != "index.html":
            # Hashed bundles never change, so browsers may keep them.
            cache = "public, max-age=31536000, immutable" if "/assets/" in f.as_posix() else "no-cache"
            return FileResponse(f, headers={"Cache-Control": cache})
        # SPA fallback; no-cache so a redeploy shows up on the next visit.
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
