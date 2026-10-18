import { useEffect, useState } from "react";
import { api, downloadFile } from "../api";
import { fmtPct } from "../components";
import type { Card, InspectionResult, Investigation } from "../types";
import { downloadCsv, Empty, Icon, Modal, PageHeader, Stat, timeAgo, useToast } from "../ui";

const D_LABELS: [string, string, string][] = [
  ["D1_team", "D1 · Team", "Who works on this problem"],
  ["D2_problem", "D2 · Problem", "What happened, where, how much"],
  ["D3_containment", "D3 · Containment", "What stops bad parts reaching the customer now"],
  ["D4_root_cause", "D4 · Root cause", "Why it happened, with evidence"],
  ["D5_corrective_actions", "D5 · Corrective actions", "What will remove the cause"],
  ["D6_implementation", "D6 · Implementation", "Who does it, by when, and the result"],
  ["D7_prevention", "D7 · Prevent recurrence", "How the system changes so it does not return"],
  ["D8_recognition", "D8 · Recognition", "Close-out and thanks to the team"],
];

export default function Reports() {
  const [invs, setInvs] = useState<Investigation[] | null>(null);
  const [reports, setReports] = useState<Record<string, any>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const toast = useToast();

  const load = async () => {
    try {
      const list = await api<Investigation[]>("/learn/investigations");
      setInvs(list);
      const reps = await Promise.all(list.filter((i) => i.report_id).map((i) => api(`/learn/reports/${i.report_id}`)));
      setReports(Object.fromEntries(reps.map((r) => [r.id, r])));
    } catch (e: any) { setErr(e.message); }
  };
  useEffect(() => { load(); }, []);

  const exportAudit = async () => {
    const ds = await api<InspectionResult[]>("/decisions?limit=1000");
    downloadCsv("senpaiqc-inspection-audit.csv", [
      ["id", "time", "part", "line", "shift", "machine", "mould", "lot", "path", "model", "ai_decision", "final_decision", "needs_confirm", "confirmed_by", "cited_rules", "latency_ms", "cost_usd"],
      ...ds.map((d: any) => [d.id, d.created_at, d.part_number, d.line?.line_id, d.line?.shift, d.line?.machine_id, d.line?.mould_id, d.line?.material_lot,
        d.path, d.reasoning_model, d.model_decision ?? d.decision, d.decision, d.needs_human_confirm, d.confirmed_by,
        d.defects.map((x: any) => x.card_id ?? "UNKNOWN").join(" "), d.latency_ms, d.cost_usd])]);
    toast({ title: "Audit trail exported", body: ` ${ds.length} inspection records.` });
  };
  const exportRules = async () => {
    const cs = await api<Card[]>("/teach/cards");
    downloadCsv("senpaiqc-expert-rules.csv", [["card_id", "part", "defect", "severity", "accept_limit", "rework_action", "status", "approved_by", "source"],
      ...cs.map((c) => [c.card_id, c.part_number, c.defect_name, c.severity, c.accept_limit, c.rework_action, c.status, c.approved_by, `${c.source_video} ${c.source_timestamp}`])]);
    toast({ title: "Rules register exported", body: ` ${cs.length} rules.` });
  };

  const all = Object.values(reports);
  const current = open ? reports[open] : null;
  const inv = invs?.find((i) => i.report_id === open);

  return (
    <>
      <PageHeader eyebrow="Document center" title="Reports & 8D"
        sub="Customer-ready 8D reports drafted by the root-cause agent and finished by the QC engineer, plus traceable exports of every decision and rule." />
      {err && <div className="banner"><Icon name="alert" />{err}</div>}

      <div className="stat-grid">
        <Stat label="8D reports" value={all.length} icon="file" foot="One per analysed spike" />
        <Stat label="Drafts to finish" value={all.filter((r) => r.status === "draft").length} icon="clock" glow="rgba(246,189,96,.12)" foot="Agent drafts need a person" />
        <Stat label="Approved" value={all.filter((r) => r.status === "approved").length} icon="check" glow="rgba(53,212,154,.1)" foot="Ready for the customer" />
        <Stat label="Open spikes" value={(invs ?? []).filter((i) => i.status === "open").length} icon="alert" glow="rgba(255,111,131,.1)" foot="No root cause yet" />
      </div>

      <section className="panel">
        <div className="panel-head"><div><h2 className="panel-title">8D reports</h2><div className="panel-desc">Open one to edit sections D1–D8 and approve it.</div></div></div>
        {invs && all.length === 0 && <Empty title="No 8D reports yet">Flag a spike and run “Find root cause” in Quality analytics.</Empty>}
        <div className="list" style={{ padding: "0 20px 10px" }}>
          {all.map((r) => {
            const i = invs?.find((x) => x.report_id === r.id);
            return (
              <div className="list-item" key={r.id} style={{ alignItems: "center" }}>
                <div className="list-icon"><Icon name="file" /></div>
                <div className="grow">
                  <div className="list-title">{i ? `${i.defect_name} spike · ${i.part_number}` : r.id}</div>
                  <div className="list-desc">{i ? `Flagged ${i.shift_key} at ${fmtPct(i.rate)} · ` : ""}drafted by {r.generated_by}{r.edited_by ? ` · edited by ${r.edited_by}` : ""}</div>
                </div>
                <span className={`status ${r.status === "approved" ? "pass" : "review"}`}>{r.status === "approved" ? "Approved" : "Draft"}</span>
                <span className="list-time hide-sm">{timeAgo(r.updated_at ?? r.created_at)}</span>
                <button className="btn btn-sm btn-quiet" title="Download .docx for Google Docs or Word" aria-label="Download .docx"
                  onClick={() => downloadFile(`/learn/reports/${r.id}/docx`, `${r.id}.docx`).catch((e) => toast({ title: "Download failed", body: ` ${e.message}`, error: true }))}>
                  <Icon name="download" size={15} /> .docx</button>
                <button className="btn btn-sm" onClick={() => setOpen(r.id)}>Open</button>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel section">
        <div className="panel-head"><div><h2 className="panel-title">Exports</h2><div className="panel-desc">Built from the live records at the moment you click. Nothing is sample data.</div></div></div>
        <div className="list" style={{ padding: "0 20px 10px" }}>
          <div className="list-item" style={{ alignItems: "center" }}>
            <div className="list-icon"><Icon name="database" /></div>
            <div className="grow"><div className="list-title">Inspection audit trail</div><div className="list-desc">Each decision with the AI's call, the person's final call, the expert rules cited, time and cost.</div></div>
            <button className="btn btn-sm" onClick={exportAudit}><Icon name="download" size={15} /> CSV</button>
          </div>
          <div className="list-item" style={{ alignItems: "center" }}>
            <div className="list-icon"><Icon name="book" /></div>
            <div className="grow"><div className="list-title">Expert rules register</div><div className="list-desc">Every rule, its limit, fix, approver and source video.</div></div>
            <button className="btn btn-sm" onClick={exportRules}><Icon name="download" size={15} /> CSV</button>
          </div>
        </div>
      </section>

      {current && <ReportEditor report={current} inv={inv} onClose={() => setOpen(null)} onSaved={(r) => { setReports({ ...reports, [r.id]: r }); }} />}
    </>
  );
}

function ReportEditor({ report, inv, onClose, onSaved }: { report: any; inv?: Investigation; onClose: () => void; onSaved: (r: any) => void }) {
  const [sections, setSections] = useState<Record<string, string>>(report.sections);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const save = async (approve: boolean) => {
    setBusy(true);
    try {
      const r = await api(`/learn/reports/${report.id}`, { method: "PUT", body: JSON.stringify({ sections, approve }) });
      onSaved(r);
      toast({ title: approve ? "8D approved" : "Draft saved" });
      if (approve) onClose();
    } catch (e: any) { toast({ title: "Could not save", body: ` ${e.message}`, error: true }); }
    setBusy(false);
  };
  const markdown = () => {
    const md = [`# 8D report — ${inv ? `${inv.defect_name} on ${inv.part_number}` : report.id}`, "",
      `Status: ${report.status} · Drafted by ${report.generated_by}${report.edited_by ? ` · Edited by ${report.edited_by}` : ""}`, "",
      ...D_LABELS.flatMap(([k, l]) => [`## ${l}`, "", sections[k] || "_(empty)_", ""])].join("\n");
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a"); a.href = url; a.download = `${report.id}.md`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <Modal wide title={inv ? `8D · ${inv.defect_name} spike on ${inv.part_number}` : report.id}
      sub={<>Drafted by {report.generated_by}. The agent wrote a draft; you own the final text.</>} onClose={onClose}>
      {inv?.hypotheses?.[0] && (
        <div className="banner info"><Icon name="target" /><div><b>Top hypothesis:</b> {inv.hypotheses[0].statement}. {inv.hypotheses[0].evidence.join("; ")}</div></div>
      )}
      {D_LABELS.map(([k, label, help]) => (
        <div className="field" key={k}>
          <label htmlFor={k}>{label} <span className="hint" style={{ fontWeight: 400 }}>— {help}</span></label>
          <textarea id={k} value={sections[k] ?? ""} onChange={(e) => setSections({ ...sections, [k]: e.target.value })} />
        </div>
      ))}
      <div className="modal-actions">
        <button className="btn btn-quiet" title="Opens in Google Docs (upload to Drive) or Microsoft Word"
          onClick={() => downloadFile(`/learn/reports/${report.id}/docx`, `${report.id}.docx`).catch((e) => toast({ title: "Download failed", body: ` ${e.message}`, error: true }))}>
          <Icon name="download" /> Google Docs / Word (.docx)</button>
        <button className="btn btn-quiet" onClick={markdown}><Icon name="download" /> Markdown</button>
        <span className="grow" />
        <button className="btn" disabled={busy} onClick={() => save(false)}>Save draft</button>
        <button className="btn btn-primary" disabled={busy} onClick={() => save(true)}><Icon name="check" /> Approve 8D</button>
      </div>
    </Modal>
  );
}
