import os
import json
import sqlite3
import contextlib
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from PIL import Image, ImageOps, ImageFile
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
_BAD_IMAGE_WARNING_COUNT = 0
_THUMBNAIL_WARNING_COUNT = 0
WARNING_SAMPLE_LIMIT = 10

IndexState = CheckpointState


def _limited_warning(kind, message):
    global _BAD_IMAGE_WARNING_COUNT, _THUMBNAIL_WARNING_COUNT
    if kind == "bad_image":
        _BAD_IMAGE_WARNING_COUNT += 1
        count = _BAD_IMAGE_WARNING_COUNT
    else:
        _THUMBNAIL_WARNING_COUNT += 1
        count = _THUMBNAIL_WARNING_COUNT

    if count <= WARNING_SAMPLE_LIMIT:
        logger.warning(message)
    elif count == WARNING_SAMPLE_LIMIT + 1:
        logger.warning(f"{kind} warning 样本超过 {WARNING_SAMPLE_LIMIT} 个，后续同类日志降级为 debug")
    else:
        logger.debug(message)


def _reset_warning_counters():
    global _BAD_IMAGE_WARNING_COUNT, _THUMBNAIL_WARNING_COUNT
    _BAD_IMAGE_WARNING_COUNT = 0
    _THUMBNAIL_WARNING_COUNT = 0


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


