from types import SimpleNamespace

from app.classifier.pipeline import Pipeline
from app.classifier.retriever import Candidate
from app.npa.parser import NpaItemIn
from app.schemas import Regime

# ограничение на телевизоры 26.40.20.1, запрет на мониторы 26.20.17 — условные позиции для теста
ITEMS = [NpaItemIn(appendix=2, item_no="1", title="Телевизоры", codes=["26.40.20.1"], regime=Regime.restriction),
         NpaItemIn(appendix=1, item_no="2", title="Мониторы", codes=["26.20.17"], regime=Regime.ban)]


def pipe(k=10, t=0.03) -> Pipeline:
    p = Pipeline.__new__(Pipeline)
    p.s = SimpleNamespace(vote_k=k, vote_temperature=t)
    return p


def c(code: str, score: float, title: str = "товар") -> Candidate:
    return Candidate(code=code, title=title, score=score, matched_text=title)


def test_vote_sums_close_codes_of_one_regime():
    # лучший — монитор (запрет), но два телевизора почти так же близки: в сумме перевешивает «ограничение»
    cands = [c("26.20.17.110", 0.900), c("26.40.20.110", 0.895), c("26.40.20.120", 0.894), c("10.71.11.110", 0.70)]
    out = pipe()._vote("телевизор", cands, ITEMS)
    assert out[0].code == "26.40.20.110"                   # лучший по рангу кандидат победившего режима
    assert [x.code for x in out[1:]] == ["26.20.17.110", "26.40.20.120", "10.71.11.110"]


def test_vote_keeps_clear_winner():
    cands = [c("26.20.17.110", 0.95), c("26.40.20.110", 0.85), c("26.40.20.120", 0.84)]
    assert pipe()._vote("монитор", cands, ITEMS) == cands  # отрыв больше температуры — вердикт не меняется


def test_vote_respects_goods_before_services():
    # услуга с тем же режимом не голосует за товар: группа лучшего кандидата — товары
    cands = [c("26.20.17.110", 0.90), c("26.40.20.110", 0.899, "Услуги по ремонту телевизоров"),
             c("26.40.20.120", 0.898, "Услуги по аренде телевизоров")]
    assert pipe()._vote("монитор samsung", cands, ITEMS) == cands
