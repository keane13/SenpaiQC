from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from guards import ai_quota_agent
from config import REPO_ROOT
from container import get_container

from . import labels, service

router = APIRouter(prefix="/learn", tags=["learn"])


@router.get("/dashboard")
def dashboard(user: str = Depends(current_user)):
    return service.dashboard(get_container())


@router.get("/spc")
def spc(part_number: str = "IMP-200", defect: str = "porosity", user: str = Depends(current_user)):
    return service.spc_chart(get_container(), part_number, defect)


class ScanBody(BaseModel):
    part_number: str = "IMP-200"
    defects: list[str] = ["porosity", "shrinkage", "crack", "burr"]


@router.post("/scan")
def scan(body: ScanBody, user: str = Depends(current_user)):
    return service.scan(get_container(), body.part_number, body.defects)


@router.get("/investigations")
def investigations(user: str = Depends(current_user)):
    return get_container().docs.list("investigations", 100)


@router.post("/investigations/{inv_id}/analyse")
def analyse(inv_id: str, user: str = Depends(ai_quota_agent)):
    try:
        return service.analyse(get_container(), inv_id)
    except KeyError:
        raise HTTPException(404, "investigation not found")
    except Exception as exc:  # Gemini quota or outage: say so instead of a bare 500
        text = str(exc)
        if "402" in text or "credits are depleted" in text:
            raise HTTPException(503, "Gemini billing credits for this project are used up. Top up in AI Studio, then press Find root cause again.") from exc
        if "429" in text or "RESOURCE_EXHAUSTED" in text:
            raise HTTPException(503, "Gemini quota reached for now. Wait a minute and press Find root cause again.") from exc
        raise HTTPException(503, "The root-cause agent could not finish. Try again in a minute.") from exc


@router.get("/reports/{report_id}")
def report(report_id: str, user: str = Depends(current_user)):
    r = service.get_report(get_container(), report_id)
    if r is None:
        raise HTTPException(404, "report not found")
    return r


class ReportEdit(BaseModel):
    sections: dict[str, str]
    approve: bool = False


@router.get("/reports/{report_id}/docx")
def report_docx(report_id: str, user: str = Depends(current_user)):
    from fastapi.responses import Response

    from .docx_export import report_docx as build

    c = get_container()
    r = service.get_report(c, report_id)
    if r is None:
        raise HTTPException(404, "report not found")
    inv = c.docs.get("investigations", r["investigation_id"]) if r.get("investigation_id") else None
    return Response(build(r, inv), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}.docx"'})


@router.put("/reports/{report_id}")
def edit_report(report_id: str, body: ReportEdit, user: str = Depends(current_user)):
    try:
        return service.update_report(get_container(), report_id, body.sections, user, body.approve)
    except KeyError:
        raise HTTPException(404, "report not found")


@router.post("/labels/export")
def export(part_number: str = "IMP-200", user: str = Depends(current_user)):
    return labels.export_labels(get_container(), part_number)


@router.get("/eval")
def eval_summary(user: str = Depends(current_user)):
    """The dashboard's metric tiles read eval/results/summary.json only (never projected)."""
    import json

    p = REPO_ROOT / "eval" / "results" / "summary.json"
    if not p.exists():
        return {"available": False}
    return {"available": True} | json.loads(p.read_text())
