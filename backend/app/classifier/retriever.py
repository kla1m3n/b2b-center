"""Поиск ближайших кодов ОКПД2 в pgvector."""
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Okpd2Code, Okpd2Text

OVERFETCH = 10  # у кода несколько текстов (наименование + синонимы + формулировки doc2query) → берём с запасом
TIE_EPS = 1e-6  # одинаковые тексты у разных кодов (общий синоним «папка») дают одинаковую оценку до последнего знака


@dataclass
class Candidate:
    code: str
    title: str
    score: float
    matched_text: str


def _break_ties(session: Session, vec: list[float], cands: list[Candidate]) -> list[Candidate]:
    """Коды с одинаковой оценкой — по близости запроса к официальному наименованию кода, затем по коду.
    Без этого победителя выбирал порядок строк в БД, и после нового seed ответ мог смениться."""
    tied = {c.code for a, b in zip(cands, cands[1:]) if a.score - b.score < TIE_EPS for c in (a, b)}
    if not tied:
        return cands
    dist = Okpd2Text.embedding.cosine_distance(vec)
    title_sim = dict(session.execute(
        select(Okpd2Text.code, func.max(1 - dist))
        .where(Okpd2Text.code.in_(tied), Okpd2Text.kind == "official")
        .group_by(Okpd2Text.code)
    ).all())
    group, prev = 0, None  # группы равных оценок; порядок групп — как пришёл из поиска
    keys = {}
    for c in cands:
        if prev is not None and prev - c.score >= TIE_EPS:
            group += 1
        keys[c.code], prev = (group, -float(title_sim.get(c.code, 0.0)), c.code), c.score
    return sorted(cands, key=lambda c: keys[c.code])


def retrieve(session: Session, query_vecs: np.ndarray, k: int) -> list[list[Candidate]]:
    session.execute(text("SET LOCAL hnsw.ef_search = 200"))
    out = []
    for vec in query_vecs:
        dist = Okpd2Text.embedding.cosine_distance(vec.tolist())
        rows = session.execute(
            select(Okpd2Text.code, Okpd2Text.text, Okpd2Code.title, (1 - dist).label("score"))
            .join(Okpd2Code, Okpd2Code.code == Okpd2Text.code)
            .where(Okpd2Code.is_leaf.is_(True))  # в закупках указывают коды нижнего уровня
            .order_by(dist, Okpd2Text.code, Okpd2Text.id)  # при равной близости порядок не должен зависеть от БД
            .limit(k * OVERFETCH)
        ).all()
        best: dict[str, Candidate] = {}
        for code, matched, title, score in rows:
            if code not in best:  # строки уже отсортированы по близости
                best[code] = Candidate(code=code, title=title, score=float(score), matched_text=matched)
        out.append(_break_ties(session, vec.tolist(), list(best.values()))[:k])
    return out
