from typing import List, Optional, Tuple

import numpy as np
from core.models import FaceCluster


class FaceClustersRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, cluster: FaceCluster) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_clusters
                (person_name, user_corrected, representative_face)
                VALUES (?, ?, ?)
            """, (cluster.person_name, cluster.user_corrected,
                  cluster.representative_face))
            return result.lastrowid

    def insert_with_embeddings(self, person_name: str, representative_face: int,
                               embeddings: List[Tuple[int, bytes]]) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_clusters
                (person_name, user_corrected, representative_face, created_at)
                VALUES (?, 0, ?, datetime('now'))
            """, (person_name, representative_face))
            cluster_id = result.lastrowid

            for file_id, emb_bytes in embeddings:
                conn.execute(
                    "INSERT INTO face_embeddings (file_id, embedding, cluster_id) VALUES (?, ?, ?)",
                    (file_id, emb_bytes, cluster_id)
                )

            return cluster_id

    def get_all(self) -> List[FaceCluster]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT cluster_id, person_name, user_corrected,
                       representative_face, created_at
                FROM face_clusters ORDER BY created_at DESC
            """).fetchall()
        return [
            FaceCluster(
                cluster_id=r[0], person_name=r[1], user_corrected=r[2],
                representative_face=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_by_id(self, cluster_id: int) -> Optional[FaceCluster]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT cluster_id, person_name, user_corrected,
                       representative_face, created_at
                FROM face_clusters WHERE cluster_id = ?
            """, (cluster_id,)).fetchone()
        if row:
            return FaceCluster(
                cluster_id=row[0], person_name=row[1], user_corrected=row[2],
                representative_face=row[3], created_at=row[4]
            )
        return None

    def update_name(self, cluster_id: int, person_name: str, user_corrected: int = 1):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE face_clusters
                SET person_name = ?, user_corrected = ?
                WHERE cluster_id = ?
            """, (person_name, user_corrected, cluster_id))

    def delete(self, cluster_id: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM face_clusters WHERE cluster_id = ?", (cluster_id,))
