"""Пересчёт эталонных пунктов ПП (appendix_item_expected) в наборах оценки по активной редакции базы НПА.

Пункты по эталонному коду считаются тем же matcher, что и в сервисе (как Expectations.items_of в eval.py).
Нужен после смены базы: эталоны прошлой базы ссылаются на исключённые позиции (прил. 2 поз. 109, 111, 112)
и не знают подпунктов вида 388(1). Код и вердикт эталона не меняются; если по новой базе вердикт кода
другой, строка только печатается — решать человеку. holdout.csv не трогать: он для финального замера.

Запуск: docker compose run --rm -v ./backend:/app -v ./data:/datarw api \\
        python scripts/relabel_npa_items.py /datarw/eval/dev.csv /datarw/eval/testset.csv [--write]
"""
import argparse
import csv
from pathlib import Path

from scripts.eval import Expectations


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", type=Path, nargs="+")
    p.add_argument("--write", action="store_true", help="записать изменения (иначе только показать)")
    a = p.parse_args()
    exp = Expectations()
    for path in a.files:
        if path.name.startswith("holdout"):
            raise SystemExit("holdout.csv не пересчитывается: он для финального замера")
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
        fields = list(rows[0].keys())
        changed = 0
        for r in rows:
            items = exp.items_of(r["okpd2_expected"])
            new = " ".join(sorted(items))
            if items != set(r["appendix_item_expected"].split()):  # eval сравнивает множества: порядок не трогаем
                changed += 1
                print(f"{path.name}: {r['name'][:50]:50} | {r['okpd2_expected']:13} | {r['appendix_item_expected'] or '—'} -> {new or '—'}")
                r["appendix_item_expected"] = new
            regimes = exp.verdicts(r["okpd2_expected"])
            if r["regime_expected"] not in regimes:
                print(f"  ! вердикт эталона «{r['regime_expected']}» не совпадает с новой базой {sorted(regimes)}: {r['name'][:60]}")
        print(f"{path.name}: изменено {changed} из {len(rows)}")
        if a.write and changed:
            with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, delimiter=";", lineterminator="\n")
                w.writeheader()
                w.writerows(rows)


if __name__ == "__main__":
    main()
