"""Ask SenpaiQC: questions answered only from the plant's own records.

Retrieval is deliberately simple: the corpus is small (rule cards, a few investigations and
reports, statistics and evaluation summaries), so keyword scoring over a few dozen documents is
enough and fully explainable. No vector database, no web search.
Guardrails: input length limits, sources passed as data, citations checked against what was
retrieved, answers marked ungrounded when they cite nothing valid.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from config import REPO_ROOT

MAX_QUESTION = 500
MAX_HISTORY_CHARS = 2000
CONTEXT_BUDGET = 24_000  # characters of sources per question

# Floor vocabulary in Bahasa Indonesia mapped to the English terms the records use.
SYNONYMS = {
    "porositas": "porosity", "pori": "porosity", "lubang": "porosity pinhole",
    "retak": "crack", "retakan": "crack", "susut": "shrinkage", "penyusutan": "shrinkage",
    "sirip": "burr flash", "gram": "burr", "cacat": "defect", "skrap": "scrap", "buang": "scrap",
    "perbaiki": "rework", "perbaikan": "rework", "batas": "limit accept", "terima": "accept",
    "akar": "root cause", "penyebab": "cause root", "laporan": "report 8d", "cetakan": "mould",
    "lot": "lot material", "mesin": "machine", "akurasi": "accuracy recall eval", "model": "model yolo eval",
    "biaya": "cost", "latensi": "latency", "pelatihan": "training yolo", "data": "data dataset",
}
STOP = set("the a an of to in on for and or is are was be it this that what which how why when where who with "
           "yang dan di ke dari untuk apa bagaimana kenapa mengapa ini itu ada dengan atau berapa".split())


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        out.append(w)
        out.extend(SYNONYMS.get(w, "").split())
    return out


def _fmt_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def build_corpus(c) -> list[dict]:
    docs: list[dict] = []
    for card in c.cards.list():
        status = "APPROVED" if card.status.value == "approved" else "DRAFT (not used on the line)"
        docs.append({
            "id": f"card:{card.card_id}", "type": "expert_rule", "page": "knowledge",
            "title": f"Expert rule: {card.defect_name} on {card.part_number} ({status.split()[0].lower()})",
            "text": (f"Status: {status}. Approved by: {card.approved_by or 'nobody yet'}.\n"
                     f"Defect: {card.defect_name}. Severity: {card.severity.value}.\n"
                     f"Looks like: {'; '.join(card.visual_cues)}.\nWhere: {card.typical_location}.\n"
                     f"How to look: {getattr(card, 'inspection_view', '') or 'not stated'}.\n"
                     f"Accept if: {card.accept_limit}.\nHow to fix: {card.rework_action}.\n"
                     f"Source: {card.source_video} {card.source_timestamp}".strip()),
        })

    for inv in c.docs.list("investigations", 100):
        hyps = "\n".join(f"#{h['rank']} {h['statement']} (blames {h['blamed']}; evidence: {'; '.join(h['evidence'])}; "
                         f"confidence {h['confidence']})" for h in inv.get("hypotheses", []))
        docs.append({
            "id": f"investigation:{inv['id']}", "type": "investigation", "page": "analytics",
            "title": f"Investigation {inv['id']}: {inv['defect_name']} spike on {inv.get('part_number', '')}",
            "text": (f"Status: {inv['status']}. Flagged subgroup {inv['shift_key']}: rate {_fmt_pct(inv['rate'])}, "
                     f"control limit {_fmt_pct(inv['ucl'])}, normal {_fmt_pct(inv['center'])}. "
                     f"Analysed by: {inv.get('agent_model') or 'not yet'}. "
                     f"Flag to 8D draft: {inv.get('time_to_8d_minutes', 'n/a')} min. "
                     "Process data behind this investigation is SYNTHETIC unless stated otherwise.\n"
                     f"Hypotheses:\n{hyps or 'none yet'}"),
        })
        if inv.get("report_id"):
            rep = c.docs.get("reports", inv["report_id"])
            if rep:
                body = "\n".join(f"{k}: {v}" for k, v in rep.get("sections", {}).items() if v)
                docs.append({
                    "id": f"report:{rep['id']}", "type": "8d_report", "page": "reports",
                    "title": f"8D report {rep['id']} ({rep.get('status', 'draft')})",
                    "text": f"Status: {rep.get('status')}. Drafted by {rep.get('generated_by')}; edited by {rep.get('edited_by') or 'nobody yet'}.\n{body}",
                })

    from slices.learn.service import dashboard

    try:
        d = dashboard(c)
        m, s = d["measured"], d["synthetic"]
        pareto = ", ".join(f"{r['defect_name']} {r['n']}" for r in d["pareto"])
        docs.append({
            "id": "stats:line", "type": "statistics", "page": "analytics",
            "title": "Line statistics (live and synthetic)",
            "text": (f"Live (measured by this deployment): {m['parts']} parts, escalated to Gemini {_fmt_pct(m['escalation_rate'])}, "
                     f"decisions {m['decisions']}, cost per 1,000 parts {m['cost_per_1000_usd']}, "
                     f"p95 latency fast path {m['p95_latency_yolo_ms']} ms, Gemini path {m['p95_latency_er2_ms']} ms.\n"
                     f"SYNTHETIC process history: {s['parts']} parts, decisions {s['decisions']}.\n"
                     f"Defect Pareto (live + synthetic, rejected parts): {pareto or 'none'}."),
        })
    except Exception:  # statistics are helpful, never required
        pass

    decisions = c.docs.list("decisions", 500)
    if decisions:
        by = Counter(x["decision"] for x in decisions)
        overrides = [x for x in decisions if x.get("model_decision") and x["model_decision"] != x["decision"]]
        cited = Counter(f["card_id"] for x in decisions for f in x.get("defects", []) if f.get("card_id"))
        waiting = sum(1 for x in decisions if x.get("needs_human_confirm") and not x.get("confirmed"))
        docs.append({
            "id": "stats:decisions", "type": "statistics", "page": "queue",
            "title": "Recent inspection decisions",
            "text": (f"Last {len(decisions)} decisions: {dict(by)}. Waiting for a person: {waiting}. "
                     f"Human overrides of the AI: {len(overrides)}. Most cited expert rules: {dict(cited.most_common(5))}."),
        })

    ev = REPO_ROOT / "eval" / "results" / "summary.json"
    if ev.exists():
        e = json.loads(ev.read_text())
        rc = e.get("root_cause") or {}
        docs.append({
            "id": "eval:summary", "type": "evaluation", "page": "analytics",
            "title": f"Evaluation on the held-out golden set ({e.get('generated_at', '')[:10]})",
            "text": (f"Golden set n={e.get('golden_n')} held-out images. Recall {_fmt_pct(e.get('recall'))}, "
                     f"false reject rate {_fmt_pct(e.get('false_reject_rate'))}, escalation rate {_fmt_pct(e.get('escalation_rate_before'))}"
                     f" (after retrain: {_fmt_pct(e.get('escalation_rate_after'))}), card citation accuracy {_fmt_pct(e.get('card_citation_accuracy'))}, "
                     f"p95 latency YOLO {e.get('p95_latency_yolo_ms')} ms, ER 2 {e.get('p95_latency_er2_ms')} ms, "
                     f"cost per 1,000 parts ${e.get('cost_per_1000_parts_usd')}. Root cause hit: {e.get('root_cause_hit')} "
                     f"(analyst {rc.get('analyst')}, {rc.get('tool_calls')} tool calls, flag to 8D {e.get('time_to_8d_minutes')} min). "
                     f"Notes: {' '.join(e.get('notes', []))}"),
        })
    for name in ("yolo_baseline.json", "yolo_retrain.json"):
        p = REPO_ROOT / "eval" / "results" / name
        if p.exists():
            y = json.loads(p.read_text())
            docs.append({
                "id": f"training:{y.get('name', name)}", "type": "model_training", "page": "analytics",
                "title": f"YOLO training run '{y.get('name')}'",
                "text": f"YOLO classification model, validation top-1 accuracy {_fmt_pct(y.get('top1'))}, "
                        f"{y.get('epochs')} epochs, image size {y.get('imgsz')} px, weights {y.get('weights')}. "
                        "Trained on the public casting dataset (pump impellers, ok vs defective).",
            })
    return docs


def retrieve(docs: list[dict], question: str, k: int = 10) -> list[dict]:
    q = Counter(_tokens(question))
    scored = []
    for d in docs:
        words = Counter(_tokens(d["title"] + " " + d["text"]))
        overlap = sum(min(n, words[w]) * (2 if w in _tokens(d["title"]) else 1) for w, n in q.items())
        scored.append((overlap, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    picked, used = [], 0
    for score, d in scored:
        if len(picked) >= k:
            break
        if score == 0 and len(picked) >= 4:  # keep a few general sources even with no keyword hit
            continue
        if used + len(d["text"]) > CONTEXT_BUDGET:
            continue
        picked.append(d)
        used += len(d["text"])
    return picked


def ask(c, question: str, history: list[dict]) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("Ask a question.")
    if len(question) > MAX_QUESTION:
        raise ValueError(f"Keep the question under {MAX_QUESTION} characters.")
    trimmed, size = [], 0
    for h in reversed(history[-6:]):
        t = str(h.get("text", ""))[:600]
        if size + len(t) > MAX_HISTORY_CHARS:
            break
        trimmed.insert(0, {"role": "assistant" if h.get("role") == "assistant" else "user", "text": t})
        size += len(t)

    sources = retrieve(build_corpus(c), question)
    out = c.qa.answer(question, sources, trimmed)
    valid = {d["id"]: d for d in sources}
    cited = [cid for cid in dict.fromkeys(out.citations) if cid in valid]
    grounded = out.grounded and bool(cited)
    return {
        "answer": out.text,
        "grounded": grounded,
        "citations": [{"id": cid, "title": valid[cid]["title"], "type": valid[cid]["type"], "page": valid[cid]["page"]} for cid in cited],
        "dropped_citations": [x for x in out.citations if x not in valid],
        "follow_ups": out.follow_ups,
        "sources_considered": len(sources),
        "model": out.usage.model, "latency_ms": out.usage.latency_ms, "cost_usd": out.usage.cost_usd,
    }
