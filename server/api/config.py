"""Runtime configuration. Thresholds and prices live here, not in slice code."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # "local" uses SQLite + files under var/; "gcp" uses Firestore, GCS and BigQuery.
    backend: str = "local"
    gcp_project: str = ""
    gcs_bucket: str = ""
    bq_dataset: str = "senpaiqc"
    firestore_database: str = "(default)"  # Firestore location is fixed per database, so regions get their own
    local_dir: Path = REPO_ROOT / "var"

    # Gemini. Without a key the offline adapters are used and every result says so.
    gemini_api_key: str = ""
    # Vertex AI: Gemini billed to the Google Cloud project, authenticated by the service account
    # (no API key). ER 2 is not on Vertex, so it stays on the Gemini API key when that has credit
    # and falls back to the text model on Vertex otherwise.
    use_vertex: bool = False
    vertex_location: str = "global"
    er2_model: str = "gemini-robotics-er-2-preview"
    text_model: str = "gemini-3.8-flash"
    er2_thinking_level: str = "MEDIUM"
    # USD per 1M tokens, paid tier, through 2026-12-31 (ai.google.dev/gemini-api/docs/pricing).
    er2_price_in: float = 1.00
    er2_price_out: float = 5.00
    text_price_in: float = 0.75
    text_price_out: float = 3.75

    # Fast path
    yolo_weights: str = ""  # local path or gs:// URI; empty -> no YOLO, everything escalates
    yolo_label_counts: str = ""  # inline JSON {"IMP-200": 1200}, a JSON file, or gs:// URI

    # Escalation policy (tuned on val, never on golden)
    keep_threshold: float = 0.85
    escalate_floor: float = 0.40
    min_labels_per_part: int = 50

    # Act
    robot_mode: bool = False

    # Auth: "demo" accepts a fixed demo token; "firebase" verifies Firebase ID tokens.
    auth_mode: str = "demo"
    demo_token: str = "senpaiqc-demo"
    cors_origins: str = ""  # empty: same-origin only (web and API served by one service)

    # Guardrails for a public demo URL (see guards.py)
    ai_calls_per_minute: int = 20
    ai_calls_per_day: int = 300  # daily budget in cost units per instance (1 unit ~ 1 Gemini call)
    max_video_mb: int = 30  # direct upload through the API (Cloud Run caps request bodies at 32 MiB)
    max_video_upload_mb: int = 500  # via a signed URL straight to Cloud Storage

    # Root-cause agent: empty -> run in-process; else POST to this ADK service URL.
    agent_url: str = ""

    def check_deploy_secrets(self) -> None:
        """Fail fast on Cloud Run instead of serving a public URL with a guessable token."""
        if self.backend != "gcp":
            return
        if self.auth_mode == "demo" and (self.demo_token in ("", "senpaiqc-demo", "kaizenlens-demo") or len(self.demo_token) < 12):
            raise RuntimeError("DEMO_TOKEN is missing or the local default. Push SENPAIQC_DEMO_TOKEN with infra/push_secrets.sh.")
        if not self.gemini_api_key and not self.use_vertex:
            raise RuntimeError("GEMINI_API_KEY is missing. Map SENPAIQC_GEMINI_API_KEY from Secret Manager.")

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key) or self.use_vertex


@lru_cache
def get_settings() -> Settings:
    return Settings()
