"""Кладёт веса моделей в HF_HOME на этапе сборки образа (после сборки интернет не нужен).

Если модель уже есть в локальном кэше (папка .hf в корне репозитория, подключается при сборке как /seed),
она копируется оттуда — без интернета. Иначе скачивается с HuggingFace с повторами при обрывах.

EMBED_BACKEND=onnx: из репозитория берутся только файл ONNX (EMBED_ONNX_FILE или int8 из onnx/, иначе
onnx/model.onnx), токенизатор и конфиги — без весов PyTorch.
"""
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet-CDN нестабилен, качаем обычным HTTP

from huggingface_hub import snapshot_download  # noqa: E402

ALLOW = ["*.json", "*.txt", "*.model", "*.safetensors", "sentencepiece*", "tokenizer*", "1_Pooling/*", "modules.json"]
ALLOW_ONNX = ["*.json", "*.txt", "*.model", "sentencepiece*", "tokenizer*", "1_Pooling/*", "modules.json"]
ATTEMPTS = 5
SEED = Path("/seed/hub")
BACKEND = os.environ.get("EMBED_BACKEND", "torch")
ONNX_FILE = os.environ.get("EMBED_ONNX_FILE", "")


def from_seed(name: str) -> bool:
    src = SEED / f"models--{name.replace('/', '--')}"
    if not (src / "snapshots").exists():
        return False
    dst = Path(os.environ.get("HF_HOME", "/models")) / "hub" / src.name
    shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
    print(f"{name}: взята из локального кэша .hf", flush=True)
    return True


def download(name: str, allow: list[str]) -> Path:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            print(f"Скачиваю {name} (попытка {attempt})", flush=True)
            return Path(snapshot_download(name, allow_patterns=allow))
        except Exception as e:  # сетевые сбои: докачиваем с того же места
            if attempt == ATTEMPTS:
                raise
            print(f"Ошибка: {e!s:.200}. Повтор через {attempt * 10} с", flush=True)
            time.sleep(attempt * 10)


def download_onnx(name: str) -> None:
    """Только то, что нужно ONNX Runtime: файл модели (+ внешние веса, если есть) и токенизатор."""
    wanted = [ONNX_FILE, ONNX_FILE + "_data"] if ONNX_FILE else ["onnx/*int8*.onnx", "onnx/*int8*.onnx_data"]
    path = download(name, ALLOW_ONNX + wanted)
    if not list(path.glob("onnx/*.onnx")):  # int8 нет — обычная модель
        path = download(name, ALLOW_ONNX + ["onnx/model.onnx", "onnx/model.onnx_data"])
    found = sorted(p.relative_to(path).as_posix() for p in path.glob("onnx/*.onnx"))
    if not found:
        raise SystemExit(f"{name}: в репозитории нет файла ONNX (onnx/*.onnx) — для EMBED_BACKEND=onnx он обязателен")
    print(f"{name}: ONNX {', '.join(found)}", flush=True)


for model in [m for m in sys.argv[1:] if m] or [os.environ["EMBED_MODEL"]]:
    if model.startswith(("/", "./", "../")):  # своя модель из папки (data/models) — подключается томом, не качается
        print(f"{model}: локальная папка, скачивать не нужно", flush=True)
        continue
    if from_seed(model):
        continue
    if BACKEND == "onnx":
        download_onnx(model)
    else:
        download(model, ALLOW)
