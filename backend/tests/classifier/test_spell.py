from app.classifier.spell import Speller, damerau

SPELLER = Speller([
    "Приемники телевизионные (телевизоры) цветного изображения", "телевизор",
    "Блокноты", "блокнот", "Тетради школьные", "Мониторы", "монитор",
    "Системные блоки", "системный блок", "Столы письменные", "Лампы светодиодные",
])


def test_damerau_counts_swap_as_one_edit():
    assert damerau("нотубук", "ноутбук", 2) == 1
    assert damerau("телвеизор", "телевизор", 2) == 1
    assert damerau("монитор", "кофеварка", 2) == 3  # больше лимита — limit+1


def test_typos_in_main_word_are_fixed():
    assert SPELLER.correct("телвеизор светодиодный 55 дюймов") == "телевизор светодиодный 55 дюймов"
    assert SPELLER.correct("блконот а5") == "блокнот а5"
    assert SPELLER.correct("моинтор samsung") == "монитор samsung"
    assert SPELLER.correct("сисетмный блок") == "системный блок"


def test_unknown_but_correct_words_are_kept():
    # слова нет в словаре, но и близкого словарного тоже — не «исправляем»
    assert SPELLER.correct("толстовка трикотажная") == "толстовка трикотажная"
    # другая форма известного слова — не опечатка
    assert SPELLER.correct("тетрадь школьная") == "тетрадь школьная"


def test_short_latin_and_digit_tokens_untouched():
    assert SPELLER.correct("lenovo ideapad 15.6 i5") == "lenovo ideapad 15.6 i5"
    assert SPELLER.correct("стол") == "стол"
