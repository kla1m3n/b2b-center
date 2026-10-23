"""Векторные представления текста.

Три способа загрузки модели, по возможности одинаковые по результату:
  * sentence-transformers (основной, как раньше);
  * transformers + pooling вручную — если папку модели сохранила более новая версия sentence-transformers,
    чем стоит в образе (модель дообучалась в Kaggle), и SentenceTransformer её не открывает;
  * ONNX Runtime (EMBED_BACKEND=onnx) — модель из ноутбука, квантованная в int8: запрос в ~4 раза быстрее на CPU.
"""
import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def prefixes(model_name: str) -> tuple[str, str]:
    """Префиксы (запрос, документ), с которыми обучалась модель."""
    name = model_name.lower()
    if "e5" in name:
        return "query: ", "passage: "
    if "frida" in name:
        return "search_query: ", "search_document: "
    return "", ""


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class _Pooled:
    """Токенизатор (tokenizers) + пулинг из конфига sentence-transformers + L2-нормировка. Модель задаёт подкласс."""

    def __init__(self, model_dir: Path):
        from tokenizers import Tokenizer

        self.dir = model_dir
        self.max_len = int(_read_json(model_dir / "sentence_bert_config.json").get("max_seq_length", 512))
        pool = _read_json(model_dir / "1_Pooling" / "config.json")
        self.pooling = "cls" if pool.get("pooling_mode_cls_token") else "mean"
        tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tc = _read_json(model_dir / "tokenizer_config.json")
        pad = tc.get("pad_token") if isinstance(tc.get("pad_token"), str) else None
        pad = pad or next((t for t in ("<pad>", "[PAD]") if tok.token_to_id(t) is not None), "<pad>")
        tok.enable_truncation(self.max_len)
        tok.enable_padding(pad_id=tok.token_to_id(pad) or 0, pad_token=pad)
        self.tok = tok

    def _hidden(self, ids: np.ndarray, mask: np.ndarray, types: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok.encode_batch(texts[i:i + batch_size])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            types = np.array([e.type_ids for e in enc], dtype=np.int64)
            h = self._hidden(ids, mask, types).astype(np.float32)
            if self.pooling == "cls":
                v = h[:, 0]
            else:
                m = mask[..., None].astype(np.float32)
                v = (h * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            out.append(v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None))
        return np.concatenate(out) if out else np.zeros((0, 0), np.float32)


class _OnnxModel(_Pooled):
    def __init__(self, model_dir: Path, onnx_file: str = ""):
        import onnxruntime as ort

        super().__init__(model_dir)
        path = model_dir / onnx_file if onnx_file else None
        if path is None or not path.exists():  # не указан — int8 из ноутбука, иначе обычный model.onnx
            found = sorted((model_dir / "onnx").glob("model_*int8*.onnx")) + sorted((model_dir / "onnx").glob("model.onnx"))
            if not found:
                raise FileNotFoundError(f"В {model_dir}/onnx нет файла модели ONNX")
            path = found[0]
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.inputs = [i.name for i in self.sess.get_inputs()]
        log.info("Эмбеддер ONNX: %s", path)

    def _hidden(self, ids, mask, types):
        feed = {"input_ids": ids, "attention_mask": mask, "token_type_ids": types}
        return self.sess.run(None, {k: feed[k] for k in self.inputs})[0]


class _TorchModel(_Pooled):
    def __init__(self, model_dir: Path, device: str):
        import torch
        from transformers import AutoModel

        super().__init__(model_dir)
        self.torch, self.device = torch, device
        self.model = AutoModel.from_pretrained(str(model_dir)).to(device).eval()

    def _hidden(self, ids, mask, types):
        with self.torch.inference_mode():
            t = lambda a: self.torch.from_numpy(a).to(self.device)
            return self.model(input_ids=t(ids), attention_mask=t(mask)).last_hidden_state.float().cpu().numpy()


class Embedder:
    def __init__(self, model_name: str, device: str = "cpu", backend: str | None = None, onnx_file: str | None = None):
        from app.config import get_settings

        s = get_settings()
        if backend is None:  # настройки ONNX относятся только к модели из EMBED_MODEL
            backend = s.embed_backend if model_name == s.embed_model else "torch"
            onnx_file = s.embed_onnx_file if onnx_file is None else onnx_file
        self.model_name = model_name
        self._q, self._p = prefixes(model_name)
        self._st = self._raw = None
        if backend == "onnx":
            self._raw = _OnnxModel(Path(model_name), onnx_file or "")
        else:
            try:
                from sentence_transformers import SentenceTransformer

                self._st = SentenceTransformer(model_name, device=device)
            except Exception as e:  # папка от более новой sentence-transformers — читаем напрямую
                if not Path(model_name).is_dir():
                    raise
                log.warning("SentenceTransformer не открыл %s (%s) — загрузка через transformers", model_name, e)
                self._raw = _TorchModel(Path(model_name), device)
        self.dim: int = int(self._encode(["x"]).shape[1])

    def _encode(self, texts: list[str]) -> np.ndarray:
        if self._st is not None:
            return self._st.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True,
                                   show_progress_bar=len(texts) > 1000)
        return self._raw.encode(texts, 64)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([self._q + t for t in texts])

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([self._p + t for t in texts])
