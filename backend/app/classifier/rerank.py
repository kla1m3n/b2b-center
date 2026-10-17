"""Поправки к порядку кандидатов после поиска по смыслу."""
import re

from app.classifier.retriever import Candidate

# Код-услуга: «Услуги по аренде легковых автомобилей…», «Работы по монтажу…»
_SERVICE_TITLE = re.compile(r"^(услуги|работы)\b", re.IGNORECASE)
# Признаки того, что закупается именно услуга или работа
_SERVICE_QUERY = re.compile(
    r"услуг|работ|ремонт|обслуж|монтаж|установк|доставк|перевоз|транспортир|аренд|прокат|изготовлен|пошив|"
    r"разработк|проведени|оказани|сервис|страхов|обучени|консультац|уборк|вывоз|утилизац|техническ\w* поддержк",
    re.IGNORECASE,
)


def prefer_goods(query: str, cands: list[Candidate]) -> list[Candidate]:
    """Если в наименовании нет признаков услуги, коды-услуги уходят ниже товаров.

    «Автомобиль легковой Lada Vesta» по смыслу ближе всего к «Услугам по аренде легковых автомобилей»,
    но закупают автомобиль. Порядок внутри товаров и внутри услуг сохраняется.
    """
    if _SERVICE_QUERY.search(query):
        return cands
    goods = [c for c in cands if not _SERVICE_TITLE.match(c.title)]
    return goods + [c for c in cands if _SERVICE_TITLE.match(c.title)] if goods else cands


# Разделы ОКПД2, где лежат медицинские изделия и материалы: изделия и инструменты (32.50), препараты и
# перевязочные материалы (21.20), медицинская аппаратура (26.60), медицинские перчатки (22.19.60)
_MEDICAL_PREFIXES = ("3250", "2120", "2660", "221960")
_MEDICAL_QUERY = "медицинское изделие"  # так normalize() переносит в начало пометку ЕИС «(является медицинским изделием)»


def prefer_medical(query: str, cands: list[Candidate]) -> list[Candidate]:
    """Для товара с пометкой ЕИС «является медицинским изделием» коды медицинских разделов идут первыми.

    Без этого «Цемент костный (является медицинским изделием)» уходит в «Цементы общестроительные»,
    а «Шкаф для хранения лекарственных средств» — в «Банки стеклянные».
    """
    if not query.startswith(_MEDICAL_QUERY):
        return cands
    med = [c for c in cands if c.code.replace(".", "").startswith(_MEDICAL_PREFIXES)]
    return med + [c for c in cands if c not in med] if med else cands
