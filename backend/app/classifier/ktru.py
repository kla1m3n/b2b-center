"""Точный поиск по каталогу КТРУ: наименование дословно совпало с позицией КТРУ → её код ОКПД2.

По 44-ФЗ заказчик берёт наименование из КТРУ, если позиция там есть, поэтому в реальных закупках такие названия
часты (в dev — 61 из 88). Поиск по смыслу для них избыточен и ошибается на соседних кодах («Катетер уретральный
для однократного дренирования» → .110 вместо .190). Справочник — data/ktru_names.csv (scripts/build_ktru_names.py).
"""
import csv
from pathlib import Path

from app.classifier.normalize import normalize
from app.classifier.rerank import _MEDICAL_QUERY, is_medical_code


class KtruNames:
    def __init__(self, rows: list[tuple[str, str]]):
        """rows — (код ОКПД2, наименование позиции КТРУ); ключ — нормализованное наименование, как у запроса."""
        self._by_norm: dict[str, tuple[str, str]] = {}
        for code, text in rows:
            self._by_norm.setdefault(normalize(text), (code, text))

    @classmethod
    def load(cls, path: Path) -> "KtruNames | None":
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            return cls([(r["code"].strip(), r["text"].strip()) for r in csv.DictReader(f, delimiter=";")])

    def __len__(self) -> int:
        return len(self._by_norm)

    def lookup(self, norm: str) -> tuple[str, str] | None:
        """(код, наименование позиции) для нормализованного запроса или None.

        Запрос с пометкой ЕИС «является медицинским изделием», а позиция КТРУ — не в медицинском разделе
        («Трубка дренажная нестерильная» в КТРУ — трубы пластмассовые): заказчик и каталог расходятся, точного
        ответа нет — решает поиск с правилом медизделий.
        """
        medical = norm.startswith(_MEDICAL_QUERY)
        hit = self._by_norm.get(norm[len(_MEDICAL_QUERY):].strip() if medical else norm)
        if hit is None or (medical and not is_medical_code(hit[0])):
            return None
        return hit
