"""
pp1875_core — ядро классификатора товаров по ПП РФ от 23.12.2024 № 1875
(национальный режим в закупках; база по умолчанию — ред. от 30.09.2026).

Один и тот же файл используется:
  * в Kaggle-ноутбуке при обучении и оценке;
  * в бэкенде (FastAPI/Celery) при инференсе: PP1875Classifier.load(<artifacts>).

Схема инференса:
  наименование -> нормализация -> bi-encoder -> top-K кодов ОКПД2 (поиск по ВСЕМУ ОКПД2)
  -> cross-encoder (переранжирование top-R) -> softmax с температурой
  -> агрегация вероятностей по позициям ПП 1875 (совпадение кода по префиксу)
  -> позиция (или «не входит в перечни») + откалиброванная уверенность + ссылка на пункт.

torch / sentence-transformers / transformers импортируются лениво, поэтому
сопоставление с ПП и калибровку можно использовать и тестировать без них.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

PP_TITLE = "Постановление Правительства РФ от 23.12.2024 № 1875"
NONE_KEY = "NONE"  # товар не входит ни в одну позицию приложений ПП 1875

# Код ОКПД2: 26 / 26.2 / 26.20 / 26.20.1 / 26.20.11 / 26.20.11.1 / 26.20.11.110
_CODE_FULL = re.compile(r"\d{2}(?:\.\d{1,3}){0,4}")
_EXCL_RE = r"(?i)\b(?:кроме|за исключением|исключая)\b"
_CODE_FIND = re.compile(r"(?<![\d.])\d{2}(?:\.\d{1,3}){0,4}(?![\d])")


# ----------------------------------------------------------------------------- текст и коды
def normalize_text(s) -> str:
    """Унификация наименований из спецификаций: ё->е, кавычки, пробелы, CAPS LOCK."""
    s = "" if s is None else str(s)
    s = s.replace(" ", " ").replace("ё", "е").replace("Ё", "Е")
    s = re.sub(r"[«»“”„]", '"', s)
    s = re.sub(r"\s+", " ", s).strip(" ;,")
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        s = s.lower()  # «БУМАГА ДЛЯ ОФИСНОЙ ТЕХНИКИ А4» -> обычный регистр
    return s


def norm_code(x) -> str | None:
    """'26.20.11.110-00000001' (КТРУ) -> '26.20.11.110'; мусор -> None."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    s = str(x).strip().replace(" ", "").replace(",", ".")
    s = s.split("-")[0].rstrip(".")
    return s if _CODE_FULL.fullmatch(s) else None


def find_codes(cell) -> list[str]:
    """Все коды ОКПД2 из ячейки вида '26.20.11, 26.20.13 (кроме ...)'."""
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    out = []
    for c in _CODE_FIND.findall(str(cell)):
        c = norm_code(c)
        if c and c not in out:
            out.append(c)
    return out


def match_prefix(code: str) -> str:
    """Префикс, которым код покрывает потомков.

    До 6 знаков иерархия ОКПД2 совпадает со строковым префиксом (26.2 -> 26.20 -> 26.20.1 -> 26.20.11).
    В последнем 3-значном сегменте нули на конце означают группу: 26.40.20.120 включает
    26.40.20.121…129, 10.51.30.100 включает 10.51.30.1xx, 28.29.50.000 = вся группа 28.29.50.
    """
    head, _, last = code.rpartition(".")
    if code.count(".") == 3 and len(last) == 3:
        last = last.rstrip("0")
        return f"{head}.{last}" if last else head
    return code


def parent_code(code: str, code_set: set[str]) -> str | None:
    """Ближайший существующий предок с учётом групп вида XX.XX.XX.120 / .100."""
    head, _, last = code.rpartition(".")
    cands = []
    if code.count(".") == 3 and len(last) == 3:
        if last[2] != "0":
            cands.append(f"{head}.{last[:2]}0")
        if last[1:] != "00":
            cands.append(f"{head}.{last[0]}00")
    s = code
    while len(s) > 2:
        s = s[:-1].rstrip(".")
        cands.append(s)
    for c in cands:
        if c != code and c in code_set:
            return c
    return None


