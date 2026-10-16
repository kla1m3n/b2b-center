"""Конвейер классификации: нормализация → поиск по смыслу → сверка с ПП → результат.

Кросс-энкодер (реранкер) убран: на реальных закупках он ухудшал точность и был в 10 раз медленнее (reports/models.md).
"""
import re
import threading
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.classifier.confidence import calibrated
from app.classifier.embedder import Embedder
from app.classifier.matcher import match, rank_by_overlap, verdict
from app.classifier.normalize import normalize
from app.classifier.retriever import Candidate, retrieve
from app.config import Settings
from app.models import ClassificationCache, NpaVersion
from app.npa.service import get_active_version, get_items
from app.schemas import REGIME_LABELS, Alternative, ClassificationResult, NpaMatch, Okpd2Ref, Regime

EMPTY_ERROR = "Пустое или нераспознанное наименование"
_has_word = re.compile(r"[a-zа-я]{2,}")


class Pipeline:
    def __init__(self, settings: Settings, session_factory: Callable[[], Session],
                 embedder: Embedder | None = None, llm=None):
        self.s = settings
        self.session_factory = session_factory
        self.embedder = embedder
        self.llm = llm
        self._items: dict[int, list] = {}
        self._lock = threading.Lock()

    def warmup(self) -> None:
        if self.embedder is None:
            self.embedder = Embedder(self.s.embed_model, self.s.device)
        self.embedder.encode_queries(["прогрев"])
        with self.session_factory() as session:  # позиции активной редакции ПП — в память при старте
            version = get_active_version(session)
            if version:
                self._version_items(session, version.id)

    def _version_items(self, session: Session, version_id: int) -> list:
        with self._lock:
            if version_id not in self._items:
                self._items = {version_id: get_items(session, version_id)}  # держим только одну версию
            return self._items[version_id]

    def _result(self, name: str, cands: list[Candidate], matches: list[NpaMatch]) -> dict:
        coef = self.s.confidence_coef
        best = cands[0]
        second = cands[1].score if len(cands) > 1 else 0.0
        conf = calibrated(best.score, second, coef)
        v = verdict(matches)
        expl = f"Наиболее близкое наименование ОКПД2: «{best.title}»"
        if best.matched_text != best.title:
            expl += f" (совпадение по «{best.matched_text}»)"
        expl += f". Вердикт по ПП № 1875: {REGIME_LABELS[v].lower()}."
        return ClassificationResult(
            input=name,
            okpd2=Okpd2Ref(code=best.code, title=best.title),
            alternatives=[Alternative(code=c.code, title=c.title,
                                      confidence=round(calibrated(c.score, best.score, coef), 4)) for c in cands[1:4]],
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
                cached_res = by_norm[norm]
                # Пометку пересчитываем: кэш живёт дольше настройки порога (NEEDS_REVIEW_THRESHOLD)
                out.append(ClassificationResult.model_validate({
                    **cached_res, "input": name,
                    "needs_review": cached_res["confidence"] < self.s.needs_review_threshold,
                }))
            else:
                out.append(ClassificationResult(input=name, error=EMPTY_ERROR, needs_review=True, verdict=Regime.none))
        return out

    def _classify_unique(self, session: Session, norms: list[str], version: NpaVersion | None) -> dict[str, dict]:
        qvecs = self.embedder.encode_queries(norms)
        cand_lists = retrieve(session, qvecs, self.s.retrieve_k)
        items = self._version_items(session, version.id) if version else []
        source_url = version.source_url if version else ""
        out = {}
        for norm, cands in zip(norms, cand_lists):
            if not cands:
                continue
            matches = rank_by_overlap(norm, match(cands[0].code, items, source_url))
            out[norm] = self._result(norm, cands, matches)
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
