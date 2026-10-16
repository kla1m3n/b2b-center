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
