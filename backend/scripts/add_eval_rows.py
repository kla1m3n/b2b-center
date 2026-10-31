"""Пополнение наборов оценки позициями реальных закупок, не трогая уже размеченные строки.

Вход — CSV в формате data/eval/zakupki_raw.csv (Наименование;Код ОКПД2;Ссылка;Сфера), например выгрузка
scripts/fetch_eis_notices.py. Отбор:
  - код есть в справочнике ОКПД2;
  - не утечка: наименование не совпадает (≥ 70% общих слов) ни с обучающими текстами (--train: train_pairs.csv,
    train_v2.csv, synth.csv… — колонка text), ни с позициями, уже лежащими в data/eval/*.csv;
  - не больше --max-per-code позиций на код и --per-sphere на сферу — набор не заполнят однотипные строки.
Отобранные делятся по сферам: --dev-share в dev.csv, остальные в holdout.csv (дописываются в конец). Эталонные
вердикт и пункты ПП — тем же matcher, что в сервисе. Выбранные строки добавляются и в zakupki_raw.csv.

    docker compose run --rm -v ./backend:/app -v ./data:/datarw -v <папка с обучающими CSV>:/train:ro api \\
        python scripts/add_eval_rows.py --raw /datarw/train/eis_notices.csv \\
        --train /train/train_pairs.csv /train/train_v2.csv /train/okpd2_generated_raw.csv --per-sphere 60 [--dry-run]

holdout.csv скрипт не читает построчно для отчёта и не показывает: только дописывает новые строки и использует
наименования всех наборов для защиты от дублей.
"""
import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.classifier.matcher import match, verdict  # noqa: E402
from app.npa.parser import parse_npa  # noqa: E402
from make_train_set import LeakGuard, load_eval, tokens  # noqa: E402

FIELDS = ["name", "okpd2_expected", "regime_expected", "appendix_item_expected", "sphere", "source"]
MIN_WORDS = 2  # «Бумага», «Товар» — не наименование закупки


def read_train(paths: list[Path]) -> list[frozenset[str]]:
    out = []
    for path in paths:
        with path.open(encoding="utf-8-sig") as f:
            header = f.readline()
            f.seek(0)
            reader = csv.DictReader(f, delimiter=";" if header.count(";") > header.count(",") else ",")
            col = next((c for c in ("text", "name", "query") if c in (reader.fieldnames or [])), None)
            if col is None:
                sys.exit(f"{path}: нет колонки text/name/query")
            out += [tokens(r[col]) for r in reader if r.get(col)]
    return out


def labeled(name: str, code: str, sphere: str, url: str, items) -> dict:
    found = match(code, items)
    return {"name": name, "okpd2_expected": code, "regime_expected": verdict(found).value,
            "appendix_item_expected": " ".join(sorted(f"{m.appendix}:{m.item_no}" for m in found)),
            "sphere": sphere, "source": url}


def select(rows: list[list[str]], known: set[str], guard: LeakGuard, per_sphere: int, max_per_code: int,
           rng: random.Random) -> tuple[list[list[str]], Counter]:
    """Отбор позиций: справочник, длина, утечки, дубли, лимиты на код и сферу. Порядок — случайный (seed)."""
    rng.shuffle(rows)
    why, picked, per_code, per_sph, taken = Counter(), [], Counter(), Counter(), set()
    for r in rows:
        name, code, sphere = r[0], r[1], r[3]
        key = tokens(name)
        if code not in known:
            why["кода нет в справочнике"] += 1
        elif len(key) < MIN_WORDS:
            why["короткое наименование"] += 1
        elif key in taken:
            why["дубль в выгрузке"] += 1
        elif guard.leaks(key):
            why["похоже на обучение или наборы оценки"] += 1
        elif per_code[code] >= max_per_code:
            why["лимит на код"] += 1
        elif per_sph[sphere] >= per_sphere:
            why["лимит на сферу"] += 1
        else:
            picked.append(r)
            taken.add(key)
            per_code[code] += 1
            per_sph[sphere] += 1
    return picked, why


def split(picked: list[list[str]], dev_share: float) -> tuple[list[list[str]], list[list[str]]]:
    by_sphere = defaultdict(list)
    for r in picked:
        by_sphere[r[3]].append(r)
    dev, holdout = [], []
    for sphere in sorted(by_sphere):
        group = by_sphere[sphere]
        k = round(len(group) * dev_share)
        dev += group[:k]
        holdout += group[k:]
    return dev, holdout


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--train", type=Path, nargs="*", default=[], help="обучающие CSV для защиты от утечки")
    p.add_argument("--data", type=Path, default=Path("/datarw"))
    p.add_argument("--per-sphere", type=int, default=60)
    p.add_argument("--max-per-code", type=int, default=2)
    p.add_argument("--dev-share", type=float, default=0.7)
    p.add_argument("--seed", type=int, default=1875)
    p.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не записывать")
    a = p.parse_args()

    ev = a.data / "eval"
    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        known = {r["code"] for r in csv.DictReader(f, delimiter=";")}
    items = parse_npa(a.data / "npa" / "pp1875.json").items
    guard = LeakGuard(load_eval(ev) + read_train(a.train))
    with a.raw.open(encoding="utf-8-sig") as f:
        rows = [[x.strip() for x in r[:4]] for r in csv.reader(f, delimiter=";")
                if len(r) >= 4 and r[0].strip() and not r[0].startswith("Наименование")]

    picked, why = select(rows, known, guard, a.per_sphere, a.max_per_code, random.Random(a.seed))
    dev, holdout = split(picked, a.dev_share)
    print(f"в выгрузке {len(rows)}; отобрано {len(picked)} → dev +{len(dev)}, holdout +{len(holdout)}")
    print("отброшено:", dict(why))
    print("по сферам (dev):", dict(Counter(r[3] for r in dev)))
    if a.dry_run:
        return
    for name, part in (("dev.csv", dev), ("holdout.csv", holdout)):
        with (ev / name).open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", lineterminator="\n")
            w.writerows(labeled(r[0], r[1], r[3], r[2], items) for r in part)
    with (ev / "zakupki_raw.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=";", lineterminator="\n").writerows([r[0], r[1], r[2], r[3]] for r in picked)
    print(f"дописано: dev.csv +{len(dev)}, holdout.csv +{len(holdout)}, zakupki_raw.csv +{len(picked)}")


if __name__ == "__main__":
    main()
