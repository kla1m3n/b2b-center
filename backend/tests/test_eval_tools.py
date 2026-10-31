import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from add_eval_rows import labeled, select, split  # noqa: E402
from fetch_eis_notices import purchase_objects, sphere  # noqa: E402
from make_train_set import LeakGuard, tokens  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.npa.parser import parse_npa  # noqa: E402

# Упрощённое извещение с пространствами имён, как в выгрузке ЕИС: позиция с ОКПД2, позиция КТРУ, лекарство,
# позиция без наименования. Проверяет разбор, а не точную схему ЕИС — её сверяем на первом реальном архиве (--sample).
NOTICE = """<?xml version="1.0" encoding="UTF-8"?>
<ns5:export xmlns:ns5="http://zakupki.gov.ru/oos/export/1" xmlns:ns2="http://zakupki.gov.ru/oos/base/1"
            xmlns:ns4="http://zakupki.gov.ru/oos/common/1" xmlns:ns7="http://zakupki.gov.ru/oos/EPtypes/1">
 <ns7:epNotificationEF2020>
  <ns7:commonInfo><ns7:purchaseNumber>0373100012326000101</ns7:purchaseNumber></ns7:commonInfo>
  <ns7:notificationInfo><ns7:purchaseObjectsInfo>
   <ns7:notDrugPurchaseObjectsInfo>
    <ns4:purchaseObject>
     <ns4:OKPD2><ns2:OKPDCode>26.20.11.110</ns2:OKPDCode><ns2:OKPDName>Компьютеры портативные</ns2:OKPDName></ns4:OKPD2>
     <ns4:name>Ноутбук   с диагональю 15,6 дюйма</ns4:name>
    </ns4:purchaseObject>
    <ns4:purchaseObject>
     <ns4:KTRU><ns2:code>17.12.14.129-00000002</ns2:code><ns2:name>Бумага для офисной техники белая</ns2:name></ns4:KTRU>
    </ns4:purchaseObject>
    <ns4:purchaseObject><ns4:OKPD2><ns2:OKPDCode>31.01.12.160</ns2:OKPDCode></ns4:OKPD2></ns4:purchaseObject>
   </ns7:notDrugPurchaseObjectsInfo>
   <ns7:drugPurchaseObjectsInfo><ns4:drugPurchaseObjectInfo><ns4:MNNName>Парацетамол</ns4:MNNName>
   </ns4:drugPurchaseObjectInfo></ns7:drugPurchaseObjectsInfo>
  </ns7:purchaseObjectsInfo></ns7:notificationInfo>
 </ns7:epNotificationEF2020>
</ns5:export>""".encode("utf-8")


def test_notice_objects_parsed_without_namespaces():
    number, objs = purchase_objects(NOTICE)
    assert number == "0373100012326000101"
    assert objs == [("Ноутбук с диагональю 15,6 дюйма", "26.20.11.110"),          # пробелы схлопнуты
                    ("Бумага для офисной техники белая", "17.12.14.129")]        # КТРУ → код ОКПД2 до «-»
    # позиция без наименования и лекарство (МНН) не берутся


def test_sphere_by_okpd2_prefix():
    assert sphere("32.50.13.110") == "Медицина"
    assert sphere("26.20.11.110") == "ИТ"
    assert sphere("14.12.30.130") == "Одежда"
    assert sphere("10.71.11.110") == "Продукты"
    assert sphere("45.20.11.000") == "Прочее"


def row(name, code, sph="ИТ"):
    return [name, code, "https://zakupki.gov.ru/x", sph]


def test_select_drops_leaks_duplicates_and_respects_limits():
    known = {"26.20.11.110", "17.12.14.129"}
    guard = LeakGuard([tokens("Ноутбук Lenovo IdeaPad 15")])               # «обучение» / уже размеченные наборы
    rows = [row("Ноутбук Lenovo IdeaPad 15", "26.20.11.110"),              # утечка
            row("Монитор", "26.20.11.110"),                                # одно слово
            row("Ноутбук HP ProBook 450", "26.20.11.110"),
            row("ноутбук hp probook 450", "26.20.11.110"),                 # дубль после нормализации
            row("Ноутбук Acer Aspire 7", "26.20.11.110"),
            row("Ноутбук Dell Vostro 3520", "26.20.11.110"),               # третий на код — лимит 2
            row("Сервер стоечный 2U", "99.99.99.999"),                     # кода нет в справочнике
            row("Бумага офисная А4 белая", "17.12.14.129", "Канцелярия")]
    picked, why = select(rows, known, guard, per_sphere=10, max_per_code=2, rng=random.Random(1))
    names = {r[0] for r in picked}
    assert len([n for n in names if n.lower().startswith("ноутбук")]) == 2
    assert "Ноутбук Lenovo IdeaPad 15" not in names and "Монитор" not in names
    assert "Бумага офисная А4 белая" in names
    assert why["похоже на обучение или наборы оценки"] == 1 and why["кода нет в справочнике"] == 1
    assert why["короткое наименование"] == 1 and why["лимит на код"] + why["дубль в выгрузке"] == 2


def test_select_per_sphere_limit_and_split_share():
    known = {f"10.71.11.{i:03d}" for i in range(110, 130)}
    rows = [row(f"Хлеб пшеничный формовой {i}", f"10.71.11.{110 + i:03d}", "Продукты") for i in range(20)]
    picked, _ = select(rows, known, LeakGuard([]), per_sphere=10, max_per_code=2, rng=random.Random(1))
    assert len(picked) == 10
    dev, holdout = split(picked, 0.7)
    assert (len(dev), len(holdout)) == (7, 3)
    assert not {r[0] for r in dev} & {r[0] for r in holdout}


def test_labels_use_service_matcher():
    items = parse_npa(Path(get_settings().data_dir) / "npa" / "pp1875.json").items
    # 10.51.30.120 покрывается позицией ПП с кодом группы 10.51.30.100 (правило нулей в конце)
    r = labeled("Масло сливочное с наполнителем", "10.51.30.120", "Продукты", "u", items)
    assert r["regime_expected"] == "restriction" and "2:450" in r["appendix_item_expected"].split()
    assert labeled("Услуги такси", "49.32.11.000", "Прочее", "u", items)["regime_expected"] == "none"


def test_prepare_testset_refuses_to_reshuffle_holdout(tmp_path, monkeypatch):
    import prepare_testset

    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "holdout.csv").write_text("name\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["prepare_testset.py", "--data", str(tmp_path)])
    with pytest.raises(SystemExit, match="перемешает holdout"):
        prepare_testset.main()
