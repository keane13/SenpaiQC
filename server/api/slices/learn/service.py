"""Learn slice: SPC flags, root-cause investigations, 8D drafts, dashboard numbers."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.models import EIGHT_D_KEYS, EightDReport, Investigation
from domain.spc import Subgroup, p_chart

from .rca_tools import RcaToolbox, z_two_prop

BASELINE_SUBGROUPS = 20  # phase-I: first 10 days x 2 shifts


def spc_chart(c, part_number: str, defect: str) -> list[dict]:
    rows = c.events.query("shift_rates", {"part_number": part_number, "defect": defect})
    subgroups = [Subgroup(f"{r['day']}/{r['shift']}", int(r["n"]), int(r["d"] or 0)) for r in rows]
    base = BASELINE_SUBGROUPS if len(subgroups) > BASELINE_SUBGROUPS + 4 else None
    return [p.__dict__ for p in p_chart(subgroups, base)]


def scan(c, part_number: str, defects: list[str]) -> list[Investigation]:
    """Run the p-chart rule; the first out-of-control subgroup per defect opens one investigation."""
    opened = []
    existing = {(i["defect_name"], i["part_number"]) for i in c.docs.list("investigations", 500)
                if i["status"] != "closed"}
    for defect in defects:
        if (defect, part_number) in existing:
            continue
        chart = spc_chart(c, part_number, defect)
        ooc = next((p for p in chart if p["out_of_control"]), None)
        if not ooc:
            continue
        days = sorted({p["key"].split("/")[0] for p in chart})
        inv = Investigation(
            id=f"INV-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
            defect_name=defect, shift_key=ooc["key"], rate=round(ooc["p"], 4),
            ucl=round(ooc["ucl"], 4), center=round(ooc["center"], 4),
        )
        doc = inv.model_dump(mode="json") | {
            "part_number": part_number,
            "data_start": f"{days[0]}T00:00:00+00:00",
            "data_end": (datetime.fromisoformat(days[-1]) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00+00:00"),
        }
        c.docs.put("investigations", inv.id, doc)
        opened.append(doc)
    return opened


def analyse(c, inv_id: str) -> dict:
    inv = c.docs.get("investigations", inv_id)
    if inv is None:
        raise KeyError(inv_id)
    started = time.perf_counter()
    toolbox = RcaToolbox(c.events, c.cards, inv)
    if c.settings.agent_url:
        import httpx

        from .rca_tools import Findings

        headers = {"x-senpaiqc-agent-key": c.settings.demo_token}
        if c.settings.backend == "gcp":
            # The agent service is private on Cloud Run; call it with a Google-signed ID token.
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            headers["Authorization"] = f"Bearer {id_token.fetch_id_token(Request(), c.settings.agent_url)}"
        r = httpx.post(f"{c.settings.agent_url.rstrip('/')}/analyse", json=inv, timeout=300, headers=headers)
        r.raise_for_status()
        body = r.json()
        toolbox.trace = body["trace"]
        toolbox.findings = Findings(**body["findings"]) if body["findings"] else None
        usage, analyst = body["usage"], body["model"]
        cost = usage["input_tokens"] / 1e6 * c.settings.text_price_in + usage["output_tokens"] / 1e6 * c.settings.text_price_out
    elif c.settings.gemini_enabled:
        from adapters.adk_agent import run_investigation

        s = c.settings
        usage = run_investigation(toolbox, s.text_model, s.gemini_api_key,
                                  (s.gcp_project, s.vertex_location) if s.use_vertex else None)
        analyst = f"adk-agent:{c.settings.text_model}" + (" on Vertex AI" if c.settings.use_vertex else "")
        cost = usage["input_tokens"] / 1e6 * c.settings.text_price_in + usage["output_tokens"] / 1e6 * c.settings.text_price_out
    else:
        deterministic_analysis(toolbox)
        analyst = "deterministic-ranker (offline, no LLM)"
        cost = 0.0
    elapsed_s = time.perf_counter() - started
    if toolbox.findings is None:
        hypotheses, sections = [], {k: "" for k in EIGHT_D_KEYS}
        sections["D4_root_cause"] = "The agent did not return valid findings. Investigate manually."
    else:
        hypotheses = [h.model_dump() for h in toolbox.findings.hypotheses]
        sections = {k: toolbox.findings.sections.get(k, "") for k in EIGHT_D_KEYS}
    report = EightDReport(id=f"8D-{inv_id}", investigation_id=inv_id, sections=sections, generated_by=analyst)
    c.docs.put("reports", report.id, report.model_dump(mode="json"))
    flagged_at = datetime.fromisoformat(inv["created_at"])
    inv |= {
        "status": "analysed", "hypotheses": hypotheses, "agent_trace": toolbox.trace,
        "agent_model": analyst, "report_id": report.id,
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "analysis_seconds": round(elapsed_s, 1),
        "time_to_8d_minutes": round((datetime.now(timezone.utc) - flagged_at).total_seconds() / 60, 2),
        "analysis_cost_usd": round(cost, 6),
    }
    c.docs.put("investigations", inv_id, inv)
    return inv


def deterministic_analysis(tb: RcaToolbox) -> None:
    """Offline analyst: the same tools the agent uses, ranked by a two-proportion z-test.

    Used when Gemini is unavailable and as a sanity baseline in eval; never presented as AI.
    """
    ctx = tb.get_process_context()
    before, after = ctx["suggested_before"], ctx["suggested_after"]
    single = []
    for dim in ("machine_id", "mould_id", "material_lot", "shift"):
        rows_a = tb.query_events("rate_by_dim", json.dumps({"dim": dim, **after})).get("rows", [])
        rows_b = {r["value"]: r for r in tb.query_events("rate_by_dim", json.dumps({"dim": dim, **before})).get("rows", [])}
        tot_n, tot_d = sum(r["n"] for r in rows_a), sum(r["d"] or 0 for r in rows_a)
        for r in rows_a:
            z = z_two_prop(r["d"] or 0, r["n"], tot_d - (r["d"] or 0), tot_n - r["n"])
            b = rows_b.get(r["value"])
            single.append({"blamed": {dim: r["value"]}, "z": z, "rate_after": r["rate"],
                           "n_after": r["n"], "rate_before": b["rate"] if b else None})
    pairs = tb.query_events("rate_by_mould_lot", json.dumps({**after, "min_n": 30})).get("rows", [])
    tot_n, tot_d = sum(r["n"] for r in pairs), sum(r["d"] or 0 for r in pairs)
    pair_h = []
    for r in pairs:
        z = z_two_prop(r["d"] or 0, r["n"], tot_d - (r["d"] or 0), tot_n - r["n"])
        pair_h.append({"blamed": {"mould_id": r["mould_id"], "material_lot": r["material_lot"]},
                       "z": z, "rate_after": r["rate"], "n_after": r["n"], "rate_before": None})
    ranked = sorted(single + pair_h, key=lambda h: h["z"], reverse=True)[:3]
    hyps = []
    for i, h in enumerate(ranked, 1):
        who = ", ".join(f"{k}={v}" for k, v in h["blamed"].items())
        ev = [f"after-window rate {h['rate_after']:.1%} on n={h['n_after']} (z={h['z']:.1f} vs rest)"]
        if h["rate_before"] is not None:
            ev.append(f"before-window rate {h['rate_before']:.1%}")
        hyps.append({"rank": i, "statement": f"{ctx['defect_name']} spike driven by {who}", "blamed": h["blamed"],
                     "evidence": ev, "confidence": "high" if h["z"] > 6 else "medium" if h["z"] > 3 else "low"})
    top = hyps[0] if hyps else None
    who = ", ".join(f"{k} {v}" for k, v in top["blamed"].items()) if top else "unknown"
    sections = {
        "D1_team": "QC engineer (owner), senior inspector, casting line lead, material receiving.",
        "D2_problem": f"{ctx['defect_name']} rate {ctx['rate']:.1%} on {ctx['part_number']} in subgroup "
                      f"{ctx['flagged_subgroup']} exceeded the p-chart UCL {ctx['ucl']:.1%} (centre {ctx['center_line']:.1%}).",
        "D3_containment": f"Quarantine and 100% inspect parts from {who} since the spike started; hold remaining stock.",
        "D4_root_cause": (f"Leading hypothesis: {top['statement']}. Evidence: {'; '.join(top['evidence'])}." if top
                          else "No dominant factor found."),
        "D5_corrective_actions": "To be decided by the QC engineer after verifying the hypothesis on the floor.",
        "D6_implementation": "To be completed by the QC engineer.",
        "D7_prevention": "Add the blamed factor to incoming checks and keep the p-chart rule active.",
        "D8_recognition": "To be completed by the QC engineer.",
    }
    tb.draft_8d(json.dumps({"hypotheses": hyps, "sections": sections}))


def get_report(c, report_id: str) -> Optional[dict]:
    return c.docs.get("reports", report_id)


def update_report(c, report_id: str, sections: dict[str, str], editor: str, approve: bool) -> dict:
    rep = c.docs.get("reports", report_id)
    if rep is None:
        raise KeyError(report_id)
    rep["sections"] = {k: sections.get(k, rep["sections"].get(k, "")) for k in EIGHT_D_KEYS}
    rep["edited_by"] = editor
    rep["updated_at"] = datetime.now(timezone.utc).isoformat()
    if approve:
        rep["status"] = "approved"
    c.docs.put("reports", report_id, rep)
    return rep


def dashboard(c, since: Optional[datetime] = None) -> dict:
    start = since or datetime(2000, 1, 1, tzinfo=timezone.utc)
    summary = c.events.query("path_summary", {"start": start})
    pareto = c.events.query("pareto", {"start": start})
    daily = c.events.query("daily", {"start": start})
    lat = c.events.query("latencies", {"start": start})

    def agg(rows, synthetic):
        rows = [r for r in rows if int(r["synthetic"]) == synthetic]
        n = sum(r["n"] for r in rows)
        er2 = sum(r["n"] for r in rows if r["path"] == "er2")
        cost = sum(r["cost_usd"] or 0 for r in rows)
        by_dec = {}
        for r in rows:
            by_dec[r["decision"]] = by_dec.get(r["decision"], 0) + r["n"]
        return {"parts": n, "escalation_rate": er2 / n if n else None,
                "cost_per_1000_usd": (cost / n * 1000) if n else None, "decisions": by_dec}

    def p95(path):
        xs = sorted(r["latency_ms"] for r in lat if r["path"] == path)
        return xs[int(0.95 * (len(xs) - 1))] if xs else None

    return {
        "measured": agg(summary, 0) | {"p95_latency_yolo_ms": p95("yolo"), "p95_latency_er2_ms": p95("er2")},
        "synthetic": agg(summary, 1),
        "pareto": pareto,
        "daily": daily,
        "investigations": c.docs.list("investigations", 100),
        "mode": c.mode(),
    }
