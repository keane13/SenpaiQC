"""ADK root-cause agent as its own Cloud Run service.

POST /analyse {investigation} -> {findings, trace, usage}. Reads events through the same
read-only templates as the API (BigQuery on GCP, SQLite locally).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server" / "api"))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402

from adapters.adk_agent import run_investigation  # noqa: E402
from config import get_settings  # noqa: E402
from container import get_container  # noqa: E402
from slices.learn.rca_tools import RcaToolbox  # noqa: E402

app = FastAPI(title="SenpaiQC root-cause agent")


@app.post("/analyse")
async def analyse(req: Request):
    s = get_settings()
    if not s.gemini_enabled:
        raise HTTPException(503, "GEMINI_API_KEY not configured")
    if req.headers.get("x-senpaiqc-agent-key") != s.demo_token and s.auth_mode == "demo":
        raise HTTPException(401, "bad agent key")
    inv = await req.json()
    c = get_container()
    tb = RcaToolbox(c.events, c.cards, inv)
    import anyio

    usage = await anyio.to_thread.run_sync(run_investigation, tb, s.text_model, s.gemini_api_key)
    return {
        "findings": tb.findings.model_dump() if tb.findings else None,
        "trace": tb.trace, "usage": usage, "model": f"adk-agent:{s.text_model}",
    }


@app.get("/health")
def health():
    return {"ok": True}
