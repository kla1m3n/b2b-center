"""Рекомендация по действию, текст обоснования и сводка по списку — для тендерного специалиста.

Всё строится шаблонами из уже определённых кода, режима и пунктов ПП: ИИ здесь нет, поэтому текст
воспроизводим и проверяем. Формулировки намеренно общие и отсылают к пункту постановления: условия
и исключения конкретной позиции специалист сверяет по тексту ПП (ссылка — в каждом результате).
"""
import math
import re
from collections.abc import Sequence

from app.schemas import (Alternative, ClassificationResult, LowConfidenceItem, NpaMatch, Regime, RegimeShare,
                         ReportSummary)

LOWEST_N = 5  # сколько позиций с наименьшей уверенностью показывать в сводке
ITEMS_LIMIT = 5  # сколько пунктов ПП перечислять в обосновании полностью
TITLE_LIMIT = 200  # до скольки знаков сокращать наименование позиции ПП в тексте
REGIME_ORDER = [Regime.ban, Regime.restriction, Regime.advantage, Regime.none]
REGIME_NAMES = {  # подписи в сводке и отчётах
    Regime.ban: "Запрет",
    Regime.restriction: "Ограничение",
    Regime.advantage: "Минимальная доля",  # прил. № 3 — не «преимущество»: это другая мера постановления
    Regime.none: "Не подпадает",
}


def pct(value: float) -> int:
    """Проценты с округлением вниз, как на сайте и в Excel: 0.7964 при пороге 80% — это 79%."""
    return math.floor(value * 100 + 1e-9)


def item_ref(m: NpaMatch) -> str:
    return f"прил. № {m.appendix}, п. {m.item_no}"


def more(n: int) -> str:
    """«и ещё 3 пункта» — с согласованием слова."""
    word = "пункт" if n % 10 == 1 and n % 100 != 11 else \
        "пункта" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "пунктов"
    return f"и ещё {n} {word}"


def short(text: str, limit: int = TITLE_LIMIT) -> str:
    """Длинное наименование позиции ПП (перечни медизделий — до 900 знаков) обрезается по слову."""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def main_items(matches: Sequence[NpaMatch], limit: int = ITEMS_LIMIT) -> tuple[list[NpaMatch], int]:
    """Пункты для текста: у широких кодов (медизделия) их десятки — показываем главные и число остальных.

    Главные — первый пункт каждого приложения (в том числе прил. № 3 с долей), затем по порядку результата
    (он уже по близости наименования к товару). Порядок сохраняется."""
    if len(matches) <= limit:
        return list(matches), 0
    firsts = {m.appendix: i for i, m in reversed(list(enumerate(matches)))}
    keep = set(firsts.values())
    for i in range(len(matches)):
        if len(keep) >= limit:
            break
        keep.add(i)
    return [m for i, m in enumerate(matches) if i in keep], len(matches) - len(keep)


def items_ref(matches: Sequence[NpaMatch], limit: int = 3) -> str:
    shown, hidden = main_items(matches, limit)
    text = "; ".join(item_ref(m) + (f" (мин. доля {m.quota}%)" if m.quota else "") for m in shown)
    return (text + (f" {more(hidden)}" if hidden else "")) or "не входит в прил. № 1–3"


def _quota_note(matches: Sequence[NpaMatch], also: bool) -> str:
    """Фраза о приложении № 3 (минимальная обязательная доля российских товаров для закупок по 223-ФЗ)."""
    m = next((x for x in matches if x.appendix == 3), None)
    if m is None:
        return ""
    share = f" — {m.quota}%" if m.quota else ""
    return (f"Позиция {'также ' if also else ''}входит в прил. № 3 (п. {m.item_no}): для закупок по 223-ФЗ установлена "
            f"минимальная обязательная доля товаров российского происхождения{share}; учитывайте закупку при расчёте доли.")


WARNING = "Внимание:"  # так начинается примечание позиции о предстоящем переносе в другое приложение (ПП № 1428)
# «с 01.07.2027 — запрет (прил. 1, поз. 136(1))» и «для закупок с извещениями с 01.01.2027 — запрет (прил. 1, поз. 31(1-1))»
_CHANGE = re.compile(r"с (\d{2}\.\d{2}\.\d{4}) — (запрет|ограничение)(?: \((прил\. \d+, поз\. [^\s,]+)\))?")  # номер сам со скобками: 136(1)


