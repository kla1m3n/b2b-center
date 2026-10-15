import pytest

from app.classifier.retriever import retrieve


@pytest.mark.models
def test_retrieve_finds_laptop(seeded_session, embedder):
    cands = retrieve(seeded_session, embedder.encode_queries(["ноутбук lenovo"]), k=20)[0]
    assert len(cands) <= 20
    assert "26.20.11" in [c.code[:8] for c in cands]  # top-20 поиска; порядок исправляет реранкер


@pytest.mark.models
def test_retrieve_one_list_per_query_and_unique_codes(seeded_session, embedder):
    res = retrieve(seeded_session, embedder.encode_queries(["бумага а4", "стул офисный"]), k=5)
    assert len(res) == 2
    for cands in res:
        codes = [c.code for c in cands]
        assert len(codes) == len(set(codes))
        assert all(cands[i].score >= cands[i + 1].score for i in range(len(cands) - 1))
