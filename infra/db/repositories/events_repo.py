from typing import List, Optional, Tuple
from core.models import Event


PhotoEventRow = Tuple[int, Optional[str], Optional[float], Optional[float], Optional[int]]


class EventsRepository:
    def __init__(self, db):
        self.db = db

    def get_photos_for_event_detection(self) -> List[PhotoEventRow]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id, pm.date_taken, pm.gps_lat, pm.gps_lon, fc.category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL
                ORDER BY pm.date_taken ASC
            """).fetchall()
        return rows

    def insert(self, event: Event) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO events
                (start_date, end_date, gps_cluster, location_name, photo_ids, event_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event.start_date, event.end_date, event.gps_cluster,
                  event.location_name, event.photo_ids, event.event_type))
            return result.lastrowid

    def get_all(self) -> List[Event]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT event_id, start_date, end_date, gps_cluster,
                       location_name, photo_ids, event_type
                FROM events ORDER BY start_date DESC
            """).fetchall()
        return [
            Event(
                event_id=r[0], start_date=r[1], end_date=r[2], gps_cluster=r[3],
                location_name=r[4], photo_ids=r[5], event_type=r[6]
            )
            for r in rows
        ]

    def get_by_id(self, event_id: int) -> Optional[Event]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT event_id, start_date, end_date, gps_cluster,
                       location_name, photo_ids, event_type
                FROM events WHERE event_id = ?
            """, (event_id,)).fetchone()
        if row:
            return Event(
                event_id=row[0], start_date=row[1], end_date=row[2], gps_cluster=row[3],
                location_name=row[4], photo_ids=row[5], event_type=row[6]
            )
        return None

    def delete(self, event_id: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
