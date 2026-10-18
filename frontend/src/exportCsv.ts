// Выгрузка результатов в CSV, который Excel открывает без мастера импорта (UTF-8 с BOM, разделитель «;»).
// Колонки как у backend-экспорта .xlsx (план, задача 8). Нужна, пока нет /api/jobs/{id}/export.xlsx
// и для одиночной проверки, у которой нет задачи на backend.
import { REGIME_LABELS, type ClassificationResult } from "./types";
import { confidencePct } from "./confidence";

const HEADER = ["Товар", "Код ОКПД2", "Наименование ОКПД2", "Режим", "Приложение", "Пункт", "Уверенность, %", "Проверить вручную"];

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
    ];
  });
  return "﻿" + [HEADER, ...rows].map((row) => row.map(cell).join(";")).join("\r\n");
}

export function downloadCsv(results: ClassificationResult[], filename = "pp1875-results.csv"): void {
  const blob = new Blob([resultsToCsv(results)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
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
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "shablon-tovary.csv";
  a.click();
  URL.revokeObjectURL(url);
}
