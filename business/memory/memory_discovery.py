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
from config import CATEGORY_LIFE
from business.classifier.category_rules import category_match_sql


MAX_EVENT_SPAN_DAYS = 21
MAX_EVENT_GAP_DAYS = 2
MAX_MEMORY_PHOTOS = 20


def _filter_life_photos(file_ids: List[int]) -> List[int]:
    """只保留分类为生活照片(category=1)的文件ID"""
    if not file_ids:
        return []
    with Database().connect() as conn:
        rows = conn.execute("""
            SELECT f.id FROM files f
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE """ + category_match_sql(CATEGORY_LIFE) + """ AND f.id IN ({})
        """.format(",".join("?" * len(file_ids))), [CATEGORY_LIFE] + file_ids).fetchall()
    allowed = {r[0] for r in rows}
    return [fid for fid in file_ids if fid in allowed]


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
        # 只保留生活样片分类的照片
        if category != CATEGORY_LIFE:
            continue
        month_day = date_taken[5:10]
        year = date_taken[:4]
        key = f"{year}-{month_day}"
        if key not in groups:
            groups[key] = {"ids": [], "date": date_taken}
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
            category=CATEGORY_LIFE,
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
        if category != CATEGORY_LIFE:
            continue
        day = date_taken[:10]
        if day not in groups:
            groups[day] = {"ids": []}
        groups[day]["ids"].append(file_id)

    memories = []
    for day, group in groups.items():
        photo_ids = group["ids"][:20]
        title = f"近期回忆 · {day}"
        existing = _find_existing_memory(memories_repo, "recent", day)
        if existing:
            continue

        m = Memory(
            category=CATEGORY_LIFE,
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


def discover_special_date_memories(max_groups: Optional[int] = 2, min_photos: int = 3) -> List[Memory]:
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
                      AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
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
        if category != CATEGORY_LIFE:
            continue
        month_day = date_taken[5:10]
        year = date_taken[:4]
        key = f"{year}-{month_day}"
        if key not in groups:
            groups[key] = {"ids": [], "month_day": month_day}
        groups[key]["ids"].append(file_id)

    memories = []
    group_items = list(groups.items())
    if max_groups is not None:
        group_items = group_items[:max_groups]

    for key, group in group_items:
        if len(group["ids"]) < min_photos:
            continue

        photo_ids = group["ids"][:20]
        label = _SPECIAL_DATES.get(group["month_day"], group["month_day"])
        title = f"{label} · {key[:4]}"

        existing = _find_existing_memory(memories_repo, "special_date", key)
        if existing:
            continue

        m = Memory(
            category=CATEGORY_LIFE,
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
                   COUNT(*) as cnt,
                   MIN(pm.date_taken) as first_date
            FROM files f
            JOIN photo_metadata pm ON f.id = pm.file_id
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE f.is_image = 1
              AND """ + category_match_sql(CATEGORY_LIFE) + """
              AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
              AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
            GROUP BY f.folder_path
            HAVING cnt >= 3
            ORDER BY cnt DESC
            LIMIT ?
        """, (CATEGORY_LIFE, top_n)).fetchall()

    if not rows:
        return []

    memories = []
    for folder_path, folder_name, cnt, first_date in rows:
        with db.connect() as conn:
            file_rows = conn.execute("""
                SELECT f.id FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.folder_path = ?
                  AND f.is_image = 1
                  AND (pm.is_duplicate_of IS NULL OR pm.is_duplicate_of = 0)
                  AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
                ORDER BY pm.date_taken DESC
                LIMIT 20
            """, (folder_path,)).fetchall()
        photo_ids = [r[0] for r in file_rows]
        if not photo_ids:
            continue

        display_name = folder_name or os.path.basename(folder_path)
        title = f"{display_name} · {cnt}张"

        existing = _find_existing_memory(memories_repo, "folder", folder_path)
        if existing:
            continue

        m = Memory(
            category=CATEGORY_LIFE,
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


def discover_person_memories(threshold: int = 3) -> List[Memory]:
    """发现人物回忆：基于人脸聚类生成每人物的回忆卡片"""
    from infra.db.repositories.face_clusters_repo import FaceClustersRepository
    from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository

    db = Database()
    clusters_repo = FaceClustersRepository(db)
    embeddings_repo = FaceEmbeddingsRepository(db)
    memories_repo = MemoriesRepository(db)

    clusters = clusters_repo.get_all()
    if not clusters:
        return []

    memories = []
    for cluster in clusters:
        file_ids = embeddings_repo.get_file_ids_by_cluster(cluster.cluster_id)
        if not file_ids or len(file_ids) < threshold:
            continue

        # 检查是否已存在
        existing = _find_existing_memory(memories_repo, "person", str(cluster.cluster_id))
        if existing:
            continue

        person_name = cluster.person_name or f"一位朋友 · {len(file_ids)}张照片"
        photo_ids = file_ids[:20]  # 限制 20 张
        # 只保留生活样片分类的照片
        photo_ids = _filter_life_photos(photo_ids)
        if not photo_ids or len(photo_ids) < threshold:
            continue

        m = Memory(
            category=CATEGORY_LIFE,
            memory_type="person",
            title=person_name,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0],
            payload=json.dumps({"cluster_id": cluster.cluster_id}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)
        logger.info(f"人物回忆: {person_name}, {len(photo_ids)} 张")

    logger.info(f"人物回忆发现 {len(memories)} 组")
    return memories


def discover_scene_memories(threshold: int = 5) -> List[Memory]:
    """发现场景回忆：基于 SigLIP 标签聚合生成场景回忆"""
    from infra.db.repositories.photo_tags_repo import PhotoTagsRepository

    db = Database()
    tags_repo = PhotoTagsRepository(db)
    memories_repo = MemoriesRepository(db)

    # 获取所有 siglip 标签及其关联的照片
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT tag, COUNT(*) as cnt, GROUP_CONCAT(file_id) as file_ids
            FROM photo_tags
            WHERE source = 'siglip'
            GROUP BY tag
            HAVING cnt >= ?
            ORDER BY cnt DESC
            LIMIT 20
        """, (threshold,)).fetchall()

    if not rows:
        return []

    memories = []
    for tag, cnt, file_ids_str in rows:
        if not file_ids_str:
            continue
        file_ids = [int(x) for x in file_ids_str.split(",")]
        if len(file_ids) < threshold:
            continue

        existing = _find_existing_memory(memories_repo, "scene", str(tag))
        if existing:
            continue

        title = f"场景: {tag}"
        photo_ids = file_ids[:20]
        # 只保留生活样片分类的照片
        photo_ids = _filter_life_photos(photo_ids)
        if len(photo_ids) < threshold:
            continue

        m = Memory(
            category=CATEGORY_LIFE,
            memory_type="scene",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0],
            payload=json.dumps({"scene_tag": tag, "count": cnt}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)
        logger.info(f"场景回忆: {tag}, {len(photo_ids)} 张")

    logger.info(f"场景回忆发现 {len(memories)} 组")
    return memories


def _parse_date_taken(value: str) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt)], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _split_temporal_segments(photos, max_gap_days: int = MAX_EVENT_GAP_DAYS, max_span_days: int = MAX_EVENT_SPAN_DAYS):
    segments = []
    current = []
    current_start = None
    previous_dt = None

    for photo in sorted(photos, key=lambda p: p[1] or ""):
        dt = _parse_date_taken(photo[1])
        if dt is None:
            continue

        should_break = False
        if current and previous_dt is not None and (dt.date() - previous_dt.date()).days > max_gap_days:
            should_break = True
        if current and current_start is not None and (dt.date() - current_start.date()).days >= max_span_days:
            should_break = True

        if should_break:
            segments.append(current)
            current = []
            current_start = None

        if not current:
            current_start = dt
        current.append(photo)
        previous_dt = dt

    if current:
        segments.append(current)
    return segments


