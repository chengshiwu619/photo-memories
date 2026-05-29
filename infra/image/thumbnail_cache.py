import os
from typing import Any


THUMBNAIL_CACHE_VERSION = "v2"
THUMBNAIL_JPEG_QUALITY = 90


def build_thumbnail_filename(file_id: int) -> str:
    return f"{file_id}.jpg"


def build_thumbnail_path(thumbnail_dir: str, file_id: int) -> str:
    return os.path.join(thumbnail_dir, build_thumbnail_filename(file_id))


def build_thumbnail_cache_signature(settings: Any) -> str:
    width, height = getattr(settings, "thumbnail_size", (600, 600))
    return f"{THUMBNAIL_CACHE_VERSION}:{width}x{height}:q{THUMBNAIL_JPEG_QUALITY}"
