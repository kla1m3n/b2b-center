"""Исправление опечаток в наименовании по словарю справочника ОКПД2 и синонимов.

Опечатка в главном слове ломает и поиск по смыслу, и поиск по словам: «Телвеизор LED» уходил
в «Светильники», «Блконот» — в «Бумагу копировальную». Слово заменяется, только если:
  - его нет в словаре (наименования кодов + синонимы), нет и его основы («клетку» при «клетки» — не опечатка),
    оно кириллическое и не короче 5 букв;
  - есть словарное слово на расстоянии Дамерау–Левенштейна ≤ 1 (≤ 2 для слов от 8 букв),
    с теми же первыми двумя буквами (или с переставленными 2-й и 3-й: «пилта» -> «плита») — чтобы не
    «исправлять» редкие, но верные слова.
Из нескольких кандидатов берётся ближайший, при равенстве — самый частый в справочнике.
"""
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

from app.classifier.lexical import stem

_WORD = re.compile(r"[а-я]+")


def damerau(a: str, b: str, limit: int) -> int:
    """Расстояние Дамерау–Левенштейна (с перестановкой соседних букв); limit+1, если больше limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


class Speller:
    def __init__(self, texts: Iterable[str]):
        self.freq: Counter[str] = Counter()
        for t in texts:
            self.freq.update(_WORD.findall(t.lower().replace("ё", "е")))
        self.stems = {stem(w) for w in self.freq}
        self.by_prefix: dict[str, list[str]] = defaultdict(list)
        for w in self.freq:
            if len(w) >= 4:
                self.by_prefix[w[:2]].append(w)

    def correct_word(self, word: str) -> str:
        if len(word) < 5 or word in self.freq or not _WORD.fullmatch(word) or stem(word) in self.stems:
            return word
        limit = 2 if len(word) >= 8 else 1
        best, best_key = word, None
        # те же первые две буквы — или переставленные 2-я и 3-я («пилта» -> «плита»): первая буква совпадает всегда
        prefixes = dict.fromkeys([word[:2], word[0] + word[2]])
        for cand in (c for p in prefixes for c in self.by_prefix.get(p, ())):
            d = damerau(word, cand, limit)
            if d <= limit:
                key = (d, -self.freq[cand])
                if best_key is None or key < best_key:
                    best, best_key = cand, key
        return best

    def correct(self, text: str) -> str:
        """text — уже нормализованное наименование (нижний регистр, токены через пробел)."""
        return " ".join(self.correct_word(t) for t in text.split())
