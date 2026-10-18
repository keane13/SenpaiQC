import { useEffect, useState } from "react";
import { api, imageUrl } from "./api";
import { LANGUAGES, loadPrefs, savePrefs } from "./prefs";
import type { DecisionValue, InspectionResult } from "./types";
import { Icon, useToast } from "./ui";

/** Image with ER 2 points and boxes drawn on top. Coordinates are pixels from the API. */
export function DefectOverlay({ result, src }: { result: InspectionResult; src?: string }) {
  const [w, h] = result.image_size?.length === 2 ? result.image_size : [1, 1];
  const r = Math.max(w, h) / 60;
  return (
    <div className="overlay-wrap">
      <img src={src ?? imageUrl(result.id)} alt={`Part ${result.part_number} with ${result.defects.length} marked defect(s)`} />
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        {result.defects.map((d, i) => (
          <g key={i}>
            {d.box?.length === 4 && (
              <rect x={d.box[0]} y={d.box[1]} width={d.box[2] - d.box[0]} height={d.box[3] - d.box[1]}
                fill="none" stroke="#ff6f83" strokeWidth={r / 3} strokeDasharray={d.card_id ? undefined : `${r} ${r / 2}`} />
            )}
            {d.point?.length === 2 && (
              <>
                <circle cx={d.point[0]} cy={d.point[1]} r={r} fill="none" stroke="#fff" strokeWidth={r / 2.2} />
                <circle cx={d.point[0]} cy={d.point[1]} r={r} fill="none" stroke="#ff6f83" strokeWidth={r / 4} />
                <text x={d.point[0] + r * 1.4} y={d.point[1] - r} fill="#fff" stroke="#000" strokeWidth={r / 10}
                  fontSize={r * 1.6} fontWeight={700} paintOrder="stroke">{i + 1}</text>
              </>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

const DECISION_HELP: Record<string, string> = {
  pass: "Part is good. Send it to the next station.",
  rework: "Part can be fixed. Follow the rework steps below.",
  scrap: "Part cannot be fixed. Put it in the scrap bin.",
};

export function DecisionBanner({ result }: { result: InspectionResult }) {
  const icon = result.decision === "pass" ? "check" : result.decision === "scrap" ? "x" : "wrench";
  const state = result.confirmed ? `Confirmed by ${result.confirmed_by}` : result.needs_human_confirm ? "Waiting for your confirmation" : "Automatic decision";
  return (
    <div className={`decision ${result.decision}`} role="status">
      <Icon name={icon} size={30} />
      <div>{result.decision}<small>{DECISION_HELP[result.decision]} · {state}</small></div>
    </div>
  );
}

/** Which model actually judged an escalated part. Never claims ER 2 when a fallback answered. */
export function reasonerLabel(model?: string | null): string {
  if (!model) return "Offline fallback";
  if (model.includes("robotics")) return "Gemini Robotics ER 2";
  if (model.startsWith("vertex:")) return `Gemini on Vertex AI (${model.slice(7)})`;
  if (model.includes("gemini")) return `Gemini (${model})`;
  return "Offline fallback";
}

export function PathInfo({ result }: { result: InspectionResult }) {
  const who = reasonerLabel(result.reasoning_model);
  return (
    <div className="row small" style={{ margin: "10px 0" }}>
      <span className={`status ${result.path === "yolo" ? "info" : "review"}`}>
        {result.path === "yolo" ? "Fast check (YOLO)" : who === "Offline fallback" ? "Escalated (AI offline)" : `Checked by ${who}`}
      </span>
      {result.yolo.class !== null && <span className="chip">YOLO {result.yolo.class} · {Math.round(result.yolo.confidence * 100)}%</span>}
      <span className="chip"><Icon name="clock" size={13} /> {(result.latency_ms / 1000).toFixed(1)} s</span>
      <span className="chip">${result.cost_usd.toFixed(4)}</span>
      {result.escalation_reason && <span className="muted small" style={{ width: "100%" }}>Why a closer look: {result.escalation_reason}</span>}
    </div>
  );
}

export function DefectList({ result }: { result: InspectionResult }) {
  if (!result.defects.length) return <p className="muted small">No defect marked on this part.</p>;
  return (
    <table className="plain">
      <tbody>
        {result.defects.map((d, i) => (
          <tr key={i}>
            <td className="mono" style={{ width: 24 }}>{i + 1}</td>
            <td><b>{d.label || "defect"}</b><div className="muted small">{d.severity}</div></td>
            <td style={{ textAlign: "right" }}>{d.card_id ? <span className="chip blue">Expert rule {d.card_id}</span> : <span className="status review">No matching expert rule</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LanguageSwitch({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="lang-switch" role="group" aria-label="Language">
      {LANGUAGES.map(([k, v]) => (
        <button key={k} aria-pressed={value === k} onClick={() => onChange(k)} title={v}>{k.toUpperCase()}</button>
      ))}
    </div>
  );
}

/** Rework steps in the operator's language, with tick boxes so nothing is skipped. */
export function ReworkGuide({ decisionId }: { decisionId: string }) {
  const [lang, setLang] = useState<string>(loadPrefs().language);
  const [guide, setGuide] = useState<any>(null);
  const [done, setDone] = useState<Set<number>>(new Set());
  const [err, setErr] = useState("");
  useEffect(() => {
    setGuide(null);
    setErr("");
    setDone(new Set());
    api(`/act/guide/${decisionId}?lang=${lang}`).then(setGuide).catch((e) => setErr(e.message));
  }, [decisionId, lang]);
  const change = (l: string) => { setLang(l); const p = loadPrefs(); savePrefs({ ...p, language: l as any }); };
  const total = guide?.steps?.length ?? 0;
  return (
    <section className="panel">
      <div className="panel-head">
        <div><h2 className="panel-title">What to do now</h2><div className="panel-desc">Steps come from the expert's rule for this defect.</div></div>
        <LanguageSwitch value={lang} onChange={change} />
      </div>
      <div className="panel-body">
        {err && <p className="error">{err}</p>}
        {!guide && !err && <p><span className="spinner" /> Preparing steps…</p>}
        {guide?.decision === "pass" && <p>Nothing to fix. Send the part on.</p>}
        {total > 0 && (
          <>
            <ol className="steps" style={{ listStyle: "none", paddingLeft: 0 }}>
              {guide.steps.map((s: string, i: number) => (
                <li key={i}>
                  <label style={{ display: "flex", gap: 12, alignItems: "flex-start", cursor: "pointer" }}>
                    <input type="checkbox" checked={done.has(i)} style={{ width: 22, height: 22, marginTop: 2, accentColor: "var(--blue)" }}
                      onChange={() => setDone((d) => { const n = new Set(d); n.has(i) ? n.delete(i) : n.add(i); return n; })} />
                    <span style={{ textDecoration: done.has(i) ? "line-through" : undefined, opacity: done.has(i) ? .6 : 1 }}>
                      <b>{i + 1}.</b> {s}
                    </span>
                  </label>
                </li>
              ))}
            </ol>
            <p className="small muted">{done.size} of {total} steps done{done.size === total ? " — ready for re-inspection." : ""}</p>
          </>
        )}
        {guide?.card_id && <p className="muted small">Source: expert rule <span className="mono">{guide.card_id}</span>{guide.card_source ? ` · ${guide.card_source}` : ""}</p>}
      </div>
    </section>
  );
}

/** Human confirmation. Scrap asks twice because it cannot be undone on the floor. */
export function ConfirmBar({ result, onDone }: { result: InspectionResult; onDone: (r: InspectionResult) => void }) {
  const [busy, setBusy] = useState(false);
  const [armedScrap, setArmedScrap] = useState(false);
  const toast = useToast();
  if (result.confirmed) return <p className="muted small"><Icon name="check" size={14} /> Confirmed by {result.confirmed_by}.</p>;
  const send = async (decision: DecisionValue) => {
    if (decision === "scrap" && !armedScrap) { setArmedScrap(true); return; }
    setBusy(true);
    try {
      const body: Record<string, string> = {};
      if (decision !== result.decision) body.decision = decision;
      const r = await api<InspectionResult>(`/decisions/${result.id}/confirm`, { method: "POST", body: JSON.stringify(body) });
      toast({ title: `Recorded: ${decision}`, body: decision !== result.decision ? " You overrode the AI. Your call is what gets logged." : " Logged to the quality record." });
      onDone(r);
    } catch (e: any) {
      toast({ title: "Could not save", body: ` ${e.message}`, error: true });
    } finally {
      setBusy(false);
      setArmedScrap(false);
    }
  };
  const choices: DecisionValue[] = ["pass", "rework", "scrap"];
  return (
    <section className="panel">
      <div className="panel-head"><div><h2 className="panel-title">Your decision</h2><div className="panel-desc">The AI suggests <b>{result.decision}</b>. You have the final say.</div></div></div>
      <div className="panel-body">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
          {choices.map((d) => (
            <button key={d} className={`btn btn-lg ${d === result.decision ? `btn-${d}` : "btn-quiet"}`} disabled={busy} onClick={() => send(d)}>
              {d === "scrap" && armedScrap ? "Tap again to scrap" : d === result.decision ? `Confirm ${d}` : d}
            </button>
          ))}
        </div>
        {armedScrap && <p className="small error" style={{ marginTop: 8 }}>Scrap is final for this part. Tap “Tap again to scrap” to confirm, or choose another option.</p>}
      </div>
    </section>
  );
}

export function fmtPct(x: number | null | undefined, digits = 1) {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}

/** Who actually decided: never claim ER 2 when the offline fallback answered. */
export function checkedBy(d: InspectionResult): string {
  if (d.path === "yolo") return "Fast check (YOLO)";
  return reasonerLabel(d.reasoning_model).replace(/ \(.*\)$/, "");
}
