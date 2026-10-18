"""Interfaces the slices depend on. Adapters implement them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from domain.models import (
    DefectFinding,
    DefectKnowledgeCard,
    EightDReport,
    InspectionEvent,
    InspectionResult,
    Investigation,
    RobotCall,
)


@dataclass
class ModelUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    retries: int = 0


@dataclass
class Prediction:
    class_: Optional[str]
    confidence: float


@dataclass
class ReasoningOutput:
    defects: list[DefectFinding]
    decision: str
    rationale: str
    needs_human_confirm: bool
    usage: ModelUsage
    schema_valid: bool = True
    confidence: Optional[float] = None


@dataclass
class EpisodeRecord:
    episode_id: str
    uri: str
    steps: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    simulator: str = ""


class VisionModel(Protocol):
    name: str

    def predict(self, image: bytes) -> Prediction: ...
    def known_classes(self) -> set[str]: ...
    def label_count(self, part_number: str) -> int: ...


class ReasoningModel(Protocol):
    """Spatial judgment on an image (ER 2, or a fallback)."""

    name: str

    def inspect(
        self, image: bytes, mime_type: str, width: int, height: int,
        part_number: str, cards: list[DefectKnowledgeCard],
    ) -> ReasoningOutput: ...

    def plan_robot(
        self, image: bytes, mime_type: str, part_id: str, decision: str, rationale: str,
        cards: list[DefectKnowledgeCard],
    ) -> tuple[list[RobotCall], ModelUsage]: ...


class TextModel(Protocol):
    """Video understanding and prose (Gemini Flash, or a fallback)."""

    name: str

    def draft_cards(
        self, video: bytes, mime_type: str, part_number: str, source_uri: str,
    ) -> tuple[list[DefectKnowledgeCard], ModelUsage]: ...

    def rework_steps(
        self, card: Optional[DefectKnowledgeCard], rationale: str, language: str,
    ) -> tuple[list[str], ModelUsage]: ...


@dataclass
class Answer:
    text: str
    citations: list[str]  # source ids, validated against what was retrieved
    grounded: bool
    follow_ups: list[str]
    usage: ModelUsage


class QAModel(Protocol):
    """Answers questions only from SenpaiQC records (retrieved sources)."""

    name: str

    def answer(self, question: str, sources: list[dict], history: list[dict]) -> Answer: ...


class CardStore(Protocol):
    def list(self, part_number: Optional[str] = None, status: Optional[str] = None) -> list[DefectKnowledgeCard]: ...
    def get(self, card_id: str) -> Optional[DefectKnowledgeCard]: ...
    def put(self, card: DefectKnowledgeCard) -> None: ...


class DocStore(Protocol):
    """Generic store for decisions, investigations and 8D reports."""

    def put(self, collection: str, doc_id: str, data: dict[str, Any]) -> None: ...
    def get(self, collection: str, doc_id: str) -> Optional[dict[str, Any]]: ...
    def list(self, collection: str, limit: int = 200) -> list[dict[str, Any]]: ...


class BlobStore(Protocol):
    def save(self, path: str, data: bytes, content_type: str) -> str: ...
    def load(self, uri: str) -> bytes: ...


class EventSink(Protocol):
    def write(self, event: InspectionEvent) -> None: ...
    def query(self, template: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class RobotBridge(Protocol):
    name: str

    def run(
        self, part_id: str, calls: list[RobotCall], scrap_confirmed: bool,
        on_present: Optional[Callable[[float], Optional[str]]] = None,
    ) -> EpisodeRecord:
        """on_present(angle_deg) runs once, while the part is held at the camera; a returned
        bin name reroutes the following place_in_bin (it still passes the safety gate)."""
        ...

    def second_look(self, image: bytes, box: list[int], angle_deg: float) -> tuple[bytes, str]:
        """A closer view of the region in `box` (pixel [x1, y1, x2, y2]) and how it was taken."""
        ...


class RootCauseAnalyst(Protocol):
    name: str

    def analyse(self, investigation: Investigation) -> tuple[list[dict], list[dict], EightDReport]: ...


__all__ = [
    "BlobStore", "CardStore", "DocStore", "EpisodeRecord", "EventSink", "InspectionResult",
    "ModelUsage", "Prediction", "ReasoningModel", "ReasoningOutput", "RobotBridge",
    "RootCauseAnalyst", "TextModel", "VisionModel",
]
