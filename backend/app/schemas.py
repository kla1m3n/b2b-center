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
    Regime.advantage: "МИН. ДОЛЯ",  # прил. № 3: минимальная обязательная доля российских товаров (223-ФЗ)
    Regime.none: "НЕ ПОДПАДАЕТ",
}


class Okpd2Ref(BaseModel):
    code: str
    title: str


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


class Alternative(BaseModel):
    code: str
    title: str
    confidence: float
    # Режим и пункты ПП, если бы товар отнесли к этому коду: специалист видит, меняется ли режим при другом коде
    verdict: Regime = Regime.none
    npa_matches: list[NpaMatch] = []
    regime_differs: bool = False  # режим отличается от режима выбранного кода


class ClassificationResult(BaseModel):
    input: str
    okpd2: Okpd2Ref | None = None
    matched_text: str = ""  # текст классификатора (наименование кода или синоним), с которым совпал товар
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
    npa_version: str = ""  # название редакции ПП, по которой определён режим
    recommendation: str = ""  # что делать специалисту при таком режиме (app/report.py)
    justification: str = ""  # готовый текст обоснования для документации или служебной записки


class RegimeShare(BaseModel):
    regime: Regime
    label: str
    count: int
    share: float  # доля от всех позиций списка, 0..1


class LowConfidenceItem(BaseModel):
    idx: int  # номер позиции в списке, с 1
    input: str
    code: str
    verdict: Regime
    confidence: float


class ReportSummary(BaseModel):
    """Сводка по списку для тендерного специалиста: режимы, ручная проверка, наименьшая уверенность."""
    total: int
    errors: int  # нераспознанные наименования
    by_regime: list[RegimeShare]
    needs_review: int
    needs_review_share: float
    lowest_confidence: list[LowConfidenceItem]


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
    summary: ReportSummary | None = None  # вместе с results, при status = done
