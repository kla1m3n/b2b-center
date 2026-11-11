"""Рекомендации, текст обоснования и сводка по списку (app/report.py) — без моделей и БД."""
from app.report import finalize, items_ref, justification, main_items, recommendation, review_items, short, summarize
from app.schemas import Alternative, ClassificationResult, NpaMatch, Okpd2Ref, Regime

URL = "https://example.org/pp1875"


def npa(appendix: int, item_no: str, title: str = "Позиция", quota: int | None = None, cond: bool = False,
        note: str = "") -> NpaMatch:
    regime = {1: Regime.ban, 2: Regime.restriction, 3: Regime.advantage}[appendix]
    return NpaMatch(regime=regime, appendix=appendix, item_no=item_no, title=title, matched_code="26.20.11",
                    quota=quota, has_conditions=cond, note=note, source_url=URL)


def result(verdict: Regime, matches=(), conf: float = 0.93, review: bool = False, alternatives=(), **kw) -> ClassificationResult:
    return finalize(ClassificationResult(
        input=kw.pop("input", "Ноутбук Lenovo IdeaPad 15"), okpd2=Okpd2Ref(code="26.20.11.110", title="Ноутбуки"),
        matched_text=kw.pop("matched_text", "ноутбук lenovo hp asus acer"), confidence=conf, needs_review=review,
        npa_matches=list(matches), verdict=verdict, alternatives=list(alternatives), npa_source_url=URL,
        npa_version="ПП РФ № 1875 (ред. на 30.09.2026)", **kw))


def test_recommendation_ban_names_item_and_russian_analog():
    r = result(Regime.ban, [npa(1, "10", "Бумага и картон"), npa(3, "13", "Бумага и картон", quota=90)])
    assert "запрещена (прил. № 1, п. 10)" in r.recommendation
    assert "российского происхождения" in r.recommendation and "обоснование невозможности" in r.recommendation
    assert "также входит в прил. № 3 (п. 13)" in r.recommendation and "90%" in r.recommendation


def test_recommendation_restriction_and_quota():
    r = result(Regime.restriction, [npa(2, "195"), npa(3, "37", quota=80)])
    assert "ограничение" in r.recommendation and "(прил. № 2, п. 195)" in r.recommendation
    assert "заявка с иностранным товаром отклоняется" in r.recommendation
    assert "минимальная обязательная доля" in r.recommendation and "80%" in r.recommendation


def test_recommendation_advantage_is_minimum_share_without_ban():
    r = result(Regime.advantage, [npa(3, "143", "Лифты", quota=90)])
    assert r.recommendation.startswith("Запрета и ограничения нет")
    assert "входит в прил. № 3 (п. 143)" in r.recommendation and "также" not in r.recommendation
    assert "223-ФЗ" in r.recommendation and "90%" in r.recommendation


def test_recommendation_none():
    r = result(Regime.none)
    assert "не входит в приложения № 1–3" in r.recommendation and "на общих основаниях" in r.recommendation


def test_recommendation_needs_review_warns_about_other_regime():
    alt = Alternative(code="26.20.13.000", title="Машины вычислительные", confidence=0.4, verdict=Regime.ban,
                      npa_matches=[npa(1, "27")], regime_differs=True)
    r = result(Regime.restriction, [npa(2, "195")], conf=0.6123, review=True, alternatives=[alt])
    assert r.recommendation.startswith("Сначала подтвердите код ОКПД2 вручную: уверенность 61%.")
    assert "При коде 26.20.13.000 режим будет другим — «запрет»." in r.recommendation
    # основной текст по режиму выбранного кода остаётся
    assert "ограничение" in r.recommendation


def test_recommendation_confident_result_does_not_mention_alternatives():
    alt = Alternative(code="26.20.13.000", title="Машины", confidence=0.1, verdict=Regime.ban, regime_differs=True)
    r = result(Regime.restriction, [npa(2, "195")], alternatives=[alt])
    assert "Сначала подтвердите" not in r.recommendation and "26.20.13.000" not in r.recommendation


def test_recommendation_conditions_and_error():
    r = result(Regime.restriction, [npa(2, "300", cond=True)])
    assert "дополнительные условия" in r.recommendation
    err = finalize(ClassificationResult(input="123", error="Пустое или нераспознанное наименование"))
    assert "не распознано" in err.recommendation and err.justification == ""