def build_docs(okpd: pd.DataFrame, ctx_levels: int = 2) -> pd.DataFrame:
    """
    Документы для поиска = ЛИСТЬЯ ОКПД2 (самые подробные коды).
    Текст документа = наименование + наименования предков: у листьев часто
    названия вида «Прочие ...» и без контекста раздела они неразличимы.
    """
    df = okpd[["code", "name"]].copy()
    df["code"] = df["code"].map(norm_code)
    df = df.dropna(subset=["code"]).drop_duplicates("code")
    df["name"] = df["name"].map(normalize_text)
    names = dict(zip(df["code"], df["name"]))
    code_set = set(names)
    parents = {c: parent_code(c, code_set) for c in code_set}
    has_child = {p for p in parents.values() if p}
    rows = []
    for c in sorted(code_set - has_child):
        ctx, p = [], parents[c]
        while p and len(ctx) < ctx_levels:
            if names[p].lower() != names[c].lower() and names[p] not in ctx:
                ctx.append(names[p])
            p = parents[p]
        text = names[c] + (f" (раздел: {'; '.join(ctx)})" if ctx else "")
        rows.append((c, names[c], text[:400]))
    return pd.DataFrame(rows, columns=["code", "name", "doc_text"])


def leaf_candidates(code: str, leaves: Sequence[str], max_n: int = 60) -> list[str]:
    """Коды нижнего уровня, которыми может быть код-группа из КТРУ/закупки.

    В КТРУ группа пишется нулями на конце: 10.12.10.000 = группа 10.12.10, 10.20.30.000 = класс 10.20.3.
    Встречаются и коды старой редакции (32.30.14.113). Ищем самую узкую группу справочника, в которой есть
    коды нижнего уровня; слишком широкую (> max_n кодов) не берём — по ней нельзя выбрать код.
    """
    if code in leaves:
        return [code]
    digits = code.replace(".", "")
    if code.endswith(".000"):
        digits = code[:-4].replace(".", "")
    p = digits
    while len(p) >= 4:
        hit = [l for l in leaves if l.replace(".", "").startswith(p)]
        if hit:
            return hit if len(hit) <= max_n else []
        p = p.rstrip("0") if p.endswith("0") and p.rstrip("0") != p else p[:-1]
    return []


# ----------------------------------------------------------------------------- генерация текстов LLM
# Общие для Qwen в ноутбуке и tools/gigachat_generate.py: отбор кодов, карточка кода, промпты, разбор ответа.
SYSTEM_PROMPT = "Ты эксперт по государственным закупкам в РФ и классификатору ОКПД2."
_RULES = ("Если код — услуги или работы, пиши именно услуги/работы, а не оборудование, материалы или расходники к ним; "
          "монтаж, ремонт, обслуживание, поставку оборудования пиши, только если это прямо есть в названии кода. "
          "Не пиши ничего, что относится к кодам из списка «не путать». Не пересказывай название кода "
          "перестановкой его слов — называй конкретные позиции так, как их назвал бы заказчик. ")
SYNTH_TASK = ("Напиши {n} разных реалистичных наименований позиций этого кода так, как их пишут заказчики "
              "в спецификациях закупок по 44-ФЗ и 223-ФЗ. " + _RULES +
              "Примерно половина — общие наименования без бренда (часть с техническими характеристиками, единицами "
              "измерения, сокращениями); не больше трети — с брендом и моделью, и только реально существующими, "
              "ничего не выдумывай. Длина и стиль разные.")
D2Q_TASK = ("Напиши {n} разных коротких (2–7 слов) формулировок, которыми заказчики называют такие позиции "
            "в закупках: бытовые названия, сокращения, с характеристиками и без; бренды — редко и только настоящие. "
            + _RULES +
            "В каждой формулировке должен быть назван предмет закупки: без общих фраз, подходящих к любому коду "
            "(«техническое подключение», «удаление отходов», «обслуживание системы»).")
