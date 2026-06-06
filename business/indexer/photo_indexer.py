import os
import json
import sqlite3
import contextlib
import io
import threading
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
STAT_SAMPLE_LIMIT = 3
MISSING_THUMBNAIL_REQUEUE_CHECK_LIMIT = 2000
_INDEX_OUTCOMES = {}
_INDEX_OUTCOMES_LOCK = threading.Lock()

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


def _set_index_outcome(file_id, outcome, thumbnail_path=None, error=None):
    with _INDEX_OUTCOMES_LOCK:
        _INDEX_OUTCOMES[file_id] = {
            "outcome": outcome,
            "thumbnail_path": thumbnail_path,
            "error": error,
        }


def _pop_index_outcome(file_id):
    with _INDEX_OUTCOMES_LOCK:
        return _INDEX_OUTCOMES.pop(file_id, None)


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


def get_unindexed_photos(force_retry=False, priority_filter=None):
    """获取待索引照片列表，按优先级分类返回。

    缩略图完成判定：
    - is_image=1
    - photo_metadata.thumbnail_path 有效（非 NULL、非空、非 '__FAILED__'）
    - 对应缩略图文件存在

    优先级（4 级队列）：
    1. new_changed_create: 本轮扫描新增/变化的文件，缩略图缺失 → P0 最高
    2. historical_missing: DB 中历史遗留，缩略图文件确实不存在 → P1
    3. recover_existing: 缩略图文件已存在但 DB 未回填 → P2
    4. failed_or_invalid: 之前失败的，仅 force_retry 时纳入 → P3

    path_status / canonical_key / path maintenance 不影响此查询。

    Args:
        force_retry: 是否纳入之前失败的项目
        priority_filter: 可选，指定只返回某一级队列
            'new_changed_create' / 'historical_missing' / 'recover_existing' / 'failed_or_invalid'
    """
    with _db.connect() as conn:
        # --- P0: new_changed_create ---
        # 条件：无 photo_metadata OR thumbnail_path 为空/''/失败且源文件变化
        # 且缩略图文件不存在（排除 recover_existing）
        new_changed_rows = conn.execute("""
            SELECT f.id, f.file_path, 'new_changed_create' AS category
            FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1
              AND (f.path_status IS NULL OR f.path_status NOT IN
                   ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
              AND (
                  pm.file_id IS NULL
                  OR pm.thumbnail_path IS NULL
                  OR pm.thumbnail_path = ''
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
            ORDER BY COALESCE(pm.date_taken, f.file_mtime) DESC, f.id
        """).fetchall()

        # 区分 P0(缩略图文件不存在) vs P2(缩略图文件已存在)
        p0_rows = []
        p2_rows = []
        _thumb_dir = get_settings().thumbnail_dir
        seen_ids = set()

        for row in new_changed_rows:
            file_id, file_path, _ = row
            if file_id in seen_ids:
                continue
            seen_ids.add(file_id)
            thumb_path = os.path.join(_thumb_dir, f"{file_id}.jpg")
            if os.path.exists(thumb_path):
                # 缩略图文件已存在但 DB 未回填 → P2 recover_existing
                p2_rows.append((file_id, file_path, "recover_existing"))
            else:
                # 缩略图文件不存在 → 需要真正创建
                # 进一步区分：有 pm 记录的是 historical_missing，否则是 new_changed_create
                has_pm = conn.execute(
                    "SELECT 1 FROM photo_metadata WHERE file_id = ?", (file_id,)
                ).fetchone()
                if has_pm:
                    p0_rows.append((file_id, file_path, "historical_missing"))
                else:
                    p0_rows.append((file_id, file_path, "new_changed_create"))

        # --- P3: failed_or_invalid (仅 force_retry) ---
        p3_rows = []
        if force_retry:
            p3_rows_raw = conn.execute("""
                SELECT f.id, f.file_path, 'failed_or_invalid' AS category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1
                  AND (f.path_status IS NULL OR f.path_status NOT IN
                       ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
                  AND pm.thumbnail_path = '__FAILED__'
                  AND pm.source_file_size = f.file_size
                  AND pm.source_file_mtime = f.file_mtime
                  AND pm.thumbnail_status IN ('failed', 'skipped')
                ORDER BY f.id
            """).fetchall()
            for row in p3_rows_raw:
                if row[0] not in seen_ids:
                    p3_rows.append(row)
                    seen_ids.add(row[0])

        # --- missing_on_disk 检查 ---
        missing_check_rows = conn.execute("""
            SELECT f.id, f.file_path, pm.thumbnail_path
            FROM files f
            JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1
              AND (f.path_status IS NULL OR f.path_status NOT IN
                   ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
              AND pm.thumbnail_path IS NOT NULL
              AND pm.thumbnail_path != ''
              AND pm.thumbnail_path != '__FAILED__'
              AND COALESCE(pm.thumbnail_status, 'ok') IN ('ok', 'recovered')
            ORDER BY f.id
            LIMIT ?
        """, (MISSING_THUMBNAIL_REQUEUE_CHECK_LIMIT,)).fetchall()

        for file_id, file_path, thumbnail_path in missing_check_rows:
            if file_id not in seen_ids and not os.path.exists(thumbnail_path):
                p0_rows.append((file_id, file_path, 'historical_missing'))
                seen_ids.add(file_id)

        # 按 priority_filter 过滤
        if priority_filter == 'new_changed_create':
            all_rows = [(fid, fp, cat) for fid, fp, cat in p0_rows if cat == 'new_changed_create']
        elif priority_filter == 'historical_missing':
            all_rows = [(fid, fp, cat) for fid, fp, cat in p0_rows if cat == 'historical_missing']
        elif priority_filter == 'recover_existing':
            all_rows = list(p2_rows)
        elif priority_filter == 'failed_or_invalid':
            all_rows = list(p3_rows)
        else:
            # 默认：按优先级合并 P0 → P1 → P2 → P3
            all_rows = list(p0_rows) + list(p2_rows) + list(p3_rows)

        logger.debug(
            "thumbnail queue classified: new_changed_create=%s historical_missing=%s "
            "recover_existing=%s failed_or_invalid=%s",
            sum(1 for _, _, c in p0_rows if c == 'new_changed_create'),
            sum(1 for _, _, c in p0_rows if c == 'historical_missing'),
            len(p2_rows),
            len(p3_rows),
        )
        return all_rows


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
        return thumb_path, None, None, "existing", None

    thumb_size = get_settings().thumbnail_size
    try:
        orig_w, orig_h = create_thumbnail_file(
            filepath,
            thumb_path,
            thumbnail_size=thumb_size,
            quality=THUMBNAIL_JPEG_QUALITY,
        )
        if not os.path.exists(thumb_path):
            return None, None, None, "failed", "thumbnail_file_missing_after_create"
        return thumb_path, orig_w, orig_h, "ok", None
    except Exception as e:
        error_type = _classify_image_error(e)
        if error_type == "truncated_or_broken_stream":
            try:
                orig_w, orig_h = _create_thumbnail_tolerant(filepath, thumb_path, thumb_size)
                if not os.path.exists(thumb_path):
                    return None, None, None, "failed", "thumbnail_file_missing_after_recover"
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
        _set_index_outcome(file_id, "path_invalid", error="source_file_missing")
        return _metadata_row(
            file_id,
            thumbnail_path="__FAILED__",
            phash_status="skipped",
            phash_error="source_file_missing",
            thumbnail_status="skipped",
            thumbnail_error="source_file_missing",
            source_file_size=source_file_size,
            source_file_mtime=source_file_mtime,
        )

    try:
        with Image.open(file_path) as _test:
            _test.load()  # 强制解码像素数据，提前捕获截断文件
    except Exception as e:
        error_type = _classify_image_error(e)
        if error_type == "corrupted_or_unreadable":
            _limited_warning("bad_image", f"无法识别图片, 标记跳过: {file_path}: {e}")
            _set_index_outcome(file_id, "thumbnail_skipped", error=f"{error_type}: {e}")
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
    if thumb_path and not os.path.exists(thumb_path):
        thumb_path = None
        thumb_status = "failed"
        thumb_error = "thumbnail_file_missing_after_create"

    if thumb_status == "existing":
        thumb_db_status = "ok"
        _set_index_outcome(file_id, "thumbnail_existing", thumbnail_path=thumb_path)
    elif thumb_status == "recovered":
        thumb_db_status = "recovered"
        _set_index_outcome(file_id, "thumbnail_recovered", thumbnail_path=thumb_path)
    elif thumb_path:
        thumb_db_status = "ok"
        _set_index_outcome(file_id, "thumbnail_created", thumbnail_path=thumb_path)
    else:
        thumb_db_status = "failed"
        _set_index_outcome(file_id, "thumbnail_failed", error=thumb_error)

    import json as json_mod
    exif_json = (
        json_mod.dumps(exif_data["raw"], ensure_ascii=False)
        if exif_data["raw"]
        else None
    )

    if thumb_path and os.path.exists(thumb_path):
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
        thumb_db_status,
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
    """batch_rows: list of (file_id, file_path, category) tuples."""
    if workers <= 1:
        results = []
        for file_id, file_path, _category in batch_rows:
            results.append((file_id, file_path, _index_single_photo(file_id, file_path), None))
        return results

    ordered_results = [None] * len(batch_rows)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_index_single_photo, file_id, file_path): (idx, file_id, file_path)
            for idx, (file_id, file_path, _category) in enumerate(batch_rows)
        }
        for future in as_completed(future_map):
            idx, file_id, file_path = future_map[future]
            try:
                row = future.result()
                ordered_results[idx] = (file_id, file_path, row, None)
            except Exception as exc:
                ordered_results[idx] = (file_id, file_path, None, exc)
    return ordered_results


