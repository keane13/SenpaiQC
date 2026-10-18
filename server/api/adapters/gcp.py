"""GCP adapters: Firestore documents, Cloud Storage blobs, BigQuery events."""
from __future__ import annotations

from typing import Any, Optional

from google.cloud import bigquery, firestore, storage

from domain.models import InspectionEvent

from .sql_templates import render


class FirestoreDocStore:
    def __init__(self, project: str, database: str = "(default)"):
        self.db = firestore.Client(project=project, database=database)

    def put(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self.db.collection(collection).document(doc_id).set(data)

    def get(self, collection: str, doc_id: str) -> Optional[dict[str, Any]]:
        snap = self.db.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def list(self, collection: str, limit: int = 200) -> list[dict[str, Any]]:
        q = self.db.collection(collection).limit(limit)
        return [d.to_dict() for d in q.stream()]


class GcsBlobStore:
    def __init__(self, project: str, bucket: str):
        self.bucket = storage.Client(project=project).bucket(bucket)

    def save(self, path: str, data: bytes, content_type: str) -> str:
        self.bucket.blob(path).upload_from_string(data, content_type=content_type)
        return f"gs://{self.bucket.name}/{path}"

    def load(self, uri: str) -> bytes:
        path = uri.split("/", 3)[3]
        return self.bucket.blob(path).download_as_bytes()

    def upload_url(self, path: str, content_type: str, max_bytes: int) -> dict:
        """V4 signed PUT URL so large videos go browser -> Cloud Storage, not through Cloud Run
        (32 MiB request cap). On Cloud Run the runtime service account signs through the IAM
        signBlob API, so it needs roles/iam.serviceAccountTokenCreator on itself."""
        from datetime import timedelta

        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        headers = {"x-goog-content-length-range": f"0,{max_bytes}"}
        url = self.bucket.blob(path).generate_signed_url(
            version="v4", expiration=timedelta(minutes=30), method="PUT", content_type=content_type,
            headers=headers, service_account_email=getattr(creds, "service_account_email", None),
            access_token=creds.token,
        )
        return {"url": url, "headers": {"Content-Type": content_type, **headers}, "uri": f"gs://{self.bucket.name}/{path}"}

    def size(self, uri: str) -> int | None:
        blob = self.bucket.get_blob(uri.split("/", 3)[3])
        return blob.size if blob else None

    def download_to_file(self, uri: str, dst: str) -> None:
        self.bucket.blob(uri.split("/", 3)[3]).download_to_filename(dst)


class BigQueryEventSink:
    dialect = "bigquery"

    def __init__(self, project: str, dataset: str):
        self.client = bigquery.Client(project=project)
        self.table = f"`{project}.{dataset}.inspection_events`"
        self.table_id = f"{project}.{dataset}.inspection_events"

    def write(self, e: InspectionEvent) -> None:
        self.write_many([e])

    def write_many(self, events: list[InspectionEvent]) -> None:
        rows = [e.model_dump(mode="json") for e in events]
        errors = self.client.insert_rows_json(self.table_id, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors[:3]}")

    def count(self) -> int:
        return next(iter(self.client.query(f"SELECT COUNT(*) AS n FROM {self.table}").result()))["n"]

    def query(self, template: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        sql = render(template, "bigquery", self.table, params.pop("dim", None))
        qp = [_param(k, v) for k, v in params.items()]
        job = self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=qp))
        return [dict(r.items()) for r in job.result()]


def _param(name: str, value: Any) -> bigquery.ScalarQueryParameter:
    if hasattr(value, "isoformat"):
        return bigquery.ScalarQueryParameter(name, "TIMESTAMP", value)
    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bigquery.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", value)
    return bigquery.ScalarQueryParameter(name, "STRING", str(value))
