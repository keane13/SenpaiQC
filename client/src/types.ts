export type Severity = "minor" | "major" | "critical";
export type DecisionValue = "pass" | "rework" | "scrap";

export interface Card {
  card_id: string;
  part_number: string;
  defect_name: string;
  visual_cues: string[];
  typical_location: string;
  inspection_view: string;
  accept_limit: string;
  severity: Severity;
  rework_action: string;
  source_video: string;
  source_timestamp: string;
  approved_by: string | null;
  status: "draft" | "approved";
}

export interface Defect {
  card_id: string | null;
  point: number[];
  box: number[];
  severity: Severity;
  label: string;
}

export interface InspectionResult {
  id: string;
  image_uri: string;
  part_number: string;
  path: "yolo" | "er2";
  yolo: { class: string | null; confidence: number };
  defects: Defect[];
  decision: DecisionValue;
  rationale: string;
  needs_human_confirm: boolean;
  latency_ms: number;
  cost_usd: number;
  escalation_reason: string | null;
  reasoning_model: string | null;
  confirmed?: boolean;
  confirmed_by?: string;
  image_size: number[];
  line?: Record<string, string>;
}

export interface Mode {
  backend: string;
  fast_path: string;
  reasoning: string;
  text: string;
  robot: string;
  gemini: boolean;
}

export interface Hypothesis {
  rank: number;
  statement: string;
  blamed: Record<string, string>;
  evidence: string[];
  confidence: string;
}

export interface Investigation {
  id: string;
  defect_name: string;
  part_number: string;
  shift_key: string;
  rate: number;
  ucl: number;
  center: number;
  status: "open" | "analysed" | "closed";
  hypotheses: Hypothesis[];
  agent_trace: { tool: string; args: Record<string, unknown>; result_preview: string }[];
  agent_model: string | null;
  report_id: string | null;
  time_to_8d_minutes?: number;
  analysis_seconds?: number;
}
