// Повторяет backend/app/schemas.py. Меняется схема на backend — меняем и здесь.

export type Regime = "ban" | "restriction" | "advantage" | "none";

export const REGIME_LABELS: Record<Regime, string> = {
  ban: "ЗАПРЕТ",
  restriction: "ОГРАНИЧЕНИЕ",
  advantage: "МИН. ДОЛЯ", // прил. № 3: минимальная обязательная доля, а не «преимущество» — другая мера ПП
  none: "НЕ ПОДПАДАЕТ",
};

export interface Okpd2Ref {
  code: string;
  title: string;
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

export interface Alternative {
  code: string;
  title: string;
  confidence: number; // 0..1
  // Режим и пункты ПП, если бы товар отнесли к этому коду
  verdict: Regime;
  npa_matches: NpaMatch[];
  regime_differs: boolean; // режим отличается от режима выбранного кода
}

export interface ClassificationResult {
  input: string;
  okpd2: Okpd2Ref | null;
  matched_text: string; // текст классификатора (наименование кода или синоним), с которым совпал товар
  alternatives: Alternative[];
  confidence: number; // 0..1
  needs_review: boolean;
  npa_matches: NpaMatch[];
  verdict: Regime;
  explanation: string;
  error: string | null;
  npa_source_url: string; // текст действующей редакции ПП — есть и у «не подпадает»
  npa_version: string; // название редакции ПП, по которой определён режим
  recommendation: string; // что делать специалисту при таком режиме
  justification: string; // готовый текст обоснования для документации
  code_confirmed: boolean; // код выбран или подтверждён специалистом: пометка «проверьте вручную» снята
  auto_code: string; // код, который система предлагала автоматически (если специалист выбрал другой)
}

// Сводка по списку (backend/app/report.py: summarize). На сайте считается из результатов тем же правилом
// (src/summary.ts): она нужна и для одиночной проверки, и для результатов из истории.
export interface RegimeShare {
  regime: Regime;
  label: string;
  count: number;
  share: number; // доля от всех позиций списка, 0..1
}

export interface LowConfidenceItem {
  idx: number; // номер позиции в списке, с 1
  input: string;
  code: string;
  verdict: Regime;
  confidence: number;
}

export interface ReportSummary {
  total: number;
  errors: number;
  by_regime: RegimeShare[];
  needs_review: number;
  needs_review_share: number;
  lowest_confidence: LowConfidenceItem[];
}

export interface HealthOut {
  status: "ok" | "starting";
  db: boolean;
  models: boolean;
  npa_version: string | null;
  npa_upload_protected: boolean; // загрузка редакции ПП требует пароль администратора
}

// --- backend/app/schemas.py (JobOut) и backend/app/api/npa.py (VersionOut, ItemOut) ---

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobOut {
  job_id: string;
  status: JobStatus;
  total: number;
  done: number;
  error: string | null;
  results: ClassificationResult[] | null; // только при status = "done"
  summary: ReportSummary | null; // вместе с results
}

export type NpaVersionStatus = "parsing" | "ready" | "failed";

export interface NpaVersion {
  id: number;
  title: string;
  source_url: string;
  uploaded_at: string; // ISO
  status: NpaVersionStatus;
  is_active: boolean;
  items_count: number;
  error: string | null;
  warnings: string[]; // например, «Код … отсутствует в справочнике ОКПД2»
}

export interface NpaItemDetails {
  id: number;
  version_id: number;
  appendix: number;
  item_no: string;
  title: string;
  codes: string[];
  regime: Regime;
  quota: number | null;
  note: string;
  has_conditions: boolean;
  source_url: string;
}
