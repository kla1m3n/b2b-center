from app.models import Okpd2Code
from app.seed import okpd2_texts


def code(c, title, parent=None, leaf=True):
    return Okpd2Code(code=c, title=title, parent_code=parent, is_leaf=leaf)


def test_texts_are_plain_titles_of_leaf_codes_plus_synonyms():
    codes = [
        code("31.09", "Мебель прочая", leaf=False),
        code("31.09.13.190", "Мебель деревянная прочая, не включенная в другие группировки", "31.09"),
        code("26.20.11.110", "Ноутбуки"),
    ]
    texts = okpd2_texts(codes, synonyms=[("26.20.11.110", "лэптоп"), ("31.09", "мебель"), ("99.99", "нет такого")])
    assert texts == [
        ("31.09.13.190", "Мебель деревянная прочая, не включенная в другие группировки", "official"),
        ("26.20.11.110", "Ноутбуки", "official"),
        ("26.20.11.110", "лэптоп", "synonym"),
    ]
