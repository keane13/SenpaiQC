"""Local adapters: SQLite for events and documents, the filesystem for blobs.

Used for development and tests; the same ports are served by Firestore/GCS/BigQuery on GCP.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from domain.models import DefectKnowledgeCard, InspectionEvent

from .sql_templates import render

# One SQLite connection is shared by FastAPI's worker threads: every read and write takes the lock.
_lock = threading.RLock()


class _DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS docs (collection TEXT, id TEXT, data TEXT, PRIMARY KEY (collection, id));
            CREATE TABLE IF NOT EXISTS inspection_events (
                event_ts TEXT, line_id TEXT, shift TEXT, machine_id TEXT, mould_id TEXT,
                material_lot TEXT, part_number TEXT, path TEXT, defect_name TEXT,
                decision TEXT, confirmed INTEGER, latency_ms INTEGER, cost_usd REAL);
            CREATE INDEX IF NOT EXISTS ev_ts ON inspection_events(event_ts);
            """
        )


_dbs: dict[Path, _DB] = {}


def db(path: Path) -> _DB:
    with _lock:
        if path not in _dbs:
            _dbs[path] = _DB(path)
        return _dbs[path]


class SqliteDocStore:
    def __init__(self, path: Path):
        self.db = db(path)

    def put(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        with _lock:
            self.db.conn.execute(
                "INSERT OR REPLACE INTO docs VALUES (?, ?, ?)",
                (collection, doc_id, json.dumps(data, default=str)),
            )
            self.db.conn.commit()

    def get(self, collection: str, doc_id: str) -> Optional[dict[str, Any]]:
        with _lock:
            row = self.db.conn.execute(
                "SELECT data FROM docs WHERE collection = ? AND id = ?", (collection, doc_id)
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def list(self, collection: str, limit: int = 200) -> list[dict[str, Any]]:
        with _lock:
            rows = self.db.conn.execute(
                "SELECT data FROM docs WHERE collection = ? ORDER BY rowid DESC LIMIT ?", (collection, limit)
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]


class DocCardStore:
    """CardStore on top of any DocStore."""

    def __init__(self, docs):
        self.docs = docs

    def list(self, part_number=None, status=None):
        cards = [DefectKnowledgeCard(**d) for d in self.docs.list("cards", limit=1000)]
        return [c for c in cards
                if (part_number is None or c.part_number == part_number)
                and (status is None or c.status.value == status)]

    def get(self, card_id):
        d = self.docs.get("cards", card_id)
        return DefectKnowledgeCard(**d) if d else None

    def put(self, card):
        self.docs.put("cards", card.card_id, card.model_dump(mode="json"))


class SqliteEventSink:
    dialect = "sqlite"

    def __init__(self, path: Path):
        self.db = db(path)

    def write(self, e: InspectionEvent) -> None:
        self.write_many([e])

    def write_many(self, events: list[InspectionEvent]) -> None:
        with _lock:
            self.db.conn.executemany(
                "INSERT INTO inspection_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(e.event_ts.isoformat(), e.line_id, e.shift, e.machine_id, e.mould_id, e.material_lot,
                  e.part_number, e.path, e.defect_name, e.decision, int(e.confirmed), e.latency_ms,
                  e.cost_usd) for e in events],
            )
            self.db.conn.commit()

    def query(self, template: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        sql = render(template, "sqlite", "inspection_events", params.pop("dim", None))
        sql = re.sub(r"@(\w+)", r":\1", sql)
        bound = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in params.items()}
        with _lock:
            return [dict(r) for r in self.db.conn.execute(sql, bound).fetchall()]

    def count(self) -> int:
        with _lock:
            return self.db.conn.execute("SELECT COUNT(*) FROM inspection_events").fetchone()[0]

    def clear(self) -> None:
        with _lock:
            self.db.conn.execute("DELETE FROM inspection_events")
            self.db.conn.commit()


class LocalBlobStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def save(self, path: str, data: bytes, content_type: str) -> str:
        dst = self.root / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return f"local://{path}"

    def load(self, uri: str) -> bytes:
        return (self.root / uri.removeprefix("local://")).read_bytes()

    def upload_url(self, path: str, content_type: str, max_bytes: int) -> None:
        return None  # local: the browser uploads straight to the API, which has no 32 MiB cap here

    def size(self, uri: str):
        p = self.root / uri.removeprefix("local://")
        return p.stat().st_size if p.exists() else None

    def download_to_file(self, uri: str, dst: str) -> None:
        import shutil

        shutil.copyfile(self.root / uri.removeprefix("local://"), dst)
