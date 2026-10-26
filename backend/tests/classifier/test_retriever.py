import pytest

from app.classifier.retriever import retrieve
from app.config import get_settings


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


def test_ties_broken_by_official_title_then_code(session):
    from app.classifier.retriever import Candidate, _break_ties
    from app.models import Okpd2Code, Okpd2Text

    q = [1.0] + [0.0] * (get_settings().embed_dim - 1)
    near = [0.9, 0.1] + [0.0] * (get_settings().embed_dim - 2)   # официальное наименование ближе к запросу
    far = [0.1, 0.9] + [0.0] * (get_settings().embed_dim - 2)
    session.add_all([Okpd2Code(code=c, title=c, is_leaf=True) for c in ("99.99.99.110", "99.99.99.120", "99.99.99.130")])
    session.flush()
    session.add_all([Okpd2Text(code="99.99.99.110", text="a", kind="official", embedding=far),
                     Okpd2Text(code="99.99.99.120", text="b", kind="official", embedding=near),
                     Okpd2Text(code="99.99.99.130", text="c", kind="official", embedding=far)])
    session.flush()
    cands = [Candidate("99.99.99.110", "", 0.9, "папка"), Candidate("99.99.99.130", "", 0.9, "папка"),
             Candidate("99.99.99.120", "", 0.9, "папка"), Candidate("99.99.99.111", "", 0.5, "x")]
    got = [c.code for c in _break_ties(session, q, cands)]
    # ничья из трёх: ближе всех по наименованию .120; у .110 и .130 наименования одинаково далеки — по коду
    assert got == ["99.99.99.120", "99.99.99.110", "99.99.99.130", "99.99.99.111"]
    assert _break_ties(session, q, cands[2:]) == cands[2:]  # без ничьих порядок не меняется


@pytest.mark.models
def test_retrieve_returns_only_leaf_codes(seeded_session, embedder):
    from app.models import Okpd2Code

    leaf = {c.code for c in seeded_session.query(Okpd2Code).filter_by(is_leaf=True)}
    cands = retrieve(seeded_session, embedder.encode_queries(["компьютеры"]), k=20)[0]
    assert cands and all(c.code in leaf for c in cands)
