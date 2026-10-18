// Per-device preferences (an operator's phone stays on their line and language).
// Stored in localStorage when available; the app works without it.

export interface Prefs {
  language: "en" | "id" | "th" | "vi";
  role: "operator" | "inspector" | "qc";
  ctx: { part_number: string; line_id: string; shift: string; machine_id: string; mould_id: string; material_lot: string };
}

const DEFAULTS: Prefs = {
  language: "id",
  role: "operator",
  ctx: { part_number: "IMP-200", line_id: "L1", shift: "A", machine_id: "MC-02", mould_id: "MD-04", material_lot: "LOT-2409C" },
};

export function loadPrefs(): Prefs {
  try {
    const raw = JSON.parse(localStorage.getItem("sq.prefs") ?? "{}");
    return { ...DEFAULTS, ...raw, ctx: { ...DEFAULTS.ctx, ...(raw.ctx ?? {}) } };
  } catch {
    return DEFAULTS;
  }
}

export function savePrefs(p: Prefs) {
  try { localStorage.setItem("sq.prefs", JSON.stringify(p)); } catch { /* storage unavailable */ }
}

export const LANGUAGES = [["en", "English"], ["id", "Bahasa Indonesia"], ["th", "ไทย"], ["vi", "Tiếng Việt"]] as const;
export const ROLES = [["operator", "Line operator"], ["inspector", "Senior inspector"], ["qc", "QC engineer"]] as const;
