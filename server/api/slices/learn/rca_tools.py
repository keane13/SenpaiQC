"""Root-cause tools. The ADK agent calls these; they are plain, read-only, deterministic.

`query_events` only accepts a template name from an allow-list plus parameters, so the
model can never run free-form SQL.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from adapters.sql_templates import DIMENSIONS
from domain.models import EIGHT_D_KEYS

AGENT_TEMPLATES = ("rate_by_dim", "rate_by_mould_lot", "first_seen", "shift_rates")


class Hypothesis(BaseModel):
    rank: int
    statement: str
    blamed: dict[str, str] = Field(description="dimension -> value, e.g. {'mould_id': 'MD-04'}")
    evidence: list[str] = Field(description="Counts, rates and before/after comparisons")
    confidence: str = Field(description="high | medium | low")


class Findings(BaseModel):
    hypotheses: list[Hypothesis]
    sections: dict[str, str] = Field(description=f"8D sections keyed by {EIGHT_D_KEYS}")


class RcaToolbox:
    """Tools bound to one investigation. Records every call for the agent trace."""

    def __init__(self, events, cards, investigation: dict):
        self.events = events
        self.cards = cards
        self.inv = investigation
        self.trace: list[dict] = []
        self.findings: Optional[Findings] = None

    # ---- tools exposed to the agent -------------------------------------------------
    def query_events(self, sql_template: str, params_json: str) -> dict:
        """Run a read-only templated query on inspection_events.

        Args:
            sql_template: one of rate_by_dim, rate_by_mould_lot, first_seen, shift_rates.
            params_json: JSON object. Keys: dim (one of line_id, shift, machine_id, mould_id,
                material_lot; for rate_by_dim and first_seen), start and end (ISO timestamps; for
                rate_by_dim and rate_by_mould_lot), min_n (int; rate_by_mould_lot). part_number and
                defect are filled in from the investigation.
        Returns:
            {"rows": [...]} with n, d and rate per group, or {"error": "..."}.
        """
        try:
            if sql_template not in AGENT_TEMPLATES:
                raise ValueError(f"template must be one of {AGENT_TEMPLATES}")
            p = json.loads(params_json or "{}")
            if not isinstance(p, dict):
                raise ValueError("params_json must be a JSON object")
            allowed = {"dim", "start", "end", "min_n"}
            if set(p) - allowed:
                raise ValueError(f"unknown params {sorted(set(p) - allowed)}")
            if "dim" in p and p["dim"] not in DIMENSIONS:
                raise ValueError(f"dim must be one of {DIMENSIONS}")
            params: dict[str, Any] = {"part_number": self.inv["part_number"]}
            if sql_template in ("rate_by_dim", "rate_by_mould_lot", "shift_rates"):
                params["defect"] = self.inv["defect_name"]
            if sql_template in ("rate_by_dim", "rate_by_mould_lot"):
                params["start"] = _ts(p.get("start", "2000-01-01T00:00:00+00:00"))
                params["end"] = _ts(p.get("end", "2100-01-01T00:00:00+00:00"))
            if sql_template == "rate_by_mould_lot":
                params["min_n"] = int(p.get("min_n", 30))
            if sql_template in ("rate_by_dim", "first_seen"):
                params["dim"] = p.get("dim", "mould_id")
            rows = self.events.query(sql_template, params)
            for r in rows:
                if "d" in r and r.get("n"):
                    r["rate"] = round((r["d"] or 0) / r["n"], 4)
                for k, v in list(r.items()):
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
            out = {"rows": rows}
        except (ValueError, json.JSONDecodeError) as exc:
            out = {"error": str(exc)}
        self._log("query_events", {"sql_template": sql_template, "params_json": params_json}, out)
        return out

    def get_cards(self, part_number: str) -> dict:
        """Approved Defect Knowledge Cards for a part number (the expert's rules)."""
        cards = [c.model_dump(mode="json", include={"card_id", "defect_name", "accept_limit", "severity",
                                                    "rework_action", "typical_location"})
                 for c in self.cards.list(part_number=part_number, status="approved")]
        out = {"cards": cards}
        self._log("get_cards", {"part_number": part_number}, out)
        return out

    def get_process_context(self, window: str = "spike") -> dict:
        """Facts about the flagged spike: defect, part, the out-of-control subgroup, its rate and
        control limits, plus suggested before/after windows (ISO timestamps).

        Args:
            window: "spike" (default).
        """
        flag_day = datetime.fromisoformat(self.inv["shift_key"].split("/")[0]).replace(tzinfo=timezone.utc)
        out = {
            "investigation_id": self.inv["id"],
            "part_number": self.inv["part_number"],
            "defect_name": self.inv["defect_name"],
            "flagged_subgroup": self.inv["shift_key"],
            "rate": self.inv["rate"], "center_line": self.inv["center"], "ucl": self.inv["ucl"],
            "data_start": self.inv.get("data_start"),
            "data_end": self.inv.get("data_end"),
            "suggested_before": {"start": self.inv.get("data_start"), "end": (flag_day - timedelta(days=3)).isoformat()},
            "suggested_after": {"start": (flag_day - timedelta(days=3)).isoformat(), "end": self.inv.get("data_end")},
            "dimensions": list(DIMENSIONS),
        }
        self._log("get_process_context", {"window": window}, out)
        return out

    def draft_8d(self, findings_json: str) -> dict:
        """Submit ranked hypotheses and the 8D draft. Call exactly once, at the end.

        Args:
            findings_json: JSON {"hypotheses": [{"rank", "statement", "blamed": {dimension: value},
                "evidence": [str], "confidence"}], "sections": {D1_team..D8_recognition: str}}.
        Returns:
            {"ok": true} or {"error": "..."} — fix the JSON and call again on error.
        """
        try:
            f = Findings.model_validate_json(findings_json)
            missing = [k for k in EIGHT_D_KEYS if k not in f.sections]
            if missing:
                raise ValueError(f"missing 8D sections: {missing}")
            bad = [k for h in f.hypotheses for k in h.blamed if k not in DIMENSIONS]
            if bad:
                raise ValueError(f"blamed dimensions must be in {DIMENSIONS}, got {bad}")
            self.findings = f
            out = {"ok": True}
        except (ValidationError, ValueError) as exc:
            out = {"error": str(exc)[:800]}
        self._log("draft_8d", {"chars": len(findings_json or "")}, out)
        return out

    # ---- helpers -------------------------------------------------------------------
    def _log(self, tool: str, args: dict, out: dict) -> None:
        preview = json.dumps(out, default=str)
        self.trace.append({"tool": tool, "args": args, "result_preview": preview[:600]})


def _ts(v: str) -> datetime:
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def z_two_prop(d1: int, n1: int, d2: int, n2: int) -> float:
    """Two-proportion z statistic (group vs rest)."""
    if not n1 or not n2:
        return 0.0
    p = (d1 + d2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0
    return ((d1 / n1) - (d2 / n2)) / se if se else 0.0
