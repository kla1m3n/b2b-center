from app.classifier.embedder import prefixes


def test_e5_prefixes():
    assert prefixes("intfloat/multilingual-e5-base") == ("query: ", "passage: ")


def test_frida_prefixes():
    assert prefixes("sergeyzh/rubert-mini-frida") == ("search_query: ", "search_document: ")
    assert prefixes("ai-forever/FRIDA") == ("search_query: ", "search_document: ")


def test_models_without_prefixes():
    assert prefixes("deepvk/USER-bge-m3") == ("", "")
    assert prefixes("sergeyzh/LaBSE-ru-turbo") == ("", "")
