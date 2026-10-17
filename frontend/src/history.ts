// История последних проверок — только в этом браузере (localStorage). Хранилище может быть недоступно
// (приватный режим, запрет сайтам) — тогда история просто не сохраняется.
import type { ClassificationResult } from "./types";

const KEY = "pp1875.history.v1";
const MAX_ENTRIES = 10;

export interface HistoryEntry {
  id: string;
  at: string; // ISO
  source: string; // «3 товара» или имя файла
  results: ClassificationResult[];
}

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function save(entries: HistoryEntry[]): HistoryEntry[] {
  // Если не помещается (квота ~5 МБ) — выкидываем самые старые записи
  for (let list = entries; list.length > 0; list = list.slice(0, -1)) {
    try {
      localStorage.setItem(KEY, JSON.stringify(list));
      return list;
    } catch {
      /* пробуем короче */
    }
  }
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* хранилище недоступно */
  }
  return [];
}

export function addToHistory(source: string, results: ClassificationResult[]): HistoryEntry[] {
  // id уникален и для двух проверок в одну миллисекунду
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const entry: HistoryEntry = { id, at: new Date().toISOString(), source, results };
  return save([entry, ...loadHistory()].slice(0, MAX_ENTRIES));
}

export function removeFromHistory(id: string): HistoryEntry[] {
  return save(loadHistory().filter((e) => e.id !== id));
}

export function clearHistory(): HistoryEntry[] {
  return save([]);
}
