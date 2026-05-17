import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

from logger_setup import logger
from db_manager import Database
from core.models import Memory
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from config import get_settings


def discover_on_this_day(lookback_years: Optional[List[int]] = None) -> List[Memory]:
    if lookback_years is None:
        lookback_years = list(range(1, 11))

    today = datetime.now()
    target_dates = []
    for y in lookback_years:
        try:
            target = today.replace(year=today.year - y)
            target_dates.append(target.strftime("%m-%d"))
        except ValueError:
            continue

    if not target_dates:
        return []

    db = Database()
    pm_repo = PhotoMetadataRepository(db)
    memories_repo = MemoriesRepository(db)

    rows = pm_repo.get_photos_by_month_day(target_dates)

    if not rows:
        return []

    groups = {}
    for file_id, folder_path, date_taken, category in rows:
        month_day = date_taken[5:10]
        year = date_taken[:4]
        key = f"{year}-{month_day}"
        if key not in groups:
            groups[key] = {"ids": [], "category": category or 1, "date": date_taken}
        groups[key]["ids"].append(file_id)

    memories = []
    for key, group in groups.items():
        year_diff = today.year - int(key[:4])
        photo_ids = group["ids"][:20]
        title = f"{year_diff}年前的今天"
        description = f"{key[:4]}年{key[5:7]}月{key[8:10]}日"

        existing = _find_existing_memory(memories_repo, "on_this_day", key)
        if existing:
            continue

        m = Memory(
            category=group["category"],
            memory_type="on_this_day",
            title=title,
            description=description,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"date_key": key, "years_ago": year_diff}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"那年今日发现 {len(memories)} 组回忆")
    return memories


def discover_recent_memories(days: Optional[int] = None) -> List[Memory]:
    if days is None:
        days = get_settings().memory_high_freq_days
    since = (datetime.now() - timedelta(days=days)).isoformat()

    db = Database()
    pm_repo = PhotoMetadataRepository(db)
    memories_repo = MemoriesRepository(db)

    rows = pm_repo.get_recent_photos(since)

    if not rows:
        return []

    groups = {}
    for file_id, folder_path, date_taken, category in rows:
        day = date_taken[:10]
        if day not in groups:
            groups[day] = {"ids": [], "category": category or 1}
        groups[day]["ids"].append(file_id)

    memories = []
    for day, group in groups.items():
        photo_ids = group["ids"][:20]
        title = f"近期回忆 · {day}"
        existing = _find_existing_memory(memories_repo, "recent", day)
        if existing:
            continue

        m = Memory(
            category=group["category"],
            memory_type="recent",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"date": day}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"近期回忆发现 {len(memories)} 组")
    return memories


def get_on_this_day_memories() -> List[Memory]:
    db = Database()
    memories_repo = MemoriesRepository(db)
    return memories_repo.get_undismissed_by_type("on_this_day")


_SPECIAL_DATES = {
    "01-01": "元旦",
    "02-14": "情人节",
    "03-08": "妇女节",
    "05-01": "劳动节",
    "06-01": "儿童节",
    "10-01": "国庆节",
    "12-25": "圣诞节",
}


def discover_special_date_memories() -> List[Memory]:
    month_days = list(_SPECIAL_DATES.keys())
    db = Database()
    pm_repo = PhotoMetadataRepository(db)
    memories_repo = MemoriesRepository(db)

    rows = pm_repo.get_photos_by_month_day(month_days)

    if not rows:
        with db.connect() as conn:
            rows = conn.execute(f"""
                SELECT f.id, f.folder_path, pm.date_taken, fc.category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                  AND ({" OR ".join("substr(pm.date_taken, 6, 5) = ?" for _ in month_days)})
                ORDER BY pm.date_taken DESC
            """, month_days).fetchall()

    if not rows:
        return []

    groups = {}
    for row in rows:
        file_id = row[0]
        folder_path = row[1]
        date_taken = row[2]
        category = row[3]
        month_day = date_taken[5:10]
        year = date_taken[:4]
        key = f"{year}-{month_day}"
        if key not in groups:
            groups[key] = {"ids": [], "category": category or 1, "month_day": month_day}
        groups[key]["ids"].append(file_id)

    memories = []
    for key, group in groups.items():
        if len(group["ids"]) < 1:
            continue

        photo_ids = group["ids"][:20]
        label = _SPECIAL_DATES.get(group["month_day"], group["month_day"])
        title = f"{label} · {key[:4]}"

        existing = _find_existing_memory(memories_repo, "special_date", key)
        if existing:
            continue

        m = Memory(
            category=group["category"],
            memory_type="special_date",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"date_key": key}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"特殊日期回忆发现 {len(memories)} 组")
    return memories


def discover_folder_memories(top_n: int = 5) -> List[Memory]:
    db = Database()
    memories_repo = MemoriesRepository(db)

    with db.connect() as conn:
        rows = conn.execute("""
            SELECT f.folder_path, f.folder_name,
                   fc.category,
                   COUNT(*) as cnt,
                   MIN(pm.date_taken) as first_date
            FROM files f
            JOIN photo_metadata pm ON f.id = pm.file_id
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE f.is_image = 1
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
            GROUP BY f.folder_path
            HAVING cnt >= 3
            ORDER BY cnt DESC
            LIMIT ?
        """, (top_n,)).fetchall()

    if not rows:
        return []

    memories = []
    for folder_path, folder_name, category, cnt, first_date in rows:
        with db.connect() as conn:
            file_rows = conn.execute("""
                SELECT f.id FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.folder_path = ?
                  AND f.is_image = 1
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                ORDER BY pm.date_taken DESC
                LIMIT 20
            """, (folder_path,)).fetchall()
        photo_ids = [r[0] for r in file_rows]
        if not photo_ids:
            continue

        display_name = folder_name or os.path.basename(folder_path)
        date_label = first_date[:10] if first_date else ""
        title = f"{display_name} · {date_label}" if date_label else display_name

        existing = _find_existing_memory(memories_repo, "folder", folder_path)
        if existing:
            continue

        m = Memory(
            category=category or 1,
            memory_type="folder",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0],
            payload=json.dumps({"folder_path": folder_path}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"文件夹回忆发现 {len(memories)} 组")
    return memories


def _find_existing_memory(memories_repo: MemoriesRepository, memory_type: str, payload_key: str) -> Optional[int]:
    rows = memories_repo.find_by_type_and_payload_key(memory_type)

    for mid, payload_str in rows:
        if not payload_str:
            continue
        try:
            payload = json.loads(payload_str)
            if "date_key" in payload and payload["date_key"] == payload_key:
                return mid
            if "date" in payload and payload["date"] == payload_key:
                return mid
            if "cluster_id" in payload and str(payload["cluster_id"]) == payload_key:
                return mid
            if "event_id" in payload and str(payload["event_id"]) == payload_key:
                return mid
            if "scene_cluster_idx" in payload and str(payload["scene_cluster_idx"]) == payload_key:
                return mid
            if "folder_path" in payload and payload["folder_path"] == payload_key:
                return mid
        except Exception:
            continue
    return None