def _build_event_segments(rows, gps_delta: float = 0.01, max_gap_days: int = MAX_EVENT_GAP_DAYS, max_span_days: int = MAX_EVENT_SPAN_DAYS):
    events = {}
    for file_id, date_taken, lat, lon in rows:
        lat_r = round(lat / gps_delta) * gps_delta
        lon_r = round(lon / gps_delta) * gps_delta
        key = (lat_r, lon_r)
        events.setdefault(key, []).append((file_id, date_taken))

    segments = []
    for (lat_r, lon_r), photos in events.items():
        for segment in _split_temporal_segments(photos, max_gap_days=max_gap_days, max_span_days=max_span_days):
            if not segment:
                continue
            dates = [p[1][:10] for p in segment if p[1]]
            if not dates:
                continue
            start_date = min(dates)
            end_date = max(dates)
            segments.append({
                "location_key": f"{lat_r},{lon_r}",
                "start_date": start_date,
                "end_date": end_date,
                "photos": segment,
                "unique_dates": sorted(set(dates)),
            })
    return segments


def _location_key(lat: float, lon: float, gps_delta: float) -> str:
    lat_r = round(lat / gps_delta) * gps_delta
    lon_r = round(lon / gps_delta) * gps_delta
    return f"{lat_r},{lon_r}"


def _build_trip_segments(rows, gps_delta: float = 0.01, max_gap_days: int = MAX_EVENT_GAP_DAYS, max_span_days: int = MAX_EVENT_SPAN_DAYS):
    dated = []
    for file_id, date_taken, lat, lon in rows:
        dt = _parse_date_taken(date_taken)
        if dt is None:
            continue
        dated.append((file_id, date_taken, lat, lon, dt, _location_key(lat, lon, gps_delta)))

    segments = []
    current = []
    current_start = None
    previous_dt = None
    for item in sorted(dated, key=lambda p: p[4]):
        dt = item[4]
        should_break = False
        if current and previous_dt is not None and (dt.date() - previous_dt.date()).days > max_gap_days:
            should_break = True
        if current and current_start is not None and (dt.date() - current_start.date()).days >= max_span_days:
            should_break = True

        if should_break:
            segments.append(current)
            current = []
            current_start = None

        if not current:
            current_start = dt
        current.append(item)
        previous_dt = dt

    if current:
        segments.append(current)

    trip_segments = []
    for segment in segments:
        dates = [p[1][:10] for p in segment if p[1]]
        location_keys = sorted({p[5] for p in segment})
        if len(set(dates)) < 2 or len(location_keys) < 3:
            continue
        start_date = min(dates)
        end_date = max(dates)
        trip_segments.append({
            "event_key": f"trip|{start_date}|{end_date}|{'/'.join(location_keys[:4])}",
            "start_date": start_date,
            "end_date": end_date,
            "photos": [(p[0], p[1]) for p in segment],
            "unique_dates": sorted(set(dates)),
            "location_keys": location_keys,
        })
    return trip_segments


