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
    """Код позиции `parent` покрывает `code`, если совпадают все его уровни (через точку)."""
    p, c = parent.split("."), code.split(".")
    return len(p) <= len(c) and c[: len(p)] == p


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
