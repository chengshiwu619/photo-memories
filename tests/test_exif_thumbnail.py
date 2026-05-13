import os
import tempfile
import shutil
from PIL import Image


def _create_test_jpeg(path, width=200, height=150):
    img = Image.new("RGB", (width, height), color=(255, 128, 0))
    img.save(path, "JPEG")


def test_extract_exif_no_exif():
    from indexer.photo_indexer import extract_exif
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
    from indexer.photo_indexer import extract_exif
    result = extract_exif("/nonexistent/path.jpg")
    assert result["date_taken"] is None


def test_generate_thumbnail_creates_file():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 800, 600)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path, w, h = generate_thumbnail(src, "1.jpg")
            assert thumb_path is not None
            assert os.path.exists(thumb_path)
            assert w == 800
            assert h == 600
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_skips_existing():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 400, 300)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path1, w1, h1 = generate_thumbnail(src, "2.jpg")
            assert w1 == 400
            assert h1 == 300
            thumb_path2, w2, h2 = generate_thumbnail(src, "2.jpg")
            assert w2 is None
            assert h2 is None
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_respects_max_size():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "big.jpg")
        _create_test_jpeg(src, 3000, 2000)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path, w, h = generate_thumbnail(src, "3.jpg")
            thumb_img = Image.open(thumb_path)
            assert thumb_img.width <= 400
            assert thumb_img.height <= 400
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_auto_rotate():
    from indexer.photo_indexer import _auto_rotate
    img = Image.new("RGB", (100, 50))
    result = _auto_rotate(img)
    assert result is not None
    assert result.size[0] == 100
