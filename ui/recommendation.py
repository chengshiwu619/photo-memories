import os
import random

from db_manager import Database

CATEGORY_COLORS = {
    1: "#27ae60", 2: "#2980b9",
}

PAGE_SIZE = 30
MAX_SAME_FOLDER_STREAK = 12
SMALL_FOLDER_THRESHOLD = 100
FRESHNESS_WINDOW_DAYS = 7
MAX_SAME_DAY_STREAK = 12
MIN_MEMORY_VISIBLE_REFS = 4


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

    capped = {}
    for day, ps in day_groups.items():
        capped[day] = ps[:MAX_SAME_DAY_STREAK]

    result = []
    streak_day = None
    streak_count = 0
    pending = {day: list(ps) for day, ps in capped.items()}

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
    }


def _has_renderable_thumbnail(photo):
    thumb = photo.get("thumbnail_path", "")
    return bool(thumb and thumb != "__FAILED__" and os.path.exists(thumb))


def _filter_renderable_photos(photos):
    return [p for p in photos if _has_renderable_thumbnail(p)]


def _get_recently_shown_ids(db, cat_id, days=FRESHNESS_WINDOW_DAYS):
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


def load_photos_from_ids(db, all_ids, require_thumbnail=False):
    if not all_ids:
        return []
    seen = set()
    unique_ids = []
    for pid in all_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    placeholders = ",".join("?" * len(unique_ids))
    rows = db.execute(
        f"""SELECT f.id, f.file_path, f.file_name, f.folder_path,
                   f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                   pm.width, pm.height, pm.date_taken
            FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.id IN ({placeholders})
                  AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')""",
        unique_ids,
    ).fetchall()
    by_id = {}
    for r in rows:
        d = _make_photo_dict(r)
        if require_thumbnail:
            if _has_renderable_thumbnail(d):
                by_id[d["id"]] = d
        elif not d.get("thumbnail_path") or os.path.exists(d["thumbnail_path"]):
            by_id[d["id"]] = d
    valid = [by_id[pid] for pid in unique_ids if pid in by_id]
    return _interleave_small_folders(valid)


def _filter_photos_for_category(db, cat_id, photos):
    if not photos:
        return []
    photo_ids = [p["id"] for p in photos]
    placeholders = ",".join("?" * len(photo_ids))
    valid_ids = {
        r[0] for r in db.execute(
            f"""SELECT f.id
                FROM files f
                JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE fc.category = ? AND f.id IN ({placeholders})""",
            [cat_id] + photo_ids,
        ).fetchall()
    }
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

    base_select = """
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE fc.category = ?
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


def _load_ranked_memory_photos(db, cat_id):
    ranked = []
    seen_ids = set()
    rows = db.execute(
        "SELECT id, photo_ids FROM memories WHERE category = ? ORDER BY created_at DESC",
        (cat_id,),
    ).fetchall()

    for row in rows:
        try:
            import json
            photo_ids = json.loads(row["photo_ids"])
        except Exception:
            continue

        photos = load_photos_from_ids(db, photo_ids, require_thumbnail=True)
        photos = _filter_photos_for_category(db, cat_id, photos)
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

        for p in photos:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                ranked.append(p)

    return ranked


def load_category_photos_batch(db, cat_id, offset, limit=PAGE_SIZE):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE COALESCE(fc.category, 1) = ? AND f.is_image IN (0, 1)
              AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
        ORDER BY pm.date_taken DESC
        LIMIT ? OFFSET ?
    """, (cat_id, limit, offset)).fetchall()
    if not rows and offset == 0:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            rows = db.execute("""
                SELECT f.id, f.file_path, f.file_name, f.folder_path,
                       f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                       pm.width, pm.height, pm.date_taken
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image IN (0, 1)
                      AND (pm.thumbnail_path IS NULL OR pm.thumbnail_path != '__FAILED__')
                      AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                ORDER BY pm.date_taken DESC
                LIMIT ?
            """, (limit,)).fetchall()
    valid = []
    for r in rows:
        d = _make_photo_dict(r)
        if not d.get("thumbnail_path") or os.path.exists(d["thumbnail_path"]):
            valid.append(d)
    return _interleave_small_folders(valid)


def load_starred_photos(db, cat_id):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        JOIN photo_metadata pm ON f.id = pm.file_id
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        WHERE pm.is_starred = 1 AND f.is_image = 1 AND fc.category = ? AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
        ORDER BY pm.date_taken DESC
    """, (cat_id,)).fetchall()
    import os as _os
    valid = []
    for r in rows:
        d = _make_photo_dict(r)
        if d.get("thumbnail_path") and _os.path.exists(d["thumbnail_path"]):
            valid.append(d)
    return _interleave_small_folders(valid)


def rank_category_photos(db, cat_id):
    memory_photos = _load_ranked_memory_photos(db, cat_id)

    batch_photos = _filter_renderable_photos(load_category_photos_batch(db, cat_id, 0, limit=9999))

    seen_file_ids = set()
    ordered = []
    for p in memory_photos:
        if p["id"] not in seen_file_ids:
            seen_file_ids.add(p["id"])
            ordered.append(p)
    for p in batch_photos:
        if p["id"] not in seen_file_ids:
            seen_file_ids.add(p["id"])
            ordered.append(p)

    if not ordered:
        return []

    recently_shown = _get_recently_shown_ids(db, cat_id)

    fresh = [p for p in ordered if p["id"] not in recently_shown]
    stale = [p for p in ordered if p["id"] in recently_shown]

    random.shuffle(fresh)
    random.shuffle(stale)

    result = []
    result.extend(fresh)
    result.extend(stale)
    return _interleave_by_time(_interleave_small_folders(result))


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
    return _interleave_by_time(_interleave_small_folders(combined))
