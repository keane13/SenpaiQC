"""Day-0 check: one ER 2 call and one Gemini text call; appends the result to docs/api-check.md.

  GEMINI_API_KEY=... python infra/api_check.py [image.jpg]
Records latency, token counts, the parsed points (to confirm the [y, x] 0-1000 convention)
and any quota error. If ER 2 is blocked, the app still runs: set ER2_MODEL to a Flash model.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "api"))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from config import get_settings  # noqa: E402


def sample_image() -> bytes:
    import cv2
    import numpy as np

    img = np.full((480, 640, 3), 170, np.uint8)
    cv2.circle(img, (320, 240), 180, (200, 200, 195), -1)
    cv2.circle(img, (420, 160), 8, (25, 25, 25), -1)  # dark "pinhole" at x=420, y=160
    return cv2.imencode(".jpg", img)[1].tobytes()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    s = get_settings()
    if not s.gemini_api_key:
        raise SystemExit("set GEMINI_API_KEY")
    c = genai.Client(api_key=s.gemini_api_key)
    image = Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else sample_image()
    lines = [f"\n## Run {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"]

    prompt = ('Point to the darkest small spot. Answer as JSON [{"point": [y, x], "label": "spot"}]; '
              "points are [y, x] normalised to 0-1000.")
    for model, contents, cfg in [
        (s.er2_model, [types.Part.from_bytes(data=image, mime_type="image/jpeg"), prompt],
         types.GenerateContentConfig(response_mime_type="application/json",
                                     thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"))),
        (s.text_model, ["Reply with the single word: ready"], None),
    ]:
        t = time.perf_counter()
        try:
            r = c.models.generate_content(model=model, contents=contents, config=cfg)
            ms = int((time.perf_counter() - t) * 1000)
            um = r.usage_metadata
            lines.append(f"- `{model}`: OK, {ms} ms, tokens in/out {um.prompt_token_count}/{um.candidates_token_count}, "
                         f"thoughts {um.thoughts_token_count}\n  - output: `{(r.text or '').strip()[:300]}`")
            if model == s.er2_model and len(sys.argv) == 1:
                try:
                    y, x = json.loads(r.text)[0]["point"]
                    lines.append(f"  - expected spot at pixel x=420, y=160 -> normalised [y, x] ≈ [333, 656]; got [{y}, {x}]")
                except Exception as exc:  # report, do not hide
                    lines.append(f"  - could not parse point: {exc}")
        except Exception as exc:
            lines.append(f"- `{model}`: FAILED after {int((time.perf_counter() - t) * 1000)} ms: {exc}")
    out = ROOT / "docs" / "api-check.md"
    if not out.exists():
        out.write_text("# Gemini API check (day 0)\n\nAppended by `infra/api_check.py`. Measured, not projected.\n")
    with out.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
