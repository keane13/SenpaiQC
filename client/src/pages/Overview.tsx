import { useEffect, useState } from "react";
import { api } from "../api";
import type { Page } from "../App";
import { fmtPct, checkedBy } from "../components";
import { loadPrefs } from "../prefs";
import type { Card, InspectionResult, Investigation, Mode } from "../types";
import { DecisionBadge, Empty, Icon, type IconName, PageHeader, Stat, timeAgo } from "../ui";

type Action = { key: string; icon: IconName; tone: string; title: string; desc: string; cta: string; page: Page; roles: string[] };

export default function Overview({ mode, go }: { mode: Mode | null; go: (p: Page) => void }) {
  const [dash, setDash] = useState<any>(null);
  const [recent, setRecent] = useState<InspectionResult[]>([]);
  const [pending, setPending] = useState<InspectionResult[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [err, setErr] = useState("");
  const role = loadPrefs().role;

  useEffect(() => {
    Promise.all([
      api("/learn/dashboard").then(setDash),
      api<InspectionResult[]>("/decisions?limit=8").then(setRecent),
      api<InspectionResult[]>("/decisions?pending=true").then(setPending),
      api<Card[]>("/teach/cards").then(setCards),
    ]).catch((e) => setErr(e.message));
  }, []);

  const invs: Investigation[] = dash?.investigations ?? [];
  const openInv = invs.filter((i) => i.status === "open");
  const drafts = cards.filter((c) => c.status === "draft");
  const reportsToReview = invs.filter((i) => i.status === "analysed");

  const actions: Action[] = [
    { key: "confirm", icon: "inbox", tone: "amber", title: `${pending.length} part${pending.length === 1 ? "" : "s"} waiting for your decision`,
      desc: "Scrap calls, unknown defects and offline results need a person.", cta: "Review now", page: "queue", roles: ["operator", "inspector", "qc"] },
    { key: "cards", icon: "book", tone: "", title: `${drafts.length} expert rule${drafts.length === 1 ? "" : "s"} to approve`,
      desc: "Draft cards from expert videos are not used on the line until approved.", cta: "Open knowledge", page: "knowledge", roles: ["inspector", "qc"] },
    { key: "inv", icon: "alert", tone: "red", title: `${openInv.length} defect spike${openInv.length === 1 ? "" : "s"} without a root cause`,
      desc: openInv[0] ? `${openInv[0].defect_name} on ${openInv[0].part_number} at ${fmtPct(openInv[0].rate)} (limit ${fmtPct(openInv[0].ucl)}).` : "",
      cta: "Find root cause", page: "analytics", roles: ["qc", "inspector"] },
    { key: "8d", icon: "file", tone: "", title: `${reportsToReview.length} 8D draft${reportsToReview.length === 1 ? "" : "s"} to check`,
      desc: "The agent drafted these; edit and approve before they go to the customer.", cta: "Open reports", page: "reports", roles: ["qc"] },
  ];
  const counts: Record<string, number> = { confirm: pending.length, cards: drafts.length, inv: openInv.length, "8d": reportsToReview.length };
  const mine = actions.filter((a) => counts[a.key] > 0 && (a.roles.includes(role) || a.key === "confirm"));

  const activity = [
    ...recent.map((d) => ({ t: (d as any).confirmed_at ?? (d as any).created_at, icon: d.decision === "pass" ? "check" : d.decision === "scrap" ? "x" : "wrench",
      tone: d.decision === "pass" ? "green" : d.decision === "scrap" ? "red" : "amber",
      title: `${d.decision[0].toUpperCase()}${d.decision.slice(1)} · ${d.part_number}`, desc: d.confirmed ? `Confirmed by ${d.confirmed_by}` : d.needs_human_confirm ? "Waiting for confirmation" : "Automatic" })),
    ...invs.map((i) => ({ t: (i as any).analysed_at ?? (i as any).created_at, icon: "alert", tone: i.status === "open" ? "red" : "",
      title: i.status === "open" ? `Spike flagged: ${i.defect_name}` : `Root cause drafted: ${i.defect_name}`, desc: `${i.part_number} · ${i.shift_key}` })),
  ].filter((a) => a.t).sort((a, b) => (a.t < b.t ? 1 : -1)).slice(0, 6);

  const m = dash?.measured;
  const hour = new Date().getHours();
  const greet = hour < 11 ? "Good morning" : hour < 15 ? "Good afternoon" : "Good evening";

  return (
    <>
      <PageHeader eyebrow="Workspace overview" title={greet}
        sub="Here is what needs attention on the line. Numbers on this page come from logged decisions, not estimates." />
      {err && <div className="banner"><Icon name="alert" />{err}</div>}

      <div className="stat-grid">
        <Stat label="Parts inspected (live)" value={m ? m.parts.toLocaleString() : "—"} foot="Logged by this deployment" icon="box" />
        <Stat label="Waiting for a person" value={pending.length} foot="Scrap, unknown or offline results" icon="clock" glow="rgba(246,189,96,.12)" />
        <Stat label="Sent to Gemini ER 2" value={fmtPct(m?.escalation_rate)} foot="Share of live parts escalated" icon="layers" glow="rgba(82,208,230,.1)" />
        <Stat label="Open defect spikes" value={openInv.length} foot={`${invs.length} investigations in total`} icon="activity" glow="rgba(255,111,131,.1)" />
      </div>

      <div className="grid-2">
        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">What needs you now</h2><div className="panel-desc">Sorted for your role. Finish these and the line keeps moving.</div></div></div>
          <div className="panel-body">
            {!dash && !err && <p><span className="spinner" /> Loading…</p>}
            {dash && mine.length === 0 && <Empty title="You're all caught up">Inspect the next part, or check quality analytics.</Empty>}
            {mine.map((a) => (
              <div className="next-action" key={a.key}>
                <div className={`list-icon ${a.tone}`}><Icon name={a.icon} /></div>
                <div className="grow"><div className="list-title">{a.title}</div><div className="list-desc">{a.desc}</div></div>
                <button className="btn btn-sm" onClick={() => go(a.page)}>{a.cta} <Icon name="arrow" size={14} /></button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">Activity</h2><div className="panel-desc">Latest decisions and investigations</div></div></div>
          <div className="panel-body">
            {activity.length === 0 && <p className="muted small">No activity yet. Inspect a part to start.</p>}
            <div className="list">
              {activity.map((a, i) => (
                <div className="list-item" key={i}>
                  <div className={`list-icon ${a.tone}`}><Icon name={a.icon as IconName} size={16} /></div>
                  <div><div className="list-title">{a.title}</div><div className="list-desc">{a.desc}</div></div>
                  <div className="list-time">{timeAgo(a.t)}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="panel section">
        <div className="panel-head">
          <div><h2 className="panel-title">Recent inspections</h2><div className="panel-desc">Tap a row to see the evidence</div></div>
          <button className="text-link" onClick={() => go("queue")}>Open the queue <Icon name="arrow" size={13} /></button>
        </div>
        {recent.length === 0 ? <Empty title="No inspections yet">Use “Inspect a part” to check your first part.</Empty> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Part</th><th>Checked by</th><th>Decision</th><th>Status</th><th>When</th></tr></thead>
              <tbody>
                {recent.map((d) => (
                  <tr key={d.id} className="clickable" onClick={() => { location.hash = `queue?open=${d.id}`; }}>
                    <td><div className="cell-main">{d.part_number}</div><div className="cell-sub mono">{d.id}</div></td>
                    <td>{checkedBy(d)}</td>
                    <td><DecisionBadge decision={d.decision} /></td>
                    <td>{d.confirmed ? <span className="status pass">Confirmed</span> : d.needs_human_confirm ? <span className="status review">Needs you</span> : <span className="status neutral">Auto</span>}</td>
                    <td className="small">{timeAgo((d as any).created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {mode && !mode.gemini && (
        <div className="banner section"><Icon name="alert" /><div>Offline mode: no Gemini key on the server. Escalated parts get a heuristic candidate mark only and always wait for a person.</div></div>
      )}
    </>
  );
}