def _new_index_stats(total):
    return {
        "total": total,
        "processed": 0,
        "indexed": 0,
        "thumbnail_created": 0,
        "thumbnail_existing": 0,
        "thumbnail_recovered": 0,
        "thumbnail_failed": 0,
        "thumbnail_skipped": 0,
        "skipped_failed": 0,
        "video_skipped": 0,
        "unsupported_media": 0,
        "path_invalid": 0,
        "db_updated": 0,
        "output_dir": get_settings().thumbnail_dir,
        "sample_created_paths": [],
        "sample_failed": [],
    }


def _record_index_result(stats, file_id, file_path, row, error):
    stats["processed"] += 1
    outcome = _pop_index_outcome(file_id) or {}
    outcome_name = outcome.get("outcome")
    if error is not None:
        stats["thumbnail_failed"] += 1
        if len(stats["sample_failed"]) < STAT_SAMPLE_LIMIT:
            stats["sample_failed"].append({"file_id": file_id, "path": file_path, "error": repr(error)})
        return
    if row is None:
        stats["thumbnail_skipped"] += 1
        return

    stats["indexed"] += 1
    thumb_path = row[7]
    thumb_status = row[13]
    thumb_error = row[14]

    if outcome_name == "path_invalid":
        stats["path_invalid"] += 1
    elif outcome_name == "thumbnail_existing":
        stats["thumbnail_existing"] += 1
    elif outcome_name == "thumbnail_recovered":
        stats["thumbnail_recovered"] += 1
        if thumb_path and len(stats["sample_created_paths"]) < STAT_SAMPLE_LIMIT:
            stats["sample_created_paths"].append(thumb_path)
    elif outcome_name == "thumbnail_created":
        stats["thumbnail_created"] += 1
        if thumb_path and len(stats["sample_created_paths"]) < STAT_SAMPLE_LIMIT:
            stats["sample_created_paths"].append(thumb_path)
    elif outcome_name == "thumbnail_skipped" or thumb_status == "skipped":
        stats["thumbnail_skipped"] += 1
    elif outcome_name == "thumbnail_failed" or thumb_status == "failed" or thumb_path == "__FAILED__":
        stats["thumbnail_failed"] += 1
    elif thumb_path and thumb_path != "__FAILED__":
        stats["thumbnail_created"] += 1
        if len(stats["sample_created_paths"]) < STAT_SAMPLE_LIMIT:
            stats["sample_created_paths"].append(thumb_path)

    if thumb_path == "__FAILED__" or thumb_status in ("failed", "skipped"):
        if len(stats["sample_failed"]) < STAT_SAMPLE_LIMIT:
            stats["sample_failed"].append({"file_id": file_id, "path": file_path, "error": thumb_error})


