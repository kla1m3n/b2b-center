"""Кладёт веса моделей в HF_HOME на этапе сборки образа (после сборки интернет не нужен).

Если модель уже есть в локальном кэше (папка .hf в корне репозитория, подключается при сборке как /seed),
она копируется оттуда — без интернета. Иначе скачивается с HuggingFace с повторами при обрывах.
"""
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet-CDN нестабилен, качаем обычным HTTP

from huggingface_hub import snapshot_download  # noqa: E402

ALLOW = ["*.json", "*.txt", "*.model", "*.safetensors", "sentencepiece*", "tokenizer*", "1_Pooling/*", "modules.json"]
ATTEMPTS = 5
SEED = Path("/seed/hub")


def from_seed(name: str) -> bool:
    src = SEED / f"models--{name.replace('/', '--')}"
    if not (src / "snapshots").exists():
        return False
    dst = Path(os.environ.get("HF_HOME", "/models")) / "hub" / src.name
    shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
    print(f"{name}: взята из локального кэша .hf", flush=True)
    return True


def download(name: str) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            print(f"Скачиваю {name} (попытка {attempt})", flush=True)
            snapshot_download(name, allow_patterns=ALLOW)
            return
        except Exception as e:  # сетевые сбои: докачиваем с того же места
            if attempt == ATTEMPTS:
                raise
            print(f"Ошибка: {e!s:.200}. Повтор через {attempt * 10} с", flush=True)
            time.sleep(attempt * 10)


for model in [m for m in sys.argv[1:] if m] or [os.environ["EMBED_MODEL"]]:
    if model.startswith(("/", "./", "../")):  # своя модель из папки (data/models) — подключается томом, не качается
        print(f"{model}: локальная папка, скачивать не нужно", flush=True)
        continue
    if not from_seed(model):
        download(model)
