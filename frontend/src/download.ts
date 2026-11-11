// Сохранение файла из браузера: отчёты, обоснование, CSV.

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Текстовый файл в UTF-8 с BOM и переводами строк Windows — «Блокнот» и Word открывают его без кракозябр. */
export function saveText(text: string, filename: string): void {
  saveBlob(new Blob(["﻿" + text.replace(/\r?\n/g, "\r\n")], { type: "text/plain;charset=utf-8" }), filename);
}
