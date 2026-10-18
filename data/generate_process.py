"""Generate SYNTHETIC process + inspection events with one planted root cause.

Everything this script writes is synthetic and is labelled so: line_id starts with "SYN-",
latency_ms and cost_usd are 0 (they are never measured on synthetic rows).

Planted cause (written to data/planted_cause.json so eval can score the agent):
  from day 18, material lot LOT-2409C feeds machine MC-02. On mould MD-04 that lot raises
  porosity from ~3% to ~30%. The same lot on MD-03, and MD-04 with other lots, stay normal,
  so only the mould x lot interaction explains the spike. Machine MC-02 looks guilty too
  (it hosts MD-04) — a decoy a shallow analysis would stop at.

Usage:  python data/generate_process.py [--start 2026-09-08] [--days 30] [--seed 7]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
PART = "IMP-200"
MACHINES = {"MC-01": ["MD-01", "MD-02"], "MC-02": ["MD-03", "MD-04"], "MC-03": ["MD-05", "MD-06"]}
BASE_LOTS = ["LOT-2408A", "LOT-2408B", "LOT-2409A", "LOT-2409B"]
PLANTED = {"mould_id": "MD-04", "material_lot": "LOT-2409C", "machine_id": "MC-02", "start_day": 18,
           "defect_name": "porosity", "rate_after": 0.30}
BASE_RATES = {"porosity": 0.030, "shrinkage": 0.012, "crack": 0.004, "burr": 0.015}
PARTS_PER_MOULD_SHIFT = 60
SHIFTS = {"A": 6, "B": 14}  # start hour UTC, 8-hour shifts
ESCALATION_SHARE = 0.15  # share of synthetic rows tagged as ER 2 path (illustrative only)


def lot_for(rng: random.Random, day: int, machine: str) -> str:
    if day >= PLANTED["start_day"] and machine == PLANTED["machine_id"]:
        return PLANTED["material_lot"]
    if day >= PLANTED["start_day"] and machine == "MC-01" and rng.random() < 0.15:
        return PLANTED["material_lot"]  # the lot also appears elsewhere, without effect
    return BASE_LOTS[(day // 7 + list(MACHINES).index(machine)) % len(BASE_LOTS)]


def generate(start: datetime, days: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for day in range(1, days + 1):
        date = start + timedelta(days=day - 1)
        for shift, hour in SHIFTS.items():
            for machine, moulds in MACHINES.items():
                lot = lot_for(rng, day, machine)
                for mould in moulds:
                    for i in range(PARTS_PER_MOULD_SHIFT + rng.randint(-5, 5)):
                        ts = date + timedelta(hours=hour, seconds=rng.randint(0, 8 * 3600 - 1))
                        rates = dict(BASE_RATES)
                        if day >= PLANTED["start_day"] and mould == PLANTED["mould_id"] and lot == PLANTED["material_lot"]:
                            rates[PLANTED["defect_name"]] = PLANTED["rate_after"]
                        defect = None
                        r = rng.random()
                        acc = 0.0
                        for name, p in rates.items():
                            acc += p
                            if r < acc:
                                defect = name
                                break
                        decision = "pass" if defect is None else ("scrap" if defect == "crack" else "rework")
                        rows.append({
                            "event_ts": ts.isoformat(), "line_id": "SYN-L1", "shift": shift,
                            "machine_id": machine, "mould_id": mould, "material_lot": lot,
                            "part_number": PART,
                            "path": "er2" if rng.random() < ESCALATION_SHARE else "yolo",
                            "defect_name": defect, "decision": decision, "confirmed": defect is not None,
                            "latency_ms": 0, "cost_usd": 0.0,
                        })
    rows.sort(key=lambda r: r["event_ts"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-09-08")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    rows = generate(start, a.days, a.seed)
    out = HERE / "process_events.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    truth = PLANTED | {"part_number": PART, "first_affected_date": (start + timedelta(days=PLANTED["start_day"] - 1)).date().isoformat(),
                       "synthetic": True, "seed": a.seed}
    (HERE / "planted_cause.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote {len(rows)} SYNTHETIC rows to {out.name}; planted cause -> planted_cause.json")


if __name__ == "__main__":
    main()
