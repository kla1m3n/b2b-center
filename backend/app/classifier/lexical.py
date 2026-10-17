"""Поиск по словам (BM25) в дополнение к поиску по смыслу.

Эмбеддинги иногда цепляются за похожие куски слов («Краска порошковая» → «Средства стиральные»,
«Кисель» → «Кислоты»), а совпадение самих слов с официальным наименованием ОКПД2 — сильный сигнал.
BM25 учитывает редкость слова: «плита» в наименованиях встречается редко и весит много,
«изделие» — часто и почти ничего не решает. Индекс строится в памяти по текстам okpd2_text (~16 тыс.).
"""
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

_WORD = re.compile(r"[a-zа-я0-9]+")
# Окончания русских слов, от длинных к коротким: «плиты»/«плита» → «плит», «легковой»/«легковые» → «легков»
_ENDINGS = sorted(
    "ями ами ого его ому ему ыми ими ией ия ие ий ый ой ая яя ое ее ые ую юю ом ем ах ях ам ям ов ев ей ь а я ы и е о у ю".split(),
    key=len, reverse=True,
)
_STOP = {"для", "или", "без", "при", "под", "над", "из", "на", "по", "от", "до", "не", "в", "с", "и", "к", "со", "мм", "см", "шт"}


def stem(word: str) -> str:
    for e in _ENDINGS:
        if word.endswith(e) and len(word) - len(e) >= 3:
            word = word[: -len(e)]
            break
    return word[:8]  # 7 букв склеивали «металлические» и «металлизированная»


def tokens(text: str) -> list[str]:
    words = _WORD.findall(text.lower().replace("ё", "е"))
    return [stem(w) for w in words if len(w) >= 3 and w not in _STOP and not w.isdigit()]


class LexicalIndex:
    """BM25 по текстам кодов (официальное наименование + синонимы); результат — лучший текст на код."""

    def __init__(self, docs: Iterable[tuple[str, str]], k1: float = 1.2, b: float = 0.75):
        self.codes: list[str] = []
        self.texts: list[str] = []
        self.lens: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, (code, text) in enumerate(docs):
            toks = tokens(text)
            self.codes.append(code)
            self.texts.append(text)
            self.lens.append(len(toks))
            for t, tf in Counter(toks).items():
                self.postings[t].append((i, tf))
        n = len(self.codes) or 1
        self.avg = (sum(self.lens) / n) or 1.0
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int) -> list[tuple[str, float, str]]:
        """(код, BM25, совпавший текст) — по убыванию, не больше k кодов."""
        scores: dict[int, float] = defaultdict(float)
        for t in set(tokens(query)):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in self.postings[t]:
                norm = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
                scores[i] += idf * tf * (self.k1 + 1) / norm
        best: dict[str, tuple[float, str]] = {}
        for i, sc in sorted(scores.items(), key=lambda x: -x[1]):
            code = self.codes[i]
            if code not in best:
                best[code] = (sc, self.texts[i])
                if len(best) == k:
                    break
        return [(c, sc, t) for c, (sc, t) in best.items()]


def rrf(rankings: list[list[str]], weights: list[float] | None = None, k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion: объединяет несколько упорядоченных списков кодов в один (с весами списков)."""
    score: dict[str, float] = defaultdict(float)
    for ranking, w in zip(rankings, weights or [1.0] * len(rankings)):
        for pos, code in enumerate(ranking):
            score[code] += w / (k + pos + 1)
    return sorted(score, key=lambda c: -score[c])
