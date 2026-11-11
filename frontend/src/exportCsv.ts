// Выгрузка результатов в CSV, который Excel открывает без мастера импорта (UTF-8 с BOM, разделитель «;»).
// Нужна в режиме заглушек (без backend нет отчётов Excel и Word) и как простая таблица для своих расчётов.
import { REGIME_LABELS, type ClassificationResult } from "./types";
import { confidencePct } from "./confidence";
import { saveBlob } from "./download";

const HEADER = ["Товар", "Код ОКПД2", "Наименование ОКПД2", "Режим", "Приложение", "Пункт", "Уверенность, %", "Проверить вручную", "Рекомендация"];

function cell(v: string | number): string {
  const s = String(v);
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function resultsToCsv(results: ClassificationResult[]): string {
  const rows = results.map((r) => {
    const top = r.npa_matches[0];
    return [
      r.input,
      r.okpd2?.code ?? "",
      r.okpd2?.title ?? r.error ?? "",
      r.error ? "" : REGIME_LABELS[r.verdict],
      top ? top.appendix : "",
      r.error ? "" : r.npa_matches.map((m) => `${m.appendix}:${m.item_no}`).join(", ") || "не входит в прил. 1–3",
      r.error ? "" : confidencePct(r.confidence),
      r.needs_review ? "да" : "",
      r.recommendation,
    ];
  });
  return "﻿" + [HEADER, ...rows].map((row) => row.map(cell).join(";")).join("\r\n");
}

export function downloadCsv(results: ClassificationResult[], filename = "pp1875-results.csv"): void {
  saveBlob(new Blob([resultsToCsv(results)], { type: "text/csv;charset=utf-8" }), filename);
}

// Шаблон для загрузки списка: backend сам находит колонку с наименованиями и пропускает шапку (io_files.read_names)
const TEMPLATE_ROWS = [
  ["№", "Наименование товара", "Количество"],
  ["1", "Ноутбук Lenovo IdeaPad Slim 3 15.6\"", "5"],
  ["2", "Бумага офисная А4, 500 листов", "100"],
  ["3", "Стул офисный на колёсах", "12"],
  ["4", "Щебень гранитный фракции 20-40", "30"],
];

export function downloadTemplate(): void {
  const csv = "\uFEFF" + TEMPLATE_ROWS.map((row) => row.map(cell).join(";")).join("\r\n");
  saveBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), "shablon-tovary.csv");
}
