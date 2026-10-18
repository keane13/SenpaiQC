import { useEffect, useState } from "react";
import { api } from "../api";
import { Bars, PChart, type PPoint } from "../charts";
import { fmtPct } from "../components";
import type { Investigation } from "../types";
import { Empty, Icon, PageHeader, Stat, useToast } from "../ui";

const DEFECTS = ["porosity", "shrinkage", "burr", "crack"];

export default function Insights() {
  const [dash, setDash] = useState<any>(null);
  const [evalS, setEval] = useState<any>(null);
  const [defect, setDefect] = useState("porosity");
  const [spc, setSpc] = useState<PPoint[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const toast = useToast();

  const load = () => {
    api("/learn/dashboard").then(setDash).catch((e) => setErr(e.message));
    api("/learn/eval").then(setEval).catch(() => setEval({ available: false }));
  };
  useEffect(load, []);
  useEffect(() => { api<PPoint[]>(`/learn/spc?part_number=IMP-200&defect=${defect}`).then(setSpc).catch(() => setSpc([])); }, [defect]);

  const scan = async () => {
    setBusy("scan");
    try {
      const opened = await api<unknown[]>("/learn/scan", { method: "POST", body: "{}" });
      toast({ title: opened.length ? `${opened.length} spike(s) flagged` : "No new spikes", body: opened.length ? " An investigation was opened for each." : " All defects are inside their control limits." });
      load();
    } catch (e: any) { setErr(e.message); }
    setBusy("");
  };
  const analyse = async (id: string) => {
    setBusy(id);
    try { await api(`/learn/investigations/${id}/analyse`, { method: "POST" }); toast({ title: "Root cause drafted", body: " Check the evidence, then edit the 8D in Reports." }); load(); }
    catch (e: any) { toast({ title: "Analysis failed", body: ` ${e.message}`, error: true }); }
    setBusy("");
  };

  if (!dash) return <p>{err ? <span className="error">{err}</span> : <><span className="spinner" /> Loading…</>}</p>;
  const m = dash.measured, s = dash.synthetic;
  const flagged = spc.filter((p) => p.out_of_control).length;

  return (
    <>
      <PageHeader eyebrow="Quality intelligence" title="Quality analytics"
        sub="Spot defect spikes early, find out why, and act. A spike is flagged by a fixed statistical rule (p-chart, 3σ); the AI only explains it."
        actions={<button className="btn btn-primary" onClick={scan} disabled={!!busy}>{busy === "scan" ? <span className="spinner" /> : <Icon name="activity" />} Check for spikes</button>} />
      {err && <div className="banner"><Icon name="alert" />{err}</div>}

      <div className="stat-grid">
        <Stat label="Live parts inspected" value={m.parts.toLocaleString()} icon="box" foot="Measured by this deployment" />
        <Stat label="Escalated to Gemini" value={fmtPct(m.escalation_rate)} icon="layers" foot="Lower = cheaper; falls as YOLO learns" glow="rgba(82,208,230,.1)" />
        <Stat label="Cost per 1,000 parts" value={m.cost_per_1000_usd != null ? `$${m.cost_per_1000_usd.toFixed(2)}` : "—"} icon="database" foot="From logged token cost" />
        <Stat label="p95 time · fast / Gemini" value={<span style={{ fontSize: 22 }}>{m.p95_latency_yolo_ms ?? "—"} / {m.p95_latency_er2_ms ?? "—"} ms</span>} icon="clock" foot="Measured on live parts" />
      </div>

      <section className="panel">
        <div className="panel-head">
          <div><h2 className="panel-title">Defect rate per shift <span className="chip synthetic">synthetic history</span></h2>
            <div className="panel-desc">Part IMP-200. {flagged ? `${flagged} shift(s) above the control limit.` : "All shifts inside the limit."} Red dots are out of control.</div></div>
          <select className="select" style={{ width: "auto" }} aria-label="Defect" value={defect} onChange={(e) => setDefect(e.target.value)}>
            {DEFECTS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div className="panel-body"><PChart points={spc} /></div>
      </section>

      <div className="grid-even section">
        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">Defect Pareto</h2><div className="panel-desc">{s.parts.toLocaleString()} synthetic + {m.parts} live parts</div></div></div>
          <div className="panel-body"><Bars rows={dash.pareto.map((r: any) => ({ label: r.defect_name, value: r.n }))} format={(v) => v.toLocaleString()} /></div>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">Evaluation on held-out parts</h2><div className="panel-desc">From <span className="mono">eval/run_all.py</span> only. Nothing here is projected.</div></div></div>
          <div className="panel-body">
            {evalS?.available ? (
              <>
                <table className="plain"><tbody>
                  {[["Defect recall", fmtPct(evalS.recall)], ["False reject rate", fmtPct(evalS.false_reject_rate)],
                    ["Escalation before → after retrain", `${fmtPct(evalS.escalation_rate_before, 0)} → ${fmtPct(evalS.escalation_rate_after, 0)}`],
                    ["Expert-rule citation accuracy", fmtPct(evalS.card_citation_accuracy, 0)],
                    ["Root cause found (planted scenario)", evalS.root_cause_hit == null ? "—" : evalS.root_cause_hit ? "Yes" : "No"],
                    ["Spike → 8D draft", evalS.time_to_8d_minutes != null ? `${evalS.time_to_8d_minutes} min` : "—"]].map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{v}</td></tr>))}
                </tbody></table>
                {evalS.notes?.length > 0 && <ul className="hint" style={{ paddingLeft: 18 }}>{evalS.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>}
              </>
            ) : <Empty title="Not measured yet">Run <span className="mono">python eval/run_all.py</span>. Nothing is shown until it produces numbers.</Empty>}
          </div>
        </section>
      </div>

      <section className="panel section">
        <div className="panel-head"><div><h2 className="panel-title">Investigations</h2><div className="panel-desc">Each flagged spike. The root-cause agent tests machines, moulds, lots and their combinations with read-only queries.</div></div></div>
        <div className="panel-body">
          {dash.investigations.length === 0 && <Empty title="No spikes flagged">Press “Check for spikes” after new decisions arrive.</Empty>}
          {dash.investigations.map((inv: Investigation) => <InvestigationRow key={inv.id} inv={inv} busy={busy === inv.id} onAnalyse={() => analyse(inv.id)} />)}
        </div>
      </section>
    </>
  );
}

function InvestigationRow({ inv, busy, onAnalyse }: { inv: Investigation; busy: boolean; onAnalyse: () => void }) {
  return (
    <div className="next-action" style={{ alignItems: "flex-start", flexDirection: "column" }}>
      <div className="row" style={{ width: "100%" }}>
        <div className={`list-icon ${inv.status === "open" ? "red" : ""}`}><Icon name="alert" /></div>
        <div className="grow">
          <div className="list-title">{inv.defect_name} spike on {inv.part_number}</div>
          <div className="list-desc">Flagged {inv.shift_key}: {fmtPct(inv.rate)} vs limit {fmtPct(inv.ucl)} (normal {fmtPct(inv.center)}) · <span className="mono">{inv.id}</span></div>
        </div>
        {inv.status === "open"
          ? <button className="btn btn-primary btn-sm" onClick={onAnalyse} disabled={busy}>{busy ? <><span className="spinner" /> Investigating…</> : <><Icon name="target" size={15} /> Find root cause</>}</button>
          : <a className="btn btn-sm" href="#reports">Open 8D <Icon name="arrow" size={14} /></a>}
      </div>
      {inv.hypotheses?.length > 0 && (
        <div style={{ width: "100%", marginTop: 6 }}>
          {inv.hypotheses.map((h) => (
            <div key={h.rank} style={{ borderLeft: "3px solid var(--blue)", paddingLeft: 12, margin: "10px 0" }}>
              <div className="row"><b>#{h.rank} {h.statement}</b><span className={`status ${h.confidence === "high" ? "info" : "neutral"}`}>{h.confidence} confidence</span></div>
              <div className="row" style={{ margin: "6px 0" }}>{Object.entries(h.blamed).map(([k, v]) => <span key={k} className="chip blue mono">{k} = {v}</span>)}</div>
              <ul className="small" style={{ margin: 0, color: "var(--text-2)" }}>{h.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </div>
          ))}
          <p className="hint">By {inv.agent_model} · {inv.analysis_seconds}s · flag to draft {inv.time_to_8d_minutes} min</p>
          <details className="small"><summary>Show the agent's {inv.agent_trace.length} tool calls</summary>
            <table className="plain"><tbody>{inv.agent_trace.map((t, i) => (
              <tr key={i}><td className="mono">{t.tool}</td><td className="mono" style={{ wordBreak: "break-all" }}>{JSON.stringify(t.args)}<div className="muted">{t.result_preview.slice(0, 220)}</div></td></tr>
            ))}</tbody></table>
          </details>
        </div>
      )}
    </div>
  );
}
