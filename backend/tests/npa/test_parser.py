import re
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.npa.parser import NpaParseError, parse_npa
from app.schemas import Regime

FIXTURES = Path(__file__).parent.parent / "fixtures"
CODE_RE = re.compile(r"\d{2}(\.\d{1,3}){0,3}")


def test_parse_json_sample_extracts_all_appendices():
    doc = parse_npa(FIXTURES / "npa_sample.json")
    items = doc.items
    assert {i.regime for i in items} == {Regime.ban, Regime.restriction, Regime.advantage}
    assert all(i.codes and all(CODE_RE.fullmatch(c) for c in i.codes) for i in items)
    assert all(i.item_no for i in items)
    assert doc.title and doc.source_url


def test_parse_json_quota_and_subitem():
    items = parse_npa(FIXTURES / "npa_sample.json").items
    shcheben = next(i for i in items if i.appendix == 3 and i.item_no == "1")
    assert shcheben.quota == 80
    assert any(i.item_no == "31_1" and i.regime == Regime.ban for i in items)


def test_conditions_flag_from_title():
    items = parse_npa(FIXTURES / "npa_sample.json").items
    med = next(i for i in items if i.appendix == 2 and i.item_no == "179")  # «за исключением: кровати…»
    paper = next(i for i in items if i.appendix == 1 and i.item_no == "10")  # «Бумага и картон»
    assert med.has_conditions is True
    assert paper.has_conditions is False


def test_parse_xlsx(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["appendix", "item_no", "title", "codes", "quota", "exclusions", "note"])
    ws.append([1, "10", "Бумага и картон", "17.12", None, "17.12.14", ""])
    ws.append([3, "37", "Компьютеры портативные", "26.20.11, 26.20.13", 80, None, None])
    path = tmp_path / "npa.xlsx"
    wb.save(path)
    items = parse_npa(path).items
    assert items[0].exclusions == ["17.12.14"]
    assert items[1].codes == ["26.20.11", "26.20.13"]
    assert items[1].quota == 80 and items[1].regime == Regime.advantage


def test_bad_file_raises_russian_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(NpaParseError, match="Не удалось"):
        parse_npa(bad)
    with pytest.raises(NpaParseError, match="формат"):
        parse_npa(tmp_path / "x.docx")


def test_empty_items_raise(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text('{"title": "x", "items": []}', encoding="utf-8")
    with pytest.raises(NpaParseError, match="позиц"):
        parse_npa(p)
