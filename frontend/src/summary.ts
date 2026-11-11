// Сводка по списку для тендерного специалиста — то же правило, что backend/app/report.py (summarize, review_items).
// Считается на сайте из результатов: нужна и для одиночной проверки, и для результатов из истории.
import type { ClassificationResult, Regime, ReportSummary } from "./types";

export const LOWEST_N = 5; // сколько позиций с наименьшей уверенностью показывать
export const REGIME_ORDER: Regime[] = ["ban", "restriction", "advantage", "none"];
export const REGIME_NAMES: Record<Regime, string> = {
  ban: "Запрет",
  restriction: "Ограничение",
  advantage: "Преимущество",
  none: "Не подпадает",
};

/** Короткое действие по режиму — для строки таблицы; полный текст рекомендации приходит с backend. */
export const REGIME_ACTIONS: Record<Regime, string> = {
  ban: "Закупать российский товар",
  restriction: "Установить ограничение",
  advantage: "Учесть в доле закупок",
  none: "Ограничений нет",
};

export function shortAction(r: ClassificationResult): string {
  if (r.error) return "Уточнить наименование";
  return r.needs_review ? "Сначала проверить код" : REGIME_ACTIONS[r.verdict];
}

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

export function summarize(results: ClassificationResult[]): ReportSummary {
  const total = results.length;
  const ok = results.map((r, i) => ({ r, idx: i + 1 })).filter(({ r }) => !r.error && r.okpd2);
  const share = (n: number) => (total ? round4(n / total) : 0);
  const review = ok.filter(({ r }) => r.needs_review).length;
  return {
    total,
    errors: total - ok.length,
    by_regime: REGIME_ORDER.map((regime) => {
      const count = ok.filter(({ r }) => r.verdict === regime).length;
      return { regime, label: REGIME_NAMES[regime], count, share: share(count) };
    }),
    needs_review: review,
    needs_review_share: share(review),
    lowest_confidence: [...ok]
      .sort((a, b) => a.r.confidence - b.r.confidence || a.idx - b.idx)
      .slice(0, LOWEST_N)
      .map(({ r, idx }) => ({ idx, input: r.input, code: r.okpd2!.code, verdict: r.verdict, confidence: r.confidence })),
  };
}

/** Доля в процентах для подписи: целое число, но ненулевая доля не превращается в «0%». */
export function sharePct(share: number): string {
  const p = Math.round(share * 100);
  return share > 0 && p === 0 ? "<1%" : `${p}%`;
}
