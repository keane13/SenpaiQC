"""Ultralytics YOLO fast path, CPU only. Weights are loaded once at cold start."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np

from ports import Prediction


class UltralyticsVision:
    def __init__(self, weights: str, label_counts_path: str = ""):
        from ultralytics import YOLO  # imported lazily so the API runs without it

        local = _fetch(weights)
        self.model = YOLO(local)
        self.task = self.model.task  # "classify" or "detect"
        self.name = f"yolo:{Path(local).name}"
        self._classes = set(self.model.names.values()) | ({"ok"} if self.task == "detect" else set())
        self._counts = load_label_counts(label_counts_path)

    def predict(self, image: bytes) -> Prediction:
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        r = self.model.predict(img, device="cpu", verbose=False, conf=0.05)[0]
        if self.task == "classify":
            idx = int(r.probs.top1)
            return Prediction(class_=self.model.names[idx], confidence=float(r.probs.top1conf))
        # Detection has no "ok" class: an image is ok with confidence 1 - (strongest box).
        if r.boxes is None or len(r.boxes) == 0:
            return Prediction(class_="ok", confidence=0.95)
        i = int(r.boxes.conf.argmax())
        top = float(r.boxes.conf[i])
        if top < 0.25:
            return Prediction(class_="ok", confidence=1 - top)
        return Prediction(class_=self.model.names[int(r.boxes.cls[i])], confidence=top)

    def known_classes(self) -> set[str]:
        return self._classes

    def label_count(self, part_number: str) -> int:
        return int(self._counts.get(part_number, 0))


def load_label_counts(value: str) -> dict[str, int]:
    """YOLO_LABEL_COUNTS: inline JSON ({"IMP-200": 5639}, handy as a Cloud Run env var),
    a local file, or a gs:// URI. Empty -> {} (every part counts as new and escalates)."""
    value = value.strip()
    if not value:
        return {}
    text = value if value.startswith("{") else Path(_fetch(value)).read_text()
    return {k: int(v) for k, v in json.loads(text).items()}


def _fetch(weights: str) -> str:
    if not weights.startswith("gs://"):
        return weights
    from google.cloud import storage

    bucket, _, blob = weights[5:].partition("/")
    dst = Path(tempfile.gettempdir()) / Path(blob).name
    if not dst.exists():
        storage.Client().bucket(bucket).blob(blob).download_to_filename(dst)
    return str(dst)
