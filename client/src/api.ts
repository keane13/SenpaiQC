// Thin API client. Auth is a demo token (local) or a Firebase ID token (deployed).

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const FIREBASE_KEY = import.meta.env.VITE_FIREBASE_API_KEY as string | undefined;
export const firebaseEnabled = Boolean(FIREBASE_KEY);

type Session = { token: string; refresh?: string; expires?: number; user: string };
let session: Session | null = load();

function load(): Session | null {
  try {
    const raw = localStorage.getItem("sq.session");
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}
function save(s: Session | null) {
  session = s;
  try {
    if (s) localStorage.setItem("sq.session", JSON.stringify(s));
    else localStorage.removeItem("sq.session");
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export const currentUser = () => session?.user ?? null;
export const logout = () => save(null);

export async function demoLogin(token: string) {
  save({ token, user: "demo-inspector" });
  await api("/decisions?limit=1"); // throws (and signs out) if the server rejects the token
}

export async function firebaseLogin(email: string, password: string) {
  const r = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_KEY}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, returnSecureToken: true }) },
  );
  const j = await r.json();
  if (!r.ok) throw new Error(j.error?.message ?? "sign-in failed");
  save({ token: j.idToken, refresh: j.refreshToken, expires: Date.now() + Number(j.expiresIn) * 1000 - 60_000, user: j.email });
}

async function token(): Promise<string> {
  if (!session) throw new Error("not signed in");
  if (session.refresh && session.expires && Date.now() > session.expires) {
    const r = await fetch(`https://securetoken.googleapis.com/v1/token?key=${FIREBASE_KEY}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `grant_type=refresh_token&refresh_token=${encodeURIComponent(session.refresh)}`,
    });
    const j = await r.json();
    if (!r.ok) {
      save(null);
      throw new Error("session expired");
    }
    save({ ...session, token: j.id_token, refresh: j.refresh_token, expires: Date.now() + Number(j.expires_in) * 1000 - 60_000 });
  }
  return session!.token;
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await token()}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const r = await fetch(`${BASE}/api${path}`, { ...init, headers });
  if (r.status === 401) {
    save(null);
    window.dispatchEvent(new Event("sq:signed-out"));
    throw new Error("invalid demo token");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json() as Promise<T>;
}

export const secondLookUrl = (episodeId: string) =>
  `${BASE}/api/act/second-look/${episodeId}/image?token=${encodeURIComponent(session?.token ?? "")}`;

/** Authenticated file download (keeps the token out of the URL). */
export async function downloadFile(path: string, filename: string) {
  const r = await fetch(`${BASE}/api${path}`, { headers: { Authorization: `Bearer ${await token()}` } });
  if (!r.ok) throw new Error(`Download failed (${r.status})`);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const imageUrl = (decisionId: string) =>
  `${BASE}/api/decisions/${decisionId}/image?token=${encodeURIComponent(session?.token ?? "")}`;
