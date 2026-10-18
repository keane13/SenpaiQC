"""Gemini Robotics ER 2 adapter: defect pointing with card citation, and robot planning.

Coordinate convention (ai.google.dev/gemini-api/docs/robotics-overview): points are
[y, x] normalised to 0-1000. We ask for boxes as [ymin, xmin, ymax, xmax] in the same
0-1000 space and convert both to pixels here, never in the UI.
"""
from __future__ import annotations

import json
import time
from enum import Enum

from google.genai import types
from pydantic import BaseModel, Field

from domain.geometry import box1000_to_px, yx1000_to_px
from domain.models import DefectFinding, DefectKnowledgeCard, RobotCall, Severity
from ports import ModelUsage, ReasoningOutput

from . import gemini_common as gc

UNKNOWN = "UNKNOWN"


class _Sev(str, Enum):
    minor = "minor"
    major = "major"
    critical = "critical"


class _Dec(str, Enum):
    pass_ = "pass"
    rework = "rework"
    scrap = "scrap"


class Er2Defect(BaseModel):
    label: str = Field(description="Defect name")
    card_id: str = Field(description=f"card_id of the cited card, or {UNKNOWN}")
    point: list[int] = Field(description="[y, x] normalised 0-1000")
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax] normalised 0-1000")
    severity: _Sev
    evidence: str = Field(description="What you see, measured against the card's accept_limit")


class Er2Inspection(BaseModel):
    defects: list[Er2Defect]
    decision: _Dec
    rationale: str
    needs_human_confirm: bool
    confidence: float = Field(description="0-1: how sure you are of the decision")


INSPECT_PROMPT = """You are the final visual inspector for cast part {part_number}.
A senior inspector taught you these approved Defect Knowledge Cards (JSON):
{cards}

Look at the image.
1. Point at every defect you see. Points are [y, x] normalised to 0-1000; boxes are
   [ymin, xmin, ymax, xmax] normalised to 0-1000.
2. For each defect, cite the card_id whose visual_cues match. If no card matches, use
   card_id "{unknown}".
3. Decide using each cited card's accept_limit and severity:
   - pass: no defect, or every defect is within its card's accept_limit.
   - rework: a defect exceeds its limit and the card's rework_action can fix it.
   - scrap: the card says the defect cannot be reworked (for example on a sealing face).
   - Any "{unknown}" defect: decision rework and needs_human_confirm true.
4. rationale: one or two sentences in English that name the card you relied on.
5. confidence: 0-1, how sure you are of the decision. Lower it when the view is too small,
   blurred or badly lit to judge the card's accept_limit.
Return only JSON matching the schema."""

ROBOT_PROMPT = """You control a SO-101 arm at an inspection cell. Part {part_id} is in the
camera view. The inspection decision is "{decision}" because: {rationale}
The senior inspector's Defect Knowledge Cards for this part (JSON):
{cards}
1. Pick the part.
2. Present it to the camera once for a second look. Choose angle_deg from the cited card's
   inspection_view (how the expert looks at this defect); if no card gives a view, use the
   angle that best shows the area named in typical_location.
3. Place it in the bin that matches the decision, then stop.
Use only the declared functions."""


def _robot_tools() -> types.Tool:
    part = {"type": "string", "description": "Part id"}
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="pick", description="Pick up the part.",
            parameters_json_schema={"type": "object", "properties": {"part_id": part}, "required": ["part_id"]},
        ),
        types.FunctionDeclaration(
            name="present_to_camera", description="Rotate the held part in front of the camera.",
            parameters_json_schema={
                "type": "object",
                "properties": {"part_id": part, "angle_deg": {"type": "number", "description": "-90 to 90"}},
                "required": ["part_id", "angle_deg"],
            },
        ),
        types.FunctionDeclaration(
            name="place_in_bin", description="Place the held part in a bin.",
            parameters_json_schema={
                "type": "object",
                "properties": {"part_id": part, "bin": {"type": "string", "enum": ["pass", "rework", "scrap"]}},
                "required": ["part_id", "bin"],
            },
        ),
        types.FunctionDeclaration(
            name="stop", description="Stop the arm and return home.",
            parameters_json_schema={"type": "object", "properties": {}},
        ),
    ])


