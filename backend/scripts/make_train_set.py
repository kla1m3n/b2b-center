"""Синтетическая обучающая выборка для дообучения модели поиска → data/train/synthetic.csv.

Пары «запрос → текст кода ОКПД2» с трудным негативом — под то же обучение, что у BOBUS2317/e5-large-pp1875
(InfoNCE, префиксы «query: » к запросу и «passage: » к текстам кодов добавляет ноутбук обучения).

Источники запросов (колонка source):
  title    — официальное наименование кода нижнего уровня без «прочие», уточнений в скобках и хвоста после «;»;
  synonym  — бытовые названия из data/okpd2_synonyms.csv;
  seed     — наименования «как в закупках» из scripts/train_seed.py;
  aug_*    — искажения как в реальных спецификациях: шаблоны ЕИС (aug_boiler), артикул (aug_specs), количество
             (aug_qty), ГОСТ (aug_gost), опечатка (aug_typo), ЗАГЛАВНЫЕ (aug_upper). Делаются для synonym/seed
             и для title кодов из приложений ПП 1875 — их ошибка меняет вердикт.

positive — официальное наименование кода (как в индексе поиска). Трудный негатив — код нижнего уровня
из той же группы (самый длинный общий префикс), в половине случаев с другим режимом ПП: «соседний код,
другой вердикт» — самая дорогая ошибка.

Защита от утечки: запрос выбрасывается, если после нормализации совпадает с наименованием из data/eval/*.csv
или делит с ним ≥ 70% слов. Наборы оценки при этом не печатаются (holdout не смотрим до финального замера).
Запрос, попавший на несколько кодов, выбрасывается целиком. split=val — ~5% кодов (по хэшу кода):
проверка обучения на кодах, которых модель не видела.

--extra — добавить готовые пары из других источников: CSV через запятую с колонками text и okpd2 (или code),
необязательно source (например, КТРУ и синтетика из ноутбука обучения). Они проходят те же фильтры: утечка,
несколько кодов, дубли; код группы КТРУ (XX.XX.XX.000) заменяется кодом нижнего уровня, если он в группе один.

Запуск (нужен пакет app, поэтому в образе backend):
  docker run --rm -v ./backend:/app -v ./data:/data pp1875-backend python scripts/make_train_set.py
  ... python scripts/make_train_set.py --extra /extra/train_pairs.csv /extra/synth.csv --out /data/train/train_full.csv
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.classifier.matcher import code_covers  # noqa: E402
from gen_synonyms import resolve  # noqa: E402
from train_seed import SEED  # noqa: E402

LEAK_JACCARD = 0.7
VAL_SHARE = 20  # каждый 20-й код (по хэшу) — в val
AUG_PP, AUG_OTHER = 3, 1  # искажений на запрос: коды из ПП / остальные (у title остальных — без искажений)

_TOKEN = re.compile(r"[a-zа-я0-9]+")
_NOISE = re.compile(r",?\s*\b(не включенн\w* в другие группировки|прочие|прочая|прочий|прочее)\b", re.IGNORECASE)
_WORD = re.compile(r"[А-Яа-яЁё]{5,}")
REGIMES = {1: "ban", 2: "restriction", 3: "advantage"}

BOILER = [
    "Поставка {}",
    "Поставка товара: {} (или эквивалент)",
    "{} (или эквивалент)",
    "Закупка: {}",
    "{} для нужд учреждения",
    "Товар: {}. Характеристики — согласно техническому заданию",
    "{} в ассортименте",
    "Приобретение {}",
]


def tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower().replace("ё", "е")))


def short_title(title: str) -> str:
    t = title.split(";")[0]
    t = re.sub(r"\s*\([^)]*\)", "", t)
    t = _NOISE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" ,.:-")


def typo(name: str, rng: random.Random) -> str | None:
    words = list(_WORD.finditer(name))
    if not words:
        return None
    m = rng.choice(words)
    w, i = m.group(), rng.randrange(1, len(m.group()) - 2)
    kind = rng.choice(["swap", "drop", "double"])
    if kind == "swap":
        w = w[:i] + w[i + 1] + w[i] + w[i + 2:]
    elif kind == "drop":
        w = w[:i] + w[i + 1:]
    else:
        w = w[:i] + w[i] + w[i:]
    return name[: m.start()] + w + name[m.end():]


def article(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEHKMPTX") for _ in range(rng.randint(1, 3)))
    return f"{letters}-{rng.randint(100, 99999)}"


AUGMENT = {
    "aug_boiler": lambda n, r: r.choice(BOILER).format(n[0].lower() + n[1:] if r.random() < 0.5 else n),
    "aug_specs": lambda n, r: f"{n}, арт. {article(r)}",
    "aug_qty": lambda n, r: r.choice(["{} — {} шт.", "{1} шт. {0}", "{}, {} уп.", "{}; кол-во: {}"]).format(
        n, r.choice([1, 2, 5, 10, 20, 50, 100])),
    "aug_gost": lambda n, r: f"{n} ГОСТ {r.randint(1000, 34999)}-{r.choice([2013, 2014, 2015, 2017, 2019, 2021])}",
    "aug_typo": typo,
    "aug_upper": lambda n, r: n.upper(),
}


def regimes(leaves: list[str], items: list[dict]) -> dict[str, str]:
    by_class: dict[str, list[str]] = defaultdict(list)  # перебираем только коды того же класса (2 цифры)
    for code in leaves:
        by_class[code[:2]].append(code)
    best: dict[str, int] = {}
    for it in items:
        for p in it["codes"]:
            for code in by_class[p[:2]]:
                if code_covers(p, code) and not any(code_covers(x, code) for x in it["exclusions"]):
                    best[code] = min(best.get(code, 9), it["appendix"])
    return {c: REGIMES.get(best.get(c), "none") for c in leaves}


def hard_negative(code: str, regime: dict[str, str], by_prefix: dict[str, list[str]], rng: random.Random) -> str | None:
    digits = code.replace(".", "")
    nearest, other_regime = None, None
    for n in (8, 6, 5, 4):
        # категория и её подкатегории — по ПП один и тот же ответ, такой «негатив» учил бы модель неправде
        sib = [c for c in by_prefix.get(digits[:n], []) if not code_covers(c, code) and not code_covers(code, c)]
        nearest = nearest or sib
        other_regime = other_regime or [c for c in sib if regime[c] != regime[code]]
    pool = other_regime if other_regime and rng.random() < 0.5 else nearest
    return rng.choice(pool) if pool else None


def load_eval(eval_dir: Path) -> list[frozenset[str]]:
    out = []
    for path in sorted(eval_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                name = row.get("name") or next((v for k, v in row.items() if k and k.startswith("Наименование")), "")
                if name:
                    out.append(tokens(name))
    return out


class LeakGuard:
    def __init__(self, names: list[frozenset[str]]):
        self.names = names
        self.exact = set(names)
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, t in enumerate(names):
            for w in t:
                self.postings[w].append(i)

    def leaks(self, q: frozenset[str]) -> bool:
        if q in self.exact:
            return True
        cand = {i for w in q for i in self.postings.get(w, ())}
        return any(len(q & self.names[i]) / len(q | self.names[i]) >= LEAK_JACCARD for i in cand)


def load_extra(paths: list[Path], leaves: list[str], by_prefix: dict[str, list[str]]) -> tuple[list, Counter]:
    """Пары (код, текст, источник) из CSV --extra; код группы → единственный код нижнего уровня в ней."""
    leaf_set, out, skipped = set(leaves), [], Counter()
    for path in paths:
        with path.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                code, text = (r.get("okpd2") or r.get("code") or "").strip(), (r.get("text") or "").strip()
                if code not in leaf_set:
                    group = by_prefix.get(code.removesuffix(".000").replace(".", ""), [])
                    if len(group) != 1:
                        skipped[f"{path.stem}: код группы без единственного кода нижнего уровня"] += 1
                        continue
                    code = group[0]
                out.append((code, text, r.get("source") or path.stem))
    return out, skipped


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--out", type=Path, default=None, help="по умолчанию <data>/train/synthetic.csv")
    p.add_argument("--seed", type=int, default=1875)
    p.add_argument("--extra", type=Path, nargs="*", default=[], help="CSV с колонками text, okpd2|code[, source]")
    a = p.parse_args()
    rng = random.Random(a.seed)

    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    title = {r["code"]: r["title"] for r in rows}
    leaves = [r["code"] for r in rows if r["is_leaf"] == "1"]
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for c in leaves:
        d = c.replace(".", "")
        for n in (4, 5, 6, 8, 9):
            by_prefix[d[:n]].append(c)
    items = json.loads((a.data / "npa" / "pp1875.json").read_text(encoding="utf-8"))["items"]
    regime = regimes(leaves, items)

    base: list[tuple[str, str, str]] = []  # (код, запрос, источник)
    for c in leaves:
        base.append((c, short_title(title[c]), "title"))
    with (a.data / "okpd2_synonyms.csv").open(encoding="utf-8") as f:
        base += [(r["code"], r["text"], "synonym") for r in csv.DictReader(f, delimiter=";") if r["code"] in regime]
    unresolved = 0
    for prefix, pattern, names in SEED:
        codes = resolve(rows, prefix, pattern)
        if not codes:
            unresolved += 1
            continue
        base += [(codes[0], n, "seed") for n in names]
    extra, skipped = load_extra(a.extra, leaves, by_prefix)
    n_own = len(base)
    base += extra

    pairs = []
    for i, (code, text, source) in enumerate(base):
        if not text:
            continue
        pairs.append((code, text, source))
        in_pp = regime[code] != "none"
        if i >= n_own:  # готовые пары: одно искажение и только для кодов из ПП, чтобы не раздувать выборку
            n_aug = 1 if in_pp else 0
        else:
            n_aug = AUG_PP if in_pp else (AUG_OTHER if source != "title" else 0)
        for kind in rng.sample(list(AUGMENT), n_aug):
            variant = AUGMENT[kind](text, rng)
            if variant and variant != text:
                pairs.append((code, variant, kind))

    guard = LeakGuard(load_eval(a.data / "eval"))
    by_text: dict[frozenset[str], set[str]] = defaultdict(set)
    for code, text, _ in pairs:
        by_text[tokens(text)].add(code)
    dropped = Counter()
    seen, out = set(), []
    for code, text, source in pairs:
        key = tokens(text)
        if not key:
            continue
        if len(by_text[key]) > 1:
            dropped["несколько кодов"] += 1
            continue
        if guard.leaks(key):
            dropped[f"похоже на наборы оценки ({source})"] += 1
            continue
        exact = re.sub(r"\s+", " ", text).strip()  # регистр не трогаем: «ЗАГЛАВНЫЕ» — отдельный вариант для модели
        if (exact, code) in seen:
            dropped["дубль"] += 1
            continue
        seen.add((exact, code))
        neg = hard_negative(code, regime, by_prefix, rng)
        split = "val" if int(hashlib.md5(code.encode()).hexdigest()[:8], 16) % VAL_SHARE == 0 else "train"
        out.append({"query": text, "code": code, "positive": title[code], "negative_code": neg or "",
                    "negative": title[neg] if neg else "", "regime": regime[code], "source": source, "split": split})

    out_path = a.out or a.data / "train" / "synthetic.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), delimiter=";")
        w.writeheader()
        w.writerows(out)

    codes = {r["code"] for r in out}
    print(f"{out_path}: {len(out)} пар, кодов {len(codes)} из {len(leaves)}, "
          f"из них в ПП {sum(regime[c] != 'none' for c in codes)} из {sum(v != 'none' for v in regime.values())}")
    print("  по источникам:", dict(Counter(r["source"] for r in out).most_common()))
    print("  по режимам:", dict(Counter(r["regime"] for r in out).most_common()))
    print("  split:", dict(Counter(r["split"] for r in out)), "| без негатива:", sum(not r["negative_code"] for r in out))
    print("  выброшено:", dict(dropped.most_common()), "| несопоставленных записей seed:", unresolved)
    if skipped:
        print("  не взято из --extra:", dict(skipped))


if __name__ == "__main__":
    main()
