import os
import json
import sqlite3
from datetime import datetime
from PIL import Image, ImageOps
import exifread

from pillow_heif import register_heif_opener
register_heif_opener()

Image.MAX_IMAGE_PIXELS = 500_000_000

from logger_setup import logger
from config import THUMBNAIL_DIR, THUMBNAIL_SIZE, DATA_DIR
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

CHECKPOINT_FILE = os.path.join(DATA_DIR, "index_checkpoint.json")

_cp = CheckpointManager(CHECKPOINT_FILE)
_db = Database()

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
            WHERE f.is_image = 1 AND pm.file_id IS NULL
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
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    thumb_path = os.path.join(THUMBNAIL_DIR, thumbnail_name)

    if os.path.exists(thumb_path):
        return thumb_path, None, None

    try:
        with Image.open(filepath) as img:
            img.draft("RGB", THUMBNAIL_SIZE)
            img = _auto_rotate(img)
            w, h = img.size
            img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=80)
        return thumb_path, w, h
    except Exception as e:
        logger.error(f"缩略图生成失败 {filepath}: {e}")
        return None, None, None


INDEX_COMMIT_EVERY = 20


def index_photos(progress_callback=None, batch_limit=None):
    _db.init_tables()

    photos = get_unindexed_photos()
    total = len(photos)
    display_total = min(total, batch_limit) if batch_limit else total
    logger.info(f"开始索引照片: 共 {total} 张待索引")
    cp = _cp.load()
    start_idx = cp["current_index"] if cp else 0
    indexed = cp.get("indexed", 0) if cp else 0

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, indexed=0)
        logger.info("新索引任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, indexed={indexed}")

    conn = _db.get_persistent_connection()

    batch_count = 0

    for i in range(start_idx, total):
        file_id, file_path = photos[i]

        try:
            if not os.path.exists(file_path):
                logger.warning(f"文件不存在, 跳过: {file_path}")
                continue

            exif_data = extract_exif(file_path)

            thumbnail_name = f"{file_id}.jpg"
            thumb_path, orig_w, orig_h = generate_thumbnail(file_path, thumbnail_name)

            import json as json_mod
            exif_json = (
                json_mod.dumps(exif_data["raw"], ensure_ascii=False)
                if exif_data["raw"]
                else None
            )

            conn.execute(
                """INSERT OR REPLACE INTO photo_metadata
                   (file_id, date_taken, camera_model, gps_lat, gps_lon,
                    width, height, thumbnail_path, exif_json, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
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
                ),
            )
            indexed += 1
            batch_count += 1

            if indexed % INDEX_COMMIT_EVERY == 0:
                conn.commit()
        except Exception as e:
            logger.error(f"索引照片失败 {file_path}: {e}")

        if progress_callback:
            progress_callback(i + 1, display_total)

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, indexed=indexed)
            logger.info(f"索引热身完成: {indexed}/{total}, 剩余 {total - i - 1} 张后台继续")
            conn.commit()
            conn.close()
            return {"paused": True, "batch_limit_reached": True, "total": total, "indexed": indexed}

        if (i + 1) % 20 == 0:
            if _cp.is_pause_or_stop_requested():
                _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, indexed=indexed)
                logger.info(f"索引暂停: {indexed}/{total}")
                conn.commit()
                conn.close()
                return {"paused": True, "total": total, "indexed": indexed}

            _cp.save(CheckpointState.RUNNING, current_index=i + 1, total=total, indexed=indexed)

    conn.commit()
    conn.close()
    _cp.clear()
    logger.info(f"索引完成: 总计 {total}, 已索引 {indexed}")
    return {"total": total, "indexed": indexed}


if __name__ == "__main__":
    result = index_photos()
    if result.get("paused"):
        print(f"索引暂停: {result['indexed']}/{result['total']}")
    else:
        print(f"索引完成: 总计 {result['total']}, 已索引 {result['indexed']}")