def upcoming(matches: Sequence[NpaMatch]) -> list[tuple[NpaMatch, str]]:
    """Пункты с предупреждением о предстоящем изменении и его текст без «Внимание:».

    Остальные примечания (история редакций, условия применения) не предупреждения — в текст не выносятся."""
    return [(m, m.note.strip()[len(WARNING):].strip().rstrip(".")) for m in matches
            if m.note.strip().startswith(WARNING)]


def _change_advice(m: NpaMatch, text: str) -> str:
    c = _CHANGE.search(text)
    if c is None:
        return f"У пункта ({item_ref(m)}) есть предстоящее изменение — сверьте с текстом ПП."
    date, regime, where = c.groups()
    return (f"Для извещений, размещаемых с {date}, режим изменится на «{regime}»"
            + (f" ({where})" if where else "") + ": проверьте дату извещения.")


def recommendation(r: ClassificationResult) -> str:
    """Что делать специалисту: по режиму выбранного кода, с оговорками о ручной проверке и условиях пункта."""
    if r.error or r.okpd2 is None:
        return "Наименование не распознано: уточните его (что за товар, без артикулов и сокращений) и повторите проверку."
    top = next((m for m in r.npa_matches if m.regime == r.verdict), None)
    ref = f" ({item_ref(top)})" if top is not None else ""  # пункта может не быть у результата из старого кэша
    parts = []
    if r.needs_review and not r.code_confirmed:
        parts.append(f"Сначала подтвердите код ОКПД2 вручную: уверенность {pct(r.confidence)}%.")
        other = next((a for a in r.alternatives if a.regime_differs), None)
        if other is not None:
            parts.append(f"При коде {other.code} режим будет другим — «{REGIME_NAMES[other.verdict].lower()}».")
    if r.verdict == Regime.ban:
        parts.append(
            f"Закупка товара иностранного происхождения запрещена{ref}. Закупайте товар российского "
            "происхождения: установите запрет в извещении и документации и требуйте подтверждение страны происхождения "
            "товара. Если российского аналога нет, подготовьте обоснование невозможности соблюдения запрета в порядке, "
            "установленном постановлением.")
    elif r.verdict == Regime.restriction:
        parts.append(
            f"Действует ограничение закупок иностранных товаров{ref}: заявка с иностранным товаром "
            "отклоняется, если подана соответствующая требованиям заявка с товаром российского происхождения. "
            "Установите ограничение в извещении и документации и требуйте подтверждение страны происхождения товара.")
    elif r.verdict == Regime.advantage:
        parts.append("Запрета и ограничения нет: иностранный товар к закупке допускается, товарам российского "
                     "происхождения предоставляется преимущество по общим правилам постановления.")
    else:
        parts.append("Код не входит в приложения № 1–3: запрета, ограничения и минимальной доли нет. Закупка проводится "
                     "на общих основаниях; товарам российского происхождения предоставляется преимущество "
                     "по общим правилам постановления.")
    quota = _quota_note(r.npa_matches, also=r.verdict in (Regime.ban, Regime.restriction))
    if quota:
        parts.append(quota)
    if top is not None and top.has_conditions:
        parts.append("У пункта есть дополнительные условия — сверьте товар с текстом пункта.")
    parts += [_change_advice(m, text) for m, text in upcoming(r.npa_matches)]
    return " ".join(parts)


def _alt_line(a: Alternative) -> str:
    return (f"{a.code} — {a.title}: {REGIME_NAMES[a.verdict].lower()} ({items_ref(a.npa_matches)}), "
            f"уверенность {pct(a.confidence)}%" + ("; режим отличается от выбранного" if a.regime_differs else ""))