def get_unindexed_photos(force_retry=False):
    """获取待索引照片列表，排除路径状态异常的文件。"""
    # 路径状态过滤：排除 damaged/missing/stat_failed/outside_root
    path_filter = """AND (f.path_status IS NULL OR f.path_status NOT IN
        ('damaged_path', 'missing', 'stat_failed', 'outside_root'))"""

    with _db.connect() as conn:
        if force_retry:
            rows = conn.execute(f"""
                SELECT f.id, f.file_path FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1
                  {path_filter}
                  AND (
                      pm.file_id IS NULL
                      OR pm.thumbnail_path IS NULL
                      OR pm.thumbnail_path = '__FAILED__'
                      OR pm.thumbnail_status IN ('failed', 'skipped')
                  )
            """).fetchall()
            return rows

        rows = conn.execute(f"""
            SELECT f.id, f.file_path FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1
              {path_filter}
              AND (
                  pm.file_id IS NULL
                  OR pm.thumbnail_path IS NULL
                  OR (
                      pm.thumbnail_path = '__FAILED__'
                      AND (
                          pm.source_file_size IS NULL
                          OR pm.source_file_mtime IS NULL
                          OR pm.source_file_size != f.file_size
                          OR pm.source_file_mtime != f.file_mtime
                      )
                  )
              )
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
            with contextlib.redirect_stderr(io.StringIO()):
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


def _classify_image_error(exc):
    text = str(exc).lower()
    if "cannot identify image file" in text:
        return "corrupted_or_unreadable"
    if "image file is truncated" in text or "broken data stream" in text:
        return "truncated_or_broken_stream"
    return "thumbnail_error"


def _create_thumbnail_tolerant(filepath, thumb_path, thumbnail_size):
    previous = ImageFile.LOAD_TRUNCATED_IMAGES
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        return create_thumbnail_file(
            filepath,
            thumb_path,
            thumbnail_size=thumbnail_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous


def generate_thumbnail(filepath, thumbnail_name):
    _thumb_dir = get_settings().thumbnail_dir
    os.makedirs(_thumb_dir, exist_ok=True)
    try:
        file_id = int(os.path.splitext(thumbnail_name)[0])
        thumb_path = build_thumbnail_path(_thumb_dir, file_id)
    except ValueError:
        thumb_path = os.path.join(_thumb_dir, thumbnail_name)

    if os.path.exists(thumb_path):
        return thumb_path, None, None, "ok", None

    thumb_size = get_settings().thumbnail_size
    try:
        orig_w, orig_h = create_thumbnail_file(
            filepath,
            thumb_path,
            thumbnail_size=thumb_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
        return thumb_path, orig_w, orig_h, "ok", None
    except Exception as e:
        error_type = _classify_image_error(e)
        if error_type == "truncated_or_broken_stream":
            try:
                orig_w, orig_h = _create_thumbnail_tolerant(filepath, thumb_path, thumb_size)
                logger.info(f"截断图片容错生成缩略图成功: {filepath}")
                return thumb_path, orig_w, orig_h, "recovered", None
            except Exception as retry_exc:
                retry_type = _classify_image_error(retry_exc)
                error_text = f"{retry_type}: {retry_exc}"
                _limited_warning("thumbnail", f"截断图片容错生成缩略图失败 {filepath}: {retry_exc}")
                return None, None, None, "failed", error_text
        error_text = f"{error_type}: {e}"
        _limited_warning("thumbnail", f"缩略图生成失败 {filepath}: {e}")
        return None, None, None, "failed", error_text


INDEX_COMMIT_EVERY = 20
INDEX_WORKERS = 2


def _compute_phash_once(filepath):
    with Image.open(filepath) as img:
        img = _auto_rotate(img)
        img.thumbnail((256, 256), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        return str(imagehash.phash(img))


def compute_phash_result(filepath):
    try:
        return _compute_phash_once(filepath), "ok", None
    except Exception as e:
        error_type = _classify_image_error(e)
        if error_type == "truncated_or_broken_stream":
            previous = ImageFile.LOAD_TRUNCATED_IMAGES
            try:
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                return _compute_phash_once(filepath), "recovered", None
            except Exception as retry_exc:
                retry_type = _classify_image_error(retry_exc)
                error_text = f"{retry_type}: {retry_exc}"
                _limited_warning("thumbnail", f"pHash容错计算失败 {filepath}: {retry_exc}")
                return None, "failed", error_text
            finally:
                ImageFile.LOAD_TRUNCATED_IMAGES = previous
        error_text = f"{error_type}: {e}"
        _limited_warning("thumbnail", f"pHash计算失败 {filepath}: {e}")
        return None, "failed", error_text


def compute_phash(filepath):
    phash, _status, _error = compute_phash_result(filepath)
    return phash


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


def _metadata_row(
    file_id,
    date_taken=None,
    camera_model=None,
    gps_lat=None,
    gps_lon=None,
    width=None,
    height=None,
    thumbnail_path=None,
    exif_json=None,
    indexed_at=None,
    phash=None,
    phash_status="ok",
    phash_error=None,
    thumbnail_status="ok",
    thumbnail_error=None,
    source_file_size=None,
    source_file_mtime=None,
):
    return (
        file_id,
        date_taken,
        camera_model,
        gps_lat,
        gps_lon,
        width,
        height,
        thumbnail_path,
        exif_json,
        indexed_at or datetime.now().isoformat(),
        phash,
        phash_status,
        phash_error,
        thumbnail_status,
        thumbnail_error,
        source_file_size,
        source_file_mtime,
    )


def _source_stat(filepath):
    try:
        stat = os.stat(filepath)
        return stat.st_size, datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        return None, None


def _index_single_photo(file_id, file_path):
    source_file_size, source_file_mtime = _source_stat(file_path)
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在, 跳过: {file_path}")
        return None

    try:
        with Image.open(file_path) as _test:
            _test.load()  # 强制解码像素数据，提前捕获截断文件
    except Exception as e:
        error_type = _classify_image_error(e)
        if error_type == "corrupted_or_unreadable":
            _limited_warning("bad_image", f"无法识别图片, 标记跳过: {file_path}: {e}")
            return _metadata_row(
                file_id,
                thumbnail_path="__FAILED__",
                phash_status="skipped",
                phash_error="thumbnail_failed",
                thumbnail_status="skipped",
                thumbnail_error=f"{error_type}: {e}",
                source_file_size=source_file_size,
                source_file_mtime=source_file_mtime,
            )
        if error_type != "truncated_or_broken_stream":
            _limited_warning("bad_image", f"图片解码失败, 尝试缩略图链路: {file_path}: {e}")

    exif_data = extract_exif(file_path)
    thumbnail_name = build_thumbnail_filename(file_id)
    thumb_path, orig_w, orig_h, thumb_status, thumb_error = generate_thumbnail(file_path, thumbnail_name)

    import json as json_mod
    exif_json = (
        json_mod.dumps(exif_data["raw"], ensure_ascii=False)
        if exif_data["raw"]
        else None
    )

    if thumb_path:
        phash, phash_status, phash_error = compute_phash_result(file_path)
    else:
        phash, phash_status, phash_error = None, "skipped", "thumbnail_failed"

    return _metadata_row(
        file_id,
        exif_data["date_taken"],
        exif_data["camera_model"],
        exif_data["gps_lat"],
        exif_data["gps_lon"],
        orig_w,
        orig_h,
        thumb_path or "__FAILED__",
        exif_json,
        datetime.now().isoformat(),
        phash,
        phash_status,
        phash_error,
        thumb_status,
        thumb_error,
        source_file_size,
        source_file_mtime,
    )


def _flush_pending_writes(pending_writes, limit=None):
    if not pending_writes:
        return 0
    rows_to_write = pending_writes if limit is None else pending_writes[:limit]
    with _db.connect() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO photo_metadata
               (file_id, date_taken, camera_model, gps_lat, gps_lon,
                width, height, thumbnail_path, exif_json, indexed_at, phash,
                phash_status, phash_error,
                thumbnail_status, thumbnail_error, source_file_size, source_file_mtime)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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


def index_photos(progress_callback=None, batch_limit=None, workers=INDEX_WORKERS, batch_size=INDEX_COMMIT_EVERY, force_retry=False):
    _db.init_tables()
    _reset_warning_counters()
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)

    photos = get_unindexed_photos(force_retry=force_retry)
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
