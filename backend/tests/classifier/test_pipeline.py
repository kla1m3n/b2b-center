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
