# Gemini API check (day 0)

Appended by `infra/api_check.py`. Measured, not projected.

## Run 2026-10-17T15:58:57+00:00

- `gemini-robotics-er-2-preview`: OK, 4106 ms, tokens in/out 1107/24, thoughts 189
  - output: `[
  {"point": [333, 657], "label": "spot"}
]`
  - expected spot at pixel x=420, y=160 -> normalised [y, x] ≈ [333, 656]; got [333, 657]
- `gemini-3.8-flash`: OK, 3516 ms, tokens in/out 8/1, thoughts 194
  - output: `ready`
