import os
from typing import Any, Tuple


THUMBNAIL_CACHE_VERSION = "v2"
THUMBNAIL_JPEG_QUALITY = 90


def build_thumbnail_filename(file_id: int) -> str:
    return f"{file_id}.jpg"


def build_thumbnail_path(thumbnail_dir: str, file_id: int) -> str:
    return os.path.join(thumbnail_dir, build_thumbnail_filename(file_id))


def build_thumbnail_cache_signature(settings: Any) -> str:
    width, height = getattr(settings, "thumbnail_size", (600, 600))
    return f"{THUMBNAIL_CACHE_VERSION}:{width}x{height}:q{THUMBNAIL_JPEG_QUALITY}"


def build_legacy_thumbnail_cache_signature(settings: Any) -> str:
    width, height = getattr(settings, "thumbnail_size", (600, 600))
    return f"{width}x{height}_q{THUMBNAIL_JPEG_QUALITY}"


def classify_thumbnail_cache_signature(stored_signature: str | None, settings: Any) -> str:
    if not stored_signature:
        return "missing"

    current_signature = build_thumbnail_cache_signature(settings)
    if stored_signature == current_signature:
        return "current"

    legacy_signature = build_legacy_thumbnail_cache_signature(settings)
    if stored_signature == legacy_signature:
        return "legacy"

    return "stale"


def create_thumbnail_file(
    source_path: str,
    target_path: str,
    thumbnail_size: Tuple[int, int],
    quality: int = THUMBNAIL_JPEG_QUALITY,
) -> Tuple[int, int]:
    from PIL import Image, ImageOps

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with Image.open(source_path) as img:
        orig_w, orig_h = img.size
        img.draft("RGB", thumbnail_size)
        img = ImageOps.exif_transpose(img)
        img.thumbnail(thumbnail_size, Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(target_path, "JPEG", quality=quality)
    return orig_w, orig_h
