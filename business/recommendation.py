"""Photo query, ranking, and random memory sequencing shared by the web application."""

import os
import random
import time
from datetime import datetime

from db_manager import Database
from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from business.classifier.category_rules import (
    category_match_sql,
    category_match_without_folder_sql,
    sample_keyword_exists_sql,
    strong_life_source_sql,
    strong_sample_source_sql,
)
from business.deletion_queue import pending_delete_filter_sql

# 路径健康状态过滤条件：排除 damaged/missing/stat_failed/outside_root
# 旧数据 path_status 为 NULL 的仍然可见（兼容）
_PATH_STATUS_FILTER = (
    "AND (f.path_status IS NULL OR f.path_status NOT IN "
    "('damaged_path', 'missing', 'stat_failed', 'outside_root')) "
    + pending_delete_filter_sql("f")
)

CATEGORY_COLORS = {
    1: "#27ae60", 2: "#2980b9",
}

PAGE_SIZE = 30
MAX_SAME_FOLDER_STREAK = 12
SMALL_FOLDER_THRESHOLD = 100
FRESHNESS_WINDOW_DAYS = 30
RANDOM_CANDIDATE_LIMIT = 9999
MIN_FRESH_RANDOM_CANDIDATES = PAGE_SIZE * 2
FAST_RANDOM_CANDIDATE_MULTIPLIER = 4
MAX_SAME_DAY_STREAK = 12
MIN_MEMORY_VISIBLE_REFS = 4
SQL_PARAM_CHUNK_SIZE = 900
SQL_EXCLUDE_TEMP_TABLE_THRESHOLD = SQL_PARAM_CHUNK_SIZE
TEMP_EXCLUDED_FILE_IDS_TABLE = "random_excluded_file_ids"
MEMORY_ROW_BATCH_SIZE = 32
FOREGROUND_MEMORY_PRIORITY_LIMIT = 12
FOREGROUND_MEMORY_ROW_SCAN_LIMIT = MEMORY_ROW_BATCH_SIZE * 8
DEFAULT_RANDOM_NEARBY_STREAK = 3
EXPANDED_RANDOM_NEARBY_STREAK = DEFAULT_RANDOM_NEARBY_STREAK
PROXIMITY_INTEREST_LIMIT = 12
MEMORY_SEGMENT_MIN = 10
MEMORY_SEGMENT_MAX = 25
MEMORY_SEGMENT_EVENT_GAP_HOURS = 36
MEMORY_SEGMENT_LOOKAHEAD = 32
DIVERSITY_DAY_HISTORY = MEMORY_SEGMENT_MAX


def _sample_keyword_exists_sql():
    return sample_keyword_exists_sql()


def _path_text_sql():
    from business.classifier.category_rules import path_text_sql
    return path_text_sql()


def _strong_life_source_sql():
    return strong_life_source_sql()


def _strong_sample_source_sql():
    return strong_sample_source_sql()


def _category_match_sql(cat_id):
    return category_match_sql(cat_id)


def _category_match_without_folder_sql(cat_id):
    return category_match_without_folder_sql(cat_id)


def _normalize_file_ids(file_ids):
    normalized = []
    seen = set()
    for pid in file_ids or []:
        if pid is None:
            continue
        try:
            file_id = int(pid)
        except (TypeError, ValueError):
            continue
        if file_id in seen:
            continue
        seen.add(file_id)
        normalized.append(file_id)
    return normalized


def _exclude_file_ids_sql(db, exclude_ids):
    excluded_ids = _normalize_file_ids(exclude_ids)
    if not excluded_ids:
        return "", []
    if len(excluded_ids) <= SQL_EXCLUDE_TEMP_TABLE_THRESHOLD:
        return f"AND f.id NOT IN ({','.join('?' for _ in excluded_ids)})", excluded_ids

    db.execute(
        f"CREATE TEMP TABLE IF NOT EXISTS {TEMP_EXCLUDED_FILE_IDS_TABLE} "
        "(file_id INTEGER PRIMARY KEY)"
    )
    db.execute(f"DELETE FROM {TEMP_EXCLUDED_FILE_IDS_TABLE}")
    db.executemany(
        f"INSERT OR IGNORE INTO {TEMP_EXCLUDED_FILE_IDS_TABLE}(file_id) VALUES (?)",
        ((pid,) for pid in excluded_ids),
    )
    return (
        f"AND NOT EXISTS (SELECT 1 FROM {TEMP_EXCLUDED_FILE_IDS_TABLE} "
        "excluded WHERE excluded.file_id = f.id)",
        [],
    )