ONE_CODE_PROMPT = "Код ОКПД2 {card}\n{task}\nПо одному на строку, без нумерации и пояснений."


def parse_lines(txt: str) -> list[str]:
    """Строки ответа LLM: без нумерации и маркеров, только парные внешние кавычки снимаются."""
    out = []
    for ln in (txt or "").split("\n"):
        ln = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", ln).strip()
        if len(ln) > 1 and (ln[0], ln[-1]) in (('"', '"'), ("«", "»")):
            ln = ln[1:-1].strip()
        if 3 <= len(ln) <= 200 and not ln.lower().startswith(("код окпд", "вот ", "примеры", "не путать")):
            out.append(ln)
    return list(dict.fromkeys(out))


def code_cards(docs: pd.DataFrame, n_neighbors: int = 4) -> dict[str, str]:
    """Карточка кода для промпта: «код: «название» [товары|услуги|работы]» + до n соседей «не путать».

    Берётся чистое название кода (docs['name']), соседи — ближайшие по порядку классификатора коды
    той же подгруппы, при нехватке — из группы выше.
    """
    codes = docs["code"].tolist()
    name = dict(zip(docs["code"], docs["name"].astype(str)))
    pos = {c: i for i, c in enumerate(codes)}
    by_parent: dict[str, list[str]] = {}
    for c in codes:
        for lvl in (1, 2):
            by_parent.setdefault(c.rsplit(".", lvl)[0], []).append(c)
    short = lambda t: t if len(t) <= 90 else t[:90].rsplit(" ", 1)[0].rstrip(",") + "…"
    cards = {}
    for c in codes:
        near = [x for x in by_parent.get(c.rsplit(".", 1)[0], []) if x != c]
        if len(near) < n_neighbors:
            near += [x for x in by_parent.get(c.rsplit(".", 2)[0], []) if x != c and x not in near]
        near = sorted(near, key=lambda x: abs(pos[x] - pos[c]))[:n_neighbors]
        title = name[c]
        low = title.lower()
        kind = "услуги" if low.startswith("услуг") else "работы" if low.startswith("работ") else "товары"
        avoid = "; ".join(f"«{short(name[x])}»" for x in near)
        cards[c] = f"{c}: «{title}» [{kind}]" + (f"\n  не путать с: {avoid}" if avoid else "")
    return cards


def real_pair_counts(pairs: pd.DataFrame, leaves: set[str]) -> dict[str, int]:
    """Сколько реальных пар (КТРУ + синонимы) у каждого кода нижнего уровня, коды-группы — по своим кандидатам."""
    cnt: dict[str, int] = {}
    lv = sorted(leaves)
    for code, n in pairs["code"].dropna().value_counts().items():
        cands = [code] if code in leaves else leaf_candidates(code, lv)
        for c in cands:
            cnt[c] = cnt.get(c, 0) + (n if len(cands) == 1 else 0)
    return cnt


def synth_targets(docs: pd.DataFrame, real_counts: dict[str, int], max_codes: int = 6500,
                  seed: int = 42, few: int = 5) -> list[str]:
    """Коды для синтетики по приоритету: (1) коды под позициями ПП, у которых нет или мало (< few) реальных пар;
    (2) их «соседи» вне ПП — трудные негативы для вердикта «не подпадает»; (3) коды ПП с реальными парами;
    плюс 10% случайных кодов вне ПП. Внутри групп порядок перемешан, чтобы обрезка max_codes не выкидывала
    целые разделы классификатора (раньше брались первые 3000 кодов ПП по порядку — разделы 26–32 не попадали)."""
    import random
    rng = random.Random(seed)
    outcome = dict(zip(docs["code"], docs["outcome"]))
    in_pp = [c for c in docs["code"] if outcome[c] != NONE_KEY]
    prefixes = {c.rsplit(".", 1)[0] for c in in_pp}
    siblings = [c for c in docs["code"] if outcome[c] == NONE_KEY and c.rsplit(".", 1)[0] in prefixes]
    need = [c for c in in_pp if real_counts.get(c, 0) < few]
    have = [c for c in in_pp if real_counts.get(c, 0) >= few]
    rest = [c for c in docs["code"] if outcome[c] == NONE_KEY and c not in set(siblings)]
    for lst in (need, siblings, have, rest):
        rng.shuffle(lst)
    n_rand = max_codes // 10
    main = (need + siblings + have)[:max_codes - n_rand]
    return main + rest[:n_rand]


