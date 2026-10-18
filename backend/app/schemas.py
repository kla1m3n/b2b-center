from enum import Enum

from pydantic import BaseModel


class Regime(str, Enum):
    ban = "ban"
    restriction = "restriction"
    advantage = "advantage"
    none = "none"


REGIME_BY_APPENDIX = {1: Regime.ban, 2: Regime.restriction, 3: Regime.advantage}
REGIME_LABELS = {
    Regime.ban: "ЗАПРЕТ",
    Regime.restriction: "ОГРАНИЧЕНИЕ",
    Regime.advantage: "ПРЕИМУЩЕСТВО",
    Regime.none: "НЕ ПОДПАДАЕТ",
}


class Okpd2Ref(BaseModel):
    code: str
    title: str


class Alternative(BaseModel):
    code: str
    title: str
    confidence: float


class NpaMatch(BaseModel):
    item_id: int | None = None
    regime: Regime
    appendix: int
    item_no: str
    title: str
    matched_code: str
    quota: int | None = None
    has_conditions: bool = False
    note: str = ""
    source_url: str = ""


class ClassificationResult(BaseModel):
    input: str
    okpd2: Okpd2Ref | None = None
    alternatives: list[Alternative] = []
    confidence: float = 0.0
    needs_review: bool = True
    npa_matches: list[NpaMatch] = []
    verdict: Regime = Regime.none
    explanation: str = ""
    error: str | None = None
    # Текст действующей редакции ПП — ссылка есть у любого результата, в том числе «не подпадает»,
    # где пунктов приложений нет (критерий ТЗ: «каждый результат содержит ссылку на НПА»)
    npa_source_url: str = ""


class HealthOut(BaseModel):
    status: str
    db: bool
    models: bool
    npa_version: str | None
    npa_upload_protected: bool = False  # загрузка редакции ПП требует пароль администратора (фронт показывает поле)


class JobCreated(BaseModel):
    job_id: str


class JobOut(BaseModel):
    job_id: str
    status: str  # queued | running | done | failed
    total: int
    done: int
    error: str | None = None
    results: list[ClassificationResult] | None = None
