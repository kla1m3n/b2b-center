"""Выгрузка результатов: отчёт Excel (сводка + все позиции), обоснование и сводный отчёт Word."""
import io
from collections.abc import Sequence
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app import report
from app.docx import Document
from app.schemas import REGIME_LABELS, ClassificationResult

EXPORT_COLUMNS = ["№", "Товар", "Код ОКПД2", "Наименование ОКПД2", "Режим ПП 1875", "Пункты ПП 1875",
                  "Уверенность, %", "Проверить вручную", "Рекомендация", "Альтернативные коды и их режим", "Пояснение"]
REVIEW_COLUMNS = ["№", "Товар", "Код ОКПД2", "Режим ПП 1875", "Уверенность, %", "Что сделать"]
REGIME_FILL = {"ban": "F8D7DA", "restriction": "FFF3CD", "advantage": "D6E4FF", "none": "D4EDDA"}
REVIEW_FILL = "FFE5B4"
HEAD_FILL = "E7E6E6"
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _items(r: ClassificationResult) -> str:
    return "; ".join(
        f"прил. {m.appendix} п. {m.item_no}" + (f" (доля {m.quota}%)" if m.quota else "") for m in r.npa_matches
    ) or "не входит в прил. 1–3"


def _alternatives(r: ClassificationResult) -> str:
    return "\n".join(
        f"{a.code} — {REGIME_LABELS[a.verdict]} ({report.items_ref(a.npa_matches)}), {report.pct(a.confidence)}%"
        for a in r.alternatives)


def _edition(results: Sequence[ClassificationResult]) -> str:
    return next((f"Редакция: {r.npa_version}" for r in results if r.npa_version), "")


def _header(ws, row: int, values: Sequence[str]) -> None:
    for col, v in enumerate(values, 1):
        cell = ws.cell(row, col, v)
        cell.font, cell.fill, cell.alignment = BOLD, _fill(HEAD_FILL), WRAP


