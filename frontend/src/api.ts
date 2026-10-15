// Клиент API. При VITE_USE_MOCKS=true все вызовы уходят в заглушки (src/mocks.ts).
import * as mocks from "./mocks";
import type { ClassificationResult, HealthOut, JobOut, NpaItemDetails, NpaVersion } from "./types";

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, init);
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

export function classify(name: string): Promise<ClassificationResult> {
  return USE_MOCKS ? mocks.classify(name) : request("/classify", json({ name }));
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

/** Ссылка на Excel с результатами пакета (backend). В режиме заглушек недоступно. */
export function jobExportUrl(id: string): string | null {
  return USE_MOCKS ? null : `/api/jobs/${id}/export.xlsx`;
}

export function getNpaVersions(): Promise<NpaVersion[]> {
  return USE_MOCKS ? mocks.getNpaVersions() : request("/npa/versions");
}

export function getNpaItem(id: number): Promise<NpaItemDetails> {
  return USE_MOCKS ? mocks.getNpaItem(id) : request(`/npa/items/${id}`);
}

export function uploadNpa(file: File, title: string, sourceUrl: string, adminToken: string): Promise<{ version_id: number }> {
  if (USE_MOCKS) return mocks.uploadNpa(file, title);
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("source_url", sourceUrl);
  // Заголовок для защиты загрузки на публичном сервере — согласовать с backend
  return request("/npa/upload", { method: "POST", body: form, headers: { "X-Admin-Token": adminToken } });
}
