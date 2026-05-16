import json
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from collections import defaultdict

from logger_setup import logger
from db_manager import Database
from core.models import Event
from infra.db.repositories.events_repo import EventsRepository

_TIME_GAP_HOURS = 6
_GPS_CLUSTER_RADIUS_KM = 0.5


def detect_events() -> List[Event]:
    db = Database()
    events_repo = EventsRepository(db)

    rows = events_repo.get_photos_for_event_detection()
    if not rows:
        return []

    segments = _segment_by_time(rows)
    events = []

    for segment in segments:
        sub_segments = _sub_segment_by_gps(segment)
        for sub in sub_segments:
            photo_ids = [r[0] for r in sub]
            start_date = sub[0][1][:10]
            end_date = sub[-1][1][:10]
            gps_lat = sub[0][2]
            gps_lon = sub[0][3]
            category = sub[0][4] or 1

            gps_cluster = None
            if gps_lat is not None and gps_lon is not None:
                gps_cluster = f"{gps_lat:.2f},{gps_lon:.2f}"

            event_type = "travel" if start_date != end_date else "event"

            e = Event(
                start_date=start_date,
                end_date=end_date,
                gps_cluster=gps_cluster,
                photo_ids=json.dumps(photo_ids[:50]),
                event_type=event_type,
            )

            e.event_id = events_repo.insert(e)
            events.append(e)

    logger.info(f"事件检测完成: {len(events)} 个事件")
    return events


def _segment_by_time(rows) -> List[List[tuple]]:
    if not rows:
        return []

    segments = []
    current = [rows[0]]

    for i in range(1, len(rows)):
        prev_date = _parse_date(rows[i - 1][1])
        curr_date = _parse_date(rows[i][1])

        if prev_date and curr_date:
            gap = curr_date - prev_date
            if gap > timedelta(hours=_TIME_GAP_HOURS):
                segments.append(current)
                current = [rows[i]]
                continue

        current.append(rows[i])

    if current:
        segments.append(current)

    return segments


def _sub_segment_by_gps(segment) -> List[List[tuple]]:
    has_gps = any(r[2] is not None and r[3] is not None for r in segment)
    if not has_gps:
        return [segment]

    sub_segments = []
    current = [segment[0]]

    for i in range(1, len(segment)):
        prev_lat, prev_lon = segment[i - 1][2], segment[i - 1][3]
        curr_lat, curr_lon = segment[i][2], segment[i][3]

        if prev_lat is not None and prev_lon is not None and curr_lat is not None and curr_lon is not None:
            dist = _haversine_km(prev_lat, prev_lon, curr_lat, curr_lon)
            if dist > _GPS_CLUSTER_RADIUS_KM * 10:
                sub_segments.append(current)
                current = [segment[i]]
                continue

        current.append(segment[i])

    if current:
        sub_segments.append(current)

    return sub_segments


def _parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    from math import radians, sin, cos, sqrt, asin
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * asin(sqrt(a))


def get_events() -> List[Event]:
    db = Database()
    events_repo = EventsRepository(db)
    return events_repo.get_all()
