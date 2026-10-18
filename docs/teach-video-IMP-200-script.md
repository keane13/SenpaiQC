# Teach video for IMP-200: recording script

The narrated video a QC inspector records once and uploads in **Expert knowledge → Teach from a
video**. Gemini on Vertex AI watches it and drafts one rule card per defect; the inspector then
edits and approves each card in the app. Slides: [`teach-video-IMP-200.pptx`](teach-video-IMP-200.pptx)
(the same narration is in the speaker notes).

- **Length:** about 2 min 30 s (the app accepts up to 10 min / 500 MB).
- **Who speaks:** a QC inspector, in their own words. English or Bahasa Indonesia both work; the
  cards are written in English either way.
- **Images:** Kaggle casting dataset, illustrative only. A real part on camera is better.

## Before you record

1. Replace `[name]` in the opening with the inspector's name and role.
2. For each defect, say all six things Gemini turns into card fields: **what it looks like**, **where
   it appears**, **how to look** (angle and light), **the accept limit** (with numbers),
   **the decision** (pass / rework / scrap) and **the fix**.
3. Say the numbers clearly ("0.5 millimetres", "30 degrees"). Gemini copies them into the accept limit.
4. Point at the defect on screen when you name it; the card keeps the video timestamp.
5. After the upload, check every draft card and approve it. Drafts are never used on the line.

## Running order

| Time | Slide | Segment | Decision |
|---|---|---|---|
| 0:00–0:15 | 1 | Opening: the part and a good example | – |
| 0:15–0:50 | 2 | Porosity | Rework; scrap if on the sealing face |
| 0:50–1:20 | 3 | Shrinkage | Rework (weld repair) |
| 1:20–1:50 | 4 | Crack | Scrap, never rework |
| 1:50–2:20 | 5 | Burr | Minor; under 0.3 mm passes |
| 2:20–2:30 | 6 | Closing | – |

## Narration

### 1. Opening (0:00–0:15)

> I'm [name], a QC inspector. This is part IMP-200, a cast impeller. I'll walk through the four
> most common defects, and when a part passes, needs rework, or must be scrapped. This is a good
> part: the hub surface is smooth, with no dark spots.

### 2. Porosity (0:15–0:50)

> First defect: porosity. You see round pinholes, clusters of small dark dots, or dull spots near
> the hub. It usually shows up at the hub and the blade root. To see it, tilt the part about 30
> degrees so the light rakes across the hub surface. The pinholes show as dark dots with a bright
> rim. The limit: at most 2 pinholes under 0.5 millimetres outside the sealing face, and none at
> all on the sealing face. This is rework: grind the area flush, and fill it with approved epoxy if
> it is less than 1 millimetre deep. If any pinhole is on the sealing face, scrap the part.

*On camera: point at the small dots on the left side of the rim.*

### 3. Shrinkage (0:50–1:20)

> Second: shrinkage. The cavity is irregular and jagged, with a branch-like, dendritic texture
> inside, and the surface looks sunken. It forms in the thick sections at the hub. Tilt the part
> 45 degrees toward the light and look into the thick hub section. The limit: no visible shrinkage
> cavity on any machined face. This is rework: mark the cavity, send it to weld repair, re-machine
> it, and inspect it again.

### 4. Crack (1:20–1:50)

> Third, and the most dangerous: crack. It is a thin dark line that follows a blade edge or the
> outer rim. Rotate the part about minus 20 degrees and follow each blade edge and the outer rim
> under low-angle light. The limit is zero, there is no tolerance. This is scrap. Do not rework
> it, and tag the mould for inspection.

*On camera: point at the line on the lower-left of the rim.*

### 5. Burr (1:50–2:20)

> Fourth: burr, or flash. You see a raised, rough edge, a thin fin of metal along the parting line
> of the mould, on the outer rim. View the part edge-on, at about 80 degrees, so the raised flash
> stands out against the background. Flash under 0.3 millimetres high is acceptable. Above that it
> is a minor defect: deburr it with a hand file along the parting line, blow off the chips, and
> re-inspect the edge.

*On camera: point at the rough edge along the rim.*

### 6. Closing (2:20–2:30)

> Those are the four defects for IMP-200. When in doubt, hold the part and ask QC.

## What the cards should say (check after upload)

| Defect | Cues | Location | How to look | Accept limit | Fix |
|---|---|---|---|---|---|
| **Porosity** (rework; scrap on sealing face) | Round pinholes; clusters of small dark dots; dull spots near the hub | Hub and blade root | Tilt 30° so light rakes across the hub: dark dots with a bright rim | Max 2 pinholes under 0.5 mm outside the sealing face; none on it | Grind flush; fill with approved epoxy if under 1 mm deep |
| **Shrinkage** (rework) | Irregular, jagged cavity; branch-like texture inside; sunken surface | Thick sections at the hub | Tilt 45° toward the light and look into the thick hub section | No visible shrinkage cavity on machined faces | Mark the cavity; weld repair; re-machine and re-inspect |
| **Crack** (scrap) | Thin dark line that follows a blade edge or the outer rim | Blade edges and outer rim | Rotate −20° and follow each blade edge and the rim under low-angle light | Zero. No tolerance | Scrap the part; tag the mould for inspection |
| **Burr** (minor) | Raised, rough edge; flash along the parting line | Outer rim and parting line | View edge-on at about 80° so raised flash stands out | Flash under 0.3 mm high is acceptable | Deburr with a hand file; blow off chips; check the edge again |
