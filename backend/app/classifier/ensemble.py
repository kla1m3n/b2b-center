"""Ансамбль двух моделей эмбеддингов: сходство запроса с текстом ОКПД2 — взвешенное среднее сходств по обеим моделям.

Основная модель (EMBED_MODEL, векторы в pgvector) и вторая (ENSEMBLE_MODEL, обычно исходная e5-large без дообучения).
Текстов ~16 тыс., поэтому поиск — полным перебором в памяти (две матрицы 16k × 1024, float16), без второго
HNSW-индекса в БД. Векторы второй модели — из data/index/<модель>.npz; тексты, которых там нет (новые синонимы),
досчитываются при старте.
"""
import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classifier.embedder import Embedder
from app.classifier.retriever import TIE_EPS, Candidate
from app.models import Okpd2Code, Okpd2Text

log = logging.getLogger(__name__)


class EnsembleIndex:
    def __init__(self, codes: list[str], texts: list[str], kinds: list[str], titles: dict[str, str],
                 main: np.ndarray, second: np.ndarray, weight: float, embedder: Embedder | None = None):
        """codes/texts/kinds — тексты поиска (коды нижнего уровня), main/second — их векторы по двум моделям."""
        self.texts, self.titles, self.w, self.embedder = texts, titles, weight, embedder
        self.main, self.second = main.astype(np.float16), second.astype(np.float16)
        self.codes = np.array(codes)
        self._ucodes, self._code_of = np.unique(self.codes, return_inverse=True)  # номер кода у каждого текста
        self._official = {c: i for i, (c, k) in reversed(list(enumerate(zip(codes, kinds)))) if k == "official"}

    @classmethod
    def load(cls, session: Session, model_name: str, index: Path, weight: float) -> "EnsembleIndex":
        q = session.execute(
            select(Okpd2Text.code, Okpd2Text.text, Okpd2Text.kind, Okpd2Text.embedding, Okpd2Code.title)
            .join(Okpd2Code, Okpd2Code.code == Okpd2Text.code)
            .where(Okpd2Code.is_leaf.is_(True))
            .order_by(Okpd2Text.code, Okpd2Text.id)
        ).all()
        codes, texts = [r[0] for r in q], [r[1] for r in q]
        main = np.stack([np.asarray(r[3], dtype=np.float32) for r in q])
        embedder = Embedder(model_name, backend="onnx", onnx_file="")
        known = {}
        if index.exists():
            z = np.load(index, allow_pickle=False)
            known = dict(zip(zip(z["codes"].tolist(), z["texts"].tolist()), z["vectors"]))
        second = np.zeros_like(main)
        missing = [i for i, key in enumerate(zip(codes, texts)) if key not in known]
        for i, key in enumerate(zip(codes, texts)):
            if key in known:
                second[i] = known[key]
        if missing:
            log.info("Ансамбль: векторов второй модели нет для %d текстов — считаю", len(missing))
            second[missing] = embedder.encode_passages([texts[i] for i in missing])
        log.info("Ансамбль: %s, вес %.2f, текстов %d", model_name, weight, len(texts))
        return cls(codes, texts, [r[2] for r in q], {r[0]: r[4] for r in q}, main, second, weight, embedder)

    def scores(self, qmain: np.ndarray, qsecond: np.ndarray) -> np.ndarray:
        """Сходство запроса с каждым текстом: (1 − w) · основная модель + w · вторая."""
        return ((1 - self.w) * (self.main @ qmain.astype(np.float16)).astype(np.float32)
                + self.w * (self.second @ qsecond.astype(np.float16)).astype(np.float32))

    def _best_text(self, sc: np.ndarray) -> np.ndarray:
        """Номер лучшего текста каждого кода (в порядке self._ucodes)."""
        order = np.lexsort((-sc, self._code_of))  # по коду, внутри — по убыванию сходства
        first = np.r_[True, self._code_of[order][1:] != self._code_of[order][:-1]]
        return order[first]

    def _cand(self, sc: np.ndarray, i: int) -> Candidate:
        code = str(self.codes[i])
        return Candidate(code=code, title=self.titles[code], score=float(sc[i]), matched_text=self.texts[i])

    def search(self, qmain: np.ndarray, qsecond: np.ndarray, k: int) -> tuple[list[Candidate], Callable[[str], Candidate | None]]:
        """Топ-k кодов и функция «код → кандидат» (для кодов, найденных только поиском по словам)."""
        sc = self.scores(qmain, qsecond)
        best = self._best_text(sc)
        top = best[np.argsort(-sc[best], kind="stable")[: k * 2]]
        cands = [self._cand(sc, int(i)) for i in top]
        # равные оценки (общий синоним у разных кодов) — по близости к официальному наименованию, затем по коду
        title_sim = {c.code: float(sc[self._official[c.code]]) if c.code in self._official else 0.0 for c in cands}
        cands.sort(key=lambda c: (-round(c.score / TIE_EPS), -title_sim[c.code], c.code))

        def lookup(code: str) -> Candidate | None:
            j = int(np.searchsorted(self._ucodes, code))
            return self._cand(sc, int(best[j])) if j < len(self._ucodes) and self._ucodes[j] == code else None

        return cands[:k], lookup