def test_justification_has_everything_the_task_asks_for():
    alt = Alternative(code="26.20.11.130", title="Планшетные компьютеры", confidence=0.0512, verdict=Regime.restriction,
                      npa_matches=[npa(2, "195")])
    other = Alternative(code="26.40.20.110", title="Телевизоры", confidence=0.02, verdict=Regime.none, regime_differs=True)
    r = result(Regime.restriction, [npa(2, "195", "Компьютеры портативные"), npa(3, "37", "Компьютеры портативные", quota=80)],
               conf=0.8849, alternatives=[alt, other])
    text = r.justification
    assert "Наименование товара: Ноутбук Lenovo IdeaPad 15" in text
    assert "Код ОКПД2: 26.20.11.110 — Ноутбуки" in text  # код и официальное название
    assert "совпало с формулировкой «ноутбук lenovo hp asus acer»" in text  # совпавший фрагмент
    assert "Режим по ПП № 1875: ограничение." in text
    assert "приложение № 2, пункт 195 (ограничение): «Компьютеры портативные», код 26.20.11" in text
    assert "приложение № 3, пункт 37 (минимальная доля)" in text and "минимальная доля 80%" in text
    assert f"Источник: ПП РФ № 1875 (ред. на 30.09.2026) {URL}" in text  # ссылка
    assert "Уверенность классификации: 88%." in text
    assert "26.20.11.130 — Планшетные компьютеры: ограничение (прил. № 2, п. 195), уверенность 5%" in text
    assert "26.40.20.110 — Телевизоры: не подпадает (не входит в прил. № 1–3), уверенность 2%; режим отличается" in text
    assert f"Рекомендация: {r.recommendation}" in text


def test_justification_official_title_match_and_no_items():
    r = result(Regime.none, matched_text="Ноутбуки", conf=0.5, review=True)
    assert "соответствует официальному наименованию кода" in r.justification
    assert "Основание: код не входит в приложения № 1–3 постановления." in r.justification
    assert "Уверенность классификации: 50% — ниже порога, код требуется подтвердить вручную." in r.justification


def test_summary_counts_shares_review_and_lowest_confidence():
    results = [
        result(Regime.ban, [npa(1, "10")], conf=0.95, input="Бумага"),
        result(Regime.restriction, [npa(2, "195")], conf=0.9, input="Ноутбук"),
        result(Regime.restriction, [npa(2, "199")], conf=0.55, review=True, input="Компьютер"),
        result(Regime.advantage, [npa(3, "143")], conf=0.86, input="Лифт"),
        result(Regime.none, conf=0.3, review=True, input="Штука"),
        result(Regime.none, conf=0.99, input="Хлеб"),
        finalize(ClassificationResult(input="123", error="Пустое или нераспознанное наименование")),
        result(Regime.none, conf=0.91, input="Батон"),
    ]
    s = summarize(results)
    assert s.total == 8 and s.errors == 1
    assert [(x.regime, x.count, x.share) for x in s.by_regime] == [
        (Regime.ban, 1, 0.125), (Regime.restriction, 2, 0.25), (Regime.advantage, 1, 0.125), (Regime.none, 3, 0.375)]
    assert [x.label for x in s.by_regime] == ["Запрет", "Ограничение", "Минимальная доля", "Не подпадает"]
    assert s.needs_review == 2 and s.needs_review_share == 0.25
    # наименьшая уверенность — по возрастанию, с номером позиции в списке; нераспознанные сюда не входят
    assert [(x.idx, x.input) for x in s.lowest_confidence] == [(5, "Штука"), (3, "Компьютер"), (4, "Лифт"), (2, "Ноутбук"), (8, "Батон")]
    # ручная проверка: сначала нераспознанное, затем по росту уверенности
    assert [i for i, _ in review_items(results)] == [7, 5, 3]


def test_summary_of_empty_list():
    s = summarize([])
    assert s.total == 0 and s.needs_review_share == 0 and s.lowest_confidence == []
    assert all(x.count == 0 and x.share == 0 for x in s.by_regime)


def test_plain_helpers_do_not_change_result():
    r = result(Regime.restriction, [npa(2, "195")])
    assert recommendation(r) == r.recommendation and justification(r) == r.justification


