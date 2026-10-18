# 3-minute demo script

Each shot lists the app path that proves it. Record on the deployed Cloud Run URL with the
mode chip in the top bar showing "Gemini on". Never show a number that `eval/` or the app's
logs did not produce, and say "synthetic" wherever process data appears.

| Time | Shot | In the app | Voice-over (gist) |
|---|---|---|---|
| 0:00–0:20 | Problem | (slide) | Senior inspectors retire; their judgment leaves with them. Visual QC is inconsistent between shifts. |
| 0:20–0:50 | Teach: a narrated video becomes rules | Knowledge → Teach from video → upload → open a draft card → edit "How the expert looks" → Approve | Gemini watches the video and drafts rules in the narrator's words, with timestamps. Nothing reaches the line until a person approves it. |
| 0:50–1:20 | Inspect: easy part stays on YOLO, hard part escalates | Inspect → sample "ok" part (fast path) → sample "defective" part (escalates) → overlay + "cites imp-200-…" | YOLO answers confident parts on CPU. Uncertain parts go to Gemini Robotics ER 2, which points at the defect and cites the approved rule. |
| 1:20–1:50 | Robot second look | Inspect → "Sort with simulated arm" → Robot tab → replay + second-look panel | ER 2 reads the rule's inspection view, presents the part at that angle, judges the closer view, then sorts. Say it: simulated cell, digital zoom. |
| 1:50–2:05 | Safety and the operator | Robot log showing a blocked scrap or a hold; Inspect → rework guide → Bahasa Indonesia | Scrap needs a person. Two looks disagree → hold bin. Rework steps come from the expert's rule, in the operator's language. |
| 2:05–2:40 | Learn: root cause | Insights → Check for spikes → Find root cause → agent trace → edit 8D | On synthetic process data with a planted cause, the ADK agent names the mould and lot with evidence and drafts an 8D for the QC engineer. |
| 2:40–3:00 | Measured results | Insights → evaluation tiles; Robot → second-look tiles | Recall, false-reject rate, escalation rate, p95 latency and cost per 1,000 parts, all measured on the held-out golden set. |

## Before recording

1. Deployed URL works from a clean browser on a phone; demo token at hand.
2. `docs/api-check.md` shows one successful ER 2 call and one text-model call.
3. YOLO weights and label counts set on Cloud Run (`YOLO_WEIGHTS`, `YOLO_LABEL_COUNTS`).
4. `python eval/run_all.py` done before the deploy, so `eval/results/summary.json` has real values.
5. At least 3 robot episodes recorded, including one that shows a block or a hold.
6. Seed cards replaced by the cards approved from your own narrated video (or clearly labelled seed).
7. Practise the Inspect and Robot shots once; Gemini latency is real, so cut the waiting in editing,
   not by faking results.
