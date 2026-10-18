"""Escalation policy and decision rules. Plain code, no model calls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Decision, DefectKnowledgeCard, Severity

GOOD_CLASS = "ok"


@dataclass(frozen=True)
class EscalationPolicy:
    keep_threshold: float = 0.85
    escalate_floor: float = 0.40
    min_labels_per_part: int = 50

    def route(
        self,
        yolo_class: Optional[str],
        confidence: float,
        known_classes: set[str],
        label_count: int,
    ) -> tuple[str, Optional[str]]:
        """Return ("yolo" | "er2", escalation_reason)."""
        if label_count < self.min_labels_per_part:
            return "er2", f"new part: {label_count} labels < {self.min_labels_per_part}"
        if yolo_class is None or yolo_class not in known_classes:
            return "er2", f"unknown class: {yolo_class!r}"
        if confidence >= self.keep_threshold:
            return "yolo", None
        if confidence >= self.escalate_floor:
            return "er2", f"uncertain: confidence {confidence:.2f} in [{self.escalate_floor}, {self.keep_threshold})"
        # Below the floor YOLO has essentially no opinion; treat it like unknown.
        return "er2", f"low confidence {confidence:.2f} < {self.escalate_floor}"


def yolo_decision(yolo_class: str, cards: list[DefectKnowledgeCard]) -> Decision:
    """Decision when the fast path is trusted. Defect class maps to its card's severity."""
    if yolo_class == GOOD_CLASS:
        return Decision.pass_
    card = next((c for c in cards if c.defect_name == yolo_class), None)
    if card is not None and card.severity == Severity.critical:
        return Decision.scrap
    return Decision.rework


def needs_confirm(decision: Decision, any_uncited: bool, model_flag: bool) -> bool:
    """Golden rule: every scrap and every unknown defect needs a human."""
    return decision == Decision.scrap or any_uncited or model_flag
