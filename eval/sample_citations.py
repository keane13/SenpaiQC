"""Sample 30 ER 2 escalations from the last golden run for hand-checking card citations.

Writes eval/citation_review.csv with an empty `correct` column. Open each image, read the
cited card, and fill `correct` with 1 or 0. run_all.py then reports card_citation_accuracy.
"""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = json.loads((ROOT / "eval" / "results" / "golden_before.json").read_text())["rows"]
esc = [r for r in rows if r["route"] == "er2" and r["model"] and "robotics" in r["model"]]
random.Random(0).shuffle(esc)
out = ROOT / "eval" / "citation_review.csv"
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["decision_id", "image", "label", "decision", "cited", "correct"])
    for r in esc[:30]:
        w.writerow([r["id"], r["path"], r["label"], r["decision"], " ".join(c or "UNKNOWN" for c in r["cited"]), ""])
print(f"wrote {min(30, len(esc))} rows to {out}")
