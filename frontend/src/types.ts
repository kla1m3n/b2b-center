// Повторяет backend/app/schemas.py. Меняется схема на backend — меняем и здесь.

export type Regime = "ban" | "restriction" | "advantage" | "none";

export const REGIME_LABELS: Record<Regime, string> = {
  ban: "ЗАПРЕТ",
  restriction: "ОГРАНИЧЕНИЕ",
  advantage: "ПРЕИМУЩЕСТВО",
  none: "НЕ ПОДПАДАЕТ",
};

export interface Okpd2Ref {
  code: string;
  title: string;
}

export interface Alternative {
  code: string;
  title: string;
  confidence: number; // 0..1
}

export interface NpaMatch {
  item_id: number | null;
  regime: Regime;
  appendix: number;
  item_no: string;
  title: string;
  matched_code: string;
  quota: number | null;
  has_conditions: boolean;
  note: string;
  source_url: string;
}

export interface ClassificationResult {
  input: string;
  okpd2: Okpd2Ref | null;
  alternatives: Alternative[];
  confidence: number; // 0..1
  needs_review: boolean;
  npa_matches: NpaMatch[];
  verdict: Regime;
  explanation: string;
  error: string | null;
}

export interface HealthOut {
  status: "ok" | "starting";
  db: boolean;
  models: boolean;
  npa_version: string | null;
}

// --- По плану (задачи 8–9), на backend ещё не реализовано ---

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobOut {
  status: JobStatus;
  total: number;
  done: number;
  results: ClassificationResult[] | null;
}

export type NpaVersionStatus = "parsing" | "ready" | "failed";

export interface NpaVersion {
  id: number;
  title: string;
  uploaded_at: string; // ISO
  status: NpaVersionStatus;
  is_active: boolean;
  items_count: number;
  error: string | null;
}

export interface NpaItemDetails {
  id: number;
  appendix: number;
  item_no: string;
  title: string;
  codes: string[];
  quota: number | null;
  note: string;
  raw_text: string;
  source_url: string;
}
