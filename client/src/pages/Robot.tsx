import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { api, imageUrl, secondLookUrl } from "../api";
import type { Mode } from "../types";
import { Empty, Icon, PageHeader, Stat } from "../ui";
import { webglAvailable } from "./robot3dSupport";

// Three.js is loaded only when an episode is opened.
const Robot3D = lazy(() => import("./Robot3D"));

interface Frame { action: string; q: number[]; holding: boolean }

export default function Robot({ mode }: { mode: Mode | null }) {
  const [eps, setEps] = useState<any[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    api<any[]>("/act/episodes").then(setEps).catch(() => setEps([]));
    api("/act/second-look/stats").then(setStats).catch(() => setStats(null));
  }, []);
  useEffect(() => {
    if (!sel) return;
    api(`/act/episodes/${sel}`).then((e) => { setFrames(e.frames); setMeta(e); });
  }, [sel]);

  return (
    <>
      <PageHeader eyebrow="Act" title="Robot cell"
        sub={<>The arm takes the expert's second look. ER 2 reads the cited rule's <i>how the expert looks</i>, calls <span className="mono">pick</span> and <span className="mono">present_to_camera</span> at that angle, judges the closer view, then <span className="mono">place_in_bin</span>. If the two looks disagree the part goes to <b>hold</b> for a person. A safety gate checks every call (allowed function, right part, valid bin, workspace limits, scrap only after a person confirms) before the simulated SO-101 arm moves.</>} />
      {stats?.n > 0 && <SecondLookStats s={stats} />}
      {mode?.robot === "off" && <div className="banner"><Icon name="alert" />Robot mode is off on this server. Recorded episodes still replay below.</div>}
      {eps.length === 0 && <div className="panel"><Empty title="No episodes yet">Inspect a part, then press “Sort with simulated arm”.</Empty></div>}
      {eps.map((e) => (
        <div className="panel" key={e.episode_id} role="button" tabIndex={0} onKeyDown={(k) => k.key === "Enter" && setSel(e.episode_id)} onClick={() => setSel(e.episode_id)} style={{ padding: 16, marginBottom: 10, cursor: "pointer", outline: sel === e.episode_id ? "2px solid var(--blue)" : undefined }}>
          <div className="row">
            <b className="grow mono">{e.episode_id}</b>
            {e.second_look?.status === "done" && <span className={`status ${e.second_look.agrees ? "pass" : "hold"}`}>{e.second_look.agrees ? "second look agrees" : "held for a person"}</span>}
            {e.blocked?.length > 0 && <span className="status scrap">{e.blocked.length} blocked</span>}
          </div>
          <div className="small muted">planner {e.planner} · simulator {e.simulator} · decision {e.decision_id}</div>
        </div>
      ))}
      {sel && frames.length > 0 && <Replay frames={frames} meta={meta} />}
      {sel && <SecondLook ep={eps.find((e) => e.episode_id === sel)} />}
    </>
  );
}

const BINS: Record<string, number> = { pass: 60, rework: 90, scrap: 120, hold: 145 };

