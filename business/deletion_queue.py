from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable

from db_manager import Database


PENDING_DELETE_TAG = "system:pending-delete"
PENDING_DELETE_SOURCE = "deletion-queue"
DELETE_ORIGINALS_CONFIRMATION = "DELETE_ORIGINALS"


def _normalize_ids(values: Iterable[object] | None, limit=100000) -> list[int]:
    result = []
    seen = set()
    for value in values or []:
        try:
            file_id = int(value)
        except (TypeError, ValueError):
            continue
        if file_id <= 0 or file_id in seen:
            continue
        seen.add(file_id)
        result.append(file_id)
        if len(result) >= limit:
            break
    return result


def pending_delete_exists_sql(file_alias="f") -> str:
    return (
        "EXISTS (SELECT 1 FROM photo_tags pending_delete "
        f"WHERE pending_delete.file_id = {file_alias}.id "
        f"AND pending_delete.tag = '{PENDING_DELETE_TAG}' "
        f"AND pending_delete.source = '{PENDING_DELETE_SOURCE}')"
    )


def pending_delete_filter_sql(file_alias="f") -> str:
    return f"AND NOT {pending_delete_exists_sql(file_alias)}"


def queue_for_deletion(file_ids: Iterable[object], db=None) -> dict:
    ids = _normalize_ids(file_ids)
    if not ids:
        return {"requested": 0, "queued": 0}
    db = db or Database()
    queued = 0
    with db.connect() as conn:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            before = conn.total_changes
            conn.execute(
                f"""
                INSERT OR IGNORE INTO photo_tags (file_id, tag, source)
                SELECT id, ?, ? FROM files WHERE id IN ({placeholders})
                """,
                [PENDING_DELETE_TAG, PENDING_DELETE_SOURCE, *batch],
            )
            queued += conn.total_changes - before
    return {"requested": len(ids), "queued": queued}


def restore_from_deletion(file_ids: Iterable[object], db=None) -> dict:
    ids = _normalize_ids(file_ids)
    if not ids:
        return {"requested": 0, "restored": 0}
    db = db or Database()
    restored = 0
    with db.connect() as conn:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            before = conn.total_changes
            conn.execute(
                f"""
                DELETE FROM photo_tags
                WHERE file_id IN ({placeholders}) AND tag = ? AND source = ?
                """,
                [*batch, PENDING_DELETE_TAG, PENDING_DELETE_SOURCE],
            )
            restored += conn.total_changes - before
    return {"requested": len(ids), "restored": restored}


def pending_deletion_count(db=None) -> int:
    db = db or Database()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM photo_tags WHERE tag = ? AND source = ?",
            (PENDING_DELETE_TAG, PENDING_DELETE_SOURCE),
        ).fetchone()
    return int(row[0]) if row else 0


def pending_deletion_ids(limit=100000, db=None) -> list[int]:
    db = db or Database()
    limit = min(max(int(limit), 1), 100000)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT file_id FROM photo_tags
            WHERE tag = ? AND source = ?
            ORDER BY created_at DESC, file_id DESC
            LIMIT ?
            """,
            (PENDING_DELETE_TAG, PENDING_DELETE_SOURCE, limit),
        ).fetchall()
    return [int(row["file_id"]) for row in rows]


def load_pending_deletions(limit=240, offset=0, db=None) -> list[dict]:
    db = db or Database()
    limit = min(max(int(limit), 1), 600)
    offset = max(int(offset), 0)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.file_path, f.file_name, f.folder_path, f.file_mtime,
                   pm.thumbnail_path, pm.width, pm.height, pm.date_taken, pm.is_starred
            FROM photo_tags pending_delete
            JOIN files f ON f.id = pending_delete.file_id
            LEFT JOIN photo_metadata pm ON pm.file_id = f.id
            WHERE pending_delete.tag = ? AND pending_delete.source = ?
              AND pm.thumbnail_path IS NOT NULL
              AND pm.thumbnail_path != ''
              AND pm.thumbnail_path != '__FAILED__'
            ORDER BY pending_delete.created_at DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            (PENDING_DELETE_TAG, PENDING_DELETE_SOURCE, limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def _is_within_registered_folder(file_path: str, source_dir: str, folder_path: str) -> bool:
    registered_root = source_dir or folder_path
    if not file_path or not registered_root:
        return False
    try:
        path = os.path.normcase(os.path.abspath(file_path))
        root = os.path.normcase(os.path.abspath(registered_root))
        return os.path.commonpath([path, root]) == root
    except (OSError, ValueError):
        return False


def delete_pending_originals(
    file_ids: Iterable[object],
    confirmation: str,
    db=None,
) -> dict:
    if confirmation != DELETE_ORIGINALS_CONFIRMATION:
        raise ValueError("explicit deletion confirmation required")
    ids = _normalize_ids(file_ids, limit=5000)
    if not ids:
        return {"requested": 0, "deleted": 0, "deletedIds": [], "failed": 0, "errors": []}
    db = db or Database()
    rows = []
    with db.connect() as conn:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows.extend(conn.execute(
                f"""
                SELECT f.id, f.file_path, f.folder_path, f.source_dir
                FROM files f
                WHERE f.id IN ({placeholders})
                  AND {pending_delete_exists_sql('f')}
                """,
                batch,
            ).fetchall())

    deleted_ids = []
    errors = []
    for row in rows:
        file_id = int(row["id"])
        file_path = row["file_path"] or ""
        if not _is_within_registered_folder(
            file_path,
            row["source_dir"] or "",
            row["folder_path"] or "",
        ):
            errors.append({"id": file_id, "error": "path is outside its registered source"})
            continue
        path = Path(file_path)
        try:
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                errors.append({"id": file_id, "error": "registered path is not a file"})
                continue
            path.unlink()
            deleted_ids.append(file_id)
        except FileNotFoundError:
            deleted_ids.append(file_id)
        except OSError as exc:
            errors.append({"id": file_id, "error": str(exc)})

    if deleted_ids:
        with db.connect() as conn:
            for start in range(0, len(deleted_ids), 500):
                batch = deleted_ids[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                conn.execute(
                    f"""
                    UPDATE files SET path_status = 'missing', path_error = 'deleted_by_user'
                    WHERE id IN ({placeholders})
                    """,
                    batch,
                )
                conn.execute(
                    f"""
                    DELETE FROM photo_tags
                    WHERE file_id IN ({placeholders}) AND tag = ? AND source = ?
                    """,
                    [*batch, PENDING_DELETE_TAG, PENDING_DELETE_SOURCE],
                )
    return {
        "requested": len(ids),
        "deleted": len(deleted_ids),
        "deletedIds": deleted_ids,
        "failed": len(errors) + (len(ids) - len(rows)),
        "errors": errors[:50],
    }
