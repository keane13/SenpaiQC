"""Wires adapters to ports from settings. The only place that chooses implementations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from config import Settings, get_settings
from domain.policy import EscalationPolicy

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    docs: object
    cards: object
    blobs: object
    events: object
    vision: object
    reasoning: object
    text: object
    qa: object
    robot: object
    policy: EscalationPolicy

    def mode(self) -> dict:
        return {
            "backend": self.settings.backend,
            "fast_path": self.vision.name,
            "reasoning": self.reasoning.name,
            "text": self.text.name,
            "robot": self.robot.name if self.settings.robot_mode else "off",
            "gemini": self.settings.gemini_enabled,
        }


def build(s: Settings) -> Container:
    from adapters.local import DocCardStore

    if s.backend == "gcp":
        from adapters.gcp import BigQueryEventSink, FirestoreDocStore, GcsBlobStore

        docs = FirestoreDocStore(s.gcp_project, s.firestore_database)
        blobs = GcsBlobStore(s.gcp_project, s.gcs_bucket)
        events = BigQueryEventSink(s.gcp_project, s.bq_dataset)
    else:
        from adapters.local import LocalBlobStore, SqliteDocStore, SqliteEventSink

        db_path = s.local_dir / "senpaiqc.db"
        docs = SqliteDocStore(db_path)
        blobs = LocalBlobStore(s.local_dir / "blobs")
        events = SqliteEventSink(db_path)

    if s.gemini_enabled:
        from adapters.gemini_er2 import GeminiER2
        from adapters.gemini_text import GeminiText

        reasoning, text = GeminiER2(s), GeminiText(s)
    else:
        from adapters.offline import OfflineReasoning, OfflineText

        log.warning("GEMINI_API_KEY not set: using offline adapters; results are flagged for a human.")
        reasoning, text = OfflineReasoning(), OfflineText()

    vision = None
    if s.yolo_weights:
        try:
            from adapters.yolo import UltralyticsVision

            vision = UltralyticsVision(s.yolo_weights, s.yolo_label_counts)
        except Exception as exc:  # missing ultralytics or weights: escalate everything
            log.warning("YOLO not loaded (%s); every part escalates.", exc)
    if vision is None:
        from adapters.offline import NoVision

        vision = NoVision()

    from adapters.robot_sim import ScriptedSO101Sim

    return Container(
        settings=s, docs=docs, cards=DocCardStore(docs), blobs=blobs, events=events,
        vision=vision, reasoning=reasoning, text=text, qa=text, robot=ScriptedSO101Sim(blobs),
        policy=EscalationPolicy(s.keep_threshold, s.escalate_floor, s.min_labels_per_part),
    )


@lru_cache
def get_container() -> Container:
    return build(get_settings())
