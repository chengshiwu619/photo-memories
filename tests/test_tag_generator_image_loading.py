import os
import sys
import types


class _FakeArray(list):
    @property
    def size(self):
        return len(self)

    def flatten(self):
        return list(self)


def _fake_np_array(value, dtype=None):
    if isinstance(value, list) and value and isinstance(value[0], list):
        return [_FakeArray(row) for row in value]
    if isinstance(value, list):
        return _FakeArray(value)
    return value


if "numpy" not in sys.modules:
    fake_numpy = types.SimpleNamespace(
        ndarray=object,
        float32=float,
        array=_fake_np_array,
        argsort=lambda seq: list(sorted(range(len(seq)), key=lambda idx: seq[idx])),
    )
    sys.modules["numpy"] = fake_numpy

if "PIL" not in sys.modules:
    class _FakeOpenedImage:
        mode = "RGB"

        def load(self):
            return None

        def copy(self):
            return self

        def thumbnail(self, size, resample):
            return None

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_image_module = types.SimpleNamespace(
        LANCZOS=1,
        Image=_FakeOpenedImage,
        open=lambda path: _FakeOpenedImage(),
    )
    fake_imageops_module = types.SimpleNamespace(exif_transpose=lambda img: img)
    fake_pil_module = types.SimpleNamespace(Image=fake_image_module, ImageOps=fake_imageops_module)
    sys.modules["PIL"] = fake_pil_module
    sys.modules["PIL.Image"] = fake_image_module
    sys.modules["PIL.ImageOps"] = fake_imageops_module

if "config" not in sys.modules:
    fake_config = types.SimpleNamespace(
        get_settings=lambda: types.SimpleNamespace(thumbnail_dir="D:/fake-thumbnails")
    )
    sys.modules["config"] = fake_config


from business.image_recognition import tag_generator as tg


class _FakeSettings:
    def __init__(self, thumbnail_dir):
        self.thumbnail_dir = thumbnail_dir


def test_encode_images_batch_detailed_loads_file_id_from_thumbnail_dir(tmp_path, monkeypatch):
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    (thumb_dir / "3.jpg").write_bytes(b"fake-image")
    settings = _FakeSettings(str(thumb_dir))

    monkeypatch.setattr(tg, "_resolve_settings", lambda provided=None: settings)
    monkeypatch.setattr("infra.image.clip_encoder._load_model", lambda: True)
    monkeypatch.setattr("infra.image.clip_encoder._preprocess", lambda img: [1.0, 2.0])
    monkeypatch.setattr(
        tg,
        "_load_thumbnail_image",
        lambda file_id, settings: (object(), None) if file_id == 3 else (None, {"file_id": file_id, "thumbnail_path": os.path.join(settings.thumbnail_dir, f"{file_id}.jpg"), "reason": "thumbnail_not_found"}),
    )
    monkeypatch.setattr(
        tg,
        "_encode_preprocessed_batch",
        lambda inputs, ce: [_FakeArray([0.1, 0.2, 0.3])],
    )

    result = tg._encode_images_batch_detailed([3], settings=settings)

    assert result["encoded_count"] == 1
    assert result["encode_failed_count"] == 0
    assert result["embeddings"][0][0] == 3


def test_encode_images_batch_detailed_records_thumbnail_not_found(tmp_path, monkeypatch):
    settings = _FakeSettings(str(tmp_path / "thumbs"))
    monkeypatch.setattr(tg, "_resolve_settings", lambda provided=None: settings)
    monkeypatch.setattr("infra.image.clip_encoder._load_model", lambda: True)

    result = tg._encode_images_batch_detailed([3], settings=settings)

    assert result["encoded_count"] == 0
    assert result["encode_failed_count"] == 1
    assert result["encode_errors"][0]["reason"] == "thumbnail_not_found"


