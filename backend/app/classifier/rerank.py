"""Поправки к порядку кандидатов после поиска по смыслу."""
import re
from collections.abc import Callable

from app.classifier.retriever import Candidate

# Код-услуга: «Услуги по аренде легковых автомобилей…», «Работы по монтажу…»
_SERVICE_TITLE = re.compile(r"^(услуги|работы)\b", re.IGNORECASE)
# Признаки того, что закупается именно услуга или работа
_SERVICE_QUERY = re.compile(
    r"услуг|работ|ремонт|обслуж|монтаж|установк|доставк|перевоз|транспортир|аренд|прокат|изготовлен|пошив|"
    r"разработк|проведени|оказани|сервис|страхов|обучени|консультац|уборк|вывоз|утилизац|техническ\w* поддержк|"
    r"тираж|печатани",  # «Печать брошюр, тираж 500 экз.» — услуга печати, а не брошюровочная машина
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
# перевязочные материалы (21.20), медицинская аппаратура (26.60), медицинские перчатки (22.19.60).
# Исключать лекарства 21.20.1 пробовали (31.10.2026): вердикт на dev не исправился ни у одного товара, а один
# угаданный («Комплект мониторинга глюкозы») стал ошибкой — правильный 32.50.50.190 всё равно не первый.
_MEDICAL_PREFIXES = ("3250", "2120", "2660", "221960")
_MEDICAL_QUERY = "медицинское изделие"  # так normalize() переносит в начало пометку ЕИС «(является медицинским изделием)»


def is_medical_code(code: str) -> bool:
    return code.replace(".", "").startswith(_MEDICAL_PREFIXES)


def _is_medical(c: Candidate) -> bool:
    """Медицинский раздел или совпадение с медицинским синонимом («костюм медицинский» у 14.12.30.190)."""
    return is_medical_code(c.code) or "медицин" in c.matched_text.lower()


def prefer_medical(query: str, cands: list[Candidate], by_score: bool = False) -> list[Candidate]:
    """Для товара с пометкой ЕИС «является медицинским изделием» коды медицинских изделий идут первыми.

    Без этого «Цемент костный (является медицинским изделием)» уходит в «Цементы общестроительные»,
    а «Шкаф для хранения лекарственных средств» — в «Банки стеклянные».
    by_score: медицинские кандидаты — по сходству, а не в порядке слияния, и медицинским считается совпадение
    с медицинским синонимом. Иначе «Костюм изолирующий» (0,73 у «костюм медицинский») уступал «маске» (0,40).
    """
    if not query.startswith(_MEDICAL_QUERY):
        return cands
    is_med = _is_medical if by_score else (lambda c: is_medical_code(c.code))
    med = [c for c in cands if is_med(c)]
    if by_score:
        med.sort(key=lambda c: -c.score)
    return med + [c for c in cands if c not in med] if med else cands


def same_group(query: str) -> Callable[[Candidate, Candidate], bool]:
    """Кандидат в той же группе, что и лучший, по правилам выше: товар/услуга (если в запросе нет признаков
    услуги) и медицинский/прочий раздел (если товар — медизделие). Голосование по режиму ПП идёт только
    внутри группы лучшего кандидата — иначе оно отменяло бы эти правила."""
    goods_rule = not _SERVICE_QUERY.search(query)
    med_rule = query.startswith(_MEDICAL_QUERY)

    def key(c: Candidate) -> tuple[bool, bool]:
        return (goods_rule and bool(_SERVICE_TITLE.match(c.title)), med_rule and is_medical_code(c.code))

    return lambda a, b: key(a) == key(b)
