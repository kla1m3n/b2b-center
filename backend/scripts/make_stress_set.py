"""Стресс-набор: варианты наименований из testset.csv так, как их пишут в реальных спецификациях.

Эталоны копируются из исходной строки — вручную ничего не размечается, поэтому набор проверяет именно
устойчивость классификатора к «грязному» вводу, а не чьё-то мнение о правильном коде.

Варианты (детерминированно, без случайности):
  typo_swap  — переставлены две соседние буквы в самом длинном слове («нотубук»);
  typo_drop  — пропущена буква в самом длинном слове;
  specs      — дописаны артикул и количество: «…, арт. KX-2041, 5 шт.»;
  qty_first  — количество и единица в начале: «10 шт. …»;
  boiler     — шаблоны ЕИС: «Поставка товара: … (или эквивалент)»;
  upper      — ЗАГЛАВНЫМИ БУКВАМИ.

Запуск: python scripts/make_stress_set.py --data /data   →   data/eval/stress.csv
"""
import argparse
import csv
import re
from pathlib import Path

_WORD = re.compile(r"[А-Яа-яЁё]{5,}")


def _longest_word(name: str) -> re.Match | None:
    words = list(_WORD.finditer(name))
    return max(words, key=lambda m: len(m.group())) if words else None


def typo_swap(name: str) -> str | None:
    m = _longest_word(name)
    if not m:
        return None
    w = m.group()
    i = len(w) // 2
    return name[: m.start()] + w[: i - 1] + w[i] + w[i - 1] + w[i + 1:] + name[m.end():]


def typo_drop(name: str) -> str | None:
    m = _longest_word(name)
    if not m:
        return None
    w = m.group()
    i = len(w) // 2
    return name[: m.start()] + w[:i] + w[i + 1:] + name[m.end():]


VARIANTS = {
    "typo_swap": typo_swap,
    "typo_drop": typo_drop,
    "specs": lambda n: f"{n}, арт. KX-2041, 5 шт.",
    "qty_first": lambda n: f"10 шт. {n}",
    "boiler": lambda n: f"Поставка товара: {n} (или эквивалент)",
    "upper": lambda n: n.upper(),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--src", default="testset.csv")
    p.add_argument("--out", default="stress.csv")
    a = p.parse_args()
    src, out = a.data / "eval" / a.src, a.data / "eval" / a.out
    with src.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    fields = list(rows[0].keys()) + ["variant"]
    result = []
    for r in rows:
        for kind, make in VARIANTS.items():
            name = make(r["name"])
            if name and name != r["name"]:
                result.append({**r, "name": name, "variant": kind})
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(result)
    print(f"{out}: {len(result)} вариантов из {len(rows)} наименований")


if __name__ == "__main__":
    main()
