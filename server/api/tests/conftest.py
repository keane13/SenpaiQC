import sys
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("YOLO_WEIGHTS", "")
    monkeypatch.setenv("ROBOT_MODE", "true")
    monkeypatch.setenv("AGENT_URL", "")
    import config
    import container

    config.get_settings.cache_clear()
    container.get_container.cache_clear()
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as tc:
        tc.headers["Authorization"] = "Bearer senpaiqc-demo"
        yield tc
    container.get_container.cache_clear()
    config.get_settings.cache_clear()


def jpeg_with_dark_spot() -> bytes:
    import cv2
    import numpy as np

    img = np.full((240, 320, 3), 170, np.uint8)
    cv2.circle(img, (200, 90), 6, (30, 30, 30), -1)
    return cv2.imencode(".jpg", img)[1].tobytes()
