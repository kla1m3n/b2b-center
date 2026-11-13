"""Аудит разметки обучающих файлов: где коды противоречат друг другу, КТРУ и наборам оценки.

Три проверки (отчёт — audit/*.csv, в обучение ничего не пишет):
  1. medical   — в тексте признаки медизделия, а код не из медицинских разделов (32.50, 21.20, 26.60, 22.19.60);
  2. conflicts — одно и то же наименование (после нормализации) с разными кодами в разных строках;
  3. eval      — наименования, близкие к товарам dev/testset/validation (правило clean_extra), и какие коды им
                 ставит обучение против эталона: видно, где данные учат не тому, что проверяет оценка.

    python data_build/audit_labels.py --core kaggle_dataset --eval ../../data/eval --validation <validation.csv> \
        --out audit train_v2.csv train_pairs.csv ktru.csv synth_weak.csv
"""
import argparse
import collections
import os
import re
import sys

import pandas as pd

MED_CODE = ("32.50", "21.20", "26.60", "22.19.60")
MED_TEXT = re.compile(
    r"медицинск|хирургич|стоматолог|катетер|дренаж|зонд\b|шприц|игл\w* инъекц|инфузи|трансфузи|имплант|эндопротез|"
    r"стерильн|перевязоч|бинт|лейкопластыр|шовн\w* материал|скальпел|пинцет\w* (хирург|анатом)|ив[дл]\b|"
    r"для гемодиализ|уретральн|интубац|трахеостом|канюл|стент|электрокардио|дефибриллят|ингалятор|небулайзер|"
    r"тонометр|глюкометр|термометр\w* медиц|пульсоксиметр|рентген|узи\b|ультразвуков\w* диагност", re.IGNORECASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--validation", default="")
    ap.add_argument("--out", default="audit")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    sys.path.insert(0, a.core)
    import pp1875_core as core

    norm = lambda s: " ".join(re.findall(r"[a-zа-я0-9]+", core.normalize_text(str(s)).lower().replace("ё", "е")))
    frames = []
    for f in a.files:
        df = pd.read_csv(f, dtype=str, sep=None, engine="python", encoding="utf-8-sig", keep_default_na=False)
        t = next(c for c in ("text", "query", "name") if c in df.columns)
        c = next(c for c in ("okpd2", "code") if c in df.columns)
        src = df["source"] if "source" in df.columns else ""
        frames.append(pd.DataFrame({"file": os.path.basename(f), "row": df.index + 2, "text": df[t], "code": df[c],
                                    "source": src}))
    d = pd.concat(frames, ignore_index=True)
    d = d[d["code"].str.match(r"^\d{2}\.\d{2}")]
    d["norm"] = d["text"].map(norm)
    os.makedirs(a.out, exist_ok=True)
    print(f"строк {len(d)}, файлов {d['file'].nunique()}")

    # 1. медизделие по тексту, код не медицинский
    med = d[d["text"].str.contains(MED_TEXT) & ~d["code"].str.startswith(MED_CODE)]
    g = med.groupby(["code"]).agg(rows=("text", "size"), files=("file", lambda s: ",".join(sorted(set(s)))),
                                  sources=("source", lambda s: ",".join(sorted(set(s)))),
                                  example=("text", "first")).sort_values("rows", ascending=False)
    g.to_csv(os.path.join(a.out, "medical_nonmedical_code.csv"), encoding="utf-8-sig")
    print(f"\n1. признаки медизделия + немедицинский код: {len(med)} строк, {len(g)} кодов")
    print(g.head(25).to_string(max_colwidth=60))

    # 2. одно наименование — разные коды
    n_codes = d.groupby("norm")["code"].nunique()
    conf = d[d["norm"].isin(n_codes[n_codes > 1].index) & (d["norm"].str.len() > 3)]
    c2 = conf.groupby("norm").agg(codes=("code", lambda s: " ".join(f"{k}×{v}" for k, v in s.value_counts().items())),
                                  rows=("code", "size"), files=("file", lambda s: ",".join(sorted(set(s)))))
    c2 = c2.sort_values("rows", ascending=False)
    c2.to_csv(os.path.join(a.out, "same_text_different_codes.csv"), encoding="utf-8-sig")
    print(f"\n2. одинаковое наименование с разными кодами: {len(c2)} наименований, {len(conf)} строк")
    print(c2.head(15).to_string(max_colwidth=70))

    # 3. рядом с товарами наборов оценки
    ev = []
    for f in ["dev.csv", "testset.csv"]:
        e = pd.read_csv(os.path.join(a.eval, f), sep=";", dtype=str)
        ev += [(f, n, c) for n, c in zip(e["name"], e["okpd2_expected"])]
    if a.validation:
        e = pd.read_csv(a.validation, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        nc = next(c for c in ("okpd2_expected", "okpd2", "code") if c in e.columns)
        ev += [("validation", n, c) for n, c in zip(e[next(c for c in ("name", "text") if c in e.columns)], e[nc])]
    tok = lambda s: set(norm(s).split())
    T = [tok(x) for x in d["norm"]]
    inv = collections.defaultdict(list)
    for j, w in enumerate(T):
        for x in w:
            inv[x].append(j)
    rows = []
    for f, name, gold in ev:
        e = tok(name)
        if not e:
            continue
        cnt = collections.Counter(j for x in e for j in inv.get(x, ()))
        # обучающая строка содержит почти все слова товара (товар короче): «Трубка дренажная нестерильная, диаметр 6»
        near = [j for j, c in cnt.items() if c >= max(2, 0.8 * len(e)) or (len(e) == 1 and T[j] == e)]
        if not near:
            continue
        codes = d.iloc[near]["code"].value_counts()
        g4 = str(gold).rstrip("0").rstrip(".")
        agree = int(sum(v for k, v in codes.items() if k.startswith(g4) or str(gold).startswith(k)))
        rows.append({"set": f, "name": name, "gold": gold, "train_rows": len(near), "agree": agree,
                     "share": round(agree / len(near), 2), "top_train_codes": " ".join(f"{k}×{v}" for k, v in codes.head(4).items())})
    r = pd.DataFrame(rows).sort_values(["share", "train_rows"], ascending=[True, False])
    r.to_csv(os.path.join(a.out, "eval_vs_train.csv"), index=False, encoding="utf-8-sig")
    bad = r[(r["share"] < 0.5) & (r["train_rows"] >= 3)]
    print(f"\n3. товаров оценки с похожими строками в обучении: {len(r)}; обучение в основном против эталона: {len(bad)}")
    print(bad.head(40).to_string(max_colwidth=55, index=False))


if __name__ == "__main__":
    main()
