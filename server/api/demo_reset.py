"""Close open investigations so the next "Check for spikes" opens a new one and sends an alert.

Nothing is deleted: investigations, hypotheses and 8D reports stay, marked status=closed.
  python server/api/demo_reset.py                 # uses the backend in .env / environment
  BACKEND=gcp GCP_PROJECT=... FIRESTORE_DATABASE=... python server/api/demo_reset.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import get_settings


def main() -> None:
    s = get_settings()
    if s.backend == "gcp":
        from adapters.gcp import FirestoreDocStore

        docs = FirestoreDocStore(s.gcp_project, s.firestore_database)
    else:
        from adapters.local import SqliteDocStore

        docs = SqliteDocStore(s.local_dir / "senpaiqc.db")
    closed = 0
    for inv in docs.list("investigations", 500):
        if inv.get("status") != "closed":
            inv |= {"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat(), "closed_by": "demo-reset"}
            docs.put("investigations", inv["id"], inv)
            closed += 1
            print("closed", inv["id"], inv["defect_name"], inv.get("part_number", ""))
    print(f"{closed} investigation(s) closed on {s.backend}")


if __name__ == "__main__":
    main()
