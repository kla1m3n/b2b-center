// Рекомендация и обоснование для заглушек — зеркало backend/app/report.py (на рабочем сайте эти тексты
// приходят с backend в полях recommendation и justification; здесь — чтобы демо и тесты выглядели так же).
import { confidencePct } from "./confidence";
import { REGIME_NAMES } from "./summary";
import type { Alternative, ClassificationResult, NpaMatch } from "./types";

const itemRef = (m: NpaMatch) => `прил. № ${m.appendix}, п. ${m.item_no}`;

export function itemsRef(matches: NpaMatch[]): string {
  return matches.map((m) => itemRef(m) + (m.quota ? ` (мин. доля ${m.quota}%)` : "")).join("; ") || "не входит в прил. № 1–3";
}

function quotaNote(matches: NpaMatch[], also: boolean): string {
  const m = matches.find((x) => x.appendix === 3);
  if (!m) return "";
  return `Позиция ${also ? "также " : ""}входит в прил. № 3 (п. ${m.item_no}): для закупок по 223-ФЗ установлена `
    + `минимальная обязательная доля товаров российского происхождения${m.quota ? ` — ${m.quota}%` : ""}; учитывайте закупку при расчёте доли.`;
}

export function recommendation(r: ClassificationResult): string {
  if (r.error || !r.okpd2) {
    return "Наименование не распознано: уточните его (что за товар, без артикулов и сокращений) и повторите проверку.";
  }
  const top = r.npa_matches.find((m) => m.regime === r.verdict);
  const ref = top ? ` (${itemRef(top)})` : "";
  const parts: string[] = [];
  if (r.needs_review) {
    parts.push(`Сначала подтвердите код ОКПД2 вручную: уверенность ${confidencePct(r.confidence)}%.`);
    const other = r.alternatives.find((a) => a.regime_differs);
    if (other) parts.push(`При коде ${other.code} режим будет другим — «${REGIME_NAMES[other.verdict].toLowerCase()}».`);
  }
  if (r.verdict === "ban") {
    parts.push(`Закупка товара иностранного происхождения запрещена${ref}. Закупайте товар российского происхождения: `
      + "установите запрет в извещении и документации и требуйте подтверждение страны происхождения товара. "
      + "Если российского аналога нет, подготовьте обоснование невозможности соблюдения запрета в порядке, установленном постановлением.");
  } else if (r.verdict === "restriction") {
    parts.push(`Действует ограничение закупок иностранных товаров${ref}: заявка с иностранным товаром отклоняется, `
      + "если подана соответствующая требованиям заявка с товаром российского происхождения. "
      + "Установите ограничение в извещении и документации и требуйте подтверждение страны происхождения товара.");
  } else if (r.verdict === "advantage") {
    parts.push("Запрета и ограничения нет: иностранный товар к закупке допускается, товарам российского происхождения предоставляется преимущество.");
  } else {
    parts.push("Код не входит в приложения № 1–3: запрета, ограничения и минимальной доли нет. Закупка проводится "
      + "на общих основаниях; товарам российского происхождения предоставляется преимущество по общим правилам постановления.");
  }
  const quota = quotaNote(r.npa_matches, r.verdict === "ban" || r.verdict === "restriction");
  if (quota) parts.push(quota);
  if (top?.has_conditions) parts.push("У пункта есть дополнительные условия — сверьте товар с текстом пункта.");
  return parts.join(" ");
}

const altLine = (a: Alternative) =>
  `${a.code} — ${a.title}: ${REGIME_NAMES[a.verdict].toLowerCase()} (${itemsRef(a.npa_matches)}), уверенность ${confidencePct(a.confidence)}%`
  + (a.regime_differs ? "; режим отличается от выбранного" : "");

export function justification(r: ClassificationResult): string {
  if (r.error || !r.okpd2) return "";
  const lines = [
    "Обоснование применения национального режима по постановлению Правительства РФ от 23.12.2024 № 1875",
    "",
    `Наименование товара: ${r.input}`,
    `Код ОКПД2: ${r.okpd2.code} — ${r.okpd2.title}`,
  ];
  const matched = r.matched_text || r.okpd2.title;
  lines.push(matched.trim().toLowerCase() === r.okpd2.title.trim().toLowerCase()
    ? `Основание выбора кода: наименование товара соответствует официальному наименованию кода в ОКПД2 — «${r.okpd2.title}».`
    : `Основание выбора кода: наименование товара совпало с формулировкой «${matched}», относящейся к этому коду ОКПД2.`);
  lines.push(`Режим по ПП № 1875: ${REGIME_NAMES[r.verdict].toLowerCase()}.`);
  if (r.npa_matches.length) {
    lines.push("Основание — пункты постановления:");
    for (const m of r.npa_matches) {
      lines.push(`  — приложение № ${m.appendix}, пункт ${m.item_no} (${REGIME_NAMES[m.regime].toLowerCase()}): «${m.title}», код ${m.matched_code}`
        + (m.quota ? `; минимальная доля ${m.quota}%` : "") + (m.has_conditions ? "; есть дополнительные условия" : ""));
    }
  } else {
    lines.push("Основание: код не входит в приложения № 1–3 постановления.");
  }
  const source = [r.npa_version, r.npa_source_url].filter(Boolean).join(" ");
  if (source) lines.push(`Источник: ${source}`);
  lines.push(`Уверенность классификации: ${confidencePct(r.confidence)}%`
    + (r.needs_review ? " — ниже порога, код требуется подтвердить вручную." : "."));
  if (r.alternatives.length) {
    lines.push("Альтернативные коды ОКПД2 и их режим:");
    lines.push(...r.alternatives.map((a) => `  — ${altLine(a)}`));
  }
  lines.push(`Рекомендация: ${r.recommendation || recommendation(r)}`);
  return lines.join("\n");
}

export function finalize(r: ClassificationResult): ClassificationResult {
  const withRec = { ...r, recommendation: recommendation(r) };
  return { ...withRec, justification: justification(withRec) };
}
