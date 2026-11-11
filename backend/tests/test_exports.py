"""Отчёт Excel (сводка + результаты) и документы Word (обоснование, сводный отчёт)."""
import zipfile
from datetime import date
from io import BytesIO
from xml.etree import ElementTree

from openpyxl import load_workbook

from app.exports import justification_to_docx, report_to_docx, results_to_xlsx
from app.report import finalize
from app.schemas import Alternative, ClassificationResult, NpaMatch, Okpd2Ref, Regime

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
URL = "https://example.org/pp1875?a=1&b=2"


def laptop(conf: float = 0.92, review: bool = False, name: str = "Ноутбук") -> ClassificationResult:
    alt = Alternative(code="26.20.13.000", title="Машины вычислительные", confidence=0.31, verdict=Regime.ban,
                      npa_matches=[NpaMatch(regime=Regime.ban, appendix=1, item_no="27", title="Машины", matched_code="26.20.13")],
                      regime_differs=True)
    return finalize(ClassificationResult(
        input=name, okpd2=Okpd2Ref(code="26.20.11.110", title="Ноутбуки"), matched_text="ноутбук", confidence=conf,
        needs_review=review, verdict=Regime.restriction, alternatives=[alt], npa_source_url=URL,
        npa_version="ПП РФ № 1875 (ред. на 30.09.2026)",
        npa_matches=[NpaMatch(regime=Regime.restriction, appendix=2, item_no="195", title="Компьютеры",
                              matched_code="26.20.11", source_url=URL),
                     NpaMatch(regime=Regime.advantage, appendix=3, item_no="37", title="Компьютеры",
                              matched_code="26.20.11", quota=80, source_url=URL)]))


def bread() -> ClassificationResult:
    return finalize(ClassificationResult(input="Хлеб", okpd2=Okpd2Ref(code="10.71.11.110", title="Хлеб"),
                                         matched_text="Хлеб", confidence=0.97, needs_review=False, verdict=Regime.none))


def broken() -> ClassificationResult:
    return finalize(ClassificationResult(input="123", error="Пустое или нераспознанное наименование"))


def cells(ws) -> list[list]:
    return [[c.value for c in row] for row in ws.iter_rows()]


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert z.testzip() is None
        for name in z.namelist():  # каждая часть — корректный XML
            ElementTree.fromstring(z.read(name))
        root = ElementTree.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p"))


def test_xlsx_has_summary_sheet_and_results_sheet():
    wb = load_workbook(BytesIO(results_to_xlsx([laptop(), laptop(0.61, review=True, name="Нетбук"), bread(), broken()])))
    assert wb.sheetnames == ["Сводка", "Результаты"]
    summary = cells(wb["Сводка"])
    flat = {row[0]: row for row in summary if row[0]}
    assert flat["Запрет"][1:3] == [0, 0] and flat["Ограничение"][1:3] == [2, 50] and flat["Не подпадает"][1:3] == [1, 25]
    assert flat["Не распознано"][1:3] == [1, 25] and flat["Всего"][1] == 4
    assert flat["Требуют ручной проверки"][1:3] == [2, 50]
    # список для ручной проверки: нераспознанное и позиция с низкой уверенностью, с рекомендацией
    start = next(i for i, row in enumerate(summary) if row[0] == "Позиции для ручной проверки")
    assert summary[start + 1][:6] == ["№", "Товар", "Код ОКПД2", "Режим ПП 1875", "Уверенность, %", "Что сделать"]
    assert summary[start + 2][:2] == [4, "123"] and summary[start + 3][:5] == [2, "Нетбук", "26.20.11.110", "ОГРАНИЧЕНИЕ", 61]
    assert "Сначала подтвердите код ОКПД2 вручную" in summary[start + 3][5]
    low = next(i for i, row in enumerate(summary) if row[0] and str(row[0]).startswith("Позиции с наименьшей уверенностью"))
    assert [row[1] for row in summary[low + 2:low + 5]] == ["Нетбук", "Ноутбук", "Хлеб"]


