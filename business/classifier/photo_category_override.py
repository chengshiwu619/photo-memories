from __future__ import annotations

from datetime import datetime

from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from db_manager import Database
from logger_setup import logger
from business.classifier.category_rules import CONFIRMED_SAMPLE_SOURCE, CONFIRMED_SAMPLE_TAG


def batch_set_photo_category(file_ids, category=CATEGORY_SAMPLE, batch_size=1000, user="user", db=None):
    ids = []
    seen = set()
    for file_id in file_ids or []:
        try:
            fid = int(file_id)
        except (TypeError, ValueError):
            continue
        if fid > 0 and fid not in seen:
            seen.add(fid)
            ids.append(fid)

    if not ids:
        return {"requested": 0, "updated": 0, "missing": 0, "category": category}

    updated = 0
    missing = 0
    old_categories = {}
    chunk_size = max(1, int(batch_size))
    db = db or Database()
    with db.connect() as conn:
        try:
            conn.execute("BEGIN")
            for start in range(0, len(ids), chunk_size):
                batch = ids[start:start + chunk_size]
                placeholders = ",".join("?" * len(batch))
                rows = conn.execute(
                    f"""
                    SELECT f.id, pm.category
                    FROM files f
                    LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                    WHERE f.id IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                found = {int(row["id"]): row["category"] for row in rows}
                for fid, old_cat in found.items():
                    old_categories[fid] = old_cat
                missing += len(batch) - len(found)
                if not found:
                    continue
                conn.executemany(
                    """
                    INSERT INTO photo_metadata (file_id, category, indexed_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(file_id) DO UPDATE SET
                        category = excluded.category,
                        indexed_at = datetime('now')
                    """,
                    [(fid, category) for fid in found],
                )
                if category == CATEGORY_SAMPLE:
                    conn.executemany(
                        "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                        [
                            (fid, CONFIRMED_SAMPLE_TAG, CONFIRMED_SAMPLE_SOURCE)
                            for fid in found
                        ],
                    )
                elif category == CATEGORY_LIFE:
                    conn.executemany(
                        "DELETE FROM photo_tags WHERE file_id = ? AND tag = ? AND source = ?",
                        [
                            (fid, CONFIRMED_SAMPLE_TAG, CONFIRMED_SAMPLE_SOURCE)
                            for fid in found
                        ],
                    )
                updated += len(found)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    logger.info(
        "batch update: %s files set to 样片 by %s %s",
        updated,
        user,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return {
        "requested": len(ids),
        "updated": updated,
        "missing": missing,
        "category": category,
        "old_categories": old_categories,
    }
