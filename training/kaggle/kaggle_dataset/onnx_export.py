"""
ONNX + int8 для модели из artifacts/: экспорт, квантизация, замер скорости на CPU, совпадение векторов и точность.
Запускается последней ячейкой ноутбука отдельным процессом (после установки sentence-transformers[onnx]).
Результат: папка <модель>-onnx/ с int8-файлом, раздел "onnx" в metrics.json, обновлённый artifacts.zip.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.getcwd())
from pp1875_core import NONE_KEY, PP1875Classifier  # noqa: E402


def covers(parent, code):
    """Правило иерархии бэкенда (matcher.code_covers): префикс цифр + категория/группа с нулями в конце."""
    p, c = parent.replace(".", ""), code.replace(".", "")
    if c.startswith(p):
        return True
    if len(p) != 9 or len(c) != 9 or not p.endswith("0"):
        return False
    k = 6 + len(p[6:].rstrip("0"))
    return c[:k] == p[:k]


def verdict_of(key):
    return 0 if key in (None, NONE_KEY) else min(int(k[1:].split(".")[0]) for k in key.split("|"))


def evaluate(clf, df, leaves, pp):
    """code_top1 и verdict — как в ноутбуке (вердикт как в eval.py бэкенда)."""
    if df is None or not len(df):
        return {}
    codes, logits, _ = clf.candidates(df["text"].tolist(), use_ce=False)
    c1 = vr = 0
    for cc, lg, g in zip(codes, logits, df["code"]):
        best = cc[int(np.argmax(lg))]
        golds = [g] if g in leaves else [l for l in leaves if covers(g, l)] or [g]
        c1 += covers(g, best)
        vr += verdict_of(pp.outcome(best)) in {verdict_of(pp.outcome(x)) for x in golds}
    return {"code_top1": round(c1 / len(df), 4), "verdict": round(vr / len(df), 4)}


def mb(*patterns):
    return sum(os.path.getsize(f) for p in patterns for f in glob.glob(p)) / 2**20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--qconfig", default="avx2")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--pool", type=int, default=50)
    ap.add_argument("--val", required=True)
    ap.add_argument("--test", required=True)
    a = ap.parse_args()

    import torch
    import sentence_transformers
    from sentence_transformers import SentenceTransformer, export_dynamic_quantized_onnx_model
    torch.set_num_threads(a.threads)
    print(f"sentence-transformers {sentence_transformers.__version__}, torch {torch.__version__}")

    A, name = a.art.rstrip("/"), a.model_dir
    src, onnx_dir = f"{A}/{name}", f"{A}/{name}-onnx"
    clf = PP1875Classifier.load(A, device="cpu")                        # PyTorch fp32 на CPU + индекс из ноутбука
    qp, dp = clf.calib["q_prefix"], clf.calib["d_prefix"]
    pp, leaves = clf.pp, set(clf.docs["code"])
    val, test = pd.read_pickle(a.val), pd.read_pickle(a.test)

    # 1. Экспорт в ONNX (fp32) и int8-квантизация
    m_fp32 = SentenceTransformer(src, backend="onnx", device="cpu")
    m_fp32.save(onnx_dir)
    try:
        export_dynamic_quantized_onnx_model(m_fp32, a.qconfig, onnx_dir)                 # веса в ~4 раза меньше
    except Exception as e:                       # модель > 2 ГБ (e5-large fp32) — квантуем через onnxruntime напрямую
        print("Квантизация через sentence-transformers не прошла:", str(e)[:200], "-> onnxruntime")
        from onnxruntime.quantization import QuantType, quantize_dynamic
        # имя как у sentence-transformers — по суффиксу файл выбирает pick_onnx_file бэкенда;
        # int8 e5-large ~560 МБ < 2 ГБ, поэтому одним файлом (download_models качает только onnx/*int8*.onnx)
        u8 = a.qconfig == "avx2"
        out = f"{onnx_dir}/onnx/model_{'quint8' if u8 else 'qint8'}_{a.qconfig}.onnx"
        quantize_dynamic(f"{onnx_dir}/onnx/model.onnx", out, per_channel=True,
                         weight_type=QuantType.QUInt8 if u8 else QuantType.QInt8, use_external_data_format=False)
    q_file = os.path.relpath(sorted(glob.glob(f"{onnx_dir}/onnx/model_*int8*.onnx"))[0], onnx_dir)
    m_int8 = SentenceTransformer(onnx_dir, backend="onnx", device="cpu", model_kwargs={"file_name": q_file})
    m_torch = clf.bi
    for m in (m_fp32, m_int8, m_torch):
        m.max_seq_length = a.max_len

    # 2. Скорость и совпадение векторов (запросы dev)
    qs = [qp + t for t in (val["text"].tolist() * 3)[:100]]
    sizes = {"PyTorch fp32": mb(f"{src}/*.safetensors", f"{src}/*.bin"),
             "ONNX fp32": mb(f"{onnx_dir}/onnx/model.onnx", f"{onnx_dir}/onnx/model.onnx_data"),
             "ONNX int8": mb(f"{onnx_dir}/{q_file}", f"{onnx_dir}/{q_file}_data", f"{onnx_dir}/{q_file}.data")}
    rows, vecs = [], {}
    for nm, m in (("PyTorch fp32", m_torch), ("ONNX fp32", m_fp32), ("ONNX int8", m_int8)):
        m.encode(qs[:4], normalize_embeddings=True)                                   # прогрев
        t0 = time.perf_counter()
        for q in qs[:20]:
            m.encode([q], normalize_embeddings=True)
        t1 = (time.perf_counter() - t0) / 20
        t0 = time.perf_counter(); vecs[nm] = np.asarray(m.encode(qs, batch_size=32, normalize_embeddings=True))
        rows.append({"вариант": nm, "1 запрос, мс": round(t1 * 1000, 1),
                     "100 запросов, с": round(time.perf_counter() - t0, 2), "размер модели, МБ": round(sizes[nm])})
    speed = pd.DataFrame(rows)
    speed["ускорение"] = (speed["100 запросов, с"].iloc[0] / speed["100 запросов, с"]).round(2)
    cos8 = (vecs["ONNX int8"] * vecs["PyTorch fp32"]).sum(1)
    cos32 = (vecs["ONNX fp32"] * vecs["PyTorch fp32"]).sum(1)
    print(f"\nCPU, {a.threads} потока, только эмбеддинг запроса (без поиска и правил ПП):")
    print(speed.to_string(index=False))
    print(f"Косинус с PyTorch: ONNX fp32 — средний {cos32.mean():.5f}; "
          f"ONNX int8 — средний {cos8.mean():.4f}, минимальный {cos8.min():.4f}")

    # 3. Точность: (а) PyTorch, (б) int8-запросы + fp32-индекс из ноутбука, (в) всё int8 по top-POOL кандидатам
    ref_val, ref_test = evaluate(clf, val, leaves, pp), evaluate(clf, test, leaves, pp)
    mixed = PP1875Classifier(m_int8, clf.docs, clf.doc_emb, pp, None, None, dict(clf.calib), "cpu", clf.texts)
    mx_val, mx_test = evaluate(mixed, val, leaves, pp), evaluate(mixed, test, leaves, pp)
    pool, _, _ = clf.search_codes(clf.encode_queries(val["text"].tolist()), a.pool)
    sub = clf.texts[clf.texts["code"].isin({c for cc in pool for c in cc})].reset_index(drop=True)
    sub_emb = np.asarray(m_int8.encode([dp + t for t in sub["text"]], batch_size=64, normalize_embeddings=True))
    full8 = PP1875Classifier(m_int8, clf.docs, sub_emb, pp, None, None, dict(clf.calib), "cpu", sub)
    f8_val = evaluate(full8, val, leaves, pp)
    q_res = pd.DataFrame([
        {"вариант": "PyTorch fp32 (как сейчас)", **{f"val_{k}": v for k, v in ref_val.items()},
         "test_verdict": ref_test.get("verdict")},
        {"вариант": "int8-запросы + fp32-индекс", **{f"val_{k}": v for k, v in mx_val.items()},
         "test_verdict": mx_test.get("verdict")},
        {"вариант": f"всё int8 (top-{a.pool} fp32, только dev)", **{f"val_{k}": v for k, v in f8_val.items()},
         "test_verdict": None},
    ])
    print("\nТочность (без cross-encoder):")
    print(q_res.to_string(index=False))

    # 4. metrics.json, fp32-ONNX не храним, архив заново
    mp = f"{A}/metrics.json"
    metrics = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    metrics["onnx"] = {"qconfig": a.qconfig, "file": q_file, "speed": speed.to_dict("records"),
                       "cos_int8_mean": float(cos8.mean()), "cos_int8_min": float(cos8.min()),
                       "quality": q_res.to_dict("records")}
    json.dump(metrics, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
    for f in glob.glob(f"{onnx_dir}/onnx/model.onnx*"):
        os.remove(f)
    shutil.make_archive(A, "zip", A)
    print(f"\nONNX int8: папка '{name}-onnx', файл '{q_file}'. "
          f"Архив обновлён: {os.path.getsize(A + '.zip') / 2**20:.0f} MB")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # ONNX — необязательный шаг: модель и артефакты уже сохранены
        import traceback
        traceback.print_exc()
        print("\n!!! ONNX-экспорт не удался, основная модель и artifacts.zip не затронуты:", repr(e)[:300])
