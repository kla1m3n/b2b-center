from app.models import Okpd2Code
from app.seed import okpd2_texts


def code(c, title, parent=None, leaf=True):
    return Okpd2Code(code=c, title=title, parent_code=parent, is_leaf=leaf)


def test_texts_are_plain_titles_of_leaf_codes_plus_synonyms():
    codes = [
        code("31.09", "Мебель прочая", leaf=False),
        code("31.09.13.190", "Мебель деревянная прочая, не включенная в другие группировки", "31.09"),
        code("26.20.11.110", "Ноутбуки"),
    ]
    texts = okpd2_texts(codes, synonyms=[("26.20.11.110", "лэптоп"), ("31.09", "мебель"), ("99.99", "нет такого")])
    assert texts == [
        ("31.09.13.190", "Мебель деревянная прочая, не включенная в другие группировки", "official"),
        ("26.20.11.110", "Ноутбуки", "official"),
        ("26.20.11.110", "лэптоп", "synonym"),
    ]


def test_reindex_replaces_search_texts_and_clears_cache(session, tmp_path, monkeypatch):
    import numpy as np
    from sqlalchemy import delete, text

    from app.config import get_settings
    from app.models import ClassificationCache, Okpd2Text
    from app.seed import model_slug, run

    dim = get_settings().embed_dim
    session.execute(delete(Okpd2Text))
    session.execute(delete(ClassificationCache))
    session.execute(delete(Okpd2Code))
    session.add(Okpd2Code(code="26.20.11.110", title="Ноутбуки", is_leaf=True))
    session.add(ClassificationCache(norm_name="ноутбук", npa_version=0, result={}))
    session.commit()
    (tmp_path / "index").mkdir()
    np.savez_compressed(tmp_path / "index" / f"{model_slug(get_settings().embed_model)}.npz",
                        codes=np.array(["26.20.11.110", "26.20.11.110"]), texts=np.array(["Ноутбуки", "лэптоп"]),
                        kinds=np.array(["official", "synonym"]), vectors=np.ones((2, dim), dtype=np.float16))
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    session.add(Okpd2Text(code="26.20.11.110", text="устаревший текст", kind="official", embedding=[0.0] * dim))
    session.commit()

    run(session, reindex=True)

    texts = sorted(t.text for t in session.query(Okpd2Text))
    assert texts == ["Ноутбуки", "лэптоп"]
    assert session.query(ClassificationCache).count() == 0
    session.execute(text("SELECT 1"))



def test_run_always_clears_answer_cache(session):
    # кэш переживает перезапуск, а код/калибровка могли поменяться — при запуске он сбрасывается
    from sqlalchemy import func, select
    from sqlalchemy.dialects.postgresql import insert

    from app.models import ClassificationCache
    from app.seed import run

    session.execute(insert(ClassificationCache).values(norm_name="старый ответ", npa_version=0, result={})
                    .on_conflict_do_nothing())
    session.commit()
    run(session)
    assert session.scalar(select(func.count()).select_from(ClassificationCache)) == 0
