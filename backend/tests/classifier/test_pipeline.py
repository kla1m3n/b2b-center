import shutil
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.models import ClassificationCache, NpaItem, NpaVersion
from app.npa.service import create_version, process_version
from app.schemas import Regime

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def npa_ready(seeded_session, tmp_path):
    s = seeded_session
    for t in (ClassificationCache, NpaItem, NpaVersion):
        s.execute(delete(t))
    s.commit()
    src = tmp_path / "npa.json"
    shutil.copy(FIXTURES / "npa_sample.json", src)
    v = create_version(s, src, "образец", "https://example.org/pp1875")
    process_version(s, v.id)
    yield s
    for t in (ClassificationCache, NpaItem, NpaVersion):
        s.execute(delete(t))
    s.commit()


@pytest.fixture
def pipeline(npa_ready, embedder):
    from app.classifier.pipeline import Pipeline
    from app.config import get_settings
    from app.db import SessionLocal

    p = Pipeline(get_settings(), SessionLocal, embedder=embedder)
    p.warmup()
    return p


@pytest.mark.models
def test_pipeline_order_duplicates_and_garbage(pipeline):
    res = pipeline.classify_many(["ноутбук lenovo", "", "asdf", "Ноутбук Lenovo"])
    assert len(res) == 4
    assert res[0].okpd2.code.startswith("26.20.11") and res[3].okpd2.code == res[0].okpd2.code
    assert res[0].input == "ноутбук lenovo" and res[3].input == "Ноутбук Lenovo"
    assert res[1].error and res[1].needs_review
    assert res[2].needs_review and res[2].confidence < 0.6


@pytest.mark.models
def test_pipeline_verdict_and_references(pipeline):
    r = pipeline.classify_many(["Ноутбук HP ProBook 450 G9"])[0]
    assert r.verdict == Regime.restriction
    assert [(m.appendix, m.item_no) for m in r.npa_matches] == [(2, "195"), (3, "37")]
    assert all(m.source_url == "https://example.org/pp1875" and m.item_id for m in r.npa_matches)
    assert 0 < r.confidence <= 1 and len(r.alternatives) <= 3
    assert r.explanation


@pytest.mark.models
def test_alternatives_have_regime_of_their_own_code(pipeline, npa_ready):
    """Режим и пункты ПП альтернативы — то, что matcher даёт по её коду; отличие от выбранного режима помечено."""
    from app.classifier.matcher import match, verdict
    from app.npa.service import get_active_version, get_items

    items = get_items(npa_ready, get_active_version(npa_ready).id)
    seen = set()
    for r in pipeline.classify_many(["Ноутбук HP ProBook 450 G9", "Монитор Samsung 27", "Бумага офисная А4", "Стол письменный"]):
        assert r.alternatives
        for a in r.alternatives:
            expected = match(a.code, items)
            assert a.verdict == verdict(expected)
            assert [(m.appendix, m.item_no) for m in a.npa_matches] == sorted((m.appendix, m.item_no) for m in expected) \
                or {(m.appendix, m.item_no) for m in a.npa_matches} == {(m.appendix, m.item_no) for m in expected}
            assert a.regime_differs == (a.verdict != r.verdict)
            assert all(m.source_url == "https://example.org/pp1875" for m in a.npa_matches)
            seen.add(a.regime_differs)
        # обоснование перечисляет каждую альтернативу с её режимом
        for a in r.alternatives:
            assert a.code in r.justification
    assert seen  # альтернативы были


@pytest.mark.models
def test_result_has_recommendation_justification_and_edition(pipeline):
    r = pipeline.classify_many(["Ноутбук HP ProBook 450 G9"])[0]
    assert r.npa_version == "образец" and r.matched_text
    assert "ограничение" in r.recommendation and "(прил. № 2, п. 195)" in r.recommendation
    assert "Наименование товара: Ноутбук HP ProBook 450 G9" in r.justification
    assert f"Код ОКПД2: {r.okpd2.code} — {r.okpd2.title}" in r.justification
    assert "приложение № 2, пункт 195" in r.justification and "https://example.org/pp1875" in r.justification
    assert f"Рекомендация: {r.recommendation}" in r.justification
    # из кэша — то же самое: рекомендация и обоснование строятся после кэша
    again = pipeline.classify_many(["ноутбук hp probook 450 g9"])[0]
    assert again.recommendation == r.recommendation and again.justification.count("Рекомендация:") == 1
    bad = pipeline.classify_many(["123"])[0]
    assert bad.error and "не распознано" in bad.recommendation and bad.justification == ""


