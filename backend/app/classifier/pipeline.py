"""Конвейер классификации: нормализация → поиск → переранжирование → сверка с ПП → результат."""
import math
import re
import threading
from collections.abc import Callable

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.classifier.confidence import to_confidence
from app.classifier.embedder import Embedder
from app.classifier.matcher import match, verdict
from app.classifier.normalize import normalize
from app.classifier.reranker import Reranker
from app.classifier.retriever import Candidate, retrieve
from app.config import Settings
from app.models import ClassificationCache, NpaVersion
from app.npa.service import get_active_version, get_items
from app.schemas import REGIME_LABELS, Alternative, ClassificationResult, NpaMatch, Okpd2Ref, Regime

EMPTY_ERROR = "Пустое или нераспознанное наименование"
_has_word = re.compile(r"[a-zа-я]{2,}")


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class Pipeline:
    def __init__(self, settings: Settings, session_factory: Callable[[], Session],
                 embedder: Embedder | None = None, reranker: Reranker | None = None, llm=None):
        self.s = settings
        self.session_factory = session_factory
        self.embedder = embedder
        self.reranker = reranker
        self.llm = llm
        self._item_vecs: dict[int, tuple[list, np.ndarray]] = {}
        self._lock = threading.Lock()

    def warmup(self) -> None:
        if self.embedder is None:
            self.embedder = Embedder(self.s.embed_model, self.s.device)
        if self.reranker is None:
            self.reranker = Reranker(self.s.rerank_model, self.s.device)
        self.embedder.encode_queries(["прогрев"])
        self.reranker.score([("прогрев", "прогрев")])

    # --- позиции ПП активной версии с эмбеддингами наименований (для порядка внутри приложения)
    def _version_items(self, session: Session, version_id: int) -> tuple[list, np.ndarray]:
        with self._lock:
            if version_id not in self._item_vecs:
                items = get_items(session, version_id)
                vecs = self.embedder.encode_passages([i.title for i in items]) if items else np.zeros((0, 1))
                self._item_vecs = {version_id: (items, vecs)}  # держим только одну версию
            return self._item_vecs[version_id]

    def _npa_matches(self, code: str, query_vec: np.ndarray, items: list, vecs: np.ndarray,
                     source_url: str) -> list[NpaMatch]:
        found = match(code, items, source_url)
        if len(found) < 2:
            return found
        sim = {it.id: float(vecs[i] @ query_vec) for i, it in enumerate(items)}
        # порядок режимов (запрет → ограничение → преимущество) сохраняется, внутри — по близости наименования
        return sorted(found, key=lambda m: (m.appendix, -sim.get(m.item_id, 0.0)))

    def _result(self, name: str, cands: list[Candidate], raw: list[float], matches: list[NpaMatch]) -> dict:
        order = sorted(range(len(cands)), key=lambda i: -raw[i])
        probs = to_confidence([raw[i] for i in order], self.s.confidence_temperature)
        best = cands[order[0]]
        conf = probs[0] * _sigmoid(raw[order[0]])
        v = verdict(matches)
        expl = f"Наиболее близкое наименование ОКПД2: «{best.title}»"
        if best.matched_text != best.title:
            expl += f" (совпадение по «{best.matched_text}»)"
        expl += f". Вердикт по ПП № 1875: {REGIME_LABELS[v].lower()}."
        return ClassificationResult(
            input=name,
            okpd2=Okpd2Ref(code=best.code, title=best.title),
            alternatives=[Alternative(code=cands[i].code, title=cands[i].title,
                                      confidence=round(p * _sigmoid(raw[i]), 4))
                          for i, p in zip(order[1:4], probs[1:4])],
            confidence=round(conf, 4),
            needs_review=conf < self.s.needs_review_threshold,
            npa_matches=matches,
            verdict=v,
            explanation=expl,
        ).model_dump(mode="json")

    def classify_many(self, names: list[str], npa_version_id: int | None = None) -> list[ClassificationResult]:
        norms = [normalize(n) for n in names]
        with self.session_factory() as session:
            version = session.get(NpaVersion, npa_version_id) if npa_version_id else get_active_version(session)
            vid = version.id if version else 0
            todo = sorted({n for n in norms if _has_word.search(n)})
            cached = {c.norm_name: c.result for c in session.scalars(
                select(ClassificationCache).where(ClassificationCache.npa_version == vid,
                                                  ClassificationCache.norm_name.in_(todo)))} if todo else {}
            todo = [n for n in todo if n not in cached]
            fresh = self._classify_unique(session, todo, version) if todo else {}
            if fresh:
                session.execute(pg_insert(ClassificationCache).values(
                    [{"norm_name": n, "npa_version": vid, "result": r} for n, r in fresh.items()]
                ).on_conflict_do_nothing())
                session.commit()
        by_norm = {**cached, **fresh}
        out = []
        for name, norm in zip(names, norms):
            if norm in by_norm:
                out.append(ClassificationResult.model_validate({**by_norm[norm], "input": name}))
            else:
                out.append(ClassificationResult(input=name, error=EMPTY_ERROR, needs_review=True, verdict=Regime.none))
        return out

    def _classify_unique(self, session: Session, norms: list[str], version: NpaVersion | None) -> dict[str, dict]:
        qvecs = self.embedder.encode_queries(norms)
        cand_lists = retrieve(session, qvecs, self.s.retrieve_k)
        items, ivecs = self._version_items(session, version.id) if version else ([], np.zeros((0, 1)))
        source_url = version.source_url if version else ""

        pairs, spans = [], []
        for norm, cands in zip(norms, cand_lists):
            top = cands[: self.s.rerank_k]
            start = len(pairs)
            pairs += [(norm, c.title if c.matched_text == c.title else f"{c.matched_text}. {c.title}") for c in top]
            spans.append((start, len(pairs)))
        raw_all = self.reranker.score(pairs)

        out = {}
        for norm, qv, cands, (a, b) in zip(norms, qvecs, cand_lists, spans):
            top = cands[: self.s.rerank_k]
            if not top:
                continue
            raw = raw_all[a:b]
            best = top[int(np.argmax(raw))]
            matches = self._npa_matches(best.code, qv, items, ivecs, source_url)
            out[norm] = self._result(norm, top, raw, matches)
        return out


_pipeline: Pipeline | None = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> Pipeline:
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            from app.config import get_settings
            from app.db import SessionLocal

            _pipeline = Pipeline(get_settings(), SessionLocal)
            _pipeline.warmup()
        return _pipeline