function Replay({ frames, meta }: { frames: Frame[]; meta: any }) {
  const [i, setI] = useState(0);
  const [mode3d, setMode3d] = useState(webglAvailable());
  const blockedBins: string[] = (meta.blocked ?? []).map((b: any) => b.call?.args?.bin).filter(Boolean);
  const [playing, setPlaying] = useState(true);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { setI(0); setPlaying(true); }, [frames]);
  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => setI((x) => (x + 1 < frames.length ? x + 1 : (setPlaying(false), x))), 60);
    return () => window.clearInterval(timer.current);
  }, [playing, frames.length]);

  const f = frames[i];
  const [pan, lift, elbow, wrist] = f.q;
  // Side view: planar 3-link arm from shoulder_lift, elbow_flex, wrist_flex.
  const rad = (d: number) => (d * Math.PI) / 180;
  // lift -90 = upright; elbow measured from the upper arm; wrist relative to the forearm.
  const a1 = rad(-lift), a2 = a1 - rad(elbow), a3 = a2 + rad(wrist);
  const base = { x: 120, y: 170 };
  const p1 = { x: base.x + 70 * Math.cos(a1), y: base.y - 70 * Math.sin(a1) };
  const p2 = { x: p1.x + 60 * Math.cos(a2), y: p1.y - 60 * Math.sin(a2) };
  const p3 = { x: p2.x + 25 * Math.cos(a3), y: p2.y - 25 * Math.sin(a3) };
  // Top view: pan angle; 0° = part tray, -45° = camera, bins at 60/90/120/145°.
  const tv = (deg: number, r: number) => ({ x: 380 + r * Math.cos(rad(deg - 90)), y: 110 + r * Math.sin(rad(deg - 90)) });
  const tip = tv(pan, 80);

  return (
    <div className="panel section" style={{ padding: 16 }}>
      <div className="row" style={{ marginBottom: 10 }}>
        <b className="grow">Episode replay</b>
        <div className="lang-switch" role="group" aria-label="Replay style">
          <button aria-pressed={mode3d} onClick={() => setMode3d(true)} disabled={!webglAvailable()}>3D</button>
          <button aria-pressed={!mode3d} onClick={() => setMode3d(false)}>2D</button>
        </div>
      </div>
      {mode3d ? (
        <Suspense fallback={<div className="robot-3d" style={{ display: "grid", placeItems: "center" }}><span className="spinner" /></div>}>
          <Robot3D frames={frames} index={i} blockedBins={blockedBins} />
        </Suspense>
      ) : (
      <svg className="chart big" viewBox="0 0 520 200" role="img" aria-label={`Arm replay frame ${i + 1} of ${frames.length}: ${f.action}`}>
        <text x={10} y={16}>side view</text>
        <line x1={20} x2={240} y1={172} y2={172} stroke="var(--line)" strokeWidth={2} />
        <polyline points={`${base.x},${base.y} ${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y}`} fill="none" stroke="var(--ink)" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
        {f.holding && <circle cx={p3.x} cy={p3.y} r={8} fill="var(--accent)" />}
        <text x={290} y={16}>top view</text>
        <circle cx={380} cy={110} r={4} fill="var(--ink)" />
        {Object.entries(BINS).map(([b, deg]) => { const p = tv(deg, 80); return <g key={b}><rect x={p.x - 16} y={p.y - 12} width={32} height={24} rx={4} fill="none" stroke={`var(--${b})`} strokeWidth={2} /><text x={p.x} y={p.y + 26} textAnchor="middle">{b}</text></g>; })}
        {(() => { const c = tv(-45, 80); return <g><rect x={c.x - 10} y={c.y - 8} width={20} height={16} fill="var(--surface-2)" stroke="var(--ink-2)" /><text x={c.x} y={c.y - 12} textAnchor="middle">camera</text></g>; })()}
        {(() => { const t = tv(0, 80); return <text x={t.x} y={t.y - 14} textAnchor="middle">tray</text>; })()}
        <line x1={380} y1={110} x2={tip.x} y2={tip.y} stroke="var(--ink)" strokeWidth={5} strokeLinecap="round" />
        {f.holding && <circle cx={tip.x} cy={tip.y} r={7} fill="var(--accent)" />}
      </svg>
      )}
      <div className="row small">
        <button className="btn btn-sm" onClick={() => { if (i >= frames.length - 1) setI(0); setPlaying(!playing); }}>{playing ? "Pause" : "Play"}</button>
        <input type="range" min={0} max={frames.length - 1} value={i} onChange={(e) => { setPlaying(false); setI(Number(e.target.value)); }} className="grow" aria-label="Frame" />
        <span className="mono">{f.action}</span>
      </div>
      <table className="plain small" style={{ marginTop: 8 }}>
        <tbody>{meta.log.map((s: any, k: number) => (
          <tr key={k}><td className="mono">{s.call.name}({Object.entries(s.call.args).map(([a, v]) => `${a}=${v}`).join(", ")})</td>
            <td className={s.status === "blocked" ? "error" : ""}>{s.status}{s.reason ? `: ${s.reason}` : ""}</td></tr>
        ))}</tbody>
      </table>
      <p className="muted small">Simulator: {meta.simulator} (scripted kinematic controller; joint-space interpolation between named poses).</p>
    </div>
  );
}