def test_encode_images_batch_detailed_records_image_open_failed(tmp_path, monkeypatch):
    settings = _FakeSettings(str(tmp_path / "thumbs"))
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    (thumb_dir / "3.jpg").write_text("not an image", encoding="utf-8")
    monkeypatch.setattr(tg, "_resolve_settings", lambda provided=None: settings)
    monkeypatch.setattr("infra.image.clip_encoder._load_model", lambda: True)
    monkeypatch.setattr(tg.Image, "open", lambda path: (_ for _ in ()).throw(RuntimeError("bad image")))

    result = tg._encode_images_batch_detailed([3], settings=settings)

    assert result["encoded_count"] == 0
    assert result["encode_failed_count"] == 1
    assert result["encode_errors"][0]["reason"] == "image_open_failed"


def test_generate_tags_batch_returns_partial_success_with_encode_failures(monkeypatch):
    monkeypatch.setattr(tg, "is_available", lambda: True)
    monkeypatch.setattr(tg, "_get_text_embeddings", lambda candidates: _FakeArray([[1.0], [0.5]]))
    monkeypatch.setattr(tg, "compute_similarity", lambda image_emb, text_emb: [0.9, 0.1])
    monkeypatch.setattr(
        tg,
        "_encode_images_batch_detailed",
        lambda file_ids, settings=None, batch_size=16: {
            "embeddings": [(3, [1.0])],
            "encoded_count": 1,
            "encode_failed_count": 1,
            "encode_errors": [{"file_id": 4, "reason": "thumbnail_not_found"}],
        },
    )

    result = tg.generate_tags_batch([3, 4], candidates=["beach", "mountain"], return_diagnostics=True)

    assert result["tags_by_file"] == {3: ["beach"]}
    assert result["encoded_count"] == 1
    assert result["encode_failed_count"] == 1
    assert result["encode_errors"][0]["reason"] == "thumbnail_not_found"


def test_generate_tags_batch_reports_text_model_failure(monkeypatch, tmp_path):
    settings = _FakeSettings(str(tmp_path / "thumbs"))
    monkeypatch.setattr(tg, "is_available", lambda: True)
    monkeypatch.setattr(tg, "_get_text_embeddings", lambda candidates: _FakeArray([]))

    result = tg.generate_tags_batch(
        [3, 4],
        candidates=["nsfw"],
        settings=settings,
        return_diagnostics=True,
    )

    assert result["tags_by_file"] == {}
    assert result["encoded_count"] == 0
    assert result["encode_failed_count"] == 2
    assert {item["reason"] for item in result["encode_errors"]} == {"model_text_encode_failed"}


def test_visual_review_tags_use_calibrated_thresholds_only_for_default_candidates():
    assert tg._candidate_threshold("gravure", 0.25, True) == 0.25
    assert tg._candidate_threshold("nsfw", 0.25, True) == 0.052
    assert tg._candidate_threshold("nude", 0.25, True) == 0.07
    assert tg._candidate_threshold("explicit", 0.25, True) == 0.097
    assert tg._candidate_threshold("nipples", 0.25, True) == 0.083
    assert tg._candidate_threshold("female genitals", 0.25, True) == 0.1
    assert tg._candidate_threshold("vulva", 0.25, True) == 0.061
    assert tg._candidate_threshold("labia", 0.25, True) == 0.076
    assert tg._candidate_threshold("beach", 0.25, True) == 0.25
    assert tg._candidate_threshold("gravure", 0.25, False) == 0.25


def test_visual_review_prompts_use_explicit_descriptions(monkeypatch):
    captured = []
    tg._text_embeddings_cache.clear()
    monkeypatch.setattr(tg, "encode_text", lambda prompts: captured.extend(prompts) or _FakeArray([[1.0]]))

    tg._get_text_embeddings(["vulva"])

    assert captured == ["a clearly visible vulva"]


def test_calibrated_anatomy_tag_is_checked_outside_top_k():
    similarities = tg.np.array([0.9, 0.07])

    tags = tg._select_tags(
        similarities,
        ["beach", "vulva"],
        top_k=1,
        threshold=0.25,
        use_visual_calibration=True,
    )

    assert tags == ["beach", "vulva", tg.CALIBRATED_REVIEW_TAG]
