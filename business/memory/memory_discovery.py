import json
from datetime import datetime, timedelta
from typing import List, Optional

from logger_setup import logger
from db_manager import Database
from core.models import Memory
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.face_clusters_repo import FaceClustersRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository
from infra.db.repositories.events_repo import EventsRepository
from config import MEMORY_HIGH_FREQ_DAYS


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


def discover_recent_memories(days: int = MEMORY_HIGH_FREQ_DAYS) -> List[Memory]:
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


def discover_person_memories() -> List[Memory]:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    embeddings_repo = FaceEmbeddingsRepository(db)
    memories_repo = MemoriesRepository(db)

    clusters = clusters_repo.get_all()
    if not clusters:
        return []

    memories = []
    for cluster in clusters:
        if cluster.user_corrected and not cluster.person_name:
            continue

        member_ids = embeddings_repo.get_file_ids_by_cluster(cluster.cluster_id)
        if len(member_ids) < 3:
            continue

        photo_ids = member_ids[:20]
        name = cluster.person_name or f"人物{cluster.cluster_id}"
        title = f"与{name}的回忆"

        existing = _find_existing_memory(memories_repo, "person", str(cluster.cluster_id))
        if existing:
            continue

        m = Memory(
            category=1,
            memory_type="person",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"cluster_id": cluster.cluster_id, "person_name": name}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"人物回忆发现 {len(memories)} 组")
    return memories


def discover_event_memories() -> List[Memory]:
    db = Database()
    events_repo = EventsRepository(db)
    memories_repo = MemoriesRepository(db)

    events = events_repo.get_all()
    if not events:
        return []

    memories = []
    for event in events:
        try:
            photo_ids = json.loads(event.photo_ids) if event.photo_ids else []
        except Exception:
            continue

        if len(photo_ids) < 3:
            continue

        photo_ids = photo_ids[:20]
        event_type_label = "旅行" if event.event_type == "trip" else "事件"
        title = f"{event_type_label} · {event.start_date[:10]}"

        existing = _find_existing_memory(memories_repo, "event", str(event.event_id))
        if existing:
            continue

        m = Memory(
            category=1,
            memory_type="event",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"event_id": event.event_id, "event_type": event.event_type}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"事件回忆发现 {len(memories)} 组")
    return memories


def discover_scene_memories() -> List[Memory]:
    from business.image_recognition.scene_cluster import cluster_by_scene
    from infra.db.repositories.files_repo import FilesRepository

    db = Database()
    files_repo = FilesRepository(db)
    memories_repo = MemoriesRepository(db)

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM files WHERE is_image = 1 LIMIT 2000"
        ).fetchall()
    file_ids = [r[0] for r in rows]

    if not file_ids:
        return []

    scene_clusters = cluster_by_scene(file_ids)
    if not scene_clusters:
        return []

    memories = []
    for cluster_idx, cluster_file_ids in scene_clusters.items():
        if len(cluster_file_ids) < 5:
            continue

        photo_ids = cluster_file_ids[:20]
        title = f"场景回忆 · 组{cluster_idx + 1}"

        existing = _find_existing_memory(memories_repo, "scene", str(cluster_idx))
        if existing:
            continue

        m = Memory(
            category=1,
            memory_type="scene",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"scene_cluster_idx": cluster_idx}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"场景回忆发现 {len(memories)} 组")
    return memories


def get_on_this_day_memories() -> List[Memory]:
    db = Database()
    memories_repo = MemoriesRepository(db)
    return memories_repo.get_undismissed_by_type("on_this_day")


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
        except Exception:
            continue
    return None
