import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from logger_setup import logger
from db_manager import Database
from core.models import FaceCluster, FaceEmbedding
from infra.db.repositories.face_clusters_repo import FaceClustersRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository
from business.image_recognition._clustering import greedy_cluster

_DISTANCE_THRESHOLD = 0.6


def cluster_faces(embeddings: List[Tuple[int, np.ndarray]], threshold: float = _DISTANCE_THRESHOLD) -> Dict[int, int]:
    if not embeddings:
        return {}

    db = Database()
    clusters_repo = FaceClustersRepository(db)

    clusters = greedy_cluster(embeddings, metric="euclidean", threshold=threshold)

    file_to_cluster = {}
    for cluster_idx, cluster in enumerate(clusters):
        representative_id = cluster[0][0]
        emb_data = [(file_id, emb.astype(np.float32).tobytes()) for file_id, emb in cluster]

        cluster_id = clusters_repo.insert_with_embeddings("", representative_id, emb_data)

        for file_id, _ in cluster:
            file_to_cluster[file_id] = cluster_id

    logger.info(f"人脸聚类完成: {len(embeddings)} 个嵌入 -> {len(clusters)} 个聚类")
    return file_to_cluster


def get_clusters() -> List[FaceCluster]:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    return clusters_repo.get_all()


def get_cluster_members(cluster_id: int) -> List[int]:
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    return embeddings_repo.get_file_ids_by_cluster(cluster_id)


def rename_cluster(cluster_id: int, name: str):
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    clusters_repo.update_name(cluster_id, name)
    logger.info(f"聚类 {cluster_id} 命名为: {name}")


def reassign_face(embedding_id: int, new_cluster_id: int):
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)


def create_cluster_from_face(embedding_id: int, person_name: str = "") -> int:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    embeddings_repo = FaceEmbeddingsRepository(db)

    cluster = FaceCluster(person_name=person_name, representative_face=embedding_id)
    new_cluster_id = clusters_repo.insert(cluster)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)
    return new_cluster_id


def get_person_memories() -> Dict[str, List[int]]:
    clusters = get_clusters()
    result = {}
    for c in clusters:
        name = c.person_name or f"人物{c.cluster_id}"
        members = get_cluster_members(c.cluster_id)
        if members:
            result[name] = members
    return result


def recluster_all(threshold: float = _DISTANCE_THRESHOLD) -> Dict[int, int]:
    """读取 DB 中所有嵌入，清空旧聚类，重新聚类并更新 cluster_id"""
    db = Database()
    clusters_repo = FaceClustersRepository(db)

    with db.connect() as conn:
        rows = conn.execute("SELECT id, file_id, embedding FROM face_embeddings").fetchall()

    if not rows:
        logger.info("重聚类跳过：face_embeddings 表为空")
        return {}

    items = [(r[0], np.frombuffer(r[2], dtype=np.float32)) for r in rows]

    # 清空旧聚类
    with db.connect() as conn:
        conn.execute("UPDATE face_embeddings SET cluster_id = NULL")
        conn.execute("DELETE FROM face_clusters")

    clusters = greedy_cluster(
        [(emb_id, emb) for emb_id, _ in items],
        metric="euclidean",
        threshold=threshold,
    )

    file_to_cluster: Dict[int, int] = {}
    for cluster in clusters:
        representative_emb_id = cluster[0][0]
        # 找到该嵌入对应的 file_id，作为聚类的代表照片
        rep_file_id = None
        for emb_id, file_id, _ in rows:
            if emb_id == representative_emb_id:
                rep_file_id = file_id
                break

        cluster_id = clusters_repo.insert(FaceCluster(person_name="", representative_face=rep_file_id))

        emb_ids = [emb_id for emb_id, _ in cluster]
        with db.connect() as conn:
            for emb_id in emb_ids:
                conn.execute(
                    "UPDATE face_embeddings SET cluster_id = ? WHERE id = ?",
                    (cluster_id, emb_id),
                )

        for emb_id, _ in cluster:
            for row_emb_id, row_file_id, _ in rows:
                if row_emb_id == emb_id:
                    file_to_cluster[row_file_id] = cluster_id

    logger.info(f"人脸重聚类完成: {len(rows)} 个嵌入 -> {len(clusters)} 个聚类")
    return file_to_cluster
