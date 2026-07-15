from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from db_manager import Database
from business.classifier.category_rules import (
    category_match_sql,
    protected_life_override_sql,
    strong_life_source_sql,
    strong_sample_filename_sql,
)


DISMISSED_TAG = "nsfw-review:dismissed"
DISMISSED_SOURCE = "manual"
VISUAL_REVIEW_TAGS = {
    "nsfw",
    "nude",
    "explicit",
    "lingerie",
    "gravure",
    "model portrait",
    "photobook",
}
VISUAL_REASON_WEIGHT = 20
FILENAME_REASON_WEIGHT = 10


@dataclass(frozen=True)
class NsfwReviewCandidate:
    file_id: int
    file_path: str
    file_name: str
    folder_path: str
    thumbnail_path: str
    width: int | None
    height: int | None
    date_taken: str | None
    reasons: List[str]
    score: int

    def as_dict(self) -> dict:
        return {
            "id": self.file_id,
            "file_id": self.file_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "folder_path": self.folder_path,
            "thumbnail_path": self.thumbnail_path,
            "width": self.width,
            "height": self.height,
            "date_taken": self.date_taken,
            "reasons": list(self.reasons),
            "reason_text": " / ".join(self.reasons),
            "score": self.score,
        }


def nsfw_visual_candidates() -> List[str]:
    return sorted(VISUAL_REVIEW_TAGS)


def _normalize_tag(tag: str | None) -> str:
    return (tag or "").strip().lower()


def _reason_score(reasons: Iterable[str]) -> int:
    score = 0
    for reason in reasons:
        if reason.startswith("visual:"):
            score += VISUAL_REASON_WEIGHT
        elif reason.startswith("filename:"):
            score += FILENAME_REASON_WEIGHT
    return score


def _dismissed_filter_sql(file_alias="f") -> str:
    return (
        "NOT EXISTS ("
        "SELECT 1 FROM photo_tags dismissed "
        f"WHERE dismissed.file_id = {file_alias}.id "
        f"AND dismissed.tag = '{DISMISSED_TAG}' "
        f"AND dismissed.source = '{DISMISSED_SOURCE}'"
        ")"
    )


def load_review_candidates(limit=120, offset=0, db=None) -> list[dict]:
    db = db or Database()
    limit = max(1, int(limit))
    offset = max(0, int(offset))
    life_sql = category_match_sql(CATEGORY_LIFE)
    strong_life_source = strong_life_source_sql("f.folder_path")
    filename_sql = strong_sample_filename_sql("f.file_name")
    protected_life_override = protected_life_override_sql("f.folder_path", "f.file_name")
    visual_placeholders = ",".join("?" for _ in VISUAL_REVIEW_TAGS)
    params = [CATEGORY_LIFE, *sorted(VISUAL_REVIEW_TAGS), limit, offset]
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                f.id AS file_id,
                f.file_path,
                f.file_name,
                f.folder_path,
                pm.thumbnail_path,
                pm.width,
                pm.height,
                pm.date_taken,
                CASE WHEN {filename_sql} THEN 1 ELSE 0 END AS filename_match,
                GROUP_CONCAT(DISTINCT lower(pt.tag)) AS visual_tags
            FROM files f
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            LEFT JOIN photo_tags pt
                ON pt.file_id = f.id
               AND pt.source = 'siglip'
               AND lower(pt.tag) IN ({visual_placeholders})
            WHERE ({life_sql} OR ({strong_life_source} AND {filename_sql}))
              AND f.is_image = 1
              AND (pm.category IS NULL OR pm.category != {CATEGORY_SAMPLE})
              AND NOT {protected_life_override}
              AND pm.thumbnail_path IS NOT NULL
              AND pm.thumbnail_path != ''
              AND pm.thumbnail_path != '__FAILED__'
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
              AND (f.path_status IS NULL OR f.path_status NOT IN
                  ('damaged_path', 'missing', 'stat_failed', 'outside_root'))
              AND {_dismissed_filter_sql("f")}
              AND ({filename_sql} OR pt.file_id IS NOT NULL)
            GROUP BY f.id
        ORDER BY pm.date_taken DESC, f.file_mtime DESC, filename_match DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

    candidates: list[dict] = []
    for row in rows:
        reasons = []
        if row["filename_match"]:
            reasons.append("filename:sample-pattern")
        visual_tags = [
            tag for tag in (_normalize_tag(t) for t in (row["visual_tags"] or "").split(","))
            if tag
        ]
        for tag in visual_tags:
            reasons.append(f"visual:{tag}")
        candidate = NsfwReviewCandidate(
            file_id=int(row["file_id"]),
            file_path=row["file_path"] or "",
            file_name=row["file_name"] or "",
            folder_path=row["folder_path"] or "",
            thumbnail_path=row["thumbnail_path"] or "",
            width=row["width"],
            height=row["height"],
            date_taken=row["date_taken"],
            reasons=reasons,
            score=_reason_score(reasons),
        )
        candidates.append(candidate.as_dict())
    return candidates


def dismiss_review_candidate(file_id: int, db=None) -> bool:
    try:
        fid = int(file_id)
    except (TypeError, ValueError):
        return False
    if fid <= 0:
        return False

    db = db or Database()
    with db.connect() as conn:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            (fid, DISMISSED_TAG, DISMISSED_SOURCE),
        )
        return conn.total_changes > before


def dismiss_review_candidates(file_ids: Iterable[int], db=None) -> dict:
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
        return {"requested": 0, "inserted": 0}

    db = db or Database()
    with db.connect() as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
            [(fid, DISMISSED_TAG, DISMISSED_SOURCE) for fid in ids],
        )
        return {"requested": len(ids), "inserted": conn.total_changes - before}


def mark_review_candidate_as_sample(file_id: int, db=None) -> bool:
    try:
        fid = int(file_id)
    except (TypeError, ValueError):
        return False
    if fid <= 0:
        return False

    db = db or Database()
    with db.connect() as conn:
        protected_life_override = protected_life_override_sql("f.folder_path", "f.file_name")
        row = conn.execute(
            f"SELECT 1 FROM files f WHERE f.id = ? AND NOT {protected_life_override}",
            (fid,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            INSERT INTO photo_metadata (file_id, category, indexed_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(file_id) DO UPDATE SET
                category = excluded.category,
                indexed_at = datetime('now')
            """,
            (fid, CATEGORY_SAMPLE),
        )
        return True


def mark_review_candidates_as_sample(file_ids: Iterable[int], db=None) -> dict:
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
        return {"requested": 0, "updated": 0, "missing": 0}

    db = db or Database()
    updated = 0
    missing = 0
    with db.connect() as conn:
        conn.execute("BEGIN")
        try:
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                protected_life_override = protected_life_override_sql("f.folder_path", "f.file_name")
                rows = conn.execute(
                    f"SELECT f.id FROM files f WHERE f.id IN ({placeholders}) AND NOT {protected_life_override}",
                    batch,
                ).fetchall()
                found_ids = [int(row["id"]) for row in rows]
                missing += len(batch) - len(found_ids)
                if not found_ids:
                    continue
                conn.executemany(
                    """
                    INSERT INTO photo_metadata (file_id, category, indexed_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(file_id) DO UPDATE SET
                        category = excluded.category,
                        indexed_at = datetime('now')
                    """,
                    [(fid, CATEGORY_SAMPLE) for fid in found_ids],
                )
                updated += len(found_ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {"requested": len(ids), "updated": updated, "missing": missing}
