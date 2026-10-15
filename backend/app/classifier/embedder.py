"""Векторные представления текста (sentence-transformers)."""
import numpy as np
from sentence_transformers import SentenceTransformer


def prefixes(model_name: str) -> tuple[str, str]:
    """Префиксы (запрос, документ), с которыми обучалась модель."""
    name = model_name.lower()
    if "e5" in name:
        return "query: ", "passage: "
    if "frida" in name:
        return "search_query: ", "search_document: "
    return "", ""


class Embedder:
    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.dim: int = self.model.get_sentence_embedding_dimension()
        self._q, self._p = prefixes(model_name)

    def _encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True,
                                 show_progress_bar=len(texts) > 1000)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([self._q + t for t in texts])

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([self._p + t for t in texts])