def _percent(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0


def _summary_sheet(ws, results: Sequence[ClassificationResult]) -> None:
    """Лист «Сводка»: режимы с долями, затем позиции для ручной проверки и позиции с наименьшей уверенностью."""
    s = report.summarize(results)
    ws.cell(1, 1, "Сводка по проверке товаров на соответствие ПП РФ № 1875").font = Font(bold=True, size=14)
    ws.cell(2, 1, _edition(results))
    _header(ws, 4, ["Режим", "Позиций", "Доля, %"])
    row = 5
    for x in s.by_regime:
        ws.cell(row, 1, x.label).fill = _fill(REGIME_FILL[x.regime.value])
        ws.cell(row, 2, x.count)
        ws.cell(row, 3, _percent(x.count, s.total))
        row += 1
    if s.errors:
        ws.cell(row, 1, "Не распознано")
        ws.cell(row, 2, s.errors)
        ws.cell(row, 3, _percent(s.errors, s.total))
        row += 1
    ws.cell(row, 1, "Всего").font = BOLD
    ws.cell(row, 2, s.total).font = BOLD
    ws.cell(row, 3, 100.0 if s.total else 0.0).font = BOLD
    row += 2
    ws.cell(row, 1, "Требуют ручной проверки").font = BOLD
    ws.cell(row, 2, s.needs_review + s.errors).font = BOLD
    ws.cell(row, 3, _percent(s.needs_review + s.errors, s.total)).font = BOLD
    row += 2

    ws.cell(row, 1, "Позиции для ручной проверки").font = Font(bold=True, size=12)
    row += 1
    review = report.review_items(results)
    if review:
        _header(ws, row, REVIEW_COLUMNS)
        for idx, r in review:
            row += 1
            values = [idx, r.input, r.okpd2.code if r.okpd2 else "", "" if r.error else REGIME_LABELS[r.verdict],
                      "" if r.error else report.pct(r.confidence), r.recommendation or report.recommendation(r)]
            for col, v in enumerate(values, 1):
                ws.cell(row, col, v).alignment = WRAP
            ws.cell(row, 2).fill = _fill(REVIEW_FILL)
    else:
        ws.cell(row, 1, "Нет: по всем позициям уверенность выше порога.")
    row += 2

    ws.cell(row, 1, f"Позиции с наименьшей уверенностью (до {report.LOWEST_N})").font = Font(bold=True, size=12)
    row += 1
    _header(ws, row, REVIEW_COLUMNS[:5])
    for x in s.lowest_confidence:
        row += 1
        for col, v in enumerate([x.idx, x.input, x.code, REGIME_LABELS[x.verdict], report.pct(x.confidence)], 1):
            ws.cell(row, col, v).alignment = WRAP
    for col, width in zip("ABCDEF", (30, 50, 16, 18, 16, 90)):
        ws.column_dimensions[col].width = width


def results_to_xlsx(results: Sequence[ClassificationResult]) -> bytes:
    """Отчёт в Excel: лист «Сводка» (режимы, ручная проверка) и лист «Результаты» (все позиции с рекомендацией)."""
    wb = Workbook()
    wb.active.title = "Сводка"
    _summary_sheet(wb.active, results)
    ws = wb.create_sheet("Результаты")
    _header(ws, 1, EXPORT_COLUMNS)
    for idx, r in enumerate(results, 1):
        ws.append([
            idx,
            r.input,
            r.okpd2.code if r.okpd2 else "",
            r.okpd2.title if r.okpd2 else "",
            "" if r.error else REGIME_LABELS[r.verdict],
            "" if r.error else _items(r),
            "" if r.error else report.pct(r.confidence),  # вниз, как на сайте: 0.7964 при пороге 80% — это 79%
            "да" if r.needs_review else "нет",
            r.recommendation or report.recommendation(r),
            _alternatives(r),
            r.error or r.explanation,
        ])
        for cell in ws[ws.max_row]:
            cell.alignment = WRAP
        if not r.error:
            ws.cell(ws.max_row, 5).fill = _fill(REGIME_FILL[r.verdict.value])
        if r.needs_review:
            ws.cell(ws.max_row, 8).fill = _fill(REVIEW_FILL)
    for col, width in zip("ABCDEFGHIJK", (6, 40, 16, 45, 16, 28, 14, 12, 70, 45, 50)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions  # фильтр Excel по любой колонке, в том числе «Проверить вручную»
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _justification_block(doc: Document, r: ClassificationResult) -> None:
    """Обоснование одной позиции в Word — те же сведения, что в тексте report.justification."""
    doc.field("Наименование товара", r.input)
    if r.error or r.okpd2 is None:
        doc.field("Результат", r.error or "наименование не распознано")
        doc.field("Рекомендация", r.recommendation or report.recommendation(r))
        return
    doc.field("Код ОКПД2", f"{r.okpd2.code} — {r.okpd2.title}")
    matched = r.matched_text or r.okpd2.title
    if matched.strip().lower() == r.okpd2.title.strip().lower():
        doc.field("Основание выбора кода", "наименование товара соответствует официальному наименованию кода в ОКПД2.")
    else:
        doc.field("Основание выбора кода",
                  f"наименование товара совпало с формулировкой «{matched}», относящейся к этому коду ОКПД2.")
    doc.field("Режим по ПП № 1875", report.REGIME_NAMES[r.verdict].lower())
    if r.npa_matches:
        rows: list[list] = [["Приложение, пункт", "Режим", "Наименование позиции", "Код", "Мин. доля"]]
        shown, hidden = report.main_items(r.npa_matches)
        rows += [[f"Прил. № {m.appendix}, п. {m.item_no}", report.REGIME_NAMES[m.regime],
                  report.short(m.title) + (" (есть дополнительные условия)" if m.has_conditions else ""), m.matched_code,
                  f"{m.quota}%" if m.quota else "—"] for m in shown]
        doc.table(rows, [20, 16, 40, 14, 10])
        if hidden:
            doc.para(f"Остальные пункты постановления, распространяющиеся на этот код ({hidden}), — "
                     "в полном результате проверки на сайте.")
    else:
        doc.field("Основание", "код не входит в приложения № 1–3 постановления.")
    if r.npa_version or r.npa_source_url:
        doc.field("Источник", r.npa_version or r.npa_source_url, url=r.npa_source_url)
    doc.field("Уверенность классификации", f"{report.pct(r.confidence)}%"
              + (" — ниже порога, код требуется подтвердить вручную" if r.needs_review else ""))
    if r.alternatives:
        doc.para(("Альтернативные коды ОКПД2 и их режим:", {"bold": True}))
        rows = [["Код", "Наименование", "Режим", "Пункты ПП", "Увер."]]
        rows += [[a.code, a.title, report.REGIME_NAMES[a.verdict] + (" — режим другой" if a.regime_differs else ""),
                  report.items_ref(a.npa_matches), f"{report.pct(a.confidence)}%"] for a in r.alternatives]
        doc.table(rows, [16, 36, 18, 20, 10])
    doc.field("Рекомендация", r.recommendation or report.recommendation(r))


def _footer(doc: Document, today: date) -> None:
    doc.para(f"Сформировано автоматически {today:%d.%m.%Y} классификатором товаров по ПП № 1875. "
             "Код ОКПД2 подобран по наименованию товара; режим определён сверкой кода с приложениями постановления.")


def justification_to_docx(r: ClassificationResult, today: date | None = None) -> bytes:
    """Обоснование по одному товару — документ Word для вставки в документацию или служебную записку."""
    doc = Document()
    doc.heading("Обоснование применения национального режима")
    doc.para("по постановлению Правительства Российской Федерации от 23.12.2024 № 1875")
    _justification_block(doc, r)
    _footer(doc, today or date.today())
    return doc.to_bytes()


def report_to_docx(results: Sequence[ClassificationResult], today: date | None = None) -> bytes:
    """Сводный отчёт в Word: сводка по режимам, позиции для ручной проверки, обоснование по каждой позиции."""
    s = report.summarize(results)
    doc = Document()
    doc.heading("Сводный отчёт по проверке товаров на соответствие ПП РФ № 1875")
    if _edition(results):
        doc.para(_edition(results))
    doc.para(f"Позиций в списке: {s.total}. Требуют ручной проверки: {s.needs_review + s.errors}.")

    doc.heading("1. Сводка по режимам", 2)
    rows: list[list] = [["Режим", "Позиций", "Доля"]]
    rows += [[x.label, str(x.count), f"{_percent(x.count, s.total):g}%"] for x in s.by_regime]
    if s.errors:
        rows.append(["Не распознано", str(s.errors), f"{_percent(s.errors, s.total):g}%"])
    rows.append([("Всего", {"bold": True}), (str(s.total), {"bold": True}), ("100%", {"bold": True})])
    doc.table(rows, [50, 25, 25])

    doc.heading("2. Позиции для ручной проверки", 2)
    review = report.review_items(results)
    if review:
        rows = [["№", "Товар", "Код ОКПД2", "Режим", "Увер."]]
        rows += [[str(i), r.input, r.okpd2.code if r.okpd2 else "—",
                  "—" if r.error else report.REGIME_NAMES[r.verdict], "—" if r.error else f"{report.pct(r.confidence)}%"]
                 for i, r in review]
        doc.table(rows, [6, 46, 18, 20, 10])
    else:
        doc.para("Нет: по всем позициям уверенность выше порога.")

    doc.heading("3. Обоснование по каждой позиции", 2)
    for i, r in enumerate(results, 1):
        doc.para((f"Позиция {i}", {"bold": True}))
        _justification_block(doc, r)
    _footer(doc, today or date.today())
    return doc.to_bytes()
