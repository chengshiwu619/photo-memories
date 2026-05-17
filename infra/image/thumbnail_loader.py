import os
from typing import Optional, Tuple
from PIL import Image, ImageOps
from collections import OrderedDict

from logger_setup import logger
from config import get_settings


class ThumbnailLoader:
    def __init__(self, cache_size=256):
        self._cache: OrderedDict[int, Image.Image] = OrderedDict()
        self._cache_size = cache_size

    def load(self, file_id: int, size: Optional[Tuple[int, int]] = None) -> Optional[Image.Image]:
        if file_id in self._cache:
            self._cache.move_to_end(file_id)
            return self._cache[file_id].copy()

        thumb_path = os.path.join(get_settings().thumbnail_dir, f"{file_id}.jpg")
        if not os.path.exists(thumb_path):
            return None

        try:
            img = Image.open(thumb_path)
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if size:
                img.thumbnail(size, Image.LANCZOS)
            self._cache[file_id] = img
            self._cache.move_to_end(file_id)
            self._evict()
            return img.copy()
        except Exception as e:
            logger.warning(f"缩略图加载失败 file_id={file_id}: {e}")
            return None

    def _evict(self):
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def clear(self):
        for img in self._cache.values():
            try:
                img.close()
            except Exception:
                pass
        self._cache.clear()

    def preload(self, file_ids):
        for fid in file_ids:
            if fid not in self._cache:
                self.load(fid)


_loader: Optional[ThumbnailLoader] = None


def get_thumbnail_loader() -> ThumbnailLoader:
    global _loader
    if _loader is None:
        _loader = ThumbnailLoader()
    return _loader
