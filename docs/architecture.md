# Architecture

```
Phone PWA (Firebase Hosting) ──/api/**──► senpaiqc-api (Cloud Run, FastAPI)
                                             │  slices: teach · inspect · act · learn
                                             │  ports ◄─ adapters
                                             ├─ YOLO (Ultralytics, CPU, loaded at cold start)
                                             ├─ Gemini Robotics ER 2   (pointing, card citation, robot function calls)
                                             ├─ Gemini 3.8 Flash       (video → cards, rework steps)
                                             ├─ Firestore              (cards, decisions, investigations, 8D, episodes)
                                             ├─ Cloud Storage          (images, expert videos, episodes, label exports)
                                             ├─ BigQuery               (inspection_events)
                                             └─► senpaiqc-agent (Cloud Run, private, ADK) ──► BigQuery (read-only templates)
```

Domain code (`server/api/domain`) imports no Google SDK. Slices depend on ports; `container.py`
is the only place that picks adapters, which is how offline, local and GCP modes swap without
touching slice code.

## Flow

1. **Teach.** A video is uploaded to GCS. Gemini Flash returns a list of cards under a response
   schema, which is validated with Pydantic and retried once. The cards are saved as `draft`. The
   inspector edits them (any edit resets the card to draft) and approves. Only approved cards
   reach Inspect.
2. **Inspect.** YOLO runs on the image. `EscalationPolicy` (config: 0.85 / 0.40 / min labels) sends
   uncertain, unknown-class or new-part images to ER 2 with the approved cards. ER 2 returns
   `[y, x]` points and `[ymin, xmin, ymax, xmax]` boxes in 0–1000, which the adapter converts to
   pixel `[x, y]` / `[x1, y1, x2, y2]`. A cited `card_id` that is not an approved card counts as
   uncited. An uncited defect can never pass. Scrap, uncited or schema-invalid results set
   `needs_human_confirm`. `latency_ms` and `cost_usd` (from token usage and the published price)
   are logged per call.
3. **Event write.** Auto-accepted results go to BigQuery at once. Flagged ones go only after a
   human confirms, with any override kept.
4. **Act.** Rework steps come from the cited card's `rework_action`, translated by Flash, and are
   cached per language. Robot mode (`ROBOT_MODE`) is a **second look**: the planner gets the
   cited cards (plus the defect a person confirmed) and presents the part at the angle the card's
   `inspection_view` gives. While the part is held, `RobotBridge.second_look` takes a closer view
   of the region ER 2 pointed at (in the simulator: a digital zoom), ER 2 judges it, and before /
   after metrics are stored on the episode and the decision. If the two looks disagree, the part is
   rerouted to the `hold` bin and flagged for a person; the robot never overrides a decision.
   Every call still goes through the safety gate (allow-listed function, known part, valid bin,
   angle limits, scrap only after a confirm), and the episode JSON is saved to GCS.
   `GET /api/act/second-look/stats` aggregates agreement, human-confirm rate, uncited defects and
   ER 2's self-reported confidence before and after.
5. **Learn.** A p-chart per defect has one subgroup per day and shift, with its centre line from
   the first 10 days, so a spike cannot widen its own limits. The first point above the UCL
   opens an investigation. The ADK agent can only use `query_events` (template name plus params,
   with dimensions allow-listed), `get_cards`, `get_process_context` and `draft_8d` (validated
   JSON). It ranks hypotheses with numbers and names the blamed dimension values. The 8D is
   stored as a draft for the QC engineer to edit and approve.
6. **Teacher–student.** Confirmed ER 2 decisions are exported in Ultralytics layout
   (classification folders plus detection txt). `eval/train_yolo.py --extra` retrains, and
   `eval/run_all.py --weights-after` measures the escalation drop.

## Guardrails

- Every Gemini call has a response schema, is validated, and gets one retry. If it still fails,
  a human decides.
- No free-form SQL: templates only, values are bound parameters, and dimension names come from
  an allow-list.
- Scrap decisions, new cards and exported labels all require a person.
- Synthetic rows are tagged (`SYN-`), and live latency and cost queries exclude them.
- Offline adapters never present output as an AI judgment.

## Ask SenpaiQC (grounded Q&A)

`POST /api/ask` answers questions from the plant's own records only: expert rule cards (with
approved/draft status), investigations and 8D reports, line statistics (live and synthetic,
labelled), the golden-set evaluation and YOLO training runs. Retrieval is keyword scoring over a
few dozen documents with an Indonesian-to-English floor vocabulary; no vector database is needed
at this size. Gemini Flash answers under a response schema and must cite source ids. The server
drops any citation that was not retrieved and marks the answer "not found in records" when nothing
valid is cited. Sources are passed as data with an explicit instruction to ignore instructions
inside them; the assistant is read-only. Measured: about 2–5 s and $0.002 per question.

## Security and guardrails

| Layer | Guardrail |
|---|---|
| Access | Bearer token on every API route except `/api/health` and sample images; constant-time token compare; Firebase ID tokens in the Firebase option. Image URLs carry the token, so `Referrer-Policy: no-referrer` |
| Cost | Per-user limit of 20 AI calls a minute and 400 a day per instance (`AI_CALLS_PER_*`); Cloud Run `--max-instances 2`; Gemini runs only on escalated parts |
| Input | Image ≤ 15 MB and must decode. Video: ≤ 30 MB straight through the API, otherwise up to 500 MB / 10 min via a 30-minute signed URL to Cloud Storage (size enforced by `x-goog-content-length-range`, only `teach/uploads/` objects accepted), then the Gemini Files API. Questions ≤ 500 characters, history trimmed |
| Model output | Every Gemini call has a response schema, Pydantic validation and one retry; invalid output → a person decides |
| Decisions | Uncited defects never pass; scrap, uncited and invalid results wait for a human; overrides are logged |
| Data | The root-cause agent uses named, read-only SQL templates with bound parameters and allow-listed dimensions |
| Robot | Safety gate: allowed functions, right part, valid bin, angle limits, scrap only after a confirm, hold on disagreement |
| Browser | CSP (`script-src 'self'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`; CORS off unless the web app is hosted elsewhere |
| Secrets | Gemini key in Secret Manager; `.env` is git- and upload-ignored; least-privilege service account |
| Honesty | Synthetic data labelled everywhere; the offline mode never presents output as AI judgment |

## Exports

8D reports download as `.docx` (opens in Google Docs via Drive, or in Word) and Markdown;
inspection audit trail and the expert rules register download as CSV (opens in Google Sheets).
No Google account linking is needed, so judges can use every export with the demo token.
