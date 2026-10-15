"""Идемпотентная первичная загрузка: ОКПД2, тексты для поиска с эмбеддингами, базовая редакция ПП.

Запуск: python -m app.seed [--reindex]
"""
import csv
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, engine, init_db
from app.models import ClassificationCache, Okpd2Code, Okpd2Text
from app.npa.service import create_version, get_active_version, process_version

log = logging.getLogger("seed")
SEED_LOCK = 1875


def model_slug(model_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")


def okpd2_texts(codes: Sequence[Okpd2Code], synonyms: Sequence[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Тексты для поиска: (code, text, kind) — официальные наименования кодов нижнего уровня и синонимы к ним.

    Дописывание наименований родительских групп ухудшало поиск (reports/models.md), поэтому только чистые названия.
    """
    leaf = {c.code for c in codes if c.is_leaf}
    out = [(c.code, c.title, "official") for c in codes if c.code in leaf]
    out += [(code, s, "synonym") for code, s in synonyms if code in leaf]
    return out


def read_synonyms(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [(r["code"].strip(), r["text"].strip()) for r in csv.DictReader(f, delimiter=";") if r["text"].strip()]


def _load_okpd2(session: Session, data: Path) -> None:
    with (data / "okpd2.csv").open(encoding="utf-8") as f:
        rows = [{"code": r["code"], "title": r["title"], "parent_code": r["parent_code"] or None,
                 "is_leaf": r["is_leaf"] == "1"} for r in csv.DictReader(f, delimiter=";")]
    session.execute(insert(Okpd2Code), rows)
    session.commit()
    log.info("ОКПД2: загружено %d кодов", len(rows))


def _load_texts(session: Session, data: Path) -> None:
    s = get_settings()
    index = data / "index" / f"{model_slug(s.embed_model)}.npz"
    if index.exists():
        z = np.load(index, allow_pickle=False)
        texts = list(zip(z["codes"].tolist(), z["texts"].tolist(), z["kinds"].tolist()))
        vecs = z["vectors"].astype(np.float32)
        log.info("Индекс загружен из %s (%d текстов)", index.name, len(texts))
    else:
        from app.classifier.embedder import Embedder

        codes = list(session.scalars(select(Okpd2Code)))
        texts = okpd2_texts(codes, read_synonyms(data / "okpd2_synonyms.csv"))
        log.info("Индекса нет — считаю эмбеддинги для %d текстов (несколько минут)", len(texts))
        vecs = Embedder(s.embed_model, s.device).encode_passages([t[1] for t in texts])
    known = set(session.scalars(select(Okpd2Code.code)))
    rows = [{"code": c, "text": t, "kind": k, "embedding": v}
            for (c, t, k), v in zip(texts, vecs) if c in known]
    for i in range(0, len(rows), 2000):
        session.execute(insert(Okpd2Text), rows[i:i + 2000])
    session.execute(text(
        "CREATE INDEX IF NOT EXISTS okpd2_text_embedding_hnsw ON okpd2_text "
        "USING hnsw (embedding vector_cosine_ops)"))
    session.commit()
    log.info("Тексты для поиска: %d", len(rows))


def _load_npa(session: Session, data: Path) -> None:
    path = data / "npa" / "pp1875.json"
    v = create_version(session, path, "", "")
    process_version(session, v.id)
    session.refresh(v)
    log.info("ПП 1875: версия %s, статус %s", v.title, v.status)


def run(session: Session, reindex: bool = False) -> None:
    """reindex=True — заново загрузить тексты поиска (после правки синонимов или смены индекса) и сбросить кэш."""
    data = Path(get_settings().data_dir)
    session.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SEED_LOCK})
    try:
        if reindex:
            session.execute(delete(Okpd2Text))
            session.execute(delete(ClassificationCache))
            session.commit()
        if not session.scalar(select(func.count()).select_from(Okpd2Code)):
            _load_okpd2(session, data)
        if not session.scalar(select(func.count()).select_from(Okpd2Text)):
            _load_texts(session, data)
        if get_active_version(session) is None:
            _load_npa(session, data)
    finally:
        session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SEED_LOCK})
        session.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    init_db()
    with SessionLocal() as s:
        run(s, reindex="--reindex" in sys.argv)
    engine.dispose()