class GeminiER2:
    """Spatial reasoning: Gemini Robotics ER 2 when its API key has credit, else the text model on
    Vertex AI with the same prompt and schema. A hard ER 2 failure (no credit, not found) opens a
    10-minute circuit so parts are not delayed by repeated failing calls."""

    BREAKER_SECONDS = 600

    def __init__(self, settings):
        self.s = settings
        self.primary = gc.client(settings.gemini_api_key) if settings.gemini_api_key else None
        self.fallback = gc.vertex_client(settings.gcp_project, settings.vertex_location) if settings.use_vertex else None
        self._open_until = 0.0
        if self.primary and self.fallback:
            self.name = f"{settings.er2_model} (fallback: {settings.text_model} on Vertex AI)"
        elif self.primary:
            self.name = settings.er2_model
        else:
            self.name = f"{settings.text_model} on Vertex AI"

    def _routes(self):
        """(client, model, price_in, price_out, thinking, label) in the order to try."""
        routes = []
        if self.primary and time.monotonic() >= self._open_until:
            routes.append((self.primary, self.s.er2_model, self.s.er2_price_in, self.s.er2_price_out,
                           self.s.er2_thinking_level, self.s.er2_model))
        if self.fallback:
            routes.append((self.fallback, self.s.text_model, self.s.text_price_in, self.s.text_price_out,
                           "LOW", f"vertex:{self.s.text_model}"))
        return routes

    def _trip(self, model: str) -> None:
        if model != self.s.er2_model:
            return
        text = gc.last_error.get("text", "")
        if "402" in text or "credits are depleted" in text or "404" in text:
            self._open_until = time.monotonic() + 6 * 3600  # no credit / no access: will not fix itself soon
        elif gc.hard_failure(text) or "429" in text:
            self._open_until = time.monotonic() + self.BREAKER_SECONDS

    def inspect(self, image, mime_type, width, height, part_number, cards) -> ReasoningOutput:
        card_json = json.dumps([_card_brief(c) for c in cards], ensure_ascii=False, indent=1)
        prompt = INSPECT_PROMPT.format(part_number=part_number, cards=card_json or "[]", unknown=UNKNOWN)
        parsed, usage = None, ModelUsage(model=self.name)
        for c, model, p_in, p_out, thinking, label in self._routes():
            gc.last_error["text"] = ""
            parsed, usage = gc.call_structured(
                c, model, [types.Part.from_bytes(data=image, mime_type=mime_type), prompt],
                Er2Inspection, p_in, p_out, thinking_level=thinking,
            )
            usage.model = label
            if parsed is not None:
                break
            self._trip(model)
        if parsed is None:
            return ReasoningOutput(
                defects=[], decision="rework",
                rationale=gc.unavailable_reason() or "The model returned schema-invalid output twice; a human must decide.",
                needs_human_confirm=True, usage=usage, schema_valid=False,
            )
        valid_ids = {c.card_id for c in cards}
        findings = []
        for d in parsed.defects:
            cited = d.card_id if d.card_id in valid_ids else None
            findings.append(DefectFinding(
                card_id=cited,
                point=yx1000_to_px(d.point, width, height) if len(d.point) == 2 else [],
                box=box1000_to_px(d.box_2d, width, height) if len(d.box_2d) == 4 else [],
                severity=Severity(d.severity.value),
                label=d.label,
            ))
        return ReasoningOutput(
            defects=findings, decision=parsed.decision.value, rationale=parsed.rationale,
            needs_human_confirm=parsed.needs_human_confirm, usage=usage,
            confidence=max(0.0, min(1.0, parsed.confidence)),
        )

    def plan_robot(self, image, mime_type, part_id, decision, rationale, cards):
        contents = [types.Part.from_bytes(data=image, mime_type=mime_type),
                    ROBOT_PROMPT.format(part_id=part_id, decision=decision, rationale=rationale,
                                        cards=json.dumps([_card_brief(c) for c in cards], ensure_ascii=False, indent=1))]
        last_exc = None
        for c, model, p_in, p_out, thinking, label in self._routes():
            started = time.perf_counter()
            cfg = types.GenerateContentConfig(
                tools=[_robot_tools()],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY")),
                thinking_config=types.ThinkingConfig(thinking_level=thinking),
            )
            try:
                resp = c.models.generate_content(model=model, contents=contents, config=cfg)
            except Exception as exc:  # fall through to the next route
                gc.last_error["text"] = str(exc)
                self._trip(model)
                last_exc = exc
                continue
            usage = gc.usage_from(resp, label, p_in, p_out, started)
            calls = [RobotCall(name=fc.name, args=dict(fc.args or {})) for fc in (resp.function_calls or [])]
            return calls, usage
        raise RuntimeError(gc.unavailable_reason() or f"robot planning failed: {last_exc}")


def _card_brief(c: DefectKnowledgeCard) -> dict:
    return {
        "card_id": c.card_id, "defect_name": c.defect_name, "visual_cues": c.visual_cues,
        "typical_location": c.typical_location, "inspection_view": c.inspection_view, "accept_limit": c.accept_limit,
        "severity": c.severity.value, "rework_action": c.rework_action,
    }


def no_usage(model: str) -> ModelUsage:
    return ModelUsage(model=model)
