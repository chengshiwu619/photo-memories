import os
import tempfile
import shutil
from types import SimpleNamespace
from PIL import Image


def _create_test_jpeg(path, width=200, height=150):
    img = Image.new("RGB", (width, height), color=(255, 128, 0))
    img.save(path, "JPEG")


def test_extract_exif_no_exif():
    from business.indexer.photo_indexer import extract_exif
    tmp = tempfile.mkdtemp()
    try:
        jpg = os.path.join(tmp, "test.jpg")
        _create_test_jpeg(jpg)
        result = extract_exif(jpg)
        assert "date_taken" in result
        assert "camera_model" in result
        assert "gps_lat" in result
        assert "gps_lon" in result
        assert "orientation" in result
        assert result["date_taken"] is None
        assert result["camera_model"] is None
    finally:
        shutil.rmtree(tmp)


def test_extract_exif_file_not_found():
    from business.indexer.photo_indexer import extract_exif
    result = extract_exif("/nonexistent/path.jpg")
    assert result["date_taken"] is None


def test_generate_thumbnail_creates_file():
    from business.indexer.photo_indexer import generate_thumbnail
    from unittest.mock import patch
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 800, 600)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        fake_settings = SimpleNamespace(thumbnail_dir=thumb_dir, thumbnail_size=(600, 600))
        with patch("business.indexer.photo_indexer.get_settings", return_value=fake_settings):
            try:
                thumb_path, w, h, status, error = generate_thumbnail(src, "1.jpg")
                assert thumb_path is not None
                assert os.path.exists(thumb_path)
                assert status == "ok"
                assert error is None
            finally:
                pass
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_skips_existing():
    from business.indexer.photo_indexer import generate_thumbnail
    from unittest.mock import patch
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 400, 300)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        fake_settings = SimpleNamespace(thumbnail_dir=thumb_dir, thumbnail_size=(600, 600))
        with patch("business.indexer.photo_indexer.get_settings", return_value=fake_settings):
            try:
                thumb_path1, w1, h1, status1, error1 = generate_thumbnail(src, "2.jpg")
                assert thumb_path1 is not None
                assert status1 == "ok"
                assert error1 is None
                thumb_path2, w2, h2, status2, error2 = generate_thumbnail(src, "2.jpg")
                assert w2 is None
                assert h2 is None
                assert status2 == "existing"
                assert error2 is None
            finally:
                pass
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_respects_max_size():
    from business.indexer.photo_indexer import generate_thumbnail
    from unittest.mock import patch
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "big.jpg")
        _create_test_jpeg(src, 3000, 2000)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        fake_settings = SimpleNamespace(thumbnail_dir=thumb_dir, thumbnail_size=(600, 600))
        with patch("business.indexer.photo_indexer.get_settings", return_value=fake_settings):
            try:
                thumb_path, w, h, status, error = generate_thumbnail(src, "3.jpg")
                assert status == "ok"
                assert error is None
                max_width, max_height = fake_settings.thumbnail_size
                with Image.open(src) as src_img:
                    expected_ratio = src_img.width / src_img.height
                with Image.open(thumb_path) as thumb_img:
                    actual_ratio = thumb_img.width / thumb_img.height

                    assert thumb_img.width <= max_width
                    assert thumb_img.height <= max_height
                    assert thumb_img.width == max_width
                    assert thumb_img.height == int(max_width / expected_ratio)
                    assert abs(actual_ratio - expected_ratio) < 0.01
            finally:
                pass
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_fails_when_output_file_missing(monkeypatch):
    from business.indexer.photo_indexer import generate_thumbnail
    from unittest.mock import patch
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        fake_settings = SimpleNamespace(thumbnail_dir=thumb_dir, thumbnail_size=(600, 600))
        with patch("business.indexer.photo_indexer.get_settings", return_value=fake_settings):
            monkeypatch.setattr(
                "business.indexer.photo_indexer.create_thumbnail_file",
                lambda *args, **kwargs: (200, 150),
            )
            thumb_path, w, h, status, error = generate_thumbnail(src, "99.jpg")

        assert thumb_path is None
        assert status == "failed"
        assert error == "thumbnail_file_missing_after_create"
    finally:
        shutil.rmtree(tmp)


def test_auto_rotate():
    from business.indexer.photo_indexer import _auto_rotate
    img = Image.new("RGB", (100, 50))
    result = _auto_rotate(img)
    assert result is not None
    assert result.size[0] == 100
