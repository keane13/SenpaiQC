"""Create the BigQuery dataset and table, and let the service account write to that dataset only.

  python infra/bq_setup.py PROJECT REGION SERVICE_ACCOUNT_EMAIL [DATASET]
Uses the Python client instead of the `bq` CLI, so it works wherever the app's own
dependencies are installed. Safe to run again: existing dataset, table and grant are kept.
"""
import sys
from pathlib import Path

from google.cloud import bigquery

project, region, sa = sys.argv[1], sys.argv[2], sys.argv[3]
dataset = sys.argv[4] if len(sys.argv) > 4 else "senpaiqc"
client = bigquery.Client(project=project)

ddl = (Path(__file__).parent / "bigquery.sql").read_text()
ddl = ddl.replace("PROJECT", project).replace("DATASET", dataset).replace("REGION", region)
ddl = "\n".join(line for line in ddl.splitlines() if not line.lstrip().startswith("--"))
for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
    client.query(stmt, location=region).result()
print(f"dataset {project}.{dataset} and table inspection_events ready ({region})")

ds = client.get_dataset(f"{project}.{dataset}")
entry = bigquery.AccessEntry(role="WRITER", entity_type="userByEmail", entity_id=sa)
if not any(e.entity_id == sa and e.role == "WRITER" for e in ds.access_entries):
    ds.access_entries = list(ds.access_entries) + [entry]
    client.update_dataset(ds, ["access_entries"])
    print(f"granted WRITER on the dataset to {sa}")
else:
    print(f"{sa} already has WRITER on the dataset")
