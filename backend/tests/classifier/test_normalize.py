from app.classifier.normalize import normalize


def test_normalize_drops_articles_quantities_and_expands_abbrev():
    assert normalize("  Ноут HP 15s-FQ5000 ,  1 шт ") == "ноутбук hp"


def test_normalize_yo_and_case():
    assert normalize("Ёлка") == "елка"


def test_normalize_keeps_meaningful_short_tokens():
    assert normalize("Бумага офисная А4, 500 листов") == "бумага офисная а4 500 листов"
    assert normalize("МФУ лазерное") == "многофункциональное устройство лазерное"


def test_normalize_garbage_becomes_empty():
    assert normalize(" - ; ") == ""
