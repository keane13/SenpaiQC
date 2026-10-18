import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ConfirmBar, DecisionBanner, DefectList, DefectOverlay, PathInfo, ReworkGuide } from "../components";
import { loadPrefs, savePrefs, type Prefs } from "../prefs";
import type { InspectionResult, Mode } from "../types";
import { Icon, Modal, PageHeader, useToast } from "../ui";

const CTX_FIELDS: [keyof Prefs["ctx"], string][] = [
  ["part_number", "Part number"], ["line_id", "Line"], ["shift", "Shift"],
  ["machine_id", "Machine"], ["mould_id", "Mould"], ["material_lot", "Material lot"],
];
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export default function Inspect({ mode, onChange }: { mode: Mode | null; onChange: () => void }) {
  const [prefs, setPrefs] = useState(loadPrefs);
  const [editCtx, setEditCtx] = useState(false);
  const [preview, setPreview] = useState<string>();
  const [result, setResult] = useState<InspectionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  const [robot, setRobot] = useState<any>(null);
  const [samples, setSamples] = useState<{ name: string; label?: string; source?: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const last = useRef<{ blob: Blob; name: string; url: string } | null>(null);
  const toast = useToast();

  useEffect(() => { api("/samples").then(setSamples).catch(() => setSamples([])); }, []);

  const run = async (blob: Blob, name: string, previewUrl: string, forcePath?: "er2") => {
    setErr(""); setResult(null); setRobot(null); setPreview(previewUrl); setBusy(true);
    last.current = { blob, name, url: previewUrl };
    const fd = new FormData();
    fd.append("image", blob, name);
    Object.entries(prefs.ctx).forEach(([k, v]) => fd.append(k, v));
    if (forcePath) fd.append("force_path", forcePath);
    try {
      const r = await api<InspectionResult>("/inspect", { method: "POST", body: fd });
      setResult(r);
      onChange();
      if (!r.needs_human_confirm) toast({ title: `Logged: ${r.decision}`, body: " Recorded automatically." });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const onFile = async (f?: File) => { if (f) run(await downscale(f), f.name, URL.createObjectURL(f)); };
  const onSample = async (name: string) => {
    const url = `${BASE}/api/samples/${encodeURIComponent(name)}`;
    const blob = await (await fetch(url)).blob();
    run(blob, name, url);
  };
  const runRobot = async () => {
    if (!result) return;
    setRobot({ running: true });
    try { setRobot(await api(`/act/robot/${result.id}`, { method: "POST" })); } catch (e: any) { setRobot({ error: e.message }); }
  };
  const ctxSummary = `${prefs.ctx.part_number} · ${prefs.ctx.line_id} · shift ${prefs.ctx.shift} · ${prefs.ctx.machine_id} · ${prefs.ctx.mould_id} · ${prefs.ctx.material_lot}`;

  return (
    <>
      <PageHeader eyebrow="Quality check" title="Inspect a part"
        sub="Take a clear photo from the top, part filling the frame. Easy parts are decided in a second; unclear ones get a closer look by Gemini with the expert's rules." />

      <div className="inspect-grid">
        <section className="panel">
          <div className="panel-body" style={{ paddingTop: 20 }}>
            <label className={`dropzone ${drag ? "drag" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files?.[0]); }}>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} aria-label="Take or choose a part photo" />
              {busy ? <><span className="spinner" /><b>Checking the part…</b><span>Usually 1–5 seconds</span></>
                : <><Icon name="scan" size={30} /><b>Take a photo or drop an image</b><span>On a phone this opens the camera</span></>}
            </label>
            {err && <p className="error" role="alert">{err}</p>}

            <div className="row" style={{ marginTop: 14 }}>
              <span className="small muted grow">For: <b style={{ color: "var(--text)" }}>{ctxSummary}</b></span>
              <button className="btn btn-sm btn-quiet" onClick={() => setEditCtx(true)}>Change</button>
            </div>

            {samples.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="small" style={{ fontWeight: 650, marginBottom: 8 }}>No part at hand? Try a sample photo</div>
                <div className="samples">
                  {samples.map((s) => (
                    <button key={s.name} className="sample" disabled={busy} onClick={() => onSample(s.name)} title={s.label ? `Dataset label: ${s.label}` : s.name}>
                      <img src={`${BASE}/api/samples/${encodeURIComponent(s.name)}`} alt={`Sample part ${s.name}`} loading="lazy" />
                    </button>
                  ))}
                </div>
                <p className="hint" style={{ marginTop: 6 }}>Source: {[...new Set(samples.map((s) => s.source).filter(Boolean))].join("; ") || "sample images"}</p>
              </div>
            )}
          </div>
        </section>

        <div>
          {!result && !busy && (
            <section className="panel">
              <div className="panel-body" style={{ paddingTop: 20 }}>
                <h2 className="panel-title">How it decides</h2>
                <ol className="small" style={{ paddingLeft: 18, color: "var(--text-2)" }}>
                  <li>A fast model checks every photo.</li>
                  <li>If it is unsure, or the part is new, Gemini Robotics ER 2 looks closer, points at each defect and names the expert rule it used.</li>
                  <li>Scrap and anything unknown always waits for you.</li>
                  <li>You get the fix steps in your language.</li>
                </ol>
              </div>
            </section>
          )}
          {result && (
            <>
              <DecisionBanner result={result} />
              <PathInfo result={result} />
              {result.path === "yolo" && last.current && (
                <div className="row small section">
                  <span className="muted grow">Decided by the fast model alone. Want the expert rules applied?</span>
                  <button className="btn btn-sm" disabled={busy} onClick={() => { const l = last.current!; run(l.blob, l.name, l.url, "er2"); }}>
                    <Icon name="eye" /> Ask Gemini for a second opinion</button>
                </div>
              )}
              <DefectOverlay result={result} src={preview} />
              <section className="panel section">
                <div className="panel-head"><div><h2 className="panel-title">Why</h2><div className="panel-desc">{result.rationale}</div></div></div>
                <div className="panel-body"><DefectList result={result} /></div>
              </section>
            </>
          )}
        </div>
      </div>

      {result && (
        <div className="grid-even section">
          {result.needs_human_confirm && <ConfirmBar result={result} onDone={(r) => { setResult({ ...result, ...r }); onChange(); }} />}
          <ReworkGuide decisionId={result.id} />
          {mode?.robot && mode.robot !== "off" && (
            <section className="panel">
              <div className="panel-head"><div><h2 className="panel-title">Robot cell</h2><div className="panel-desc">The simulated arm takes a second look the way the expert's rule says, then sorts the part. Every move is checked by a safety gate first.</div></div></div>
              <div className="panel-body">
                <button className="btn btn-block" onClick={runRobot} disabled={robot?.running}><Icon name="robot" /> Sort with simulated arm</button>
                {robot?.error && <p className="error">{robot.error}</p>}
                {robot?.log && (
                  <table className="plain" style={{ marginTop: 10 }}><tbody>
                    {robot.log.map((s: any, i: number) => (
                      <tr key={i}><td className="mono">{s.call.name}</td><td className={s.status === "blocked" ? "error" : ""}>{s.status}{s.reason ? `: ${s.reason}` : ""}</td></tr>
                    ))}
                  </tbody></table>
                )}
                {robot?.second_look?.status === "done" && (
                  <p className={robot.second_look.agrees ? "small" : "small error"} style={{ marginTop: 8 }}>
                    <b>Second look</b> at {robot.second_look.angle_deg}°: {robot.second_look.before.decision} → {robot.second_look.after.decision}
                    {robot.second_look.agrees ? " (agrees)" : " (disagrees: part held for a person)"}
                  </p>
                )}
                {robot?.second_look?.status === "skipped" && <p className="small muted" style={{ marginTop: 8 }}>Second look skipped: {robot.second_look.reason}</p>}
                {robot?.episode_id && <a href="#robot" className="text-link">Replay the episode <Icon name="arrow" size={13} /></a>}
              </div>
            </section>
          )}
        </div>
      )}

      {editCtx && (
        <Modal title="Where is this part from?" sub="Saved on this device. It goes into the quality record so spikes can be traced to a machine, mould or lot." onClose={() => setEditCtx(false)}>
          <form onSubmit={(e) => { e.preventDefault(); savePrefs(prefs); setEditCtx(false); }}>
            <div className="form-grid">
              {CTX_FIELDS.map(([k, label]) => (
                <div className="field" key={k}><label htmlFor={`ctx-${k}`}>{label}</label>
                  <input id={`ctx-${k}`} value={prefs.ctx[k]} onChange={(e) => setPrefs({ ...prefs, ctx: { ...prefs.ctx, [k]: e.target.value } })} /></div>
              ))}
            </div>
            <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={() => { setPrefs(loadPrefs()); setEditCtx(false); }}>Cancel</button><button className="btn btn-primary">Save</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

/** Phone photos are large; 1280 px on the long side is plenty and keeps uploads fast on factory Wi-Fi. */
async function downscale(f: File): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(f);
    const s = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
    if (s === 1 && f.type === "image/jpeg") return f;
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * s);
    c.height = Math.round(bmp.height * s);
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    return await new Promise((res) => c.toBlob((b) => res(b ?? f), "image/jpeg", 0.9));
  } catch {
    return f;
  }
}
