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
    with_items, without = pipeline.classify_many(["Ноутбук HP ProBook 450 G9", "asdf"])
    assert with_items.npa_matches and with_items.npa_source_url == "https://example.org/pp1875"
    assert without.npa_source_url == "https://example.org/pp1875"
    if not without.npa_matches:
        assert "не входит в приложения 1–3" in without.explanation
