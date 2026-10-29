"""Дообучение модели поиска на data/train/train_full.csv и экспорт в ONNX int8 под AVX2 — для бэкенда проекта.

Нужен GPU (Kaggle T4/P100 или сервер): ~1 ч на эпоху для e5-large и 146 тыс. пар. Порядок — training/README.md.

Обучение: тройки (запрос, наименование кода, трудный негатив) из make_train_set.py, префиксы «query: » / «passage: »
как в backend/app/classifier/embedder.py, CachedMultipleNegativesRankingLoss — большой батч (больше негативов
в батче) при небольшой памяти; NO_DUPLICATES — в батче нет одинаковых текстов, иначе код «негатив» сам себе.
Тексты кодов — голые наименования, ровно как в индексе сайта (seed.okpd2_texts), без «(раздел: …)».

Проверка — InformationRetrievalEvaluator на split=val (коды, которых нет в обучении): поиск по всем
наименованиям кодов нижнего уровня и синонимам, как на сайте; печатается до и после обучения.

Результат: <out>/ (PyTorch) и <out>-onnx/ (onnx/model_quint8_avx2.onnx + токенизатор), архив <out>-onnx.zip.
"""
import argparse
import csv
import glob
import os
import random
import shutil

import numpy as np

Q, P = "query: ", "passage: "


def read_csv(path: str, delimiter: str = ";") -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def build_evaluator(val: list[dict], okpd2: list[dict], synonyms: list[dict], limit: int, seed: int):
    from sentence_transformers.evaluation import InformationRetrievalEvaluator

    corpus, docs_of = {}, {}
    for r in okpd2:
        if r["is_leaf"] == "1":
            corpus[f"{r['code']}|t"] = P + r["title"]
            docs_of.setdefault(r["code"], set()).add(f"{r['code']}|t")
    for i, r in enumerate(synonyms):
        if r["code"] in docs_of:
            corpus[f"{r['code']}|s{i}"] = P + r["text"]
            docs_of[r["code"]].add(f"{r['code']}|s{i}")
    rows = [r for r in val if r["code"] in docs_of]
    random.Random(seed).shuffle(rows)
    rows = rows[:limit]
    queries = {str(i): Q + r["query"] for i, r in enumerate(rows)}
    relevant = {str(i): docs_of[r["code"]] for i, r in enumerate(rows)}
    return InformationRetrievalEvaluator(queries, corpus, relevant, name="val", accuracy_at_k=[1, 3, 10],
                                         precision_recall_at_k=[10], mrr_at_k=[10], ndcg_at_k=[10], map_at_k=[10],
                                         show_progress_bar=False, batch_size=128)


