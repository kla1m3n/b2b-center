from app.classifier.rerank import prefer_goods, prefer_medical, same_group
from app.classifier.retriever import Candidate


def c(code: str, title: str) -> Candidate:
    return Candidate(code=code, title=title, score=0.8, matched_text=title)


SERVICE = c("49.32.12.000", "Услуги по аренде легковых автомобилей с водителем")
CAR = c("29.10.22.000", "Средства транспортные с двигателем с искровым зажиганием")


def test_goods_go_before_services_for_a_product():
    assert prefer_goods("автомобиль легковой lada vesta", [SERVICE, CAR]) == [CAR, SERVICE]


def test_services_kept_when_query_is_a_service():
    assert prefer_goods("аренда автомобиля с водителем", [SERVICE, CAR]) == [SERVICE, CAR]


def test_only_services_left_as_is():
    assert prefer_goods("автомобиль", [SERVICE]) == [SERVICE]


BUILD_CEMENT = c("23.51.12.110", "Цементы общестроительные")
DENTAL = c("21.20.24.180", "Материалы стоматологические, не включенные в другие группировки")


def test_medical_codes_first_for_medical_device():
    assert prefer_medical("медицинское изделие цемент стоматологический", [BUILD_CEMENT, DENTAL]) == [DENTAL, BUILD_CEMENT]


def test_medical_rule_ignores_regular_goods():
    assert prefer_medical("цемент м500", [BUILD_CEMENT, DENTAL]) == [BUILD_CEMENT, DENTAL]


def test_medical_by_score_orders_by_similarity_and_counts_medical_synonym():
    suit = Candidate(code="14.12.30.190", title="Одежда производственная", score=0.73, matched_text="костюм медицинский")
    mask = Candidate(code="32.50.50.190", title="Изделия медицинские прочие", score=0.40, matched_text="маска медицинская")
    tool = Candidate(code="32.50.11.110", title="Аппараты стоматологические", score=0.39, matched_text="аппараты")
    dental = Candidate(code="21.20.24.180", title="Материалы стоматологические", score=0.52, matched_text="материалы")
    q = "медицинское изделие костюм изолирующий"
    assert prefer_medical(q, [suit, mask])[0] is mask                      # прежнее правило: медицинский раздел выше
    assert prefer_medical(q, [suit, mask], by_score=True)[0] is suit         # медицинский синоним и сходство 0,73
    assert prefer_medical(q, [tool, dental], by_score=True)[0] is dental


def test_print_run_is_a_service():
    printing = c("18.12.19.110", "Услуги по печатанию брошюр")
    machine = c("28.23.23.000", "Машины офисные прочие")
    assert prefer_goods("печать брошюр полноцветная тираж 500 экз", [printing, machine])[0] is printing


def test_same_group_follows_rerank_rules():
    goods = same_group("автомобиль легковой")
    assert goods(CAR, CAR) and not goods(CAR, SERVICE)
    assert same_group("аренда автомобиля")(CAR, SERVICE)       # запрос — услуга: правило товаров не действует
    med = same_group("медицинское изделие цемент")
    assert med(DENTAL, DENTAL) and not med(DENTAL, BUILD_CEMENT)
