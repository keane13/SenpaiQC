"""Inspect slice: YOLO on every image, escalate to ER 2 by policy, log everything."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np

from domain.models import (
    Decision, DefectFinding, InspectionEvent, InspectionResult, LineContext, YoloOutput,
)
from domain.policy import GOOD_CLASS, needs_confirm, yolo_decision


def image_size(image: bytes) -> tuple[int, int]:
    arr = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise ValueError("not a decodable image")
    return arr.shape[1], arr.shape[0]


def inspect(c, image: bytes, mime_type: str, part_number: str, ctx: LineContext,
            force_path: Optional[str] = None) -> InspectionResult:
    started = time.perf_counter()
    width, height = image_size(image)
    decision_id = f"D-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    uri = c.blobs.save(f"line/{datetime.now(timezone.utc):%Y-%m-%d}/{decision_id}.jpg", image, mime_type)
    cards = c.cards.list(part_number=part_number, status="approved")

    pred = c.vision.predict(image)
    path, reason = c.policy.route(pred.class_, pred.confidence, c.vision.known_classes(),
                                  c.vision.label_count(part_number))
    if force_path in ("yolo", "er2") and not (force_path == "yolo" and pred.class_ is None):
        path, reason = force_path, (f"forced: {force_path}" if force_path != path else reason)

    cost = 0.0
    reasoning_model = None
    confidence = None
    if path == "yolo":
        decision = yolo_decision(pred.class_, cards)
        card = next((x for x in cards if x.defect_name == pred.class_), None)
        defects = [] if pred.class_ == GOOD_CLASS else [
            DefectFinding(card_id=card.card_id if card else None, label=pred.class_,
                          severity=card.severity if card else "major")]
        rationale = f"YOLO {pred.class_} at {pred.confidence:.2f} (≥ {c.policy.keep_threshold})."
        flag = needs_confirm(decision, any_uncited=False, model_flag=False)
    else:
        out = c.reasoning.inspect(image, mime_type, width, height, part_number, cards)
        reasoning_model = out.usage.model
        cost = out.usage.cost_usd
        confidence = out.confidence
        defects = out.defects
        decision = Decision(out.decision)
        uncited = any(d.card_id is None for d in defects)
        if uncited and decision == Decision.pass_:
            decision = Decision.rework  # an unknown defect can never pass silently
        rationale = out.rationale
        flag = needs_confirm(decision, uncited, out.needs_human_confirm or not out.schema_valid)

    result = InspectionResult(
        id=decision_id, image_uri=uri, part_number=part_number, path=path,
        yolo=YoloOutput(class_=pred.class_, confidence=round(pred.confidence, 4)),
        defects=defects, decision=decision, rationale=rationale, needs_human_confirm=flag,
        latency_ms=int((time.perf_counter() - started) * 1000), cost_usd=round(cost, 6),
        escalation_reason=reason, reasoning_model=reasoning_model, confidence=confidence, image_size=[width, height],
    )
    doc = result.model_dump(mode="json", by_alias=True) | {"line": ctx.model_dump(), "event_written": False}
    c.docs.put("decisions", decision_id, doc)
    if not flag:
        _emit(c, doc, confirmed=False)
    return result


def confirm(c, decision_id: str, user: str, decision: Optional[str], defect_name: Optional[str]) -> dict:
    """Human confirm. Overrides are kept; the BigQuery event is written once, here."""
    doc = c.docs.get("decisions", decision_id)
    if doc is None:
        raise KeyError(decision_id)
    if decision:
        doc["model_decision"] = doc["decision"]
        doc["decision"] = Decision(decision).value
    if defect_name is not None:
        doc["confirmed_defect_name"] = defect_name or None
    doc["confirmed"] = True
    doc["confirmed_by"] = user
    doc["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    if not doc.get("event_written"):
        _emit(c, doc, confirmed=True)
    c.docs.put("decisions", decision_id, doc)
    return doc


def _defect_name(c, doc: dict) -> Optional[str]:
    if doc["decision"] == "pass":
        return None
    if doc.get("confirmed_defect_name"):
        return doc["confirmed_defect_name"]
    for d in doc.get("defects", []):
        if d.get("card_id"):
            card = c.cards.get(d["card_id"])
            if card:
                return card.defect_name
        if d.get("label"):
            return d["label"]
    return doc.get("yolo", {}).get("class") or "unknown"


def _emit(c, doc: dict, confirmed: bool) -> None:
    line = doc["line"]
    c.events.write(InspectionEvent(
        event_ts=datetime.now(timezone.utc), line_id=line["line_id"], shift=line["shift"],
        machine_id=line["machine_id"], mould_id=line["mould_id"], material_lot=line["material_lot"],
        part_number=doc["part_number"], path=doc["path"], defect_name=_defect_name(c, doc),
        decision=doc["decision"], confirmed=confirmed, latency_ms=doc["latency_ms"], cost_usd=doc["cost_usd"],
    ))
    doc["event_written"] = True
    c.docs.put("decisions", doc["id"], doc)
