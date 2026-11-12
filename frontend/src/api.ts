// Клиент API. При VITE_USE_MOCKS=true все вызовы уходят в заглушки (src/mocks.ts).
import { saveBlob } from "./download";
import * as mocks from "./mocks";
import type { ClassificationResult, HealthOut, JobOut, NpaItemDetails, NpaVersion } from "./types";

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/api${path}`, init);
  } catch {
    // сервер недоступен или нет сети — вместо «Failed to fetch» из браузера
    throw new ApiError("Нет связи с сервером. Проверьте подключение и повторите.");
  }
  if (!r.ok) {
    let msg = `Ошибка сервера (${r.status})`;
    try {
      const body = await r.json();
      if (typeof body?.detail === "string") msg = body.detail;
    } catch {
      /* тело не JSON — оставляем общее сообщение */
    }
    throw new ApiError(msg);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function getHealth(): Promise<HealthOut> {
  return USE_MOCKS ? mocks.getHealth() : request("/health");
}

/** С code — пересчёт под код, выбранный специалистом (режим, пункты ПП, рекомендация и обоснование по нему). */
export function classify(name: string, code?: string): Promise<ClassificationResult> {
  return USE_MOCKS ? mocks.classify(name, code) : request("/classify", json(code ? { name, code } : { name }));
}

export function classifyBatch(names: string[]): Promise<{ job_id: string }> {
  return USE_MOCKS ? mocks.classifyBatch(names) : request("/classify/batch", json({ names }));
}

export function classifyFile(file: File): Promise<{ job_id: string }> {
  if (USE_MOCKS) return mocks.classifyFile(file);
  const form = new FormData();
  form.append("file", file);
  return request("/classify/batch", { method: "POST", body: form });
}

export function getJob(id: string): Promise<JobOut> {
  return USE_MOCKS ? mocks.getJob(id) : request(`/jobs/${id}`);
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const r = await fetch(`/api${path}`, init);
  if (!r.ok) {
    let msg = `Не удалось сформировать файл (${r.status})`;
    try {
      const body = await r.json();
      if (typeof body?.detail === "string") msg = body.detail;
    } catch {
      /* тело не JSON — оставляем общее сообщение */
    }
    throw new ApiError(msg);
  }
  return r.blob();
}

export type ReportKind = "xlsx" | "docx";

/** Отчёты Excel и Word формирует backend; в режиме заглушек их нет (остаются CSV и текст обоснования). */
export const REPORTS_AVAILABLE = !USE_MOCKS;

/** Отчёт по списку: Excel (сводка + результаты) или Word (сводка, ручная проверка, обоснования).
 *  У пакета есть задача на backend — отчёт берётся по ней; у одиночной проверки и результатов из истории
 *  задачи нет — отчёт строится по наименованиям (проверенные товары backend берёт из кэша). */
export async function downloadReport(kind: ReportKind, jobId: string | null, names: string[],
                                     codes: (string | null)[] = []): Promise<void> {
  // коды, выбранные специалистом, знает только сайт — такой отчёт строится по наименованиям и кодам, а не по задаче
  const manual = codes.some(Boolean);
  const blob = jobId && !manual
    ? await requestBlob(`/jobs/${jobId}/${kind === "xlsx" ? "export.xlsx" : "report.docx"}`)
    : await requestBlob(`/report.${kind}`, json(manual ? { names, codes } : { names }));
  saveBlob(blob, `pp1875-otchet.${kind}`);
}

/** Обоснование по одному товару документом Word (code — если код выбран специалистом). */
export async function downloadJustification(name: string, code?: string): Promise<void> {
  saveBlob(await requestBlob("/classify/justification.docx", json(code ? { name, code } : { name })), "pp1875-obosnovanie.docx");
}

/** Таблица специалиста (.xlsx) с дописанными справа результатами и листом сводки — его строки и колонки на месте. */
export async function downloadAnnotated(file: File, codes: (string | null)[] = []): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  if (codes.some(Boolean)) form.append("codes", JSON.stringify(codes));
  const blob = await requestBlob("/report/annotated.xlsx", { method: "POST", body: form });
  saveBlob(blob, file.name.replace(/\.xlsx$/i, "") + " — ПП 1875.xlsx");
}

export function getNpaVersions(): Promise<NpaVersion[]> {
  return USE_MOCKS ? mocks.getNpaVersions() : request("/npa/versions");
}

export function getNpaItem(id: number): Promise<NpaItemDetails> {
  return USE_MOCKS ? mocks.getNpaItem(id) : request(`/npa/items/${id}`);
}

export function uploadNpa(file: File, title: string, sourceUrl: string, adminToken = ""): Promise<{ version_id: number }> {
  if (USE_MOCKS) return mocks.uploadNpa(file, title, sourceUrl, adminToken);
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("source_url", sourceUrl);
  // Пароль нужен, если на сервере задан ADMIN_TOKEN (тогда /api/health отдаёт npa_upload_protected: true)
  const headers: Record<string, string> = adminToken ? { "X-Admin-Token": adminToken } : {};
  return request("/npa/upload", { method: "POST", body: form, headers });
}
