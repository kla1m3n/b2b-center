"""Детерминированная сверка кода ОКПД2 с позициями ПП № 1875 (без ИИ)."""
import re
from collections.abc import Sequence
from typing import Protocol

from app.schemas import NpaMatch, Regime

REGIME_ORDER = {Regime.ban: 0, Regime.restriction: 1, Regime.advantage: 2, Regime.none: 3}


class NpaItemLike(Protocol):
    appendix: int
    item_no: str
    title: str
    codes: list[str]
    regime: Regime | str
    quota: int | None
    exclusions: list[str]
    note: str
    has_conditions: bool


def code_covers(parent: str, code: str) -> bool:
    """Код позиции `parent` покрывает `code`.

    1. Цифры parent — префикс цифр code: подгруппа 26.20.1 включает вид 26.20.11, подкласс 26.2 — группу 26.20.
    2. Категория включает свои подкатегории. По ОК 034-2014 (введение): категория — XX.XX.XX.XX0,
       подкатегория — XX.XX.XX.XXX. Пункт ПП на «Счетчики электроэнергии» 26.51.63.130 распространяется и на
       26.51.63.131/.139, хотя цифры .130 не префикс .139. В открытом справочнике все такие коды помечены
       конечными с родителем-видом, поэтому правило 1 этого не видит.
    """
    p, c = parent.replace(".", ""), code.replace(".", "")
    if c.startswith(p):
        return True
    return len(p) == 9 and p.endswith("0") and len(c) == 9 and c[:8] == p[:8]


def _item_no_key(item_no: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", item_no)) or (0,)


def match(code: str, items: Sequence[NpaItemLike], source_url: str = "") -> list[NpaMatch]:
    found = []
    for it in items:
        covering = next((c for c in it.codes if code_covers(c, code)), None)
        if covering is None or any(code_covers(x, code) for x in it.exclusions or []):
            continue
        found.append(NpaMatch(
            item_id=getattr(it, "id", None),
            regime=Regime(it.regime),
            appendix=it.appendix,
            item_no=it.item_no,
            title=it.title,
            matched_code=covering,
            quota=it.quota,
            has_conditions=bool(getattr(it, "has_conditions", False)),
            note=getattr(it, "note", "") or "",
            source_url=source_url,
        ))
    found.sort(key=lambda m: (REGIME_ORDER[m.regime], m.appendix, _item_no_key(m.item_no)))
    return found


def verdict(matches: list[NpaMatch]) -> Regime:
    return min((m.regime for m in matches), key=REGIME_ORDER.__getitem__, default=Regime.none)


def _stems(text: str) -> set[str]:
    """Грубые основы слов: первые 5 букв слов длиннее 3 символов («контейнеры» ~ «контейнер»)."""
    return {w[:5] for w in re.findall(r"[a-zа-яё]+", text.lower()) if len(w) > 3}


def rank_by_overlap(query: str, matches: list[NpaMatch]) -> list[NpaMatch]:
    """Внутри одного приложения выше позиции, чьё наименование ближе к товару по общим словам.

    Порядок приложений (запрет → ограничение → преимущество) сохраняется.
    """
    q = _stems(query)
    return sorted(matches, key=lambda m: (REGIME_ORDER[m.regime], m.appendix, -len(q & _stems(m.title))))
