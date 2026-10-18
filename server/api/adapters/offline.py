"""Offline fallbacks used when GEMINI_API_KEY is not set.

They never pretend to be Gemini: every result is flagged for a human and the rationale
says no AI judgment was made. The image heuristic only proposes a candidate spot.
"""
from __future__ import annotations

import re
from typing import Optional

import cv2
import numpy as np

from domain.models import CardStatus, DefectFinding, DefectKnowledgeCard, RobotCall, Severity
from ports import ModelUsage, Prediction, ReasoningOutput

OFFLINE_NOTE = "Offline mode (no GEMINI_API_KEY): no AI judgment was made."


def dark_spot_candidate(image: bytes) -> Optional[tuple[list[int], list[int]]]:
    """Darkest compact blob relative to its surroundings, as ([x, y], [x1, y1, x2, y2])."""
    arr = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        return None
    blur = cv2.GaussianBlur(arr, (0, 0), 9)
    diff = cv2.subtract(blur, arr)  # pixels darker than their neighbourhood
    _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    # Each dark blob separately (nested ones too); pinholes are small, so large regions such as
    # the hub, the background or the part edge are ignored.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    max_area = 0.01 * arr.shape[0] * arr.shape[1]
    best, best_contrast = None, 0.0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not 4 <= area <= max_area or max(w, h) > 0.2 * max(arr.shape):
            continue
        contrast = float(diff[labels == i].mean())
        if contrast > best_contrast:
            best, best_contrast = (int(x), int(y), int(w), int(h)), contrast
    if best is None:
        return None
    x, y, w, h = best
    return [x + w // 2, y + h // 2], [x, y, x + w, y + h]


class OfflineReasoning:
    name = "offline-heuristic"

    def inspect(self, image, mime_type, width, height, part_number, cards):
        cand = dark_spot_candidate(image)
        defects = []
        if cand:
            defects.append(DefectFinding(card_id=None, point=cand[0], box=cand[1],
                                         severity=Severity.major, label="candidate (heuristic)"))
        return ReasoningOutput(
            defects=defects, decision="rework",
            rationale=OFFLINE_NOTE + (" A dark-spot candidate is marked for the inspector." if cand else ""),
            needs_human_confirm=True, usage=ModelUsage(model=self.name), schema_valid=True,
        )

    def plan_robot(self, image, mime_type, part_id, decision, rationale, cards):
        """Scripted plan (no model) so the robot path can be exercised offline. The second-look
        angle is read from the first card whose inspection_view states one in degrees."""
        angle = next((float(m.group(1)) for c in cards
                      if (m := re.search(r"(-?\d+(?:\.\d+)?)\s*(?:°|deg)", c.inspection_view))), 30.0)
        calls = [
            RobotCall(name="pick", args={"part_id": part_id}),
            RobotCall(name="present_to_camera", args={"part_id": part_id, "angle_deg": angle}),
            RobotCall(name="place_in_bin", args={"part_id": part_id, "bin": decision}),
            RobotCall(name="stop", args={}),
        ]
        return calls, ModelUsage(model="scripted-plan")


class OfflineText:
    name = "offline-template"

    def draft_cards(self, video, mime_type, part_number, source_uri):
        # Without video understanding we can only hand the inspector a blank card to fill in.
        card = DefectKnowledgeCard(
            card_id=f"{part_number.lower()}-manual-{abs(hash(source_uri)) % 10000:04d}",
            part_number=part_number, defect_name="fill_in",
            visual_cues=["(offline mode: describe the cues from the video)"],
            source_video=source_uri, status=CardStatus.draft,
        )
        return [card], ModelUsage(model=self.name)

    def rework_steps(self, card, rationale, language):
        if card is None or not card.rework_action:
            steps = ["Hold the part for the senior inspector.", "Record the defect location and photo."]
        else:
            steps = [s.strip().capitalize() for s in re.split(r"[;.]\s*", card.rework_action) if s.strip()]
            steps.append(f"Re-inspect against the limit: {card.accept_limit}")
        if language != "en":
            steps.insert(0, "(Translation needs Gemini; showing English.)")
        return steps, ModelUsage(model=self.name)

    def answer(self, question, sources, history):
        from ports import Answer

        top = sources[:3]
        lines = ["Offline mode (no GEMINI_API_KEY): no AI answer was written. The closest records are:"]
        lines += [f"- {d['title']}: {d['text'][:220]}" for d in top]
        return Answer("\n".join(lines), [d["id"] for d in top], False, [], ModelUsage(model=self.name))


class NoVision:
    """No YOLO weights loaded: every part escalates. Honest default before training."""

    name = "none"

    def predict(self, image: bytes) -> Prediction:
        return Prediction(class_=None, confidence=0.0)

    def known_classes(self) -> set[str]:
        return set()

    def label_count(self, part_number: str) -> int:
        return 0