# ----------------------------------------------------------------------------- ПП 1875
class PPIndex:
    """
    Позиции приложений ПП 1875. Ожидаемые колонки CSV:
      appendix  — номер приложения (1, 2, 3 ...)
      item      — номер позиции/пункта в приложении
      okpd2     — код(ы) ОКПД2 позиции (можно несколько через запятую)
      name      — наименование позиции
      regime    — (необяз.) 'запрет' / 'ограничение' / 'минимальная доля' ...
      exceptions— (необяз.) текстовые оговорки/условия — показываются пользователю
      excl_okpd2— (необяз.) коды-исключения; «кроме 26.20.13» прямо в okpd2 тоже понимается
      url       — (необяз.) ссылка на пункт постановления
      min_share / effective_from / note — (необяз.) доля для прил. 3, дата начала применения, примечание
    Обновление CSV не требует ни переобучения, ни переиндексации:
    позиции применяются к уже найденному коду ОКПД2 по префиксу.
    """

    def __init__(self, pp: pd.DataFrame, base_url: str = "", edition: str = "", on_date: str | None = None):
        """on_date (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД, по умолчанию сегодня): новые подпункты вида 82(1), которые на эту дату
        ещё не действуют, не учитываются — как в data/npa/pp1875.json бэкенда (scripts/build_npa_json.py)."""
        df = pp.copy()
        df.columns = [str(c).replace("\ufeff", "").strip().lower() for c in df.columns]
        for col in ("appendix", "item", "okpd2", "name"):
            if col not in df.columns:
                raise ValueError(f"В файле ПП 1875 нет колонки '{col}'. Есть: {list(df.columns)}")
        for col in ("regime", "exceptions", "url", "min_share", "effective_from", "note"):
            if col not in df.columns:
                df[col] = ""
        df = df.fillna("")
        import datetime as _dt
        def _d(x):
            x = str(x).strip()
            for f in ("%d.%m.%Y", "%Y-%m-%d"):
                try:
                    return _dt.datetime.strptime(x, f).date()
                except ValueError:
                    pass
            return None
        today = _d(on_date) if on_date else _dt.date.today()
        future = df["effective_from"].map(lambda x: (_d(x) or today) > today) & df["item"].astype(str).str.contains(r"\(")
        if future.any():
            print(f"[PPIndex] не действуют на {today:%d.%m.%Y}: {int(future.sum())} новых подпунктов — не учитываются")
        df = df[~future]
        # «26.20 (кроме 26.20.13)»: коды после слов-исключений не включаются, а исключаются
        parts = df["okpd2"].astype(str).str.split(_EXCL_RE, n=1, regex=True)
        df["codes"] = parts.map(lambda x: find_codes(x[0]))
        df["excl"] = parts.map(lambda x: find_codes(x[1]) if len(x) > 1 else [])
        if "excl_okpd2" in df.columns:
            df["excl"] = [a + [c for c in find_codes(b) if c not in a] for a, b in zip(df["excl"], df["excl_okpd2"])]
        bad = df[df["codes"].map(len) == 0]
        if len(bad):
            print(f"[PPIndex] пропущено {len(bad)} строк без распознанного кода ОКПД2")
        df = df[df["codes"].map(len) > 0].reset_index(drop=True)
        df["appendix"] = df["appendix"].astype(str).str.strip()
        df["item"] = df["item"].astype(str).str.strip()
        df["key"] = "П" + df["appendix"] + "." + df["item"]
        self.df, self.base_url, self.edition = df, base_url, edition
        self.by_code: dict[str, list[int]] = {}
        df["excl"] = df["excl"].map(lambda xs: [match_prefix(x) for x in xs])
        for i, codes in enumerate(df["codes"]):
            for c in codes:
                self.by_code.setdefault(match_prefix(c), []).append(i)
        self._cache: dict[str, str] = {}

    def match(self, code: str) -> list[int]:
        """Позиции, чей код — префикс кода товара; по каждому приложению самая точная."""
        best: dict[str, tuple[int, list[int]]] = {}  # приложение -> (длина префикса, позиции)
        for k in range(len(code), 1, -1):
            for i in self.by_code.get(code[:k], []):
                if any(code.startswith(e) for e in self.df.at[i, "excl"]):
                    continue                                    # код попал в «кроме ...» этой позиции
                app = self.df.at[i, "appendix"]
                if app not in best:
                    best[app] = (k, [i])                        # длинный префикс найден первым
                elif best[app][0] == k and i not in best[app][1]:
                    best[app][1].append(i)                      # несколько позиций с тем же кодом
        return sorted(i for _, idx in best.values() for i in idx)

    def outcome(self, code: str) -> str:
        """Ключ исхода: 'П1.12|П2.40' или 'NONE'."""
        if code not in self._cache:
            idx = self.match(code)
            self._cache[code] = "|".join(self.df.at[i, "key"] for i in idx) if idx else NONE_KEY
        return self._cache[code]

    def describe(self, key: str) -> list[dict]:
        if key == NONE_KEY:
            return []
        out = []
        for k in key.split("|"):
            r = self.df[self.df["key"] == k].iloc[0]
            url = r["url"] or (f"{self.base_url}" if self.base_url else "")
            out.append({
                "appendix": r["appendix"], "item": r["item"], "key": k,
                "okpd2": ", ".join(r["codes"]), "name": r["name"], "regime": r["regime"],
                "exceptions": r["exceptions"],
                "min_share": r.get("min_share", ""), "effective_from": r.get("effective_from", ""),
                "note": r.get("note", ""),
                # одинаковый код ОКПД2 у нескольких позиций одного приложения (мед. изделия
                # различаются кодами НКМИ) — по ОКПД2 позицию однозначно не определить
                "ambiguous": sum(1 for x in key.split("|") if x.startswith(f"П{r['appendix']}.")) > 1,
                "reference": f"{PP_TITLE}{' (ред. ' + self.edition + ')' if self.edition else ''}, "
                             f"приложение № {r['appendix']}, позиция {r['item']}",
                "url": url,
            })
        return out


