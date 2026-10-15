import csv
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.config import get_settings
from app.models import Okpd2Code, Okpd2Text

DATA = Path(get_settings().data_dir)
# Небольшой срез ОКПД2: ноутбуки и «соседи», чтобы поиск было из чего выбирать.
SAMPLE_PREFIXES = ("26.20.1", "26.20.2", "17.12.1", "31.01.1", "22.29.2", "26.40.2")


@pytest.fixture(scope="session")
def embedder():
    from app.classifier.embedder import Embedder

    s = get_settings()
    return Embedder(s.embed_model, s.device)


@pytest.fixture
def seeded_session(session, embedder):
    from app.seed import okpd2_texts

    with (DATA / "okpd2.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter=";") if r["code"].startswith(SAMPLE_PREFIXES)]
    session.execute(delete(Okpd2Text))
    session.execute(delete(Okpd2Code))
    codes = [Okpd2Code(code=r["code"], title=r["title"], parent_code=r["parent_code"] or None,
                       is_leaf=r["is_leaf"] == "1") for r in rows]
    session.add_all(codes)
    session.flush()
    texts = okpd2_texts(codes, synonyms=[])
    vecs = embedder.encode_passages([t[1] for t in texts])
    session.add_all(Okpd2Text(code=c, text=t, kind=k, embedding=v) for (c, t, k), v in zip(texts, vecs))
    session.commit()
    yield session
    session.execute(delete(Okpd2Text))
    session.execute(delete(Okpd2Code))
    session.commit()