const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function SecondLookStats({ s }: { s: any }) {
  return (
    <div className="stat-grid">
      <Stat label="Second looks" value={s.n} icon="robot" foot={`${pct(s.agreement_rate)} agree with the first look`} />
      <Stat label="Needs a person · before → after" value={<span style={{ fontSize: 22 }}>{pct(s.needs_human_before)} → {pct(s.needs_human_after)}</span>} icon="user" foot="Share of parts flagged for human confirm" />
      <Stat label="Defects without a rule · before → after" value={<span style={{ fontSize: 22 }}>{s.uncited_before} → {s.uncited_after}</span>} icon="book" foot="Uncited defects never pass on their own" />
      <Stat label="Model confidence · before → after" value={<span style={{ fontSize: 22 }}>{s.confidence_pairs ? `${s.confidence_before} → ${s.confidence_after}` : "—"}</span>} icon="gauge"
        foot={s.confidence_pairs ? `ER 2 self-reported, ${s.confidence_pairs} pairs; not calibrated` : "Needs Gemini on both looks"} />
    </div>
  );
}

function SecondLook({ ep }: { ep: any }) {
  const sl = ep?.second_look;
  if (!sl) return null;
  if (sl.status !== "done") return <div className="panel section" style={{ padding: 16 }}><p className="muted small">Second look skipped: {sl.reason}</p></div>;
  const rows: [string, string][] = [["decision", "Decision"], ["confidence", "Model confidence"], ["cited", "Defects citing a rule"], ["uncited", "Defects without a rule"], ["needs_human_confirm", "Needs a person"]];
  const show = (v: any) => (v == null ? "—" : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));
  return (
    <div className="panel section" style={{ padding: 16 }}>
      <div className="row"><h2 className="panel-title grow">Second look at {sl.angle_deg}°</h2>
        <span className={`status ${sl.agrees ? "pass" : "hold"}`}>{sl.agrees ? "agrees" : "disagrees: held for a person"}</span></div>
      <div className="grid-even" style={{ marginTop: 12 }}>
        <figure style={{ margin: 0 }}><img src={imageUrl(ep.decision_id)} alt="First look: the line camera photo" style={{ width: "100%", borderRadius: 8 }} /><figcaption className="small muted">First look (line camera)</figcaption></figure>
        <figure style={{ margin: 0 }}><img src={secondLookUrl(ep.episode_id)} alt="Second look: closer view of the pointed region" style={{ width: "100%", borderRadius: 8 }} /><figcaption className="small muted">{sl.view}</figcaption></figure>
      </div>
      <table className="plain small" style={{ marginTop: 10 }}>
        <thead><tr><th></th><th>Before</th><th>After</th></tr></thead>
        <tbody>{rows.map(([k, label]) => (
          <tr key={k}><td>{label}</td><td className="mono">{show(sl.before[k])}</td><td className="mono">{show(sl.after[k])}</td></tr>
        ))}</tbody>
      </table>
      <p className="small"><b>Why:</b> {sl.rationale}</p>
      <p className="muted small">Rules with an expert view: {sl.cards_used.length ? sl.cards_used.join(", ") : "none"} · {sl.model} · {sl.latency_ms} ms · ${sl.cost_usd.toFixed(4)}</p>
    </div>
  );
}