def _interleave_small_folders(photos):
    if not photos:
        return photos

    folder_counts = {}
    for p in photos:
        fp = p.get("folder_path", "")
        folder_counts[fp] = folder_counts.get(fp, 0) + 1

    small_folders = {fp for fp, cnt in folder_counts.items() if cnt < SMALL_FOLDER_THRESHOLD}

    if not small_folders:
        return photos

    result = []
    streak_folder = None
    streak_count = 0
    pending = list(photos)

    while pending:
        placed = False
        for i, p in enumerate(pending):
            fp = p.get("folder_path", "")
            is_small = fp in small_folders

            if is_small and fp == streak_folder and streak_count >= MAX_SAME_FOLDER_STREAK:
                continue

            result.append(p)
            pending.pop(i)
            if fp == streak_folder:
                streak_count += 1
            else:
                streak_folder = fp
                streak_count = 1
            placed = True
            break

        if not placed:
            streak_folder = None
            streak_count = 0
            result.append(pending.pop(0))

    return result


def _interleave_by_time(photos):
    if not photos:
        return photos

    day_groups = {}
    day_order = []
    for p in photos:
        dt = p.get("date_taken", "")
        if dt and len(dt) >= 10:
            day = dt[:10]
        else:
            mtime = p.get("file_mtime", "")
            day = mtime[:10] if mtime and len(mtime) >= 10 else "unknown"
        if day not in day_groups:
            day_groups[day] = []
            day_order.append(day)
        day_groups[day].append(p)

    result = []
    streak_day = None
    streak_count = 0
    pending = {day: list(ps) for day, ps in day_groups.items()}

    while any(pending.values()):
        placed = False
        for day in day_order:
            if not pending.get(day):
                continue
            if day == streak_day and streak_count >= MAX_SAME_DAY_STREAK:
                continue
            p = pending[day].pop(0)
            result.append(p)
            if day == streak_day:
                streak_count += 1
            else:
                streak_day = day
                streak_count = 1
            placed = True
            break

        if not placed:
            streak_day = None
            streak_count = 0
            for day in day_order:
                if pending.get(day):
                    result.append(pending[day].pop(0))
                    streak_day = day
                    streak_count = 1
                    placed = True
                    break

    return result


def _photo_day(photo):
    dt = photo.get("date_taken", "")
    if dt and len(dt) >= 10:
        return dt[:10]
    mtime = photo.get("file_mtime", "")
    return mtime[:10] if mtime and len(mtime) >= 10 else "unknown"


def _photo_time_bucket(photo):
    day = _photo_day(photo)
    if day == "unknown" or len(day) < 10:
        return ""
    try:
        week_in_month = (int(day[8:10]) - 1) // 7 + 1
    except (TypeError, ValueError):
        return day[:7]
    return f"{day[:7]}-w{week_in_month}"


def photo_visual_key(photo):
    """Stable recommendation-only identity for duplicate suppression across batches."""
    phash = str(photo.get("phash") or "").strip().lower()
    if phash:
        return ("phash", phash)
    file_path = photo.get("file_path") or ""
    if file_path:
        return ("path", os.path.normcase(os.path.normpath(file_path)))
    photo_id = photo.get("id")
    return ("id", int(photo_id)) if photo_id is not None else None


def _photo_timestamp(photo):
    value = photo.get("date_taken") or photo.get("file_mtime") or ""
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.toordinal() * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second
    except (TypeError, ValueError, OverflowError):
        return 0