def export_onnx(src: str, dst: str, probe: list[str]) -> None:
    """ONNX fp32 → int8 под AVX2 (файл model_quint8_avx2.onnx — его выбирает pick_onnx_file бэкенда)."""
    from sentence_transformers import SentenceTransformer, export_dynamic_quantized_onnx_model

    fp32 = SentenceTransformer(src, backend="onnx", device="cpu")
    fp32.save(dst)
    try:
        export_dynamic_quantized_onnx_model(fp32, "avx2", dst)
    except Exception as e:  # e5-large fp32 > 2 ГБ (внешние данные) — квантуем onnxruntime напрямую, как в onnx_export.py
        print("sentence-transformers не квантовал:", str(e)[:200], "→ onnxruntime")
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(f"{dst}/onnx/model.onnx", f"{dst}/onnx/model_quint8_avx2.onnx",
                         weight_type=QuantType.QUInt8, per_channel=True, use_external_data_format=True)
    q_file = os.path.relpath(sorted(glob.glob(f"{dst}/onnx/model_*int8*.onnx"))[0], dst)
    int8 = SentenceTransformer(dst, backend="onnx", device="cpu", model_kwargs={"file_name": q_file})
    ref = SentenceTransformer(src, device="cpu")
    cos = (np.asarray(int8.encode(probe, normalize_embeddings=True))
           * np.asarray(ref.encode(probe, normalize_embeddings=True))).sum(1)
    print(f"ONNX int8 ({q_file}): косинус с PyTorch средний {cos.mean():.4f}, минимальный {cos.min():.4f}")
    for f in glob.glob(f"{dst}/onnx/model.onnx*"):  # fp32 (2+ ГБ) бэкенду не нужен
        os.remove(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True, help="train_full.csv из make_train_set.py")
    ap.add_argument("--okpd2", required=True, help="data/okpd2.csv")
    ap.add_argument("--synonyms", required=True, help="data/okpd2_synonyms.csv")
    ap.add_argument("--base", default="intfloat/multilingual-e5-large")
    ap.add_argument("--out", default="e5-large-pp1875-v2", help="в имени должно быть «e5» — по нему бэкенд выбирает префиксы")
    ap.add_argument("--epochs", type=float, default=1)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--mini-batch", type=int, default=32, help="кусок батча в памяти GPU (CachedMNRL)")
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--max-rows", type=int, default=0, help="взять не больше N строк обучения (0 — все), для пробного запуска")
    ap.add_argument("--val-queries", type=int, default=2000)
    ap.add_argument("--no-onnx", action="store_true")
    ap.add_argument("--seed", type=int, default=1875)
    a = ap.parse_args()

    import torch
    from datasets import Dataset
    from sentence_transformers import (SentenceTransformer, SentenceTransformerTrainer,
                                       SentenceTransformerTrainingArguments)
    from sentence_transformers.losses import CachedMultipleNegativesRankingLoss
    from sentence_transformers.training_args import BatchSamplers

    rows = read_csv(a.train)
    train = [r for r in rows if r["split"] == "train" and r["negative"]]
    val = [r for r in rows if r["split"] == "val"]
    random.Random(a.seed).shuffle(train)
    if a.max_rows:
        train = train[:a.max_rows]
    print(f"обучение: {len(train)} троек, проверка: {len(val)} запросов (коды не из обучения)")
    ds = Dataset.from_dict({"anchor": [Q + r["query"] for r in train],
                            "positive": [P + r["positive"] for r in train],
                            "negative": [P + r["negative"] for r in train]})

    gpu = torch.cuda.is_available()
    model = SentenceTransformer(a.base, device="cuda" if gpu else "cpu")
    model.max_seq_length = a.max_len
    evaluator = build_evaluator(val, read_csv(a.okpd2), read_csv(a.synonyms), a.val_queries, a.seed)
    before = evaluator(model)
    print("до обучения:", {k: round(v, 4) for k, v in before.items() if "accuracy" in k or "mrr" in k})

    args = SentenceTransformerTrainingArguments(
        output_dir=f"{a.out}-checkpoints", num_train_epochs=a.epochs, per_device_train_batch_size=a.batch,
        learning_rate=a.lr, warmup_ratio=0.1, fp16=gpu, batch_sampler=BatchSamplers.NO_DUPLICATES,
        eval_strategy="no", save_strategy="no", logging_steps=50, report_to="none", seed=a.seed)
    trainer = SentenceTransformerTrainer(model=model, args=args, train_dataset=ds,
                                         loss=CachedMultipleNegativesRankingLoss(model, mini_batch_size=a.mini_batch))
    trainer.train()
    after = evaluator(model)
    print("после обучения:", {k: round(v, 4) for k, v in after.items() if "accuracy" in k or "mrr" in k})
    model.save(a.out)
    shutil.rmtree(f"{a.out}-checkpoints", ignore_errors=True)

    if not a.no_onnx:
        dst = f"{a.out}-onnx"
        export_onnx(a.out, dst, [Q + r["query"] for r in val[:50]])
        shutil.make_archive(dst, "zip", root_dir=".", base_dir=dst)
        print(f"готово: {dst}/ и {dst}.zip — распаковать в data/models/ проекта (см. training/README.md)")


if __name__ == "__main__":
    main()