def test_wide_codes_list_main_items_only():
    """У медизделий на код приходятся десятки пунктов: в тексте — главные, первый пункт каждого приложения обязательно."""
    matches = [npa(2, str(300 + i), "Изделие " + "медицинское " * 40) for i in range(14)] + [npa(3, "37", quota=80)]
    shown, hidden = main_items(matches)
    assert [m.item_no for m in shown] == ["300", "301", "302", "303", "37"] and hidden == 10
    assert main_items(matches[:3]) == (matches[:3], 0)
    assert items_ref(matches) == "прил. № 2, п. 300; прил. № 2, п. 301; прил. № 3, п. 37 (мин. доля 80%) и ещё 12 пунктов"
    r = result(Regime.restriction, matches)
    assert r.justification.count("приложение № 2, пункт") == 4 and "приложение № 3, пункт 37" in r.justification
    assert "остальные пункты, распространяющиеся на этот код (10)" in r.justification
    items = [line for line in r.justification.splitlines() if line.startswith("  — приложение")]
    assert max(len(line) for line in items) < 300  # длинные наименования позиций сокращены
    assert short("слово " * 100).endswith("…") and len(short("слово " * 100)) <= 201 and short("коротко") == "коротко"


def test_appendix3_is_named_minimum_share_not_advantage():
    """Прил. № 3 ПП 1875 — перечень товаров с минимальной обязательной долей закупок российских товаров (п. 2,
    подп. «л» п. 4: закупки по 223-ФЗ). «Преимущество» — другая мера постановления, подписывать так прил. № 3 нельзя."""
    from app import report
    from app.schemas import REGIME_LABELS

    assert REGIME_LABELS[Regime.advantage] == "МИН. ДОЛЯ"
    assert report.REGIME_NAMES[Regime.advantage] == "Минимальная доля"


# Примечания ПП № 1428 (data/npa/pp1875.json): позиции прил. 2, которые переходят в запрет
FURNITURE = ("Внимание: с 01.07.2027 — запрет (прил. 1, поз. 136(1)), позиция исключается из прил. 2 "
             "(ПП от 30.10.2026 N 1428)")
BATTERIES = ("Внимание: для закупок с извещениями с 01.01.2027 — запрет (прил. 1, поз. 31(1-1)), позиция исключается "
             "из прил. 2 (ПП от 30.10.2026 N 1428)")


def test_upcoming_change_is_in_justification_and_recommendation():
    """Специалист копирует обоснование в документацию: о будущем запрете он должен узнать из текста, а не только
    из подробностей на сайте."""
    r = result(Regime.restriction, [npa(2, "139", "Мебель", note=FURNITURE), npa(3, "232", quota=50)])
    lines = r.justification.splitlines()
    warn = [x for x in lines if x.startswith("Внимание")]
    assert warn == ["Внимание, предстоящее изменение (прил. № 2, п. 139): с 01.07.2027 — запрет (прил. 1, поз. 136(1)), "
                    "позиция исключается из прил. 2 (ПП от 30.10.2026 N 1428)."]
    # строка — сразу после пунктов постановления, до источника
    assert lines.index(warn[0]) < next(i for i, x in enumerate(lines) if x.startswith("Источник:"))
    assert ("Для извещений, размещаемых с 01.07.2027, режим изменится на «запрет» (прил. 1, поз. 136(1)): "
            "проверьте дату извещения.") in r.recommendation
    assert "ограничение закупок иностранных товаров (прил. № 2, п. 139)" in r.recommendation  # текущий режим — прежний


def test_upcoming_change_wording_for_notice_date():
    r = result(Regime.restriction, [npa(2, "190", "Аккумуляторы", note=BATTERIES)])
    assert "Для извещений, размещаемых с 01.01.2027, режим изменится на «запрет» (прил. 1, поз. 31(1-1))"         in r.recommendation
    assert "Внимание, предстоящее изменение (прил. № 2, п. 190): для закупок с извещениями с 01.01.2027" in r.justification


def test_ordinary_notes_are_not_warnings():
    # история редакций и условия применения — не предупреждения: в тексте их нет
    notes = ["(в ред. Постановления Правительства РФ от 13.07.2026 N 881)",
             "введена Постановлением Правительства РФ от 25.09.2026 N 1236 Применяется с 01.10.2026"]
    r = result(Regime.restriction, [npa(2, "195", note=notes[0]), npa(3, "37", quota=80, note=notes[1])])
    assert "Внимание" not in r.justification and "режим изменится" not in r.recommendation


def test_warning_without_recognizable_date_still_shown():
    r = result(Regime.restriction, [npa(2, "195", note="Внимание: позиция будет изменена")])
    assert "Внимание, предстоящее изменение (прил. № 2, п. 195): позиция будет изменена." in r.justification
    assert "У пункта (прил. № 2, п. 195) есть предстоящее изменение — сверьте с текстом ПП." in r.recommendation
