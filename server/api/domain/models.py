"""Pure domain models. No Google SDK imports here — only adapters talk to Google."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    minor = "minor"
    major = "major"
    critical = "critical"


class Decision(str, Enum):
    pass_ = "pass"
    rework = "rework"
    scrap = "scrap"


class CardStatus(str, Enum):
    draft = "draft"
    approved = "approved"


class DefectKnowledgeCard(BaseModel):
    card_id: str
    part_number: str
    defect_name: str
    visual_cues: list[str] = Field(default_factory=list)
    typical_location: str = ""
    # How the expert looks at it, e.g. "tilt 30 deg toward the light, check the flange edge".
    # Robot mode turns this into a present_to_camera pose for the second look.
    inspection_view: str = ""
    accept_limit: str = ""
    severity: Severity = Severity.major
    rework_action: str = ""
    source_video: str = ""
    source_timestamp: str = ""
    approved_by: Optional[str] = None
    status: CardStatus = CardStatus.draft


class YoloOutput(BaseModel):
    class_: Optional[str] = Field(default=None, alias="class")
    confidence: float = 0.0

    model_config = {"populate_by_name": True}


class DefectFinding(BaseModel):
    card_id: Optional[str] = None  # None = defect not covered by any approved card
    point: list[int] = Field(default_factory=list)  # pixel [x, y]
    box: list[int] = Field(default_factory=list)  # pixel [x1, y1, x2, y2]
    severity: Severity = Severity.major
    label: str = ""

    @field_validator("point")
    @classmethod
    def _point_len(cls, v: list[int]) -> list[int]:
        if v and len(v) != 2:
            raise ValueError("point must be [x, y]")
        return v

    @field_validator("box")
    @classmethod
    def _box_len(cls, v: list[int]) -> list[int]:
        if v and len(v) != 4:
            raise ValueError("box must be [x1, y1, x2, y2]")
        return v


class InspectionResult(BaseModel):
    id: str = ""
    image_uri: str
    part_number: str
    path: Literal["yolo", "er2"]
    yolo: YoloOutput = Field(default_factory=YoloOutput)
    defects: list[DefectFinding] = Field(default_factory=list)
    decision: Decision
    rationale: str = ""
    needs_human_confirm: bool = False
    latency_ms: int = 0
    cost_usd: float = 0.0
    # Bookkeeping beyond the contract (kept separate so the contract stays intact).
    escalation_reason: Optional[str] = None
    reasoning_model: Optional[str] = None
    confidence: Optional[float] = None  # model-reported 0-1 (ER 2 only), not a calibrated probability
    confirmed: bool = False
    confirmed_by: Optional[str] = None
    image_size: list[int] = Field(default_factory=list)  # [width, height]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LineContext(BaseModel):
    """Where the part came from. Feeds the BigQuery event and the root-cause agent."""

    line_id: str = "L1"
    shift: str = "A"
    machine_id: str = "MC-01"
    mould_id: str = "MD-01"
    material_lot: str = "LOT-0001"


class InspectionEvent(BaseModel):
    """Row in BigQuery senpaiqc.inspection_events."""

    event_ts: datetime
    line_id: str
    shift: str
    machine_id: str
    mould_id: str
    material_lot: str
    part_number: str
    path: str
    defect_name: Optional[str]
    decision: str
    confirmed: bool
    latency_ms: int
    cost_usd: float


class RobotCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class GateVerdict(BaseModel):
    call: RobotCall
    allowed: bool
    reason: str = ""


class Investigation(BaseModel):
    id: str
    defect_name: str
    shift_key: str  # e.g. "2026-09-20/B"
    rate: float
    ucl: float
    center: float
    status: Literal["open", "analysed", "closed"] = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analysed_at: Optional[datetime] = None
    hypotheses: list[dict] = Field(default_factory=list)
    agent_trace: list[dict] = Field(default_factory=list)
    agent_model: Optional[str] = None
    report_id: Optional[str] = None


class EightDReport(BaseModel):
    id: str
    investigation_id: str
    status: Literal["draft", "approved"] = "draft"
    sections: dict[str, str] = Field(default_factory=dict)  # D1..D8 -> text
    generated_by: str = ""
    edited_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


EIGHT_D_KEYS = [
    "D1_team",
    "D2_problem",
    "D3_containment",
    "D4_root_cause",
    "D5_corrective_actions",
    "D6_implementation",
    "D7_prevention",
    "D8_recognition",
]
