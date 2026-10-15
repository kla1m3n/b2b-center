"""Поиск ближайших кодов ОКПД2 в pgvector."""
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Okpd2Code, Okpd2Text

OVERFETCH = 4  # у кода несколько текстов (наименование + синонимы) → берём с запасом


@dataclass
class Candidate:
    code: str
    title: str
    score: float
    matched_text: str


def retrieve(session: Session, query_vecs: np.ndarray, k: int) -> list[list[Candidate]]:
    session.execute(text("SET LOCAL hnsw.ef_search = 200"))
    out = []
    for vec in query_vecs:
        dist = Okpd2Text.embedding.cosine_distance(vec.tolist())
        rows = session.execute(
            select(Okpd2Text.code, Okpd2Text.text, Okpd2Code.title, (1 - dist).label("score"))
            .join(Okpd2Code, Okpd2Code.code == Okpd2Text.code)
            .order_by(dist)
            .limit(k * OVERFETCH)
        ).all()
        best: dict[str, Candidate] = {}
        for code, matched, title, score in rows:
            if code not in best:  # строки уже отсортированы по близости
                best[code] = Candidate(code=code, title=title, score=float(score), matched_text=matched)
        out.append(list(best.values())[:k])
    return out
