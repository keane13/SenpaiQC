import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ConfirmBar, DecisionBanner, DefectList, DefectOverlay, PathInfo, checkedBy } from "../components";
import type { InspectionResult } from "../types";
import { DecisionBadge, downloadCsv, Empty, Icon, Modal, PageHeader, Stat, timeAgo } from "../ui";

type Filter = "needs" | "all" | "pass" | "rework" | "scrap";
const FILTERS: [Filter, string][] = [["needs", "Needs me"], ["all", "All"], ["pass", "Pass"], ["rework", "Rework"], ["scrap", "Scrap"]];

export default function Queue({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<InspectionResult[] | null>(null);
  const [filter, setFilter] = useState<Filter>("needs");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(new URLSearchParams(location.hash.split("?")[1] ?? "").get("open"));
  const [err, setErr] = useState("");

  const load = () => api<InspectionResult[]>("/decisions?limit=300").then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const needs = (d: InspectionResult) => d.needs_human_confirm && !d.confirmed;
  const count = (f: Filter) => (items ?? []).filter((d) => f === "all" || (f === "needs" ? needs(d) : d.decision === f)).length;
  const shown = useMemo(() => (items ?? [])
    .filter((d) => filter === "all" || (filter === "needs" ? needs(d) : d.decision === filter))
    .filter((d) => `${d.id} ${d.part_number} ${d.decision} ${d.rationale} ${(d.line && Object.values(d.line).join(" ")) || ""}`.toLowerCase().includes(q.toLowerCase())),
  [items, filter, q]);
  const current = items?.find((d) => d.id === open) ?? null;
  const close = () => { setOpen(null); if (location.hash.includes("?")) history.replaceState(null, "", "#queue"); };

  const exportCsv = () => downloadCsv("senpaiqc-inspections.csv", [
    ["id", "time", "part", "line", "machine", "mould", "lot", "checked_by", "ai_decision", "final_decision", "confirmed_by", "latency_ms", "cost_usd", "rationale"],
    ...(items ?? []).map((d: any) => [d.id, d.created_at, d.part_number, d.line?.line_id, d.line?.machine_id, d.line?.mould_id, d.line?.material_lot,
      d.path, d.model_decision ?? d.decision, d.decision, d.confirmed_by, d.latency_ms, d.cost_usd, d.rationale]),
  ]);

  return (
    <>
      <PageHeader eyebrow="Quality operations" title="Needs confirmation"
        sub="Every scrap, every unknown defect and every offline result waits here. Open a part, look at the evidence, and make the call."
        actions={<button className="btn btn-quiet" onClick={exportCsv} disabled={!items?.length}><Icon name="download" /> Export audit trail (CSV)</button>} />
      {err && <div className="banner"><Icon name="alert" />{err}</div>}

      <div className="stat-grid">
        <Stat label="Waiting for you" value={count("needs")} icon="clock" glow="rgba(246,189,96,.12)" foot="Oldest first is a good habit" />
        <Stat label="Rework" value={count("rework")} icon="wrench" foot="In the loaded records" />
        <Stat label="Scrap" value={count("scrap")} icon="x" glow="rgba(255,111,131,.1)" foot="Each one confirmed by a person" />
        <Stat label="Pass" value={count("pass")} icon="check" glow="rgba(53,212,154,.1)" foot="In the loaded records" />
      </div>

      <section className="panel">
        <div className="toolbar">
          <div><div className="panel-title">Inspection records <span className="muted" style={{ fontWeight: 500 }}>({shown.length})</span></div>
            <div className="panel-desc">Select a row to see the photo, the marked defects and the expert rule used.</div></div>
          <label className="search"><Icon name="search" size={16} /><input type="search" placeholder="Search part, ID, mould, lot…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search records" /></label>
        </div>
        <div className="filters" role="group" aria-label="Filter records">
          {FILTERS.map(([k, label]) => (
            <button key={k} className="filter-pill" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}<span className="n">{count(k)}</span></button>
          ))}
        </div>
        {items === null && !err && <p style={{ padding: "0 18px 18px" }}><span className="spinner" /> Loading…</p>}
        {items && shown.length === 0 && (filter === "needs" ? <Empty title="Nothing waiting for you">Good shift. New items appear here as parts are inspected.</Empty> : <Empty title="No records match">Try another filter or clear the search.</Empty>)}
        {shown.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Part</th><th>Line / mould / lot</th><th>Checked by</th><th>Decision</th><th>Status</th><th>When</th><th /></tr></thead>
              <tbody>
                {shown.map((d) => (
                  <tr key={d.id} className="clickable" onClick={() => setOpen(d.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setOpen(d.id)}>
                    <td><div className="cell-main">{d.part_number}</div><div className="cell-sub mono">{d.id}</div></td>
                    <td className="small">{d.line ? `${d.line.line_id} · ${d.line.mould_id} · ${d.line.material_lot}` : "—"}</td>
                    <td>{checkedBy(d)}</td>
                    <td><DecisionBadge decision={d.decision} /></td>
                    <td>{d.confirmed ? <span className="status pass">Confirmed</span> : needs(d) ? <span className="status review">Needs you</span> : <span className="status neutral">Auto</span>}</td>
                    <td className="small">{timeAgo((d as any).created_at)}</td>
                    <td><Icon name="chevron" size={15} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-foot"><span>Showing {shown.length} of {items?.length ?? 0} loaded records</span><span>Your confirmations are what the quality record keeps.</span></div>
      </section>

      {current && (
        <Modal wide title={`${current.part_number} · ${current.decision}`} sub={<span className="mono">{current.id}</span>} onClose={close}>
          <div className="inspect-grid">
            <div><DefectOverlay result={current} /></div>
            <div>
              <DecisionBanner result={current} />
              <PathInfo result={current} />
              <p>{current.rationale}</p>
              <DefectList result={current} />
            </div>
          </div>
          <div className="section">
            <ConfirmBar result={current} onDone={(r) => { setItems((xs) => xs?.map((x) => (x.id === r.id ? { ...x, ...r } : x)) ?? null); onChange(); close(); }} />
          </div>
        </Modal>
      )}
    </>
  );
}