def test_xlsx_results_have_recommendation_and_alternative_regime():
    ws = load_workbook(BytesIO(results_to_xlsx([laptop(), broken()])))["Результаты"]
    header = [c.value for c in ws[1]]
    assert header[:5] == ["№", "Товар", "Код ОКПД2", "Наименование ОКПД2", "Режим ПП 1875"]
    row = dict(zip(header, [c.value for c in ws[2]]))
    assert row["№"] == 1 and row["Товар"] == "Ноутбук" and row["Код ОКПД2"] == "26.20.11.110"
    assert row["Режим ПП 1875"] == "ОГРАНИЧЕНИЕ" and row["Уверенность, %"] == 92 and row["Проверить вручную"] == "нет"
    assert "прил. 2 п. 195" in row["Пункты ПП 1875"] and "прил. 3 п. 37 (доля 80%)" in row["Пункты ПП 1875"]
    assert "ограничение" in row["Рекомендация"]
    assert row["Альтернативные коды и их режим"] == "26.20.13.000 — ЗАПРЕТ (прил. № 1, п. 27), 31%"
    err = dict(zip(header, [c.value for c in ws[3]]))
    assert err["Режим ПП 1875"] in ("", None) and err["Проверить вручную"] == "да" and "не распознано" in err["Рекомендация"]


def test_xlsx_no_review_items():
    summary = cells(load_workbook(BytesIO(results_to_xlsx([bread()])))["Сводка"])
    assert any(row[0] == "Нет: по всем позициям уверенность выше порога." for row in summary)


def test_justification_docx_is_valid_and_complete():
    data = justification_to_docx(laptop(), today=date(2026, 11, 12))
    text = docx_text(data)
    for part in ("Обоснование применения национального режима", "Наименование товара: Ноутбук",
                 "Код ОКПД2: 26.20.11.110 — Ноутбуки", "совпало с формулировкой «ноутбук»", "Режим по ПП № 1875: ограничение",
                 "Прил. № 2, п. 195", "80%", "Уверенность классификации: 92%", "26.20.13.000", "Запрет — режим другой",
                 "Рекомендация: Действует ограничение", "Сформировано автоматически 12.11.2026"):
        assert part in text, part
    with zipfile.ZipFile(BytesIO(data)) as z:
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    assert "https://example.org/pp1875?a=1&amp;b=2" in rels and 'TargetMode="External"' in rels  # ссылка на текст ПП


def test_justification_docx_has_upcoming_change_warning():
    r = laptop()
    r.npa_matches[0].note = ("Внимание: с 01.07.2027 — запрет (прил. 1, поз. 136(1)), позиция исключается из прил. 2 "
                             "(ПП от 30.10.2026 N 1428)")
    text = docx_text(justification_to_docx(finalize(r)))
    assert ("Внимание, предстоящее изменение (прил. № 2, п. 195): с 01.07.2027 — запрет (прил. 1, поз. 136(1)), "
            "позиция исключается из прил. 2 (ПП от 30.10.2026 N 1428).") in text
    assert "Для извещений, размещаемых с 01.07.2027, режим изменится на «запрет»" in text
    assert "Внимание" not in docx_text(justification_to_docx(laptop()))  # без примечания — строки нет


def test_docx_escapes_special_and_control_characters():
    r = laptop(name='Ноутбук <15"> & «чехол»\x0b')
    text = docx_text(justification_to_docx(r))
    assert 'Наименование товара: Ноутбук <15"> & «чехол»' in text


def test_report_docx_has_summary_review_list_and_every_item():
    text = docx_text(report_to_docx([laptop(), laptop(0.61, review=True, name="Нетбук"), bread(), broken()],
                                    today=date(2026, 11, 12)))
    assert "Сводный отчёт по проверке товаров на соответствие ПП РФ № 1875" in text
    assert "Редакция: ПП РФ № 1875 (ред. на 30.09.2026)" in text
    assert "Позиций в списке: 4. Требуют ручной проверки: 2." in text
    for part in ("1. Сводка по режимам", "2. Позиции для ручной проверки", "3. Обоснование по каждой позиции",
                 "Позиция 1", "Позиция 4", "Наименование товара: Хлеб", "Результат: Пустое или нераспознанное наименование"):
        assert part in text, part
