import os
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from PIL import Image, ImageOps
import exifread
import imagehash

from pillow_heif import register_heif_opener
register_heif_opener()

Image.MAX_IMAGE_PIXELS = 500_000_000

from logger_setup import logger
from config import get_settings
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState
from infra.image.thumbnail_cache import (
    THUMBNAIL_JPEG_QUALITY,
    build_thumbnail_filename,
    build_thumbnail_path,
    create_thumbnail_file,
)

_db = Database()
_cp = CheckpointManager(_db, "index")

IndexState = CheckpointState


def clear_checkpoint():
    _cp.clear()


def get_checkpoint_status():
    status = _cp.get_status()
    if not status["has_checkpoint"]:
        return {"has_checkpoint": False}
    data = status.get("data", {})
    return {
        "has_checkpoint": True,
        "state": data.get("state"),
        "current_index": data.get("current_index", 0),
        "total": data.get("total", 0),
        "indexed": data.get("indexed", 0),
    }


def set_paused():
    _cp.request_pause()


def set_stopped():
    _cp.request_stop()


def get_unindexed_photos():
    with _db.connect() as conn:
        rows = conn.execute("""
            SELECT f.id, f.file_path FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1
              AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path = '__FAILED__')
        """).fetchall()
    return rows


def _auto_rotate(img):
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def extract_exif(filepath):
    result = {
        "date_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "raw": {},
        "orientation": None,
    }

    try:
        with open(filepath, "rb") as f:
            tags = exifread.process_file(f, details=False)

        for tag, value in tags.items():
            result["raw"][tag] = str(value)

        orient_tag = tags.get("Image Orientation")
        if orient_tag:
            try:
                result["orientation"] = int(str(orient_tag))
            except (ValueError, TypeError):
                pass

        date_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if date_tag:
            try:
                dt = datetime.strptime(str(date_tag), "%Y:%m:%d %H:%M:%S")
                result["date_taken"] = dt.isoformat()
            except ValueError:
                pass

        model_tag = tags.get("Image Model")
        if model_tag:
            result["camera_model"] = str(model_tag).strip()

        lat_tag = tags.get("GPS GPSLatitude")
        lon_tag = tags.get("GPS GPSLongitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        if lat_tag and lon_tag:
            try:
                lat = _convert_gps(lat_tag)
                lon = _convert_gps(lon_tag)
                if lat_ref and str(lat_ref).strip() == "S":
                    lat = -lat
                if lon_ref and str(lon_ref).strip() == "W":
                    lon = -lon
                result["gps_lat"] = lat
                result["gps_lon"] = lon
            except Exception:
                pass
    except Exception:
        pass

    return result


def _convert_gps(value):
    parts = str(value).strip("[]").split(",")
    degrees = float(parts[0].split("/")[0]) / float(parts[0].split("/")[-1])
    minutes = float(parts[1].split("/")[0]) / float(parts[1].split("/")[-1])
    seconds = float(parts[2].split("/")[0]) / float(parts[2].split("/")[-1])
    return degrees + minutes / 60 + seconds / 3600


def generate_thumbnail(filepath, thumbnail_name):
    _thumb_dir = get_settings().thumbnail_dir
    os.makedirs(_thumb_dir, exist_ok=True)
    try:
        file_id = int(os.path.splitext(thumbnail_name)[0])
        thumb_path = build_thumbnail_path(_thumb_dir, file_id)
    except ValueError:
        thumb_path = os.path.join(_thumb_dir, thumbnail_name)

    if os.path.exists(thumb_path):
        return thumb_path, None, None

    try:
        thumb_size = get_settings().thumbnail_size
        orig_w, orig_h = create_thumbnail_file(
            filepath,
            thumb_path,
            thumbnail_size=thumb_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
        return thumb_path, orig_w, orig_h
    except Exception as e:
        logger.error(f"缩略图生成失败 {filepath}: {e}")
        return None, None, None


INDEX_COMMIT_EVERY = 20
INDEX_WORKERS = 2


def compute_phash(filepath):
    try:
        with Image.open(filepath) as img:
            img = _auto_rotate(img)
            img.thumbnail((256, 256), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            return str(imagehash.phash(img))
    except Exception as e:
        logger.warning(f"pHash计算失败 {filepath}: {e}")
        return None


def dedup_by_phash(progress_callback=None):
    with _db.connect() as conn:
        rows = conn.execute(
            "SELECT file_id, phash FROM photo_metadata WHERE phash IS NOT NULL ORDER BY file_id"
        ).fetchall()

    if not rows:
        return {"checked": 0, "duplicates": 0}

    phash_map = {}
    duplicate_count = 0
    pending_dup_updates = []

    for i, (file_id, phash_str) in enumerate(rows):
        h = imagehash.hex_to_hash(phash_str)
        found_dup = False
        for existing_id, existing_hash in phash_map.items():
            if h - existing_hash <= get_settings().phash_threshold:
                pending_dup_updates.append((existing_id, file_id))
                duplicate_count += 1
                found_dup = True
                break
        if not found_dup:
            phash_map[file_id] = h

        if len(pending_dup_updates) >= 50:
            with _db.connect() as conn:
                conn.executemany(
                    "UPDATE photo_metadata SET is_duplicate_of = ? WHERE file_id = ?",
                    pending_dup_updates,
                )
            pending_dup_updates.clear()

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(i + 1, len(rows))

    if pending_dup_updates:
        with _db.connect() as conn:
            conn.executemany(
                "UPDATE photo_metadata SET is_duplicate_of = ? WHERE file_id = ?",
                pending_dup_updates,
            )

    logger.info(f"去重完成: 检查 {len(rows)} 张, 发现 {duplicate_count} 张重复")
    return {"checked": len(rows), "duplicates": duplicate_count}


def _index_single_photo(file_id, file_path):
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在, 跳过: {file_path}")
        return None

    try:
        with Image.open(file_path) as _test:
            _test.load()  # 强制解码像素数据，提前捕获截断文件
    except Exception as e:
        logger.warning(f"无法识别图片, 标记跳过: {file_path}: {e}")
        return (
            file_id, None, None, None, None,
            None, None, "__FAILED__", None,
            datetime.now().isoformat(), None,
        )

    exif_data = extract_exif(file_path)
    thumbnail_name = build_thumbnail_filename(file_id)
    thumb_path, orig_w, orig_h = generate_thumbnail(file_path, thumbnail_name)

    import json as json_mod
    exif_json = (
        json_mod.dumps(exif_data["raw"], ensure_ascii=False)
        if exif_data["raw"]
        else None
    )

    phash = compute_phash(file_path)

    return (
        file_id,
        exif_data["date_taken"],
        exif_data["camera_model"],
        exif_data["gps_lat"],
        exif_data["gps_lon"],
        orig_w,
        orig_h,
        thumb_path,
        exif_json,
        datetime.now().isoformat(),
        phash,
    )


def _flush_pending_writes(pending_writes, limit=None):
    if not pending_writes:
        return 0
    rows_to_write = pending_writes if limit is None else pending_writes[:limit]
    with _db.connect() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO photo_metadata
               (file_id, date_taken, camera_model, gps_lat, gps_lon,
                width, height, thumbnail_path, exif_json, indexed_at, phash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows_to_write,
        )
    flushed = len(rows_to_write)
    del pending_writes[:flushed]
    return flushed


def _process_index_batch(batch_rows, workers):
    if workers <= 1:
        results = []
        for file_id, file_path in batch_rows:
            results.append((file_id, file_path, _index_single_photo(file_id, file_path), None))
        return results

    ordered_results = [None] * len(batch_rows)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_index_single_photo, file_id, file_path): (idx, file_id, file_path)
            for idx, (file_id, file_path) in enumerate(batch_rows)
        }
        for future in as_completed(future_map):
            idx, file_id, file_path = future_map[future]
            try:
                row = future.result()
                ordered_results[idx] = (file_id, file_path, row, None)
            except Exception as exc:
                ordered_results[idx] = (file_id, file_path, None, exc)
    return ordered_results


def index_photos(progress_callback=None, batch_limit=None, workers=INDEX_WORKERS, batch_size=INDEX_COMMIT_EVERY):
    _db.init_tables()
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)

    photos = get_unindexed_photos()
    total = len(photos)
    logger.info(f"开始索引照片: 共 {total} 张待索引, workers={workers}, batch_size={batch_size}")
    cp = _cp.load()
    start_idx = cp["current_index"] if cp else 0
    indexed = cp.get("indexed", 0) if cp else 0

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, indexed=0)
        logger.info("新索引任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, indexed={indexed}")

    batch_count = 0
    pending_writes = []

    for batch_start in range(start_idx, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_rows = photos[batch_start:batch_end]
        batch_results = _process_index_batch(batch_rows, workers)

        for offset, (file_id, file_path, row, error) in enumerate(batch_results):
            if error is not None:
                logger.error(f"索引照片失败 {file_path}: {error}")
            elif row is not None:
                pending_writes.append(row)
                indexed += 1
                batch_count += 1

            while len(pending_writes) >= INDEX_COMMIT_EVERY:
                _flush_pending_writes(pending_writes, limit=INDEX_COMMIT_EVERY)

            if progress_callback:
                progress_callback(batch_start + offset + 1, total)

        if pending_writes:
            _flush_pending_writes(pending_writes)

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=batch_end, total=total, indexed=indexed)
            logger.info(f"索引热身完成: {indexed}/{total}, 剩余 {total - batch_end} 张后台继续")
            return {"paused": True, "batch_limit_reached": True, "total": total, "indexed": indexed}

        if _cp.is_pause_or_stop_requested():
            _cp.save(CheckpointState.PAUSED, current_index=batch_end, total=total, indexed=indexed)
            logger.info(f"索引暂停: {indexed}/{total}")
            return {"paused": True, "total": total, "indexed": indexed}

        _cp.save(CheckpointState.RUNNING, current_index=batch_end, total=total, indexed=indexed)

    if pending_writes:
        _flush_pending_writes(pending_writes)

    _cp.clear()
    logger.info(f"索引完成: 总计 {total}, 已索引 {indexed}")

    dedup_by_phash()

    return {"total": total, "indexed": indexed}


if __name__ == "__main__":
    result = index_photos()
    if result.get("paused"):
        print(f"索引暂停: {result['indexed']}/{result['total']}")
    else:
        print(f"索引完成: 总计 {result['total']}, 已索引 {result['indexed']}")
