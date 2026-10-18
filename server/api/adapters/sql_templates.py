"""Read-only, parameterised SQL. The agent picks a template by name; it never writes SQL.

Each template has a BigQuery and a SQLite variant. `{table}` and `{dim}` are filled from
allow-lists here, never from model output; values always go through bound parameters.
"""
from __future__ import annotations

DIMENSIONS = ("line_id", "shift", "machine_id", "mould_id", "material_lot")

_DAY = {"bigquery": "FORMAT_TIMESTAMP('%F', event_ts)", "sqlite": "substr(event_ts, 1, 10)"}

_T = {
    # p-chart subgroups for one defect: one row per (day, shift)
    "shift_rates": """
        SELECT {day} AS day, shift, COUNT(*) AS n,
               SUM(CASE WHEN defect_name = @defect AND decision != 'pass' THEN 1 ELSE 0 END) AS d
        FROM {table}
        WHERE part_number = @part_number
        GROUP BY day, shift ORDER BY day, shift""",
    # defect rate split by one process dimension within a time window
    "rate_by_dim": """
        SELECT {dim} AS value, COUNT(*) AS n,
               SUM(CASE WHEN defect_name = @defect AND decision != 'pass' THEN 1 ELSE 0 END) AS d
        FROM {table}
        WHERE part_number = @part_number AND event_ts >= @start AND event_ts < @end
        GROUP BY value ORDER BY value""",
    # interaction of mould and material lot (the classic casting suspects)
    "rate_by_mould_lot": """
        SELECT mould_id, material_lot, COUNT(*) AS n,
               SUM(CASE WHEN defect_name = @defect AND decision != 'pass' THEN 1 ELSE 0 END) AS d
        FROM {table}
        WHERE part_number = @part_number AND event_ts >= @start AND event_ts < @end
        GROUP BY mould_id, material_lot HAVING COUNT(*) >= @min_n ORDER BY mould_id, material_lot""",
    "first_seen": """
        SELECT {dim} AS value, MIN(event_ts) AS first_ts, MAX(event_ts) AS last_ts, COUNT(*) AS n
        FROM {table} WHERE part_number = @part_number GROUP BY value ORDER BY first_ts""",
    "pareto": """
        SELECT defect_name, COUNT(*) AS n FROM {table}
        WHERE decision != 'pass' AND defect_name IS NOT NULL AND event_ts >= @start
        GROUP BY defect_name ORDER BY n DESC""",
    "path_summary": """
        SELECT CASE WHEN line_id LIKE 'SYN-%' THEN 1 ELSE 0 END AS synthetic,
               path, decision, COUNT(*) AS n, SUM(cost_usd) AS cost_usd,
               SUM(CASE WHEN confirmed THEN 1 ELSE 0 END) AS confirmed
        FROM {table} WHERE event_ts >= @start GROUP BY synthetic, path, decision""",
    "latencies": """
        SELECT path, latency_ms FROM {table}
        WHERE event_ts >= @start AND line_id NOT LIKE 'SYN-%' ORDER BY event_ts DESC LIMIT 5000""",
    "daily": """
        SELECT {day} AS day, COUNT(*) AS n,
               SUM(CASE WHEN decision != 'pass' THEN 1 ELSE 0 END) AS rejects,
               SUM(CASE WHEN path = 'er2' THEN 1 ELSE 0 END) AS escalations,
               SUM(cost_usd) AS cost_usd
        FROM {table} WHERE event_ts >= @start GROUP BY day ORDER BY day""",
}

TEMPLATE_NAMES = tuple(_T)


def render(name: str, dialect: str, table: str, dim: str | None = None) -> str:
    if name not in _T:
        raise ValueError(f"unknown template {name!r}; allowed: {TEMPLATE_NAMES}")
    if "{dim}" in _T[name]:
        if dim not in DIMENSIONS:
            raise ValueError(f"dimension {dim!r} not in {DIMENSIONS}")
    sql = _T[name].format(table=table, dim=dim or "", day=_DAY[dialect])
    return sql
