import { useState } from "react";
import { demoLogin, firebaseEnabled, firebaseLogin } from "../api";
import { loadPrefs, ROLES, savePrefs } from "../prefs";
import { Icon } from "../ui";

const FLOW = [
  ["01", "Teach", "An expert explains defects once on video."],
  ["02", "Inspect", "Every part is checked; hard cases go to Gemini."],
  ["03", "Act", "Clear rework steps in the operator's language."],
  ["04", "Improve", "Spikes are flagged, root cause and 8D drafted."],
];

// The default demo token only exists on a developer's machine; deployed servers refuse it.
const IS_LOCAL = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);

export default function Login({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(loadPrefs().role);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const enter = async (fn: () => Promise<void> | void) => {
    setErr("");
    setBusy(true);
    try {
      await fn();
      savePrefs({ ...loadPrefs(), role });
      onDone();
    } catch (e: any) {
      setErr(e.message ?? "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-left">
        <div className="brand"><div className="brand-mark"><Icon name="logo" size={22} /></div>
          <div><div className="brand-name">Senpai<span>QC</span></div><div className="brand-sub">QUALITY INTELLIGENCE</div></div></div>
        <div className="login-hero">
          <div className="eyebrow">Expert-taught inspection for casting SMEs</div>
          <h1 className="login-title">Turn a senior inspector's eye into <span>every shift's standard.</span></h1>
          <p className="login-desc">Teach once on video. Check every part. Fix it the right way. Find the root cause when defects spike. People stay in charge of every scrap and every rule.</p>
          <div className="row">
            <span className="chip blue"><Icon name="scan" size={14} /> Gemini Robotics ER 2</span>
            <span className="chip blue"><Icon name="shield" size={14} /> Human-approved decisions</span>
            <span className="chip blue"><Icon name="globe" size={14} /> Bahasa · ไทย · Tiếng Việt</span>
          </div>
          <div className="flow">
            {FLOW.map(([n, t, d]) => <div className="flow-step" key={n}><div className="n">{n}</div><b>{t}</b><span>{d}</span></div>)}
          </div>
        </div>
        <div className="small muted">Google Cloud AI Builder Cup 2026 · Manufacturing prototype. Process history in the demo is synthetic and labelled.</div>
      </section>

      <section className="login-right">
        <div className="login-card">
          <div className="brand" style={{ padding: "0 0 26px" }}><div className="brand-mark"><Icon name="logo" size={22} /></div>
            <div><div className="brand-name">Senpai<span>QC</span></div><div className="brand-sub">QUALITY INTELLIGENCE</div></div></div>
          <h2 style={{ fontSize: 26, margin: 0, letterSpacing: "-.8px" }}>Welcome</h2>
          <p className="muted" style={{ margin: "6px 0 20px" }}>Pick your role so the app opens on what matters to you.</p>

          <div className="field">
            <span>I am a…</span>
            <div style={{ display: "grid", gap: 8 }}>
              {ROLES.map(([k, label]) => (
                <label key={k} className="filter-pill" aria-pressed={role === k} style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 46 }}>
                  <input type="radio" name="role" checked={role === k} onChange={() => setRole(k)} style={{ accentColor: "var(--blue)" }} />
                  {label}
                </label>
              ))}
            </div>
          </div>

          <form onSubmit={(e) => { e.preventDefault(); enter(() => firebaseEnabled ? firebaseLogin(email, password) : demoLogin(token.trim())); }}>
            {firebaseEnabled ? (
              <>
                <div className="field"><label htmlFor="em">Work email</label><input id="em" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
                <div className="field"><label htmlFor="pw">Password</label><input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
              </>
            ) : (
              <div className="field">
                <label htmlFor="tk">Access token</label>
                <input id="tk" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste the access token you were given" required autoComplete="off" spellCheck={false} />
                <span className="hint">Judges: the token is in the submission notes, next to the demo link.</span>
              </div>
            )}
            {err && <p className="error small" role="alert">{err === "invalid demo token" ? "That token was not accepted. Check it and try again." : err}</p>}
            <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? "Signing in…" : <>Sign in <Icon name="arrow" /></>}</button>
          </form>
          {!firebaseEnabled && IS_LOCAL && (
            <>
              <div className="divider">LOCAL DEMO</div>
              <button className="btn btn-quiet btn-block" disabled={busy} onClick={() => enter(() => demoLogin("senpaiqc-demo"))}>
                <Icon name="login" /> Continue with the local demo token
              </button>
              <p className="hint" style={{ textAlign: "center", marginTop: 10 }}>Works only where the server uses the default local token.</p>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
