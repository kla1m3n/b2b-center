from pathlib import Path

import huggingface_hub.constants as hf_constants
import pytest

from app.classifier.embedder import _model_dir, pick_onnx_file, pooling_mode


def test_pooling_config_old_and_new_formats():
    assert pooling_mode({"word_embedding_dimension": 1024, "pooling_mode_cls_token": False,
                         "pooling_mode_mean_tokens": True}) == "mean"          # sentence-transformers 3.x
    assert pooling_mode({"pooling_mode_cls_token": True}) == "cls"
    assert pooling_mode({"embedding_dimension": 1024, "pooling_mode": "mean", "include_prompt": True}) == "mean"  # 5.x
    assert pooling_mode({"pooling_mode": "cls"}) == "cls"
    assert pooling_mode({}) == "mean"
    with pytest.raises(ValueError):
        pooling_mode({"pooling_mode": "max"})

ST_EXPORT = [Path(f"onnx/{n}.onnx") for n in ("model", "model_qint8_arm64", "model_qint8_avx512",
                                                "model_qint8_avx512_vnni", "model_quint8_avx2")]


def test_onnx_file_matches_cpu():
    name = lambda **kw: pick_onnx_file(ST_EXPORT, **kw).name  # noqa: E731
    assert name(machine="x86_64", flags={"avx2"}) == "model_quint8_avx2.onnx"          # не arm64 по алфавиту
    assert name(machine="x86_64", flags={"avx2", "avx512f"}) == "model_qint8_avx512.onnx"
    assert name(machine="x86_64", flags={"avx2", "avx512f", "avx512_vnni"}) == "model_qint8_avx512_vnni.onnx"
    assert name(machine="aarch64", flags=set()) == "model_qint8_arm64.onnx"


def test_onnx_file_fallbacks():
    vnni_only = [Path("onnx/model_qint8_avx512_vnni.onnx")]  # как в ноутбуке: один файл — берём его на любом x86
    assert pick_onnx_file(vnni_only, machine="x86_64", flags={"avx2"}) == vnni_only[0]
    assert pick_onnx_file([Path("onnx/model.onnx")], machine="x86_64", flags=set()).name == "model.onnx"
    assert pick_onnx_file([Path("onnx/model_quantized.onnx")], machine="x86_64", flags=set()).name == "model_quantized.onnx"
    assert pick_onnx_file([], machine="x86_64", flags=set()) is None


def test_local_folder_used_as_is(tmp_path):
    assert _model_dir(str(tmp_path)) == tmp_path


def test_hub_name_resolved_from_build_cache(tmp_path, monkeypatch):
    # так кладёт модель scripts/download_models.py при сборке: hub/models--<org>--<name>/snapshots/<rev>
    repo = tmp_path / "models--team--e5-large-pp1875-onnx"
    snap = repo / "snapshots" / "abc123"
    (snap / "onnx").mkdir(parents=True)
    (snap / "onnx" / "model_qint8_avx2.onnx").write_bytes(b"")
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text("abc123")
    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(tmp_path))
    assert _model_dir("team/e5-large-pp1875-onnx") == snap


def test_missing_model_explains_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="пересоберите образ"):
        _model_dir("team/no-such-model")
