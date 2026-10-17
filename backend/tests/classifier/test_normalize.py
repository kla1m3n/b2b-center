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


def test_normalize_drops_eis_boilerplate_phrases():
    # пометка ЕИС переносится в начало как подсказка о сфере, а не тянет за собой весь запрос
    assert normalize("Катетер уретральный (является медицинским изделием)") == "медицинское изделие катетер уретральный"
    assert normalize("Перчатки резиновые (не является медицинским изделием)") == "перчатки резиновые"
    assert normalize("Картридж Xerox (или аналог)") == "картридж xerox"
    assert normalize("Бумага А4 или эквивалент") == "бумага а4"


def test_normalize_expands_industry_abbreviations():
    assert normalize("Плита ДСП 16 мм") == "плита плита древесно-стружечная 16 мм"
    assert normalize("Панель ПВХ") == "панель поливинилхлорид"