def index_photos(progress_callback=None, batch_limit=None, workers=INDEX_WORKERS, batch_size=INDEX_COMMIT_EVERY, force_retry=False, priority_filter=None):
    """索引照片，创建缩略图。

    Args:
        priority_filter: 可选，指定只处理某一级队列
            'new_changed_create' / 'historical_missing' / 'recover_existing' / 'failed_or_invalid'
            None = 按优先级合并处理所有队列
    """
    _db.init_tables()
    _reset_warning_counters()
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)

    photos = get_unindexed_photos(force_retry=force_retry, priority_filter=priority_filter)
    total = len(photos)
    stats = _new_index_stats(total)
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
            _record_index_result(stats, file_id, file_path, row, error)
            if error is not None:
                logger.error(f"索引照片失败 {file_path}: {error}")
            elif row is not None:
                pending_writes.append(row)
                indexed += 1
                batch_count += 1

            while len(pending_writes) >= INDEX_COMMIT_EVERY:
                stats["db_updated"] += _flush_pending_writes(pending_writes, limit=INDEX_COMMIT_EVERY)

            if progress_callback:
                progress_callback(batch_start + offset + 1, total)

        if pending_writes:
            stats["db_updated"] += _flush_pending_writes(pending_writes)

        logger.info(
            "缩略图索引批次结果: processed=%s created=%s existing=%s recovered=%s failed=%s "
            "skipped=%s path_invalid=%s db_updated=%s output_dir=%s",
            stats["processed"],
            stats["thumbnail_created"],
            stats["thumbnail_existing"],
            stats["thumbnail_recovered"],
            stats["thumbnail_failed"],
            stats["thumbnail_skipped"],
            stats["path_invalid"],
            stats["db_updated"],
            stats["output_dir"],
        )
        if stats["sample_created_paths"] or stats["sample_failed"]:
            logger.debug(
                "缩略图索引样本: sample_created=%s sample_failed=%s",
                stats["sample_created_paths"],
                stats["sample_failed"],
            )

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=batch_end, total=total, indexed=indexed)
            logger.info(f"索引热身完成: {indexed}/{total}, 剩余 {total - batch_end} 张后台继续")
            stats.update({"paused": True, "batch_limit_reached": True, "total": total, "indexed": indexed})
            return stats

        if _cp.is_pause_or_stop_requested():
            _cp.save(CheckpointState.PAUSED, current_index=batch_end, total=total, indexed=indexed)
            logger.info(f"索引暂停: {indexed}/{total}")
            stats.update({"paused": True, "total": total, "indexed": indexed})
            return stats

        _cp.save(CheckpointState.RUNNING, current_index=batch_end, total=total, indexed=indexed)

    if pending_writes:
        stats["db_updated"] += _flush_pending_writes(pending_writes)

    _cp.clear()
    logger.info(f"索引完成: 总计 {total}, 已索引 {indexed}")

    dedup_by_phash()

    stats.update({"total": total, "indexed": indexed})
    return stats


