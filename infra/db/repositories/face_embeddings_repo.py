from typing import List, Optional
from core.models import FaceEmbedding


class FaceEmbeddingsRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, embedding: FaceEmbedding) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_embeddings
                (file_id, embedding, cluster_id)
                VALUES (?, ?, ?)
            """, (embedding.file_id, embedding.embedding, embedding.cluster_id))
            return result.lastrowid

    def get_by_file_id(self, file_id: int) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE file_id = ?
            """, (file_id,)).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_by_cluster_id(self, cluster_id: int) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE cluster_id = ?
            """, (cluster_id,)).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_file_ids_by_cluster(self, cluster_id: int) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT file_id FROM face_embeddings WHERE cluster_id = ?",
                (cluster_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def update_cluster(self, embedding_id: int, cluster_id: Optional[int]):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE face_embeddings SET cluster_id = ? WHERE id = ?
            """, (cluster_id, embedding_id))

    def get_all_unclustered(self) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE cluster_id IS NULL
            """).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_existing_file_ids(self) -> set:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT file_id FROM face_embeddings").fetchall()
        return {r[0] for r in rows}
