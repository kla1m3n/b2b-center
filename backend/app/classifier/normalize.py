"""Нормализация наименования товара перед поиском."""
import re

ABBREVIATIONS: dict[str, str] = {
    "ноут": "ноутбук",
    "мфу": "многофункциональное устройство",
    "пк": "персональный компьютер",
    "сист": "системный",
    "эл": "электрический",
    "канц": "канцелярский",
    "хоз": "хозяйственный",
    "мед": "медицинский",
    "одноразов": "одноразовый",
    "ибп": "источник бесперебойного питания",
    "свд": "светодиодный",
    "led": "светодиодный",
    "тв": "телевизор",
    "жк": "жидкокристаллический",
    "ссд": "твердотельный накопитель",
    "ssd": "твердотельный накопитель",
    "hdd": "жесткий диск",
    "озу": "оперативная память",
}
UNITS = r"шт|штук|штуки|уп|упак|упаковка|упаковки|компл|комплект|пач|пачка|пачки"

_quantity_re = re.compile(rf"\b\d+\s*(?:{UNITS})\b\.?")
_unit_re = re.compile(rf"\b(?:{UNITS})\b\.?")
_token_re = re.compile(r"[a-zа-я0-9]+(?:[-/.][a-zа-я0-9]+)*")


def _is_article(token: str) -> bool:
    """Артикул/модель: длинный токен, смешивающий буквы и цифры (15s-fq5000, nx.kdkeu.009)."""
    return len(token) >= 6 and bool(re.search(r"\d", token)) and bool(re.search(r"[a-zа-я]", token))


def normalize(name: str) -> str:
    s = name.lower().replace("ё", "е")
    s = _quantity_re.sub(" ", s)
    s = _unit_re.sub(" ", s)
    tokens = [t for t in _token_re.findall(s) if not _is_article(t)]
    tokens = [ABBREVIATIONS.get(t, t) for t in tokens]
    return " ".join(tokens)
