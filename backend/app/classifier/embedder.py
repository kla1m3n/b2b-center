"""Векторные представления текста (sentence-transformers)."""
import numpy as np
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.dim: int = self.model.get_sentence_embedding_dimension()
        self._e5 = "e5" in model_name.lower()

    def _encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True,
                                 show_progress_bar=len(texts) > 1000)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"query: {t}" if self._e5 else t for t in texts])

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" if self._e5 else t for t in texts])
