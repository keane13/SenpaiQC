import { useEffect, useRef, useState } from "react";

/** Width of the container in CSS pixels, so SVG text stays at its real size on any screen. */
function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export interface PPoint { key: string; n: number; d: number; p: number; center: number; ucl: number; out_of_control: boolean }

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

/** p-chart: defect proportion per shift, centre line, 3-sigma UCL. Out-of-control points carry a ▲ label. */
export function PChart({ points }: { points: PPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [ref, W] = useWidth<HTMLElement>();
  if (!points.length) return <p className="muted">No data.</p>;
  const H = W < 480 ? 200 : 240, L = 40, R = 12, T = 12, B = 28;
  const ymax = Math.max(...points.map((p) => Math.max(p.p, p.ucl))) * 1.1 || 0.1;
  const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, points.length - 1);
  const y = (v: number) => T + (1 - v / ymax) * (H - T - B);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.p)}`).join("");
  const ucl = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.ucl)}`).join("");
  const ticks = [0, ymax / 2, ymax];
  const firstOoc = points.findIndex((p) => p.out_of_control);
  const h = hover !== null ? points[hover] : null;
  return (
    <figure style={{ margin: 0 }} ref={ref}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="p-chart of defect rate per shift"
        onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
            <text x={L - 6} y={y(t) + 3} textAnchor="end">{pct(t)}</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(points[0].center)} y2={y(points[0].center)} stroke="var(--ink-2)" strokeWidth={1} />
        <text x={W - R} y={y(points[0].center) - 4} textAnchor="end">centre {pct(points[0].center)}</text>
        <path d={ucl} fill="none" stroke="var(--scrap)" strokeWidth={1.5} strokeDasharray="5 4" />
        <text x={W - R} y={y(points[points.length - 1].ucl) - 4} textAnchor="end">UCL (3σ)</text>
        <path d={line} fill="none" stroke="var(--info)" strokeWidth={2} />
        {points.map((p, i) => (
          <g key={p.key}>
            <circle cx={x(i)} cy={y(p.p)} r={p.out_of_control ? 4.5 : 3} fill={p.out_of_control ? "var(--scrap)" : "var(--info)"}
              stroke="var(--surface)" strokeWidth={2} />
            <rect x={x(i) - (W - L - R) / points.length / 2} y={T} width={(W - L - R) / points.length} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} />
          </g>
        ))}
        {firstOoc >= 0 && (
          <text x={x(firstOoc)} y={y(points[firstOoc].p) - 9} textAnchor="middle" style={{ fill: "var(--scrap)", fontWeight: 700 }}>▲ first flag</text>
        )}
        <text x={L} y={H - 8}>{points[0].key}</text>
        <text x={W - R} y={H - 8} textAnchor="end">{points[points.length - 1].key}</text>
        {h && hover !== null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--ink-2)" strokeWidth={1} />
          </g>
        )}
      </svg>
      <figcaption className="small muted" style={{ minHeight: 20 }}>
        {h ? <>{h.key}: <b>{pct(h.p)}</b> ({h.d}/{h.n}) · UCL {pct(h.ucl)} {h.out_of_control && <span className="error">▲ out of control</span>}</>
          : "Hover a shift for its numbers. Centre line from the first 10 days (phase I)."}
      </figcaption>
      <details className="small"><summary>Table view</summary>
        <table className="plain"><thead><tr><th>Shift</th><th>n</th><th>defects</th><th>rate</th><th>UCL</th><th></th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.key}><td>{p.key}</td><td>{p.n}</td><td>{p.d}</td><td>{pct(p.p)}</td><td>{pct(p.ucl)}</td><td>{p.out_of_control ? "▲" : ""}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}

/** Horizontal bars, sorted, single hue; value labels in text ink. */
export function Bars({ rows, format = (v: number) => String(v) }: { rows: { label: string; value: number }[]; format?: (v: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="muted small">No data yet.</p>;
  return (
    <div role="list">
      {rows.map((r) => (
        <div key={r.label} role="listitem" className="bar-row" title={`${r.label}: ${format(r.value)}`}>
          <span className="bar-label">{r.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(r.value / max) * 100}%` }} /></div>
          <span className="bar-num">{format(r.value)}</span>
        </div>
      ))}
    </div>
  );
}
