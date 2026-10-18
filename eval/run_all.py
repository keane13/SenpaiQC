"""Measure everything the deck and dashboard show. Writes eval/results/summary.json.

  python eval/run_all.py                         # golden set with the configured adapters
  python eval/run_all.py --weights-after runs/retrain/best.pt   # adds escalation after retrain
  python eval/run_all.py --skip-golden           # root-cause scenario only

Inputs
  data/golden/manifest.csv   path,label[,defect_name]   label in {ok, defective}; never trained on
  eval/citation_review.csv   decision_id,correct        hand-checked ER 2 citations (from sample_citations.py)
  data/planted_cause.json    truth for the synthetic root-cause scenario

Metrics are null when their inputs are missing; nothing is estimated or projected.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "server" / "api"
RESULTS = ROOT / "eval" / "results"


def fresh_container(work: Path, weights: str | None):
    """A container on an isolated local store, with the configured model adapters."""
    os.environ["LOCAL_DIR"] = str(work)
    os.environ["BACKEND"] = "local"
    if weights is not None:
        os.environ["YOLO_WEIGHTS"] = weights
    sys.path.insert(0, str(API))
    import config
    import container

    config.get_settings.cache_clear()
    container.get_container.cache_clear()
    return container.get_container()


def workdir(name: str) -> Path:
    """Isolated store for one run (SQLite stays open on Windows, so no temp-dir cleanup)."""
    base = RESULTS / ".work"
    if name == "golden-before":  # first run of an eval: clear stores left by earlier runs
        shutil.rmtree(base, ignore_errors=True)
    d = base / f"{name}-{uuid.uuid4().hex[:6]}"
    d.mkdir(parents=True)
    return d


def p95(xs: list[int]) -> int | None:
    xs = sorted(xs)
    return xs[int(0.95 * (len(xs) - 1))] if xs else None


def run_golden(weights: str | None, limit: int | None, name: str) -> dict:
    manifest = ROOT / "data" / "golden" / "manifest.csv"
    if not manifest.exists():
        return {"available": False, "reason": "data/golden/manifest.csv missing (run data/prepare_casting.py)"}
    rows = list(csv.DictReader(manifest.open()))[:limit]
    c = fresh_container(workdir(name), weights)
    from domain.models import DefectKnowledgeCard, LineContext
    from slices.inspect.service import inspect

    for d in json.loads((ROOT / "data" / "seed_cards.json").read_text()):
        c.cards.put(DefectKnowledgeCard(**d))
    out = []
    for r in rows:
        img = (ROOT / "data" / "golden" / r["path"]).read_bytes()
        res = inspect(c, img, "image/jpeg", "IMP-200", LineContext(line_id="EVAL"))
        out.append({"path": r["path"], "label": r["label"], "route": res.path, "decision": res.decision.value,
                    "latency_ms": res.latency_ms, "cost_usd": res.cost_usd, "id": res.id,
                    "cited": [d.card_id for d in res.defects], "model": res.reasoning_model})
    mode = c.mode()
    defective = [o for o in out if o["label"] == "defective"]
    good = [o for o in out if o["label"] == "ok"]
    return {
        "available": True, "n": len(out), "mode": mode,
        "recall": sum(o["decision"] != "pass" for o in defective) / len(defective) if defective else None,
        "false_reject_rate": sum(o["decision"] != "pass" for o in good) / len(good) if good else None,
        "escalation_rate": sum(o["route"] == "er2" for o in out) / len(out) if out else None,
        "p95_latency_yolo_ms": p95([o["latency_ms"] for o in out if o["route"] == "yolo"]),
        "p95_latency_er2_ms": p95([o["latency_ms"] for o in out if o["route"] == "er2"]),
        "cost_per_1000_parts_usd": sum(o["cost_usd"] for o in out) / len(out) * 1000 if out else None,
        "rows": out,
    }


def run_root_cause() -> dict:
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_process.py")], check=True, capture_output=True)
    truth = json.loads((ROOT / "data" / "planted_cause.json").read_text())
    c = fresh_container(workdir("root-cause"), None)
    from domain.models import DefectKnowledgeCard, InspectionEvent
    from slices.learn import service

    for d in json.loads((ROOT / "data" / "seed_cards.json").read_text()):
        c.cards.put(DefectKnowledgeCard(**d))
    with (ROOT / "data" / "process_events.csv").open() as f:
        c.events.write_many([InspectionEvent(**(r | {
            "event_ts": datetime.fromisoformat(r["event_ts"]), "defect_name": r["defect_name"] or None,
            "confirmed": r["confirmed"] == "True"})) for r in csv.DictReader(f)])
    invs = service.scan(c, truth["part_number"], ["porosity", "shrinkage", "crack", "burr"])
    target = next((i for i in invs if i["defect_name"] == truth["defect_name"]), None)
    if target is None:
        return {"root_cause_hit": False, "spc_flagged": False}
    inv = service.analyse(c, target["id"])
    top = inv["hypotheses"][0]["blamed"] if inv["hypotheses"] else {}
    hit = top.get("mould_id") == truth["mould_id"] and top.get("material_lot") == truth["material_lot"]
    return {
        "spc_flagged": True, "flagged_subgroup": target["shift_key"], "first_affected_date": truth["first_affected_date"],
        "root_cause_hit": hit, "top_hypothesis": top, "analyst": inv["agent_model"],
        "time_to_8d_minutes": inv["time_to_8d_minutes"], "analysis_seconds": inv["analysis_seconds"],
        "analysis_cost_usd": inv.get("analysis_cost_usd"), "tool_calls": len(inv["agent_trace"]),
    }


def citation_accuracy() -> dict:
    p = ROOT / "eval" / "citation_review.csv"
    if not p.exists():
        return {"card_citation_accuracy": None, "citation_reviewed": 0}
    rows = [r for r in csv.DictReader(p.open()) if r.get("correct", "").strip() in {"1", "0", "true", "false"}]
    ok = sum(r["correct"].strip() in {"1", "true"} for r in rows)
    return {"card_citation_accuracy": ok / len(rows) if rows else None, "citation_reviewed": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-before", default=None, help="YOLO weights for the baseline run (default: env)")
    ap.add_argument("--weights-after", default=None, help="YOLO weights after one teacher-student retrain")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-golden", action="store_true")
    a = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    notes = []
    before = {"available": False} if a.skip_golden else run_golden(a.weights_before, a.limit, "golden-before")
    after = run_golden(a.weights_after, a.limit, "golden-after") if (a.weights_after and not a.skip_golden) else None
    rca = run_root_cause()
    cit = citation_accuracy()

    if before.get("available"):
        (RESULTS / "golden_before.json").write_text(json.dumps(before, indent=1))
        if not before["mode"]["gemini"]:
            notes.append("Golden run used offline adapters (no GEMINI_API_KEY): escalated parts were not judged by ER 2.")
        if before["mode"]["fast_path"] == "none":
            notes.append("No YOLO weights: every part escalated.")
    else:
        notes.append(f"Golden set not evaluated: {before.get('reason', 'skipped')}.")
    if after:
        (RESULTS / "golden_after.json").write_text(json.dumps(after, indent=1))
    if "deterministic" in rca.get("analyst", ""):
        notes.append("Root-cause scenario used the offline deterministic ranker, not the ADK agent.")
    notes.append("Root-cause scenario runs on SYNTHETIC process data with a planted cause.")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": before.get("mode"),
        "golden_n": before.get("n"),
        "recall": before.get("recall"),
        "false_reject_rate": before.get("false_reject_rate"),
        "escalation_rate_before": before.get("escalation_rate"),
        "escalation_rate_after": after.get("escalation_rate") if after else None,
        "card_citation_accuracy": cit["card_citation_accuracy"],
        "citation_reviewed": cit["citation_reviewed"],
        "p95_latency_yolo_ms": before.get("p95_latency_yolo_ms"),
        "p95_latency_er2_ms": before.get("p95_latency_er2_ms"),
        "cost_per_1000_parts_usd": before.get("cost_per_1000_parts_usd"),
        "time_to_8d_minutes": rca.get("time_to_8d_minutes"),
        "root_cause_hit": rca.get("root_cause_hit"),
        "root_cause": rca,
        "notes": notes,
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "root_cause"}, indent=2))


if __name__ == "__main__":
    main()
