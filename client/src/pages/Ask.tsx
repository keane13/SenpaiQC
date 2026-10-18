import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon, PageHeader } from "../ui";

type Citation = { id: string; title: string; type: string; page: string };
type Msg = { role: "user" | "assistant"; text: string; grounded?: boolean; citations?: Citation[]; follow_ups?: string[]; meta?: string; error?: boolean };

const SUGGESTIONS = [
  "Berapa batas porositas yang boleh diterima dan bagaimana memperbaikinya?",
  "Which defects must always be scrapped?",
  "What caused the porosity spike, and what evidence is there?",
  "How accurate is the inspection model on held-out parts?",
  "Apa isi draf 8D terakhir?",
];
const TYPE_LABEL: Record<string, string> = {
  expert_rule: "Expert rule", investigation: "Investigation", "8d_report": "8D report",
  statistics: "Statistics", evaluation: "Evaluation", model_training: "Model training",
};

export default function Ask() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const history = msgs.filter((m) => !m.error).map((m) => ({ role: m.role, text: m.text }));
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api("/ask", { method: "POST", body: JSON.stringify({ question, history }) });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, grounded: r.grounded, citations: r.citations, follow_ups: r.follow_ups,
        meta: `${r.model} · ${(r.latency_ms / 1000).toFixed(1)} s · $${r.cost_usd.toFixed(4)} · ${r.sources_considered} records searched` }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", text: e.message, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Ask the plant's knowledge" title="Ask SenpaiQC"
        sub="Ask about defects, the expert's rules, root causes, 8D reports or model results, in English or Bahasa Indonesia. Answers come only from SenpaiQC records and always show their sources." />

      <section className="panel chat">
        <div className="chat-log" aria-live="polite">
          {msgs.length === 0 && (
            <div className="chat-empty">
              <span className="stat-icon" style={{ width: 44, height: 44 }}><Icon name="message" size={22} /></span>
              <p className="muted">Try one of these:</p>
              <div className="row" style={{ justifyContent: "center" }}>
                {SUGGESTIONS.map((s) => <button key={s} className="filter-pill" onClick={() => send(s)}>{s}</button>)}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.role} ${m.error ? "err" : ""}`}>
              <div className="bubble-text">{m.text}</div>
              {m.role === "assistant" && !m.error && (
                <>
                  <div className="row" style={{ marginTop: 10 }}>
                    {m.grounded
                      ? <span className="status pass">Answered from records</span>
                      : <span className="status review">Not found in records — check with the inspector or QC</span>}
                    {m.citations?.map((c) => (
                      <a key={c.id} className="chip blue" href={`#${c.page}`} title={c.id}>
                        <Icon name={c.type === "expert_rule" ? "book" : c.type === "8d_report" ? "file" : c.type === "investigation" ? "alert" : "chart"} size={13} />
                        {TYPE_LABEL[c.type] ?? c.type}: {c.title.replace(/^Expert rule: /, "")}
                      </a>
                    ))}
                  </div>
                  {!!m.follow_ups?.length && i === msgs.length - 1 && (
                    <div className="row" style={{ marginTop: 8 }}>
                      {m.follow_ups.map((f) => <button key={f} className="filter-pill" onClick={() => send(f)}>{f}</button>)}
                    </div>
                  )}
                  {m.meta && <div className="hint" style={{ marginTop: 6 }}>{m.meta}</div>}
                </>
              )}
            </div>
          ))}
          {busy && <div className="bubble assistant"><span className="spinner" /> Searching the records…</div>}
          <div ref={end} />
        </div>
        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(q); }}>
          <label className="sr-only" htmlFor="ask-q">Your question</label>
          <textarea id="ask-q" rows={1} maxLength={500} value={q} placeholder="Ask about a defect, a rule, a root cause…"
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(q); } }} />
          <button className="btn btn-primary" disabled={busy || !q.trim()} aria-label="Send"><Icon name="arrow" /></button>
        </form>
      </section>
      <p className="hint" style={{ marginTop: 10 }}>
        The assistant can only read records; it cannot change decisions or approve rules. If an answer matters for a part on the line, open the cited source and check it.
      </p>
    </>
  );
}