def discover_event_memories(threshold: int = 5, gps_delta: float = 0.01) -> List[Memory]:
    """发现事件回忆：基于 GPS 坐标 + 时间断裂聚合同地点事件"""
    db = Database()
    memories_repo = MemoriesRepository(db)

    # 获取有 GPS 的照片，按时间排序
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT pm.file_id, pm.date_taken, pm.gps_lat, pm.gps_lon
            FROM photo_metadata pm
            WHERE pm.gps_lat IS NOT NULL AND pm.gps_lon IS NOT NULL
              AND pm.date_taken IS NOT NULL
              AND pm.thumbnail_path IS NOT NULL AND pm.thumbnail_path != '__FAILED__'
            ORDER BY pm.date_taken ASC
        """).fetchall()

    if not rows:
        return []

    memories = []
    trip_photo_ids = set()
    for trip in _build_trip_segments(rows, gps_delta=gps_delta):
        photos = trip["photos"]
        if len(photos) < threshold:
            continue

        existing = _find_existing_memory(memories_repo, "event", trip["event_key"])
        if existing:
            continue

        file_ids = _filter_life_photos([p[0] for p in photos])
        if len(file_ids) < threshold:
            continue
        file_ids = file_ids[:MAX_MEMORY_PHOTOS]
        trip_photo_ids.update(file_ids)

        start_date = trip["start_date"]
        end_date = trip["end_date"]
        unique_dates = trip["unique_dates"]
        title = f"{start_date[:7]} 旅行"
        if len(unique_dates) > 1:
            title += f" ({len(unique_dates)}天)"

        m = Memory(
            category=CATEGORY_LIFE,
            memory_type="event",
            title=title,
            photo_ids=json.dumps(file_ids),
            cover_file_id=file_ids[0],
            payload=json.dumps({
                "event_key": trip["event_key"],
                "event_type": "trip",
                "start_date": start_date,
                "end_date": end_date,
                "location_count": len(trip["location_keys"]),
            }),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)
        logger.info(f"旅行回忆: {title}, {len(file_ids)} 张, 位置={len(trip['location_keys'])}")

    for segment in _build_event_segments(rows, gps_delta=gps_delta):
        photos = segment["photos"]
        if len(photos) < threshold:
            continue

        unique_dates = segment["unique_dates"]
        if len(unique_dates) < 1:
            continue

        # 检查是否已存在
        location_key = segment["location_key"]
        start_date = segment["start_date"]
        end_date = segment["end_date"]
        event_key = f"{location_key}|{start_date}|{end_date}"
        existing = _find_existing_memory(memories_repo, "event", event_key)
        if existing:
            continue

        file_ids = [p[0] for p in photos]
        if trip_photo_ids and len(set(file_ids) & trip_photo_ids) / max(1, len(file_ids)) > 0.6:
            continue
        # 只保留生活样片分类的照片
        file_ids = _filter_life_photos(file_ids)
        if len(file_ids) < threshold:
            continue
        file_ids = file_ids[:MAX_MEMORY_PHOTOS]

        # 判断是否为 trip（跨多天且 ≥3天）
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days
            event_type = "trip" if 2 <= days_diff <= MAX_EVENT_SPAN_DAYS else "event"
        except:
            event_type = "event"

        title = f"{start_date[:7]} 回忆" if event_type == "event" else f"{start_date[:7]} 旅行"
        if len(unique_dates) > 1:
            title += f" ({len(unique_dates)}天)"

        m = Memory(
            category=CATEGORY_LIFE,
            memory_type="event",
            title=title,
            photo_ids=json.dumps(file_ids),
            cover_file_id=file_ids[0],
            payload=json.dumps({
                "event_key": event_key,
                "event_type": event_type,
                "gps_cluster": location_key,
                "start_date": start_date,
                "end_date": end_date,
            }),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)
        logger.info(f"事件回忆: {title}, {len(file_ids)} 张, 类型={event_type}")

    logger.info(f"事件回忆发现 {len(memories)} 组")
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
            if "event_key" in payload and payload["event_key"] == payload_key:
                return mid
            if "gps_cluster" in payload and payload["gps_cluster"] == payload_key:
                return mid
            if "scene_cluster_idx" in payload and str(payload["scene_cluster_idx"]) == payload_key:
                return mid
            if "folder_path" in payload and payload["folder_path"] == payload_key:
                return mid
        except Exception:
            continue
    return None
