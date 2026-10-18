import { useEffect, useState } from "react";
import { api } from "../api";
import type { Card } from "../types";
import { downloadCsv, Empty, Icon, Modal, PageHeader, Stat, useToast } from "../ui";

type Filter = "all" | "approved" | "draft";

export default function Knowledge() {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [upload, setUpload] = useState(false);
  const [open, setOpen] = useState<Card | null>(null);
  const [err, setErr] = useState("");
  const load = () => api<Card[]>("/teach/cards").then(setCards).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const list = (cards ?? []).filter((c) => filter === "all" || c.status === filter);
  const drafts = (cards ?? []).filter((c) => c.status === "draft").length;
  const parts = new Set((cards ?? []).map((c) => c.part_number)).size;

  return (
    <>
      <PageHeader eyebrow="Knowledge workspace" title="Expert knowledge"
        sub="A senior inspector explains defects on video once. Gemini drafts one rule card per defect in their words; the expert corrects and approves it. Only approved rules are used on the line."
        actions={<>
          <button className="btn btn-quiet" disabled={!cards?.length} onClick={() => downloadCsv("senpaiqc-expert-rules.csv", [
            ["card_id", "part", "defect", "severity", "inspection_view", "accept_limit", "rework_action", "status", "approved_by", "source_video", "timestamp"],
            ...(cards ?? []).map((c) => [c.card_id, c.part_number, c.defect_name, c.severity, c.inspection_view, c.accept_limit, c.rework_action, c.status, c.approved_by, c.source_video, c.source_timestamp])])}>
            <Icon name="download" /> Rules register (CSV)</button>
          <button className="btn btn-primary" onClick={() => setUpload(true)}><Icon name="video" /> Teach from a video</button>
        </>} />
      {err && <div className="banner"><Icon name="alert" />{err}</div>}

      <div className="stat-grid">
        <Stat label="Expert rules" value={cards?.length ?? "—"} icon="book" foot={`${parts} part number${parts === 1 ? "" : "s"}`} />
        <Stat label="Approved, in use" value={(cards?.length ?? 0) - drafts} icon="check" glow="rgba(53,212,154,.1)" foot="Used by the AI on the line" />
        <Stat label="Waiting for expert approval" value={drafts} icon="clock" glow="rgba(246,189,96,.12)" foot="Not used until approved" />
        <Stat label="Critical defects" value={(cards ?? []).filter((c) => c.severity === "critical").length} icon="alert" glow="rgba(255,111,131,.1)" foot="Always scrap, never rework" />
      </div>

      <div className="filters" style={{ padding: "0 0 14px" }} role="group" aria-label="Filter rules">
        {([["all", "All rules"], ["draft", "Needs approval"], ["approved", "Approved"]] as [Filter, string][]).map(([k, l]) => (
          <button key={k} className="filter-pill" aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>

      {cards && list.length === 0 && <div className="panel"><Empty title="No rules here yet">Teach from a video to draft the first rules.</Empty></div>}
      <div className="k-grid">
        {list.map((c) => (
          <article className="panel k-card" key={c.card_id}>
            <div className="k-art"><Icon name={c.severity === "critical" ? "alert" : c.source_video?.startsWith("SEED") ? "book" : "video"} size={28} /></div>
            <div className="row"><span className="chip blue">{c.part_number}</span>
              <span className={`status ${c.status === "approved" ? "pass" : "review"}`}>{c.status === "approved" ? "Approved" : "Needs approval"}</span>
              <span className={`status ${c.severity === "critical" ? "scrap" : c.severity === "major" ? "review" : "neutral"}`}>{c.severity}</span></div>
            <h3 className="k-title">{c.defect_name.replace(/_/g, " ")}</h3>
            <p className="k-desc"><b>Accept if:</b> {c.accept_limit || "—"}</p>
            <p className="k-desc"><b>Fix:</b> {c.rework_action || "—"}</p>
            <div className="k-meta"><span className="mono">{c.card_id}</span><span>{c.approved_by ? `by ${c.approved_by}` : "not approved"}</span></div>
            <button className="btn btn-sm" onClick={() => setOpen(c)}>{c.status === "draft" ? "Review & approve" : "View rule"} <Icon name="arrow" size={14} /></button>
          </article>
        ))}
      </div>

      <section className="panel section" style={{ padding: 18 }}>
        <div className="row"><span className="stat-icon"><Icon name="video" /></span>
          <div className="grow"><div className="panel-title">From expert video to rule</div>
            <div className="panel-desc">Upload a video → Gemini drafts rule cards with timestamps → the expert edits each one → approve → the line uses it from the next part.</div></div></div>
      </section>

      {upload && <UploadModal onClose={() => setUpload(false)} onDone={() => { setUpload(false); setFilter("draft"); load(); }} />}
      {open && <CardModal card={open} onClose={() => setOpen(null)} onSaved={() => { setOpen(null); load(); }} />}
    </>
  );
}

const DIRECT_MAX_MB = 30; // Cloud Run accepts up to 32 MiB per request
const MAX_MINUTES = 10;
const EXT_TYPES: Record<string, string> = { mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm", "3gp": "video/3gpp", mkv: "video/x-matroska" };

function videoType(f: File) {
  return f.type || EXT_TYPES[f.name.split(".").pop()?.toLowerCase() ?? ""] || "video/mp4";
}

function videoMinutes(f: File): Promise<number | null> {
  return new Promise((res) => {
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => { URL.revokeObjectURL(v.src); res(Number.isFinite(v.duration) ? v.duration / 60 : null); };
    v.onerror = () => res(null);
    v.src = URL.createObjectURL(f);
  });
}

/** PUT straight to Cloud Storage with a signed URL, reporting progress. */
function putWithProgress(url: string, headers: Record<string, string>, file: File, onPct: (p: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", url);
    Object.entries(headers).forEach(([k, v]) => x.setRequestHeader(k, v));
    x.upload.onprogress = (e) => e.lengthComputable && onPct(Math.round((e.loaded / e.total) * 100));
    x.onload = () => (x.status < 300 ? resolve() : reject(new Error(`Upload failed (${x.status}). Try again on a stable connection.`)));
    x.onerror = () => reject(new Error("Upload interrupted. Check the connection and try again."));
    x.send(file);
  });
}

function UploadModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [part, setPart] = useState("IMP-200");
  const [file, setFile] = useState<File | null>(null);
  const [minutes, setMinutes] = useState<number | null>(null);
  const [phase, setPhase] = useState<"" | "upload" | "gemini">("");
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState("");
  const toast = useToast();
  const mb = file ? file.size / 2 ** 20 : 0;
  const tooLong = minutes !== null && minutes > MAX_MINUTES;

  const pick = async (f: File | null) => {
    setFile(f); setErr(""); setMinutes(null);
    if (f) setMinutes(await videoMinutes(f));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || tooLong) return;
    setErr("");
    const type = videoType(file);
    try {
      let r: any;
      const direct = async () => {
        const fd = new FormData();
        fd.append("part_number", part);
        fd.append("video", new File([file], file.name, { type }));
        setPhase("gemini");
        return api("/teach/videos", { method: "POST", body: fd });
      };
      if (mb <= DIRECT_MAX_MB) {
        r = await direct();
      } else {
        const link = await api("/teach/upload-url", { method: "POST", body: JSON.stringify({ filename: file.name, content_type: type, size: file.size }) });
        if (link.mode === "direct") {
          r = await direct();
        } else {
          setPhase("upload"); setPct(0);
          await putWithProgress(link.url, link.headers, file, setPct);
          setPhase("gemini");
          r = await api("/teach/videos/from-upload", { method: "POST", body: JSON.stringify({ uri: link.uri, content_type: type, part_number: part }) });
        }
      }
      toast({ title: `${r.cards.length} draft rule(s) ready`, body: ` From ${file.name}. Review and approve them.` });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setPhase("");
    }
  };

  const busy = phase !== "";
  return (
    <Modal title="Teach from an expert video" sub="2–5 minutes is ideal. The expert holds each part (or a printed photo), names the defect, says when it is acceptable, how to look at it and how to fix it." onClose={busy ? () => undefined : onClose}>
      <form onSubmit={submit}>
        <div className="field"><label htmlFor="pn">Part number</label><input id="pn" value={part} onChange={(e) => setPart(e.target.value)} required disabled={busy} /></div>
        <label className="dropzone">
          <input type="file" accept="video/*" capture="environment" onChange={(e) => pick(e.target.files?.[0] ?? null)} required disabled={busy} aria-label="Expert video" />
          <Icon name="video" size={28} />
          <b>{file ? file.name : "Record or choose a video"}</b>
          <span>{file ? `${mb.toFixed(1)} MB${minutes !== null ? ` · ${minutes.toFixed(1)} min` : ""}` : `MP4, MOV, WEBM or 3GP · up to ${MAX_MINUTES} minutes and 500 MB`}</span>
        </label>
        {tooLong && <p className="error" role="alert">This video is {minutes!.toFixed(1)} minutes. Trim it to the part where the expert explains defects (up to {MAX_MINUTES} minutes).</p>}
        {phase === "upload" && (
          <div className="section" aria-live="polite">
            <div className="bar-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
            <p className="hint">Uploading to Cloud Storage… {pct}%. Keep this window open.</p>
          </div>
        )}
        {phase === "gemini" && <p className="section"><span className="spinner" /> Gemini is watching the video and drafting rules. A 3-minute video usually takes under a minute.</p>}
        {!busy && <div className="banner info section"><Icon name="book" /><div>Gemini watches the video and drafts the rules. Nothing is used on the line until the expert approves each rule.</div></div>}
        {err && <p className="error" role="alert">{err}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" disabled={busy || !file || tooLong}>{busy ? <><span className="spinner" /> Working…</> : "Draft rules"}</button>
        </div>
      </form>
    </Modal>
  );
}

function CardModal({ card, onClose, onSaved }: { card: Card; onClose: () => void; onSaved: () => void }) {
  const [edit, setEdit] = useState(card.status === "draft");
  const [f, setF] = useState(card);
  const [err, setErr] = useState("");
  const toast = useToast();
  const save = async (approve: boolean) => {
    setErr("");
    try {
      const changed = JSON.stringify({ ...f, status: 0, approved_by: 0 }) !== JSON.stringify({ ...card, status: 0, approved_by: 0 });
      if (changed) {
        await api(`/teach/cards/${card.card_id}`, { method: "PUT", body: JSON.stringify({
          defect_name: f.defect_name, visual_cues: f.visual_cues, typical_location: f.typical_location, inspection_view: f.inspection_view ?? "",
          accept_limit: f.accept_limit, severity: f.severity, rework_action: f.rework_action }) });
      }
      if (approve) await api(`/teach/cards/${card.card_id}/approve`, { method: "POST" });
      toast({ title: approve ? "Rule approved" : "Saved as draft", body: approve ? " The line uses it from the next part." : " Approve it when it is right." });
      onSaved();
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal wide title={card.defect_name.replace(/_/g, " ")} sub={<><span className="mono">{card.card_id}</span> · {card.part_number} · source: {card.source_video}{card.source_timestamp ? ` @ ${card.source_timestamp}` : ""}</>} onClose={onClose}>
      {!edit ? (
        <>
          <div className="kv">
            <div><label>Status</label><strong>{card.status === "approved" ? `Approved by ${card.approved_by}` : "Needs approval"}</strong></div>
            <div><label>Severity</label><strong>{card.severity}</strong></div>
            <div><label>Where it appears</label><strong>{card.typical_location || "—"}</strong></div>
          </div>
          <p><b>What it looks like:</b> {card.visual_cues.join("; ")}</p>
          <p><b>How the expert looks:</b> {card.inspection_view || "—"} <span className="muted small">(robot mode presents the part this way for a second look)</span></p>
          <p><b>Accept if:</b> {card.accept_limit}</p>
          <p><b>How to fix:</b> {card.rework_action}</p>
          <div className="modal-actions">
            <button className="btn btn-quiet" onClick={onClose}>Close</button>
            <button className="btn" onClick={() => setEdit(true)}>Edit rule</button>
          </div>
          <p className="hint">Editing an approved rule sends it back for approval, so the line never uses an unchecked change.</p>
        </>
      ) : (
        <>
          <div className="form-grid">
            <div className="field"><label htmlFor="dn">Defect name</label><input id="dn" value={f.defect_name} onChange={(e) => setF({ ...f, defect_name: e.target.value })} /></div>
            <div className="field"><label htmlFor="sv">Severity</label>
              <select id="sv" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value as Card["severity"] })}>
                <option value="minor">minor — usually acceptable</option><option value="major">major — needs rework</option><option value="critical">critical — always scrap</option>
              </select></div>
            <div className="field span-2"><label htmlFor="vc">What it looks like (one cue per line)</label>
              <textarea id="vc" value={f.visual_cues.join("\n")} onChange={(e) => setF({ ...f, visual_cues: e.target.value.split("\n").filter(Boolean) })} /></div>
            <div className="field span-2"><label htmlFor="tl">Where it appears</label><input id="tl" value={f.typical_location} onChange={(e) => setF({ ...f, typical_location: e.target.value })} /></div>
            <div className="field span-2"><label htmlFor="iv">How the expert looks (angle, light, which face)</label><input id="iv" placeholder="e.g. tilt 30 deg toward the light, check the flange edge" value={f.inspection_view ?? ""} onChange={(e) => setF({ ...f, inspection_view: e.target.value })} /></div>
            <div className="field span-2"><label htmlFor="al">Accept if (the expert's limit)</label><textarea id="al" value={f.accept_limit} onChange={(e) => setF({ ...f, accept_limit: e.target.value })} /></div>
            <div className="field span-2"><label htmlFor="ra">How to fix</label><textarea id="ra" value={f.rework_action} onChange={(e) => setF({ ...f, rework_action: e.target.value })} /></div>
          </div>
          {err && <p className="error" role="alert">{err}</p>}
          <div className="modal-actions">
            <button className="btn btn-quiet" onClick={onClose}>Cancel</button>
            <button className="btn" onClick={() => save(false)}>Save draft</button>
            <button className="btn btn-primary" onClick={() => save(true)}><Icon name="check" /> Approve rule</button>
          </div>
        </>
      )}
    </Modal>
  );
}
