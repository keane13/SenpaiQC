# SenpaiQC demo video: recording script (3 minutes)

A screen recording of the **live app** with voice-over, for the submission's "Demo Video Link
(3 Minutes)". Narration is about 430 words, which is about 2 min 50 s at a calm pace. The slide
version of the same story is [`demo-video-SenpaiQC.pptx`](demo-video-SenpaiQC.pptx); use its
slides for the opening and the closing if you like.

- **App:** https://senpaiqc-568251697792.us-central1.run.app
- **Sign in:** choose **QC engineer**, paste the access token, **Sign in**. Read the token with
  `gcloud secrets versions access latest --secret SENPAIQC_DEMO_TOKEN --project smooth-reason-491707-f6`.
- **Rule:** never fake a result. Gemini and the agent take real time; cut the waiting in editing.

## Before recording (10 minutes)

1. **Fresh spike for the alert.** Close the open investigation so **Check for spikes** opens a new
   one and Telegram gets the alert (nothing is deleted):
   ```bash
   BACKEND=gcp GCP_PROJECT=smooth-reason-491707-f6 FIRESTORE_DATABASE=senpaiqc-us python server/api/demo_reset.py
   ```
2. **Phone ready:** Telegram open on the @SenpaiQCbot chat, notifications on, screen recorder or a
   second camera pointed at the phone.
3. **Draft cards:** leave the 4 `-v2` cards (drafted from the teach video) as **Needs approval**, so
   you can approve one on camera.
4. **Teach video clip:** have `teach video part IMP-200.mp4` ready to insert for 5 seconds.
5. **Browser:** 1440×900 or 1920×1080, zoom 110%, one tab, bookmarks bar hidden, light theme.
6. **Warm-up:** open the app once a minute before recording (Cloud Run starts from zero).
7. **Dry run:** do steps 3–8 below once, so the first Gemini calls are warm.

## Shot list

| # | Time | Screen | Do this | Say (short) |
|---|---|---|---|---|
| 1 | 0:00–0:12 | Sign-in page (or title slide) | Hold | Who you are, the one-line idea |
| 2 | 0:12–0:30 | Sign-in page → Overview | Pick **QC engineer**, sign in | The problem |
| 3 | 0:30–0:58 | Insert 5 s of the teach video → **Expert knowledge** | Filter **Needs approval**, open `imp-200-porosity-v2`, show the limit and timestamp, **Approve** | Teach once on video |
| 4 | 0:58–1:15 | **Inspect a part** | Tap a defective sample photo; result banner appears | YOLO decides easy parts |
| 5 | 1:15–1:35 | Same page | **Ask Gemini for a second opinion**; point at the circle and the cited rule | Gemini shows its evidence |
| 6 | 1:35–1:50 | Scroll to **What to do now** | Switch **EN → ID**, tick one step | Steps in the operator's language |
| 7 | 1:50–2:02 | **Sort with simulated arm** → **Robot cell** | Select the episode, **Play** in 3D | Same decision drives a robot |
| 8 | 2:02–2:20 | **Quality analytics** | **Check for spikes**; cut to the phone: Telegram alert arrives | Spike → alert |
| 9 | 2:20–2:38 | Same page | **Find root cause** (cut the ~30 s wait); show hypothesis #1 | ADK agent finds the cause |
| 10 | 2:38–2:48 | **Reports & 8D** → **Open** | Scroll D1–D4, point at **Google Docs / Word (.docx)** | 8D in minutes |
| 11 | 2:48–3:00 | **Ask SenpaiQC** (or closing slide) | Tap the first Bahasa Indonesia suggestion; then the live URL | Results and close |

## Narration

### 1. Opening (0:00–0:12)

> Hi, I'm Simon. This is SenpaiQC: it turns a senior inspector's eye into every shift's
> standard, and it runs on Google Cloud.

### 2. Problem (0:12–0:30)

> In casting plants across Southeast Asia, quality depends on who is on shift. The best
> inspector's judgment is never written down and leaves when they retire. Vision AI needs
> thousands of labelled images per part, and every escaped defect costs days of 8D work.

### 3. Teach (0:30–0:58)

> So the expert teaches once, on video. This two-minute video became four rule cards in nine
> seconds, using Gemini on Vertex AI: what the defect looks like, the accept limit, the fix, and
> the exact timestamp in the video. Nothing reaches the line until the expert approves it, so I
> approve the porosity rule now.

### 4. Inspect: fast path (0:58–1:15)

> On the line, the operator just takes a photo. A small YOLO model on CPU decides the easy parts
> in about a second, at zero AI cost. On our held-out test, that was 99 percent of parts.

### 5. Inspect: Gemini (1:15–1:35)

> Unclear, unknown or new parts go to Gemini. It circles the defect and cites the expert rule it
> used, so the inspector checks the reasoning instead of trusting a score. About three seconds,
> and a tenth of a cent.

### 6. Act: rework steps (1:35–1:50)

> The decision becomes the expert's rework steps, in the operator's own language: English,
> Bahasa Indonesia, Thai or Vietnamese. Scrap always needs a person to confirm.

### 7. Act: robot cell (1:50–2:02)

> The same decision can drive a robot. In this simulated SO-101 cell, every move passes a safety
> gate, and any doubt sends the part to the hold bin.

### 8. Learn: spike and alert (2:02–2:20)

> Every decision lands in BigQuery, and a plain three-sigma p-chart flags spikes. When it does,
> Pub/Sub sends the alert straight to the QC team's Telegram. This process history is synthetic,
> with one planted cause.

### 9. Learn: root cause (2:20–2:38)

> One click, and an ADK agent on Vertex AI investigates, using only read-only queries. In about
> thirty seconds, for under three cents, it found mould MD-04 with material lot LOT-2409C: the
> planted cause, not the decoy machine.

### 10. 8D report (2:38–2:48)

> It drafts the 8D report. The engineer edits, approves and exports it to Google Docs or Word:
> minutes instead of days.

### 11. Results and close (2:48–3:00)

> On 200 held-out images: 99 percent recall, zero false rejects, and seven cents of AI per
> thousand parts. SenpaiQC: teach once, inspect every part, fix it right. Try it at the link on screen.

## Editing notes

- **Cut the waits, keep the result:** teach drafting (~10 s), Gemini second opinion (~3 s), root
  cause (~30 s). Add a small "sped up" or "cut" marker if you like.
- **Captions** help judges watching without sound: put the key numbers on screen (99% recall,
  9 s video → 4 rules, 30 s to root cause, $0.07 per 1,000 parts).
- **Say "synthetic"** whenever the process history or root-cause scenario is on screen.
- **Phone shot:** a 3-second close-up of the Telegram alert is the most memorable moment.
- **Length:** the submission asks for 3 minutes; if you run long, drop shot 7 (robot) first.

## If something goes wrong while recording

| Problem | Fix |
|---|---|
| **Check for spikes** opens nothing | The investigation is still open: run `demo_reset.py` (step 1 above), then scan again |
| Telegram alert does not arrive | **Settings & status → Spike alerts → Send test**; Pub/Sub retries for up to a day |
| First page loads slowly | Cloud Run cold start; open the app a minute before recording |
| Gemini says rate limit or budget | The app allows 20 AI calls a minute and a daily budget; wait a minute, or record the next day |
| Sign-in says invalid token | Copy the token again with the `gcloud secrets` command; no spaces around it |