def diagnose_thumbnail_index_state(db_path=None, sample_limit=3):
    db = Database(db_path) if db_path else _db
    result = {
        "thumbnail_path_empty": 0,
        "thumbnail_failed": 0,
        "thumbnail_ok_file_missing": 0,
        "sample_missing": [],
    }
    with db.connect() as conn:
        result["thumbnail_path_empty"] = conn.execute(
            """SELECT COUNT(*) FROM files f
               LEFT JOIN photo_metadata pm ON f.id = pm.file_id
               WHERE f.is_image = 1 AND (pm.file_id IS NULL OR pm.thumbnail_path IS NULL OR pm.thumbnail_path = '')"""
        ).fetchone()[0]
        result["thumbnail_failed"] = conn.execute(
            """SELECT COUNT(*) FROM photo_metadata
               WHERE thumbnail_path = '__FAILED__' OR thumbnail_status IN ('failed', 'skipped')"""
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT file_id, thumbnail_path FROM photo_metadata
               WHERE thumbnail_path IS NOT NULL
                 AND thumbnail_path != ''
                 AND thumbnail_path != '__FAILED__'
                 AND COALESCE(thumbnail_status, 'ok') IN ('ok', 'recovered')"""
        ).fetchall()
    for file_id, thumbnail_path in rows:
        if not os.path.exists(thumbnail_path):
            result["thumbnail_ok_file_missing"] += 1
            if len(result["sample_missing"]) < sample_limit:
                result["sample_missing"].append({"file_id": file_id, "thumbnail_path": thumbnail_path})
    return result


def index_new_or_changed_files(progress_callback=None, workers=INDEX_WORKERS, batch_size=INDEX_COMMIT_EVERY):
    """优先索引 new/changed 文件的缩略图。

    仅处理 new_changed_create 和 historical_missing 队列，
    跳过 recover_existing 队列。
    用于扫描完成后第一时间让新图片可用。
    """
    _db.init_tables()
    _reset_warning_counters()
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)

    # P0 + P1: new_changed_create + historical_missing
    photos_p0 = get_unindexed_photos(priority_filter='new_changed_create')
    photos_p1 = get_unindexed_photos(priority_filter='historical_missing')
    photos = list(photos_p0) + list(photos_p1)
    total = len(photos)

    if total == 0:
        logger.info("start thumbnail create for new/changed files: count=0 (none pending)")
        return {"total": 0, "indexed": 0, "processed": 0,
                "thumbnail_created": 0, "thumbnail_existing": 0}

    logger.info("start thumbnail create for new/changed files: count=%s", total)
    stats = _new_index_stats(total)

    pending_writes = []
    indexed = 0

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_rows = photos[batch_start:batch_end]
        batch_results = _process_index_batch(batch_rows, workers)

        for offset, (file_id, file_path, row, error) in enumerate(batch_results):
            _record_index_result(stats, file_id, file_path, row, error)
            if error is not None:
                logger.error(f"索引照片失败 {file_path}: {error}")
            elif row is not None:
                pending_writes.append(row)
                indexed += 1

            while len(pending_writes) >= INDEX_COMMIT_EVERY:
                stats["db_updated"] += _flush_pending_writes(pending_writes, limit=INDEX_COMMIT_EVERY)

            if progress_callback:
                progress_callback(batch_start + offset + 1, total)

        if pending_writes:
            stats["db_updated"] += _flush_pending_writes(pending_writes)

    if pending_writes:
        stats["db_updated"] += _flush_pending_writes(pending_writes)

    stats.update({"total": total, "indexed": indexed})
    logger.info(
        "new/changed thumbnail batch: created=%s existing=%s recovered=%s failed=%s "
        "path_invalid=%s db_updated=%s",
        stats["thumbnail_created"], stats["thumbnail_existing"],
        stats["thumbnail_recovered"], stats["thumbnail_failed"],
        stats["path_invalid"], stats["db_updated"],
    )
    return stats


def recover_existing_thumbnails(progress_callback=None, workers=INDEX_WORKERS, batch_size=INDEX_COMMIT_EVERY, batch_limit=None):
    """低优先级回填历史 existing 缩略图。

    仅处理 recover_existing 队列：缩略图文件已存在但 DB 未回填。
    不会挡住 new/changed 缩略图创建。
    """
    _db.init_tables()
    _reset_warning_counters()
    workers = max(int(workers), 1)
    batch_size = max(int(batch_size), 1)

    photos = get_unindexed_photos(priority_filter='recover_existing')
    total = len(photos)

    if total == 0:
        logger.info("recover_existing: no thumbnails to recover")
        return {"total": 0, "indexed": 0, "processed": 0,
                "thumbnail_created": 0, "thumbnail_existing": 0}

    logger.info("recover_existing: processing %s thumbnails (P2 low priority)", total)
    stats = _new_index_stats(total)

    if batch_limit:
        photos = photos[:batch_limit]
        total = len(photos)

    pending_writes = []
    indexed = 0

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_rows = photos[batch_start:batch_end]
        batch_results = _process_index_batch(batch_rows, workers)

        for offset, (file_id, file_path, row, error) in enumerate(batch_results):
            _record_index_result(stats, file_id, file_path, row, error)
            if error is not None:
                logger.error(f"索引照片失败 {file_path}: {error}")
            elif row is not None:
                pending_writes.append(row)
                indexed += 1

            while len(pending_writes) >= INDEX_COMMIT_EVERY:
                stats["db_updated"] += _flush_pending_writes(pending_writes, limit=INDEX_COMMIT_EVERY)

        if pending_writes:
            stats["db_updated"] += _flush_pending_writes(pending_writes)

    if pending_writes:
        stats["db_updated"] += _flush_pending_writes(pending_writes)

    stats.update({"total": total, "indexed": indexed})
    logger.info(
        "recover_existing batch: created=%s existing=%s recovered=%s failed=%s db_updated=%s",
        stats["thumbnail_created"], stats["thumbnail_existing"],
        stats["thumbnail_recovered"], stats["thumbnail_failed"], stats["db_updated"],
    )
    return stats
