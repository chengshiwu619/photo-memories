import os
import random
from config import DB_PATH

CATEGORY_COLORS = {
    1: "#27ae60", 2: "#2980b9", 3: "#8e44ad", 4: "#c0392b",
}

PAGE_SIZE = 30


def _make_photo_dict(r):
    return {
        "id": r["id"], "file_path": r["file_path"], "file_name": r["file_name"],
        "folder_path": r["folder_path"],
        "folder_name": r["folder_display"] if "folder_display" in r.keys() else os.path.basename(r["folder_path"]),
        "thumbnail_path": r["thumbnail_path"],
    }


def load_photos_from_ids(db, all_ids):
    if not all_ids:
        return []
    placeholders = ",".join("?" * len(all_ids))
    rows = db.execute(
        f"""SELECT f.id, f.file_path, f.file_name, f.folder_path,
                   f.folder_name as folder_display, pm.thumbnail_path
            FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.id IN ({placeholders})""",
        all_ids,
    ).fetchall()
    return [_make_photo_dict(r) for r in rows]


def load_category_photos_batch(db, cat_id, offset, limit=PAGE_SIZE):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, pm.thumbnail_path
        FROM files f
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE fc.category = ? AND f.is_image = 1 AND pm.thumbnail_path IS NOT NULL
        ORDER BY pm.date_taken DESC
        LIMIT ? OFFSET ?
    """, (cat_id, limit, offset)).fetchall()
    if not rows and offset == 0:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            rows = db.execute("""
                SELECT f.id, f.file_path, f.file_name, f.folder_path,
                       f.folder_name as folder_display, pm.thumbnail_path
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.thumbnail_path IS NOT NULL
                ORDER BY pm.date_taken DESC
                LIMIT ?
            """, (limit,)).fetchall()
    return [_make_photo_dict(r) for r in rows]


def load_starred_photos(db, cat_id):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, pm.thumbnail_path
        FROM files f
        JOIN photo_metadata pm ON f.id = pm.file_id
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        WHERE pm.is_starred = 1 AND f.is_image = 1 AND fc.category = ? AND pm.thumbnail_path IS NOT NULL
        ORDER BY pm.date_taken DESC
    """, (cat_id,)).fetchall()
    return [_make_photo_dict(r) for r in rows]


def rank_category_photos(db, cat_id):
    all_ids = []
    for row in db.execute(
        "SELECT photo_ids FROM memories WHERE category = ? ORDER BY created_at DESC",
        (cat_id,),
    ).fetchall():
        try:
            import json
            all_ids.extend(json.loads(row["photo_ids"]))
        except Exception:
            pass

    if all_ids:
        photos = load_photos_from_ids(db, all_ids)
        photos = [p for p in photos if p.get("thumbnail_path")]
        if photos:
            starred_ids = set()
            for row in db.execute("SELECT file_id FROM photo_metadata WHERE is_starred = 1").fetchall():
                starred_ids.add(row["file_id"])

            starred_photos = [p for p in photos if p["id"] in starred_ids]
            normal_photos = [p for p in photos if p["id"] not in starred_ids]

            random.shuffle(normal_photos)

            max_starred = min(len(starred_photos), 3)
            selected_starred = starred_photos[:max_starred] if starred_photos else []

            clicked = {}
            for row in db.execute(
                "SELECT folder_path, COUNT(*) as cnt FROM click_history WHERE category = ? GROUP BY folder_path",
                (cat_id,),
            ).fetchall():
                clicked[row["folder_path"]] = row["cnt"]

            weights = {}
            for p in normal_photos:
                w = min(clicked.get(os.path.dirname(p["file_path"]), 0) * 0.05, 0.35)
                weights[p["id"]] = w

            if weights:
                normal_photos.sort(key=lambda p: weights.get(p["id"], 0), reverse=True)

            result = []
            result.extend(selected_starred)
            result.extend(normal_photos)
            return result

    return load_category_photos_batch(db, cat_id, 0)


def rank_search_photos(db, matched_ids):
    photos = load_photos_from_ids(db, matched_ids)
    random.shuffle(photos)
    return photos
