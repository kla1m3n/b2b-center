"""Скачивает веса моделей в HF_HOME на этапе сборки образа (после сборки интернет не нужен)."""
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet-CDN нестабилен, качаем обычным HTTP

from huggingface_hub import snapshot_download  # noqa: E402

ALLOW = ["*.json", "*.txt", "*.model", "*.safetensors", "sentencepiece*", "tokenizer*", "1_Pooling/*", "modules.json"]
ATTEMPTS = 5

models = [m for m in sys.argv[1:] if m] or [os.environ["EMBED_MODEL"], os.environ["RERANK_MODEL"]]
for name in models:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            print(f"Скачиваю {name} (попытка {attempt})", flush=True)
            snapshot_download(name, allow_patterns=ALLOW)
            break
        except Exception as e:  # сетевые сбои: докачиваем с того же места
            if attempt == ATTEMPTS:
                raise
            print(f"Ошибка: {e!s:.200}. Повтор через {attempt * 10} с", flush=True)
            time.sleep(attempt * 10)