def test_result_alternatives_regime_without_models():
    """_result: режим альтернатив берётся из переданных пунктов ПП, без ИИ и БД."""
    from app.classifier.pipeline import Pipeline
    from app.classifier.retriever import Candidate
    from app.config import get_settings
    from app.schemas import NpaMatch

    def m(appendix: int, no: str) -> NpaMatch:
        regime = {1: Regime.ban, 2: Regime.restriction, 3: Regime.advantage}[appendix]
        return NpaMatch(regime=regime, appendix=appendix, item_no=no, title="Позиция", matched_code="26.20")

    cands = [Candidate(code=c, title=t, score=s, matched_text=t) for c, t, s in (
        ("26.20.11.110", "Ноутбуки", 0.9), ("26.20.11.130", "Планшетные компьютеры", 0.8),
        ("26.20.13.000", "Машины вычислительные", 0.7), ("10.71.11.110", "Хлеб", 0.3))]
    res = Pipeline(get_settings(), None)._result(
        "ноутбук", cands, [m(2, "195"), m(3, "37")], [[m(2, "195")], [m(1, "27"), m(3, "40")], []])
    assert res["verdict"] == "restriction" and res["matched_text"] == "Ноутбуки"
    assert [(a["code"], a["verdict"], a["regime_differs"]) for a in res["alternatives"]] == [
        ("26.20.11.130", "restriction", False), ("26.20.13.000", "ban", True), ("10.71.11.110", "none", True)]
    assert [x["item_no"] for x in res["alternatives"][1]["npa_matches"]] == ["27", "40"]
    assert res["alternatives"][2]["npa_matches"] == []


@pytest.mark.models
def test_pipeline_uses_cache(pipeline, npa_ready):
    pipeline.classify_many(["бумага а4"])
    assert npa_ready.query(ClassificationCache).count() == 1
    pipeline.classify_many(["Бумага А4"])
    assert npa_ready.query(ClassificationCache).count() == 1


@pytest.mark.models
def test_best_code_is_top_retrieval_candidate_with_calibrated_confidence(pipeline, embedder, npa_ready):
    from app.classifier.confidence import calibrated
    from app.classifier.retriever import retrieve
    from app.config import get_settings

    cands = retrieve(npa_ready, embedder.encode_queries(["монитор samsung"]), k=20)[0]
    r = pipeline.classify_many(["Монитор Samsung"])[0]
    assert r.okpd2.code == cands[0].code
    expected = calibrated(cands[0].score, cands[1].score, get_settings().confidence_coef)
    assert abs(r.confidence - round(expected, 4)) < 1e-3


@pytest.mark.models
def test_needs_review_recomputed_for_cached_results(pipeline):
    first = pipeline.classify_many(["Ноутбук HP ProBook 450 G9"])[0]
    pipeline.s = pipeline.s.model_copy(update={"needs_review_threshold": 1.01})  # порог сменили после кэширования
    again = pipeline.classify_many(["Ноутбук HP ProBook 450 G9"])[0]  # этот ответ — из кэша
    assert again.confidence == first.confidence and again.needs_review



@pytest.mark.models
def test_every_result_links_to_npa_text(pipeline):
    # и у результата с пунктами, и у «не подпадает» (пунктов нет) — ссылка на текст редакции ПП
    with_items, without = pipeline.classify_many(["Ноутбук HP ProBook 450 G9", "Стул офисный"])  # стульев в образце ПП нет
    assert with_items.npa_matches and with_items.npa_source_url == "https://example.org/pp1875"
    assert without.npa_source_url == "https://example.org/pp1875"
    if not without.npa_matches:
        assert "не входит в приложения 1–3" in without.explanation


def _cands(*rows):
    from app.classifier.retriever import Candidate

    return [Candidate(code=c, title=t, score=s, matched_text=t) for c, t, s in rows]


def _bare_pipeline():
    from app.classifier.pipeline import Pipeline
    from app.config import get_settings

    return Pipeline(get_settings(), None)


# близость ~0,55 при калибровке любой модели проекта — уверенность заметно ниже порога 80%
LOW = (("16.21.13.000", "Плиты древесно-стружечные", 0.55), ("20.13.64.150", "Азиды", 0.545),
       ("10.71.11.110", "Хлеб", 0.54), ("31.01.11.150", "Стулья", 0.535))


def test_unrecognized_when_no_word_is_known_and_confidence_is_low():
    """«asdf», «привет»: ни одно слово не найдено в справочнике и уверенность низкая — не выдаём код и режим,
    иначе бессмыслица попадает в сводку как «Запрет»."""
    from app.classifier.pipeline import UNRECOGNIZED

    res = _bare_pipeline()._result("asdf", _cands(*LOW), [], [[], [], []], known_words=False)
    assert res["error"] == UNRECOGNIZED and res["okpd2"] is None
    assert res["verdict"] == "none" and res["alternatives"] == [] and res["npa_matches"] == []
    assert res["needs_review"] is True and 0 < res["confidence"] < 0.8


