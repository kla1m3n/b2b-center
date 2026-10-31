"""train_full.csv (v2) -> train_v2.csv для ноутбука: строже убрать утечку в eval-наборы, лишние тождественные пары."""
import collections, re, sys
import pandas as pd
sys.path.insert(0, sys.argv[1]); import pp1875_core as core
src, out, eval_dir, extra_eval = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
t = pd.read_csv(src, sep=";", dtype=str, keep_default_na=False)
n0 = len(t)
tok = lambda s: set(re.findall(r"[a-zа-я0-9]+", core.normalize_text(s).lower().replace("ё", "е")))
ev = []
for f in ["dev.csv", "testset.csv", "stress.csv", "holdout.csv"]:
    ev += pd.read_csv(f"{eval_dir}/{f}", sep=";", dtype=str)["name"].tolist()
ev += pd.read_csv(extra_eval, dtype=str, encoding="utf-8-sig")["text"].tolist()
E = [tok(x) for x in ev if tok(x)]
inv = collections.defaultdict(list)
for j, w in enumerate(E):
    for x in w: inv[x].append(j)
def leaky(q, source):
    T = tok(q)
    if not T or source == "title":            # наименования кодов — часть справочника, не утечка
        return False
    cnt = collections.Counter(j for x in T for j in inv.get(x, ()))
    for j, c in cnt.items():
        e = E[j]
        if len(e) == 1:
            if T == e: return True
        elif c >= 0.7 * len(e) and c >= 0.5 * len(T):
            return True
    return False
t["leak"] = [leaky(q, s) for q, s in zip(t["query"], t["source"])]
n_leak = int(t["leak"].sum()); bysrc = t[t["leak"]].source.value_counts().to_dict()
t = t[~t["leak"]]
# «наименование кода -> то же наименование»: оставить только для кодов без других примеров
other = set(t.loc[t["source"] != "title", "code"])
n_title = int(((t["source"] == "title") & t["code"].isin(other)).sum())
t = t[~((t["source"] == "title") & t["code"].isin(other))]
t = t.drop_duplicates(["query", "code"])
o = pd.DataFrame({"text": t["query"], "okpd2": t["code"], "negative_code": t["negative_code"],
                  "source": "v2_" + t["source"]})
o.to_csv(out, index=False)
print(f"{n0} строк -> {len(o)} | убрано близких к dev/test/stress/holdout/validation: {n_leak} {bysrc} | "
      f"тождественных «наименование -> наименование» у кодов с другими примерами: {n_title} | кодов: {o.okpd2.nunique()}")
print(o.source.value_counts().to_string())
