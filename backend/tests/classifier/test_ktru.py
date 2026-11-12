import sys
from pathlib import Path

from app.classifier.ktru import KtruNames
from app.classifier.normalize import normalize
from app.classifier.pipeline import Pipeline
from app.classifier.retriever import Candidate
from app.config import get_settings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from build_ktru_names import build  # noqa: E402

NAMES = KtruNames([("32.50.13.190", "Катетер уретральный для однократного дренирования"),
                   ("22.21.29.120", "Трубка дренажная нестерильная"),
                   ("25.71.13.110", "Нож канцелярский")])


def test_lookup_matches_normalized_name_only_exactly():
    assert NAMES.lookup(normalize("НОЖ канцелярский, 5 шт.")) == ("25.71.13.110", "Нож канцелярский")
    assert NAMES.lookup(normalize("Нож канцелярский 18 мм с фиксатором")) is None     # не дословно — решает поиск
    assert NAMES.lookup(normalize("Ножницы")) is None


def test_lookup_with_medical_mark():
    q = normalize("Катетер уретральный для однократного дренирования (является медицинским изделием)")
    assert NAMES.lookup(q)[0] == "32.50.13.190"
    # заказчик пометил медизделием, а в КТРУ позиция в трубах пластмассовых — каталог и заказчик расходятся
    assert NAMES.lookup(normalize("Трубка дренажная нестерильная (является медицинским изделием)")) is None
    assert NAMES.lookup(normalize("Трубка дренажная нестерильная"))[0] == "22.21.29.120"


def test_build_skips_ambiguous_names_and_unknown_codes():
    rows = [{"text": "Папка  пластиковая", "ktru_code": "22.29.25.000-00000001"},
            {"text": "Папка пластиковая", "ktru_code": "22.29.25.000-00000002"},      # тот же код — одна строка
            {"text": "Очки", "ktru_code": "26.20.16.190-00000001"},
            {"text": "Очки", "ktru_code": "32.50.42.190-00000001"},                   # два кода — пропуск
            {"text": "Услуга", "ktru_code": "99.99.99.999-00000001"},                 # кода нет в справочнике
            {"text": "Старый код", "ktru_code": "01.11"}]
    out, ambiguous = build(rows, {"22.29.25.000", "26.20.16.190", "32.50.42.190"})
    assert out == [("22.29.25.000", "Папка пластиковая")] and ambiguous == 1


def test_ktru_code_goes_first_and_is_explained():
    p = Pipeline(get_settings(), None)
    p._ktru = NAMES
    wrong = Candidate(code="25.71.11.110", title="Ножи (кроме ножей для машин)", score=0.7, matched_text="нож")
    right = Candidate(code="25.71.13.110", title="Изделия ножевые прочие", score=0.6, matched_text="Изделия ножевые прочие")
    cands = p._ktru_first(None, normalize("Нож канцелярский"), [wrong, right])
    assert [c.code for c in cands] == ["25.71.13.110", "25.71.11.110"] and cands[0].exact and cands[0].score == 1.0
    res = p._result("нож канцелярский", cands, [], [[]])
    assert res["okpd2"]["code"] == "25.71.13.110" and "позицией КТРУ «Нож канцелярский»" in res["explanation"]
    assert not res["needs_review"]
    assert p._ktru_first(None, "ножницы", [wrong, right]) == [wrong, right]            # нет в КТРУ — порядок прежний
