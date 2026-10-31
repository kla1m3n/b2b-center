"""Доп. файлы обучения (synth_weak.csv, ktru.csv) -> без утечки в наборы оценки, перед загрузкой в датасет Kaggle.

Ноутбук сам убирает только дословные совпадения с dev/тестом. Синтетика по слабым темам и КТРУ пишутся ровно про те
товары, на которых модель ошибается, поэтому почти-дубли («перчатки нитриловые медицинские» ~ «перчатки медицинские
нитриловые») завышали бы dev и выбор эпохи. Правило то же, что в clean_v2.py: строка — утечка, если в ней есть
>= 70% слов товара из оценки и эти слова — >= 50% слов строки.

    python data_build/clean_extra.py --core kaggle_dataset --eval ../../data/eval --validation <validation.csv> \
        synth_weak.csv ktru.csv          # пишет clean/synth_weak.csv, clean/ktru.csv (имена и колонки те же)
"""
import argparse
import collections
import os
import re
import sys

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True, help="папка с pp1875_core.py")
    ap.add_argument("--eval", required=True, help="data/eval репозитория: dev, testset, stress, holdout")
    ap.add_argument("--validation", default="", help="validation.csv (колонка text) — тоже набор оценки")
    ap.add_argument("--out-dir", default="clean", help="куда писать очищенные файлы (имена те же — их ждёт TRAIN_FILES)")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    sys.path.insert(0, a.core)
    import pp1875_core as core

    tok = lambda s: set(re.findall(r"[a-zа-я0-9]+", core.normalize_text(str(s)).lower().replace("ё", "е")))
    ev = []
    for f in ["dev.csv", "testset.csv", "stress.csv", "holdout.csv"]:
        p = os.path.join(a.eval, f)
        if os.path.exists(p):
            ev += pd.read_csv(p, sep=";", dtype=str)["name"].dropna().tolist()
    if a.validation:
        ev += pd.read_csv(a.validation, dtype=str, encoding="utf-8-sig")["text"].dropna().tolist()
    E = [w for w in map(tok, ev) if w]
    inv = collections.defaultdict(list)
    for j, w in enumerate(E):
        for x in w:
            inv[x].append(j)
    print(f"Наборов оценки: {len(E)} наименований")

    def leaky(q):
        T = tok(q)
        if not T:
            return False
        cnt = collections.Counter(j for x in T for j in inv.get(x, ()))
        for j, c in cnt.items():
            e = E[j]
            if len(e) == 1:
                if T == e:
                    return True
            elif c >= 0.7 * len(e) and c >= 0.5 * len(T):
                return True
        return False

    for f in a.files:
        df = pd.read_csv(f, dtype=str, sep=None, engine="python", encoding="utf-8-sig", keep_default_na=False)
        col = next(c for c in ("text", "query", "name") if c in df.columns)
        leak = df[col].map(leaky)
        os.makedirs(a.out_dir, exist_ok=True)
        out = os.path.join(a.out_dir, os.path.basename(f))
        df[~leak].to_csv(out, index=False)
        print(f"{f}: {len(df)} -> {int((~leak).sum())} строк (убрано близких к оценке: {int(leak.sum())}) -> {out}")
        for s in df.loc[leak, col].head(5):
            print("   пример:", s[:90])


if __name__ == "__main__":
    main()