def justification(r: ClassificationResult) -> str:
    """Готовый текст обоснования: наименование, код, совпавший фрагмент, режим и пункт со ссылкой, уверенность,
    альтернативы, рекомендация. Простой текст — вставляется в документацию или служебную записку как есть."""
    if r.error or r.okpd2 is None:
        return ""
    lines = [
        "Обоснование применения национального режима по постановлению Правительства РФ от 23.12.2024 № 1875",
        "",
        f"Наименование товара: {r.input}",
        f"Код ОКПД2: {r.okpd2.code} — {r.okpd2.title}",
    ]
    matched = r.matched_text or r.okpd2.title
    if r.code_confirmed:
        lines.append(code_basis(r))
    elif matched.strip().lower() == r.okpd2.title.strip().lower():
        lines.append("Основание выбора кода: наименование товара соответствует официальному наименованию кода "
                     f"в ОКПД2 — «{r.okpd2.title}».")
    else:
        lines.append(f"Основание выбора кода: наименование товара совпало с формулировкой «{matched}», "
                     "относящейся к этому коду ОКПД2.")
    lines.append(f"Режим по ПП № 1875: {REGIME_NAMES[r.verdict].lower()}.")
    if r.npa_matches:
        lines.append("Основание — пункты постановления:")
        shown, hidden = main_items(r.npa_matches)
        for m in shown:
            extra = (f"; минимальная доля {m.quota}%" if m.quota else "") + \
                    ("; есть дополнительные условия" if m.has_conditions else "")
            lines.append(f"  — приложение № {m.appendix}, пункт {m.item_no} ({REGIME_NAMES[m.regime].lower()}): "
                         f"«{short(m.title)}», код {m.matched_code}{extra}")
        if hidden:
            lines.append(f"  — остальные пункты, распространяющиеся на этот код ({hidden}), — в полном результате проверки")
    else:
        lines.append("Основание: код не входит в приложения № 1–3 постановления.")
    lines += [f"Внимание, предстоящее изменение ({item_ref(m)}): {text}." for m, text in upcoming(r.npa_matches)]
    source = " ".join(x for x in (r.npa_version, r.npa_source_url) if x)
    if source:
        lines.append(f"Источник: {source}")
    if not r.code_confirmed:  # у кода, выбранного специалистом, оценка системы в документе не нужна
        lines.append(f"Уверенность классификации: {pct(r.confidence)}%"
                     + (" — ниже порога, код требуется подтвердить вручную." if r.needs_review else "."))
    if r.alternatives:
        lines.append("Альтернативные коды ОКПД2 и их режим:")
        lines += [f"  — {_alt_line(a)}" for a in r.alternatives]
    lines.append(f"Рекомендация: {r.recommendation or recommendation(r)}")
    return "\n".join(lines)


def code_basis(r: ClassificationResult) -> str:
    """Основание выбора кода, когда его выбрал или подтвердил специалист."""
    if r.auto_code and r.okpd2 is not None and r.auto_code != r.okpd2.code:
        return (f"Основание выбора кода: код выбран специалистом вручную (автоматически предлагался код {r.auto_code}).")
    return "Основание выбора кода: код подобран автоматически по наименованию товара и подтверждён специалистом."


def finalize(r: ClassificationResult) -> ClassificationResult:
    """Дописывает рекомендацию и обоснование. Вызывается после пометки «проверьте вручную»: текст от неё зависит."""
    r.recommendation = recommendation(r)
    r.justification = justification(r)
    return r


def review_items(results: Sequence[ClassificationResult]) -> list[tuple[int, ClassificationResult]]:
    """Позиции для ручной проверки (номер с 1, результат): сначала нераспознанные, затем по росту уверенности."""
    marked = [(i, r) for i, r in enumerate(results, 1) if r.needs_review or r.error]
    return sorted(marked, key=lambda x: (not x[1].error, x[1].confidence, x[0]))


def summarize(results: Sequence[ClassificationResult]) -> ReportSummary:
    total = len(results)
    ok = [(i, r) for i, r in enumerate(results, 1) if not r.error and r.okpd2 is not None]
    share = lambda n: round(n / total, 4) if total else 0.0  # noqa: E731
    by_regime = []
    for regime in REGIME_ORDER:
        n = sum(r.verdict == regime for _, r in ok)
        by_regime.append(RegimeShare(regime=regime, label=REGIME_NAMES[regime], count=n, share=share(n)))
    review = sum(bool(r.needs_review) for _, r in ok)
    # код, подтверждённый специалистом, проверять уже не нужно — в список наименьшей уверенности он не идёт
    lowest = sorted((x for x in ok if not x[1].code_confirmed), key=lambda x: (x[1].confidence, x[0]))[:LOWEST_N]
    return ReportSummary(
        total=total,
        errors=total - len(ok),
        by_regime=by_regime,
        needs_review=review,
        needs_review_share=share(review),
        lowest_confidence=[LowConfidenceItem(idx=i, input=r.input, code=r.okpd2.code, verdict=r.verdict,
                                             confidence=r.confidence) for i, r in lowest],
    )