# ----------------------------------------------------------------------------- вероятности
def softmax(x: np.ndarray, T: float = 1.0, axis: int = -1) -> np.ndarray:
    z = np.asarray(x, dtype=np.float64) / max(T, 1e-6)
    z = z - z.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)


def aggregate_outcomes(cand_codes: Sequence[str], probs: np.ndarray, pp: PPIndex) -> list[tuple[str, float]]:
    """Сумма вероятностей листьев ОКПД2 по исходам ПП (позиция / NONE), по убыванию.

    Почему это важно: если модель колеблется между двумя соседними кодами,
    которые входят в одну и ту же позицию ПП, ответ по ПП всё равно уверенный.
    """
    agg: dict[str, float] = {}
    for c, p in zip(cand_codes, probs):
        k = pp.outcome(c)
        agg[k] = agg.get(k, 0.0) + float(p)
    return sorted(agg.items(), key=lambda kv: -kv[1])


def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error: насколько «90%» модели действительно означают 90%."""
    conf, correct = np.asarray(conf, float), np.asarray(correct, float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def fit_temperature(logits_list: list[np.ndarray], cand_codes_list: list[list[str]],
                    gold_outcomes: list[str], pp: PPIndex,
                    grid: Iterable[float] | None = None) -> tuple[float, float]:
    """Подбор температуры по ECE именно для отображаемой уверенности (уровень позиции ПП)."""
    grid = np.logspace(-2.5, 1.5, 81) if grid is None else grid
    best = (1.0, 9.0)
    for T in grid:
        conf, corr = [], []
        for lg, cc, g in zip(logits_list, cand_codes_list, gold_outcomes):
            k, p = aggregate_outcomes(cc, softmax(lg, T), pp)[0]
            conf.append(p)
            corr.append(k == g)
        e = ece(np.array(conf), np.array(corr))
        if e < best[1]:
            best = (float(T), e)
    return best


def pick_threshold(conf: np.ndarray, correct: np.ndarray, target: float = 0.95, min_support: int = 20) -> float:
    """Минимальный порог, при котором точность среди «уверенных» ответов >= target."""
    order = np.argsort(-conf)
    c, ok = np.asarray(conf)[order], np.asarray(correct, float)[order]
    acc = np.cumsum(ok) / np.arange(1, len(ok) + 1)
    good = [i for i in range(len(c)) if i + 1 >= min_support and acc[i] >= target]
    return float(c[max(good)]) if good else 0.99


# ----------------------------------------------------------------------------- классификатор
class PP1875Classifier:
    def __init__(self, bi, docs: pd.DataFrame, doc_emb: np.ndarray, pp: PPIndex,
                 ce=None, ce_tok=None, calib: dict | None = None, device: str = "cpu",
                 texts: pd.DataFrame | None = None):
        """docs — один ряд на код (code, name, doc_text). texts — индекс поиска, если у кода несколько текстов
        (официальное наименование + синонимы + сгенерированные формулировки, колонки code, text, kind);
        doc_emb тогда — эмбеддинги texts. Как в бэкенде: у кода берётся лучший из его текстов."""
        self.bi, self.ce, self.ce_tok = bi, ce, ce_tok
        self.docs = docs.reset_index(drop=True)
        self.doc_codes = self.docs["code"].tolist()
        self.doc_text = dict(zip(self.docs["code"], self.docs["doc_text"]))
        self.set_index(texts)
        self.doc_emb = None if doc_emb is None else doc_emb.astype(np.float32)
        self.pp, self.device = pp, device
        self.calib = {"q_prefix": "", "d_prefix": "", "topk": 30, "rerank_k": 10, "overfetch": 10,
                      "T_bi": 0.05, "T_ce": 1.0, "tau_auto": 0.8, "ce_max_len": 160, **(calib or {})}

    def set_index(self, texts: pd.DataFrame | None):
        """Тексты индекса: None — по одному наименованию на код (docs)."""
        if texts is None:
            texts = pd.DataFrame({"code": self.docs["code"], "text": self.docs["doc_text"], "kind": "official"})
        self.texts = texts.reset_index(drop=True)
        self.text_codes = self.texts["code"].tolist()
        self.multi = len(self.text_codes) != len(set(self.text_codes))

    # ---- загрузка / обновление без передеплоя
    @classmethod
    def load(cls, art_dir: str, device: str = "cpu", pp_csv: str | None = None, quantize: bool = False):
        import torch
        from sentence_transformers import SentenceTransformer
        calib = json.load(open(os.path.join(art_dir, "calib.json"), encoding="utf-8"))
        bi = SentenceTransformer(os.path.join(art_dir, calib.get("bi_dir", "biencoder")), device=device)
        docs = pd.read_parquet(os.path.join(art_dir, "okpd2_docs.parquet"))
        emb = np.load(os.path.join(art_dir, "doc_emb.npy"))
        tp = os.path.join(art_dir, "okpd2_texts.parquet")
        texts = pd.read_parquet(tp) if os.path.exists(tp) else None
        pp_df = pd.read_csv(pp_csv or os.path.join(art_dir, "pp1875.csv"), dtype=str)
        pp = PPIndex(pp_df, calib.get("pp_url", ""), calib.get("pp_edition", ""))
        ce = tok = None
        if os.path.isdir(os.path.join(art_dir, "reranker")):
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            tok = AutoTokenizer.from_pretrained(os.path.join(art_dir, "reranker"))
            ce = AutoModelForSequenceClassification.from_pretrained(os.path.join(art_dir, "reranker")).to(device).eval()
            if quantize and device == "cpu":
                ce = torch.quantization.quantize_dynamic(ce, {torch.nn.Linear}, dtype=torch.qint8)
        return cls(bi, docs, emb, pp, ce, tok, calib, device, texts)

    def reload_pp(self, pp_csv: str):
        """Новая редакция ПП 1875: подменили CSV — и всё, модель не трогаем."""
        self.pp = PPIndex(pd.read_csv(pp_csv, dtype=str), self.calib.get("pp_url", ""), self.calib.get("pp_edition", ""))

    def reindex_okpd2(self, okpd_df: pd.DataFrame, batch_size: int = 64):
        """Новая редакция ОКПД2: пересчитать эмбеддинги документов (минуты на CPU, без обучения)."""
        self.docs = build_docs(okpd_df)
        self.doc_codes = self.docs["code"].tolist()
        self.doc_text = dict(zip(self.docs["code"], self.docs["doc_text"]))
        self.set_index(None)
        self.doc_emb = self.encode_docs(self.docs["doc_text"].tolist(), batch_size)

    # ---- энкодеры
    def encode_queries(self, texts, batch_size=64):
        return self.bi.encode([self.calib["q_prefix"] + t for t in texts], batch_size=batch_size,
                              normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)

    def encode_docs(self, texts, batch_size=64):
        return self.bi.encode([self.calib["d_prefix"] + t for t in texts], batch_size=batch_size,
                              normalize_embeddings=True, convert_to_numpy=True,
                              show_progress_bar=len(texts) > 2000).astype(np.float32)

    def ce_scores(self, queries: list[str], docs: list[str], batch_size: int = 64) -> np.ndarray:
        import torch
        out = []
        with torch.inference_mode():
            for i in range(0, len(queries), batch_size):
                enc = self.ce_tok(queries[i:i + batch_size], docs[i:i + batch_size], padding=True, truncation=True,
                                  max_length=self.calib["ce_max_len"], return_tensors="pt").to(self.device)
                lg = self.ce(**enc).logits.float()
                out.append((lg[:, 0] if lg.shape[-1] == 1 else lg[:, -1]).cpu().numpy())
        return np.concatenate(out) if out else np.zeros(0, np.float32)

    # ---- поиск ближайших кодов (переопределяется, например, для pgvector)
    def search(self, q: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """q: (n, dim) нормированные эмбеддинги -> (индексы текстов индекса (n, k), косинусы (n, k)), по убыванию."""
        sims = q @ self.doc_emb.T
        k = min(k, sims.shape[1])
        top = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        top = np.take_along_axis(top, np.argsort(-np.take_along_axis(sims, top, 1), 1), 1)
        return top, np.take_along_axis(sims, top, 1)

    def search_codes(self, q: np.ndarray, k: int) -> tuple[list[list[str]], list[np.ndarray], list[list[str]]]:
        """Top-k КОДОВ: у кода с несколькими текстами берётся лучший (как retriever.py бэкенда).
        -> (коды, косинусы, совпавшие тексты) для каждого запроса."""
        n_codes = len(set(self.text_codes))
        k = min(k, n_codes)
        fetch = k * int(self.calib.get("overfetch", 10)) if self.multi else k
        if len(q) > 512:                                   # кусками: матрица сходств 20 тыс. × 100 тыс. — это 8 ГБ
            parts = [self.search_codes(q[i:i + 512], k) for i in range(0, len(q), 512)]
            return tuple(sum((p[j] for p in parts), []) for j in range(3))
        top, sims = self.search(q, fetch)
        codes, scores, matched = [], [], []
        for row, srow in zip(top, sims):
            seen, cc, ss, mm = set(), [], [], []
            for j, s in zip(row, srow):
                c = self.text_codes[j]
                if c not in seen:
                    seen.add(c); cc.append(c); ss.append(s); mm.append(self.texts.at[j, "text"])
                    if len(cc) == k:
                        break
            codes.append(cc); scores.append(np.asarray(ss, np.float32)); matched.append(mm)
        return codes, scores, matched

    # ---- кандидаты и логиты (используется и в калибровке)
    def candidates(self, texts: list[str], use_ce: bool = True, batch_size: int = 64):
        """-> (список кодов-кандидатов, список логитов, имя температуры) для каждого текста."""
        texts = [normalize_text(t) for t in texts]
        q = self.encode_queries(texts, batch_size)
        codes, sims, _ = self.search_codes(q, self.calib["topk"])
        if not (use_ce and self.ce is not None):
            return codes, sims, "T_bi"
        R = self.calib["rerank_k"]
        codes = [cc[:R] for cc in codes]
        qq = [t for t, cc in zip(texts, codes) for _ in cc]
        dd = [self.doc_text[c] for cc in codes for c in cc]
        sc = self.ce_scores(qq, dd, batch_size)
        out, i = [], 0
        for cc in codes:
            out.append(sc[i:i + len(cc)]); i += len(cc)
        return codes, out, "T_ce"

    # ---- основной метод
    def predict(self, texts: list[str], use_ce: bool = True, batch_size: int = 64) -> list[dict]:
        t0 = time.perf_counter()
        codes, logits, tname = self.candidates(texts, use_ce, batch_size)
        T, tau = self.calib[tname], self.calib["tau_auto"]
        name_of = dict(zip(self.docs["code"], self.docs["name"]))
        res = []
        for text, cc, lg in zip(texts, codes, logits):
            p = softmax(lg, T)
            outs = aggregate_outcomes(cc, p, self.pp)
            key, conf = outs[0]
            leaf_i = int(np.argmax([pi if self.pp.outcome(c) == key else -1 for c, pi in zip(cc, p)]))
            res.append({
                "query": text,
                "in_pp1875": key != NONE_KEY,
                "pp_positions": self.pp.describe(key),
                "confidence": round(conf * 100, 1),
                "status": "auto" if conf >= tau else "review",
                "okpd2": cc[leaf_i], "okpd2_name": name_of.get(cc[leaf_i], ""),
                "alternatives": [{"outcome": k, "confidence": round(v * 100, 1)} for k, v in outs[1:3]],
                "top_okpd2": [{"code": c, "name": name_of.get(c, ""), "p": round(float(x) * 100, 1)}
                              for c, x in sorted(zip(cc, p), key=lambda z: -z[1])[:5]],
            })
        dt = time.perf_counter() - t0
        for r in res:
            r["batch_seconds"] = round(dt, 3)
        return res


# ----------------------------------------------------------------------------- «умная проверка» (опционально)
def llm_check(query: str, top_okpd2: list[dict], ollama_url: str | None = None,
              model: str | None = None, timeout: float = 30.0) -> dict | None:
    """
    Опциональная проверка спорных товаров (status == 'review') локальной LLM через Ollama.
    LLM НЕ придумывает код: она выбирает номер из уже найденных кандидатов или 0 («ни один»).
    Если Ollama не поднят (у жюри без GPU) — возвращает None, основной режим не страдает.
    """
    import urllib.request
    ollama_url = ollama_url or os.getenv("OLLAMA_URL")
    model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    if not ollama_url:
        return None
    opts = "\n".join(f"{i + 1}. {c['code']} — {c['name']}" for i, c in enumerate(top_okpd2))
    prompt = (f"Товар из закупочной спецификации: «{query}».\nКандидаты ОКПД2:\n{opts}\n"
              "Выбери номер наиболее точного кода или 0, если ни один не подходит. "
              'Ответ строго JSON: {"choice": <число>, "reason": "<кратко>"}')
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    try:
        req = urllib.request.Request(ollama_url.rstrip("/") + "/api/generate", body,
                                     {"Content-Type": "application/json"})
        ans = json.loads(json.loads(urllib.request.urlopen(req, timeout=timeout).read())["response"])
        ch = int(ans.get("choice", 0))
        return {"choice": top_okpd2[ch - 1]["code"] if 1 <= ch <= len(top_okpd2) else None,
                "reason": ans.get("reason", ""), "model": model}
    except Exception as e:  # LLM — вспомогательная, никогда не роняет основной ответ
        return {"error": str(e)}