def _sequence_memory_segments(photos, prior_photos=None, rng=None, with_boundaries=False):
    """Build coherent memory runs capped at 25 photos, preserving shorter runs as-is."""
    if not photos:
        return ([], set()) if with_boundaries else []

    rng = rng or random
    grouped = {}
    for photo in photos:
        folder = photo.get("folder_path") or ""
        group_key = folder or f"__time__:{_photo_time_bucket(photo) or 'unknown'}"
        grouped.setdefault(group_key, []).append(photo)

    segments = []
    max_gap = MEMORY_SEGMENT_EVENT_GAP_HOURS * 3600
    for group_key, group_photos in grouped.items():
        ordered = sorted(
            group_photos,
            key=lambda photo: (_photo_timestamp(photo), int(photo.get("id") or 0)),
        )
        current = []
        previous_timestamp = 0
        target_size = MEMORY_SEGMENT_MAX
        for photo in ordered:
            timestamp = _photo_timestamp(photo)
            separated_event = bool(
                current
                and previous_timestamp
                and timestamp
                and timestamp - previous_timestamp > max_gap
            )
            if current and (len(current) >= target_size or separated_event):
                middle = current[len(current) // 2]
                segments.append({
                    "photos": current,
                    "folder": current[0].get("folder_path") or group_key,
                    "time_bucket": _photo_time_bucket(middle),
                })
                current = []
                target_size = MEMORY_SEGMENT_MAX
            current.append(photo)
            previous_timestamp = timestamp
        if current:
            middle = current[len(current) // 2]
            segments.append({
                "photos": current,
                "folder": current[0].get("folder_path") or group_key,
                "time_bucket": _photo_time_bucket(middle),
            })

    rng.shuffle(segments)
    recent_folders = [photo.get("folder_path") or "" for photo in list(prior_photos or [])[-2:]]
    recent_buckets = [_photo_time_bucket(photo) for photo in list(prior_photos or [])[-2:]]
    ordered_segments = []
    while segments:
        lookahead = min(MEMORY_SEGMENT_LOOKAHEAD, len(segments))
        best_index = 0
        best_score = None
        for index, segment in enumerate(segments[:lookahead]):
            folder = segment["folder"]
            bucket = segment["time_bucket"]
            score = index * 0.01
            if recent_folders and folder == recent_folders[-1]:
                score += 1000
            elif folder and folder in recent_folders:
                score += 180
            if recent_buckets and bucket and bucket == recent_buckets[-1]:
                score += 600
            elif bucket and bucket in recent_buckets:
                score += 100
            if best_score is None or score < best_score:
                best_score = score
                best_index = index
        segment = segments.pop(best_index)
        ordered_segments.append(segment)
        recent_folders = (recent_folders + [segment["folder"]])[-3:]
        recent_buckets = (recent_buckets + [segment["time_bucket"]])[-3:]

    result = []
    boundaries = set()
    for segment in ordered_segments:
        boundaries.add(len(result))
        result.extend(segment["photos"])
    return (result, boundaries) if with_boundaries else result


def _diversify_random_photos(photos, prior_photos=None, rng=None):
    """Compatibility entry: random feeds now alternate coherent memory segments."""
    return _sequence_memory_segments(photos, prior_photos=prior_photos, rng=rng)


def _interleave_by_key_with_streak(photos, key_func, default_streak, expanded_streak=None, expanded_keys=None):
    if not photos:
        return photos

    expanded_keys = set(expanded_keys or [])
    expanded_streak = expanded_streak or default_streak
    groups = {}
    key_order = []
    for photo in photos:
        key = key_func(photo)
        if key not in groups:
            groups[key] = []
            key_order.append(key)
        groups[key].append(photo)

    result = []
    streak_key = None
    streak_count = 0

    while any(groups.values()):
        placed = False
        for key in key_order:
            pending = groups.get(key)
            if not pending:
                continue
            max_streak = expanded_streak if key in expanded_keys else default_streak
            if key == streak_key and streak_count >= max_streak:
                continue
            result.append(pending.pop(0))
            if key == streak_key:
                streak_count += 1
            else:
                streak_key = key
                streak_count = 1
            placed = True
            break

        if not placed:
            for key in key_order:
                pending = groups.get(key)
                if pending:
                    result.append(pending.pop(0))
                    if key == streak_key:
                        streak_count += 1
                    else:
                        streak_key = key
                        streak_count = 1
                    break

    return result


def _spread_nearby_photos(photos, expanded_folders=None, expanded_days=None):
    # Interest signals no longer relax diversity in the random feed. They remain available
    # to explicit memory/detail views where nearby photos are an intentional interaction.
    return _diversify_random_photos(photos)


def _load_proximity_interest_keys(db, cat_id, limit=PROXIMITY_INTEREST_LIMIT):
    folders = set()
    days = set()

    def add_interest(folder_path, day_value):
        if folder_path:
            folders.add(folder_path)
        if day_value and len(day_value) >= 10:
            days.add(day_value[:10])

    try:
        clicked_rows = db.execute(
            """
            SELECT ch.folder_path, COALESCE(pm.date_taken, f.file_mtime) AS day_value
            FROM click_history ch
            LEFT JOIN files f ON f.id = ch.file_id
            LEFT JOIN photo_metadata pm ON pm.file_id = ch.file_id
            WHERE ch.category = ?
            ORDER BY ch.clicked_at DESC
            LIMIT ?
            """,
            (cat_id, limit),
        ).fetchall()
        for row in clicked_rows:
            add_interest(row["folder_path"], row["day_value"])
    except Exception:
        pass

    try:
        starred_rows = db.execute(
            """
            SELECT f.folder_path, COALESCE(pm.date_taken, f.file_mtime) AS day_value
            FROM photo_metadata pm
            JOIN files f ON f.id = pm.file_id
            WHERE pm.is_starred = 1
            ORDER BY COALESCE(pm.date_taken, f.file_mtime) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in starred_rows:
            add_interest(row["folder_path"], row["day_value"])
    except Exception:
        pass

    return {"folders": folders, "days": days}


def _make_photo_dict(r):
    return {
        "id": r["id"], "file_path": r["file_path"], "file_name": r["file_name"],
        "folder_path": r["folder_path"],
        "folder_name": r["folder_display"] if "folder_display" in r.keys() else os.path.basename(r["folder_path"]),
        "thumbnail_path": r["thumbnail_path"] if "thumbnail_path" in r.keys() and r["thumbnail_path"] else "",
        "width": r["width"] if "width" in r.keys() else None,
        "height": r["height"] if "height" in r.keys() else None,
        "date_taken": r["date_taken"] if "date_taken" in r.keys() else None,
        "file_mtime": r["file_mtime"] if "file_mtime" in r.keys() else None,
        "phash": r["phash"] if "phash" in r.keys() else None,
        "is_starred": r["is_starred"] if "is_starred" in r.keys() else 0,
    }


def _has_renderable_thumbnail(photo):
    thumb = photo.get("thumbnail_path", "")
    return bool(thumb and thumb != "__FAILED__" and os.path.exists(thumb))


def _filter_renderable_photos(photos):
    return [p for p in photos if _has_renderable_thumbnail(p)]


def _chunks(items, size=SQL_PARAM_CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]

def _get_recently_shown_ids(db, cat_id, days=FRESHNESS_WINDOW_DAYS, file_ids=None):
    if file_ids is not None:
        candidate_ids = _normalize_file_ids(file_ids)
        if not candidate_ids:
            return set()
        recent_ids = set()
        for chunk in _chunks(candidate_ids):
            placeholders = ",".join("?" * len(chunk))
            rows = db.execute(
                "SELECT DISTINCT file_id FROM photo_shown_history "
                "WHERE category = ? AND shown_at >= datetime('now', ?) "
                f"AND file_id IN ({placeholders})",
                [cat_id, f"-{days} days"] + chunk,
            ).fetchall()
            recent_ids.update(r["file_id"] for r in rows)
        return recent_ids

    rows = db.execute(
        "SELECT DISTINCT file_id FROM photo_shown_history "
        "WHERE category = ? AND shown_at >= datetime('now', ?)",
        (cat_id, f"-{days} days"),
    ).fetchall()
    return {r["file_id"] for r in rows}


def record_shown_photos(photos, cat_id):
    if not photos:
        return
    rows = [(p["id"], cat_id) for p in photos]
    with Database().connect() as conn:
        conn.executemany(
            "INSERT INTO photo_shown_history (file_id, category, shown_at) VALUES (?, ?, datetime('now'))",
            rows,
        )


def load_photos_from_ids(db, all_ids, require_thumbnail=False, preserve_order=False):
    if not all_ids:
        return []
    seen = set()
    unique_ids = []
    for pid in all_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    rows = []
    for chunk in _chunks(unique_ids):
        placeholders = ",".join("?" * len(chunk))
        rows.extend(db.execute(
            f"""SELECT f.id, f.file_path, f.file_name, f.folder_path,
                       f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                       pm.width, pm.height, pm.date_taken
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.id IN ({placeholders})
                      {_PATH_STATUS_FILTER}
                      AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')""",
            chunk,
        ).fetchall())
    by_id = {}
    for r in rows:
        d = _make_photo_dict(r)
        if require_thumbnail:
            if _has_renderable_thumbnail(d):
                by_id[d["id"]] = d
        elif not d.get("thumbnail_path") or os.path.exists(d["thumbnail_path"]):
            by_id[d["id"]] = d
    valid = [by_id[pid] for pid in unique_ids if pid in by_id]
    if preserve_order:
        return valid
    return _interleave_small_folders(valid)


def _filter_photos_for_category(db, cat_id, photos):
    if not photos:
        return []
    photo_ids = [p["id"] for p in photos]
    valid_ids = set()
    for chunk in _chunks(photo_ids):
        placeholders = ",".join("?" * len(chunk))
        valid_ids.update(
            r[0] for r in db.execute(
                f"""SELECT f.id
                    FROM files f
                    LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                    LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                    WHERE {_category_match_sql(cat_id)} AND f.id IN ({placeholders})""",
                [cat_id] + chunk,
            ).fetchall()
        )
    return [p for p in photos if p["id"] in valid_ids]


def _supplement_memory_photos(db, cat_id, photos, excluded_ids, needed):
    if needed <= 0:
        return []

    folders = [p.get("folder_path") for p in photos if p.get("folder_path")]
    dates = []
    for p in photos:
        dt = p.get("date_taken") or p.get("file_mtime")
        if dt and len(dt) >= 10:
            dates.append(dt[:10])

    seen = set(excluded_ids)
    result = []
    candidate_limit = max(needed * 10, MIN_MEMORY_VISIBLE_REFS * 3)

    def add_rows(rows):
        nonlocal needed
        for r in rows:
            p = _make_photo_dict(r)
            if p["id"] in seen or not _has_renderable_thumbnail(p):
                continue
            seen.add(p["id"])
            result.append(p)
            needed -= 1
            if needed <= 0:
                break

    base_select = f"""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
        JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE {_category_match_sql(cat_id)}
          {_PATH_STATUS_FILTER}
          AND f.is_image IN (0, 1)
          AND pm.thumbnail_path IS NOT NULL
          AND pm.thumbnail_path != '__FAILED__'
          AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
    """

    for folder in folders[:3]:
        if needed <= 0:
            break
        rows = db.execute(
            base_select + " AND f.folder_path = ? ORDER BY pm.date_taken DESC LIMIT ?",
            (cat_id, folder, candidate_limit),
        ).fetchall()
        add_rows(rows)

    for day in dates[:3]:
        if needed <= 0:
            break
        rows = db.execute(
            base_select + " AND COALESCE(pm.date_taken, f.file_mtime) LIKE ? ORDER BY pm.date_taken DESC LIMIT ?",
            (cat_id, f"{day}%", candidate_limit),
        ).fetchall()
        add_rows(rows)

    if needed > 0:
        rows = db.execute(
            base_select + " ORDER BY pm.date_taken DESC LIMIT ?",
            (cat_id, candidate_limit),
        ).fetchall()
        add_rows(rows)

    return result


def _load_ranked_memory_photos(db, cat_id, limit=None, exclude_ids=None, max_memory_rows=None):
    ranked = []
    excluded = set(exclude_ids or [])
    seen_ids = set(excluded)
    cursor = db.execute(
        """SELECT id, photo_ids, cover_file_id FROM memories
           WHERE category = ? AND dismissed_at IS NULL AND (is_hidden IS NULL OR is_hidden = 0)
           ORDER BY created_at DESC""",
        (cat_id,),
    )

    import json

    scanned_rows = 0
    while True:
        fetch_size = MEMORY_ROW_BATCH_SIZE
        if max_memory_rows is not None:
            remaining_rows = max(int(max_memory_rows) - scanned_rows, 0)
            if remaining_rows <= 0:
                break
            fetch_size = min(fetch_size, remaining_rows)
        rows = cursor.fetchmany(fetch_size)
        if not rows:
            break
        scanned_rows += len(rows)
        memory_batch = []
        for row in rows:
            try:
                photo_ids = json.loads(row["photo_ids"] or "[]")
            except Exception:
                continue
            if photo_ids:
                memory_batch.append((row, photo_ids))
        if not memory_batch:
            continue

        batch_photo_ids = []
        for _, photo_ids in memory_batch:
            batch_photo_ids.extend(photo_ids)
        loaded = load_photos_from_ids(db, batch_photo_ids, require_thumbnail=True, preserve_order=True)
        loaded = _filter_photos_for_category(db, cat_id, loaded)
        photos_by_id = {p["id"]: p for p in loaded}

        for row, photo_ids in memory_batch:
            photos = _interleave_small_folders([photos_by_id[pid] for pid in photo_ids if pid in photos_by_id])
            if len(photos) < MIN_MEMORY_VISIBLE_REFS:
                photos.extend(
                    _supplement_memory_photos(
                        db,
                        cat_id,
                        photos,
                        set(photo_ids) | seen_ids,
                        MIN_MEMORY_VISIBLE_REFS - len(photos),
                    )
                )
            if len(photos) < MIN_MEMORY_VISIBLE_REFS:
                continue

            cover_id = row["cover_file_id"]
            visible_ids = {p["id"] for p in photos}
            if cover_id not in visible_ids and photos:
                pass

            for p in photos:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    ranked.append(p)
                    if limit is not None and len(ranked) >= limit:
                        return ranked

    return ranked


def _random_candidate_limit(limit):
    if limit is None:
        return RANDOM_CANDIDATE_LIMIT
    return min(
        RANDOM_CANDIDATE_LIMIT,
        max(limit * FAST_RANDOM_CANDIDATE_MULTIPLIER, MIN_FRESH_RANDOM_CANDIDATES),
    )


def _max_file_id(db):
    row = db.execute("SELECT COALESCE(MAX(id), 0) FROM files").fetchone()
    return int(row[0]) if row and row[0] else 0


def _load_category_photo_rows(
    db,
    cat_id,
    *,
    limit,
    offset=0,
    exclude_recent_days=None,
    order_clause="pm.date_taken DESC",
    extra_where="",
    extra_params=None,
    exclude_ids=None,
    use_folder_categories=True,
    require_thumbnail=False,
):
    recent_filter = ""
    exclude_filter = ""
    thumbnail_filter = (
        "AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'"
        if require_thumbnail
        else "AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')"
    )
    params = []
    if use_folder_categories:
        category_sql = _category_match_sql(cat_id)
        params.append(cat_id)
        folder_join = "LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path"
    else:
        category_sql = _category_match_without_folder_sql(cat_id)
        folder_join = ""

    if exclude_recent_days:
        recent_filter = """
              AND NOT EXISTS (
                  SELECT 1 FROM photo_shown_history psh
                  WHERE psh.file_id = f.id
                    AND psh.category = ?
                    AND psh.shown_at >= datetime('now', ?)
              )
        """
        params.extend([cat_id, f"-{exclude_recent_days} days"])
    params.extend(extra_params or [])
    exclude_filter, exclude_params = _exclude_file_ids_sql(db, exclude_ids)
    params.extend(exclude_params)
    params.extend([limit, offset])
    return db.execute(f"""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken, pm.phash, pm.is_starred
        FROM files f
        {folder_join}
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE {category_sql} AND f.is_image IN (0, 1)
              {_PATH_STATUS_FILTER}
              {thumbnail_filter}
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
              {recent_filter}
              {extra_where}
              {exclude_filter}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """, params).fetchall()


def _rows_to_visible_photos(rows, require_thumbnail=False):
    valid = []
    for r in rows:
        d = _make_photo_dict(r)
        if require_thumbnail:
            if _has_renderable_thumbnail(d):
                valid.append(d)
        elif not d.get("thumbnail_path") or os.path.exists(d["thumbnail_path"]):
            valid.append(d)
    return valid


def _load_category_photos_random_window(
    db,
    cat_id,
    limit,
    exclude_recent_days=None,
    exclude_ids=None,
    require_thumbnail=False,
    starred_only=False,
):
    max_id = _max_file_id(db)
    if max_id <= 0:
        return []

    query_limit = limit if require_thumbnail or limit >= RANDOM_CANDIDATE_LIMIT else max(limit * 3, limit)

    def collect(use_folder_categories=True):
        # Multiplication by an odd constant is a permutation modulo 2^31. It spreads
        # adjacent file IDs globally while evaluating the expensive category filter once.
        seed = random.randint(0, 2147483647)
        order_clause = f"((f.id * 1103515245 + {seed}) & 2147483647)"
        rows = _load_category_photo_rows(
            db,
            cat_id,
            limit=query_limit,
            exclude_recent_days=exclude_recent_days,
            order_clause=order_clause,
            exclude_ids=exclude_ids,
            use_folder_categories=use_folder_categories,
            require_thumbnail=require_thumbnail,
            extra_where="AND pm.is_starred = 1" if starred_only else "",
        )
        photos = _rows_to_visible_photos(rows, require_thumbnail=require_thumbnail)
        random.shuffle(photos)
        return _diversify_random_photos(photos)[:limit]

    photos = collect(use_folder_categories=True)
    if not photos:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            photos = collect(use_folder_categories=False)
    return photos


def load_category_photos_batch(
    db,
    cat_id,
    offset,
    limit=PAGE_SIZE,
    exclude_recent_days=None,
    random_order=False,
    exclude_ids=None,
    require_thumbnail=False,
    starred_only=False,
):
    if random_order and offset == 0:
        return _load_category_photos_random_window(
            db,
            cat_id,
            max(int(limit), 1),
            exclude_recent_days=exclude_recent_days,
            exclude_ids=exclude_ids,
            require_thumbnail=require_thumbnail,
            starred_only=starred_only,
        )

    order_clause = "RANDOM()" if random_order else "pm.date_taken DESC"
    rows = _load_category_photo_rows(
        db,
        cat_id,
        limit=limit,
        offset=offset,
        exclude_recent_days=exclude_recent_days,
        order_clause=order_clause,
        exclude_ids=exclude_ids,
        require_thumbnail=require_thumbnail,
        extra_where="AND pm.is_starred = 1" if starred_only else "",
    )
    if not rows and offset == 0:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            rows = _load_category_photo_rows(
                db,
                cat_id,
                limit=limit,
                offset=0,
                exclude_recent_days=exclude_recent_days,
                order_clause=order_clause,
                exclude_ids=exclude_ids,
                use_folder_categories=False,
                require_thumbnail=require_thumbnail,
                extra_where="AND pm.is_starred = 1" if starred_only else "",
            )
    return _interleave_small_folders(_rows_to_visible_photos(rows, require_thumbnail=require_thumbnail))

def load_starred_photos(db, cat_id, limit=None, exclude_ids=None):
    exclude_clause, exclude_params = _exclude_file_ids_sql(db, exclude_ids)
    limit_clause = " LIMIT ?" if limit else ""
    params = [cat_id]
    params.extend(exclude_params)
    if limit:
        params.append(limit)
    rows = db.execute(f"""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken, pm.phash
        FROM files f
        JOIN photo_metadata pm ON f.id = pm.file_id
        LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
        WHERE pm.is_starred = 1 AND f.is_image = 1 AND {_category_match_sql(cat_id)}
              {_PATH_STATUS_FILTER}
              AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
              {exclude_clause}
        ORDER BY pm.date_taken DESC
        {limit_clause}
    """, params).fetchall()
    import os as _os
    valid = []
    for r in rows:
        d = _make_photo_dict(r)
        if d.get("thumbnail_path") and _os.path.exists(d["thumbnail_path"]):
            valid.append(d)
    return _interleave_small_folders(valid)


def count_category_photos(db, cat_id, starred_only=False):
    if starred_only:
        row = db.execute(f"""
            SELECT COUNT(*)
            FROM files f
            JOIN photo_metadata pm ON f.id = pm.file_id
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE pm.is_starred = 1 AND f.is_image = 1 AND {_category_match_sql(cat_id)}
                  {_PATH_STATUS_FILTER}
                  AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
        """, (cat_id,)).fetchone()
        return row[0] if row else 0

    row = db.execute(f"""
        SELECT COUNT(*)
        FROM files f
        LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE {_category_match_sql(cat_id)} AND f.is_image IN (0, 1)
              {_PATH_STATUS_FILTER}
              AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
    """, (cat_id,)).fetchone()
    total = row[0] if row else 0
    if total == 0:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            row = db.execute(f"""
                SELECT COUNT(*)
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image IN (0, 1)
                      AND {_category_match_without_folder_sql(cat_id)}
                      {_PATH_STATUS_FILTER}
                      AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')
                      AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
            """).fetchone()
            total = row[0] if row else 0
    return total


def rank_category_photos(
    db,
    cat_id,
    return_metrics=False,
    limit=None,
    exclude_ids=None,
    exclude_visual_keys=None,
    prior_photos=None,
):
    started = time.perf_counter()
    excluded_ids = set(exclude_ids or [])
    considered_ids = set(excluded_ids)
    seen_visual_keys = set(exclude_visual_keys or [])
    prior_context = list(prior_photos or [])
    target_limit = max(int(limit), 1) if limit is not None else None
    memory_started = time.perf_counter()
    memory_limit = None if target_limit is None else min(target_limit, FOREGROUND_MEMORY_PRIORITY_LIMIT)
    memory_row_limit = None if target_limit is None else FOREGROUND_MEMORY_ROW_SCAN_LIMIT
    memory_photos = _load_ranked_memory_photos(
        db,
        cat_id,
        limit=memory_limit,
        exclude_ids=excluded_ids,
        max_memory_rows=memory_row_limit,
    )
    memory_ms = (time.perf_counter() - memory_started) * 1000

    batch_started = time.perf_counter()
    candidate_limit = _random_candidate_limit(target_limit)
    sql_exclude_recent_days = None if target_limit is not None else FRESHNESS_WINDOW_DAYS
    batch_photos = load_category_photos_batch(
        db,
        cat_id,
        0,
        limit=candidate_limit,
        exclude_recent_days=sql_exclude_recent_days,
        random_order=True,
        exclude_ids=excluded_ids,
        require_thumbnail=True,
    )
    excluded_recent = sql_exclude_recent_days is not None
    min_fresh_needed = min(MIN_FRESH_RANDOM_CANDIDATES, target_limit) if target_limit else MIN_FRESH_RANDOM_CANDIDATES
    target_batch_needed = max(min_fresh_needed, target_limit - len(memory_photos)) if target_limit else min_fresh_needed
    if sql_exclude_recent_days is not None and len(batch_photos) < target_batch_needed:
        fallback_photos = load_category_photos_batch(
            db,
            cat_id,
            0,
            limit=candidate_limit,
            random_order=True,
            exclude_ids=excluded_ids,
            require_thumbnail=True,
        )
        seen_fallback_ids = {p["id"] for p in batch_photos}
        batch_photos.extend(p for p in fallback_photos if p["id"] not in seen_fallback_ids)
        excluded_recent = False
    batch_ms = (time.perf_counter() - batch_started) * 1000

    merge_started = time.perf_counter()
    ordered = []
    for p in list(memory_photos) + list(batch_photos):
        photo_id = p.get("id")
        if photo_id in considered_ids:
            continue
        considered_ids.add(photo_id)
        visual_key = photo_visual_key(p)
        if visual_key is not None and visual_key in seen_visual_keys:
            continue
        if visual_key is not None:
            seen_visual_keys.add(visual_key)
        ordered.append(p)

    if not ordered:
        if return_metrics:
            return [], {
                "memory_ms": memory_ms,
                "batch_ms": batch_ms,
                "merge_ms": (time.perf_counter() - merge_started) * 1000,
                "total_ms": (time.perf_counter() - started) * 1000,
                "candidate_limit": candidate_limit,
                "partial": target_limit is not None,
                "result_limit": target_limit,
            }
        return []

    recently_shown = _get_recently_shown_ids(db, cat_id, file_ids=[p["id"] for p in ordered])

    fresh = [p for p in ordered if p["id"] not in recently_shown]
    stale = [p for p in ordered if p["id"] in recently_shown]

    random.shuffle(fresh)
    random.shuffle(stale)

    fresh = _diversify_random_photos(fresh, prior_context)
    stale = _diversify_random_photos(
        stale,
        prior_context + fresh[-DIVERSITY_DAY_HISTORY:],
    )
    result = fresh + stale
    supplement_attempts = 0
    while target_limit is not None and len(result) < target_limit and supplement_attempts < 3:
        supplement_attempts += 1
        supplement_candidates = load_category_photos_batch(
            db,
            cat_id,
            0,
            limit=_random_candidate_limit(target_limit - len(result)),
            random_order=True,
            exclude_ids=set(considered_ids),
            require_thumbnail=True,
        )
        supplement = []
        candidate_visual_keys = set(seen_visual_keys)
        for photo in supplement_candidates:
            photo_id = photo.get("id")
            if photo_id in considered_ids:
                continue
            considered_ids.add(photo_id)
            visual_key = photo_visual_key(photo)
            if visual_key is not None and visual_key in candidate_visual_keys:
                continue
            if visual_key is not None:
                candidate_visual_keys.add(visual_key)
            supplement.append(photo)
        if not supplement:
            if not supplement_candidates:
                break
            continue
        supplement = _diversify_random_photos(
            supplement,
            prior_context + result[-DIVERSITY_DAY_HISTORY:],
        )
        selected = supplement[:target_limit - len(result)]
        result.extend(selected)
        seen_visual_keys.update(
            key for key in (photo_visual_key(photo) for photo in selected) if key is not None
        )
    if target_limit is not None:
        result = result[:target_limit]
    if return_metrics:
        return result, {
            "memory_ms": memory_ms,
            "batch_ms": batch_ms,
            "merge_ms": (time.perf_counter() - merge_started) * 1000,
            "total_ms": (time.perf_counter() - started) * 1000,
            "excluded_recent": excluded_recent,
            "candidate_count": len(batch_photos),
            "candidate_limit": candidate_limit,
            "partial": target_limit is not None,
            "result_limit": target_limit,
            "expanded_folder_count": 0,
            "expanded_day_count": 0,
        }
    return result

def rank_search_photos(db, matched_ids):
    photos = load_photos_from_ids(db, matched_ids)
    random.shuffle(photos)
    return _interleave_small_folders(photos)


def reshuffle_photos(photos, shown_ids=None):
    """对照片列表重新洗牌，按 fresh + stale 合并排序返回"""
    if not photos:
        return []

    if shown_ids is None:
        shown_ids = set()

    fresh = [p for p in photos if p["id"] not in shown_ids]
    stale = [p for p in photos if p["id"] in shown_ids]

    random.shuffle(fresh)
    random.shuffle(stale)

    combined = fresh + stale
    return _spread_nearby_photos(_interleave_by_time(_interleave_small_folders(combined)))
