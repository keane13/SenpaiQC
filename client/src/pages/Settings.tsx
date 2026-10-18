import { useEffect, useState } from "react";
import { api } from "../api";
import { LANGUAGES, loadPrefs, ROLES, savePrefs } from "../prefs";
import type { Mode } from "../types";
import { Icon, PageHeader, useToast } from "../ui";

type Theme = "auto" | "dark" | "light";
export function applyTheme(t: Theme) {
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}
export function loadTheme(): Theme {
  try { return (localStorage.getItem("sq.theme") as Theme) || "auto"; } catch { return "auto"; }
}

export default function Settings({ mode }: { mode: Mode | null }) {
  const [prefs, setPrefs] = useState(loadPrefs);
  const [theme, setTheme] = useState<Theme>(loadTheme());
  const [policy, setPolicy] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const toast = useToast();
  useEffect(() => { api("/health").then((h) => setPolicy(h.policy)).catch(() => undefined); }, []);

  const save = () => {
    savePrefs(prefs);
    try { localStorage.setItem("sq.theme", theme); } catch { /* ignore */ }
    applyTheme(theme);
    toast({ title: "Preferences saved", body: " On this device." });
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const r = await api("/alerts/test", { method: "POST" });
      toast({ title: r.queued ? "Test alert queued" : "Test alert sent", body: r.queued ? " Through Pub/Sub; it arrives in a few seconds." : ` To ${r.sent.join(", ")}.` });
    } catch (e: any) {
      toast({ title: "Test alert failed", body: ` ${e.message}` });
    } finally {
      setTesting(false);
    }
  };
  const channelNames = (mode?.alerts?.channels ?? []).map((c) => (c === "google-chat" ? "Google Chat" : "Telegram"));

  const row = (name: string, desc: string, value: React.ReactNode) => (
    <div className="list-item" style={{ alignItems: "center" }}>
      <div className="grow"><div className="list-title">{name}</div><div className="list-desc">{desc}</div></div><div>{value}</div>
    </div>
  );
  const on = (ok: boolean | undefined, yes: string, no: string) => <span className={`status ${ok ? "pass" : "review"}`}>{ok ? yes : no}</span>;

  return (
    <>
      <PageHeader eyebrow="Workspace preferences" title="Settings & status"
        sub="Your preferences are saved on this device. Quality rules are set on the server and shown here so everyone can see what the AI is allowed to do."
        actions={<button className="btn btn-primary" onClick={save}><Icon name="check" /> Save preferences</button>} />

      <div className="grid-even">
        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">You and this device</h2><div className="panel-desc">Saved locally.</div></div></div>
          <div className="panel-body">
            <div className="field"><label htmlFor="role">Role</label>
              <select id="role" value={prefs.role} onChange={(e) => setPrefs({ ...prefs, role: e.target.value as any })}>
                {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
              <span className="hint">Changes what “What needs you now” shows first.</span></div>
            <div className="field"><label htmlFor="lang">Language for rework steps</label>
              <select id="lang" value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value as any })}>
                {LANGUAGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
            <div className="field"><label htmlFor="theme">Appearance</label>
              <select id="theme" value={theme} onChange={(e) => { setTheme(e.target.value as Theme); applyTheme(e.target.value as Theme); }}>
                <option value="auto">Light (default, best in bright workshops)</option><option value="dark">Dark (control room, low glare)</option></select></div>
            <div className="form-grid">
              {([["part_number", "Default part number"], ["line_id", "Line"], ["shift", "Shift"], ["machine_id", "Machine"], ["mould_id", "Mould"], ["material_lot", "Material lot"]] as const).map(([k, label]) => (
                <div className="field" key={k}><label htmlFor={k}>{label}</label>
                  <input id={k} value={prefs.ctx[k]} onChange={(e) => setPrefs({ ...prefs, ctx: { ...prefs.ctx, [k]: e.target.value } })} /></div>
              ))}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">Quality rules (server)</h2><div className="panel-desc">Read-only here. Changed by the plant admin in the deployment config.</div></div></div>
          <div className="panel-body list">
            {row("A person confirms every scrap", "Scrap is never automatic.", on(true, "Always", ""))}
            {row("Unknown defects wait for a person", "If no expert rule matches, the part is held for rework and review.", on(true, "Always", ""))}
            {row("Fast check is trusted above", "Below this the photo goes to Gemini ER 2.", <b>{policy ? `${Math.round(policy.keep_threshold * 100)}% confidence` : "—"}</b>)}
            {row("New part threshold", "Parts with fewer labelled photos always get the closer look.", <b>{policy ? `${policy.min_labels_per_part} labels` : "—"}</b>)}
            {row("Only approved expert rules are used", "Drafts from videos are ignored until an expert approves them.", on(true, "Always", ""))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h2 className="panel-title">System status</h2><div className="panel-desc">What is connected right now.</div></div></div>
          <div className="panel-body list">
            {row("Gemini (Google AI)", mode?.gemini ? `Reasoning: ${mode.reasoning} · Text: ${mode.text}` : "No API key: offline adapters, every result waits for a person.", on(mode?.gemini, "Connected", "Offline"))}
            {row("Fast check (YOLO)", mode?.fast_path === "none" ? "No weights loaded: every part goes to the closer look." : mode?.fast_path ?? "", on(mode ? mode.fast_path !== "none" : undefined, "Loaded", "Not loaded"))}
            {row("Data store", mode?.backend === "gcp" ? "Firestore, Cloud Storage and BigQuery on Google Cloud." : "Local SQLite and files (development).", on(mode?.backend === "gcp", "Google Cloud", "Local"))}
            {row("Robot cell", "Simulated SO-101 arm behind a safety gate.", on(mode ? mode.robot !== "off" : undefined, "On", "Off"))}
            {row("Spike alerts",
              channelNames.length
                ? `A new spike is sent to ${channelNames.join(" and ")}${mode?.alerts?.via === "pubsub" ? " through Pub/Sub" : ""}.`
                : "No chat connected: spikes show only in Quality analytics.",
              channelNames.length
                ? <button className="btn btn-sm" onClick={sendTest} disabled={testing}>{testing ? <span className="spinner" /> : <Icon name="bell" size={15} />} Send test</button>
                : on(false, "", "Off"))}
          </div>
        </section>
      </div>
    </>
  );
}
