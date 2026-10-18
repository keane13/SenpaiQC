-- bq query --use_legacy_sql=false < infra/bigquery.sql   (replace PROJECT)
CREATE SCHEMA IF NOT EXISTS `PROJECT.DATASET` OPTIONS (location = 'REGION');

CREATE TABLE IF NOT EXISTS `PROJECT.DATASET.inspection_events` (
  event_ts     TIMESTAMP NOT NULL,
  line_id      STRING,   -- rows starting with "SYN-" are synthetic seed data
  shift        STRING,
  machine_id   STRING,
  mould_id     STRING,
  material_lot STRING,
  part_number  STRING,
  path         STRING,   -- yolo | er2
  defect_name  STRING,
  decision     STRING,   -- pass | rework | scrap
  confirmed    BOOL,
  latency_ms   INT64,
  cost_usd     FLOAT64
)
PARTITION BY DATE(event_ts)
CLUSTER BY part_number, defect_name;
