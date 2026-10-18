"""Load seed data into the configured backend (local SQLite or GCP).

  python seed.py            # cards + synthetic process events (skips events if present)
  python seed.py --reset    # local only: wipe events first
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime

from config import REPO_ROOT
from container import get_container
from domain.models import DefectKnowledgeCard, InspectionEvent

DATA = REPO_ROOT / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    c = get_container()
    for d in json.loads((DATA / "seed_cards.json").read_text()):
        if c.cards.get(d["card_id"]) is None:
            c.cards.put(DefectKnowledgeCard(**d))
    print("cards:", len(c.cards.list()))

    csv_path = DATA / "process_events.csv"
    if not csv_path.exists():
        raise SystemExit("run `python data/generate_process.py` first")
    if a.reset and hasattr(c.events, "clear"):
        c.events.clear()
    if hasattr(c.events, "count") and c.events.count() > 0:
        print("events already loaded:", c.events.count())
        return
    with csv_path.open() as f:
        rows = [InspectionEvent(
            event_ts=datetime.fromisoformat(r["event_ts"]), line_id=r["line_id"], shift=r["shift"],
            machine_id=r["machine_id"], mould_id=r["mould_id"], material_lot=r["material_lot"],
            part_number=r["part_number"], path=r["path"], defect_name=r["defect_name"] or None,
            decision=r["decision"], confirmed=r["confirmed"] == "True", latency_ms=int(r["latency_ms"]),
            cost_usd=float(r["cost_usd"]),
        ) for r in csv.DictReader(f)]
    for i in range(0, len(rows), 5000):
        c.events.write_many(rows[i:i + 5000])
    print("loaded SYNTHETIC events:", len(rows))


if __name__ == "__main__":
    main()
