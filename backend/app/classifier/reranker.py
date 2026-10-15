"""Кросс-энкодер: точная оценка пары «товар — наименование кода ОКПД2»."""
import torch
from sentence_transformers import CrossEncoder


class Reranker:
    def __init__(self, model_name: str, device: str = "cpu"):
        self.model = CrossEncoder(model_name, device=device, max_length=256)

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Сырые логиты релевантности (чем больше, тем ближе)."""
        if not pairs:
            return []
        return [float(s) for s in self.model.predict(pairs, batch_size=32, activation_fct=torch.nn.Identity(), show_progress_bar=False)]