def test_known_word_keeps_result_even_with_low_confidence():
    res = _bare_pipeline()._result("плита", _cands(*LOW), [], [[], [], []], known_words=True)
    assert res["error"] is None and res["okpd2"]["code"] == "16.21.13.000" and res["needs_review"] is True


def test_unknown_words_but_confident_result_is_kept():
    # бренд или модель без слов справочника, но поиск по смыслу уверен — это не бессмыслица
    cands = _cands(("26.20.11.110", "Ноутбуки", 0.95), ("26.20.11.130", "Планшеты", 0.80))
    res = _bare_pipeline()._result("macbook", cands, [], [[]], known_words=False)
    assert res["error"] is None and res["needs_review"] is False


def test_alternatives_sorted_by_confidence():
    # после объединения поиска по смыслу и по словам порядок кандидатов не всегда по близости (67%, 59%, 60%)
    cands = _cands(("28.29.22.110", "Огнетушители", 0.95), ("20.59.52.130", "Составы", 0.90),
                   ("26.30.50.125", "Установки", 0.86), ("23.20.13.120", "Растворы", 0.88))
    res = _bare_pipeline()._result("огнетушитель", cands, [], [[], [], []])
    conf = [a["confidence"] for a in res["alternatives"]]
    assert conf == sorted(conf, reverse=True)
    assert [a["code"] for a in res["alternatives"]] == ["20.59.52.130", "23.20.13.120", "26.30.50.125"]


@pytest.mark.models
def test_garbage_is_unrecognized_end_to_end(pipeline):
    from app.classifier.pipeline import UNRECOGNIZED

    garbage, real = pipeline.classify_many(["asdf", "Ноутбук HP ProBook 450 G9"])
    assert garbage.error == UNRECOGNIZED and garbage.okpd2 is None and "не распознано" in garbage.recommendation
    assert real.error is None and real.okpd2 is not None


@pytest.mark.models
def test_with_code_recalculates_for_code_chosen_by_specialist(pipeline, npa_ready):
    """Выбор кода вручную: режим и пункты — по новому коду, прежний код уходит в альтернативы, пометка снята."""
    from app.classifier.matcher import match, verdict
    from app.npa.service import get_active_version, get_items

    items = get_items(npa_ready, get_active_version(npa_ready).id)
    base = pipeline.classify_many(["Ноутбук HP ProBook 450 G9"])[0]
    alt = base.alternatives[0]
    r = pipeline.with_code(base, alt.code)
    assert r.okpd2.code == alt.code and r.code_confirmed and not r.needs_review and r.auto_code == base.okpd2.code
    assert r.verdict == verdict(match(alt.code, items)) and r.confidence == alt.confidence
    assert {(m.appendix, m.item_no) for m in r.npa_matches} == {(m.appendix, m.item_no) for m in match(alt.code, items)}
    assert r.alternatives[0].code == base.okpd2.code and r.alternatives[0].verdict == base.verdict
    assert alt.code not in [a.code for a in r.alternatives]
    assert all(a.regime_differs == (a.verdict != r.verdict) for a in r.alternatives)
    assert "выбран специалистом вручную" in r.justification and base.okpd2.code in r.justification
    # код вне списка альтернатив и вне приложений ПП: режим «не подпадает»
    other = pipeline.with_code(base, "17.12.14.110") if npa_ready.get(__import__("app.models", fromlist=["Okpd2Code"]).Okpd2Code, "17.12.14.110") else None
    assert other is None or (other.code_confirmed and other.confidence == 0.0 and other.auto_code == base.okpd2.code)
    # подтверждение того же кода: результат прежний, только без пометки
    same = pipeline.with_code(base, base.okpd2.code)
    assert same.okpd2 == base.okpd2 and same.verdict == base.verdict and same.code_confirmed
    assert [a.code for a in same.alternatives] == [a.code for a in base.alternatives]
    assert "подтверждён специалистом" in same.justification
    # второй выбор подряд помнит исходный автоматический код
    assert pipeline.with_code(r, base.alternatives[-1].code).auto_code == base.okpd2.code
    with pytest.raises(ValueError, match="не найден в справочнике"):
        pipeline.with_code(base, "99.99.99.999")
    mixed = pipeline.classify_with_codes(["Ноутбук HP ProBook 450 G9", "Бумага офисная А4"], [alt.code, None])
    assert mixed[0].code_confirmed and mixed[0].okpd2.code == alt.code and not mixed[1].code_confirmed
