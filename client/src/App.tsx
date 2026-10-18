import { useCallback, useEffect, useState } from "react";
import { api, currentUser, logout } from "./api";
import { loadPrefs, ROLES } from "./prefs";
import type { Mode } from "./types";
import { Icon, type IconName, ToastProvider } from "./ui";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Inspect from "./pages/Inspect";
import Queue from "./pages/Queue";
import Knowledge from "./pages/Knowledge";
import Insights from "./pages/Insights";
import Reports from "./pages/Reports";
import Robot from "./pages/Robot";
import Settings from "./pages/Settings";
import Ask from "./pages/Ask";

export type Page = "overview" | "inspect" | "queue" | "knowledge" | "analytics" | "reports" | "robot" | "settings" | "ask";

const NAV: { group: string; items: [Page, string, IconName][] }[] = [
  { group: "Daily work", items: [["overview", "Overview", "grid"], ["inspect", "Inspect a part", "scan"], ["queue", "Needs confirmation", "inbox"], ["knowledge", "Expert knowledge", "book"], ["ask", "Ask SenpaiQC", "message"]] },
  { group: "Improve", items: [["analytics", "Quality analytics", "chart"], ["reports", "Reports & 8D", "file"], ["robot", "Robot cell", "robot"]] },
  { group: "Preferences", items: [["settings", "Settings & status", "settings"]] },
];
const TITLES = Object.fromEntries(NAV.flatMap((g) => g.items.map(([k, label]) => [k, label]))) as Record<Page, string>;

function readPage(): Page {
  const h = location.hash.slice(1).split("?")[0] as Page;
  return h in TITLES ? h : "overview";
}

export default function App() {
  return <ToastProvider><Shell /></ToastProvider>;
}

function Shell() {
  const [user, setUser] = useState(currentUser());
  const [page, setPage] = useState<Page>(readPage());
  const [mode, setMode] = useState<Mode | null>(null);
  const [pending, setPending] = useState(0);
  const [drawer, setDrawer] = useState(false);
  const role = ROLES.find(([k]) => k === loadPrefs().role)?.[1] ?? "";

  useEffect(() => {
    const on = () => { setPage(readPage()); setDrawer(false); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("sq:signed-out", out);
    return () => window.removeEventListener("sq:signed-out", out);
  }, []);
  useEffect(() => {
    if (user) api("/health").then((h) => setMode(h.mode)).catch(() => setMode(null));
  }, [user]);
  const refreshPending = useCallback(
    () => api<unknown[]>("/decisions?pending=true").then((d) => setPending(d.length)).catch(() => undefined), []);
  useEffect(() => { if (user) refreshPending(); }, [user, page, refreshPending]);

  if (!user) return <Login onDone={() => setUser(currentUser())} />;
  const go = (p: Page) => { location.hash = p; };
  const initials = (user.split(/[@._-]/)[0] || "U").slice(0, 2).toUpperCase();

  return (
    <div className="app">
      <aside className={`sidebar ${drawer ? "open" : ""}`} aria-label="Main navigation">
        <div className="brand">
          <div className="brand-mark"><Icon name="logo" size={22} /></div>
          <div><div className="brand-name">Senpai<span>QC</span></div><div className="brand-sub">QUALITY INTELLIGENCE</div></div>
        </div>
        {NAV.map((g, gi) => (
          <div key={g.group}>
            {gi > 0 && <div className="nav-divider" />}
            <div className="nav-label-group">{g.group}</div>
            <nav className="nav">
              {g.items.map(([k, label, icon]) => (
                <button key={k} aria-current={page === k ? "page" : undefined} onClick={() => go(k)}>
                  <Icon name={icon} /><span className="grow">{label}</span>
                  {k === "queue" && pending > 0 && <span className="nav-count" aria-label={`${pending} waiting`}>{pending}</span>}
                </button>
              ))}
            </nav>
          </div>
        ))}
        <div className="sidebar-bottom">
          <div className="status-card">
            <div className="row"><span className={`dot ${mode?.gemini ? "" : "warn"}`} /><b className="grow">{mode ? (mode.gemini ? "Gemini connected" : "Offline mode") : "Checking…"}</b></div>
            <p>{mode ? (mode.gemini ? `Fast check: ${mode.fast_path}. Hard cases go to ER 2.` : "No Gemini key on the server. Every result waits for a person.") : "Contacting the server."}</p>
            <button className="text-link" onClick={() => go("settings")}>System status <Icon name="arrow" size={13} /></button>
          </div>
          <div className="profile">
            <div className="avatar">{initials}</div>
            <div className="grow"><div className="profile-name">{user}</div><div className="profile-role">{role}</div></div>
            <button className="icon-btn" style={{ width: 36, height: 36 }} onClick={() => { logout(); setUser(null); }} aria-label="Sign out" title="Sign out"><Icon name="logout" size={16} /></button>
          </div>
        </div>
      </aside>
      <div className={`scrim ${drawer ? "show" : ""}`} onClick={() => setDrawer(false)} />

      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setDrawer(true)} aria-label="Open navigation"><Icon name="menu" /></button>
          <div className="crumb"><span>SenpaiQC</span><Icon name="chevron" size={13} /><strong>{TITLES[page]}</strong></div>
          <div className="spacer" />
          <button className="icon-btn" onClick={() => go("queue")} aria-label={`${pending} decisions need confirmation`} title="Needs confirmation" style={{ position: "relative" }}>
            <Icon name="bell" />
            {pending > 0 && <span className="nav-count" style={{ position: "absolute", top: -6, right: -8 }}>{pending}</span>}
          </button>
          {page !== "inspect" && <button className="btn btn-primary hide-sm" onClick={() => go("inspect")}><Icon name="scan" /> Inspect a part</button>}
        </header>
        <main className="content">
          {page === "overview" && <Overview mode={mode} go={go} />}
          {page === "inspect" && <Inspect mode={mode} onChange={refreshPending} />}
          {page === "queue" && <Queue onChange={refreshPending} />}
          {page === "knowledge" && <Knowledge />}
          {page === "analytics" && <Insights />}
          {page === "reports" && <Reports />}
          {page === "robot" && <Robot mode={mode} />}
          {page === "settings" && <Settings mode={mode} />}
          {page === "ask" && <Ask />}
        </main>
      </div>
      {page !== "inspect" && (
        <button className="btn btn-primary btn-lg fab" onClick={() => go("inspect")}><Icon name="scan" /> Inspect a part</button>
      )}
    </div>
  );
}
