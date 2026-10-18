"""Shared Gemini plumbing: schema-enforced calls, one retry, usage and cost accounting."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from ports import ModelUsage

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: Optional[genai.Client] = None

# Back off and retry on rate limits and transient errors (free-tier keys allow only a few
# requests a minute; the root-cause agent makes ~20 calls in a row).
RETRY = types.HttpRetryOptions(attempts=6, initial_delay=2.0, max_delay=65.0, exp_base=2.0, jitter=1.0,
                               http_status_codes=[429, 500, 503])
HTTP_OPTIONS = types.HttpOptions(retry_options=RETRY)

last_error: dict = {"billing": False}


def unavailable_reason(text: str = "") -> str:
    """Plain-language reason for a failed call, shown to users instead of a generic error."""
    t = text or last_error.get("text", "")
    if "402" in t or "credits are depleted" in t or "billing" in t.lower():
        return "Gemini is unavailable: the project's Gemini billing credits are used up. A person must decide for now."
    if "429" in t or "RESOURCE_EXHAUSTED" in t:
        return "Gemini is busy (rate limit). Try again in a minute."
    return ""


def client(api_key: str) -> genai.Client:
    """Gemini API client (API key). Used for Gemini Robotics ER 2, which Vertex AI does not serve."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=api_key, http_options=HTTP_OPTIONS)
    return _client


_vertex: Optional[genai.Client] = None


def vertex_client(project: str, location: str) -> genai.Client:
    """Vertex AI client: billed to the project, authenticated with the service account."""
    global _vertex
    if _vertex is None:
        _vertex = genai.Client(vertexai=True, project=project, location=location, http_options=HTTP_OPTIONS)
    return _vertex


def text_client(settings) -> genai.Client:
    if settings.use_vertex:
        return vertex_client(settings.gcp_project, settings.vertex_location)
    return client(settings.gemini_api_key)


def hard_failure(text: str) -> bool:
    """Errors that retrying will not fix: no credit, model not available, no permission."""
    return any(code in text for code in ("402", "404", "403", "credits are depleted", "NOT_FOUND", "PERMISSION_DENIED"))


def usage_from(resp: Any, model: str, price_in: float, price_out: float, started: float) -> ModelUsage:
    um = getattr(resp, "usage_metadata", None)
    tin = (um.prompt_token_count or 0) if um else 0
    # Thinking tokens are billed as output.
    tout = ((um.candidates_token_count or 0) + (um.thoughts_token_count or 0)) if um else 0
    return ModelUsage(
        model=model,
        input_tokens=tin,
        output_tokens=tout,
        cost_usd=round(tin / 1e6 * price_in + tout / 1e6 * price_out, 6),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


def call_structured(
    c: genai.Client,
    model: str,
    contents: list[Any],
    schema: type[T],
    price_in: float,
    price_out: float,
    thinking_level: Optional[str] = None,
    system_instruction: Optional[str] = None,
) -> tuple[Optional[T], ModelUsage]:
    """Call with a response schema; validate with Pydantic; retry once on invalid output.

    Returns (None, usage) when both attempts fail so the caller can mark the result
    as needing a human.
    """
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None,
    )
    total = ModelUsage(model=model)
    started_all = time.perf_counter()
    for attempt in range(2):
        started = time.perf_counter()
        try:
            resp = c.models.generate_content(model=model, contents=contents, config=cfg)
        except Exception as exc:  # network / quota: count as a failed attempt
            log.warning("gemini call failed (attempt %d): %s", attempt + 1, exc)
            last_error["text"] = str(exc)
            total.retries = attempt
            if hard_failure(str(exc)):  # billing / model / permission: retrying cannot help
                break
            continue
        u = usage_from(resp, model, price_in, price_out, started)
        total.input_tokens += u.input_tokens
        total.output_tokens += u.output_tokens
        total.cost_usd = round(total.cost_usd + u.cost_usd, 6)
        total.retries = attempt
        try:
            parsed = schema.model_validate_json(resp.text or "")
            total.latency_ms = int((time.perf_counter() - started_all) * 1000)
            return parsed, total
        except ValidationError as exc:
            log.warning("schema-invalid output (attempt %d): %s", attempt + 1, exc)
    total.latency_ms = int((time.perf_counter() - started_all) * 1000)
    return None, total
